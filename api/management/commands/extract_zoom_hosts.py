"""
Django management command to extract unique Zoom host emails from webhook logs
and optionally add them to the allowed hosts list
"""
from django.core.management.base import BaseCommand
from api.models import ZoomWebhookLog, ZoomAllowedHost
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Extract unique Zoom host emails from webhook logs and optionally add them to allowed hosts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--add-to-allowed',
            action='store_true',
            help='Add extracted hosts to the ZoomAllowedHost table (disabled by default for safety)'
        )
        parser.add_argument(
            '--enable',
            action='store_true',
            help='Enable hosts when adding them (only works with --add-to-allowed)'
        )
        parser.add_argument(
            '--list-only',
            action='store_true',
            help='Only list the host emails without adding them'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Extracting Zoom Host Emails from Webhook Logs ===\n'))
        
        # Get unique host emails from webhook logs
        webhook_emails = ZoomWebhookLog.objects.filter(
            host_email__isnull=False
        ).exclude(
            host_email=''
        ).values_list('host_email', flat=True).distinct().order_by('host_email')
        
        webhook_emails_list = list(webhook_emails)
        
        if not webhook_emails_list:
            self.stdout.write(self.style.WARNING('No host emails found in webhook logs.'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'Found {len(webhook_emails_list)} unique host email(s):\n'))
        
        # Display all found emails
        for idx, email in enumerate(webhook_emails_list, 1):
            # Check if already in allowed hosts
            try:
                allowed_host = ZoomAllowedHost.objects.get(email=email)
                status = '✓ Enabled' if allowed_host.enabled else '✗ Disabled'
                self.stdout.write(f'  {idx}. {email} ({status} - Already in allowed hosts)')
            except ZoomAllowedHost.DoesNotExist:
                self.stdout.write(f'  {idx}. {email} (Not in allowed hosts)')
        
        # If only listing, stop here
        if options['list_only']:
            self.stdout.write(self.style.SUCCESS('\n✓ List complete.'))
            return
        
        # Add to allowed hosts if requested
        if options['add_to_allowed']:
            self.stdout.write(self.style.WARNING('\n--- Adding hosts to ZoomAllowedHost table ---'))
            
            enabled_status = options['enable']
            added_count = 0
            updated_count = 0
            existing_count = 0
            
            for email in webhook_emails_list:
                allowed_host, created = ZoomAllowedHost.objects.get_or_create(
                    email=email,
                    defaults={
                        'enabled': enabled_status,
                        'name': '',  # Can be filled in manually later
                        'notes': f'Auto-extracted from webhook logs'
                    }
                )
                
                if created:
                    added_count += 1
                    status = 'enabled' if enabled_status else 'disabled'
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Added: {email} ({status})'))
                else:
                    if allowed_host.enabled != enabled_status and enabled_status:
                        # Update to enabled if requested
                        allowed_host.enabled = True
                        allowed_host.save()
                        updated_count += 1
                        self.stdout.write(self.style.SUCCESS(f'  ↑ Updated to enabled: {email}'))
                    else:
                        existing_count += 1
                        status = 'enabled' if allowed_host.enabled else 'disabled'
                        self.stdout.write(f'  - Already exists: {email} ({status})')
            
            # Summary
            self.stdout.write(self.style.SUCCESS(f'\n=== Summary ==='))
            self.stdout.write(f'Total unique hosts found: {len(webhook_emails_list)}')
            self.stdout.write(self.style.SUCCESS(f'Added: {added_count}'))
            if updated_count > 0:
                self.stdout.write(self.style.SUCCESS(f'Updated to enabled: {updated_count}'))
            self.stdout.write(f'Already existed: {existing_count}')
            
            if not enabled_status and added_count > 0:
                self.stdout.write(self.style.WARNING(
                    '\n⚠ Note: New hosts were added as DISABLED. '
                    'Enable them in the Django admin or run with --enable flag.'
                ))
        else:
            self.stdout.write(self.style.WARNING(
                '\n⚠ Hosts were NOT added to the allowed list. '
                'Use --add-to-allowed flag to add them (they will be disabled by default).'
            ))
            self.stdout.write(self.style.NOTICE(
                'Example: python manage.py extract_zoom_hosts --add-to-allowed'
            ))
            self.stdout.write(self.style.NOTICE(
                'Or to add and enable: python manage.py extract_zoom_hosts --add-to-allowed --enable'
            ))
        
        self.stdout.write(self.style.SUCCESS('\n✓ Done!'))
