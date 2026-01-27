"""
This module provides a wrapper around the `scikit-optimize` library to expose
a consistent 'ask' and 'tell' interface for Bayesian optimization. This pattern
is crucial for the stateless, request-based architecture of the main Flask application,
where the optimizer is reconstructed for each step.

The main components are:
-   `SkoptBayesianOptimizer`: A class that encapsulates a `skopt.Optimizer` instance,
    managing its configuration and state.
-   `build_optimizer`: A factory function that creates and trains an instance of
    `SkoptBayesianOptimizer`.
-   `parse_training_data`: A utility function to convert the client's data format
    into numpy arrays suitable for `scikit-optimize`.
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from skopt import Optimizer
from skopt.space import Real

from utils import setup_logging

logger = setup_logging(__name__)


class SkoptBayesianOptimizer:
    """
    A wrapper for the scikit-optimize (`skopt`) Bayesian Optimizer to provide a
    stateful object that can be used in a stateless environment via the 'ask'
    and 'tell' pattern.
    """
    
    def __init__(
        self,
        param_names: List[str],
        param_mins: List[float],
        param_maxes: List[float],
        base_estimator: str = 'GP',
        acquisition_function: str = 'EI',
        acq_optimizer: str = 'auto',
        acq_func_kwargs: Optional[Dict[str, Any]] = None,
        n_initial_points: int = 5
    ):
        """
        Initializes the scikit-optimize Bayesian optimizer with a defined search space
        and configuration.
        
        Args:
            param_names: A list of names for the parameters to be optimized.
            param_mins: A list of minimum values for each parameter.
            param_maxes: A list of maximum values for each parameter.
            base_estimator: The surrogate model to use ('GP', 'RF', 'ET', 'GBRT').
            acquisition_function: The acquisition function to guide the search.
            acq_optimizer: The method used to minimize the acquisition function.
            acq_func_kwargs: Additional arguments for the acquisition function.
            n_initial_points: The number of random points to sample before fitting
                              the surrogate model.
        """
        self.param_names = param_names
        self.param_mins = param_mins
        self.param_maxes = param_maxes
        
        # The search space is defined as a list of `Real` dimensions.
        dimensions = [
            Real(low=param_mins[i], high=param_maxes[i], name=name)
            for i, name in enumerate(param_names)
        ]
        
        logger.info(f"Created search space with {len(dimensions)} dimensions.")
        logger.info(f"Parameters: {param_names}")
        
        # The core `skopt.Optimizer` is instantiated here.
        self.optimizer = Optimizer(
            dimensions,
            base_estimator=base_estimator,
            acq_func=acquisition_function,
            acq_optimizer=acq_optimizer,
            acq_func_kwargs=acq_func_kwargs or {},
            n_initial_points=n_initial_points
        )
        
        logger.info(f"Initialized scikit-optimize with: estimator={base_estimator}, acq_func={acquisition_function}, acq_optimizer={acq_optimizer}")
    
    def ask(self, n_points: int = 1) -> List[List[float]]:
        """
        Requests the next point(s) to evaluate from the optimizer.
        
        Args:
            n_points: The number of points to generate in a batch.
            
        Returns:
            A list of points, where each point is a list of parameter values.
        """
        points = self.optimizer.ask(n_points=n_points)
        logger.info(f"Generated {len(points)} new points to evaluate.")
        return points
    
    def tell(self, x_data: List[List[float]], y_data: List[float]) -> None:
        """
        "Tells" the optimizer the results of previous evaluations. This updates
        the surrogate model.
        
        Args:
            x_data: A list of evaluated parameter points.
            y_data: A list of corresponding objective function values.
        """
        if not x_data or not y_data:
            logger.warning("tell() was called with no data; no update will be performed.")
            return
        
        logger.info(f"Training optimizer with {len(x_data)} new points.")
        
        self.optimizer.tell(x_data, y_data)
    
    def get_name(self) -> str:
        """Returns the name of this optimizer backend."""
        return "scikit-optimize"


def parse_training_data(
    existing_data: List[Dict[str, Any]],
    param_names: List[str]
) -> Tuple[List[List[float]], List[float]]:
    """
    Parses and validates the client-provided data into a format suitable for
    the `tell` method of the optimizer.
    
    Args:
        existing_data: A list of dictionaries, where each dictionary represents
                       an evaluated point.
        param_names: The ordered list of parameter names.
        
    Returns:
        A tuple containing two lists: the parameter vectors (X_train) and the
        objective values (y_train).
    """
    x_train: List[List[float]] = []
    y_train: List[float] = []
    
    logger.info(f"Processing {len(existing_data)} existing data points for training.")
    
    for i, row in enumerate(existing_data):
        # Skip rows that haven't been evaluated yet.
        if 'objective' not in row or row['objective'] is None or str(row['objective']).strip() == '':
            logger.debug(f"Skipping row {i} because it has no objective value.")
            continue
        
        try:
            # Ensure all parameters are present and correctly typed.
            x_point = [float(row[name]) for name in param_names]
            y_value = float(row['objective'])
            x_train.append(x_point)
            y_train.append(y_value)
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Skipping invalid data point at index {i}: {row}. Reason: {e}")
            continue
    
    if not x_train:
        logger.warning("No valid, evaluated training points were found in the provided data.")
    else:
        logger.info(f"Extracted {len(x_train)} valid training points.")
    
    return x_train, y_train


def build_optimizer(
    param_names: List[str],
    param_mins: List[float],
    param_maxes: List[float],
    base_estimator: str = 'GP',
    acquisition_function: str = 'EI',
    acq_optimizer: str = 'auto',
    acq_func_kwargs: Optional[Dict[str, Any]] = None,
    existing_data: Optional[List[Dict[str, Any]]] = None
) -> SkoptBayesianOptimizer:
    """
    Factory function to construct and, if data is provided, train a
    `SkoptBayesianOptimizer`.
    
    This function orchestrates the creation of the optimizer and the subsequent
    training (the 'tell' step) if there is existing data.
    
    Returns:
        A configured and potentially trained `SkoptBayesianOptimizer` instance.
    """
    optimizer = SkoptBayesianOptimizer(
        param_names=param_names,
        param_mins=param_mins,
        param_maxes=param_maxes,
        base_estimator=base_estimator,
        acquisition_function=acquisition_function,
        acq_optimizer=acq_optimizer,
        acq_func_kwargs=acq_func_kwargs
    )
    
    if existing_data:
        x_train, y_train = parse_training_data(existing_data, param_names)
        if x_train:
            optimizer.tell(x_train, y_train)
            logger.info("Successfully trained the optimizer with the provided existing data.")
    
    return optimizer
