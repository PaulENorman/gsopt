"""
Bayesian Optimization Service for Google Sheets

This Flask application provides endpoints for Bayesian optimization that can be called
from Google Apps Script. It supports initialization of optimization runs and continuation
with existing data points.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import jwt
from flask import Flask, request, jsonify
from skopt import Optimizer
from skopt.space import Real

from utils import setup_logging, authenticate_request

logger = setup_logging(__name__)
app = Flask(__name__)


@dataclass
class OptimizerSettings:
    """Configuration settings for the Bayesian optimizer."""
    base_estimator: str
    acquisition_function: str
    num_params: int
    param_names: List[str]
    param_mins: List[float]
    param_maxes: List[float]
    num_init_points: int
    batch_size: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptimizerSettings':
        """
        Creates OptimizerSettings from a dictionary.
        
        Args:
            data: Dictionary containing optimizer configuration
            
        Returns:
            OptimizerSettings instance with validated values
        """
        return cls(
            base_estimator=data.get('base_estimator', 'GP'),
            acquisition_function=data.get('acquisition_function', 'EI'),
            num_params=data.get('num_params', 0),
            param_names=data.get('param_names', []),
            param_mins=data.get('param_mins', []),
            param_maxes=data.get('param_maxes', []),
            num_init_points=data.get('num_init_points', 10),
            batch_size=data.get('batch_size', 5)
        )

    def get_dimensions(self) -> Dict[str, Tuple[float, float]]:
        """Returns parameter dimensions as a dictionary of (min, max) tuples."""
        return {
            name: (self.param_mins[i], self.param_maxes[i])
            for i, name in enumerate(self.param_names)
        }


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
        logger.info(f"Objective range: min={min(y_train):.4f}, max={max(y_train):.4f}, mean={np.mean(y_train):.4f}")
    else:
        logger.warning("No valid evaluated points found")
    
    return x_train, y_train


def build_optimizer(
    settings: OptimizerSettings,
    existing_data: Optional[List[Dict[str, Any]]] = None
) -> Optimizer:
    """
    Creates and optionally trains a Bayesian optimizer.
    
    Args:
        settings: OptimizerSettings containing all configuration
        existing_data: Optional list of evaluated points for training
        
    Returns:
        Configured and trained Optimizer instance
    """
    dimensions = settings.get_dimensions()
    space = [Real(bounds[0], bounds[1], name=name) for name, bounds in dimensions.items()]
    
    logger.info(f"Created search space with {len(space)} dimensions")
    logger.info(f"Parameters: {[dim.name for dim in space]}")

    optimizer = Optimizer(
        space,
        base_estimator=settings.base_estimator,
        acq_func=settings.acquisition_function,
        n_initial_points=5
    )
    
    logger.info(f"Initialized optimizer: estimator={settings.base_estimator}, acq_func={settings.acquisition_function}")
    
    if existing_data:
        x_train, y_train = parse_training_data(existing_data, settings.param_names)
        if x_train:
            optimizer.tell(x_train, y_train)
            logger.info("Successfully trained optimizer with existing data")
    
    return optimizer


def format_points_response(
    points: List[List[float]],
    param_names: List[str]
) -> List[Dict[str, Any]]:
    """
    Formats optimizer points into JSON-serializable dictionaries.
    
    Args:
        points: List of parameter value lists from optimizer
        param_names: Ordered list of parameter names
        
    Returns:
        List of dictionaries with parameter names as keys
    """
    result = []
    for point in points:
        row = {name: float(val) for name, val in zip(param_names, point)}
        row['objective'] = ''
        result.append(row)
    
    return result


@app.route('/init-optimization', methods=['POST'])
def init_optimization():
    """
    Initializes optimization and returns initial points to evaluate.
    
    Expected JSON payload:
        {
            "settings": {
                "base_estimator": "GP",
                "acquisition_function": "EI",
                "num_init_points": 10,
                "num_params": 3,
                "param_names": ["param1", "param2", "param3"],
                "param_mins": [0, 0, 0],
                "param_maxes": [10, 10, 10]
            }
        }
    
    Returns:
        JSON response with initial points and empty objective values
    """
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        data = request.get_json()
        settings_data = data.get('settings')
        
        if not settings_data:
            return jsonify({"status": "error", "message": "settings are required"}), 400

        logger.info(f"Initializing optimization for user: {email}")
        
        settings = OptimizerSettings.from_dict(settings_data)
        optimizer = build_optimizer(settings)
        
        initial_points = optimizer.ask(n_points=settings.num_init_points)
        logger.info(f"Generated {len(initial_points)} initial points")
        
        result_data = format_points_response(initial_points, settings.param_names)

        return jsonify({
            "status": "success",
            "message": f"Generated {len(initial_points)} initial points",
            "data": result_data
        })
        
    except Exception as e:
        logger.error(f"Failed to initialize optimization: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": f"Failed to initialize optimization: {str(e)}"}), 500


@app.route('/continue-optimization', methods=['POST'])
def continue_optimization():
    """
    Continues optimization with existing data and returns next batch.
    
    Expected JSON payload:
        {
            "settings": { /* same as init-optimization */ },
            "existing_data": [
                {"param1": 1.0, "param2": 2.0, "objective": 0.5},
                ...
            ]
        }
    
    Returns:
        JSON response with new points to evaluate
    """
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        data = request.get_json()
        settings_data = data.get('settings')
        existing_data = data.get('existing_data', [])
        
        if not settings_data:
            return jsonify({"status": "error", "message": "settings are required"}), 400

        logger.info(f"Continuing optimization for user: {email}")
        logger.info(f"Received {len(existing_data)} data points from client")
        
        settings = OptimizerSettings.from_dict(settings_data)
        
        if existing_data:
            logger.info(f"Sample data point: {existing_data[0]}")
        
        optimizer = build_optimizer(settings, existing_data)
        
        new_points = optimizer.ask(n_points=settings.batch_size)
        logger.info(f"Generated {len(new_points)} new points")
        
        for i, point in enumerate(new_points):
            logger.debug(f"New point {i}: {[f'{val:.4f}' for val in point]}")
        
        result_data = format_points_response(new_points, settings.param_names)
        
        return jsonify({
            "status": "success",
            "message": f"Generated {len(new_points)} new points",
            "data": result_data
        })
        
    except Exception as e:
        logger.error(f"Failed to continue optimization: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": f"Failed to continue optimization: {str(e)}"}), 500


@app.route('/test-connection', methods=['POST'])
def test_connection():
    """
    Tests authentication and service availability.
    
    Returns:
        JSON response with connection status and authenticated user
    """
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    logger.info(f"Connection test successful for: {email}")
    return jsonify({
        "status": "success",
        "message": f"Connection verified for {email}",
        "authenticated_user": email
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)