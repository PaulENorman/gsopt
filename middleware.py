import time
import logging
from flask import request, g

logger = logging.getLogger(__name__)

def setup_request_logging(app):
    """Set up request/response logging middleware."""
    
    @app.before_request
    def before_request():
        g.start_time = time.time()
        g.request_id = request.headers.get('X-Request-ID', 'unknown')
    
    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            elapsed = time.time() - g.start_time
            logger.info(
                f"Request completed: "
                f"method={request.method} "
                f"path={request.path} "
                f"status={response.status_code} "
                f"duration={elapsed:.3f}s "
                f"user={request.headers.get('X-User-Email', 'unknown')} "
                f"request_id={g.request_id}"
            )
        return response
    
    return app
