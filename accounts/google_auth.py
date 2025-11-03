from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.conf import settings
from django.db import transaction
from allauth.socialaccount.models import SocialAccount
from django.core.cache import cache
import logging
import uuid

User = get_user_model()
logger = logging.getLogger(__name__)


def get_tokens_for_user(user):
    """
    Generate JWT tokens for a user using the same method as CustomTokenObtainPairSerializer
    """
    with transaction.atomic():
        # Increment token version like the regular auth system
        user.token_version += 1
        user.save(update_fields=['token_version'])
    
    # Generate refresh token
    refresh = RefreshToken.for_user(user)
    # Add token version to claims (same as CustomTokenObtainPairSerializer)
    refresh['version'] = user.token_version
    
    access_token = str(refresh.access_token)
    
    # Update the session cache to prevent middleware conflicts
    cache_key = f'user_session_{user.id}'
    cache.set(cache_key, access_token, timeout=31536000*10)  # 10 years (effectively unexpirable)
    
    return {
        'refresh': str(refresh),
        'access': access_token,
    }


@api_view(['POST', 'OPTIONS'])
@permission_classes([AllowAny])
def google_auth_callback(request):
    """
    Handle Google OAuth callback and return JWT tokens
    """
    # Handle CORS preflight requests for Chrome
    if request.method == 'OPTIONS':
        logger.info("Handling CORS preflight request")
        response = Response(status=status.HTTP_200_OK)
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept'
        response['Access-Control-Max-Age'] = '86400'
        return response
    
    # Add detailed logging for debugging Chrome issues
    logger.info(f"Google OAuth callback received - Method: {request.method}")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Request data keys: {list(request.data.keys()) if hasattr(request, 'data') else 'No data'}")
    
    try:
        # Get the authorization code from the request
        code = request.data.get('code')
        if not code:
            logger.error("No authorization code provided in request")
            return Response(
                {'error': 'Authorization code not provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f"Authorization code received: {code[:20]}...")  # Log first 20 chars only
        
        # Exchange code for user information
        # This would typically involve calling Google's OAuth API
        # For now, we'll handle this in the frontend and pass user data
        
        user_data = request.data.get('user_data', {})
        logger.info(f"User data received: {user_data}")
        
        email = user_data.get('email')
        
        if not email:
            logger.error("No email provided in user_data")
            return Response(
                {'error': 'Email not provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f"Looking up user with email: {email}")
        
        # Check if user exists or create new user
        try:
            user = User.objects.get(email=email)
            created = False
            logger.info(f"Found existing user: {user.id} - {user.email}")
            
            # If user existed but wasn't a Google user, update them
            if not user.is_google_user:
                logger.info("Updating existing user to Google user")
                user.is_google_user = True
                # Handle both 'sub' and 'id' fields from Google API
                google_id = user_data.get('sub') or user_data.get('id', '')
                
                # Ensure google_id is not empty to avoid constraint violations
                if not google_id:
                    google_id = f"google_user_{email.replace('@', '_').replace('.', '_')}"
                    logger.warning(f"No Google ID found for existing user, using fallback: {google_id}")
                
                user.google_id = google_id
                user.is_verified = True
                user.save()
                
        except User.DoesNotExist:
            logger.info("Creating new Google user")
            # Create new user
            username = email.split('@')[0]
            
            # Ensure unique username
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1
            
            logger.info(f"Creating user with username: {username}")
            
            # Handle both 'sub' and 'id' fields from Google API
            google_id = user_data.get('sub') or user_data.get('id', '')
            logger.info(f"Google ID to use: {google_id}")
            
            # Ensure google_id is not empty to avoid constraint violations
            if not google_id:
                # Fallback: use email as google_id if no ID is provided
                google_id = f"google_user_{email.replace('@', '_').replace('.', '_')}"
                logger.warning(f"No Google ID found, using fallback: {google_id}")
            
            try:
                user = User.objects.create(
                    email=email,
                    username=username,
                    first_name=user_data.get('given_name', ''),
                    last_name=user_data.get('family_name', ''),
                    user_type='student',
                    user_id=str(uuid.uuid4()),
                    is_google_user=True,
                    google_id=google_id,
                    is_verified=True,
                )
                user.set_unusable_password()  # Google users don't need passwords
                user.save()
                created = True
                logger.info(f"Successfully created user: {user.id}")
            except Exception as create_error:
                logger.error(f"Error creating user: {str(create_error)}")
                
                # Handle specific case of duplicate google_id constraint
                if "google_id" in str(create_error) and "duplicate key" in str(create_error):
                    logger.info("Handling duplicate google_id constraint violation")
                    
                    # Generate a unique google_id with timestamp
                    import time
                    unique_google_id = f"{google_id}_{int(time.time())}" if google_id else f"google_user_{email.split('@')[0]}_{int(time.time())}"
                    logger.info(f"Trying with unique google_id: {unique_google_id}")
                    
                    # Try creating the user with a unique google_id
                    user = User.objects.create(
                        email=email,
                        username=username,
                        first_name=user_data.get('given_name', ''),
                        last_name=user_data.get('family_name', ''),
                        user_type='student',
                        user_id=str(uuid.uuid4()),
                        is_google_user=True,
                        google_id=unique_google_id,
                        is_verified=True,
                    )
                    user.set_unusable_password()
                    user.save()
                    created = True
                    logger.info(f"Successfully created user with unique google_id: {user.id}")
                else:
                    raise
        
        # Generate JWT tokens
        logger.info("Generating JWT tokens for user")
        try:
            tokens = get_tokens_for_user(user)
            logger.info("JWT tokens generated successfully")
        except Exception as token_error:
            logger.error(f"Error generating tokens: {str(token_error)}")
            raise
        
        # Log successful authentication
        logger.info(f"Google OAuth successful for user {user.email} (ID: {user.id}, Created: {created})")
        
        response_data = {
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'user_type': user.user_type,
                'is_google_user': user.is_google_user,
                'created': created,
                'token_version': user.token_version,  # Add for debugging
            }
        }
        
        logger.info(f"Returning successful response with user data")
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Google auth error: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Response(
            {'error': 'Authentication failed', 'details': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def google_login_url(request):
    """
    Return Google OAuth login URL
    """
    try:
        from urllib.parse import urlencode
        
        # Google OAuth 2.0 parameters
        params = {
            'client_id': settings.GOOGLE_OAUTH2_CLIENT_ID,
            'redirect_uri': f"{settings.SITE_URL}/auth/google/callback/",
            'scope': 'openid email profile',
            'response_type': 'code',
            'state': 'random_state_string',  # You should generate a random state
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        google_auth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"
        
        return Response({
            'auth_url': google_auth_url
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error generating Google auth URL: {str(e)}")
        return Response(
            {'error': 'Failed to generate auth URL'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
