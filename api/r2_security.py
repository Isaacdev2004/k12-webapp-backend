"""
R2 Security Service for managing secure access to Cloudflare R2 objects
"""
import boto3
import jwt
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from django.conf import settings
from django.core.cache import cache
from botocore.exceptions import ClientError
from botocore.config import Config as BotoConfig
import logging

logger = logging.getLogger(__name__)


class R2SecurityService:
    """Service for managing secure R2 access"""
    
    def __init__(self):
        self.r2_client = self._create_r2_client()
        self.bucket_name = settings.R2_STORAGE_BUCKET_NAME
        
    def _create_r2_client(self):
        """Create boto3 client for R2"""
        return boto3.client(
            's3',
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            endpoint_url=settings.R2_ENDPOINT_URL,
            region_name='auto',
            config=BotoConfig(s3={'addressing_style': 'path'})
        )
    
    def generate_signed_url(self, key: str, expiration: int = 3600, user_id: int = None) -> Optional[str]:
        """
        Generate a URL through Cloudflare Worker for secure R2 object access
        This replaces the traditional signed URL approach with worker-based security
        
        Args:
            key: Object key in R2 (full path like zoom_recordings/file.mp4)
            expiration: Not used with worker, but kept for compatibility
            user_id: ID of the user requesting access (for audit)
            
        Returns:
            Worker URL or fallback to signed URL if worker not configured
        """
        try:
            # Clean the key
            clean_key = key.lstrip('/')
            
            # Files that are stored at root level in R2 (no media/ prefix needed)
            root_level_prefixes = [
                'zoom_recordings/',  # Zoom recordings are stored at root
                'media/',           # Already has media/ prefix
            ]
            
            # Check if key needs media/ prefix
            needs_media_prefix = True
            for prefix in root_level_prefixes:
                if clean_key.startswith(prefix):
                    needs_media_prefix = False
                    break
            
            # Add media/ prefix for Django FileField uploads (PDFs, etc.)
            if needs_media_prefix:
                clean_key = f"{clean_key}"
            
            # Try to use Cloudflare Worker first (preferred for security)
            if hasattr(settings, 'CLOUDFLARE_WORKER_URL') and settings.CLOUDFLARE_WORKER_URL:
                worker_url = f"{settings.CLOUDFLARE_WORKER_URL}/{clean_key}"
                
                # Log access for audit
                if user_id:
                    logger.info(f"Generated worker URL for user {user_id}, key: {clean_key}")
                
                return worker_url
            
            # Fallback to traditional signed URL if worker not configured
            else:
                logger.warning("CLOUDFLARE_WORKER_URL not configured, falling back to signed URLs")
                
                # Generate presigned URL with the correct key
                url = self.r2_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.bucket_name,
                        'Key': clean_key
                    },
                    ExpiresIn=expiration
                )
                
                # Log access for audit
                if user_id:
                    logger.info(f"Generated fallback signed URL for user {user_id}, key: {clean_key}, expires in: {expiration}s")
                
                return url
            
        except Exception as e:
            logger.error(f"Error generating secure URL for key {key}: {str(e)}")
            return None
    
    def generate_access_token(self, user_id: int, resource_key: str, permissions: list = None) -> str:
        """
        Generate JWT token for R2 resource access
        
        Args:
            user_id: ID of the user
            resource_key: Key of the R2 resource
            permissions: List of permissions (read, write, delete)
            
        Returns:
            JWT token string
        """
        permissions = permissions or ['read']
        
        payload = {
            'user_id': user_id,
            'resource_key': resource_key,
            'permissions': permissions,
            'exp': datetime.utcnow() + timedelta(seconds=settings.R2_ACCESS_TOKEN_EXPIRATION),
            'iat': datetime.utcnow(),
            'iss': 'codingforkids-api'
        }
        
        token = jwt.encode(
            payload,
            settings.R2_ACCESS_TOKEN_SECRET,
            algorithm=settings.R2_ACCESS_TOKEN_ALGORITHM
        )
        
        logger.info(f"Generated access token for user {user_id}, resource: {resource_key}")
        return token
    
    def validate_access_token(self, token: str, resource_key: str = None) -> Optional[Dict[str, Any]]:
        """
        Validate JWT token for resource access
        
        Args:
            token: JWT token to validate
            resource_key: Resource key to validate against (optional)
            
        Returns:
            Token payload if valid, None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                settings.R2_ACCESS_TOKEN_SECRET,
                algorithms=[settings.R2_ACCESS_TOKEN_ALGORITHM]
            )
            
            # Check if token is for specific resource
            if resource_key and payload.get('resource_key') != resource_key:
                logger.warning(f"Token resource mismatch: expected {resource_key}, got {payload.get('resource_key')}")
                return None
                
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Access token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid access token: {str(e)}")
            return None
    
    def check_user_access(self, user, resource_key: str) -> bool:
        """
        Check if user has access to specific resource
        
        Args:
            user: Django user object
            resource_key: R2 resource key
            
        Returns:
            True if user has access, False otherwise
        """
        # Admin users have access to everything
        if user.is_staff or user.is_superuser:
            return True
        
        # Allow authenticated users to access media files for now
        # TODO: Implement proper access control based on enrollments/purchases
        if user.is_authenticated:
            logger.info(f"Granting access to authenticated user {user.id} for resource {resource_key}")
            return True
            
        # Check if resource belongs to user's courses/subjects (original logic kept for future use)
        if resource_key.startswith('media/recordings/'):
            # Extract subject/course info from key
            # Format: media/recordings/subject_id/video_name.mp4
            try:
                parts = resource_key.split('/')
                if len(parts) >= 3:
                    subject_id = parts[2].split('_')[0]  # Extract subject ID
                    # Check if user has access to this subject
                    if hasattr(user, 'subjects') and user.subjects.filter(id=subject_id).exists():
                        return True
            except (IndexError, ValueError):
                logger.warning(f"Could not parse resource key: {resource_key}")
                
        # Default: deny access for unauthenticated users
        logger.warning(f"Access denied for user {user.id if user.is_authenticated else 'anonymous'} to resource {resource_key}")
        return False
    
    def get_upload_credentials(self, user, filename: str, content_type: str, size: int) -> Dict[str, Any]:
        """
        Generate credentials for secure file upload
        
        Args:
            user: Django user object
            filename: Name of the file to upload
            content_type: MIME type of the file
            size: Size of the file in bytes
            
        Returns:
            Dictionary with upload credentials
        """
        # Generate unique key
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        safe_filename = filename.replace(' ', '_').replace('..', '_')
        key = f"media/uploads/{user.id}/{timestamp}_{safe_filename}"
        
        # Generate upload ID for tracking
        upload_id = hashlib.md5(f"{key}_{user.id}_{timestamp}".encode()).hexdigest()
        
        try:
            # For large files, use multipart upload
            if size > 50 * 1024 * 1024:  # 50MB threshold
                response = self.r2_client.create_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=key,
                    ContentType=content_type,
                    CacheControl='max-age=86400'
                )
                
                return {
                    'type': 'multipart',
                    'key': key,
                    'upload_id': response['UploadId'],
                    'bucket': self.bucket_name,
                    'content_type': content_type
                }
            else:
                # For smaller files, use presigned POST
                fields = {
                    'Content-Type': content_type,
                    'Cache-Control': 'max-age=86400'
                }
                
                conditions = [
                    {'Content-Type': content_type},
                    ['content-length-range', 1, size * 2]  # Allow up to double the size
                ]
                
                response = self.r2_client.generate_presigned_post(
                    Bucket=self.bucket_name,
                    Key=key,
                    Fields=fields,
                    Conditions=conditions,
                    ExpiresIn=3600  # 1 hour
                )
                
                return {
                    'type': 'presigned_post',
                    'key': key,
                    'upload_id': upload_id,
                    'url': response['url'],
                    'fields': response['fields']
                }
                
        except ClientError as e:
            logger.error(f"Error generating upload credentials: {str(e)}")
            raise
    
    def validate_upload_completion(self, key: str, upload_id: str, user_id: int) -> bool:
        """
        Validate that file upload was completed successfully
        
        Args:
            key: R2 object key
            upload_id: Upload ID from credentials
            user_id: ID of the user who uploaded
            
        Returns:
            True if upload is valid and complete
        """
        try:
            # Check if object exists in R2
            self.r2_client.head_object(Bucket=self.bucket_name, Key=key)
            
            # Log successful upload
            logger.info(f"Upload completed successfully - User: {user_id}, Key: {key}, Upload ID: {upload_id}")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"Upload validation failed - Object not found: {key}")
                return False
            else:
                logger.error(f"Error validating upload: {str(e)}")
                return False
    
    def delete_object(self, key: str, user_id: int = None) -> bool:
        """
        Securely delete R2 object
        
        Args:
            key: R2 object key to delete
            user_id: ID of user requesting deletion (for audit)
            
        Returns:
            True if deletion successful
        """
        try:
            self.r2_client.delete_object(Bucket=self.bucket_name, Key=key)
            
            if user_id:
                logger.info(f"Object deleted by user {user_id}: {key}")
            else:
                logger.info(f"Object deleted: {key}")
                
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting object {key}: {str(e)}")
            return False


# Singleton instance
r2_security = R2SecurityService()