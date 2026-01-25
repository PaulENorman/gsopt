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
import jwt
from jwt import PyJWKClient
from flask import Request
from typing import Tuple
import os

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


def authenticate_request(request: Request) -> Tuple[bool, str, str]:
    """
    Authenticates incoming requests using Google's OIDC tokens.
    
    Returns:
        (is_valid, email, error_message)
    """
    # Get email from header
    email = request.headers.get('X-User-Email', '')
    
    # Require Gmail accounts only
    if not email or not email.endswith('@gmail.com'):
        return False, '', f'Invalid email domain. Only @gmail.com accounts are allowed. Received: {email}'
    
    # Get authorization token
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False, '', 'Missing or invalid Authorization header'
    
    token = auth_header.replace('Bearer ', '')
    
    try:
        # Verify the JWT token with Google's public keys
        jwks_url = 'https://www.googleapis.com/oauth2/v3/certs'
        jwks_client = PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and validate
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256'],
            audience=os.environ.get('CLOUD_RUN_SERVICE_URL', ''),
            options={
                'verify_exp': True,
                'verify_aud': True,
                'verify_iss': True
            }
        )
        
        # Verify the email in the token matches the header
        token_email = decoded.get('email', '')
        if token_email != email:
            return False, '', f'Email mismatch: header={email}, token={token_email}'
        
        # Verify the token is from Google
        valid_issuers = ['https://accounts.google.com', 'accounts.google.com']
        if decoded.get('iss') not in valid_issuers:
            return False, '', f'Invalid token issuer: {decoded.get("iss")}'
        
        return True, email, ''
        
    except jwt.ExpiredSignatureError:
        return False, '', 'Token has expired'
    except jwt.InvalidAudienceError:
        return False, '', 'Invalid token audience'
    except jwt.InvalidIssuerError:
        return False, '', 'Invalid token issuer'
    except jwt.InvalidTokenError as e:
        return False, '', f'Invalid token: {str(e)}'
    except Exception as e:
        # Log but don't expose internal errors to client
        logging.error(f'Authentication error: {str(e)}')
        return False, '', 'Authentication failed'
