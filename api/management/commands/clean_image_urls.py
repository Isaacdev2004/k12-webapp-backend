"""
Django management command to clean existing image URLs in the database.
This removes temporary query parameters (like X-Amz-Algorithm) from stored URLs.

Usage:
    python manage.py clean_image_urls
"""

from django.core.management.base import BaseCommand
from api.models import MockTestQuestion, MCQQuestion


class Command(BaseCommand):
    help = 'Clean image URLs by removing query parameters from MockTestQuestion and MCQQuestion'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually changing it',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        # Clean MockTestQuestion URLs
        self.stdout.write(self.style.SUCCESS('\nCleaning MockTestQuestion URLs...'))
        mock_changed = self.clean_model_urls(MockTestQuestion, dry_run)
        
        # Clean MCQQuestion URLs
        self.stdout.write(self.style.SUCCESS('\nCleaning MCQQuestion URLs...'))
        mcq_changed = self.clean_model_urls(MCQQuestion, dry_run)
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f'\n{"=" * 60}'))
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(self.style.SUCCESS(f'{"=" * 60}'))
        self.stdout.write(f'MockTestQuestion: {mock_changed} records {"would be " if dry_run else ""}updated')
        self.stdout.write(f'MCQQuestion: {mcq_changed} records {"would be " if dry_run else ""}updated')
        self.stdout.write(self.style.SUCCESS(f'Total: {mock_changed + mcq_changed} records {"would be " if dry_run else ""}updated'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nRun without --dry-run to apply changes'))

    def clean_model_urls(self, model, dry_run=False):
        """Clean URLs for a given model"""
        url_fields = [
            'question_image_url',
            'option_0_image_url',
            'option_1_image_url',
            'option_2_image_url',
            'option_3_image_url',
            'explanation_image_url'
        ]
        
        changed_count = 0
        
        for question in model.objects.all():
            changed = False
            changes = []
            
            for field in url_fields:
                url = getattr(question, field)
                if url and '?' in url:
                    clean_url = url.split('?')[0]
                    changes.append(f'  {field}: {url[:80]}... -> {clean_url[:80]}...')
                    setattr(question, field, clean_url)
                    changed = True
            
            if changed:
                changed_count += 1
                self.stdout.write(self.style.WARNING(f'\n{model.__name__} ID {question.id}:'))
                for change in changes:
                    self.stdout.write(change)
                
                if not dry_run:
                    question.save()
                    self.stdout.write(self.style.SUCCESS('  ✓ Saved'))
        
        return changed_count
