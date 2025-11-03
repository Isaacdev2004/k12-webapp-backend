from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.urls import path
from . import views
from . import secure_media_views
from . import nchl_views

from .views import (
    ProgramViewSet,
    SubjectFeeViewSet,
    CourseViewSet,
    SubjectViewSet,
    ChapterViewSet,
    TopicViewSet,
    MCQViewSet,
    MCQQuestionViewSet,
    VideoViewSet,
    ContentViewSet,
    LiveClassViewSet,
    MockTestViewSet,
    MockTestQuestionViewSet,
    NoteViewSet,
    PaymentPictureViewSet,
    MCQQuestionImportView,
    MockTestImportView,
    UserViewSet,
    TeacherUserViewSet,
    MockTestCreateView,
    MockTestListView,
    MCQCreateView,
    MCQListView,
    generate_signature,
    generate_zoom_signature,
    McqResultViewSet,
    MockTestResultViewSet,
    SubjectRecordingVideoViewSet,
    SubjectNoteViewSet,
    FreeSubjectRecordingVideoViewSet,
    FreeSubjectNoteViewSet,
    QrPaymentViewSet,
    test_aws_credentials,
    CoursesMockTestViewSet,
    OnePGPaymentViewSet,
    get_payment_instruments,
    get_service_charge,
    get_process_id,
    initiate_payment,
    payment_notification,
    payment_response,
    check_payment_status,
    enroll_free,
    getFreeSubjectRecordingVideos,
    getFreeSubjectNotes,
    # Multipart upload endpoints
    initiate_multipart_upload,
    sign_multipart_upload_part,
    complete_multipart_upload,
    abort_multipart_upload,
    admin_video_upload,
    admin_video_upload_page,
    multipart_test_page,
    test_widget_page,
    # Zoom recording endpoints
    zoom_webhook,
    zoom_recordings_list,
    process_zoom_recording,
    process_all_pending_recordings,
    sync_zoom_recordings,
    delete_zoom_recording,
    # Notifications
    register_device_token,
    send_manual_notification,
)



router = DefaultRouter()
router.register(r'user', UserViewSet, basename='user')
router.register(r'programs', ProgramViewSet)
router.register(r'subject-fees', SubjectFeeViewSet)
router.register(r'courses', CourseViewSet)
router.register(r'subjects', SubjectViewSet)
router.register(r'chapters', ChapterViewSet)
router.register(r'topics', TopicViewSet)
router.register(r'mcqs', MCQViewSet)
router.register(r'mcq-questions', MCQQuestionViewSet)
router.register(r'videos', VideoViewSet)
router.register(r'contents', ContentViewSet)
router.register(r'live-classes', LiveClassViewSet)
router.register(r'mock-tests', MockTestViewSet)
router.register(r'mock-test-questions', MockTestQuestionViewSet)
router.register(r'notes', NoteViewSet)
router.register(r'payment-pictures', PaymentPictureViewSet)
router.register(r'qr-payments', QrPaymentViewSet)

# router.register(r'teachers', TeacherUserViewSet)
router.register(r'mcq-results', McqResultViewSet, basename='mcq-result')
router.register(r'mocktest-results', MockTestResultViewSet, basename='mocktest-result')

router.register(r'subject-recording-videos', SubjectRecordingVideoViewSet)
# router.register(r'subject-notes', SubjectNoteViewSet)
router.register(r'courses-mock-tests', CoursesMockTestViewSet, basename='courses-mock-tests')
router.register(r'onepg-payments', OnePGPaymentViewSet)
app_name = 'api' 

urlpatterns = [
    path('', include(router.urls)),
    # path('courses/', CourseViewSet, name='course-list'),
    path('import/mcq-questions/', MCQQuestionImportView.as_view(), name='mcq-question-import'),
    path('mcqs/create/', MCQCreateView.as_view(), name='create-mcq'),
    path('mcqs/', MCQListView.as_view(), name='list-mcqs'),

    path('import/mock-tests/', MockTestImportView.as_view(), name='mock-test-import'),
    path('mock-tests/create/', MockTestCreateView.as_view(), name='create-mock-test'),
    path('mock-tests/', MockTestListView.as_view(), name='list-mock-tests'),

    path('generate-signature/', generate_signature),
    path('zoom/generate-signature/', generate_zoom_signature, name='zoom-generate-signature'),
    path('stream/<int:video_id>/', views.stream_video, name='stream_video'),
    path('test-aws/', test_aws_credentials, name='test_aws_credentials'),

    # OnePG Payment Gateway URLs
    path('payments/instruments/', get_payment_instruments, name='payment-instruments'),
    path('payments/service-charge/', get_service_charge, name='service-charge'),
    path('payments/process-id/', get_process_id, name='process-id'),
    path('payments/initiate/', initiate_payment, name='initiate-payment'),
    path('payments/notification/', payment_notification, name='payment-notification'),
    path('payments/response/', payment_response, name='payment-response'),
    path('payments/check-status/<str:txn_id>/', check_payment_status, name='check-payment-status'),

    # Zero-fee enrollment
    path('enrollment/free/', enroll_free, name='enroll-free'),

    # NCHL (ConnectIPS) Payment URLs
    path('nchl/initiate/', nchl_views.NCHLInitiatePaymentView.as_view(), name='nchl-initiate'),
    path('nchl/verify/', nchl_views.NCHLVerifyPaymentView.as_view(), name='nchl-verify'),
    path('nchl/callback/', nchl_views.NCHLCallbackView.as_view(), name='nchl-callback'),

    # QR Payment URLs
    path('qr-payment/generate/', views.generate_qr, name='generate-qr-payment'),
    path('qr-payment/verify/', views.verify_qr_payment, name='verify-qr-payment'),

    # free content URLs
    path('<int:program_id>/free-subject-recording-videos/', getFreeSubjectRecordingVideos, name='free-subject-recording-videos'),
    path('<int:program_id>/free-subject-notes/', getFreeSubjectNotes , name='free-subject-notes'),
    path('free-subject-recording-videos/<int:pk>/', FreeSubjectRecordingVideoViewSet.as_view({'get': 'retrieve'}), name='free-subject-recording-video-detail'),
    path('free-subject-notes/<int:pk>/', FreeSubjectNoteViewSet.as_view({'get': 'retrieve'}), name='free-subject-note-detail'),

    # Direct-to-R2 multipart upload APIs
    path('uploads/multipart/initiate/', initiate_multipart_upload, name='r2-multipart-initiate'),
    path('uploads/multipart/sign-part/', sign_multipart_upload_part, name='r2-multipart-sign-part'),
    path('uploads/multipart/complete/', complete_multipart_upload, name='r2-multipart-complete'),
    path('uploads/multipart/abort/', abort_multipart_upload, name='r2-multipart-abort'),
    
    # Admin video upload endpoint
    path('admin/video-upload/', admin_video_upload, name='admin-video-upload'),
    path('admin/video-upload-page/', admin_video_upload_page, name='admin-video-upload-page'),
    
    # Test pages
    path('uploads/multipart/test/', multipart_test_page, name='r2-multipart-test'),
    path('uploads/multipart/test-widget/', test_widget_page, name='r2-test-widget'),
    
    # Secure Media Access URLs
    path('secure-media/<path:media_key>/', secure_media_views.serve_secure_media, name='serve-secure-media'),
    path('media/secure-url/', secure_media_views.get_secure_media_url, name='secure-media-url'),
    path('media/upload-credentials/', secure_media_views.get_upload_credentials, name='media-upload-credentials'),
    path('media/complete-upload/', secure_media_views.complete_upload, name='media-complete-upload'),
    path('media/access-token/', secure_media_views.generate_access_token, name='media-access-token'),
    path('media/validate-token/', secure_media_views.validate_access_token, name='media-validate-token'),
    path('media/delete/', secure_media_views.delete_media, name='media-delete'),
    
    # Zoom recording management URLs
    path('zoom/webhook/', zoom_webhook, name='zoom-webhook'),
    path('zoom/recordings/', zoom_recordings_list, name='zoom-recordings-list'),
    path('zoom/recordings/<int:recording_id>/process/', process_zoom_recording, name='process-zoom-recording'),
    path('zoom/recordings/process-all/', process_all_pending_recordings, name='process-all-pending-recordings'),
    path('zoom/recordings/sync/', sync_zoom_recordings, name='sync-zoom-recordings'),
    path('zoom/recordings/<int:recording_id>/delete/', delete_zoom_recording, name='delete-zoom-recording'),

    # Notifications
    path('notifications/register-device/', register_device_token, name='register-device'),
    path('notifications/send/', send_manual_notification, name='send-manual-notification'),
]