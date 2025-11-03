from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

class VersionedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        
        # Check token version
        token_version = validated_token.get('version', None)
        if token_version is None or token_version != user.token_version:
            raise AuthenticationFailed('Token version is invalid or expired. Please log in again.')
        
        return user
