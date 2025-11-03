"""
Utility functions for managing Zoom recordings
"""
from django.utils import timezone
from datetime import timedelta
from api.models import ZoomRecording
import logging

logger = logging.getLogger(__name__)


def reset_stuck_recordings(max_age_hours=2):
    """
    Reset recordings that have been stuck in 'processing' status for too long
    
    Args:
        max_age_hours (int): Maximum hours a recording can be in processing before being reset
        
    Returns:
        int: Number of recordings reset
    """
    cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
    
    stuck_recordings = ZoomRecording.objects.filter(
        status='processing',
        processing_started_at__lt=cutoff_time
    )
    
    count = 0
    for recording in stuck_recordings:
        logger.warning(f"Resetting stuck recording {recording.zoom_recording_id} (stuck since {recording.processing_started_at})")
        recording.status = 'pending'
        recording.error_message = f"Auto-reset: was stuck in processing for more than {max_age_hours} hours"
        recording.processing_started_at = None
        recording.save()
        count += 1
    
    if count > 0:
        logger.info(f"Reset {count} stuck recordings")
    
    return count


def get_recording_statistics():
    """
    Get statistics about recording processing status
    
    Returns:
        dict: Statistics about recordings
    """
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    
    stats = ZoomRecording.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        processing=Count('id', filter=Q(status='processing')),
        completed=Count('id', filter=Q(status='completed')),
        failed=Count('id', filter=Q(status='failed')),
    )
    
    # Check for old processing recordings (potential stuck recordings)
    cutoff_time = timezone.now() - timedelta(hours=2)
    stats['potentially_stuck'] = ZoomRecording.objects.filter(
        status='processing',
        processing_started_at__lt=cutoff_time
    ).count()
    
    return stats


def retry_recording_by_id(recording_id):
    """
    Retry a specific recording by ID
    
    Args:
        recording_id (str): The zoom_recording_id to retry
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        recording = ZoomRecording.objects.get(zoom_recording_id=recording_id)
        
        # Reset the recording
        recording.status = 'pending'
        recording.error_message = None
        recording.processing_started_at = None
        recording.processing_completed_at = None
        recording.save()
        
        # Process it
        from api.zoom_service import ZoomRecordingService
        zoom_service = ZoomRecordingService()
        success = zoom_service.process_recording(recording)
        
        if success:
            return True, f"Successfully processed recording {recording_id}"
        else:
            recording.refresh_from_db()
            error_msg = recording.error_message or "Unknown error"
            return False, f"Failed to process recording {recording_id}: {error_msg}"
            
    except ZoomRecording.DoesNotExist:
        return False, f"Recording {recording_id} not found"
    except Exception as e:
        return False, f"Error processing recording {recording_id}: {str(e)}"
