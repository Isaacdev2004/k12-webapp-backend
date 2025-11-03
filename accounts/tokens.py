# accounts/tokens.py
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from six import text_type

class CustomPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return text_type(user.pk) + text_type(timestamp) + text_type(user.is_active)

password_reset_token = CustomPasswordResetTokenGenerator()
