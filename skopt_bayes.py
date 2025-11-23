"""
Scikit-Optimize Bayesian Optimization Wrapper

This module provides a unified interface for scikit-optimize that fits
the ask/tell pattern required by the gsopt API.
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from skopt import Optimizer
from skopt.space import Real

from utils import setup_logging

logger = setup_logging(__name__)


class SkoptBayesianOptimizer:
    """Wrapper for scikit-optimize Bayesian Optimizer."""
    
    def __init__(
        self,
        param_names: List[str],
        param_mins: List[float],
        param_maxes: List[float],
        base_estimator: str = 'GP',
        acquisition_function: str = 'EI',
        n_initial_points: int = 5
    ):
        """
        Initialize the scikit-optimize Bayesian optimizer.
        
        Args:
            param_names: List of parameter names
            param_mins: List of minimum values for each parameter
            param_maxes: List of maximum values for each parameter
            base_estimator: Base estimator type ('GP', 'RF', 'ET', 'GBRT')
            acquisition_function: Acquisition function ('EI', 'LCB', 'PI', 'gp_hedge')
            n_initial_points: Number of random initial points
        """
        self.param_names = param_names
        self.param_mins = param_mins
        self.param_maxes = param_maxes
        
        # Create search space
        dimensions = [
            Real(param_mins[i], param_maxes[i], name=name)
            for i, name in enumerate(param_names)
        ]
        
        logger.info(f"Created search space with {len(dimensions)} dimensions")
        logger.info(f"Parameters: {param_names}")
        
        # Initialize optimizer
        self.optimizer = Optimizer(
            dimensions,
            base_estimator=base_estimator,
            acq_func=acquisition_function,
            n_initial_points=n_initial_points
        )
        
        logger.info(f"Initialized scikit-optimize: estimator={base_estimator}, acq_func={acquisition_function}")
    
    def ask(self, n_points: int = 1) -> List[List[float]]:
        """
        Ask the optimizer for the next point(s) to evaluate.
        
        Args:
            n_points: Number of points to generate
            
        Returns:
            List of parameter value lists
        """
        points = self.optimizer.ask(n_points=n_points)
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
        
        logger.info(f"Training optimizer with {len(x_data)} points")
        logger.info(f"Objective range: min={min(y_data):.4f}, max={max(y_data):.4f}, mean={np.mean(y_data):.4f}")
        
        self.optimizer.tell(x_data, y_data)
    
    def get_name(self) -> str:
        """Return the name of this optimizer."""
        return "scikit-optimize"


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
    base_estimator: str = 'GP',
    acquisition_function: str = 'EI',
    existing_data: Optional[List[Dict[str, Any]]] = None
) -> SkoptBayesianOptimizer:
    """
    Creates and optionally trains a scikit-optimize Bayesian optimizer.
    
    Args:
        param_names: List of parameter names
        param_mins: List of minimum values for each parameter
        param_maxes: List of maximum values for each parameter
        base_estimator: Base estimator type
        acquisition_function: Acquisition function
        existing_data: Optional list of evaluated points for training
        
    Returns:
        Configured and trained SkoptBayesianOptimizer instance
    """
    optimizer = SkoptBayesianOptimizer(
        param_names=param_names,
        param_mins=param_mins,
        param_maxes=param_maxes,
        base_estimator=base_estimator,
        acquisition_function=acquisition_function
    )
    
    if existing_data:
        x_train, y_train = parse_training_data(existing_data, param_names)
        if x_train:
            optimizer.tell(x_train, y_train)
            logger.info("Successfully trained optimizer with existing data")
    
    return optimizer
