from rest_framework import permissions

class IsTeacher(permissions.BasePermission):
    """
    Custom permission to only allow teachers to access certain views.
    """

    def has_permission(self, request, view):
        # Check if the user is a teacher
        if request.user and hasattr(request.user, 'user_type') and request.user.user_type == 'teacher':
            return True
        return False

class IsStudent(permissions.BasePermission):
    """
    Custom permission to only allow students to access certain views.
    """

    def has_permission(self, request, view):
        # Check if the user is a student
        if request.user and hasattr(request.user, 'user_type') and request.user.user_type == 'student':
            return True
        return False

class IsSuperAdmin(permissions.BasePermission):
    """
    Custom permission to only allow superadmins to access certain views.
    """

    def has_permission(self, request, view):
        # Check if the user is a superadmin
        if request.user and hasattr(request.user, 'user_type') and request.user.user_type == 'superadmin':
            return True
        return False
    
class IsPublic(permissions.BasePermission):
    """
    Custom permission to allow public access to certain views.
    """

    def has_permission(self, request, view):
        return True

# api/permissions.py

from rest_framework import permissions

class MockTestAccessPermission(permissions.BasePermission):
    """
    Custom permission to allow access to MockTests based on their 'is_free' status
    and the user's enrolled courses.
    """

    def has_object_permission(self, request, view, obj):
        # Safe methods are allowed if user has general access
        if request.method in permissions.SAFE_METHODS:
            if obj.is_free:
                return True
            return obj.course in request.user.courses.all()
        
        # For write operations, you might want additional checks
        # For simplicity, let's restrict write operations to admin users
        return request.user.is_staff


class NoteAccessPermission(permissions.BasePermission):
    """
    Custom permission to allow access to Notes based on their 'is_free' status
    and the user's enrolled courses.
    """

    def has_object_permission(self, request, view, obj):
        # Allow access to free notes
        if obj.is_free:
            return True

        # Allow access if the user is enrolled in the associated course
        return obj.course in request.user.courses.all()


class LiveClassAccessPermission(permissions.BasePermission):
    """
    Custom permission to allow access to LiveClass based on:
    1. If the class is free (is_free=True)
    2. If the user is enrolled in the subject that the live class belongs to
    """

    def has_object_permission(self, request, view, obj):
        # Staff and superusers can access all live classes
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        # Allow access to free live classes
        if obj.is_free:
            return True

        # Check if user is enrolled in the subject that this live class belongs to
        return obj.subject in request.user.subjects.all()
