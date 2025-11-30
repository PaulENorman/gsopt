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
from typing import Tuple, Optional

import jwt
from flask import Request

# The URL for Google's public keys, used for verifying JWTs.
# While not used for strict verification in this implementation, it's good practice.
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


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
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(name)


def authenticate_request(request: Request) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Authenticates an incoming request and ensures the user has a Gmail account.

    This function checks for user identity in a prioritized order of sources:
    1.  `X-User-Email`: A custom header expected from the Google Apps Script client.
    2.  `X-Goog-Authenticated-User-Email`: A header injected by Google Cloud Run's
        Identity-Aware Proxy (IAP).
    3.  `Authorization: Bearer <token>`: A standard JWT Bearer token.

    Access is restricted to users with a `@gmail.com` email address.
    
    Args:
        request: The incoming Flask request object.
        
    Returns:
        A tuple containing:
        - A boolean indicating if authentication was successful.
        - The authenticated user's email, if successful.
        - An error message, if authentication failed.
    """
    logger = logging.getLogger(__name__)
    
    # 1. Check for the custom header from Apps Script.
    user_email = request.headers.get('X-User-Email')
    if user_email:
        return _validate_gmail(user_email, "custom header", logger)
    
    # 2. Check for the header from Google Cloud Run's IAP.
    authenticated_email = request.headers.get('X-Goog-Authenticated-User-Email')
    if authenticated_email:
        # The header value is prefixed with "accounts.google.com:", which needs to be removed.
        if authenticated_email.startswith('accounts.google.com:'):
            authenticated_email = authenticated_email.replace('accounts.google.com:', '')
        return _validate_gmail(authenticated_email, "Cloud Run header", logger)
    
    # 3. Fallback to checking for a JWT Bearer token.
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split('Bearer ')[1]
        return _validate_jwt_token(token, logger)
    
    logger.warning("Authentication failed: No valid credentials found in headers.")
    logger.debug(f"Headers checked: X-User-Email, X-Goog-Authenticated-User-Email, Authorization")
    return False, None, "Authentication required. Provide a valid credential (e.g., X-User-Email header)."


def _validate_gmail(email: str, source: str, logger: logging.Logger) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    A helper function to validate that an email address is from the '@gmail.com' domain.
    
    Args:
        email: The email address to validate.
        source: A string indicating where the email was sourced from (for logging).
        logger: The logger instance to use for logging messages.
        
    Returns:
        A tuple (is_valid, email, error_message).
    """
    if not email.endswith('@gmail.com'):
        logger.warning(f"Access denied for non-Gmail account from {source}: {email}")
        return False, None, f"Access denied: Must use a Gmail account. Received: {email}"
    
    logger.info(f"Successfully authenticated user via {source}: {email}")
    return True, email, None


def _validate_jwt_token(token: str, logger: logging.Logger) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Decodes a JWT token to extract the user's email and validates if it's a Gmail account.
    
    Note: This implementation performs a "lazy" validation by decoding the token
    without verifying its cryptographic signature. In a production environment with
    untrusted clients, full signature verification against Google's public keys
    would be necessary.
    
    Args:
        token: The JWT token string.
        logger: The logger instance.
        
    Returns:
        A tuple (is_valid, email, error_message).
    """
    try:
        # Decode the token without signature verification to inspect its claims.
        unverified_claims = jwt.decode(token, options={"verify_signature": False})
        email = unverified_claims.get('email') or unverified_claims.get('sub')
        
        if email:
            return _validate_gmail(email, "JWT token", logger)
            
    except jwt.PyJWTError as e:
        logger.warning(f"Failed to decode JWT token: {e}")
    
    return False, None, "Invalid or malformed JWT token."
