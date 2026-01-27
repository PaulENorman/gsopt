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
import time
from collections import defaultdict

import jwt
import numpy as np
from flask import Flask, request, jsonify

from utils import setup_logging, authenticate_request

logger = setup_logging(__name__)
app = Flask(__name__)

# Rate limiting storage (in-memory)
_rate_limit_storage: Dict[str, List[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX_REQUESTS = 10

def check_rate_limit(email: str) -> Tuple[bool, str]:
    """Check if user has exceeded rate limit for ping requests."""
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    
    _rate_limit_storage[email] = [
        ts for ts in _rate_limit_storage[email] 
        if ts > window_start
    ]
    
    if len(_rate_limit_storage[email]) >= _RATE_LIMIT_MAX_REQUESTS:
        return False, f"Rate limit exceeded: max {_RATE_LIMIT_MAX_REQUESTS} requests per {_RATE_LIMIT_WINDOW}s"
    
    _rate_limit_storage[email].append(now)
    return True, "OK"

# Lazy loading variables
_matplotlib_loaded = False
_skopt_plots_loaded = False
_optimizer_builder_loaded = False

def _ensure_matplotlib():
    """Lazy load matplotlib only when plotting is needed."""
    global _matplotlib_loaded
    if not _matplotlib_loaded:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        globals()['matplotlib'] = matplotlib
        globals()['plt'] = plt
        _matplotlib_loaded = True

def _ensure_skopt_plots():
    """Lazy load skopt plotting functions only when needed."""
    global _skopt_plots_loaded
    if not _skopt_plots_loaded:
        from skopt.plots import plot_convergence, plot_evaluations, plot_objective
        from scipy.optimize import OptimizeResult
        globals()['plot_convergence'] = plot_convergence
        globals()['plot_evaluations'] = plot_evaluations
        globals()['plot_objective'] = plot_objective
        globals()['OptimizeResult'] = OptimizeResult
        _skopt_plots_loaded = True

def _ensure_optimizer_builder():
    """Lazy load optimizer building functions only when needed."""
    global _optimizer_builder_loaded
    if not _optimizer_builder_loaded:
        from skopt_bayes import build_optimizer as build_skopt_optimizer
        globals()['build_skopt_optimizer'] = build_skopt_optimizer
        _optimizer_builder_loaded = True


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
    _ensure_optimizer_builder()
    
    optimizer_type = settings.base_estimator
    
    logger.info(f"Building optimizer: {optimizer_type}")
    
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

        logger.info("Initializing optimization")
        
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

        logger.info("Continuing optimization")
        logger.info(f"Received {len(existing_data)} data points from client")
        
        settings = OptimizerSettings.from_dict(settings_data)
        
        optimizer = build_optimizer(settings, existing_data)
        
        new_points = optimizer.ask(n_points=settings.batch_size)
        
        if len(new_points) > 0 and not isinstance(new_points[0], (list, np.ndarray)):
            new_points = [new_points]
            
        logger.info(f"Generated {len(new_points)} new points")
        
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

    commit_sha = os.environ.get('COMMIT_SHA') or os.environ.get('K_REVISION') or 'development'
    
    logger.info(f"Connection test successful (Build: {commit_sha})")
    return jsonify({
        "status": "success",
        "message": f"Connection verified for {email}. Build: {commit_sha}",
        "authenticated_user": email,
        "commit_sha": commit_sha
    }), 200


@app.route('/ping', methods=['POST'])
def ping() -> Tuple[Any, int]:
    """
    Lightweight ping endpoint to wake up the server without heavy library imports.
    Used for proactive server warm-up from client interactions.
    """
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403
    
    is_allowed, rate_msg = check_rate_limit(email)
    if not is_allowed:
        logger.warning("Rate limit exceeded")
        return jsonify({"status": "error", "message": rate_msg}), 429
    
    logger.info("Ping received")
    return jsonify({
        "status": "success",
        "message": "Server is ready",
        "timestamp": time.time()
    }), 200


@app.route('/plot', methods=['POST'])
def generate_plot() -> Tuple[Any, int]:
    """Generates skopt plots and returns base64 image data."""
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        _ensure_matplotlib()
        _ensure_skopt_plots()
        import io
        import base64
        
        data = request.get_json()
        plot_type = data.get('plot_type', 'convergence')
        raw_settings = data.get('settings', {})
        settings = OptimizerSettings.from_dict(raw_settings)
        existing_data = data.get('existing_data', [])
        
        opt_mode = raw_settings.get('optimization_mode', 'Minimize')
        is_max = opt_mode == 'Maximize'
        suffix = " (-Objective)" if is_max else ""

        optimizer_wrapper = build_optimizer(settings, existing_data)
        
        if hasattr(optimizer_wrapper, 'optimizer'):
            skopt_opt = optimizer_wrapper.optimizer
        else:
            skopt_opt = optimizer_wrapper
        
        if not hasattr(skopt_opt, 'get_result'):
             return jsonify({"status": "error", "message": "Optimizer backend does not support get_result()."}), 400

        res = skopt_opt.get_result()
        
        if not res.x_iters or len(res.x_iters) == 0:
            return jsonify({"status": "error", "message": "No data available to plot"}), 400

        if plot_type == 'objective' or plot_type == 'evaluations':
             dim_count = len(settings.param_names)
             if plot_type == 'evaluations':
                 fig_size = max(16, dim_count * 5) 
             else:
                 fig_size = max(12, dim_count * 4)
             plt.figure(figsize=(fig_size, fig_size))
        else:
             plt.figure(figsize=(14, 10))

        try:
            if plot_type == 'convergence':
                plot_convergence(res)
                plt.title(f"Convergence Plot{suffix}")
            elif plot_type == 'evaluations':
                plot_evaluations(res, bins=10)
            elif plot_type == 'objective':
                plot_objective(res, size=3) 
                plt.suptitle(f"Objective Partial Dependence{suffix}", fontsize=16)
        except Exception as plot_err:
             logger.error(f"Specific plotting error: {plot_err}")
             return jsonify({"status": "error", "message": f"Error creating {plot_type}: {str(plot_err)}"}), 500
        
        buf = io.BytesIO()
        dpi = 150 if plot_type == 'evaluations' else 100
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=dpi)
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
    app.run(host='0.0.0.0', port=8080, debug=False)