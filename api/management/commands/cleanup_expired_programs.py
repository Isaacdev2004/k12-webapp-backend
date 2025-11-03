from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Program
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Remove students enrolled in expired programs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually removing users',
        )
        parser.add_argument(
            '--program-id',
            type=int,
            help='Cleanup specific program by ID (optional)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting cleanup of expired programs...')
        )

        dry_run = options['dry_run']
        program_id = options.get('program_id')

        if program_id:
            # Cleanup specific program
            try:
                program = Program.objects.get(id=program_id)
                if program.is_expired():
                    if dry_run:
                        enrolled_count = program.users.count()
                        participants_count = program.participant_users.count()
                        self.stdout.write(
                            f"[DRY RUN] Would remove {enrolled_count + participants_count} users from program: {program.name}"
                        )
                    else:
                        removed_count = program.remove_all_expired_users()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Removed {removed_count} users from expired program: {program.name}"
                            )
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"Program '{program.name}' has not expired yet")
                    )
            except Program.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Program with ID {program_id} does not exist")
                )
        else:
            # Cleanup all expired programs
            if dry_run:
                expired_programs = Program.objects.filter(
                    end_date__isnull=False,
                    end_date__lt=timezone.now()
                )
                total_users_to_remove = 0
                for program in expired_programs:
                    enrolled_count = program.users.count()
                    participants_count = program.participant_users.count()
                    program_total = enrolled_count + participants_count
                    total_users_to_remove += program_total
                    
                    self.stdout.write(
                        f"[DRY RUN] Program: {program.name} - Would remove {program_total} users"
                    )
                
                self.stdout.write(
                    self.style.WARNING(
                        f"[DRY RUN] Total: {expired_programs.count()} programs, "
                        f"{total_users_to_remove} users would be removed"
                    )
                )
            else:
                result = Program.cleanup_expired_programs()
                
                if result['total_programs_cleaned'] == 0:
                    self.stdout.write(
                        self.style.SUCCESS('No expired programs found or no users to remove.')
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Cleanup completed successfully!\n"
                            f"Programs cleaned: {result['total_programs_cleaned']}\n"
                            f"Total users removed: {result['total_users_removed']}"
                        )
                    )
                    
                    # Log details of each program
                    for program_info in result['programs']:
                        self.stdout.write(
                            f"  - {program_info['program_name']}: {program_info['removed_users']} users removed"
                        )

        self.stdout.write(
            self.style.SUCCESS('Cleanup process finished.')
        )
