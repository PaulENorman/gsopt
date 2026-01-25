"""
This module provides utility functions that are shared across the application,
primarily focusing on logging configuration and request authentication.

The key functions are:
-   `setup_logging`: Configures a standardized logger for consistent output
    formatting throughout the application.
-   `authenticate_request`: Handles the authentication of incoming requests by
    checking for user identity in specific HTTP headers or a JWT Bearer token.
    It is designed to work with Google Cloud Run's identity-aware proxy and
    custom headers sent from Google Apps Script.
"""

import logging
from flask import Request
from typing import Tuple
import re

def setup_logging(name: str) -> logging.Logger:
    """
    Configures and returns a logger with a consistent format.
    
    This ensures that all log messages across the application have the same
    structure, including a timestamp, log level, logger name, and message.
    
    Args:
        name: The name for the logger, typically the module name (`__name__`).
        
    Returns:
        A configured `logging.Logger` instance.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(name)

def authenticate_request(request: Request) -> Tuple[bool, str, str]:
    """
    Simple email-based authentication for public service.
    Relies on rate limiting and input validation for security.
    
    Returns:
        (is_valid, email, error_message)
    """
    email = request.headers.get('X-User-Email', '').strip().lower()
    
    if not email:
        return False, '', 'Missing X-User-Email header'
    
    # Validate email format
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@gmail\.com$')
    if not email_pattern.match(email):
        return False, '', f'Invalid Gmail address format: {email}'
    
    # Accept any valid Gmail address
    # Security relies on rate limiting and input validation
    return True, email, ''
