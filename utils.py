"""
Utility functions for authentication and logging.
"""

import logging
from typing import Tuple, Optional

import jwt
from flask import Request


GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


def setup_logging(name: str) -> logging.Logger:
    """
    Configures and returns a logger with consistent formatting.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(name)


def authenticate_request(request: Request) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates authenticated user from custom header, Cloud Run headers, or JWT token.
    Requires Gmail account for access.
    
    Authentication priority:
        1. X-User-Email header (most reliable for Apps Script)
        2. X-Goog-Authenticated-User-Email header (Cloud Run)
        3. JWT Bearer token (fallback)
    
    Args:
        request: Flask request object
        
    Returns:
        Tuple of (is_valid, email, error_message)
    """
    logger = logging.getLogger(__name__)
    
    user_email = request.headers.get('X-User-Email')
    if user_email:
        return _validate_gmail(user_email, "custom header", logger)
    
    authenticated_email = request.headers.get('X-Goog-Authenticated-User-Email')
    if authenticated_email:
        if authenticated_email.startswith('accounts.google.com:'):
            authenticated_email = authenticated_email.replace('accounts.google.com:', '')
        return _validate_gmail(authenticated_email, "Cloud Run header", logger)
    
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return _validate_jwt_token(auth_header.split('Bearer ')[1], logger)
    
    logger.warning("No valid authentication found")
    logger.debug(f"Headers: X-User-Email={bool(user_email)}, X-Goog={bool(authenticated_email)}, Auth={bool(auth_header)}")
    return False, None, "Authentication required: Must provide Gmail email via X-User-Email header"


def _validate_gmail(email: str, source: str, logger: logging.Logger) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates that an email is a Gmail account.
    
    Args:
        email: Email address to validate
        source: Source of the email (for logging)
        logger: Logger instance
        
    Returns:
        Tuple of (is_valid, email, error_message)
    """
    if not email.endswith('@gmail.com'):
        logger.warning(f"Access denied for non-Gmail account: {email}")
        return False, None, f"Access denied: Must use a Gmail account. Got: {email}"
    
    logger.info(f"Authenticated user via {source}: {email}")
    return True, email, None


def _validate_jwt_token(token: str, logger: logging.Logger) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates JWT token and extracts email (without strict signature verification).
    
    Args:
        token: JWT token string
        logger: Logger instance
        
    Returns:
        Tuple of (is_valid, email, error_message)
    """
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        email = unverified.get('email') or unverified.get('sub')
        
        if email and email.endswith('@gmail.com'):
            logger.info(f"Authenticated user via JWT token: {email}")
            return True, email, None
        elif email:
            logger.warning(f"Access denied for non-Gmail account in JWT: {email}")
            return False, None, f"Access denied: Must use a Gmail account. Got: {email}"
    except Exception as e:
        logger.warning(f"Could not decode JWT token: {str(e)}")
    
    return False, None, "Invalid JWT token"
