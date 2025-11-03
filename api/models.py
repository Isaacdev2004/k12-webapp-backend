from datetime import timedelta, timezone
from django.db import models
from accounts.models import CustomUser
from django.utils.safestring import mark_safe
from storages.backends.s3boto3 import S3Boto3Storage
import random
import string
from datetime import datetime
from django.utils import timezone
from decimal import Decimal

class Course(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    published = models.BooleanField(default=False)
    course_thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True)

    def __str__(self):
        return self.name



class Program(models.Model):
    name = models.CharField(max_length=255)
    thumbnail = models.ImageField(upload_to='program_thumbnails/', blank=True, null=True)
    course = models.ForeignKey(Course, related_name='programs', on_delete=models.CASCADE, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    published = models.BooleanField(default=False)
    payment_picture = models.ManyToManyField(
        'api.PaymentPicture',
        related_name="api_programs_payment",  # Ensure this is unique
        blank=True
    )
    subjects = models.ManyToManyField('api.Subject', related_name='programs', blank=True, null=True)
    has_subjects = models.BooleanField(default=True, verbose_name='Subject(s)')
    has_chapters = models.BooleanField(default=True, verbose_name='Chapter(s)')
    has_topics = models.BooleanField(default=True, verbose_name='Topic(s)')
    has_chapterwise_tests = models.BooleanField(default=True, verbose_name='Chapterwise Test(s)')
    has_chapterwise_notes = models.BooleanField(default=True, verbose_name='Chapterwise Notes(s)')
    has_chapterwise_videos = models.BooleanField(default=True, verbose_name='Chapterwise Video(s)')
    has_mock_tests = models.BooleanField(default=True, verbose_name='Mock tests')
    has_live_classes = models.BooleanField(default=True, verbose_name='Live Classes')
    has_recorded_lectures = models.BooleanField(default=True, verbose_name='Recorded Lectures')
    has_discussions = models.BooleanField(default=True, verbose_name='24/7 Discussions')
    has_lecture_notes = models.BooleanField(default=True, verbose_name='Lecture Notes')
    participant_users = models.ManyToManyField(CustomUser, related_name='program_participants', blank=True)
    end_date = models.DateTimeField(null=True, blank=True, help_text="Program end date. Students will be automatically removed after this date.")
    
    def __str__(self):
        return f"{self.name} - {self.course.name}"

    def is_expired(self):
        """
        Check if the program has ended
        """
        if not self.end_date:
            return False
        return timezone.now() > self.end_date

    def remove_user_access(self, user):
        """
        Remove all program-related access for a user
        """
        # Remove user from program participants
        self.participant_users.remove(user)
        
        # Remove program from user's programs
        user.programs.remove(self)
        
        # Remove associated course
        if self.course:
            user.courses.remove(self.course)
            
        # Remove associated subjects
        if self.subjects.exists():
            user.subjects.remove(*self.subjects.all())

    def remove_all_expired_users(self):
        """
        Remove all users from an expired program without deleting the program itself
        """
        if not self.is_expired():
            return 0
            
        # Get all enrolled users (both regular and participant users)
        enrolled_users = list(self.users.all())
        participant_users = list(self.participant_users.all())
        
        # Combine and deduplicate users
        all_users = list(set(enrolled_users + participant_users))
        
        # Remove access for all users
        for user in all_users:
            self.remove_user_access(user)
        
        # Return total count of users removed
        return len(all_users)

    @classmethod
    def cleanup_expired_programs(cls):
        """
        Class method to remove all users from expired programs
        Note: This only removes user enrollments, programs themselves are preserved
        """
        expired_programs = cls.objects.filter(
            end_date__isnull=False,
            end_date__lt=timezone.now()
        )
        
        total_removed = 0
        programs_cleaned = []
        
        for program in expired_programs:
            removed_count = program.remove_all_expired_users()
            if removed_count > 0:
                total_removed += removed_count
                programs_cleaned.append({
                    'program_name': program.name,
                    'program_id': program.id,
                    'removed_users': removed_count,
                    'end_date': program.end_date
                })
        
        return {
            'total_programs_cleaned': len(programs_cleaned),
            'total_users_removed': total_removed,
            'programs': programs_cleaned,
            'note': 'Programs are preserved, only user enrollments were removed'
        }



    
class SubjectFee(models.Model):
    program = models.ForeignKey(Program, related_name='subject_fees', on_delete=models.CASCADE)
    number_of_subjects = models.PositiveIntegerField()
    fee = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.number_of_subjects} Subject(s): NPR {self.fee} - {self.program.name} - {self.program.course.name}"



class Subject(models.Model):
    course = models.ForeignKey(Course, related_name='subjects', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    # description = models.TextField(blank=True)
    subject_thumbnail = models.ImageField(upload_to='subject_thumbnails/', blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.course.name}"



class Chapter(models.Model):
    subject = models.ForeignKey(Subject, related_name='subject_chapters', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.subject.name} - {self.subject.course.name}"


class QrPayment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('wallet', 'Wallet'),
        ('account', 'Account'),
    ]
    name = models.CharField(max_length=255, blank=True, null=True)
    qr_image = models.ImageField(upload_to='QrPayment/', max_length=255, blank=True, null=True)
    accountno = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=False)
    payment_method = models.CharField(
        max_length=10, 
        choices=PAYMENT_METHOD_CHOICES, 
        default='account',
    )
    account_name = models.CharField(max_length=255, blank=True, null=True)
    account_branch = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name or f"QrPayment ({self.payment_method.capitalize()})" or f"QrPayment ID: {self.id}"



class PaymentPicture(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    payment_image = models.ImageField(upload_to='payment_pictures/',blank=True, null=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='PaymentPicture', blank=True, null=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='PaymentPicture', blank=True, null=True)
    subject = models.ManyToManyField(Subject,related_name='PaymentPicture',  blank=True)
    date = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="payment_payment_pictures",  # Ensure this is unique
    )    
    is_verified = models.BooleanField(default=False)
    total_amount = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending')
    rejected_reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user} - {self.program} - {self.status}"
    def save(self, *args, **kwargs):
        # Handle program payment association when status changes to 'approved'
        if self.status == 'approved' and self.program:
            self.program.payment_picture.add(self)  # Add this payment picture to the program's many-to-many field
            self.user.programs.add(self.program)  # CustomUser को programs मा program_name जोड्नुहोस्
            self.user.courses.add(self.course)  # CustomUser को programs मा program_name जोड्नुहोस्
            self.user.subjects.add(*self.subject.all())  # CustomUser को subjects मा subject जोड्नुहोस्

        # Handle removal of payment from program when status is 'rejected'
        elif self.status == 'rejected' and self.program:
            self.program.payment_picture.remove(self)  # Remove this payment picture from the program's many-to-many field
            self.user.courses.remove(self.course)  # CustomUser बाट program_name हटाउनुहोस्
            self.user.subjects.remove(*self.subject.all())  # CustomUser बाट subjects हटाउनुहोस्

        # Clear rejected_reason if the status is not 'rejected'
        if self.status != 'rejected':
            self.rejected_reason = None

        super().save(*args, **kwargs)


class Topic(models.Model):
    chapter = models.ForeignKey(Chapter, related_name='topics', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.chapter.name} - {self.chapter.subject.name} - {self.chapter.subject.course.name}"



class MCQ(models.Model):
    STATUS_CHOICES = [
        ('mock', 'mcq Test'),
        ('practice', 'Practice Test'),
    ]
    topic = models.ForeignKey(Topic, related_name='mcqs', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)
    is_free = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='mock')
    scheduled_start_time = models.DateTimeField(null=True, blank=True)  # New field for scheduling
    duration = models.DurationField(default=timedelta(minutes=60))  # New field for duration with a default of 60 minutes
    negMark = models.IntegerField(default=0)  # Negative marking field as an integer
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.topic.name} - {self.topic.chapter.name} - {self.topic.chapter.subject.name} - {self.topic.chapter.subject.course.name}"

class MCQQuestion(models.Model):
    mcq = models.ForeignKey(MCQ, related_name='questions', on_delete=models.CASCADE)
    question_text = models.TextField()
    question_image_url = models.URLField(blank=True, null=True)
    option_0_text = models.TextField(blank=True, null=True)
    option_1_text = models.TextField(blank=True, null=True)
    option_2_text = models.TextField(blank=True, null=True)
    option_3_text = models.TextField(blank=True, null=True)
    option_0_image_url = models.URLField(blank=True, null=True)
    option_1_image_url = models.URLField(blank=True, null=True)
    option_2_image_url = models.URLField(blank=True, null=True)
    option_3_image_url = models.URLField(blank=True, null=True)
    answer = models.IntegerField()
    weight = models.FloatField()
    explanation = models.TextField(blank=True, null=True)
    explanation_image_url = models.URLField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.mcq.title} - {self.mcq.topic.name} - {self.mcq.topic.chapter.name} - {self.mcq.topic.chapter.subject.name} - {self.mcq.topic.chapter.subject.course.name}"
    

class SubjectRecordingVideo(models.Model):
    subject = models.ForeignKey(Subject, related_name='subject_recording_videos', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    video_url = models.URLField(max_length=255, blank=True, null=True)
    is_free = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    video_file = models.FileField(upload_to='videos/',blank=True, null=True)
    video_description = models.TextField(blank=True, null=True)
    thumbnail = models.ImageField(upload_to='video_thumbnails/', blank=True, null=True)
    video_duration = models.FloatField(default=0.0, blank=True, null=True)
    is_auto_created = models.BooleanField(default=False, help_text="True if this video was automatically created from Zoom recording")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.subject.name} - {self.subject.course.name}"

class Video(models.Model):
    topic = models.ForeignKey(Topic, related_name='videos', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    video_url = models.URLField(max_length=255, blank=True, null=True)
    is_free = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    video_file = models.FileField(upload_to='videos/', blank=True, null=True)
    video_description = models.TextField(blank=True, null=True)
    thumbnail = models.ImageField(upload_to='thumbnails/', blank=True, null=True)
    video_duration = models.FloatField(default=0.0, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.topic.name} - {self.topic.chapter.name} - {self.topic.chapter.subject.name} - {self.topic.chapter.subject.course.name}"
    
class Content(models.Model):
    topic = models.ForeignKey(Topic, related_name='contents', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    thumbnail = models.ImageField(upload_to='content_thumbnails/', blank=True, null=True)
    pdf = models.FileField(upload_to='content_pdfs/', blank=True, null=True)
    is_active = models.BooleanField(default=False)
    is_free = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} - {self.topic.name} - {self.topic.chapter.name} - {self.topic.chapter.subject.name} - {self.topic.chapter.subject.course.name}"


class LiveClass(models.Model):
    RECURRENCE_CHOICES = [
        ('none', 'No Recurrence'),
        ('weekly', 'Weekly'),
    ]
    
    DAYS_OF_WEEK_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    subject = models.ForeignKey(Subject, related_name='live_classes', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    live_url = models.URLField(blank=True, null=True)  
    host = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='live_classes')
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    zoom_meeting_id = models.CharField(max_length=255, null=True, blank=True)
    zoom_password = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_free = models.BooleanField(default=False)  
    is_active = models.BooleanField(default=False)
    
    # Recurrence fields
    recurrence_type = models.CharField(max_length=10, choices=RECURRENCE_CHOICES, default='none')
    recurrence_start_date = models.DateField(blank=True, null=True)
    recurrence_end_date = models.DateField(blank=True, null=True)
    days_of_week = models.JSONField(default=list, blank=True, help_text='List of days (0=Monday, 6=Sunday)')
    day_of_week = models.IntegerField(blank=True, null=True, help_text='0=Monday, 6=Sunday (deprecated, use days_of_week)')

    def __str__(self):
        return f"{self.title} - {self.subject.name} - {self.subject.course.name}"

    @property
    def duration(self):
        """Returns the duration of the class in minutes"""
        if self.start_time and self.end_time:
            from datetime import datetime, timedelta
            # Convert time objects to datetime for calculation
            today = datetime.now().date()
            start_dt = datetime.combine(today, self.start_time)
            end_dt = datetime.combine(today, self.end_time)
            # Handle case where end time is on next day
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
            return int((end_dt - start_dt).total_seconds() / 60)
        return None

    @property
    def days_of_week_display(self):
        """Returns a comma-separated string of selected days"""
        if not self.days_of_week:
            return "No days selected"
        
        day_names = dict(self.DAYS_OF_WEEK_CHOICES)
        selected_days = [day_names.get(day, f"Day {day}") for day in self.days_of_week]
        return ", ".join(selected_days)

    def clean(self):
        """Validate the model data"""
        from django.core.exceptions import ValidationError
        
        if self.recurrence_type == 'weekly' and not self.days_of_week:
            raise ValidationError("Days of week must be selected when recurrence type is weekly.")
        
        if self.days_of_week:
            # Validate that all days are within valid range (0-6)
            invalid_days = [day for day in self.days_of_week if not isinstance(day, int) or day < 0 or day > 6]
            if invalid_days:
                raise ValidationError(f"Invalid days of week: {invalid_days}. Days must be integers from 0 (Monday) to 6 (Sunday).")

    def save(self, *args, **kwargs):
        # Call clean method to validate
        self.clean()
        
        # Backward compatibility: if day_of_week is set but days_of_week is empty, migrate it
        if self.day_of_week is not None and not self.days_of_week:
            self.days_of_week = [self.day_of_week]
        
        # If recurrence_type is weekly and days_of_week is set, clear the old day_of_week
        if self.recurrence_type == 'weekly' and self.days_of_week:
            if len(self.days_of_week) == 1:
                self.day_of_week = self.days_of_week[0]
            else:
                self.day_of_week = None  # Multiple days, so clear single day
        
        super().save(*args, **kwargs)

    class Meta:
        # Ensure this is not set to False
        managed = True  # Default (can omit entirely)

        

class MockTest(models.Model):
    STATUS_CHOICES = [
        ('mock', 'Mock Test'),
        ('practice', 'Practice Test'),
    ]
    course = models.ForeignKey(Course, related_name='mock_tests', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=False)
    is_free = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,default='mock')
    scheduled_start_time = models.DateField(null=True, blank=True)  # New field for scheduling
    duration = models.DurationField(default=timedelta(minutes=60))  # New field for duration with a default of 60 minutes
    negMark = models.IntegerField(default=0)  # Negative marking field as an integer
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)


    def __str__(self):
        return f"{self.title} - {self.course.name}"

class MockTestQuestion(models.Model):
    mock_test = models.ForeignKey(MockTest, related_name='questions', on_delete=models.CASCADE)
    question_text = models.TextField()
    question_image_url = models.URLField(blank=True, null=True)
    option_0_text = models.TextField(blank=True, null=True)
    option_1_text = models.TextField(blank=True, null=True)
    option_2_text = models.TextField(blank=True, null=True)
    option_3_text = models.TextField(blank=True, null=True)
    option_0_image_url = models.URLField(blank=True, null=True)
    option_1_image_url = models.URLField(blank=True, null=True)
    option_2_image_url = models.URLField(blank=True, null=True)
    option_3_image_url = models.URLField(blank=True, null=True)
    answer = models.IntegerField()
    weight = models.FloatField()
    explanation = models.TextField(blank=True, null=True)
    explanation_image_url = models.URLField(blank=True, null=True) 

    def __str__(self):
        return f"{self.mock_test.title} - {self.mock_test.course.name} "

class SubjectNote(models.Model):
    subject = models.ForeignKey(Subject, related_name='subject_notes', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)
    is_free = models.BooleanField(default=False)
    pdf = models.FileField(upload_to='subject_pdfs/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.subject.name} - {self.subject.course.name}"
    
class Note(models.Model):
    course = models.ForeignKey(Course, related_name='notes', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)
    is_free = models.BooleanField(default=False)
    pdf = models.FileField(upload_to='notes/pdfs/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.course.name}"


class McqResult(models.Model):
    user = models.ForeignKey(CustomUser, related_name='mcq_results_api', on_delete=models.CASCADE)
    mcq = models.ForeignKey(MCQ, related_name='results', on_delete=models.CASCADE)
    score = models.FloatField()
    total_score = models.FloatField()
    correct_answers = models.IntegerField(default=0)
    wrong_answers = models.IntegerField(default=0)
    unattempted = models.IntegerField(default=0)
    time_taken = models.DurationField(null=True, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)
    submissions_data = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.user} - {self.mcq.title} - {self.score}/{self.total_score}"


class MockTestResult(models.Model):
    STATUS_CHOICES = [
        ('mock', 'Mock Test'),
        ('practice', 'Practice Test'),
    ]
    user = models.ForeignKey(CustomUser, related_name='mocktest_results_api', on_delete=models.CASCADE)
    mock_test = models.ForeignKey(MockTest, related_name='results', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,default='mock')

    score = models.FloatField()
    total_score = models.FloatField()
    correct_answers = models.IntegerField(default=0)
    wrong_answers = models.IntegerField(default=0)
    unattempted = models.IntegerField(default=0)
    time_taken = models.DurationField(null=True, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)
    submissions_data = models.JSONField(default=dict) 
    
    def __str__(self):
        return f"{self.user} - {self.mock_test.title} - {self.score}/{self.total_score} - {self.mock_test.course.name}"

    def save(self, *args, **kwargs):
        # Save the MockTestResult first
        super().save(*args, **kwargs)
        
        # Add this result to the user's mocktest_results
        self.user.mocktest_results.add(self)

    class Meta:
        ordering = ['-completed_at']
        verbose_name = 'Mock Test Result'
        verbose_name_plural = 'Mock Test Results'

class OnePGPayment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='onepg_payments')
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='onepg_payments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='onepg_payments')
    subjects = models.ManyToManyField(Subject, related_name='onepg_payments', blank=True)
    merchant_txn_id = models.CharField(max_length=100, unique=True)
    gateway_txn_id = models.CharField(max_length=100, null=True, blank=True)
    process_id = models.CharField(max_length=100, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    service_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    instrument_code = models.CharField(max_length=50, null=True, blank=True)
    transaction_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.merchant_txn_id} - {self.user.email} - {self.amount}"

    class Meta:
        ordering = ['-transaction_date']
        verbose_name = 'OnePG Payment'
        verbose_name_plural = 'OnePG Payments'

    def save(self, *args, **kwargs):
        if not self.merchant_txn_id:
            # Generate unique merchant transaction ID
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.merchant_txn_id = f"TXN{timestamp}{random_suffix}"
        
        # Calculate total amount including service charge
        if not self.total_amount:
            self.total_amount = Decimal(self.amount) + Decimal(self.service_charge)

        # Set course from program if not set
        if not self.course_id and self.program:
            self.course = self.program.course

        # Handle program enrollment on successful payment
        if self.status == 'success':
            # Add user to program
            self.user.programs.add(self.program)
            
            # Add user to course
            self.user.courses.add(self.course)

            # Add user to program participants
            self.program.participant_users.add(self.user)
            
            # Add user to subjects
            if self.subjects.exists():
                self.user.subjects.add(*self.subjects.all())
            elif self.program.subjects.exists():
                self.user.subjects.add(*self.program.subjects.all())

        super().save(*args, **kwargs)


class QrPaymentTransaction(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='qr_payment_transactions')
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='qr_payment_transactions', null=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='qr_payment_transactions', null=True, blank=True)
    subjects = models.ManyToManyField(Subject, related_name='qr_payment_transactions', blank=True)
    bill_number = models.CharField(max_length=25, unique=True)
    transaction_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    transaction_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"QR Txn: {self.bill_number} - {self.user.email} - {self.status}"

    def save(self, *args, **kwargs):
        # Enroll user in program/course/subjects upon successful payment
        if self.status == 'success':
            if self.program:
                self.user.programs.add(self.program)
            if self.course:
                self.user.courses.add(self.course)
            if self.program:
                self.program.participant_users.add(self.user)
            if self.subjects.exists():
                self.user.subjects.add(*self.subjects.all())
            elif self.program and self.program.subjects.exists():
                self.user.subjects.add(*self.program.subjects.all())
        super().save(*args, **kwargs)


class ZoomAllowedHost(models.Model):
    """Model to track which Zoom host emails are allowed to have their recordings saved"""
    email = models.EmailField(unique=True, help_text="Zoom host email address")
    name = models.CharField(max_length=255, blank=True, null=True, help_text="Host name for reference")
    enabled = models.BooleanField(default=True, help_text="Enable/disable recording processing for this host")
    notes = models.TextField(blank=True, null=True, help_text="Optional notes about this host")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['email']
        verbose_name = 'Zoom Allowed Host'
        verbose_name_plural = 'Zoom Allowed Hosts'

    def __str__(self):
        status = "✓" if self.enabled else "✗"
        return f"{status} {self.email}" + (f" ({self.name})" if self.name else "")


class ZoomWebhookLog(models.Model):
    """Log all incoming Zoom webhook events"""
    event_type = models.CharField(max_length=100)
    meeting_id = models.CharField(max_length=255)
    host_email = models.EmailField(max_length=255, blank=True, null=True, help_text="Email of the Zoom meeting host")
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} - Meeting {self.meeting_id} - {self.created_at}"


class ZoomRecording(models.Model):
    """Model to track Zoom recording downloads and uploads"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    # Zoom recording information
    zoom_meeting_id = models.CharField(max_length=255)
    zoom_recording_id = models.CharField(max_length=255, unique=True)
    zoom_meeting_uuid = models.CharField(max_length=255)
    host_email = models.EmailField(max_length=255, blank=True, null=True, help_text="Email of the Zoom meeting host")
    recording_start_time = models.DateTimeField()
    recording_end_time = models.DateTimeField()
    duration = models.IntegerField(help_text="Duration in seconds")
    file_size = models.BigIntegerField(help_text="File size in bytes")
    file_type = models.CharField(max_length=10, default='mp4')
    zoom_download_url = models.URLField(max_length=500)
    download_token = models.TextField(blank=True, null=True)  # JWT tokens can be very long

    # Storage information
    r2_storage_key = models.CharField(max_length=500, blank=True, null=True)
    r2_storage_url = models.URLField(max_length=500, blank=True, null=True)

    # Processing status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processing_started_at = models.DateTimeField(blank=True, null=True)
    processing_completed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    # Relationships
    live_class = models.ForeignKey(LiveClass, on_delete=models.CASCADE, blank=True, null=True)
    subject_recording_video = models.OneToOneField(
        SubjectRecordingVideo,
        on_delete=models.SET_NULL,
        related_name='zoom_recording',
        blank=True,
        null=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['zoom_meeting_id']),
            models.Index(fields=['zoom_recording_id']),
            models.Index(fields=['status']),
            models.Index(fields=['host_email']),
        ]

    def __str__(self):
        return f"Recording {self.zoom_recording_id} - {self.status}"

    @property
    def duration_formatted(self):
        """Return duration in HH:MM:SS format"""
        hours = self.duration // 3600
        minutes = (self.duration % 3600) // 60
        seconds = self.duration % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class NCHLPayment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='nchl_payments')
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='nchl_payments', null=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='nchl_payments', null=True, blank=True)
    subjects = models.ManyToManyField(Subject, related_name='nchl_payments', blank=True)
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Per user request, transaction_id from NCHL. Let's make it nullable as we may not have it initially.
    transaction_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    
    response_payload = models.JSONField(null=True, blank=True)
    
    # My own transaction ID to initiate payment
    merchant_txn_id = models.CharField(max_length=100, unique=True)
    # NCHL's reference ID
    gateway_txn_id = models.CharField(max_length=100, null=True, blank=True) 

    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"NCHL Txn: {self.merchant_txn_id} - {self.user.email} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.merchant_txn_id:
            # Generate unique merchant transaction ID
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.merchant_txn_id = f"NCHL-TXN-{timestamp}{random_suffix}"
            
        # Set course from program if not set
        if not self.course_id and self.program:
            self.course = self.program.course

        # Enroll user in program/course/subjects upon successful payment
        if self.status == 'success':
            if self.program:
                self.user.programs.add(self.program)
                self.program.participant_users.add(self.user)
            if self.course:
                self.user.courses.add(self.course)
            if self.subjects.exists():
                self.user.subjects.add(*self.subjects.all())
            elif self.program and self.program.subjects.exists():
                self.user.subjects.add(*self.program.subjects.all())
                
        super().save(*args, **kwargs)
        
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'NCHL Payment'
        verbose_name_plural = 'NCHL Payments'


class BillingHistory(models.Model):
    PAYMENT_KIND_CHOICES = [
        ('onepg', 'OnePG'),
        ('nchl', 'NCHL'),
        ('qr', 'QR'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='billing_history')
    program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_kind = models.CharField(max_length=10, choices=PAYMENT_KIND_CHOICES)
    payment_id = models.IntegerField(help_text='Primary key of the payment record')
    transaction_id = models.CharField(max_length=255, blank=True, null=True)
    merchant_txn_id = models.CharField(max_length=255, blank=True, null=True)
    invoice_pdf = models.FileField(upload_to='invoices/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice {self.id} - {self.user.email} - {self.amount}"

    class Meta:
        ordering = ['-created_at']
