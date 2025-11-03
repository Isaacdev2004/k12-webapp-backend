from rest_framework import serializers
from accounts.models import CustomUser
from django.contrib.auth.password_validation import validate_password
from django.conf import settings
import logging
import boto3
from botocore.client import Config

from django.contrib.auth import get_user_model
from .models import (
    Program,
    SubjectFee,
    Course,
    Subject,
    Chapter,
    PaymentPicture,
    Topic,
    MCQ,
    MCQQuestion,
    Video,
    Content,
    LiveClass,
    MockTest,
    MockTestQuestion,
    Note,
    McqResult,
    MockTestResult,
    SubjectRecordingVideo,
    SubjectNote,
    QrPayment,
    OnePGPayment,
    QrPaymentTransaction,
    NCHLPayment
)

# Logger for this module — use logging instead of print so Gunicorn captures messages
logger = logging.getLogger(__name__)


def generate_signed_r2_url(url, expiration=3600):
    """
    Generate a signed URL for R2 storage with configurable expiration.
    
    Args:
        url: The URL to sign (can be a full URL or just a key)
        expiration: URL expiration time in seconds (default: 1 hour)
    
    Returns:
        Signed URL string or original URL if signing fails
    """
    if not url:
        return url
    
    # Clean the URL first (remove any existing query parameters)
    url = url.split('?')[0]
    
    # Skip signing if it's not an R2 URL
    if not any(domain in url for domain in ['r2.cloudflarestorage.com', 'r2.k12nepal.com', settings.R2_CUSTOM_DOMAIN or '']):
        return url
    
    try:
        # Extract the key from the URL
        # Handle different URL formats
        if 'r2.cloudflarestorage.com' in url:
            # Format: https://xxx.r2.cloudflarestorage.com/bucket/path/to/file
            parts = url.split('.r2.cloudflarestorage.com/')
            if len(parts) > 1:
                key = parts[1].split('/', 1)[1] if '/' in parts[1] else parts[1]
            else:
                return url
        elif settings.R2_CUSTOM_DOMAIN and settings.R2_CUSTOM_DOMAIN in url:
            # Format: https://custom.domain.com/path/to/file
            key = url.split(settings.R2_CUSTOM_DOMAIN + '/')[-1]
        else:
            # Assume it's just a key
            key = url
        
        # Remove 'media/' prefix if present (since it's usually in the bucket)
        # if key.startswith('media/'):
        #     key = key[6:]
        
        # Create S3 client for R2
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        
        # Generate presigned URL
        signed_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.R2_STORAGE_BUCKET_NAME,
                'Key': key
            },
            ExpiresIn=expiration
        )
        
        return signed_url
        
    except Exception as e:
        logger.error(f"Error generating signed URL for {url}: {str(e)}")
        return url  # Return original URL if signing fails


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


# If you're using a custom user model
CustomUser = get_user_model()


class SubjectNoteSerializer(serializers.ModelSerializer):
    pdf_media_key = serializers.SerializerMethodField()
    
    class Meta:
        model = SubjectNote
        fields = '__all__'
    
    def get_pdf_media_key(self, obj):
        """Return the media key for secure PDF access"""
        if obj.pdf:
            # Extract the key from the file path (remove leading 'media/' if present)
            key = str(obj.pdf.name)
            if key.startswith('media/'):
                key = key[6:]  # Remove 'media/' prefix
            return key
        return None


class SubjectRecordingVideoSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()
    
    class Meta:
        model = SubjectRecordingVideo
        fields = '__all__'
    
    def get_video_url(self, obj):
        """Convert R2 URLs to use Cloudflare Worker for secure access"""
        return convert_r2_url_to_worker_url(obj.video_url)


#######################################
#  User Serializer (for reference)
#######################################
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = '__all__'


#######################################
#  QrPaymentSerializer
#######################################
class QrPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = QrPayment
        fields = '__all__'


#######################################
#  "Leaf" Serializers
#  (lowest in the relationship tree)
#######################################
class MCQQuestionSerializer(serializers.ModelSerializer):
    question_image_url = serializers.SerializerMethodField()
    option_0_image_url = serializers.SerializerMethodField()
    option_1_image_url = serializers.SerializerMethodField()
    option_2_image_url = serializers.SerializerMethodField()
    option_3_image_url = serializers.SerializerMethodField()
    explanation_image_url = serializers.SerializerMethodField()

    class Meta:
        model = MCQQuestion
        fields = '__all__'

    def _clean_image_url(self, url):
        """
        Remove query parameters from signed URLs before saving to database.
        Strips everything after '?' to remove temporary signing parameters like:
        ?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...
        """
        if not url or url.lower() == 'nan':
            return None
        
        # Strip query parameters (everything after '?')
        url = url.split('?')[0]
        
        # Return empty string as None for consistency
        return url if url else None

    def validate_question_image_url(self, value):
        return self._clean_image_url(value)

    def validate_option_0_image_url(self, value):
        return self._clean_image_url(value)

    def validate_option_1_image_url(self, value):
        return self._clean_image_url(value)

    def validate_option_2_image_url(self, value):
        return self._clean_image_url(value)

    def validate_option_3_image_url(self, value):
        return self._clean_image_url(value)

    def validate_explanation_image_url(self, value):
        return self._clean_image_url(value)

    def get_question_image_url(self, obj):
        if obj.question_image_url and 'r2.aakhyaan.org' in obj.question_image_url:
            return convert_r2_url_to_worker_url(obj.question_image_url)
        return generate_signed_r2_url(obj.question_image_url)

    def get_option_0_image_url(self, obj):
        if obj.option_0_image_url and 'r2.aakhyaan.org' in obj.option_0_image_url:
            return convert_r2_url_to_worker_url(obj.option_0_image_url)
        return generate_signed_r2_url(obj.option_0_image_url)

    def get_option_1_image_url(self, obj):
        if obj.option_1_image_url and 'r2.aakhyaan.org' in obj.option_1_image_url:
            return convert_r2_url_to_worker_url(obj.option_1_image_url)
        return generate_signed_r2_url(obj.option_1_image_url)

    def get_option_2_image_url(self, obj):
        if obj.option_2_image_url and 'r2.aakhyaan.org' in obj.option_2_image_url:
            return convert_r2_url_to_worker_url(obj.option_2_image_url)
        return generate_signed_r2_url(obj.option_2_image_url)

    def get_option_3_image_url(self, obj):
        if obj.option_3_image_url and 'r2.aakhyaan.org' in obj.option_3_image_url:
            return convert_r2_url_to_worker_url(obj.option_3_image_url)
        return generate_signed_r2_url(obj.option_3_image_url)

    def get_explanation_image_url(self, obj):
        if obj.explanation_image_url and 'r2.aakhyaan.org' in obj.explanation_image_url:
            return convert_r2_url_to_worker_url(obj.explanation_image_url)
        return generate_signed_r2_url(obj.explanation_image_url)


class MockTestQuestionSerializer(serializers.ModelSerializer):
    question_image_url = serializers.SerializerMethodField()
    option_0_image_url = serializers.SerializerMethodField()
    option_1_image_url = serializers.SerializerMethodField()
    option_2_image_url = serializers.SerializerMethodField()
    option_3_image_url = serializers.SerializerMethodField()
    explanation_image_url = serializers.SerializerMethodField()

    class Meta:
        model = MockTestQuestion
        fields = '__all__'

    def _clean_image_url(self, url):
        """
        Remove query parameters from signed URLs before saving to database.
        Strips everything after '?' to remove temporary signing parameters like:
        ?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...
        """
        if not url or url.lower() == 'nan':
            return None
        
        # Strip query parameters (everything after '?')
        url = url.split('?')[0]
        
        # Return empty string as None for consistency
        return url if url else None

    def validate_question_image_url(self, value):
        return self._clean_image_url(value)

    def validate_option_0_image_url(self, value):
        return self._clean_image_url(value)

    def validate_option_1_image_url(self, value):
        return self._clean_image_url(value)

    def validate_option_2_image_url(self, value):
        return self._clean_image_url(value)

    def validate_option_3_image_url(self, value):
        return self._clean_image_url(value)

    def validate_explanation_image_url(self, value):
        return self._clean_image_url(value)

    def get_question_image_url(self, obj):
        logger.info("Converting URL: %s", obj.question_image_url)
        # First try worker URL, then fall back to signed URL
        if obj.question_image_url and 'r2.aakhyaan.org' in obj.question_image_url:
            return convert_r2_url_to_worker_url(obj.question_image_url)
        return generate_signed_r2_url(obj.question_image_url)

    def get_option_0_image_url(self, obj):
        if obj.option_0_image_url and 'r2.aakhyaan.org' in obj.option_0_image_url:
            return convert_r2_url_to_worker_url(obj.option_0_image_url)
        return generate_signed_r2_url(obj.option_0_image_url)

    def get_option_1_image_url(self, obj):
        if obj.option_1_image_url and 'r2.aakhyaan.org' in obj.option_1_image_url:
            return convert_r2_url_to_worker_url(obj.option_1_image_url)
        return generate_signed_r2_url(obj.option_1_image_url)

    def get_option_2_image_url(self, obj):
        if obj.option_2_image_url and 'r2.aakhyaan.org' in obj.option_2_image_url:
            return convert_r2_url_to_worker_url(obj.option_2_image_url)
        return generate_signed_r2_url(obj.option_2_image_url)

    def get_option_3_image_url(self, obj):
        if obj.option_3_image_url and 'r2.aakhyaan.org' in obj.option_3_image_url:
            return convert_r2_url_to_worker_url(obj.option_3_image_url)
        return generate_signed_r2_url(obj.option_3_image_url)

    def get_explanation_image_url(self, obj):
        if obj.explanation_image_url and 'r2.aakhyaan.org' in obj.explanation_image_url:
            return convert_r2_url_to_worker_url(obj.explanation_image_url)
        return generate_signed_r2_url(obj.explanation_image_url)


#######################################
#  Next level up: MCQ, MockTest, etc.
#######################################


class MCQSerializer(serializers.ModelSerializer):
    questions = MCQQuestionSerializer(many=True, required=False)

    class Meta:
        model = MCQ
        fields = '__all__'

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        mcq = MCQ.objects.create(**validated_data)
        for question_data in questions_data:
            MCQQuestion.objects.create(mcq=mcq, **question_data)
        return mcq

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        for question_data in questions_data:
            question_id = question_data.get('id', None)
            if question_id:
                try:
                    question = MCQQuestion.objects.get(id=question_id, mcq=instance)
                    for key, value in question_data.items():
                        setattr(question, key, value)
                    question.save()
                except MCQQuestion.DoesNotExist:
                    continue  # Optionally, handle this case
            else:
                MCQQuestion.objects.create(mcq=instance, **question_data)

        return instance

class MockTestSerializer(serializers.ModelSerializer):
    questions = MockTestQuestionSerializer(many=True, required=False)

    class Meta:
        model = MockTest
        fields = '__all__'

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        mock_test = MockTest.objects.create(**validated_data)
        for question_data in questions_data:
            MockTestQuestion.objects.create(mock_test=mock_test, **question_data)
        return mock_test

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        for question_data in questions_data:
            question_id = question_data.get('id', None)
            if question_id:
                question = MockTestQuestion.objects.get(id=question_id, mock_test=instance)
                for key, value in question_data.items():
                    setattr(question, key, value)
                question.save()
            else:
                MockTestQuestion.objects.create(mock_test=instance, **question_data)

        return instance


#######################################
#  Next level: Video, Content
#######################################

class VideoSerializer(serializers.ModelSerializer):
    thumbnail = serializers.SerializerMethodField()
    video_file = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = '__all__'

    def get_thumbnail(self, obj):
        request = self.context.get('request')
        if request and obj.thumbnail:
            return request.build_absolute_uri(obj.thumbnail.url)
        return None if not obj.thumbnail else obj.thumbnail.url

    def get_video_file(self, obj):
        request = self.context.get('request')
        if request and obj.video_file:
            return request.build_absolute_uri(obj.video_file.url)
        return None if not obj.video_file else obj.video_file.url

    def get_video_url(self, obj):
        """Convert R2 URLs to use Cloudflare Worker for secure access"""
        return convert_r2_url_to_worker_url(obj.video_url)


class ContentSerializer(serializers.ModelSerializer):
    pdf_media_key = serializers.SerializerMethodField()
    
    class Meta:
        model = Content
        fields = '__all__'
    
    def get_pdf_media_key(self, obj):
        """Return the media key for secure PDF access"""
        if obj.pdf:
            # Extract the key from the file path (remove leading 'media/' if present)
            key = str(obj.pdf.name)
            if key.startswith('media/'):
                key = key[6:]  # Remove 'media/' prefix
            return key
        return None


#######################################
#  Next level: Topic
#######################################

class TopicSerializer(serializers.ModelSerializer):
    # Nest related MCQs, Videos, and Contents
    mcqs = MCQSerializer(many=True, read_only=True)
    videos = VideoSerializer(many=True, read_only=True)
    contents = ContentSerializer(many=True, read_only=True)

    class Meta:
        model = Topic
        fields = '__all__'


#######################################
#  Next level: Chapter
#######################################

class ChapterSerializer(serializers.ModelSerializer):
    # Nest Topics
    topics = TopicSerializer(many=True, read_only=True)

    class Meta:
        model = Chapter
        fields = '__all__'


#######################################
#  Next level: Subject
#######################################

class LiveClassSerializer(serializers.ModelSerializer):
    # We can also display the host's info (CustomUser) if desired
    host = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.filter(user_type='teacher'))
    host_name = serializers.SerializerMethodField()

    class Meta:
        model = LiveClass
        fields = '__all__'

    def get_host_name(self, obj):
        # Assuming Program has a ForeignKey or ManyToOne relationship with Course
        return obj.host.username if obj.host else None

class SubjectSerializer(serializers.ModelSerializer):
    chapters = ChapterSerializer(many=True, read_only=True, source='subject_chapters')
    live_classes = LiveClassSerializer(many=True, read_only=True)
    subject_notes = SubjectNoteSerializer(many=True, read_only=True)
    subject_videos = SubjectRecordingVideoSerializer(many=True, read_only=True, source='subject_recording_videos')

    class Meta:
        model = Subject
        fields = '__all__'

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        return representation


#######################################
#  PaymentPicture 
#  (references Program, Course, Subject, User)
#######################################

class PaymentPictureSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    # Many-to-many with Subject
    subject = SubjectSerializer(many=True, read_only=True)

    # We'll reference Program and Course by ID or nest them if you prefer
    # If you want to nest them fully, uncomment lines below and comment out the PrimaryKeyRelatedFields
    program = serializers.PrimaryKeyRelatedField(read_only=True)
    course = serializers.PrimaryKeyRelatedField(read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)

    # Alternatively (fully nested, but be careful with circular references):
    # program = ProgramSerializer(read_only=True)
    # course = CourseSerializer(read_only=True)

    class Meta:
        model = PaymentPicture
        fields = '__all__'



#######################################
#  SubjectFee
#######################################

class SubjectFeeSerializer(serializers.ModelSerializer):
    # Program could be nested, or just shown as an ID
    program = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = SubjectFee
        fields = '__all__'


#######################################
#  Notes
#######################################

class NoteSerializer(serializers.ModelSerializer):
    pdf_media_key = serializers.SerializerMethodField()
    
    class Meta:
        model = Note
        fields = '__all__'
    
    def get_pdf_media_key(self, obj):
        """Return the media key for secure PDF access"""
        if obj.pdf:
            # Extract the key from the file path and ensure media/ prefix
            key = str(obj.pdf.name)
            if not key.startswith('media/'):
                key = f"media/{key}"
            return key
        return None


#######################################
#  Course
#######################################

class CourseSerializer(serializers.ModelSerializer):
    # Related name is 'subjects', 'mock_tests', etc.
    subjects = SubjectSerializer(many=True, read_only=True)
    # mock_tests = MockTestSerializer(many=True, read_only=True)
    # notes = NoteSerializer(many=True, read_only=True)
    # PaymentPictures referencing this course
    PaymentPicture = PaymentPictureSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = '__all__'
        

class SubjectsForCourseSerializer(serializers.ModelSerializer):
    live_classes = LiveClassSerializer(many=True, read_only=True)
    
    class Meta:
        model = Subject
        fields = ['id', 'name','live_classes']

#######################################
#  Program
#######################################

class NewSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name', ]

class ProgramSerializer(serializers.ModelSerializer):
    # courses = CourseSerializer(many=True, read_only=True)
    payment_picture = serializers.PrimaryKeyRelatedField(
        many=True, queryset=PaymentPicture.objects.all(), required=False
    )
    subjects = NewSubjectSerializer(many=True, read_only=True)
    subject_fees = serializers.StringRelatedField(many=True, read_only=True)
    

    class Meta:
        model = Program
        fields = [
            'id', 'name', 'description', 'price', 'thumbnail',
            'published', 'course', 'subject_fees', 'subjects', 
            'payment_picture', 'has_subjects', 'has_chapters', 
            'has_topics', 'has_chapterwise_tests', 
            'has_chapterwise_notes', 'has_chapterwise_videos',
            'has_mock_tests', 'has_live_classes',
            'has_recorded_lectures', 'has_discussions',
            'has_lecture_notes', 'end_date',
        ]
        

    def get_course_name(self, obj):
        # Assuming Program has a ForeignKey or ManyToOne relationship with Course
        return obj.course.name if obj.course else None


class SubjectsForCourseSerializer(serializers.ModelSerializer):
    live_classes = LiveClassSerializer(many=True, read_only=True)
    
    class Meta:
        model = Subject
        fields = ['id', 'name','live_classes']

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class McqResultSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(queryset=CustomUser.objects.all(), slug_field='username')
    mcq = serializers.SlugRelatedField(queryset=MCQ.objects.all(), slug_field='title')

    class Meta:
        model = McqResult
        fields = [
            'id', 'user', 'mcq', 'score', 'total_score',
            'correct_answers', 'wrong_answers', 'unattempted', 'time_taken',
            'completed_at', 'submissions_data'
        ]
        read_only_fields = ['completed_at']


class MockTestResultSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(queryset=CustomUser.objects.all(), slug_field='username')
    mock_test = serializers.PrimaryKeyRelatedField(
        queryset=MockTest.objects.all(),
        pk_field=serializers.IntegerField(min_value=1, required=True)
    )

    def validate_mock_test(self, value):
        if isinstance(value, str):
            try:
                mock_test_id = int(value)
                return MockTest.objects.get(id=mock_test_id)
            except (ValueError, MockTest.DoesNotExist):
                raise serializers.ValidationError("Invalid mock test ID")
        return value

    class Meta:
        model = MockTestResult
        fields = [
            'id', 
            'user', 
            'mock_test', 
            'score', 
            'total_score', 
            'correct_answers',
            'wrong_answers',
            'unattempted',
            'time_taken',
            'completed_at',
            'submissions_data'
        ]
        read_only_fields = ['completed_at']


class CoursesMockTestSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    class Meta:
        model = MockTest
        fields = '__all__'


class OnePGPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnePGPayment
        fields = [
            'id', 'user', 'program', 'merchant_txn_id', 'gateway_txn_id', 
            'process_id', 'amount', 'service_charge', 'total_amount', 
            'status', 'instrument_code', 'transaction_date', 'last_updated', 
            'remarks'
        ]
        read_only_fields = [
            'merchant_txn_id', 'gateway_txn_id', 'process_id', 
            'transaction_date', 'last_updated'
        ]


class CourseListSerializer(serializers.ModelSerializer):
    subjects = SubjectsForCourseSerializer(many=True, read_only=True)
    # mock_tests = MockTestSerializer(many=True, read_only=True)
    class Meta:
        model = Course
        fields = ['id', 'name', 'subjects']


class ProgramListSerializer(serializers.ModelSerializer):
    subject_fees = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = Program
        fields = ['id', 'name', 'description', 'thumbnail', 'subject_fees','published', 'price']
        # fields = '__all__'


class QrPaymentTransactionSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(slug_field='email', read_only=True)
    program = serializers.SlugRelatedField(slug_field='name', read_only=True)
    course = serializers.SlugRelatedField(slug_field='name', read_only=True)
    subjects = serializers.SlugRelatedField(many=True, slug_field='name', read_only=True)

    class Meta:
        model = QrPaymentTransaction
        fields = [
            'id', 'user', 'program', 'course', 'subjects', 'bill_number',
            'transaction_amount', 'status', 'transaction_date', 'last_updated'
        ]
        read_only_fields = [
            'bill_number', 'transaction_date', 'last_updated'
        ]


class NCHLPaymentSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(slug_field='email', read_only=True)
    program = serializers.PrimaryKeyRelatedField(read_only=True)
    course = serializers.PrimaryKeyRelatedField(read_only=True)
    subjects = serializers.SlugRelatedField(many=True, slug_field='name', read_only=True)

    class Meta:
        model = NCHLPayment
        fields = [
            'id', 'user', 'program', 'course', 'subjects',
            'merchant_txn_id', 'gateway_txn_id', 'transaction_id',
            'amount', 'status', 'timestamp', 'last_updated', 'response_payload'
        ]
        read_only_fields = [
            'merchant_txn_id', 'gateway_txn_id', 'timestamp', 'last_updated', 'response_payload'
        ]