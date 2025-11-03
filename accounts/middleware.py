from django.contrib.auth import logout
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken, BlacklistMixin
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.exceptions import TokenError
from django.core.cache import cache
from django.http import JsonResponse

class SingleSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                # Get the current token from the Authorization header
                auth_header = request.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    current_token = auth_header.split(' ')[1]
                    
                    # Get user's session key from cache
                    cache_key = f'user_session_{request.user.id}'
                    stored_token = cache.get(cache_key)
                    
                    if stored_token and stored_token != current_token:
                        # If a different token exists, invalidate all existing tokens
                        try:
                            # Blacklist all outstanding tokens for the user
                            outstanding_tokens = OutstandingToken.objects.filter(user=request.user)
                            for token in outstanding_tokens:
                                BlacklistedToken.objects.get_or_create(token=token)
                            
                            # Store the new token
                            cache.set(cache_key, current_token, timeout=31536000*10)  # 10 years timeout (effectively unexpirable)
                            
                            # Return unauthorized response
                            return JsonResponse({
                                'detail': 'You have been logged in on another device. All previous sessions have been terminated.'
                            }, status=401)
                        except Exception as e:
                            return JsonResponse({
                                'detail': 'Session error occurred. Please log in again.'
                            }, status=401)
                    
                    # Store the current token if no previous token exists
                    if not stored_token:
                        cache.set(cache_key, current_token, timeout=31536000*10)  # 10 years timeout (effectively unexpirable)
                    
            except (TokenError, IndexError):
                return JsonResponse({
                    'detail': 'Invalid token. Please log in again.'
                }, status=401)

        response = self.get_response(request)
        return response 