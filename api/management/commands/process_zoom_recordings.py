"""
Django management command to process Zoom recordings
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import ZoomRecording
from api.zoom_service import ZoomRecordingService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process Zoom recordings: download from Zoom and upload to R2 storage'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sync-days',
            type=int,
            default=7,
            help='Number of days to sync recordings from Zoom (default: 7)'
        )
        parser.add_argument(
            '--process-only',
            action='store_true',
            help='Only process existing pending recordings, do not sync new ones'
        )
        parser.add_argument(
            '--cleanup-days',
            type=int,
            default=0,
            help='Clean up recordings older than specified days (0 = no cleanup)'
        )
        parser.add_argument(
            '--max-concurrent',
            type=int,
            default=3,
            help='Maximum number of recordings to process concurrently (default: 3)'
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting Zoom recording processing...")
        
        zoom_service = ZoomRecordingService()
        
        # Sync new recordings from Zoom (unless --process-only is specified)
        if not options['process_only']:
            self.sync_recordings(zoom_service, options['sync_days'])
        
        # Process pending recordings
        self.process_recordings(zoom_service, options['max_concurrent'])
        
        # Cleanup old recordings if requested
        if options['cleanup_days'] > 0:
            self.cleanup_recordings(zoom_service, options['cleanup_days'])
        
        self.stdout.write(
            self.style.SUCCESS("Zoom recording processing completed!")
        )

    def sync_recordings(self, zoom_service: ZoomRecordingService, sync_days: int):
        """Sync recordings from Zoom for the specified number of days"""
        from datetime import datetime
        from api.models import LiveClass
        
        self.stdout.write(f"Syncing recordings from last {sync_days} days...")
        
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=sync_days)).strftime('%Y-%m-%d')
            
            meetings = zoom_service.get_recordings_by_date_range(start_date, end_date)
            synced_count = 0
            
            for meeting in meetings:
                meeting_id = meeting.get('id')
                meeting_uuid = meeting.get('uuid')
                
                recording_files = meeting.get('recording_files', [])
                
                for recording_file in recording_files:
                    if recording_file.get('file_type') in ['MP4', 'mp4']:
                        recording_id = recording_file.get('id')
                        
                        # Check if recording already exists
                        if ZoomRecording.objects.filter(zoom_recording_id=recording_id).exists():
                            continue
                        
                        # Try to find associated live class
                        live_class = None
                        try:
                            live_class = LiveClass.objects.get(zoom_meeting_id=meeting_id)
                        except LiveClass.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"No live class found for Zoom meeting {meeting_id}"
                                )
                            )
                        
                        # Create ZoomRecording
                        ZoomRecording.objects.create(
                            zoom_meeting_id=meeting_id,
                            zoom_recording_id=recording_id,
                            zoom_meeting_uuid=meeting_uuid,
                            recording_start_time=datetime.fromisoformat(
                                recording_file.get('recording_start').replace('Z', '+00:00')
                            ),
                            recording_end_time=datetime.fromisoformat(
                                recording_file.get('recording_end').replace('Z', '+00:00')
                            ),
                            duration=recording_file.get('play_time', 0) * 1000,  # Convert to milliseconds
                            file_size=recording_file.get('file_size', 0),
                            file_type=recording_file.get('file_type', 'mp4').lower(),
                            zoom_download_url=recording_file.get('download_url'),
                            download_token=recording_file.get('download_token'),
                            live_class=live_class,
                            status='pending'
                        )
                        synced_count += 1
                        
                        self.stdout.write(f"Synced recording {recording_id} from meeting {meeting_id}")
            
            self.stdout.write(
                self.style.SUCCESS(f"Synced {synced_count} new recordings from Zoom")
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to sync recordings: {str(e)}")
            )
            logger.error(f"Failed to sync recordings: {str(e)}")

    def process_recordings(self, zoom_service: ZoomRecordingService, max_concurrent: int):
        """Process pending recordings"""
        pending_recordings = ZoomRecording.objects.filter(status='pending')[:max_concurrent]
        
        if not pending_recordings:
            self.stdout.write("No pending recordings to process")
            return
        
        self.stdout.write(f"Processing {len(pending_recordings)} pending recordings...")
        
        processed = 0
        failed = 0
        
        for recording in pending_recordings:
            self.stdout.write(f"Processing recording {recording.zoom_recording_id}...")
            
            try:
                if zoom_service.process_recording(recording):
                    processed += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Successfully processed {recording.zoom_recording_id}")
                    )
                else:
                    failed += 1
                    self.stdout.write(
                        self.style.ERROR(f"✗ Failed to process {recording.zoom_recording_id}")
                    )
                    
            except Exception as e:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f"✗ Error processing {recording.zoom_recording_id}: {str(e)}")
                )
                logger.error(f"Error processing recording {recording.zoom_recording_id}: {str(e)}")
        
        self.stdout.write(
            self.style.SUCCESS(f"Processing completed: {processed} success, {failed} failed")
        )

    def cleanup_recordings(self, zoom_service: ZoomRecordingService, cleanup_days: int):
        """Clean up old recordings"""
        self.stdout.write(f"Cleaning up recordings older than {cleanup_days} days...")
        
        try:
            deleted_count = zoom_service.cleanup_old_recordings(cleanup_days)
            self.stdout.write(
                self.style.SUCCESS(f"Cleaned up {deleted_count} old recordings")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to cleanup recordings: {str(e)}")
            )
            logger.error(f"Failed to cleanup recordings: {str(e)}")
