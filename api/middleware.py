"""
Optional Middleware for Automatic Expired Program Cleanup

This middleware can be used as an alternative to the login-based cleanup.
It will check for expired programs on every request (with configurable intervals).

Add to MIDDLEWARE in settings.py:
MIDDLEWARE = [
    # ... other middleware
    'api.middleware.ExpiredProgramCleanupMiddleware',
    # ... rest of middleware
]
"""

import logging
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

class ExpiredProgramCleanupMiddleware:
    """
    Middleware to automatically cleanup expired programs at configurable intervals
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Check if cleanup should run before processing the request
        self.check_and_run_cleanup(request)
        
        response = self.get_response(request)
        return response
    
    def check_and_run_cleanup(self, request):
        """
        Check if cleanup should run and execute it if needed
        """
        try:
            # Only run for authenticated users if configured
            if not self.should_run_cleanup(request):
                return
                
            # Import here to avoid circular imports
            from api.models import Program
            
            logger.debug(f"Middleware cleanup triggered by: {getattr(request.user, 'username', 'anonymous')}")
            
            # Run the cleanup
            result = Program.cleanup_expired_programs()
            
            if result['total_programs_cleaned'] > 0:
                logger.info(
                    f"Middleware auto-cleanup: Removed {result['total_users_removed']} users "
                    f"from {result['total_programs_cleaned']} expired programs"
                )
            else:
                logger.debug("Middleware auto-cleanup: No expired programs found")
                
        except Exception as e:
            logger.error(f"Error in middleware cleanup: {str(e)}", exc_info=True)
    
    def should_run_cleanup(self, request):
        """
        Determine if cleanup should run based on configuration and timing
        """
        # Check if middleware cleanup is enabled
        if not getattr(settings, 'CLEANUP_EXPIRED_PROGRAMS_MIDDLEWARE', False):
            return False
        
        # Check if user is authenticated (if required)
        require_auth = getattr(settings, 'CLEANUP_EXPIRED_PROGRAMS_REQUIRE_AUTH', True)
        if require_auth and not request.user.is_authenticated:
            return False
        
        # Check user type restrictions
        allowed_user_types = getattr(settings, 'CLEANUP_EXPIRED_PROGRAMS_USER_TYPES', None)
        if (allowed_user_types and 
            request.user.is_authenticated and 
            request.user.user_type not in allowed_user_types):
            return False
        
        # Check cleanup interval
        cleanup_interval = getattr(settings, 'CLEANUP_EXPIRED_PROGRAMS_MIDDLEWARE_INTERVAL', 120)  # minutes
        cache_key = 'middleware_last_expired_program_cleanup'
        last_cleanup = cache.get(cache_key)
        
        if last_cleanup:
            time_since_last = (timezone.now() - last_cleanup).total_seconds() / 60
            if time_since_last < cleanup_interval:
                return False
        
        # Set cache for next interval check
        cache.set(cache_key, timezone.now(), timeout=cleanup_interval * 60)
        
        return True
