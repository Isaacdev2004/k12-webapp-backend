from rest_framework import serializers
from api.models import Subject, Course, MockTestResult, Chapter, Topic, Content, Video, MCQ, PaymentPicture, SubjectRecordingVideo, LiveClass, SubjectNote, MockTest, McqResult, OnePGPayment, QrPaymentTransaction
from accounts.models import CustomUser
import logging
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

# Utility function to convert R2 URLs to Cloudflare Worker URLs
def convert_r2_url_to_worker_url(url):
    """Convert URLs starting with https://r2.aakhyaan.org to use Cloudflare Worker"""
    if url and url.startswith('https://r2.aakhyaan.org/'):
        # Extract the path from the R2 URL
        path = url.replace('https://r2.aakhyaan.org/', '')
        
        # Use Cloudflare Worker URL if configured
        if hasattr(settings, 'CLOUDFLARE_WORKER_URL') and settings.CLOUDFLARE_WORKER_URL:
            return f"{settings.CLOUDFLARE_WORKER_URL}/{path}"
        else:
            # Fallback to original URL if worker not configured
            return url
    return url

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'phone', 'college', 'city', 'address', 'profile_image'
        ]
        read_only_fields = ['id', 'username', 'email']

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            request = self.context.get('request')
            
            # Add full URL for profile image if it exists
            if data.get('profile_image'):
                data['profile_image'] = request.build_absolute_uri(instance.profile_image.url)
            
            return data
        except Exception as e:
            logger.error(f"Error serializing user profile {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'username': instance.username,
                'email': instance.email,
                'first_name': '',
                'last_name': '',
                'phone': '',
                'college': '',
                'city': '',
                'address': '',
                'profile_image': None
            }

class ChatUserSerializer(serializers.ModelSerializer):
    user_type = serializers.CharField(source='get_user_type_display')
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'user_type',
            'first_name', 'last_name', 'profile_image'
        ]

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            request = self.context.get('request')
            
            # Add full URL for profile image if it exists
            if data.get('profile_image'):
                data['profile_image'] = request.build_absolute_uri(instance.profile_image.url)
            
            return data
        except Exception as e:
            logger.error(f"Error serializing ChatUser {instance.id}: {str(e)}")
            return super().to_representation(instance)

class EnhancedChatUserSerializer(serializers.ModelSerializer):
    """Enhanced serializer that includes unseen message count and last message data for sorting"""
    user_type = serializers.CharField(source='get_user_type_display')
    unseen_count = serializers.IntegerField(read_only=True, default=0)
    last_message_time = serializers.DateTimeField(read_only=True, allow_null=True)
    last_message_content = serializers.CharField(read_only=True, allow_null=True, max_length=100)
    last_message_sender = serializers.CharField(read_only=True, allow_null=True)
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'user_type',
            'first_name', 'last_name', 'profile_image',
            'unseen_count', 'last_message_time', 'last_message_content', 'last_message_sender'
        ]

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            request = self.context.get('request')
            
            # Add full URL for profile image if it exists
            if data.get('profile_image'):
                data['profile_image'] = request.build_absolute_uri(instance.profile_image.url)
            
            # Truncate last message content if too long
            if data.get('last_message_content') and len(data['last_message_content']) > 50:
                data['last_message_content'] = data['last_message_content'][:47] + '...'
            
            return data
        except Exception as e:
            logger.error(f"Error serializing EnhancedChatUser {instance.id}: {str(e)}")
            return super().to_representation(instance)


class LiveClassSerializer(serializers.ModelSerializer):
    host_name = serializers.CharField(source='host.get_full_name', read_only=True)
    subjectName = serializers.CharField(source='subject.name', read_only=True)
    current_datetime = serializers.SerializerMethodField()  # Add field for current datetime
    days_of_week_display = serializers.CharField(read_only=True)  # Add days display
    duration = serializers.IntegerField(read_only=True)  # Add duration property

    class Meta:
        model = LiveClass
        fields = [
            'id', 'title', 'description', 'live_url', 'host_name',
            'start_time', 'end_time', 'is_free', 'subject', 'subjectName',
            'recurrence_type', 'recurrence_start_date', 'recurrence_end_date', 
            'days_of_week', 'days_of_week_display', 'day_of_week', 'duration',
            'current_datetime'  # Add current_datetime
        ]

    def get_current_datetime(self, obj):
        return timezone.localtime(timezone.now()).isoformat()  # Returns PKT time (e.g., 2025-08-03T20:36:00+05:00)

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            return data
        except Exception as e:
            logger.error(f"Error serializing live class {instance.id}: {str(e)}")
            return {
                'id': str(instance.id),
                'title': str(instance),
                'description': None,
                'live_url': None,
                'host_name': '',
                'start_time': None,
                'end_time': None,
                'is_free': False,
                'subject': None,
                'subjectName': '',
                'recurrence_start_date': None,
                'recurrence_end_date': None,
                'current_datetime': timezone.localtime(timezone.now()).isoformat()  # Ensure fallback includes current_datetime
            } 

class SubjectNoteSerializer(serializers.ModelSerializer):
    pdf_url = serializers.SerializerMethodField()
    pdf_media_key = serializers.SerializerMethodField()

    class Meta:
        model = SubjectNote
        fields = ['id', 'title', 'pdf', 'pdf_url', 'pdf_media_key', 'created_at', 'is_active']

    def get_pdf_url(self, obj):
        # Keep for backward compatibility but prefer pdf_media_key for secure access
        request = self.context.get('request')
        if obj.pdf:
            return request.build_absolute_uri(obj.pdf.url) if request else obj.pdf.url
        return None
    
    def get_pdf_media_key(self, obj):
        """Return the media key for secure PDF access"""
        if obj.pdf:
            # Extract the key from the file path (remove leading 'media/' if present)
            key = str(obj.pdf.name)
            if key.startswith('media/'):
                key = key[6:]  # Remove 'media/' prefix
            return key
        return None

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            return data
        except Exception as e:
            logger.error(f"Error serializing subject note {instance.id}: {str(e)}")
            return {
                'id': str(instance.id),
                'title': str(instance),
                'pdf': str(instance.pdf.url),
                'created_at': None,
                'is_active': True
            }
        

        
class SubjectWithNotesSerializer(serializers.ModelSerializer):
    subject_notes = SubjectNoteSerializer(many=True, read_only=True)

    class Meta:
        model = Subject
        fields = ['id', 'name', 'subject_thumbnail', 'subject_notes']

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            request = self.context.get('request')
            
            # Add full URL for thumbnail if it exists
            if data.get('subject_thumbnail'):
                data['subject_thumbnail_url'] = request.build_absolute_uri(instance.subject_thumbnail.url)
            
            # Set is_active to True for all notes
            if data.get('subject_notes'):
                for note in data['subject_notes']:
                    if note:
                        note['is_active'] = True
            
            return data
        except Exception as e:
            logger.error(f"Error serializing subject with notes {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'name': str(instance),
                'subject_thumbnail': None,
                'subject_thumbnail_url': None,
                'subject_notes': []
            }

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name', 'subject_thumbnail']

class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'name', 'description', 'course_thumbnail']

class McqResultSerializer(serializers.ModelSerializer):
    mcq_title = serializers.CharField(source='mcq.title', read_only=True)
    topic_name = serializers.CharField(source='mcq.topic.name', read_only=True)
    chapter_name = serializers.CharField(source='mcq.topic.chapter.name', read_only=True)
    subject_name = serializers.CharField(source='mcq.topic.chapter.subject.name', read_only=True)
    course_name = serializers.CharField(source='mcq.topic.chapter.subject.course.name', read_only=True)

    class Meta:
        model = McqResult
        fields = [
            'id', 'user', 'mcq', 'mcq_title', 'topic_name', 'chapter_name',
            'subject_name', 'course_name', 'score', 'total_score', 'correct_answers',
            'wrong_answers', 'unattempted', 'completed_at', 'submissions_data'
        ]
        read_only_fields = ['user', 'completed_at']

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Ensure submissions_data is a dictionary and summary is present
            if not data.get('submissions_data'):
                data['submissions_data'] = {
                    'questions': [],
                    'summary': {
                        'score': instance.score,
                        'total_score': instance.total_score,
                        'percentage': (instance.score / instance.total_score) * 100 if instance.total_score else 0,
                        'correct_answers': instance.correct_answers,
                        'wrong_answers': instance.wrong_answers,
                        'unattempted': instance.unattempted
                    }
                }
            return data
        except Exception as e:
            logger.error(f"Error serializing McqResult {instance.id}: {str(e)}")
            # Fallback representation in case of an error
            return {
                'id': instance.id,
                'mcq_title': 'N/A',
                'score': 0,
                'total_score': 0,
                'correct_answers': 0,
                'wrong_answers': 0,
                'unattempted': 0,
                'completed_at': None,
                'submissions_data': {
                    'questions': [],
                    'summary': {
                        'score': 0,
                        'total_score': 0,
                        'percentage': 0,
                        'correct_answers': 0,
                        'wrong_answers': 0,
                        'unattempted': 0
                    }
                }
            }

class MockTestResultSerializer(serializers.ModelSerializer):
    mock_test = serializers.CharField(source='mock_test.title')
    course_name = serializers.CharField(source='mock_test.course.name', read_only=True)

    class Meta:
        model = MockTestResult
        fields = [
            'id', 'mock_test', 'course_name', 'score', 'total_score',
            'correct_answers', 'wrong_answers', 'unattempted',
            'completed_at', 'status', 'submissions_data'
        ]

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Ensure submissions_data is a dictionary
            if not data.get('submissions_data'):
                data['submissions_data'] = {
                    'questions': [],
                    'summary': {
                        'score': data.get('score', 0),
                        'total_score': data.get('total_score', 0),
                        'percentage': (data.get('score', 0) / data.get('total_score', 1)) * 100 if data.get('total_score') else 0,
                        'correct_answers': data.get('correct_answers', 0),
                        'wrong_answers': data.get('wrong_answers', 0),
                        'unattempted': data.get('unattempted', 0)
                    }
                }
            return data
        except Exception as e:
            logger.error(f"Error serializing mock test result {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'mock_test': str(instance.mock_test),
                'course_name': str(instance.mock_test.course),
                'score': instance.score,
                'total_score': instance.total_score,
                'correct_answers': instance.correct_answers,
                'wrong_answers': instance.wrong_answers,
                'unattempted': instance.unattempted,
                'completed_at': instance.completed_at,
                'status': instance.status,
                'submissions_data': {
                    'questions': [],
                    'summary': {
                        'score': instance.score,
                        'total_score': instance.total_score,
                        'percentage': (instance.score / instance.total_score) * 100 if instance.total_score else 0,
                        'correct_answers': instance.correct_answers,
                        'wrong_answers': instance.wrong_answers,
                        'unattempted': instance.unattempted
                    }
                }
            }

class DashboardStatsSerializer(serializers.Serializer):
    total_subjects_enrolled = serializers.IntegerField()
    total_programs_enrolled = serializers.IntegerField()
    total_mocktest_results = serializers.IntegerField()
    subjects = SubjectSerializer(many=True)
    courses = CourseSerializer(many=True)
    mocktest_results = MockTestResultSerializer(many=True)

    def to_representation(self, instance):
        # Ensure we have all required fields
        if not all(key in instance for key in ['total_subjects_enrolled', 'total_programs_enrolled', 'total_mocktest_results', 'subjects', 'courses', 'mocktest_results']):
            raise serializers.ValidationError("Missing required fields in dashboard stats")
        return super().to_representation(instance)

class VideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = [
            'id', 'title', 'video_url', 'video_file', 'thumbnail', 
            'video_description', 'is_free', 'is_active', 'video_duration'
        ]

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Add full URL for thumbnail if it exists
            if data.get('thumbnail'):
                data['thumbnail_url'] = self.context['request'].build_absolute_uri(instance.thumbnail.url)
            return data
        except Exception as e:
            logger.error(f"Error serializing video {instance.id}: {str(e)}")
            return None

class ContentSerializer(serializers.ModelSerializer):
    pdf_media_key = serializers.SerializerMethodField()
    
    class Meta:
        model = Content
        fields = ['id', 'title', 'thumbnail', 'pdf', 'pdf_media_key', 'is_active', 'is_free']

    def get_pdf_media_key(self, obj):
        """Return the media key for secure PDF access"""
        if obj.pdf:
            # Extract the key from the file path (remove leading 'media/' if present)
            key = str(obj.pdf.name)
            if key.startswith('media/'):
                key = key[6:]  # Remove 'media/' prefix
            return key
        return None

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Add full URLs for thumbnail and pdf if they exist
            if data.get('thumbnail'):
                data['thumbnail_url'] = self.context['request'].build_absolute_uri(instance.thumbnail.url)
            if data.get('pdf'):
                data['pdf_url'] = self.context['request'].build_absolute_uri(instance.pdf.url)
            return data
        except Exception as e:
            logger.error(f"Error serializing content {instance.id}: {str(e)}")
            return None

class MCQSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCQ
        fields = [
            'id', 'title', 'description', 'is_active', 'is_free', 
            'status', 'scheduled_start_time', 'duration', 'negMark'
        ]

    def to_representation(self, instance):
        try:
            return super().to_representation(instance)
        except Exception as e:
            logger.error(f"Error serializing MCQ {instance.id}: {str(e)}")
            return None

class TopicSerializer(serializers.ModelSerializer):
    contents = ContentSerializer(many=True, read_only=True)
    videos = VideoSerializer(many=True, read_only=True)
    mcqs = MCQSerializer(many=True, read_only=True)

    class Meta:
        model = Topic
        fields = ['id', 'name', 'description', 'contents', 'videos', 'mcqs']

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Filter out None values from nested serializers
            data['contents'] = [c for c in data['contents'] if c is not None]
            data['videos'] = [v for v in data['videos'] if v is not None]
            data['mcqs'] = [m for m in data['mcqs'] if m is not None]
            return data
        except Exception as e:
            logger.error(f"Error serializing topic {instance.id}: {str(e)}")
            return None

class ChapterSerializer(serializers.ModelSerializer):
    topics = TopicSerializer(many=True, read_only=True)

    class Meta:
        model = Chapter
        fields = ['id', 'name', 'description', 'topics']

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Filter out None values from nested serializers
            data['topics'] = [t for t in data['topics'] if t is not None]
            return data
        except Exception as e:
            logger.error(f"Error serializing chapter {instance.id}: {str(e)}")
            return None

class SubjectContentsSerializer(serializers.ModelSerializer):
    chapters = ChapterSerializer(source='subject_chapters', many=True, read_only=True)

    class Meta:
        model = Subject
        fields = ['id', 'name', 'subject_thumbnail', 'course', 'chapters']

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Add full URL for thumbnail if it exists
            if data.get('subject_thumbnail'):
                data['subject_thumbnail_url'] = self.context['request'].build_absolute_uri(instance.subject_thumbnail.url)
            # Filter out None values from nested serializers
            data['chapters'] = [c for c in data['chapters'] if c is not None]
            return data
        except Exception as e:
            logger.error(f"Error serializing subject {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'name': str(instance),
                'subject_thumbnail': None,
                'subject_thumbnail_url': None,
                'course': None,
                'chapters': []
            }

class PaymentSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(many=True, read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)
    program_name = serializers.CharField(source='program.name', read_only=True)

    class Meta:
        model = PaymentPicture
        fields = [
            'id', 'payment_image', 'course', 'course_name',
            'program', 'program_name', 'subject', 'date',
            'is_verified', 'total_amount', 'status',
            'rejected_reason'
        ]

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Add full URL for payment image if it exists
            if data.get('payment_image'):
                data['payment_image'] = self.context['request'].build_absolute_uri(instance.payment_image.url)
            # Ensure subject is an array and filter out None values
            if data.get('subject'):
                data['subject'] = [s for s in data['subject'] if s is not None]
            else:
                data['subject'] = []
            # Convert status to lowercase for consistency
            if data.get('status'):
                data['status'] = data['status'].lower()
            return data
        except Exception as e:
            logger.error(f"Error serializing payment {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'payment_image': None,
                'course': None,
                'course_name': '',
                'program': None,
                'program_name': '',
                'subject': [],
                'date': instance.date,
                'is_verified': False,
                'total_amount': 0,
                'status': 'pending',
                'rejected_reason': None
            }

class OnePGPaymentSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(many=True, read_only=True, source='subjects')
    course_name = serializers.CharField(source='course.name', read_only=True)
    program_name = serializers.CharField(source='program.name', read_only=True)

    class Meta:
        model = OnePGPayment
        fields = [
            'id', 'course', 'course_name', 'program', 'program_name', 'subject',
            'transaction_date', 'status', 'total_amount', 'merchant_txn_id'
        ]

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Map fields to match PaymentPicture structure for frontend compatibility
            data['payment_image'] = None  # OnePG payments don't have images
            data['date'] = data.pop('transaction_date')  # Rename for consistency
            data['is_verified'] = data['status'] == 'success'  # Map status to is_verified
            data['rejected_reason'] = instance.remarks if data['status'] == 'failed' else None
            # Convert status mapping: success -> approved, failed -> rejected, pending -> pending
            status_mapping = {'success': 'approved', 'failed': 'rejected', 'pending': 'pending'}
            data['status'] = status_mapping.get(data['status'], data['status']).lower()
            
            # Ensure subject is an array and filter out None values
            if data.get('subject'):
                data['subject'] = [s for s in data['subject'] if s is not None]
            else:
                data['subject'] = []
                
            return data
        except Exception as e:
            logger.error(f"Error serializing OnePG payment {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'payment_image': None,
                'course': instance.course_id if hasattr(instance, 'course') else None,
                'course_name': instance.course.name if hasattr(instance, 'course') and instance.course else '',
                'program': instance.program_id if hasattr(instance, 'program') else None,
                'program_name': instance.program.name if hasattr(instance, 'program') and instance.program else '',
                'subject': [],
                'date': instance.transaction_date,
                'is_verified': False,
                'total_amount': float(instance.total_amount) if instance.total_amount else 0,
                'status': 'pending',
                'rejected_reason': None
            }

class QrPaymentTransactionSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(many=True, read_only=True, source='subjects')
    course_name = serializers.CharField(source='course.name', read_only=True)
    program_name = serializers.CharField(source='program.name', read_only=True)

    class Meta:
        model = QrPaymentTransaction
        fields = [
            'id', 'course', 'course_name', 'program', 'program_name', 'subject',
            'transaction_date', 'status', 'transaction_amount', 'bill_number'
        ]

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            # Map fields to match PaymentPicture structure for frontend compatibility
            data['payment_image'] = None  # QR payments don't have images
            data['date'] = data.pop('transaction_date')  # Rename for consistency
            data['total_amount'] = data.pop('transaction_amount')  # Rename for consistency
            data['is_verified'] = data['status'] == 'success'  # Map status to is_verified
            data['rejected_reason'] = None  # QR payments don't have rejection reasons
            # Convert status mapping: success -> approved, failed -> rejected, pending -> pending
            status_mapping = {'success': 'approved', 'failed': 'rejected', 'pending': 'pending'}
            data['status'] = status_mapping.get(data['status'], data['status']).lower()
            
            # Ensure subject is an array and filter out None values
            if data.get('subject'):
                data['subject'] = [s for s in data['subject'] if s is not None]
            else:
                data['subject'] = []
                
            return data
        except Exception as e:
            logger.error(f"Error serializing QR payment {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'payment_image': None,
                'course': instance.course_id if hasattr(instance, 'course') else None,
                'course_name': instance.course.name if hasattr(instance, 'course') and instance.course else '',
                'program': instance.program_id if hasattr(instance, 'program') else None,
                'program_name': instance.program.name if hasattr(instance, 'program') and instance.program else '',
                'subject': [],
                'date': instance.transaction_date,
                'is_verified': False,
                'total_amount': float(instance.transaction_amount) if instance.transaction_amount else 0,
                'status': 'pending',
                'rejected_reason': None
            }

class SubjectRecordingVideoSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()
    
    class Meta:
        model = SubjectRecordingVideo
        fields = [
            'id', 'title', 'video_url', 'video_file', 'video_description',
            'thumbnail', 'is_active', 'video_duration', 'created_at', 'updated_at'
        ]

    def get_video_url(self, obj):
        """Convert R2 URLs to use Cloudflare Worker for secure access"""
        return convert_r2_url_to_worker_url(obj.video_url)

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            request = self.context.get('request')
            
            # Add full URLs for media fields
            if data.get('thumbnail'):
                data['thumbnail_url'] = request.build_absolute_uri(instance.thumbnail.url)
            if data.get('video_file'):
                data['video_file'] = request.build_absolute_uri(instance.video_file.url)
            
            return data
        except Exception as e:
            logger.error(f"Error serializing recording video {instance.id}: {str(e)}")
            return None

class SubjectVideoSerializer(serializers.ModelSerializer):
    subject_recording_videos = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ['id', 'name', 'subject_thumbnail', 'subject_recording_videos']

    def get_subject_recording_videos(self, obj):
        # Sort videos by created_at in ascending order
        videos = obj.subject_recording_videos.all().order_by('created_at')
        serializer = SubjectRecordingVideoSerializer(videos, many=True, context=self.context)
        return serializer.data

    def to_representation(self, instance):
        try:
            logger.info(f"Serializing subject {instance.id} with recording videos")
            data = super().to_representation(instance)
            request = self.context.get('request')
            
            # Add full URL for thumbnail if it exists
            if data.get('subject_thumbnail'):
                try:
                    data['subject_thumbnail_url'] = request.build_absolute_uri(instance.subject_thumbnail.url)
                    logger.info(f"Added thumbnail URL for subject {instance.id}")
                except Exception as e:
                    logger.error(f"Error building thumbnail URL for subject {instance.id}: {str(e)}")
                    data['subject_thumbnail_url'] = None
            
            # Filter out None values from videos
            if data.get('subject_recording_videos'):
                data['subject_recording_videos'] = [v for v in data['subject_recording_videos'] if v is not None]
                logger.info(f"Processed {len(data['subject_recording_videos'])} recording videos for subject {instance.id}")
            else:
                data['subject_recording_videos'] = []
            
            return data
        except Exception as e:
            logger.error(
                f"Error serializing subject recording videos for subject {instance.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return {
                'id': instance.id,
                'name': str(instance),
                'subject_thumbnail': None,
                'subject_thumbnail_url': None,
                'subject_recording_videos': []
            }

class MockTestSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    
    class Meta:
        model = MockTest
        fields = [
            'id', 'title', 'description', 'is_active', 'is_free',
            'scheduled_start_time', 'start_time', 'end_time',
            'duration', 'negMark', 'course', 'course_name', 'created_at',
            'updated_at'
        ]

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            
            # Handle duration field
            if isinstance(instance.duration, str):
                # If duration is already a string, use it directly
                data['duration'] = instance.duration
            elif hasattr(instance.duration, 'total_seconds'):
                # If duration is a timedelta, convert it
                duration_seconds = int(instance.duration.total_seconds())
                hours = duration_seconds // 3600
                minutes = (duration_seconds % 3600) // 60
                data['duration'] = f"{hours:02d}:{minutes:02d}:00"
            else:
                # Default duration if the field is invalid or None
                data['duration'] = "01:00:00"
            
            # Ensure other fields have proper default values
            data['title'] = data.get('title', '')
            data['description'] = data.get('description', '')
            data['is_active'] = data.get('is_active', False)
            data['is_free'] = data.get('is_free', False)
            data['scheduled_start_time'] = data.get('scheduled_start_time')
            data['start_time'] = data.get('start_time')
            data['end_time'] = data.get('end_time')
            data['negMark'] = data.get('negMark', 0)
            data['course'] = data.get('course')
            data['course_name'] = data.get('course_name', '')
            data['created_at'] = data.get('created_at')
            data['updated_at'] = data.get('updated_at')
            
            return data
        except Exception as e:
            logger.error(f"Error serializing mock test {instance.id}: {str(e)}")
            return {
                'id': instance.id,
                'title': str(instance),
                'description': '',
                'is_active': False,
                'is_free': False,
                'scheduled_start_time': None,
                'start_time': None,
                'end_time': None,
                'duration': '01:00:00',
                'negMark': 0,
                'course': None,
                'course_name': '',
                'created_at': None,
                'updated_at': None
            }

class DiscussionMessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    message = serializers.CharField()
    username = serializers.CharField()
    timestamp = serializers.DateTimeField()
    images = serializers.ListField(child=serializers.CharField(), required=False)
    reactions = serializers.DictField(child=serializers.IntegerField(), required=False)
    reply_to = serializers.DictField(required=False)

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            return data
        except Exception as e:
            logger.error(f"Error serializing discussion message: {str(e)}")
            return {
                'id': 0,
                'message': '',
                'username': '',
                'timestamp': None,
                'images': [],
                'reactions': {},
                'reply_to': None
            }

class DiscussionChannelSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    channel_type = serializers.CharField()
    key = serializers.CharField()
    channel_type_name = serializers.CharField()

    def to_representation(self, instance):
        try:
            data = super().to_representation(instance)
            return data
        except Exception as e:
            logger.error(f"Error serializing discussion channel: {str(e)}")
            return {
                'id': 0,
                'name': '',
                'channel_type': '',
                'key': '',
                'channel_type_name': ''
            }
