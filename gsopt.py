import pandas as pd
from dataclasses import dataclass
from flask import Flask, request, jsonify
import numpy as np
from skopt import Optimizer
from skopt.space import Real
from typing import Dict, List, Any, Optional, Tuple
import logging
import jwt
from jwt import PyJWKClient
import os

# Configure logging with timestamp and log level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Google's JWKS endpoint for validating identity tokens
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

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

def authenticate_request(request) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates the authenticated user from custom header or JWT token.
    Requires Gmail account for access.
    
    Returns:
        Tuple of (is_valid, email, error_message)
    """
    # Priority 1: Check custom header (most reliable for Apps Script)
    user_email = request.headers.get('X-User-Email')
    
    if user_email:
        if not user_email.endswith('@gmail.com'):
            logger.warning(f"Access denied for non-Gmail account: {user_email}")
            return False, None, f"Access denied: Must use a Gmail account. Got: {user_email}"
        
        logger.info(f"Authenticated user via custom header: {user_email}")
        return True, user_email, None
    
    # Priority 2: Check Cloud Run authentication headers
    authenticated_email = request.headers.get('X-Goog-Authenticated-User-Email')
    
    if authenticated_email:
        # Remove the "accounts.google.com:" prefix if present
        if authenticated_email.startswith('accounts.google.com:'):
            authenticated_email = authenticated_email.replace('accounts.google.com:', '')
        
        # Validate Gmail account
        if not authenticated_email.endswith('@gmail.com'):
            logger.warning(f"Access denied for non-Gmail account: {authenticated_email}")
            return False, None, f"Access denied: Must use a Gmail account. Got: {authenticated_email}"
        
        logger.info(f"Authenticated user via Cloud Run header: {authenticated_email}")
        return True, authenticated_email, None
    
    # Priority 3: Try JWT token (but don't enforce strict audience validation)
    auth_header = request.headers.get('Authorization', '')
    
    if auth_header.startswith('Bearer '):
        token = auth_header.split('Bearer ')[1]
        
        try:
            # Decode without verification first to see what we have
            unverified = jwt.decode(token, options={"verify_signature": False})
            email = unverified.get('email') or unverified.get('sub')
            
            if email and email.endswith('@gmail.com'):
                logger.info(f"Authenticated user via JWT token (unverified): {email}")
                return True, email, None
            elif email:
                logger.warning(f"Access denied for non-Gmail account in JWT: {email}")
                return False, None, f"Access denied: Must use a Gmail account. Got: {email}"
            
        except Exception as e:
            logger.warning(f"Could not decode JWT token: {str(e)}")
    
    # No valid authentication found
    logger.warning("No valid authentication found")
    logger.debug(f"Request headers: Authorization={bool(auth_header)}, X-User-Email={bool(user_email)}, X-Goog={bool(authenticated_email)}")
    return False, None, "Authentication required: Must provide Gmail email via X-User-Email header"

def parse_optimizer_settings(settings_data: Dict[str, Any]) -> OptimizerSettings:
    """
    Parses optimizer settings from the request payload.
    
    Expected structure:
    {
        "base_estimator": "GP",
        "acquisition_function": "EI",
        "num_init_points": 10,
        "batch_size": 5,
        "num_params": 3,
        "param_names": ["parameter1", "parameter2", "parameter3"],
        "param_mins": [0, 0, 0],
        "param_maxes": [10, 10, 10]
    }
    """
    return OptimizerSettings(
        base_estimator=settings_data.get('base_estimator', 'GP'),
        acquisition_function=settings_data.get('acquisition_function', 'EI'),
        num_params=settings_data.get('num_params', 0),
        param_names=settings_data.get('param_names', []),
        param_mins=settings_data.get('param_mins', []),
        param_maxes=settings_data.get('param_maxes', []),
        num_init_points=settings_data.get('num_init_points', 10),
        batch_size=settings_data.get('batch_size', 5)
    )

def build_optimizer(
    dimensions: Dict[str, Tuple[float, float]], 
    base_estimator: str, 
    acq_func: str,
    existing_data: Optional[List[Dict[str, Any]]] = None
) -> Optimizer:
    """
    Creates and optionally trains a Bayesian optimizer with existing data.
    
    Args:
        dimensions: Dict mapping parameter names to (min, max) tuples
        base_estimator: Type of surrogate model (e.g., 'GP', 'ET', 'RF')
        acq_func: Acquisition function (e.g., 'EI', 'PI', 'LCB')
        existing_data: Optional list of dicts with keys matching param_names + 'objective'
        
    Returns:
        Trained Optimizer instance
    """
    # Define search space
    space = [Real(v[0], v[1], name=k) for k, v in dimensions.items()]
    logger.info(f"Created search space with {len(space)} dimensions")

    # Initialize optimizer
    optimizer = Optimizer(
        space, 
        base_estimator=base_estimator, 
        acq_func=acq_func,
        n_initial_points=5
    )
    logger.info(f"Initialized optimizer with base_estimator={base_estimator}, acq_func={acq_func}")
    
    # Train with existing data if provided
    if existing_data:
        param_names = list(dimensions.keys())
        x_train = []
        y_train = []
        
        for row in existing_data:
            # Skip rows without objective values
            if 'objective' not in row or row['objective'] is None or row['objective'] == '':
                continue
            
            try:
                x_point = [float(row.get(name, 0)) for name in param_names]
                y_value = float(row['objective'])
                x_train.append(x_point)
                y_train.append(y_value)
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid data point: {row}, error: {e}")
                continue
        
        if x_train:
            optimizer.tell(x_train, y_train)
            logger.info(f"Successfully trained optimizer with {len(x_train)} points")
        else:
            logger.warning("No valid evaluated points found to train optimizer")
    
    return optimizer

@app.route('/init-optimization', methods=['POST'])
def init_optimization():
    """
    Initialize optimization and return initial points.
    
    Expected request body:
    {
        "settings": { /* OptimizerSettings as dict */ }
    }
    
    Returns:
        JSON with initial parameter combinations to evaluate
    """
    is_valid, email, error_msg = authenticate_request(request)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        data = request.get_json()
        settings_data = data.get('settings')
        
        if not settings_data:
            return jsonify({"status": "error", "message": "settings are required"}), 400

        logger.info(f"Starting optimization initialization for user: {email}")
        
        optimizer_settings = parse_optimizer_settings(settings_data)
        
        dimensions = {
            name: (optimizer_settings.param_mins[i], optimizer_settings.param_maxes[i])
            for i, name in enumerate(optimizer_settings.param_names)
        }
        
        optimizer = build_optimizer(
            dimensions,
            optimizer_settings.base_estimator,
            optimizer_settings.acquisition_function
        )
        
        # Generate initial points
        initial_points = optimizer.ask(n_points=optimizer_settings.num_init_points)
        logger.info(f"Generated {len(initial_points)} initial points")
        
        # Format as list of dicts for easy consumption
        result_data = []
        for point in initial_points:
            row = {name: float(val) for name, val in zip(optimizer_settings.param_names, point)}
            row['objective'] = ''  # Empty objective column
            result_data.append(row)

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
    Continue optimization with existing data and return next batch of points.
    
    Expected request body:
    {
        "settings": { /* OptimizerSettings as dict */ },
        "existing_data": [ { "param1": val, "param2": val, "objective": val }, ... ]
    }
    
    Returns:
        JSON with next parameter combinations to evaluate
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
        
        optimizer_settings = parse_optimizer_settings(settings_data)

        dimensions = {
            name: (optimizer_settings.param_mins[i], optimizer_settings.param_maxes[i])
            for i, name in enumerate(optimizer_settings.param_names)
        }
        
        optimizer = build_optimizer(
            dimensions,
            optimizer_settings.base_estimator,
            optimizer_settings.acquisition_function,
            existing_data
        )
        
        # Generate new batch of points
        new_points = optimizer.ask(n_points=optimizer_settings.batch_size)
        logger.info(f"Generated {len(new_points)} new points")
        
        # Format as list of dicts
        result_data = []
        for point in new_points:
            row = {name: float(val) for name, val in zip(optimizer_settings.param_names, point)}
            row['objective'] = ''  # Empty objective column
            result_data.append(row)
        
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
    Tests authentication and returns connection status.
    
    Returns:
        JSON response with authentication status
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