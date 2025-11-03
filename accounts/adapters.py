from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.db import IntegrityError
import uuid

User = get_user_model()


class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Custom account adapter to handle account creation
    """
    
    def save_user(self, request, user, form, commit=True):
        """
        Save user with custom fields
        """
        user = super().save_user(request, user, form, commit=False)
        
        # Set default values for required fields
        if not user.user_type:
            user.user_type = 'student'  # Default to student
        
        if not user.user_id:
            user.user_id = str(uuid.uuid4())
            
        if commit:
            user.save()
        return user


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom social account adapter to handle Google OAuth integration
    """
    
    def pre_social_login(self, request, sociallogin):
        """
        Handle logic before social login
        """
        # Get user email from social account
        user_email = sociallogin.user.email
        
        # Check if user with this email already exists
        if user_email:
            try:
                existing_user = User.objects.get(email=user_email)
                # If user exists but is not a Google user, link the accounts
                if not existing_user.is_google_user:
                    # Update existing user to mark as Google user
                    existing_user.is_google_user = True
                    existing_user.google_id = sociallogin.account.uid
                    existing_user.save()
                # Connect the social account to existing user
                sociallogin.connect(request, existing_user)
            except User.DoesNotExist:
                # User doesn't exist, will be created by allauth
                pass
    
    def save_user(self, request, sociallogin, form=None):
        """
        Save user from social login
        """
        user = sociallogin.user
        
        # Set required fields for your custom user model
        if not user.user_type:
            user.user_type = 'student'  # Default user type
            
        if not user.user_id:
            user.user_id = str(uuid.uuid4())
        
        # Mark as Google user
        user.is_google_user = True
        user.google_id = sociallogin.account.uid
        
        # Set username from email if not provided
        if not user.username:
            user.username = user.email.split('@')[0]
            
        # Ensure unique username
        base_username = user.username
        counter = 1
        while User.objects.filter(username=user.username).exists():
            user.username = f"{base_username}_{counter}"
            counter += 1
        
        # Set password as unusable for Google users
        user.set_unusable_password()
        
        user.save()
        return user
    
    def populate_user(self, request, sociallogin, data):
        """
        Populate user data from social account
        """
        user = super().populate_user(request, sociallogin, data)
        
        # Get additional data from Google
        extra_data = sociallogin.account.extra_data
        
        # Set first and last name from Google profile
        if 'given_name' in extra_data:
            user.first_name = extra_data.get('given_name', '')
        if 'family_name' in extra_data:
            user.last_name = extra_data.get('family_name', '')
            
        # Set profile image from Google (optional)
        if 'picture' in extra_data:
            # You can save the profile image URL or download it
            # For now, we'll just store the URL in a custom field if you want
            pass
            
        return user
