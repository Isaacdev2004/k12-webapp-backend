"""
Zoom Recording Service for downloading and uploading recordings automatically
"""
import os
import logging
import requests
import tempfile
import random
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.core.files.base import ContentFile
from typing import Optional, Dict, Any, List
from .models import ZoomRecording, ZoomWebhookLog, SubjectRecordingVideo
import boto3
from botocore.exceptions import ClientError
import jwt
import time

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

logger = logging.getLogger(__name__)


class ZoomRecordingService:
    """Service to handle Zoom recording operations using Server-to-Server OAuth"""
    
    def __init__(self):
        self.account_id = settings.ZOOM_S2S_ACCOUNT_ID
        self.client_id = settings.ZOOM_S2S_CLIENT_ID
        self.client_secret = settings.ZOOM_S2S_CLIENT_SECRET
        self.base_url = "https://api.zoom.us/v2"
        self.access_token = None
        self.token_expires_at = None
        
        # R2/S3 configuration
        self.r2_client = boto3.client(
            's3',
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name='auto'
        )
        self.bucket_name = settings.R2_STORAGE_BUCKET_NAME

    def _get_or_create_default_subject(self):
        """Get or create a default subject for unassigned recordings"""
        from .models import Course, Subject
        
        try:
            # Try to find existing default course and subject
            default_course, created = Course.objects.get_or_create(
                name="Unassigned Recordings",
                defaults={
                    'description': 'Default course for Zoom recordings without associated live classes',
                    'published': True
                }
            )
            
            if created:
                logger.info("Created default course for unassigned recordings")
            
            default_subject, created = Subject.objects.get_or_create(
                course=default_course,
                name="Unassigned Recordings",
                defaults={}
            )
            
            if created:
                logger.info("Created default subject for unassigned recordings")
            
            return default_subject
            
        except Exception as e:
            logger.error(f"Failed to create default subject: {str(e)}")
            raise

    def _generate_access_token(self) -> str:
        """Generate access token for Zoom Server-to-Server OAuth"""
        try:
            # Create JWT payload
            payload = {
                'iss': self.client_id,
                'exp': int(time.time()) + 3600  # Token expires in 1 hour
            }
            
            # Generate JWT token
            token = jwt.encode(payload, self.client_secret, algorithm='HS256')
            
            # Request access token
            auth_url = "https://zoom.us/oauth/token"
            headers = {
                'Authorization': f'Basic {self._get_basic_auth_string()}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            data = {
                'grant_type': 'account_credentials',
                'account_id': self.account_id
            }
            
            response = requests.post(auth_url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data['access_token']
            self.token_expires_at = timezone.now() + timedelta(seconds=token_data.get('expires_in', 3600))
            
            logger.info("Successfully generated Zoom access token")
            return self.access_token
            
        except Exception as e:
            logger.error(f"Failed to generate Zoom access token: {str(e)}")
            raise

    def _get_basic_auth_string(self) -> str:
        """Generate basic auth string for Zoom OAuth"""
        import base64
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return encoded_credentials

    def _get_access_token(self) -> str:
        """Get valid access token, refresh if necessary"""
        if not self.access_token or (self.token_expires_at and timezone.now() >= self.token_expires_at):
            return self._generate_access_token()
        return self.access_token

    def _make_api_request(self, endpoint: str, method: str = 'GET', **kwargs) -> Dict[Any, Any]:
        """Make authenticated API request to Zoom"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Content-Type': 'application/json'
        }
        
        response = requests.request(method, url, headers=headers, **kwargs)
        
        if response.status_code == 401:  # Token expired, retry once
            self.access_token = None
            headers['Authorization'] = f'Bearer {self._get_access_token()}'
            response = requests.request(method, url, headers=headers, **kwargs)
        
        response.raise_for_status()
        return response.json()

    def get_meeting_recordings(self, meeting_id: str) -> List[Dict]:
        """Get recordings for a specific meeting"""
        try:
            endpoint = f"/meetings/{meeting_id}/recordings"
            data = self._make_api_request(endpoint)
            return data.get('recording_files', [])
        except Exception as e:
            logger.error(f"Failed to get recordings for meeting {meeting_id}: {str(e)}")
            return []

    def get_recordings_by_date_range(self, start_date: str, end_date: str, user_id: str = 'me') -> List[Dict]:
        """Get recordings within a date range"""
        try:
            endpoint = f"/users/{user_id}/recordings"
            params = {
                'from': start_date,  # YYYY-MM-DD format
                'to': end_date,      # YYYY-MM-DD format
                'page_size': 300
            }
            data = self._make_api_request(endpoint, params=params)
            return data.get('meetings', [])
        except Exception as e:
            logger.error(f"Failed to get recordings for date range {start_date} to {end_date}: {str(e)}")
            return []

    def download_recording(self, download_url: str, download_token: str = None) -> bytes:
        """Download recording file from Zoom"""
        try:
            headers = {}
            
            # Handle different types of Zoom download URLs
            if 'webhook_download' in download_url:
                # Webhook download URLs are signed URLs that don't need additional authentication
                # but we need to pass the download_token as an Authorization header
                if download_token:
                    headers['Authorization'] = f'Bearer {download_token}'
                    logger.info("Using download token from webhook as bearer token")
                else:
                    # Try without any additional auth - webhook URLs are often pre-signed
                    logger.info("Using webhook download URL without additional authentication")
            elif download_token:
                # For regular downloads with download token
                if 'access_token=' in download_url:
                    # Token is already in URL, use as-is
                    logger.info("Using download URL with embedded access token")
                else:
                    # Add token as query parameter
                    separator = '&' if '?' in download_url else '?'
                    download_url = f"{download_url}{separator}access_token={download_token}"
                    logger.info("Added access token as query parameter")
            else:
                # Use OAuth bearer token for API-retrieved downloads
                headers['Authorization'] = f'Bearer {self._get_access_token()}'
                logger.info("Using OAuth bearer token for authentication")
            
            logger.info(f"Attempting download from: {download_url[:100]}...")
            
            # Add user agent for better compatibility
            headers['User-Agent'] = 'Aakhyaan-Recording-Service/1.0'
            
            response = requests.get(download_url, headers=headers, stream=True, timeout=300)
            response.raise_for_status()
            
            # Read the content
            content = b''
            downloaded_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
                    downloaded_size += len(chunk)
                    
                    # Log progress for large files
                    if downloaded_size % (10 * 1024 * 1024) == 0:  # Every 10MB
                        logger.info(f"Downloaded {downloaded_size / (1024*1024):.1f} MB...")
            
            logger.info(f"Successfully downloaded recording, size: {len(content)} bytes")
            return content
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error(f"Authentication failed for download. URL type: {'webhook' if 'webhook_download' in download_url else 'regular'}")
                logger.error(f"URL: {download_url[:100]}, Token present: {bool(download_token)}")
                logger.error(f"Response: {e.response.text if hasattr(e.response, 'text') else 'No response text'}")
                
                # For webhook downloads, try without any authentication
                if 'webhook_download' in download_url and download_token:
                    logger.info("Retrying webhook download without authentication...")
                    headers = {'User-Agent': 'Aakhyaan-Recording-Service/1.0'}
                    
                    # Retry once without any auth
                    response = requests.get(download_url, headers=headers, stream=True, timeout=300)
                    response.raise_for_status()
                    
                    content = b''
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            content += chunk
                    
                    logger.info(f"Successfully downloaded recording without auth, size: {len(content)} bytes")
                    return content
            raise
        except Exception as e:
            logger.error(f"Failed to download recording from {download_url[:100]}: {str(e)}")
            raise

    def upload_to_r2(self, file_content: bytes, key: str, content_type: str = 'video/mp4') -> str:
        """Upload file to R2 storage"""
        try:
            # Upload to R2
            new_r2_client = boto3.client(
                's3',
                endpoint_url=settings.R2_ENDPOINT_URL,
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                region_name='auto'
            )
            new_r2_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_content,
                ContentType=content_type,
                CacheControl='max-age=86400'
            )
            
            # Generate URL through Cloudflare Worker for security
            if hasattr(settings, 'CLOUDFLARE_WORKER_URL') and settings.CLOUDFLARE_WORKER_URL:
                url = f"{settings.CLOUDFLARE_WORKER_URL}/{key}"
            elif settings.R2_CUSTOM_DOMAIN:
                url = f"{settings.R2_CUSTOM_DOMAIN}/{key}"
            else:
                url = f"{settings.R2_ENDPOINT_URL}/{self.bucket_name}/{key}"
            
            logger.info(f"Successfully uploaded file to R2: {key}")
            return url
            
        except ClientError as e:
            logger.error(f"Failed to upload to R2: {str(e)}")
            raise

    def extract_video_thumbnail(self, video_content: bytes, duration_seconds: int) -> Optional[bytes]:
        """Extract a random frame from video as thumbnail"""
        if not CV2_AVAILABLE:
            logger.warning("OpenCV not available, skipping thumbnail extraction")
            return None
            
        try:
            # Write video content to temporary file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_video:
                temp_video.write(video_content)
                temp_video_path = temp_video.name
            
            try:
                # Open video with OpenCV
                cap = cv2.VideoCapture(temp_video_path)
                
                # Get video properties
                fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                
                if total_frames == 0 or fps == 0:
                    logger.warning("Could not read video properties for thumbnail extraction")
                    return None
                
                # Choose a random frame from the middle 80% of the video (avoid start/end)
                start_frame = int(total_frames * 0.1)  # Skip first 10%
                end_frame = int(total_frames * 0.9)    # Skip last 10%
                
                if start_frame >= end_frame:
                    # For very short videos, use the middle frame
                    random_frame = total_frames // 2
                else:
                    random_frame = random.randint(start_frame, end_frame)
                
                # Seek to the random frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, random_frame)
                
                # Read the frame
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    logger.warning("Could not read frame for thumbnail extraction")
                    return None
                
                # Resize frame to thumbnail size (maintain aspect ratio)
                height, width = frame.shape[:2]
                max_size = 400
                
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                
                resized_frame = cv2.resize(frame, (new_width, new_height))
                
                # Convert to JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                _, buffer = cv2.imencode('.jpg', resized_frame, encode_param)
                
                logger.info(f"Successfully extracted thumbnail from frame {random_frame}/{total_frames}")
                return buffer.tobytes()
                
            finally:
                cap.release()
                
        except Exception as e:
            logger.error(f"Failed to extract thumbnail: {str(e)}")
            return None
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_video_path)
            except:
                pass

    def process_recording(self, zoom_recording) -> bool:
        """Process a single Zoom recording: download and upload to R2"""
        from .models import ZoomRecording, SubjectRecordingVideo
        
        try:
            # Update status to processing
            zoom_recording.status = 'processing'
            zoom_recording.processing_started_at = timezone.now()
            zoom_recording.save()
            
            logger.info(f"Starting to process recording {zoom_recording.zoom_recording_id}")
            
            # Download the recording
            try:
                file_content = self.download_recording(
                    zoom_recording.zoom_download_url,
                    zoom_recording.download_token
                )
                logger.info(f"Successfully downloaded recording {zoom_recording.zoom_recording_id}, size: {len(file_content) / (1024*1024):.2f} MB")
            except Exception as download_error:
                raise Exception(f"Download failed: {str(download_error)}")
            
            # Generate storage key
            timestamp = zoom_recording.recording_start_time.strftime('%Y%m%d_%H%M%S')
            filename = f"zoom_recordings/{timestamp}_{zoom_recording.zoom_recording_id}.{zoom_recording.file_type}"
            
            # Upload to R2
            try:
                r2_url = self.upload_to_r2(file_content, filename)
                logger.info(f"Successfully uploaded recording {zoom_recording.zoom_recording_id} to R2: {filename}")
            except Exception as upload_error:
                raise Exception(f"R2 upload failed: {str(upload_error)}")
            
            # Update zoom recording
            zoom_recording.r2_storage_key = filename
            zoom_recording.r2_storage_url = r2_url
            zoom_recording.status = 'completed'
            zoom_recording.processing_completed_at = timezone.now()
            zoom_recording.save()
            
            # Extract thumbnail from video (do this for all recordings)
            thumbnail_content = None
            thumbnail_url = None
            
            try:
                logger.info(f"Extracting thumbnail for recording {zoom_recording.zoom_recording_id}")
                thumbnail_content = self.extract_video_thumbnail(file_content, zoom_recording.duration)
                
                if thumbnail_content:
                    # Upload thumbnail to R2
                    thumbnail_filename = f"media/video_thumbnails/{timestamp}_{zoom_recording.zoom_recording_id}_thumb.jpg"
                    thumbnail_url = self.upload_to_r2(thumbnail_content, thumbnail_filename, 'image/jpeg')
                    logger.info(f"Successfully uploaded thumbnail: {thumbnail_filename}")
                else:
                    logger.warning(f"Could not extract thumbnail for recording {zoom_recording.zoom_recording_id}")
            except Exception as thumb_error:
                logger.error(f"Thumbnail extraction failed for recording {zoom_recording.zoom_recording_id}: {str(thumb_error)}")
            
            # Create or update SubjectRecordingVideo for all recordings
            try:
                # Get subject and determine title/settings
                if zoom_recording.live_class and zoom_recording.live_class.subject:
                    # Use live class subject and settings
                    subject = zoom_recording.live_class.subject
                    title = f"{zoom_recording.live_class.title} - Recording"
                    is_free = zoom_recording.live_class.is_free
                    is_active = True  # Active for matched recordings
                    logger.info(f"Using live class subject: {subject.name}")
                else:
                    # Get or create default subject for unassigned recordings
                    subject = self._get_or_create_default_subject()
                    title = f"Zoom Recording - {zoom_recording.zoom_meeting_id}"
                    is_free = False  # Not free for unassigned recordings
                    is_active = False  # Not active for unassigned recordings
                    logger.info(f"Using default subject for unassigned recording: {subject.name}")
                
                # Check if SubjectRecordingVideo already exists
                if not zoom_recording.subject_recording_video:
                    subject_video = SubjectRecordingVideo.objects.create(
                        subject=subject,
                        title=title,
                        video_url=r2_url,
                        video_duration=zoom_recording.duration,  # Keep in seconds
                        is_active=is_active,
                        is_free=is_free,
                        is_auto_created=True  # Mark as automatically created from Zoom recording
                    )
                    
                    # Set thumbnail if extracted successfully
                    if thumbnail_content:
                        # Save thumbnail as Django file field
                        subject_video.thumbnail.save(
                            f"{zoom_recording.zoom_recording_id}_thumb.jpg",
                            ContentFile(thumbnail_content),
                            save=False
                        )
                    
                    subject_video.save()
                    zoom_recording.subject_recording_video = subject_video
                    zoom_recording.save()
                    logger.info(f"Created SubjectRecordingVideo {subject_video.id} for recording {zoom_recording.zoom_recording_id} with thumbnail: {bool(thumbnail_content)}")
                else:
                    # Update existing video
                    subject_video = zoom_recording.subject_recording_video
                    subject_video.video_url = r2_url
                    subject_video.video_duration = zoom_recording.duration
                    
                    # Update thumbnail if extracted successfully
                    if thumbnail_content:
                        subject_video.thumbnail.save(
                            f"{zoom_recording.zoom_recording_id}_thumb.jpg",
                            ContentFile(thumbnail_content),
                            save=False
                        )
                    
                    subject_video.save()
                    logger.info(f"Updated SubjectRecordingVideo {subject_video.id} for recording {zoom_recording.zoom_recording_id} with thumbnail: {bool(thumbnail_content)}")
                    
            except Exception as e:
                logger.error(f"Failed to create/update SubjectRecordingVideo for recording {zoom_recording.zoom_recording_id}: {str(e)}")
            
            logger.info(f"Successfully processed recording {zoom_recording.zoom_recording_id}")
            return True
            
        except Exception as e:
            # Update status to failed
            zoom_recording.status = 'failed'
            zoom_recording.error_message = str(e)
            zoom_recording.processing_completed_at = timezone.now()
            zoom_recording.save()
            
            logger.error(f"Failed to process recording {zoom_recording.zoom_recording_id}: {str(e)}")
            return False

    def sync_recordings_from_webhook(self, webhook_payload: Dict) -> Optional[Any]:
        """Create ZoomRecording from webhook payload"""
        from .models import ZoomRecording, LiveClass, ZoomAllowedHost
        
        try:
            object_data = webhook_payload.get('payload', {}).get('object', {})
            meeting_id = object_data.get('id')
            meeting_uuid = object_data.get('uuid')
            
            # Extract host email from webhook payload
            host_email = object_data.get('host_email', '')
            
            # Check if host is allowed to have recordings saved
            if not self._is_host_allowed(host_email):
                logger.info(f"Skipping recording for meeting {meeting_id} - host {host_email} not in allowed list")
                return None
            
            # Extract download token from top level of webhook payload
            download_token = webhook_payload.get('download_token')
            
            # Get recording files
            recording_files = object_data.get('recording_files', [])
            
            for recording_file in recording_files:
                if recording_file.get('file_type') in ['MP4', 'mp4']:  # Only process video files
                    recording_id = recording_file.get('id')
                    
                    # Check if recording already exists
                    if ZoomRecording.objects.filter(zoom_recording_id=recording_id).exists():
                        logger.info(f"Recording {recording_id} already exists, skipping")
                        continue
                    
                    # Try to find associated live class
                    live_class = None
                    try:
                        live_class = LiveClass.objects.get(zoom_meeting_id=meeting_id)
                    except LiveClass.DoesNotExist:
                        logger.warning(f"No live class found for Zoom meeting {meeting_id}")
                    
                    # Calculate duration from recording_start and recording_end timestamps
                    recording_start = datetime.fromisoformat(recording_file.get('recording_start').replace('Z', '+00:00'))
                    recording_end = datetime.fromisoformat(recording_file.get('recording_end').replace('Z', '+00:00'))
                    duration_seconds = int((recording_end - recording_start).total_seconds())
                    
                    # Create ZoomRecording
                    zoom_recording = ZoomRecording.objects.create(
                        zoom_meeting_id=meeting_id,
                        zoom_recording_id=recording_id,
                        zoom_meeting_uuid=meeting_uuid,
                        host_email=host_email,
                        recording_start_time=recording_start,
                        recording_end_time=recording_end,
                        duration=duration_seconds,  # Duration in seconds calculated from timestamps
                        file_size=recording_file.get('file_size', 0),
                        file_type=recording_file.get('file_type', 'mp4').lower(),
                        zoom_download_url=recording_file.get('download_url'),
                        download_token=download_token,  # Use token from top level of webhook payload
                        live_class=live_class,
                        status='pending'
                    )
                    
                    logger.info(f"Created ZoomRecording {recording_id} for meeting {meeting_id} from host {host_email} (duration: {duration_seconds}s, token: {bool(download_token)})")
                    return zoom_recording
                    
        except Exception as e:
            logger.error(f"Failed to sync recording from webhook: {str(e)}")
            return None
    
    def _is_host_allowed(self, host_email: str) -> bool:
        """Check if a host email is allowed to have recordings saved"""
        from .models import ZoomAllowedHost
        
        if not host_email:
            logger.warning("No host email provided, skipping recording")
            return False
        
        try:
            allowed_host = ZoomAllowedHost.objects.get(email=host_email, enabled=True)
            return True
        except ZoomAllowedHost.DoesNotExist:
            # Check if there are any allowed hosts configured
            if ZoomAllowedHost.objects.exists():
                # If there are allowed hosts configured, only save recordings from those hosts
                logger.info(f"Host {host_email} not in allowed list")
                return False
            else:
                # If no allowed hosts are configured, allow all recordings (backward compatibility)
                logger.info("No allowed hosts configured, allowing all recordings")
                return False

    def process_pending_recordings(self) -> Dict[str, int]:
        """Process all pending recordings"""
        from .models import ZoomRecording
        
        pending_recordings = ZoomRecording.objects.filter(status='pending')
        
        results = {
            'processed': 0,
            'failed': 0,
            'total': pending_recordings.count()
        }
        
        for recording in pending_recordings:
            if self.process_recording(recording):
                results['processed'] += 1
            else:
                results['failed'] += 1
        
        logger.info(f"Processed recordings: {results}")
        return results

    def cleanup_old_recordings(self, days: int = 30) -> int:
        """Clean up recordings older than specified days"""
        from .models import ZoomRecording
        
        cutoff_date = timezone.now() - timedelta(days=days)
        old_recordings = ZoomRecording.objects.filter(
            created_at__lt=cutoff_date,
            status='completed'
        )
        
        deleted_count = 0
        for recording in old_recordings:
            try:
                # Optionally delete from R2 storage as well
                if recording.r2_storage_key:
                    self.r2_client.delete_object(
                        Bucket=self.bucket_name,
                        Key=recording.r2_storage_key
                    )
                
                recording.delete()
                deleted_count += 1
                
            except Exception as e:
                logger.error(f"Failed to delete recording {recording.id}: {str(e)}")
        
        logger.info(f"Cleaned up {deleted_count} old recordings")
        return deleted_count
