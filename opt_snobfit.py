"""
SNOBFIT (Stable Noisy Optimization by Branch and FIT) Wrapper

This module provides a unified interface for SNOBFIT that fits
the ask/tell pattern required by the gsopt API.
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from SQSnobFit import snobfit

from utils import setup_logging

logger = setup_logging(__name__)


class SnobfitOptimizer:
    """Wrapper for SNOBFIT optimizer with ask/tell interface."""
    
    def __init__(
        self,
        param_names: List[str],
        param_mins: List[float],
        param_maxes: List[float],
        n_initial_points: int = 10
    ):
        """
        Initialize the SNOBFIT optimizer.
        
        Args:
            param_names: List of parameter names
            param_mins: List of minimum values for each parameter
            param_maxes: List of maximum values for each parameter
            n_initial_points: Number of initial points (used for request calculation)
        """
        self.param_names = param_names
        self.param_mins = np.array(param_mins)
        self.param_maxes = np.array(param_maxes)
        self.n_dims = len(param_names)
        self.n_initial_points = n_initial_points
        
        # SNOBFIT bounds format: (n_dim, 2) where col 0 is min, col 1 is max
        # We receive mins and maxes as lists, so we need to column_stack them
        self.bounds = np.column_stack((param_mins, param_maxes))
        
        # State tracking
        self.x_data = []  # List of evaluated points
        self.y_data = []  # List of objective values
        self.request = None  # Current request from SNOBFIT
        self.iteration = 0
        
        logger.info(f"Created SNOBFIT optimizer with {self.n_dims} dimensions")
        logger.info(f"Parameters: {param_names}")
        logger.info(f"Bounds shape: {self.bounds.shape}")
    
    def ask(self, n_points: int = 1) -> List[List[float]]:
        """
        Ask the optimizer for the next point(s) to evaluate.
        
        Args:
            n_points: Number of points to generate
            
        Returns:
            List of parameter value lists
        """
        if len(self.x_data) == 0:
            # First iteration or no data: generate random initial points
            logger.info(f"Generating {n_points} initial points (random)")
            points = []
            for _ in range(n_points):
                # Generate random points respecting bounds
                point = np.random.uniform(self.bounds[:, 0], self.bounds[:, 1])
                points.append(list(point))
            logger.info(f"Generated {len(points)} random initial points")
            self.iteration += 1
            return points
        else:
            # Subsequent iterations: use SNOBFIT with existing data
            logger.info(f"Generating {n_points} new points based on {len(self.x_data)} evaluated points")
            
            # Convert data to format expected by snobfit
            if isinstance(self.x_data, list):
                x_data = np.array(self.x_data) if self.x_data else np.empty((0, self.n_dims))
                # y_data needs to be (n, 2) for value and uncertainty
                if self.y_data:
                    vals = np.array(self.y_data).reshape(-1, 1)
                    # Add small uncertainty (sqrt(eps)) as default
                    uncertainty = np.full_like(vals, np.sqrt(np.finfo(float).eps))
                    y_data = np.hstack((vals, uncertainty))
                else:
                    y_data = np.empty((0, 2))
            else:
                x_data = self.x_data
                # Ensure y_data is (n, 2)
                if self.y_data.ndim == 1:
                    vals = self.y_data.reshape(-1, 1)
                    uncertainty = np.full_like(vals, np.sqrt(np.finfo(float).eps))
                    y_data = np.hstack((vals, uncertainty))
                elif self.y_data.shape[1] == 1:
                    vals = self.y_data
                    uncertainty = np.full_like(vals, np.sqrt(np.finfo(float).eps))
                    y_data = np.hstack((vals, uncertainty))
                else:
                    y_data = self.y_data
            
            # Create config dictionary as expected by snobfit
            config = {
                "bounds": self.bounds,
                "nreq": n_points,
                "p": 0.5  # Default probability of generating Type 4 points
            }
            
            # Calculate dx (resolution) to force stateless execution
            # This treats every call as a "new job" with the full history, 
            # preventing reliance on SQSnobFit's internal global state.
            dx = (self.bounds[:, 1] - self.bounds[:, 0]) * 1e-5
            
            # Call snobfit
            request, x_new, f_best = snobfit(
                x_data,
                y_data,
                config,
                dx=dx
            )
            
            # Take only the requested number of points
            # request contains [x, f_est, type]
            # We only need x (first n_dims columns)
            suggested_points = request[:, :self.n_dims]
            
            # Handle case where snobfit returns fewer points than requested
            if len(suggested_points) < n_points:
                num_missing = n_points - len(suggested_points)
                logger.warning(f"SNOBFIT returned only {len(suggested_points)} points, filling {num_missing} with random points")
                random_points = np.random.uniform(self.bounds[:, 0], self.bounds[:, 1], (num_missing, self.n_dims))
                suggested_points = np.vstack((suggested_points, random_points))
            
            if len(suggested_points) > n_points:
                suggested_points = suggested_points[:n_points]
            
            self.request = request
            self.iteration += 1
            
            # Convert to list format
            points = [list(point) for point in suggested_points]
            logger.info(f"Generated {len(points)} points")
            
            return points
    
    def tell(self, x_data: List[List[float]], y_data: List[float]) -> None:
        """
        Tell the optimizer about evaluated points.
        
        Args:
            x_data: List of parameter value lists
            y_data: List of objective values
        """
        if not x_data or not y_data:
            logger.warning("No data provided to tell()")
            return
        
        # Convert to numpy arrays
        x_array = np.array(x_data)
        y_array = np.array(y_data).reshape(-1, 1)
        
        # Store data
        if len(self.x_data) == 0:
            self.x_data = x_array
            self.y_data = y_array
        else:
            self.x_data = np.vstack([self.x_data, x_array])
            self.y_data = np.vstack([self.y_data, y_array])
        
        logger.info(f"Training optimizer with {len(x_data)} new points")
        logger.info(f"Total points: {len(self.x_data)}, Objective range: min={np.min(self.y_data):.4f}, max={np.max(self.y_data):.4f}")
    
    def get_name(self) -> str:
        """Return the name of this optimizer."""
        return "SNOBFIT"


def parse_training_data(
    existing_data: List[Dict[str, Any]],
    param_names: List[str]
) -> Tuple[List[List[float]], List[float]]:
    """
    Extracts and validates training data from existing data points.
    
    Args:
        existing_data: List of data points with parameter values and objectives
        param_names: Ordered list of parameter names
        
    Returns:
        Tuple of (X_train, y_train) where X_train is parameter values and 
        y_train is objective values
    """
    x_train = []
    y_train = []
    
    logger.info(f"Processing {len(existing_data)} existing data points")
    
    for i, row in enumerate(existing_data):
        if 'objective' not in row or row['objective'] is None or row['objective'] == '':
            logger.debug(f"Skipping row {i}: no objective value")
            continue
        
        try:
            x_point = [float(row.get(name, 0)) for name in param_names]
            y_value = float(row['objective'])
            x_train.append(x_point)
            y_train.append(y_value)
            logger.debug(f"Added point {i}: params={x_point}, objective={y_value}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Skipping invalid data point {i}: {row}, error: {e}")
            continue
    
    if x_train:
        logger.info(f"Extracted {len(x_train)} valid training points")
    else:
        logger.warning("No valid evaluated points found")
    
    return x_train, y_train


def build_optimizer(
    param_names: List[str],
    param_mins: List[float],
    param_maxes: List[float],
    existing_data: Optional[List[Dict[str, Any]]] = None
) -> SnobfitOptimizer:
    """
    Creates and optionally trains a SNOBFIT optimizer.
    
    Args:
        param_names: List of parameter names
        param_mins: List of minimum values for each parameter
        param_maxes: List of maximum values for each parameter
        existing_data: Optional list of evaluated points for training
        
    Returns:
        Configured and trained SnobfitOptimizer instance
    """
    optimizer = SnobfitOptimizer(
        param_names=param_names,
        param_mins=param_mins,
        param_maxes=param_maxes
    )
    
    if existing_data:
        x_train, y_train = parse_training_data(existing_data, param_names)
        if x_train:
            optimizer.tell(x_train, y_train)
            logger.info("Successfully trained optimizer with existing data")
    
    return optimizer
