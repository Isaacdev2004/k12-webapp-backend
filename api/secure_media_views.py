"""
Secure Media Views
Handles secure access to R2 media objects through authentication and signed URLs
"""

import json
import logging
from typing import Dict, Any
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from .r2_security import r2_security

logger = logging.getLogger(__name__)


@api_view(['POST'])
# @permission_classes([AllowAny])
def get_secure_media_url(request):
    """
    Generate a secure URL for accessing R2 media objects
    
    Expected payload:
    {
        "media_key": "path/to/media/file.ext"
    }
    
    Returns:
    {
        "url": "https://r2-worker.workers.dev/path/to/media/file.ext",
        "expires_in": 3600
    }
    """
    try:
        data = json.loads(request.body)
        media_key = data.get('media_key')
        
        if not media_key:
            return JsonResponse({
                'error': 'Media key is required'
            }, status=400)
        
        logger.info(f"Generating secure URL for user {request.user.id}, media key: {media_key}")
        
        # Add media/ prefix for subject_pdfs paths
        secure_key = media_key
        if media_key.startswith('subject_pdfs/') or media_key.startswith('content_pdfs/'):
            secure_key = f"media/{media_key}"
        
        # # Check if user has access to this resource
        # if not r2_security.check_user_access(request.user, media_key):
        #     logger.warning(f"Access denied for user {request.user.id} to media key: {media_key}")
        #     return JsonResponse({
        #         'error': 'Access denied'
        #     }, status=403)
        
        # Generate secure URL (now returns worker URL)
        secure_url = r2_security.generate_signed_url(
            key=secure_key,
            expiration=3600,  # 1 hour
            user_id=request.user.id
        )
        
        if not secure_url:
            logger.error(f"Failed to generate secure URL for media key: {media_key}")
            return JsonResponse({
                'error': 'Failed to generate secure URL'
            }, status=500)
        
        return JsonResponse({
            'url': secure_url,
            'expires_in': 3600
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in get_secure_media_url: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error'
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def serve_secure_media(request, media_key):
    """
    Serve media files through secure access control
    This redirects to the worker URL after authentication
    """
    try:
        logger.info(f"Serving secure media for user {request.user.id}, media key: {media_key}")
        
        # Add media/ prefix for subject_pdfs paths
        secure_key = media_key
        if media_key.startswith('subject_pdfs/'):
            secure_key = f"media/{media_key}"
        
        # Check if user has access to this resource
        if not r2_security.check_user_access(request.user, media_key):
            logger.warning(f"Access denied for user {request.user.id} to media key: {media_key}")
            return JsonResponse({
                'error': 'Access denied'
            }, status=403)
        
        # Generate secure URL (worker URL)
        secure_url = r2_security.generate_signed_url(
            key=secure_key,
            expiration=3600,
            user_id=request.user.id
        )
        
        if not secure_url:
            logger.error(f"Failed to generate secure URL for media key: {media_key}")
            raise Http404("Media file not found")
        
        # Redirect to the worker URL
        from django.shortcuts import redirect
        return redirect(secure_url)
        
    except Exception as e:
        logger.error(f"Error serving secure media: {str(e)}")
        raise Http404("Media file not found")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_access_token(request):
    """
    Generate JWT access token for media resources
    """
    try:
        data = json.loads(request.body)
        media_key = data.get('media_key')
        permissions = data.get('permissions', ['read'])
        
        if not media_key:
            return JsonResponse({
                'error': 'Media key is required'
            }, status=400)
        
        # Check if user has access to this resource
        if not r2_security.check_user_access(request.user, media_key):
            return JsonResponse({
                'error': 'Access denied'
            }, status=403)
        
        # Generate access token
        access_token = r2_security.generate_access_token(
            user_id=request.user.id,
            resource_key=media_key,
            permissions=permissions
        )
        
        return JsonResponse({
            'access_token': access_token,
            'media_key': media_key,
            'permissions': permissions
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    except Exception as e:
        logger.error(f"Error generating access token: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_access_token(request):
    """
    Validate JWT access token for media resources
    """
    try:
        data = json.loads(request.body)
        token = data.get('token')
        media_key = data.get('media_key')
        
        if not token:
            return JsonResponse({
                'error': 'Token is required'
            }, status=400)
        
        # Validate token
        payload = r2_security.validate_access_token(token, media_key)
        
        if not payload:
            return JsonResponse({
                'error': 'Invalid or expired token'
            }, status=401)
        
        return JsonResponse({
            'valid': True,
            'payload': payload
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    except Exception as e:
        logger.error(f"Error validating access token: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_upload_credentials(request):
    """
    Get credentials for secure file upload to R2
    """
    try:
        data = json.loads(request.body)
        filename = data.get('filename')
        content_type = data.get('content_type')
        size = data.get('size')
        
        if not all([filename, content_type, size]):
            return JsonResponse({
                'error': 'filename, content_type, and size are required'
            }, status=400)
        
        # Generate upload credentials
        credentials = r2_security.get_upload_credentials(
            user=request.user,
            filename=filename,
            content_type=content_type,
            size=size
        )
        
        return JsonResponse(credentials)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    except Exception as e:
        logger.error(f"Error getting upload credentials: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def complete_upload(request):
    """
    Complete and validate file upload
    """
    try:
        data = json.loads(request.body)
        key = data.get('key')
        upload_id = data.get('upload_id')
        
        if not all([key, upload_id]):
            return JsonResponse({
                'error': 'key and upload_id are required'
            }, status=400)
        
        # Validate upload completion
        success = r2_security.validate_upload_completion(
            key=key,
            upload_id=upload_id,
            user_id=request.user.id
        )
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Upload completed successfully'
            })
        else:
            return JsonResponse({
                'error': 'Upload validation failed'
            }, status=400)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    except Exception as e:
        logger.error(f"Error completing upload: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_media(request):
    """
    Delete media file from R2
    """
    try:
        data = json.loads(request.body)
        media_key = data.get('media_key')
        
        if not media_key:
            return JsonResponse({
                'error': 'Media key is required'
            }, status=400)
        
        # Check if user has permission to delete this resource
        if not r2_security.check_user_access(request.user, media_key):
            return JsonResponse({
                'error': 'Access denied'
            }, status=403)
        
        # Delete the object
        success = r2_security.delete_object(
            key=media_key,
            user_id=request.user.id
        )
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Media deleted successfully'
            })
        else:
            return JsonResponse({
                'error': 'Failed to delete media'
            }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    except Exception as e:
        logger.error(f"Error deleting media: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error'
        }, status=500)
