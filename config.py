import os
from typing import Optional

class Config:
    """Application configuration with security defaults."""
    
    # Required environment variables
    CLOUD_RUN_SERVICE_URL: str = os.environ.get('CLOUD_RUN_SERVICE_URL', '')
    COMMIT_SHA: str = os.environ.get('COMMIT_SHA', 'development')
    
    # Security settings
    MAX_CONTENT_LENGTH: int = 10 * 1024 * 1024  # 10MB
    RATE_LIMIT_WINDOW: int = 60  # seconds
    RATE_LIMIT_MAX_REQUESTS: int = 10
    
    # Optimization limits
    MAX_PARAMETERS: int = 100
    MAX_INIT_POINTS: int = 1000
    MAX_BATCH_SIZE: int = 100
    MAX_DATA_POINTS: int = 10000
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration is present."""
        if not cls.CLOUD_RUN_SERVICE_URL:
            raise ValueError('CLOUD_RUN_SERVICE_URL environment variable must be set')
        return True

# Validate on import
Config.validate()
