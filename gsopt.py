"""
This module provides a Flask-based web service for performing Bayesian optimization.
It is designed to be called from clients like Google Apps Script, enabling optimization
tasks to be managed from within a Google Sheet.

The service exposes three main endpoints:
1.  `/init-optimization`: Initializes a new optimization run and returns a set of
    initial points to be evaluated.
2.  `/continue-optimization`: Takes a set of previously evaluated points and returns
    the next batch of points to evaluate, based on the optimizer's model.
3.  `/test-connection`: A simple endpoint to verify authentication and that the
    service is running.

The application is structured to be stateless, meaning that all necessary information
(settings and data) is passed in each request. This makes it scalable and robust.
It uses a wrapper around the `scikit-optimize` library to perform the optimization.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple
import os

import jwt
import numpy as np
from flask import Flask, request, jsonify
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from skopt.plots import plot_convergence, plot_evaluations, plot_objective
from scipy.optimize import OptimizeResult
import io
import base64

from utils import setup_logging, authenticate_request
from skopt_bayes import build_optimizer as build_skopt_optimizer

logger = setup_logging(__name__)
app = Flask(__name__)


@dataclass
class OptimizerSettings:
    """
    A data class to hold and validate all configuration settings for the optimizer.
    This provides a structured way to manage the various parameters that control
    the optimization process.
    """
    base_estimator: str
    acquisition_function: str
    acq_optimizer: str
    acq_func_kwargs: Dict[str, Any]
    num_params: int
    param_names: List[str]
    param_mins: List[float]
    param_maxes: List[float]
    num_init_points: int
    batch_size: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptimizerSettings':
        """
        Factory method to create an OptimizerSettings instance from a dictionary.
        It provides default values for missing keys to ensure robustness.
        """
        return cls(
            base_estimator=data.get('base_estimator', 'GP'),
            acquisition_function=data.get('acquisition_function', 'EI'),
            acq_optimizer=data.get('acq_optimizer', 'auto'),
            acq_func_kwargs=data.get('acq_func_kwargs', {}),
            num_params=data.get('num_params', 0),
            param_names=data.get('param_names', []),
            param_mins=data.get('param_mins', []),
            param_maxes=data.get('param_maxes', []),
            num_init_points=data.get('num_init_points', 10),
            batch_size=data.get('batch_size', 5)
        )

    def get_dimensions(self) -> Dict[str, Tuple[float, float]]:
        """Returns the parameter search space as a dictionary."""
        return {
            name: (self.param_mins[i], self.param_maxes[i])
            for i, name in enumerate(self.param_names)
        }


def build_optimizer(settings: OptimizerSettings, existing_data: Optional[List[Dict[str, Any]]] = None) -> Any:
    """
    Factory function to create and configure an optimizer instance.

    This function acts as a dispatcher, selecting the appropriate optimizer
    backend based on the `base_estimator` string (e.g., 'SKOPT-GP').
    It then initializes the optimizer with the given settings and, if provided,
    trains it on existing data.
    """
    optimizer_type = settings.base_estimator
    
    logger.info(f"Building optimizer: {optimizer_type}")
    
    # The optimizer type string is parsed to support different backends.
    # For example, 'SKOPT-GP' uses the 'scikit-optimize' backend with a 'GP' model.
    if '-' in optimizer_type:
        parts = optimizer_type.split('-', 1)
        prefix, algo = parts[0].upper(), parts[1]
        
        if prefix == 'SKOPT':
            return build_skopt_optimizer(
                param_names=settings.param_names,
                param_mins=settings.param_mins,
                param_maxes=settings.param_maxes,
                base_estimator=algo.upper(),
                acquisition_function=settings.acquisition_function,
                acq_optimizer=settings.acq_optimizer,
                acq_func_kwargs=settings.acq_func_kwargs,
                existing_data=existing_data
            )

    raise ValueError(f"Unknown or unsupported optimizer type: {optimizer_type}.")

def format_points_response(
    points: List[List[float]],
    param_names: List[str]
) -> List[Dict[str, Any]]:
    """
    Formats the raw points from the optimizer into a JSON-serializable list of
    dictionaries, which is the format expected by the client.
    """
    result = []
    for point in points:
        row = {name: float(val) for name, val in zip(param_names, point)}
        # The 'objective' field is added as a placeholder for the client to fill in.
        row['objective'] = ''
        result.append(row)
    
    return result


@app.route('/init-optimization', methods=['POST'])
def init_optimization() -> Tuple[Any, int]:
    """
    Flask endpoint to initialize an optimization process.
    
    It expects a JSON payload with optimization settings and returns a set of
    initial points for the client to evaluate. These points are typically
    generated from a random or quasi-random sampling of the search space.
    """
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Request must be JSON"}), 400
            
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
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to initialize optimization: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": f"Failed to initialize optimization: {str(e)}"}), 500


@app.route('/continue-optimization', methods=['POST'])
def continue_optimization() -> Tuple[Any, int]:
    """
    Flask endpoint to continue an existing optimization process.
    
    It takes the current settings and all previously evaluated data points.
    The optimizer is "retrained" on this data, and a new batch of points
    is generated for the client to evaluate next.
    """
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Request must be JSON"}), 400

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
        
        # Ensure new_points is always a list of lists (multiple points)
        if len(new_points) > 0 and not isinstance(new_points[0], (list, np.ndarray)):
            new_points = [new_points]
            
        logger.info(f"Generated {len(new_points)} new points")
        
        for i, point in enumerate(new_points):
            try:
                logger.debug(f"New point {i}: {[f'{val:.4f}' for val in point]}")
            except (TypeError, ValueError):
                logger.debug(f"New point {i}: {point}")
        
        result_data = format_points_response(new_points, settings.param_names)
        
        return jsonify({
            "status": "success",
            "message": f"Generated {len(new_points)} new points",
            "data": result_data
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to continue optimization: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": f"Failed to continue optimization: {str(e)}"}), 500


@app.route('/test-connection', methods=['POST'])
def test_connection() -> Tuple[Any, int]:
    """
    A simple endpoint to test that the service is up and authentication is working.
    """
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    # Prioritize environmental sha from build processes, fallback to Cloud Run revision
    commit_sha = os.environ.get('COMMIT_SHA') or os.environ.get('K_REVISION') or 'development'
    
    logger.info(f"Connection test successful for: {email} (Build: {commit_sha})")
    return jsonify({
        "status": "success",
        "message": f"Connection verified for {email}. Build: {commit_sha}",
        "authenticated_user": email,
        "commit_sha": commit_sha
    }), 200


@app.route('/plot', methods=['POST'])
def generate_plot() -> Tuple[Any, int]:
    """Generates skopt plots and returns base64 image data."""
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        data = request.get_json()
        plot_type = data.get('plot_type', 'convergence')
        settings = OptimizerSettings.from_dict(data.get('settings', {}))
        existing_data = data.get('existing_data', [])

        optimizer_wrapper = build_optimizer(settings, existing_data)
        
        # Access the inner skopt.Optimizer instance from the wrapper
        if hasattr(optimizer_wrapper, 'optimizer'):
            skopt_opt = optimizer_wrapper.optimizer
        else:
            skopt_opt = optimizer_wrapper
        
        # skopt.Optimizer has a get_result() method that returns the full OptimizeResult object
        # which contains the fitted models needed for plot_objective
        if not hasattr(skopt_opt, 'get_result'):
             return jsonify({"status": "error", "message": "Optimizer backend does not support get_result()."}), 400

        res = skopt_opt.get_result()
        
        if not res.x_iters or len(res.x_iters) == 0:
            return jsonify({"status": "error", "message": "No data available to plot"}), 400

        # Adjust figure size based on plot type
        plt.figure(figsize=(10, 8))
        if plot_type == 'objective' or plot_type == 'evaluations':
             # Matrix plots need more space, especially for >3 dimensions
             dim_count = len(settings.param_names)
             fig_size = max(8, dim_count * 2.5) 
             plt.figure(figsize=(fig_size, fig_size))
        else:
             plt.figure(figsize=(10, 6))

        try:
            if plot_type == 'convergence':
                plot_convergence(res)
                plt.title("Convergence Plot")
            elif plot_type == 'evaluations':
                plot_evaluations(res, bins=10)
                plt.suptitle("Evaluations Matrix", fontsize=16)
            elif plot_type == 'objective':
                # plot_objective requires the models to be fitted.
                # Since we called tell() in build_optimizer, the last model in res.models should be valid.
                plot_objective(res, size=3) 
                plt.suptitle("Objective Partial Dependence", fontsize=16)
        except Exception as plot_err:
             logger.error(f"Specific plotting error: {plot_err}")
             return jsonify({"status": "error", "message": f"Error creating {plot_type}: {str(plot_err)}"}), 500
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close('all')

        return jsonify({
            "status": "success",
            "plot_data": img_base64
        }), 200

    except Exception as e:
        logger.error(f"Plot generation failed: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    # Note: `debug=False` is important for production environments.
    app.run(host='0.0.0.0', port=8080, debug=False)