from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import models
from channels.db import database_sync_to_async
import uuid
from django.utils import timezone

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Admin'),
    )
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    user_id = models.CharField(max_length=255, default=uuid.uuid4, blank=True, unique=True)
    phone = models.CharField(max_length=15,null=True, blank=True)
    email = models.EmailField(unique=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)  # Optional avatar field

    middle_name = models.CharField(max_length=255, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    age = models.IntegerField(null=True, blank=True)
    college = models.CharField(max_length=255, null=True, blank=True)
    payment_image = models.ImageField(upload_to='payment_images/', null=True, blank=True)
    transaction_id = models.CharField(max_length=255, default='', blank=True)
    initial_program_selection = models.CharField(max_length=255, null=True, blank=True, default='')
    initial_program_title = models.CharField(max_length=255, null=True, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    token_version = models.IntegerField(default=0)
    
    # Google OAuth integration
    is_google_user = models.BooleanField(default=False)
    google_id = models.CharField(max_length=255, null=True, blank=True, unique=True)

    programs = models.ManyToManyField('api.Program', related_name='users', blank=True)
    # user_selected_programs = models.ManyToManyField('api.Program', related_name='users', blank=True)
    subjects = models.ManyToManyField('api.Subject', related_name='users', blank=True)
    courses = models.ManyToManyField('api.Course', related_name='users', blank=True)
    mcq_results = models.ManyToManyField('api.McqResult', related_name='users', blank=True)
    mocktest_results = models.ManyToManyField('api.MockTestResult', related_name='users', blank=True)
    last_login_token = models.CharField(max_length=255, null=True, blank=True)
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='customuser_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email.split('@')[0]
        super().save(*args, **kwargs)
    
    @database_sync_to_async
    def get_user(self, username):
        return CustomUser.objects.get(username=username)

    def __str__(self):
        return self.username


class DeviceToken(models.Model):
    PLATFORM_CHOICES = (
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web'),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='android')
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.platform}"

    class Meta:
        ordering = ['-updated_at']
