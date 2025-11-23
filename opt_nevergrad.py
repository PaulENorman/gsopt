"""
Nevergrad Optimizer Wrapper

This module provides a unified interface for Nevergrad that fits
the ask/tell pattern required by the gsopt API.
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import nevergrad as ng

from utils import setup_logging

logger = setup_logging(__name__)


class NevergradOptimizer:
    """Wrapper for Nevergrad optimizer with ask/tell interface."""
    
    def __init__(
        self,
        param_names: List[str],
        param_mins: List[float],
        param_maxes: List[float],
        optimizer_name: str = "OnePlusOne",
        budget: int = 1000
    ):
        """
        Initialize the Nevergrad optimizer.
        
        Args:
            param_names: List of parameter names
            param_mins: List of minimum values for each parameter
            param_maxes: List of maximum values for each parameter
            optimizer_name: Name of the Nevergrad optimizer to use (default: OnePlusOne)
            budget: Estimated total budget for optimization
        """
        self.param_names = param_names
        self.n_dims = len(param_names)
        
        # Create parametrization with bounds
        # We use a single Array parameter for simplicity in vector handling
        self.parametrization = ng.p.Array(shape=(self.n_dims,))
        self.parametrization.set_bounds(lower=np.array(param_mins), upper=np.array(param_maxes))
        
        # Initialize optimizer
        # Note: In a stateless context, we'll re-create this and replay data
        self.optimizer_name = optimizer_name
        self.budget = budget
        
        # Store history for stateless operation
        self.x_history = []
        self.y_history = []
        
        # Create optimizer with num_workers=1 (no parallelization for Flask)
        self.optimizer = self._create_optimizer()
        
        logger.info(f"Created Nevergrad optimizer ({optimizer_name}) with {self.n_dims} dimensions")
    
    def _create_optimizer(self):
        """Create a fresh optimizer instance."""
        optimizer_class = ng.optimizers.registry[self.optimizer_name]
        return optimizer_class(
            parametrization=self.parametrization, 
            budget=self.budget,
            num_workers=1  # Critical: disable parallelization for Flask
        )
    
    def _replay_history(self):
        """Recreate optimizer and replay all historical data."""
        if not self.x_history:
            return
        
        logger.info(f"Recreating optimizer and replaying {len(self.x_history)} historical points")
        
        # Create fresh optimizer
        self.optimizer = self._create_optimizer()
        
        # Replay all historical evaluations
        for x, y in zip(self.x_history, self.y_history):
            # Create a candidate from the parameter values using spawn_child
            # This avoids the "frozen parameter" error that occurs when modifying an asked candidate
            candidate = self.parametrization.spawn_child(new_value=np.array(x))
            self.optimizer.tell(candidate, y)
        
        try:
            logger.debug(f"History replay complete. Best value: {self.optimizer.current_bests['pessimistic'].mean}")
        except Exception:
            pass
    
    def ask(self, n_points: int = 1) -> List[List[float]]:
        """
        Ask the optimizer for the next point(s) to evaluate.
        
        Args:
            n_points: Number of points to generate
            
        Returns:
            List of parameter value lists
        """
        # Replay history to ensure optimizer has latest information
        self._replay_history()
        
        logger.info(f"Asking for {n_points} points from Nevergrad")
        points = []
        
        for i in range(n_points):
            try:
                candidate = self.optimizer.ask()
                # candidate.value is a numpy array
                points.append(candidate.value.tolist())
                logger.debug(f"Generated point {i+1}/{n_points}: {candidate.value}")
            except Exception as e:
                logger.error(f"Error generating point {i+1}: {e}")
                raise
            
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
        
        logger.info(f"Storing {len(x_data)} points in history")
        
        # Store all points in history
        self.x_history.extend(x_data)
        self.y_history.extend(y_data)
        
        logger.info(f"Total historical points: {len(self.x_history)}")
        if self.y_history:
            best_y = min(self.y_history)
            logger.info(f"Best objective in history: {best_y}")
    
    def get_name(self) -> str:
        """Return the name of this optimizer."""
        return f"Nevergrad-{self.optimizer_name}"


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
    
    for i, row in enumerate(existing_data):
        if 'objective' not in row or row['objective'] is None or row['objective'] == '':
            continue
        
        try:
            x_point = [float(row.get(name, 0)) for name in param_names]
            y_value = float(row['objective'])
            x_train.append(x_point)
            y_train.append(y_value)
        except (ValueError, TypeError):
            continue
    
    return x_train, y_train


def build_optimizer(
    param_names: List[str],
    param_mins: List[float],
    param_maxes: List[float],
    optimizer_name: str = "OnePlusOne",
    existing_data: Optional[List[Dict[str, Any]]] = None
) -> NevergradOptimizer:
    """
    Creates and optionally trains a Nevergrad optimizer.
    
    Args:
        param_names: List of parameter names
        param_mins: List of minimum values for each parameter
        param_maxes: List of maximum values for each parameter
        optimizer_name: Name of the Nevergrad optimizer (e.g., 'OnePlusOne', 'DE', 'TwoPointsDE')
        existing_data: Optional list of evaluated points for training
        
    Returns:
        Configured and trained NevergradOptimizer instance
    """
    # Map generic names to specific algorithms
    name_mapping = {
        'NEVERGRAD': 'OnePlusOne',
        'NGOPT': 'OnePlusOne',  # NGOpt may have parallelization issues
    }
    optimizer_name = name_mapping.get(optimizer_name.upper(), optimizer_name)
        
    optimizer = NevergradOptimizer(
        param_names=param_names,
        param_mins=param_mins,
        param_maxes=param_maxes,
        optimizer_name=optimizer_name
    )
    
    if existing_data:
        x_train, y_train = parse_training_data(existing_data, param_names)
        if x_train:
            optimizer.tell(x_train, y_train)
            logger.info("Successfully trained optimizer with existing data")
    
    return optimizer
