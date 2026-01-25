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
from flask import Flask, request, jsonify, abort
import re

from utils import setup_logging, authenticate_request
from middleware import setup_request_logging

logger = setup_logging(__name__)
app = Flask(__name__)
app = setup_request_logging(app)

# Limit request size to prevent DoS
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"status": "error", "message": "Request too large (max 10MB)"}), 413

# Rate limiting storage (in-memory)
_rate_limit_storage: Dict[str, List[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 10

def check_rate_limit(email: str) -> Tuple[bool, str]:
    """
    Check if user has exceeded rate limit for ping requests.
    Returns (is_allowed, message)
    """
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    
    # Clean old entries
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
    # Lazy load optimizer builder only when needed
    _ensure_optimizer_builder()
    
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

def validate_optimizer_settings(data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validates optimizer settings to prevent injection attacks and resource abuse.
    
    Returns:
        (is_valid, error_message)
    """
    # Check required fields
    required_fields = ['num_params', 'param_names', 'param_mins', 'param_maxes']
    for field in required_fields:
        if field not in data:
            return False, f'Missing required field: {field}'
    
    # Validate parameter count (prevent resource exhaustion)
    num_params = data.get('num_params', 0)
    if not isinstance(num_params, int) or num_params < 1 or num_params > 100:
        return False, 'num_params must be between 1 and 100'
    
    # Validate parameter names (prevent injection)
    param_names = data.get('param_names', [])
    if len(param_names) != num_params:
        return False, 'param_names length must match num_params'
    
    name_pattern = re.compile(r'^[a-zA-Z0-9_\-\s]{1,50}$')
    for name in param_names:
        if not isinstance(name, str) or not name_pattern.match(name):
            return False, f'Invalid parameter name: {name}. Use only alphanumeric, underscore, hyphen, space (max 50 chars)'
    
    # Validate bounds
    param_mins = data.get('param_mins', [])
    param_maxes = data.get('param_maxes', [])
    
    if len(param_mins) != num_params or len(param_maxes) != num_params:
        return False, 'Parameter bounds must match num_params'
    
    for i in range(num_params):
        try:
            min_val = float(param_mins[i])
            max_val = float(param_maxes[i])
            
            # Prevent extreme values that could cause numerical issues
            if abs(min_val) > 1e10 or abs(max_val) > 1e10:
                return False, f'Parameter bounds too large (max ±1e10)'
            
            if min_val >= max_val:
                return False, f'Invalid bounds for {param_names[i]}: min must be < max'
        except (ValueError, TypeError):
            return False, f'Invalid numeric bounds for {param_names[i]}'
    
    # Validate batch sizes (prevent resource exhaustion)
    num_init_points = data.get('num_init_points', 10)
    batch_size = data.get('batch_size', 5)
    
    if not isinstance(num_init_points, int) or num_init_points < 1 or num_init_points > 1000:
        return False, 'num_init_points must be between 1 and 1000'
    
    if not isinstance(batch_size, int) or batch_size < 1 or batch_size > 100:
        return False, 'batch_size must be between 1 and 100'
    
    # Validate estimator and acquisition function (whitelist only)
    valid_estimators = ['GP', 'RF', 'ET', 'GBRT']
    base_estimator = data.get('base_estimator', 'GP')
    if '-' in base_estimator:
        base_estimator = base_estimator.split('-')[1]
    if base_estimator not in valid_estimators:
        return False, f'Invalid base_estimator. Must be one of: {valid_estimators}'
    
    valid_acq_funcs = ['EI', 'PI', 'LCB', 'gp_hedge']
    acq_func = data.get('acquisition_function', 'EI')
    if acq_func not in valid_acq_funcs:
        return False, f'Invalid acquisition_function. Must be one of: {valid_acq_funcs}'
    
    return True, ''

def validate_existing_data(data: List[Dict[str, Any]], settings: OptimizerSettings) -> Tuple[bool, str]:
    """
    Validates existing data points to prevent injection and ensure data integrity.
    
    Returns:
        (is_valid, error_message)
    """
    if not isinstance(data, list):
        return False, 'existing_data must be a list'
    
    # Limit number of data points to prevent memory exhaustion
    if len(data) > 10000:
        return False, 'Too many data points (max 10000)'
    
    for i, point in enumerate(data):
                logger.debug(f"New point {i}: {point}")
            return False, f'Data point {i} is not a dictionary'
        result_data = format_points_response(new_points, settings.param_names)
        # Validate all expected parameters are present
        return jsonify({n settings.param_names:
            "status": "success", point:
            "message": f"Generated {len(new_points)} new points", {param_name}'
            "data": result_data
        }), 200:
                val = float(point[param_name])
    except Exception as e:r NaN/Inf
        logger.error(f"Failed to continue optimization: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": f"Failed to continue optimization: {str(e)}"}), 500
            except (ValueError, TypeError):
                return False, f'Data point {i} has non-numeric value for {param_name}'
@app.route('/test-connection', methods=['POST'])
def test_connection() -> Tuple[Any, int]:sent
    """ if 'objective' in point and point['objective'] not in ['', None]:
    A simple endpoint to test that the service is up and authentication is working.
    """         obj_val = float(point['objective'])
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:return False, f'Data point {i} has invalid objective value'
        return jsonify({"status": "error", "message": error_msg}), 403
                return False, f'Data point {i} has non-numeric objective'
    # Prioritize environmental sha from build processes, fallback to Cloud Run revision
    commit_sha = os.environ.get('COMMIT_SHA') or os.environ.get('K_REVISION') or 'development'
    
    logger.info(f"Connection test successful for: {email} (Build: {commit_sha})")
    return jsonify({n() -> Tuple[Any, int]:
        "status": "success",
        "message": f"Connection verified for {email}. Build: {commit_sha}",
        "authenticated_user": email,
        "commit_sha": commit_shath optimization settings and returns a set of
    }), 200 points for the client to evaluate. These points are typically
    generated from a random or quasi-random sampling of the search space.
    """
@app.route('/ping', methods=['POST'])enticate_request(request)
def ping() -> Tuple[Any, int]:
    """ return jsonify({"status": "error", "message": error_msg}), 403
    Lightweight ping endpoint to wake up the server without heavy library imports.
    Used for proactive server warm-up from client interactions.
    """ data = request.get_json()
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:sonify({"status": "error", "message": "Request must be JSON"}), 400
        return jsonify({"status": "error", "message": error_msg}), 403
        settings_data = data.get('settings')
    # Check rate limits_data:
    is_allowed, rate_msg = check_rate_limit(email)ssage": "settings are required"}), 400
    if not is_allowed:
        logger.warning(f"Rate limit exceeded for {email}")
        return jsonify({"status": "error", "message": rate_msg}), 429ings(settings_data)
        if not is_valid_settings:
    logger.info(f"Ping received from: {email}")rom {email}: {validation_error}")
    return jsonify({sonify({"status": "error", "message": validation_error}), 400
        "status": "success",
        "message": "Server is ready",timization for user: {email}")
        "timestamp": time.time()
    }), 200tings = OptimizerSettings.from_dict(settings_data)
        optimizer = build_optimizer(settings)
        
@app.route('/plot', methods=['POST'])k(n_points=settings.num_init_points)
def generate_plot() -> Tuple[Any, int]:itial_points)} initial points"
    """Generates skopt plots and returns base64 image data."""
    is_valid, email, error_msg = authenticate_request(request)ettings.param_names)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403
            "status": "success",
    try:    "message": f"Generated {len(initial_points)} initial points",
        # Lazy load plotting libraries only when needed
        _ensure_matplotlib()
        _ensure_skopt_plots()
        import ioion as e:
        import base64f"Failed to initialize optimization: {str(e)}", exc_info=True)
        # Don't expose internal errors to client
        data = request.get_json() "error", "message": "Internal server error"}), 500
        plot_type = data.get('plot_type', 'convergence')
        raw_settings = data.get('settings', {})
        settings = OptimizerSettings.from_dict(raw_settings)
        existing_data = data.get('existing_data', [])
        
        # Check optimization mode for plot labelingtion process.
        opt_mode = raw_settings.get('optimization_mode', 'Minimize')
        is_max = opt_mode == 'Maximize'll previously evaluated data points.
        suffix = " (-Objective)" if is_max else "" a new batch of points
    is generated for the client to evaluate next.
        optimizer_wrapper = build_optimizer(settings, existing_data)
        alid, email, error_msg = authenticate_request(request)
        # Access the inner skopt.Optimizer instance from the wrapper
        if hasattr(optimizer_wrapper, 'optimizer'):": error_msg}), 403
            skopt_opt = optimizer_wrapper.optimizer
        else:
            skopt_opt = optimizer_wrapper
        if not data:
        # skopt.Optimizer has a get_result() method that returns the full OptimizeResult object
        # which contains the fitted models needed for plot_objective
        if not hasattr(skopt_opt, 'get_result'):
             return jsonify({"status": "error", "message": "Optimizer backend does not support get_result()."}), 400
        
        res = skopt_opt.get_result()
            return jsonify({"status": "error", "message": "settings are required"}), 400
        if not res.x_iters or len(res.x_iters) == 0:
            return jsonify({"status": "error", "message": "No data available to plot"}), 400
        is_valid_settings, validation_error = validate_optimizer_settings(settings_data)
        # Adjust figure size based on plot type - Increased sizes for readability
        if plot_type == 'objective' or plot_type == 'evaluations':ation_error}")
             # Matrix plots need more space, especially for >3 dimensionsr}), 400
             dim_count = len(settings.param_names)
             if plot_type == 'evaluations':on for user: {email}")
                 # Evaluations matrix needs even more space to prevent text overlap
                 fig_size = max(16, dim_count * 5) 
             else: OptimizerSettings.from_dict(settings_data)
                 # Increased multiplier and base size for objective plots
                 fig_size = max(12, dim_count * 4)
             plt.figure(figsize=(fig_size, fig_size))_data(existing_data, settings)
        else:t is_valid_data:
             # Increased standard plot sizerom {email}: {data_error}")
             plt.figure(figsize=(14, 10))ror", "message": data_error}), 400
        
        try:mizer = build_optimizer(settings, existing_data)
            if plot_type == 'convergence':
                plot_convergence(res)points=settings.batch_size)
                plt.title(f"Convergence Plot{suffix}")
            elif plot_type == 'evaluations': of lists (multiple points)
                plot_evaluations(res, bins=10)nce(new_points[0], (list, np.ndarray)):
                # Remove title for cleaner look
            elif plot_type == 'objective':
                # plot_objective requires the models to be fitted.
                # Since we called tell() in build_optimizer, the last model in res.models should be valid.
                plot_objective(res, size=3) ):
                plt.suptitle(f"Objective Partial Dependence{suffix}", fontsize=16)
        except Exception as plot_err:int {i}: {[f'{val:.4f}' for val in point]}")
             logger.error(f"Specific plotting error: {plot_err}")
             return jsonify({"status": "error", "message": f"Error creating {plot_type}: {str(plot_err)}"}), 500
        
        buf = io.BytesIO()at_points_response(new_points, settings.param_names)
        # Increase DPI for better resolution, especially for evaluations matrix
        dpi = 150 if plot_type == 'evaluations' else 100
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=dpi)
        buf.seek(0)e": f"Generated {len(new_points)} new points",
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close('all')
        
        return jsonify({e:
            "status": "success", continue optimization: {str(e)}", exc_info=True)
            "plot_data": img_base64error", "message": "Internal server error"}), 500
        }), 200

    except Exception as e:on', methods=['POST'])
        logger.error(f"Plot generation failed: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
    A simple endpoint to test that the service is up and authentication is working.
    """
@app.after_request_msg = authenticate_request(request)
def add_security_headers(response):
    """Add security headers to all responses."""": error_msg}), 403














    app.run(host='0.0.0.0', port=8080, debug=False)    # Note: `debug=False` is important for production environments.if __name__ == '__main__':    return response    response.headers['Pragma'] = 'no-cache'    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'    # Don't cache sensitive data    response.headers['Content-Security-Policy'] = "default-src 'none'"    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'    response.headers['X-XSS-Protection'] = '1; mode=block'    response.headers['X-Frame-Options'] = 'DENY'    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Prioritize environmental sha from build processes, fallback to Cloud Run revision
    commit_sha = os.environ.get('COMMIT_SHA') or os.environ.get('K_REVISION') or 'development'
    
    logger.info(f"Connection test successful for: {email} (Build: {commit_sha})")
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
    
    # Check rate limit
    is_allowed, rate_msg = check_rate_limit(email)
    if not is_allowed:
        logger.warning(f"Rate limit exceeded for {email}")
        return jsonify({"status": "error", "message": rate_msg}), 429
    
    logger.info(f"Ping received from: {email}")
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
        # Lazy load plotting libraries only when needed
        _ensure_matplotlib()
        _ensure_skopt_plots()
        import io
        import base64
        
        data = request.get_json()
        plot_type = data.get('plot_type', 'convergence')
        raw_settings = data.get('settings', {})
        settings = OptimizerSettings.from_dict(raw_settings)
        existing_data = data.get('existing_data', [])
        
        # Check optimization mode for plot labeling
        opt_mode = raw_settings.get('optimization_mode', 'Minimize')
        is_max = opt_mode == 'Maximize'
        suffix = " (-Objective)" if is_max else ""

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

        # Adjust figure size based on plot type - Increased sizes for readability
        if plot_type == 'objective' or plot_type == 'evaluations':
             # Matrix plots need more space, especially for >3 dimensions
             dim_count = len(settings.param_names)
             if plot_type == 'evaluations':
                 # Evaluations matrix needs even more space to prevent text overlap
                 fig_size = max(16, dim_count * 5) 
             else:
                 # Increased multiplier and base size for objective plots
                 fig_size = max(12, dim_count * 4)
             plt.figure(figsize=(fig_size, fig_size))
        else:
             # Increased standard plot size
             plt.figure(figsize=(14, 10))

        try:
            if plot_type == 'convergence':
                plot_convergence(res)
                plt.title(f"Convergence Plot{suffix}")
            elif plot_type == 'evaluations':
                plot_evaluations(res, bins=10)
                # Remove title for cleaner look
            elif plot_type == 'objective':
                # plot_objective requires the models to be fitted.
                # Since we called tell() in build_optimizer, the last model in res.models should be valid.
                plot_objective(res, size=3) 
                plt.suptitle(f"Objective Partial Dependence{suffix}", fontsize=16)
        except Exception as plot_err:
             logger.error(f"Specific plotting error: {plot_err}")
             return jsonify({"status": "error", "message": f"Error creating {plot_type}: {str(plot_err)}"}), 500
        
        buf = io.BytesIO()
        # Increase DPI for better resolution, especially for evaluations matrix
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
    # Note: `debug=False` is important for production environments.
    app.run(host='0.0.0.0', port=8080, debug=False)