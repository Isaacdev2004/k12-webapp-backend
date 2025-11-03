# server/home/urls.py
from django.urls import path
# from . import views   
from .views import PasswordResetView, PasswordResetConfirmView, CurrentUserView, get_users_list, get_enhanced_users_list, CustomTokenObtainPairView
from .google_auth import google_auth_callback, google_login_url
from django.views.generic import TemplateView
from rest_framework_simplejwt.views import TokenRefreshView

app_name = 'accounts'

urlpatterns = [
    path('password-reset/', PasswordResetView.as_view(), name='password_reset'),
    path('password-reset-confirm/<str:token>/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('current-user/', CurrentUserView.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update'
    }), name='current-user'),
    path('users/', get_users_list, name='users-list'),
    path('users/enhanced/', get_enhanced_users_list, name='enhanced-users-list'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Google OAuth URLs
    path('google/login/', google_login_url, name='google_login_url'),
    path('google/callback/', google_auth_callback, name='google_auth_callback'),
    path('google/test/', TemplateView.as_view(template_name='google_oauth_test.html'), name='google_oauth_test'),
]
