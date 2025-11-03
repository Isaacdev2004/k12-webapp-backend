"""
Management command to retry stuck or failed Zoom recordings
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import ZoomRecording
from api.zoom_service import ZoomRecordingService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Retry stuck or failed Zoom recordings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recording-ids',
            nargs='*',
            help='Specific recording IDs to retry (space separated)',
        )
        parser.add_argument(
            '--status',
            choices=['processing', 'failed', 'pending'],
            default='processing',
            help='Status of recordings to retry (default: processing)',
        )
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=2,
            help='Maximum age in hours for stuck recordings (default: 2)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force retry even if recently processed',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually processing',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting stuck recordings retry process...'))
        
        zoom_service = ZoomRecordingService()
        
        # Build queryset
        queryset = ZoomRecording.objects.all()
        
        if options['recording_ids']:
            # Process specific recording IDs
            queryset = queryset.filter(zoom_recording_id__in=options['recording_ids'])
            self.stdout.write(f"Processing specific recordings: {', '.join(options['recording_ids'])}")
        else:
            # Filter by status
            queryset = queryset.filter(status=options['status'])
            
            # Filter by age for stuck recordings
            if not options['force'] and options['status'] == 'processing':
                cutoff_time = timezone.now() - timedelta(hours=options['max_age_hours'])
                queryset = queryset.filter(processing_started_at__lt=cutoff_time)
                self.stdout.write(f"Processing {options['status']} recordings older than {options['max_age_hours']} hours")
            else:
                self.stdout.write(f"Processing all {options['status']} recordings")
        
        recordings = list(queryset.order_by('created_at'))
        
        if not recordings:
            self.stdout.write(self.style.WARNING('No recordings found matching criteria'))
            return
        
        self.stdout.write(f"Found {len(recordings)} recordings to process")
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN - No actual processing will occur'))
            for recording in recordings:
                self.stdout.write(
                    f"Would process: {recording.zoom_recording_id} "
                    f"(Status: {recording.status}, "
                    f"Created: {recording.created_at}, "
                    f"Started: {recording.processing_started_at})"
                )
            return
        
        # Process recordings
        success_count = 0
        error_count = 0
        
        for i, recording in enumerate(recordings, 1):
            self.stdout.write(f"Processing {i}/{len(recordings)}: {recording.zoom_recording_id}")
            
            try:
                # Reset status to pending before processing
                recording.status = 'pending'
                recording.error_message = None
                recording.processing_started_at = None
                recording.processing_completed_at = None
                recording.save()
                
                # Process the recording
                success = zoom_service.process_recording(recording)
                
                if success:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Successfully processed {recording.zoom_recording_id}")
                    )
                else:
                    error_count += 1
                    recording.refresh_from_db()
                    error_msg = recording.error_message or "Unknown error"
                    self.stdout.write(
                        self.style.ERROR(f"✗ Failed to process {recording.zoom_recording_id}: {error_msg}")
                    )
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"✗ Exception processing {recording.zoom_recording_id}: {str(e)}")
                )
                
                # Update recording status to failed
                try:
                    recording.status = 'failed'
                    recording.error_message = str(e)
                    recording.processing_completed_at = timezone.now()
                    recording.save()
                except Exception as save_error:
                    self.stdout.write(
                        self.style.ERROR(f"Failed to update recording status: {str(save_error)}")
                    )
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f'\nProcessing complete:'))
        self.stdout.write(f"Total processed: {len(recordings)}")
        self.stdout.write(self.style.SUCCESS(f"Successful: {success_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"Failed: {error_count}"))
        else:
            self.stdout.write(f"Failed: {error_count}")
