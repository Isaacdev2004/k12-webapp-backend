from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from . import settings  
from auth.views import LogoutView, PasswordResetRequestView, PasswordResetConfirmView, PasswordChangeView
from accounts.views import CurrentUserView
from django.views.static import serve
from django.contrib.staticfiles.urls import staticfiles_urlpatterns # new



urlpatterns = [
    path('admin/', admin.site.urls),
    path('nested_admin/', include('nested_admin.urls')),

    path("auth/", include("djoser.urls")),
    path("auth/", include("djoser.urls.jwt")),
    path("auth/", include("djoser.urls.authtoken")),
    # path("auth/", include("djoser.urls.activation")),
    
    # Allauth URLs for social authentication
    path('auth/', include('allauth.urls')),
    
    path('auth/current_user/', CurrentUserView.as_view({'get': 'retrieve'})),
    path("auth/logout/", LogoutView.as_view()),

    # Password management URLs
    path('auth/password/reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('auth/password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('auth/password/change/', PasswordChangeView.as_view(), name='password_change'),

    path('home/', include('home.urls')),
    path('api/', include('api.urls')),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),

    # path('elearning/', include('elearning.urls')),
    path('discussion/', include('discussion.urls')),
    path('accounts/', include('accounts.urls')),
    path('students/', include('student.urls')),

    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
]


# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
#     urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
