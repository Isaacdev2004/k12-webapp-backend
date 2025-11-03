# decorators.py

from django.http import HttpResponseForbidden

def user_type_required(user_types):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if request.user.user_type in user_types:
                return view_func(request, *args, **kwargs)
            else:
                return HttpResponseForbidden("You are not authorized to view this page.")
        return _wrapped_view
    return decorator
