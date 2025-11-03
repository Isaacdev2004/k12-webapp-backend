# discussion/permissions.py

from rest_framework import permissions

class IsAdmin(permissions.BasePermission):
    """
    Allows access only to admin users.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'user_type', None) == 'admin'

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Admins can perform any action; others can only read.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and getattr(request.user, 'user_type', None) == 'admin'

class IsAdminOrEnrolled(permissions.BasePermission):
    """
    Admins have full access. Enrolled users can read and write in subject-specific channels.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if getattr(user, 'user_type', None) == 'admin':
            return True

        channel_type = getattr(obj, 'channel_type', None)

        if channel_type in ['program', 'motivation', 'off_topics', 'meme', 'discussion']:
            return obj.program.users.filter(id=user.id).exists()
        elif channel_type in ['subject', 'assignment']:
            return obj.subject.enrolled_users.filter(id=user.id).exists()
        elif channel_type in ['notices', 'routine']:
            if request.method in permissions.SAFE_METHODS:
                return obj.program.users.filter(id=user.id).exists()
            return False  # Only admins can post, already handled above
        return False

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an 'user' attribute.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True
        # Write permissions are only allowed to the owner
        return getattr(obj, 'user', None) == request.user
