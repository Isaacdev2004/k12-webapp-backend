from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MessageViewSet, MessageImageViewSet, ReactionViewSet,
    MessageStatusViewSet, PersonalMessageStatusViewSet
)
from .unseen_counts import (
    get_unseen_counts, get_channel_unseen_count, get_personal_chat_unseen_count
)

# Create a DefaultRouter and register the viewsets
router = DefaultRouter()
router.register(r'message-images', MessageImageViewSet)
router.register(r'reactions', ReactionViewSet)
router.register(r'messages', MessageViewSet)
router.register(r'message-status', MessageStatusViewSet, basename='message-status')
router.register(r'personal-message-status', PersonalMessageStatusViewSet, basename='personal-message-status')


urlpatterns = [
    path('', include(router.urls)),
    path('unseen-counts/', get_unseen_counts, name='unseen-counts'),
    path('unseen-counts/<str:discussion_type>/<int:discussion_id>/<str:channel>/', 
         get_channel_unseen_count, name='channel-unseen-count'),
    path('unseen-counts/personal/<int:other_user_id>/', 
         get_personal_chat_unseen_count, name='personal-chat-unseen-count'),
]
