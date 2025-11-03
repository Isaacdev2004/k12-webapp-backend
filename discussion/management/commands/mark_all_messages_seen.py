"""
Management command to mark all messages as seen for all users
This will create/update MessageStatus entries and set seen_at timestamps
Useful for resetting unseen counts to 0 for all users
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from discussion.models import Message, MessageStatus, PersonalMessage
from accounts.models import CustomUser


class Command(BaseCommand):
    help = 'Mark all messages as seen for all users to reset unseen counts to 0'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--discussion-only',
            action='store_true',
            help='Only mark discussion messages as seen',
        )
        parser.add_argument(
            '--personal-only',
            action='store_true',
            help='Only mark personal messages as seen',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        discussion_only = options['discussion_only']
        personal_only = options['personal_only']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Mark discussion messages as seen
        if not personal_only:
            self.stdout.write(self.style.MIGRATE_HEADING('\n=== Processing Discussion Messages ==='))
            self.mark_discussion_messages_seen(dry_run)

        # Mark personal messages as seen
        if not discussion_only:
            self.stdout.write(self.style.MIGRATE_HEADING('\n=== Processing Personal Messages ==='))
            self.mark_personal_messages_seen(dry_run)

        self.stdout.write(self.style.SUCCESS('\n✅ Command completed successfully!'))

    def mark_discussion_messages_seen(self, dry_run=False):
        """Mark all discussion messages (group chat) as seen for all users"""
        
        # Get all discussion messages
        all_messages = Message.objects.select_related('user').all()
        total_messages = all_messages.count()
        
        self.stdout.write(f'Found {total_messages} discussion messages')

        if dry_run:
            # Count how many MessageStatus entries would be created/updated
            entries_to_create = 0
            entries_to_update = 0
            
            for message in all_messages:
                # Get all participants except the sender
                participants = message.get_participants().exclude(id=message.user.id)
                
                for participant in participants:
                    try:
                        status = MessageStatus.objects.get(message=message, user=participant)
                        if not status.seen_at:
                            entries_to_update += 1
                    except MessageStatus.DoesNotExist:
                        entries_to_create += 1
            
            self.stdout.write(self.style.WARNING(
                f'Would create {entries_to_create} new MessageStatus entries'
            ))
            self.stdout.write(self.style.WARNING(
                f'Would update {entries_to_update} existing MessageStatus entries'
            ))
            return

        # Actually perform the updates
        created_count = 0
        updated_count = 0
        now = timezone.now()
        
        with transaction.atomic():
            for idx, message in enumerate(all_messages, 1):
                if idx % 100 == 0:
                    self.stdout.write(f'Processing message {idx}/{total_messages}...')
                
                # Get all participants except the sender
                participants = message.get_participants().exclude(id=message.user.id)
                
                for participant in participants:
                    status, created = MessageStatus.objects.get_or_create(
                        message=message,
                        user=participant,
                        defaults={
                            'delivered_at': now,
                            'seen_at': now
                        }
                    )
                    
                    if created:
                        created_count += 1
                    elif not status.seen_at:
                        # Update existing entry to mark as seen
                        status.seen_at = now
                        if not status.delivered_at:
                            status.delivered_at = now
                        status.save(update_fields=['seen_at', 'delivered_at'])
                        updated_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ Created {created_count} new MessageStatus entries'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'✅ Updated {updated_count} existing MessageStatus entries'
        ))

    def mark_personal_messages_seen(self, dry_run=False):
        """Mark all personal messages as seen"""
        
        # Get all personal messages
        all_messages = PersonalMessage.objects.select_related('sender', 'receiver').all()
        total_messages = all_messages.count()
        
        self.stdout.write(f'Found {total_messages} personal messages')

        if dry_run:
            unseen_count = all_messages.exclude(status='seen').count()
            self.stdout.write(self.style.WARNING(
                f'Would mark {unseen_count} personal messages as seen'
            ))
            return

        # Actually perform the updates
        updated_count = 0
        now = timezone.now()
        
        with transaction.atomic():
            for idx, message in enumerate(all_messages, 1):
                if idx % 100 == 0:
                    self.stdout.write(f'Processing personal message {idx}/{total_messages}...')
                
                if message.status != 'seen':
                    message.status = 'seen'
                    message.seen_at = now
                    if not message.delivered_at:
                        message.delivered_at = now
                    message.save(update_fields=['status', 'seen_at', 'delivered_at'])
                    updated_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ Marked {updated_count} personal messages as seen'
        ))
