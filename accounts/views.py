from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import CustomUser
from .serializers import UserSerializer
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework import status
from .serializers import PasswordResetSerializer, PasswordResetConfirmSerializer
from .tokens import password_reset_token
from django.db import models
from django.db.models import Q, Count, Max, OuterRef, Subquery, Case, When, Value, IntegerField
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import transaction
from rest_framework.decorators import action
from discussion.models import PersonalMessage
import logging


class CurrentUserView(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_queryset(self):
        # Return a queryset containing only the current user
        return CustomUser.objects.filter(id=self.request.user.id)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    # Disable methods that shouldn't be allowed
    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Method not allowed."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def list(self, request, *args, **kwargs):
        return Response(
            {"detail": "Method not allowed."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Method not allowed."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

# accounts/views.py
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import PasswordResetSerializer, PasswordResetConfirmSerializer
from .tokens import password_reset_token

class PasswordResetView(APIView):
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                token = password_reset_token.make_token(user)
                reset_url = request.build_absolute_uri(
                    reverse('password_reset_confirm', args=[token])
                )
                send_mail(
                    'Password Reset Request',
                    f'Click the link to reset your password: {reset_url}',
                    'from@example.com',
                    [email],
                )
                return Response({"message": "Password reset link sent to email."}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmView(APIView):
    def post(self, request, token):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            new_password = serializer.validated_data['new_password']
            try:
                user = User.objects.get(email=request.data.get('email'))
                if password_reset_token.check_token(user, token):
                    user.set_password(new_password)
                    user.save()
                    return Response({"message": "Password reset successful."}, status=status.HTTP_200_OK)
                else:
                    return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_users_list(request):
    """
    Get list of users based on user type and search query
    """
    user_type = request.GET.get('user_type', None)
    search = request.GET.get('search', '')
    
    # Start with all active users
    users = CustomUser.objects.filter(is_active=True)
    
    # Filter by user type if provided
    if user_type:
        # Handle comma-separated user types
        user_types = user_type.split(',')
        users = users.filter(user_type__in=user_types)
    
    # Search in username, first_name, last_name, email if search query provided
    if search:
        users = users.filter(
            models.Q(username__icontains=search) |
            models.Q(first_name__icontains=search) |
            models.Q(last_name__icontains=search) |
            models.Q(email__icontains=search)
        )
    
    # Exclude sensitive information
    user_list = users.values(
        'id', 
        'username',
        'first_name',
        'last_name',
        'email',
        'user_type',
        'profile_image',
        'avatar',
        'is_active'
    ).order_by('first_name', 'last_name')  # Sort by name
    
    return Response(list(user_list), status=status.HTTP_200_OK)  # Return direct list instead of nested object

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_enhanced_users_list(request):
    """
    Get enhanced list of users with unseen message counts and last message info, sorted by priority
    """
    user_type = request.GET.get('user_type', None)
    search = request.GET.get('search', '')
    current_user = request.user
    
    # Start with all active users
    users = CustomUser.objects.filter(is_active=True).exclude(id=current_user.id)
    
    # Filter by user type if provided
    if user_type:
        # Handle comma-separated user types
        user_types = user_type.split(',')
        users = users.filter(user_type__in=user_types)
    
    # Search in username, first_name, last_name, email if search query provided
    if search:
        users = users.filter(
            models.Q(username__icontains=search) |
            models.Q(first_name__icontains=search) |
            models.Q(last_name__icontains=search) |
            models.Q(email__icontains=search)
        )
    
    # Subquery to get last message timestamp for each user
    last_message_subquery = PersonalMessage.objects.filter(
        Q(sender=OuterRef('pk'), receiver=current_user) |
        Q(sender=current_user, receiver=OuterRef('pk'))
    ).order_by('-timestamp').values('timestamp')[:1]
    
    # Subquery to get last message content
    last_message_content_subquery = PersonalMessage.objects.filter(
        Q(sender=OuterRef('pk'), receiver=current_user) |
        Q(sender=current_user, receiver=OuterRef('pk'))
    ).order_by('-timestamp').values('content')[:1]
    
    # Subquery to get last message sender
    last_message_sender_subquery = PersonalMessage.objects.filter(
        Q(sender=OuterRef('pk'), receiver=current_user) |
        Q(sender=current_user, receiver=OuterRef('pk'))
    ).order_by('-timestamp').values('sender__username')[:1]
    
    # Annotate users with unseen count and last message info
    enhanced_users = users.annotate(
        unseen_count=Count(
            'sent_personal_messages',
            filter=Q(
                sent_personal_messages__receiver=current_user,
                sent_personal_messages__status__in=['sent', 'delivered']
            )
        ),
        last_message_time=Subquery(last_message_subquery),
        last_message_content=Subquery(last_message_content_subquery),
        last_message_sender=Subquery(last_message_sender_subquery),
        # Add a field to handle NULL last_message_time properly
        has_messages=Case(
            When(last_message_time__isnull=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField()
        )
    ).order_by(
        # First sort by unseen messages (descending - more unseen first)
        '-unseen_count',
        # Then sort by whether user has any messages (users with messages first)
        '-has_messages',
        # Then by last message time (descending - more recent first)
        '-last_message_time',
        # Finally by name for users with no messages
        'first_name', 'last_name'
    )
    
    # Convert to list with proper formatting
    user_list = []
    for user in enhanced_users:
        # Safely handle profile_image
        profile_image_url = None
        if user.profile_image:
            try:
                profile_image_url = user.profile_image.url
            except ValueError:
                profile_image_url = None
        
        # Safely handle avatar field if it exists
        avatar_url = None
        if hasattr(user, 'avatar') and user.avatar:
            try:
                avatar_url = user.avatar.url
            except (ValueError, AttributeError):
                avatar_url = None
        
        user_data = {
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'user_type': user.user_type,
            'profile_image': profile_image_url,
            'avatar': avatar_url,
            'is_active': user.is_active,
            'unseen_count': user.unseen_count or 0,
            'last_message_time': user.last_message_time,
            'last_message_content': user.last_message_content,
            'last_message_sender': user.last_message_sender
        }
        
        # Truncate last message content if too long
        if user_data['last_message_content'] and len(user_data['last_message_content']) > 50:
            user_data['last_message_content'] = user_data['last_message_content'][:47] + '...'
            
        user_list.append(user_data)
    
    return Response(user_list, status=status.HTTP_200_OK)

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Increment token version
        with transaction.atomic():
            user.token_version += 1
            user.save()
        
        # Add token version to claims
        token['version'] = user.token_version
        
        return token

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        # If login was successful, check if we should trigger cleanup
        if response.status_code == 200:
            try:
                # Initialize logger at the beginning
                logger = logging.getLogger(__name__)
                
                # Get user info first
                username = request.data.get('username', '')
                user = None
                
                try:
                    user = CustomUser.objects.get(username=username)
                except CustomUser.DoesNotExist:
                    pass
                
                # Check if cleanup should run for this user/login
                if self.should_run_cleanup_on_login(user):
                    # Import here to avoid circular imports
                    from api.models import Program
                    from django.utils import timezone
                    
                    # Log the cleanup attempt
                    logger.debug(f"Auto-cleanup triggered by login: {username} at {timezone.now()}")
                    
                    # Trigger automatic cleanup of expired programs
                    result = Program.cleanup_expired_programs()
                    
                    # Log the cleanup result
                    if result['total_programs_cleaned'] > 0:
                        logger.info(
                            f"Auto-cleanup on login: Removed {result['total_users_removed']} users "
                            f"from {result['total_programs_cleaned']} expired programs. "
                            f"Triggered by: {username} ({user.user_type if user else 'unknown'})"
                        )
                        
                        # Add cleanup info to response for admin users
                        if user and (user.user_type == 'admin' or user.is_staff):
                            response.data['cleanup_info'] = {
                                'expired_programs_cleaned': result['total_programs_cleaned'],
                                'users_removed': result['total_users_removed'],
                                'message': 'Expired programs cleaned automatically on login',
                                'programs_cleaned': result.get('programs', [])
                            }
                            
                    else:
                        logger.debug(f"Auto-cleanup on login: No expired programs found. Triggered by: {username}")
                else:
                    logger.debug(f"Auto-cleanup skipped for login: {username} (interval not met or user type not allowed)")
                    
            except Exception as e:
                # Don't fail the login if cleanup fails
                logger = logging.getLogger(__name__)
                logger.error(f"Error during auto-cleanup on login: {str(e)}", exc_info=True)
        # mark messageStatus as delivered for discussion messages
        try:
            from discussion.models import MessageStatus
            from discussion.consumers import BaseDiscussionConsumer
            
            # Get the user from the request
            user = request.user
            
            # Fetch undelivered messages for this user
            undelivered_messages = BaseDiscussionConsumer.get_undelivered_messages(user)
            
            # Mark them as delivered
            for message in undelivered_messages:

                status_obj, created = MessageStatus.objects.get_or_create(
                    message=message,
                    user=user,
                    defaults={'delivered_at': timezone.now()}
                )
                if not created:
                    status_obj.delivered_at = timezone.now()
                    status_obj.save()

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error marking discussion messages as delivered: {str(e)}", exc_info=True)
        
        return response
    
    def should_run_cleanup_on_login(self, user=None):
        """
        Check if cleanup should run on login.
        Can be controlled via Django settings and user type.
        """
        from django.conf import settings
        from django.core.cache import cache
        from django.utils import timezone
        
        # Check if cleanup is enabled
        if not getattr(settings, 'CLEANUP_EXPIRED_PROGRAMS_ON_LOGIN', True):
            return False
        
        # Check if user type is allowed to trigger cleanup
        allowed_user_types = getattr(settings, 'CLEANUP_EXPIRED_PROGRAMS_USER_TYPES', None)
        if allowed_user_types and user and user.user_type not in allowed_user_types:
            return False
        
        # Check cleanup interval to avoid running too frequently
        cleanup_interval = getattr(settings, 'CLEANUP_EXPIRED_PROGRAMS_INTERVAL', 60)  # minutes
        last_cleanup_key = 'last_expired_program_cleanup'
        last_cleanup = cache.get(last_cleanup_key)
        
        if last_cleanup:
            time_since_last = (timezone.now() - last_cleanup).total_seconds() / 60
            if time_since_last < cleanup_interval:
                return False
        
        # Set cache for next interval check
        cache.set(last_cleanup_key, timezone.now(), timeout=cleanup_interval * 60)
        
        return True
