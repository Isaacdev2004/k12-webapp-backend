from django.urls import path
from .views import (
    DashboardStatsView, ContentsView, PaymentsView, 
    MockTestResultsView, RecordingVideoView, UserProfileView,
    LiveClassView, NotesView, ChatView, DiscussionChannelsView,
    MockTestView, McqResultsView, EnhancedChatView
)

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='student-dashboard'),
    path('contents/', ContentsView.as_view(), name='student-contents'),
    path('payments/', PaymentsView.as_view(), name='student-payments'),
    path('mocktest-results/', MockTestResultsView.as_view(), name='mocktest-results'),
    path('mcq-results/', McqResultsView.as_view(), name='mcq-results'),
    path('recording-videos/', RecordingVideoView.as_view(), name='recording-videos'),
    path('profile/', UserProfileView.as_view(), name='student-profile'),
    path('live-classes/', LiveClassView.as_view(), name='live-classes'),
    path('notes/', NotesView.as_view(), name='notes'),
    path('chat/users/', ChatView.as_view(), name='chat-users'),
    path('chat/users/enhanced/', EnhancedChatView.as_view(), name='enhanced-chat-users'),
    path('discussion/channels/', DiscussionChannelsView.as_view(), name='discussion-channels'),
    path('mocktests/', MockTestView.as_view(), name='mock-tests'),
]
