import base64
import hmac
import hashlib
import json
import logging
import os
import re
import string
import random
import time
import traceback
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from rest_framework import generics, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication

import jwt
import pandas as pd
import requests
import boto3
from botocore.client import Config as BotoConfig
from urllib.parse import quote

from accounts.models import CustomUser
from accounts.models import DeviceToken
from accounts.authentication import VersionedJWTAuthentication
from .models import (
    Chapter,
    Content,
    Course,
    LiveClass,
    MCQ,
    MCQQuestion,
    McqResult,
    MockTest,
    MockTestQuestion,
    MockTestResult,
    Note,
    OnePGPayment,
    Program,
    QrPayment,
    QrPaymentTransaction,
    PaymentPicture,
    Subject,
    SubjectFee,
    SubjectNote,
    SubjectRecordingVideo,
    Topic,
    Video,
    ZoomRecording,
    ZoomWebhookLog,
)

from .permissions import MockTestAccessPermission, NoteAccessPermission, LiveClassAccessPermission
from .serializers import (
    ChapterSerializer,
    ContentSerializer,
    CourseListSerializer,
    CourseSerializer,
    CoursesMockTestSerializer,
    FileUploadSerializer,
    LiveClassSerializer,
    MCQQuestionSerializer,
    MCQSerializer,
    McqResultSerializer,
    MockTestQuestionSerializer,
    MockTestResultSerializer,
    MockTestSerializer,
    NoteSerializer,
    OnePGPaymentSerializer,
    PaymentPictureSerializer,
    ProgramListSerializer,
    ProgramSerializer,
    QrPaymentSerializer,
    SubjectFeeSerializer,
    SubjectNoteSerializer,
    SubjectRecordingVideoSerializer,
    SubjectSerializer,
    TopicSerializer,
    UserSerializer,
    VideoSerializer,
    QrPaymentTransactionSerializer,
)

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.asymmetric import padding
import base64
import pandas as pd


def clean_image_url(url):
    """
    Remove query parameters from signed URLs before saving to database.
    Strips everything after '?' to remove temporary signing parameters like:
    ?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...
    
    This prevents storing temporary signed URLs that will expire.
    """
    if not url or pd.isna(url) or str(url).lower() == 'nan':
        return ''
    
    url = str(url).strip()
    # Strip query parameters (everything after '?')
    url = url.split('?')[0]
    
    return url if url else ''


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Ensure debug level logging is enabled

class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)



class TeacherUserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.filter(user_type='teacher')
    serializer_class = UserSerializer
    permission_classes = [AllowAny]


class QrPaymentViewSet(viewsets.ModelViewSet):
    queryset = QrPayment.objects.all()
    serializer_class = QrPaymentSerializer
    permission_classes = [AllowAny]


##########################################
#  Program
##########################################
class ProgramViewSet(viewsets.ModelViewSet):
    queryset = Program.objects.all().select_related('course').prefetch_related('subjects', 'payment_picture')
    serializer_class = ProgramSerializer
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action == 'list':
            return ProgramListSerializer
        return ProgramSerializer

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def cleanup_expired(self, request):
        """
        Manual cleanup endpoint for expired programs
        Removes user enrollments from expired programs (programs themselves are preserved)
        """
        try:
            result = Program.cleanup_expired_programs()
            
            if result['total_programs_cleaned'] == 0:
                return Response({
                    'success': True,
                    'message': 'No expired programs found or no users to remove.',
                    'data': result
                }, status=status.HTTP_200_OK)
            
            return Response({
                'success': True,
                'message': f"Cleanup completed. {result['total_users_removed']} users removed from {result['total_programs_cleaned']} expired programs. Programs are preserved.",
                'data': result
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error during program cleanup: {str(e)}")
            return Response({
                'success': False,
                'message': 'An error occurred during cleanup.',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def check_expiry(self, request, pk=None):
        """
        Check if a specific program has expired
        """
        program = self.get_object()
        
        return Response({
            'program_id': program.id,
            'program_name': program.name,
            'end_date': program.end_date,
            'is_expired': program.is_expired(),
            'enrolled_users_count': program.users.count(),
            'participant_users_count': program.participant_users.count()
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def remove_expired_users(self, request, pk=None):
        """
        Manually remove users from a specific expired program
        The program itself is preserved, only user enrollments are removed
        """
        program = self.get_object()
        
        if not program.is_expired():
            return Response({
                'success': False,
                'message': 'Program has not expired yet.',
                'program_name': program.name,
                'end_date': program.end_date,
                'is_expired': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            removed_count = program.remove_all_expired_users()
            
            return Response({
                'success': True,
                'message': f"Removed {removed_count} users from expired program. Program is preserved.",
                'program_name': program.name,
                'program_id': program.id,
                'removed_users_count': removed_count,
                'note': 'Program structure and content remain intact'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error removing users from program {program.id}: {str(e)}")
            return Response({
                'success': False,
                'message': 'An error occurred while removing users.',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

##############################F############
#  SubjectFee
##########################################
class SubjectFeeViewSet(viewsets.ModelViewSet):
    queryset = SubjectFee.objects.all()
    serializer_class = SubjectFeeSerializer
    permission_classes = [IsAuthenticated]


##########################################
#  Course
##########################################d
class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        return CourseSerializer
    



##########################################
#  Subject
##########################################
class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [AllowAny]


##########################################
#  Chapter
##########################################
class ChapterViewSet(viewsets.ModelViewSet):
    queryset = Chapter.objects.all()
    serializer_class = ChapterSerializer
    permission_classes = [AllowAny]


##########################################
#  Topic
##########################################
class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    permission_classes = [AllowAny]


##########################################
#  MCQ
##########################################
class MCQViewSet(viewsets.ModelViewSet):
    queryset = MCQ.objects.all()
    serializer_class = MCQSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            # Admin users can see all MCQs
            return MCQ.objects.all().prefetch_related('questions')
        
        # Regular users see MCQs based on existing logic
        return super().get_queryset()


##########################################
#  MCQQuestion
##########################################
class MCQQuestionViewSet(viewsets.ModelViewSet):
    queryset = MCQQuestion.objects.all()
    serializer_class = MCQQuestionSerializer
    permission_classes = [IsAuthenticated]


##########################################
#  Video
##########################################
class VideoViewSet(viewsets.ModelViewSet):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        """
        Override to pass request context to the serializer.
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

##########################################
#  Content
##########################################
class ContentViewSet(viewsets.ModelViewSet):
    queryset = Content.objects.all()
    serializer_class = ContentSerializer
    permission_classes = [IsAuthenticated]



##########################################
#  Live Class
##########################################

class LiveClassViewSet(viewsets.ModelViewSet):
    queryset = LiveClass.objects.all()
    serializer_class = LiveClassSerializer
    permission_classes = [IsAuthenticated, LiveClassAccessPermission]
    



class MockTestViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing MockTest instances.
    """
    queryset = MockTest.objects.all()  # Ensure this line is present
    serializer_class = MockTestSerializer
    permission_classes = [IsAuthenticated, MockTestAccessPermission]


    def get_queryset(self):
        user = self.request.user
        
        # Admin users can see all MockTests
        if user.is_staff or user.is_superuser:
            return MockTest.objects.all().prefetch_related('questions')
            
        # Users can see all free MockTests
        free_mocktests = MockTest.objects.filter(is_free=True)

        # Users can also see paid MockTests if they are enrolled in the course
        paid_mocktests = MockTest.objects.filter(
            is_free=False,
            course__in=user.courses.all()
        )

        return free_mocktests | paid_mocktests


##########################################
#  MockTestQuestion
##########################################
class MockTestQuestionViewSet(viewsets.ModelViewSet):
    queryset = MockTestQuestion.objects.all()
    serializer_class = MockTestQuestionSerializer
    permission_classes = [AllowAny]



class NoteViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing Note instances.
    """
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated, NoteAccessPermission]

    def get_queryset(self):
        user = self.request.user
        # Users can see all free Notes
        free_notes = Note.objects.filter(is_free=True)

        # Users can also see paid Notes if they are enrolled in the course
        paid_notes = Note.objects.filter(
            is_free=False,
            course__in=user.courses.all()
        )

        return free_notes | paid_notes


##########################################
#  Payment
##########################################
class PaymentPictureViewSet(viewsets.ModelViewSet):
    queryset = PaymentPicture.objects.all()
    serializer_class = PaymentPictureSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        """Filter payments to only show the current user's payments"""
        return PaymentPicture.objects.filter(user=self.request.user).order_by('-date')

    def create(self, request, *args, **kwargs):
        """Log incoming request and data"""
        logger.debug(f"Received POST request with Content-Type: {request.content_type}")
        logger.debug(f"Request data keys: {list(request.data.keys())}")
        logger.debug(f"User assigned: {self.request.user}")

        # Handling incoming data: program_id, course_id, subjects, payment_image, total_amount
        try:
            program_id = request.data.get('program_id')
            course_id = request.data.get('course_id')
            subjects = request.data.getlist('subjects')
            payment_image = request.FILES.get('payment_image')
            total_amount = request.data.get('total_amount')

            logger.debug(f"program_id: {program_id}")
            logger.debug(f"course_id: {course_id}")
            logger.debug(f"subjects: {subjects}")
            logger.debug(f"payment_image: {payment_image}")
            logger.debug(f"total_amount: {total_amount}")

            # Validation of required fields
            errors = {}
            if not program_id:
                errors['program_id'] = "Program ID is required."
            if not course_id:
                errors['course_id'] = "Course ID is required."
            if not payment_image:
                errors['payment_image'] = "Payment image is required."
            if not subjects:
                errors['subjects'] = "At least one subject must be selected."
            if not total_amount:
                errors['total_amount'] = "Total amount is required."

            if errors:
                logger.debug(f"Validation errors: {errors}")
                return Response({"detail": errors}, status=status.HTTP_400_BAD_REQUEST)

            # Retrieve objects using IDs
            try:
                program = Program.objects.get(id=program_id)
            except Program.DoesNotExist:
                logger.debug("Program does not exist.")
                return Response({"detail": "Program does not exist."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                course = Course.objects.get(id=course_id)
            except Course.DoesNotExist:
                logger.debug("Course does not exist.")
                return Response({"detail": "Course does not exist."}, status=status.HTTP_400_BAD_REQUEST)

            # Ensure the course belongs to the program
            if course.id != program.course.id:
                logger.debug("Course does not belong to the specified program.")
                return Response({"detail": "Course does not belong to the specified program."}, status=status.HTTP_400_BAD_REQUEST)

            user = request.user

            # Validate subjects belong to the course
            # valid_subject_ids = set(course.subjects.values_list('id', flat=True))
            # selected_subject_ids = set(subjects)
            # if not selected_subject_ids.issubset(valid_subject_ids):
            #     logger.debug("One or more selected subjects do not belong to the course.")
            #     return Response({"detail": "One or more selected subjects do not belong to the course."}, status=status.HTTP_400_BAD_REQUEST)

            # Validate total_amount is a valid number
            try:
                total_amount = float(total_amount)
            except ValueError:
                logger.debug("Total amount is not a valid number.")
                return Response({"detail": "Total amount must be a valid number."}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                validated_data = {
                    'program': program, 
                    'course': course,  
                    'user': user,  
                    'payment_image': payment_image,
                    'total_amount': total_amount,
                    'status': 'pending',  # Default status
                }

                # Create the PaymentPicture instance
                payment_picture = PaymentPicture.objects.create(**validated_data)

                # Associate subjects with the PaymentPicture instance
                payment_picture.subject.set(subjects)

            # Return a success response
            serializer = PaymentPictureSerializer(payment_picture)
            logger.debug(f"PaymentPicture created successfully: {serializer.data}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating PaymentPicture: {e}", exc_info=True)
            return Response({"detail": f"An error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MCQQuestionImportView(APIView):
    parser_classes = [MultiPartParser]
    
    def post(self, request, *args, **kwargs):
        serializer = FileUploadSerializer(data=request.data)
        if serializer.is_valid():
            file = serializer.validated_data['file']
            mcq_id = request.data.get('mcq_id')  # Get the mcq_id from the request

            if not mcq_id:
                return Response({"error": "MCQ ID is required."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                # Fetch the MCQ object based on the mcq_id
                try:
                    mcq = MCQ.objects.get(id=mcq_id)
                except MCQ.DoesNotExist:
                    return Response({"error": f"MCQ with id {mcq_id} not found."}, status=status.HTTP_400_BAD_REQUEST)

                # Read the file based on its extension
                if file.name.endswith('.csv'):
                    df = pd.read_csv(file)
                elif file.name.endswith('.xls') or file.name.endswith('.xlsx'):
                    df = pd.read_excel(file)
                elif file.name.endswith('.txt'):
                    df = pd.read_csv(file, delimiter='\t')
                else:
                    return Response({"error": "Unsupported file format"}, status=status.HTTP_400_BAD_REQUEST)

                # Check if the required columns are present in the file
                required_columns = ['question', 'answer']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    return Response({"error": f"Missing columns: {', '.join(missing_columns)}"}, status=status.HTTP_400_BAD_REQUEST)

                mcq_questions = []  # List to hold MCQQuestion instances for bulk insert

                # Iterate over the DataFrame and create MCQQuestion instances
                for index, row in df.iterrows():
                    mcq_question = MCQQuestion(
                        mcq=mcq,  # Use the fetched MCQ object
                        question_text=row['question'],
                        question_image_url=clean_image_url(row.get('questionImage', '')),
                        option_0_text=row.get('options.0.text', ''),
                        option_1_text=row.get('options.1.text', ''),
                        option_2_text=row.get('options.2.text', ''),
                        option_3_text=row.get('options.3.text', ''),
                        option_0_image_url=clean_image_url(row.get('options.0.image', '')),
                        option_1_image_url=clean_image_url(row.get('options.1.image', '')),
                        option_2_image_url=clean_image_url(row.get('options.2.image', '')),
                        option_3_image_url=clean_image_url(row.get('options.3.image', '')),
                        answer=row['answer'],
                        weight=row['weight'],
                        explanation=row.get('explanation', ''),
                        explanation_image_url=clean_image_url(row.get('explanationimage', ''))
                    )
                    mcq_questions.append(mcq_question)

                # Bulk create MCQQuestion instances
                if mcq_questions:
                    MCQQuestion.objects.bulk_create(mcq_questions)

                return Response({"success": "Data imported successfully"}, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MCQCreateView(generics.CreateAPIView):
    queryset = MCQ.objects.all()
    serializer_class = MCQSerializer
    permission_classes = [AllowAny]  # Allows all users to access this view

class MCQListView(generics.ListAPIView):
    queryset = MCQ.objects.all()
    serializer_class = MCQSerializer

    def get_queryset(self):
        topic_id = self.request.query_params.get('topic', None)
        if topic_id:
            return self.queryset.filter(topic_id=topic_id)
        return self.queryset

class MockTestCreateView(generics.CreateAPIView):
    queryset = MockTest.objects.all()
    serializer_class = MockTestSerializer

class MockTestListView(generics.ListAPIView):
    queryset = MockTest.objects.all()
    serializer_class = MockTestSerializer

    def get_queryset(self):
        course_id = self.request.query_params.get('course', None)
        if course_id:
            return self.queryset.filter(course_id=course_id)
        return self.queryset

class MockTestImportView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        mock_test_id = request.data.get('mock_test_id')

        if not file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
        if not mock_test_id:
            return Response({"error": "No mock_test_id provided"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mock_test = MockTest.objects.get(id=mock_test_id)
        except MockTest.DoesNotExist:
            return Response({"error": "Mock Test not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            # Read the file based on its extension
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            elif file.name.endswith('.xls') or file.name.endswith('.xlsx'):
                df = pd.read_excel(file)
            elif file.name.endswith('.txt'):
                df = pd.read_csv(file, delimiter='\t')
            else:
                return Response({"error": "Unsupported file format"}, status=status.HTTP_400_BAD_REQUEST)

            # Expected columns in the file:
            # question, questionImage, options.0.text, options.1.text, options.2.text, options.3.text,
            # options.0.image, options.1.image, options.2.image, options.3.image,
            # answer, weight, explanation, explanationImage

            for index, row in df.iterrows():
                MockTestQuestion.objects.create(
                    mock_test=mock_test,
                    question_text=row['question'],
                    question_image_url=clean_image_url(row.get('questionImage', '')),
                    option_0_text=row.get('options.0.text', ''),
                    option_1_text=row.get('options.1.text', ''),
                    option_2_text=row.get('options.2.text', ''),
                    option_3_text=row.get('options.3.text', ''),
                    option_0_image_url=clean_image_url(row.get('options.0.image', '')),
                    option_1_image_url=clean_image_url(row.get('options.1.image', '')),
                    option_2_image_url=clean_image_url(row.get('options.2.image', '')),
                    option_3_image_url=clean_image_url(row.get('options.3.image', '')),
                    answer=row['answer'],
                    weight=row['weight'],
                    explanation=row.get('explanation', ''),
                    explanation_image_url=clean_image_url(row.get('explanationImage', ''))
                )

            return Response({"success": "Data imported successfully"}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_zoom_signature(request):
    """
    Generate Zoom Meeting SDK signature for joining meetings
    
    Expected POST body:
    {
        "meetingNumber": "string",
        "role": 0,  # 0 for participant, 1 for host
        "videoWebRtcMode": 1  # optional
    }
    
    Returns:
    {
        "signature": "jwt_signature_string"
    }
    """
    try:
        # Get data from POST request
        meeting_number = request.data.get("meetingNumber")
        role = int(request.data.get("role", 0))  # Default to 0 (participant)
        video_webrtc_mode = request.data.get("videoWebRtcMode", 1)  # Default to 1
        
        # Log incoming request
        logger.info(f"Received Zoom signature request - Meeting: {meeting_number}, Role: {role}, User: {request.user.id}")
        
        # Validate required fields
        if not meeting_number:
            return Response(
                {"error": "meetingNumber is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if the user is enrolled in the live class with this meeting number
        try:
            live_class = LiveClass.objects.select_related('subject').get(zoom_meeting_id=meeting_number)
            
            # Check if user is staff/superuser OR enrolled in the subject OR class is free
            is_authorized = (
                request.user.is_staff or 
                request.user.is_superuser or
                live_class.is_free or
                live_class.subject in request.user.subjects.all()
            )
            
            if not is_authorized:
                logger.warning(f"User {request.user.id} attempted to access live class {live_class.id} without enrollment")
                return Response(
                    {"error": "You are not enrolled in this live class"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            logger.info(f"User {request.user.id} authorized for live class {live_class.id}")
            
        except LiveClass.DoesNotExist:
            logger.error(f"Live class not found for meeting number: {meeting_number}")
            return Response(
                {"error": "Live class not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get Zoom credentials from settings
        ZOOM_API_SECRET = settings.ZOOM_API_SECRET
        ZOOM_API_KEY = settings.ZOOM_API_KEY
        
        if not ZOOM_API_KEY or not ZOOM_API_SECRET:
            logger.error("Zoom API credentials not configured")
            return Response(
                {"error": "Zoom API credentials not configured"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Create JWT payload for Zoom Meeting SDK
        current_time = int(time.time())
        payload = {
            "sdkKey": ZOOM_API_KEY,
            "mn": meeting_number,
            "role": role,
            "iat": current_time,
            "exp": current_time + 60 * 60,  # Token expires in 1 hour
            "appKey": ZOOM_API_KEY,
            "tokenExp": current_time + 60 * 60,
        }
        
        # Generate JWT signature
        signature = jwt.encode(payload, ZOOM_API_SECRET, algorithm="HS256")
        
        logger.info(f"Successfully generated Zoom signature for meeting {meeting_number}")
        
        return Response({"signature": signature})
    
    except ValueError as e:
        logger.error(f"Invalid data in signature request: {e}")
        return Response(
            {"error": "Invalid role value"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error generating Zoom signature: {e}")
        return Response(
            {"error": f"Failed to generate signature: {str(e)}"}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Keep the old function for backwards compatibility
def generate_signature(request):
    # Log incoming request
    logger.info(f"Received request with meeting_number={request.GET.get('meeting_number')} and role={request.GET.get('role')}")

    ZOOM_API_SECRET = settings.ZOOM_API_SECRET
    ZOOM_API_KEY = settings.ZOOM_API_KEY
    try:
        # Your logic to generate the Zoom signature
        meeting_number = request.GET.get("meeting_number")
        role = int(request.GET.get("role", 0))  # Default to 0 if role not provided


        payload = {
            "sdkKey": ZOOM_API_KEY,
            "mn": meeting_number,
            "role": role,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60 * 60,
            "appKey": ZOOM_API_KEY,
            "tokenExp": int(time.time()) + 60 * 60,
        }

        signature = jwt.encode(payload, ZOOM_API_SECRET, algorithm="HS256")
        logger.info(f"Generated Zoom signature for meeting {meeting_number}: {signature}")

        return JsonResponse({"signature": signature})
    
    except Exception as e:
        logger.error(f"Error generating signature: {e}")
        return JsonResponse({"error": str(e)}, status=500)

class McqResultViewSet(viewsets.ModelViewSet):
    queryset = McqResult.objects.all()
    serializer_class = McqResultSerializer
    permission_classes = [IsAuthenticated]  # You can customize permissions as per your need

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class MockTestResultViewSet(viewsets.ModelViewSet):
    queryset = MockTestResult.objects.all()
    serializer_class = MockTestResultSerializer
    permission_classes = [IsAuthenticated]  # You can customize permissions as per your need

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class FreeSubjectRecordingVideoViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Free Subject Recording Videos
    """
    queryset = SubjectRecordingVideo.objects.filter(is_free=True).order_by('created_at')
    serializer_class = SubjectRecordingVideoSerializer
    permission_classes = [AllowAny]

class FreeSubjectNoteViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Free Subject Notes
    """
    queryset = SubjectNote.objects.filter(is_free=True)
    serializer_class = SubjectNoteSerializer
    permission_classes = [AllowAny]


def getFreeSubjectRecordingVideos(request, program_id):
    """
    Endpoint to get all free subject recording videos
    """
    if not program_id:
        return JsonResponse({"error": "Program ID is required"}, status=400)
    
    # fetch all free subject recording videos in a program
    try:
        program = Program.objects.get(id=program_id)
    except Program.DoesNotExist:
        return JsonResponse({"error": "Program not found"}, status=404)
    
    # get subjects in the program
    subjects = program.subjects.all()
    
    if not subjects:
        return JsonResponse({"error": "No subjects found in this program"}, status=404)
    
    # filter videos that are free and belong to the subjects in the program
    videos = SubjectRecordingVideo.objects.filter(is_free=True, subject__in=subjects).order_by('created_at')
    
    
    serializer = SubjectRecordingVideoSerializer(videos, many=True)
    return JsonResponse(serializer.data, safe=False)

def getFreeSubjectNotes(request, program_id):
    """
    Endpoint to get all free subject notes
    """
    if not program_id:
        return JsonResponse({"error": "Program ID is required"}, status=400)
    
    # fetch all free subject notes in a program
    try:
        program = Program.objects.get(id=program_id)
    except Program.DoesNotExist:
        return JsonResponse({"error": "Program not found"}, status=404)
    
    # get subjects in the program
    subjects = program.subjects.all()
    
    if not subjects:
        return JsonResponse({"error": "No subjects found in this program"}, status=404)
    
    # filter notes that are free and belong to the subjects in the program
    notes = SubjectNote.objects.filter(is_free=True, subject__in=subjects).order_by('created_at')
    
    serializer = SubjectNoteSerializer(notes, many=True)
    return JsonResponse(serializer.data, safe=False)

CHUNK_SIZE = 8192  # 8KB

@login_required
def stream_video(request, video_id):
    video = get_object_or_404(Video, id=video_id, is_active=True)

    # if not video.user_can_access(request.user):
    #     return HttpResponseForbidden("You do not have access to this video.")

    video_path = video.video_file.path

    if not os.path.exists(video_path):
        return HttpResponseForbidden("Video file not found.")

    file_size = os.path.getsize(video_path)
    range_header = request.META.get('HTTP_RANGE', '').strip()
    range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)

    if range_match:
        first_byte, last_byte = range_match.groups()
        first_byte = int(first_byte)
        last_byte = int(last_byte) if last_byte else file_size - 1

        if last_byte >= file_size:
            last_byte = file_size - 1

        length = last_byte - first_byte + 1
        with open(video_path, 'rb') as f:
            f.seek(first_byte)
            data = f.read(length)

        response = HttpResponse(data, status=206, content_type='video/mp4')
        response['Content-Range'] = f'bytes {first_byte}-{last_byte}/{file_size}'
        response['Accept-Ranges'] = 'bytes'
        response['Content-Length'] = str(length)
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(video_path)}"'
        return response
    else:
        response = StreamingHttpResponse(open(video_path, 'rb'), content_type='video/mp4')
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(video_path)}"'
        return response

class SubjectRecordingVideoViewSet(viewsets.ModelViewSet):
    queryset = SubjectRecordingVideo.objects.all()
    serializer_class = SubjectRecordingVideoSerializer
    # only allow access to authenticated users
    permission_classes = [IsAuthenticated]  # Adjust this as needed

    def get_serializer_context(self):
        """
        Override to pass request context to the serializer.
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class SubjectNoteViewSet(viewsets.ModelViewSet):
    queryset = SubjectNote.objects.all()
    serializer_class = SubjectNoteSerializer
    permission_classes = [AllowAny]  # You can adjust this depending on your permission needs

    def get_serializer_context(self):
        """
        Override to pass request context to the serializer.
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


def test_aws_credentials(request):
    return JsonResponse({
        'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
        'aws_bucket': settings.AWS_STORAGE_BUCKET_NAME,
        'aws_region': settings.AWS_S3_REGION_NAME,
    })

class CoursesMockTestViewSet(viewsets.ModelViewSet):
    queryset = MockTest.objects.all()
    serializer_class = CoursesMockTestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return MockTest.objects.filter(course__in=user.courses.all())


class OnePGPaymentViewSet(viewsets.ModelViewSet):
    queryset = OnePGPayment.objects.all()
    serializer_class = OnePGPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return OnePGPayment.objects.all()
        return OnePGPayment.objects.filter(user=user)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_payment_instruments(request):
    """Get available payment instruments from OnePG"""
    try:
        url = f"{settings.ONEPG_API_BASE_URL}/GetPaymentInstrumentDetails"
        
        # Generate signature
        data = {
            "MerchantId": settings.ONEPG_MERCHANT_ID,
            "MerchantName": settings.ONEPG_MERCHANT_NAME,
        }
        
        # Sort keys alphabetically and concatenate values
        sorted_keys = sorted(data.keys())
        values = ''.join(str(data[key]) for key in sorted_keys)
        
        # Generate HMAC-SHA512 signature
        signature = hmac.new(
            settings.ONEPG_SECRET_KEY.encode(),
            values.encode(),
            hashlib.sha512
        ).hexdigest().lower()
        
        data['Signature'] = signature
        
        # Add Basic Auth header
        auth = base64.b64encode(
            f"{settings.ONEPG_API_USERNAME}:{settings.ONEPG_API_PASSWORD}".encode()
        ).decode()
        headers = {
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(url, json=data, headers=headers)
        return Response(response.json())
        
    except Exception as e:
        logger.error(f"Error in get_payment_instruments: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_service_charge(request):
    """Get service charge for the payment amount"""
    try:
        url = f"{settings.ONEPG_API_BASE_URL}/GetServiceCharge"
        
        data = {
            "MerchantId": settings.ONEPG_MERCHANT_ID,
            "MerchantName": settings.ONEPG_MERCHANT_NAME,
            "Amount": str(request.data.get('amount')),
            "InstrumentCode": request.data.get('instrument_code'),
        }
        
        # Generate signature
        sorted_keys = sorted(data.keys())
        values = ''.join(str(data[key]) for key in sorted_keys)
        signature = hmac.new(
            settings.ONEPG_SECRET_KEY.encode(),
            values.encode(),
            hashlib.sha512
        ).hexdigest().lower()
        
        data['Signature'] = signature
        
        # Add Basic Auth header
        auth = base64.b64encode(
            f"{settings.ONEPG_API_USERNAME}:{settings.ONEPG_API_PASSWORD}".encode()
        ).decode()
        headers = {
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(url, json=data, headers=headers)
        return Response(response.json())
        
    except Exception as e:
        logger.error(f"Error in get_service_charge: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_process_id(request):
    """Get process ID for payment transaction"""
    try:
        url = f"{settings.ONEPG_API_BASE_URL}/GetProcessId"
        
        # Log complete request data for debugging
        logger.info(f"Process ID request data: {request.data}")
        
        # Get program and validate it exists
        program_id = request.data.get('program_id')
        try:
            program = Program.objects.get(id=program_id)
        except Program.DoesNotExist:
            return Response(
                {'error': 'Program not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get course from program
        course = program.course
        if not course:
            return Response(
                {'error': 'Program has no associated course'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get selected subjects
        subject_ids = request.data.get('subject_ids', [])
        subjects = []
        if subject_ids:
            # Validate subjects belong to the program
            subjects = Subject.objects.filter(
                id__in=subject_ids,
                programs=program
            )
            if len(subjects) != len(subject_ids):
                return Response(
                    {'error': 'One or more subjects do not belong to the program'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Get merchant transaction id
        merchant_txn_id = request.data.get('merchant_txn_id', f"AAKHYAAN-{str(int(time.time()))}")
        
        # Get amount and ensure it's a string
        amount = request.data.get('amount')
        if amount is not None:
            # Make sure amount is a string
            amount = str(amount)
        
        # Get service charge and ensure it's a string
        service_charge = request.data.get('service_charge', 0)
        if service_charge is not None:
            # Make sure service_charge is a string
            service_charge = str(service_charge)

        # Create payment record
        payment = OnePGPayment.objects.create(
            user=request.user,
            program=program,
            course=course,
            amount=amount,
            service_charge=service_charge,
            instrument_code=request.data.get('instrument_code'),
            merchant_txn_id=merchant_txn_id
        )

        # Add subjects to payment if provided
        if subjects:
            payment.subjects.set(subjects)
        
        # Prepare data for OnePG API
        data = {
            "MerchantId": settings.ONEPG_MERCHANT_ID,
            "MerchantName": settings.ONEPG_MERCHANT_NAME,
            "Amount": amount,
            "MerchantTxnId": payment.merchant_txn_id,
        }
        
        # Log data for debugging
        logger.info(f"OnePG API request data: {data}")
        
        # Generate signature
        sorted_keys = sorted(data.keys())
        values = ''.join(str(data[key]) for key in sorted_keys)
        signature = hmac.new(
            settings.ONEPG_SECRET_KEY.encode(),
            values.encode(),
            hashlib.sha512
        ).hexdigest().lower()
        
        data['Signature'] = signature
        
        # Add Basic Auth header
        auth = base64.b64encode(
            f"{settings.ONEPG_API_USERNAME}:{settings.ONEPG_API_PASSWORD}".encode()
        ).decode()
        headers = {
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/json'
        }
        
        # Log request details
        logger.info(f"Making request to OnePG: {url}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Data: {data}")
        
        try:
            response = requests.post(url, json=data, headers=headers)
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response text: {response.text[:500]}...")
            
            response_data = response.json()
            
            if response_data.get('code') == '0':
                # Update payment record with process ID
                payment.process_id = response_data['data']['ProcessId']
                payment.save()
                
                # Add payment ID to response data
                response_data['data']['paymentId'] = payment.id
                
            return Response(response_data)
        except requests.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            return Response(
                {'error': f'Error connecting to payment gateway: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except ValueError as e:  # JSON decoding error
            logger.error(f"JSON decoding error: {str(e)}, Response: {response.text[:500]}")
            return Response(
                {'error': f'Invalid response from payment gateway: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        
    except Exception as e:
        logger.error(f"Error in get_process_id: {str(e)}")
        logger.error(traceback.format_exc())  # Log full traceback
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """Initiate payment and redirect to OnePG gateway"""
    try:
        payment_id = request.data.get('payment_id')
        merchant_txn_id = request.data.get('merchant_txn_id')
        success_url = request.data.get('success_url')
        failure_url = request.data.get('failure_url')
        
        # Get payment object
        payment = get_object_or_404(
            OnePGPayment,
            process_id=payment_id,
            merchant_txn_id=merchant_txn_id,
            user=request.user
        )
        
        if not payment.process_id:
            return Response(
                {'error': 'Invalid payment. Process ID is missing.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update payment with success/failure URLs
        payment.success_url = success_url
        payment.failure_url = failure_url
        payment.save()
        
        # Prepare form data for gateway
        form_data = {
            'MerchantId': settings.ONEPG_MERCHANT_ID,
            'MerchantName': settings.ONEPG_MERCHANT_NAME,
            'MerchantTxnId': payment.merchant_txn_id,
            'Amount': str(payment.amount),
            'ProcessId': payment.process_id,
            'InstrumentCode': payment.instrument_code,
            'TransactionRemarks': f'Payment for {payment.program.name}',
            'SuccessURL': success_url,
            'FailureURL': failure_url
        }
        
        # Generate signature
        sorted_keys = sorted(form_data.keys())
        values = ''.join(str(form_data[key]) for key in sorted_keys)
        signature = hmac.new(
            settings.ONEPG_SECRET_KEY.encode(),
            values.encode(),
            hashlib.sha512
        ).hexdigest().lower()
        
        form_data['Signature'] = signature
        
        # Return form data for frontend to submit
        return Response({
            'gateway_url': f"{settings.ONEPG_GATEWAY_URL}/Payment/Index",
            'form_data': form_data
        })
        
    except Exception as e:
        logger.error(f"Error in initiate_payment: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def payment_notification(request):
    """Handle payment notification from OnePG"""
    logger.info(f"Full payment notification received: {request.GET}")
    try:
        merchant_txn_id = request.GET.get('MerchantTxnId')
        gateway_txn_id = request.GET.get('GatewayTxnId')
        
        logger.info(f"Processing payment notification for merchant_txn_id: {merchant_txn_id}, gateway_txn_id: {gateway_txn_id}")
        
        if not merchant_txn_id or not gateway_txn_id:
            logger.error("Missing transaction IDs in payment notification")
            return Response("Invalid request", status=status.HTTP_400_BAD_REQUEST)
        
        # Get payment
        try:
            payment = OnePGPayment.objects.get(merchant_txn_id=merchant_txn_id)
            logger.info(f"Found payment record: ID={payment.id}, current_status={payment.status}, user={payment.user.email}")
        except OnePGPayment.DoesNotExist:
            logger.error(f"Payment not found: {merchant_txn_id}")
            return Response("Invalid transaction ID", status=status.HTTP_404_NOT_FOUND)
        
        # Prevent multiple notification hits
        if payment.status in ["success", "failed"]:
            logger.info(f"Notification already received for payment {payment.id} with status {payment.status}")
            return Response("already received", content_type="text/plain")

        # Update payment with gateway transaction ID
        payment.gateway_txn_id = gateway_txn_id
        logger.info(f"Updated gateway_txn_id for payment {payment.id}")

        # Check transaction status from OnePG
        url = f"{settings.ONEPG_API_BASE_URL}/CheckTransactionStatus"

        data = {
            "MerchantId": settings.ONEPG_MERCHANT_ID,
            "MerchantName": settings.ONEPG_MERCHANT_NAME,
            "MerchantTxnId": merchant_txn_id,
        }

        # Generate signature
        sorted_keys = sorted(data.keys())
        values = ''.join(str(data[key]) for key in sorted_keys)
        signature = hmac.new(
            settings.ONEPG_SECRET_KEY.encode(),
            values.encode(),
            hashlib.sha512
        ).hexdigest().lower()

        data['Signature'] = signature

        # Add Basic Auth header
        auth = base64.b64encode(
            f"{settings.ONEPG_API_USERNAME}:{settings.ONEPG_API_PASSWORD}".encode()
        ).decode()
        headers = {
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/json'
        }

        logger.info(f"Making OnePG status check request for payment {payment.id}")
        response = requests.post(url, json=data, headers=headers)
        response_data = response.json()

        logger.info(f"OnePG status check response for payment {payment.id}: {response_data}")

        if response_data.get('code') == '0':  # Success response from API
            status_data = response_data.get('data', {})
            payment_status = status_data.get('Status', '').lower()

            logger.info(f"Processing OnePG status '{payment_status}' for payment {payment.id}")

            if payment_status == 'success':
                try:
                    payment.status = 'success'  # Update payment status to success
                    logger.info(f"Updating payment {payment.id} to success status")

                    # Add user to program, course, and subjects
                    payment.user.programs.add(payment.program)
                    payment.user.courses.add(payment.course)
                    if payment.subjects.exists():
                        payment.user.subjects.add(*payment.subjects.all())
                    logger.info(f"Successfully enrolled user {payment.user.email} in program/course/subjects")

                    # Update payment amount
                    payment.total_amount = Decimal(status_data.get('Amount', 0)) + Decimal(status_data.get('ServiceCharge', 0))
                    payment.save()
                    logger.info(f"Successfully processed payment {payment.id}")

                except Exception as e:
                    logger.error(f"Error processing successful payment {payment.id}: {str(e)}", exc_info=True)
                    return Response("Error processing successful payment", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            elif payment_status == 'fail':
                payment.status = 'failed'
                payment.remarks = status_data.get('CbsMessage', 'Payment failed')
                logger.info(f"Payment {payment.id} failed: {payment.remarks}")
                payment.save()

            payment.total_amount = Decimal(status_data.get('Amount', 0)) + Decimal(status_data.get('ServiceCharge', 0))
            payment.save()

        return Response("received", content_type="text/plain")
        
    except Exception as e:
        logger.error(f"Error in payment_notification: {str(e)}", exc_info=True)
        return Response("Error processing notification", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def payment_response(request):
    """Handle payment response from OnePG"""
    logger.info(f"Payment response received - Method: {request.method}")
    
    try:
        # Handle both GET and POST methods
        if request.method == 'POST':
            merchant_txn_id = request.data.get('txnId')
            gateway_txn_id = request.data.get('gatewayTxn')
            logger.info(f"POST data received: txnId={merchant_txn_id}, gatewayTxn={gateway_txn_id}")
        else:  # GET method
            merchant_txn_id = request.GET.get('MerchantTxnId')
            gateway_txn_id = request.GET.get('GatewayTxnId')
            logger.info(f"GET data received: MerchantTxnId={merchant_txn_id}, GatewayTxnId={gateway_txn_id}")
        
        logger.info(f"Processing payment response for merchant_txn_id: {merchant_txn_id}, gateway_txn_id: {gateway_txn_id}")
        
        # Redirect to frontend success/failure page
        base_url = settings.FRONTEND_URL
        
        if not merchant_txn_id:
            logger.error("Missing merchant_txn_id in payment response")
            return redirect(f"{base_url}/payment/failed?reason=missing_id")
        
        try:
            payment = OnePGPayment.objects.get(merchant_txn_id=merchant_txn_id)
            logger.info(f"Found payment record: ID={payment.id}, current_status={payment.status}, user={payment.user.email}")
            
            # Update gateway transaction ID if provided
            if gateway_txn_id:
                payment.gateway_txn_id = gateway_txn_id
                payment.save()
                logger.info(f"Updated gateway_txn_id for payment {payment.id}")
            
        except OnePGPayment.DoesNotExist:
            logger.error(f"Payment not found: {merchant_txn_id}")
            return redirect(f"{base_url}/payment/failed?reason=invalid_id")
        
        if payment.status == 'success':
            logger.info(f"Payment {payment.id} is already successful, redirecting to success page")
            return redirect(f"{base_url}/payment/success?txn={merchant_txn_id}&gateway_txn={gateway_txn_id}")
        elif payment.status == 'failed':
            logger.info(f"Payment {payment.id} is already failed, redirecting to failure page")
            return redirect(f"{base_url}/payment/failed?reason=payment_failed&txn={merchant_txn_id}")
        else:
            # Check transaction status from OnePG
            url = f"{settings.ONEPG_API_BASE_URL}/CheckTransactionStatus"
            
            data = {
                "MerchantId": settings.ONEPG_MERCHANT_ID,
                "MerchantName": settings.ONEPG_MERCHANT_NAME,
                "MerchantTxnId": merchant_txn_id,
            }
            
            # Generate signature
            sorted_keys = sorted(data.keys())
            values = ''.join(str(data[key]) for key in sorted_keys)
            signature = hmac.new(
                settings.ONEPG_SECRET_KEY.encode(),
                values.encode(),
                hashlib.sha512
            ).hexdigest().lower()
            
            data['Signature'] = signature
            
            # Add Basic Auth header
            auth = base64.b64encode(
                f"{settings.ONEPG_API_USERNAME}:{settings.ONEPG_API_PASSWORD}".encode()
            ).decode()
            headers = {
                'Authorization': f'Basic {auth}',
                'Content-Type': 'application/json'
            }
            
            logger.info(f"Making OnePG status check request for payment {payment.id}")
            response = requests.post(url, json=data, headers=headers)
            response_data = response.json()
            
            logger.info(f"OnePG status check response for payment {payment.id}: {response_data}")
            
            if response_data.get('code') == '0':
                status_data = response_data.get('data', {})
                payment_status = status_data.get('Status', '').lower()
                
                logger.info(f"Processing OnePG status '{payment_status}' for payment {payment.id}")
                
                if payment_status == 'success':
                    try:
                        payment.status = 'success'
                        logger.info(f"Updating payment {payment.id} to success status")
                        
                        # Add user to program
                        payment.user.programs.add(payment.program)
                        logger.info(f"Added user {payment.user.email} to program {payment.program.name}")
                        
                        # Add user to course
                        payment.user.courses.add(payment.course)
                        logger.info(f"Added user {payment.user.email} to course {payment.course.name}")
                        
                        # Add user to subjects
                        if payment.subjects.exists():
                            subject_names = [s.name for s in payment.subjects.all()]
                            payment.user.subjects.add(*payment.subjects.all())
                            logger.info(f"Added user {payment.user.email} to subjects: {', '.join(subject_names)}")
                        
                        payment.total_amount = Decimal(status_data.get('Amount', 0)) + Decimal(status_data.get('ServiceCharge', 0))
                        logger.info(f"Updated total amount for payment {payment.id} to {payment.total_amount}")
                        
                        payment.save()
                        logger.info(f"Successfully saved payment {payment.id} with success status")
                        
                    except Exception as e:
                        logger.error(f"Error processing successful payment {payment.id}: {str(e)}", exc_info=True)
                        return redirect(f"{base_url}/payment/failed?reason=error&txn={merchant_txn_id}")
                        
                elif payment_status == 'fail':
                    payment.status = 'failed'
                    payment.remarks = status_data.get('CbsMessage', 'Payment failed')
                    logger.info(f"Payment {payment.id} failed: {payment.remarks}")
                    payment.save()
                    return redirect(f"{base_url}/payment/failed?reason=payment_failed&txn={merchant_txn_id}")
            
            logger.info(f"Payment {payment.id} is still pending")
            return redirect(f"{base_url}/payment/pending?txn={merchant_txn_id}&gateway_txn={gateway_txn_id}")
        
    except Exception as e:
        logger.error(f"Error in payment_response: {str(e)}", exc_info=True)
        return redirect(f"{settings.FRONTEND_URL}/payment/failed?reason=error")

@api_view(['GET'])
@permission_classes([AllowAny])
def check_payment_status(request, txn_id):
    """Check payment status by transaction ID"""
    logger.info(f"Payment status check request received for txn_id: {txn_id}")
    
    try:
        if not txn_id:
            logger.error("Missing txn_id in status check request")
            return Response({
                'status': 'error',
                'message': 'Transaction ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment = OnePGPayment.objects.get(merchant_txn_id=txn_id)
            logger.info(f"Found payment record: ID={payment.id}, status={payment.status}, user={payment.user.email}")
            
        except OnePGPayment.DoesNotExist:
            logger.error(f"Payment not found for txn_id: {txn_id}")
            return Response({
                'status': 'error',
                'message': 'Invalid transaction ID'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # If payment is already in a final state, return immediately
        if payment.status in ['success', 'failed']:
            logger.info(f"Payment {payment.id} is in final state: {payment.status}")
            return Response({
                'status': payment.status,
                'message': 'Payment status retrieved',
                'gateway_txn_id': payment.gateway_txn_id
            })
        
        # Check transaction status from OnePG
        url = f"{settings.ONEPG_API_BASE_URL}/CheckTransactionStatus"
        
        data = {
            "MerchantId": settings.ONEPG_MERCHANT_ID,
            "MerchantName": settings.ONEPG_MERCHANT_NAME,
            "MerchantTxnId": txn_id,
        }
        
        # Generate signature
        sorted_keys = sorted(data.keys())
        values = ''.join(str(data[key]) for key in sorted_keys)
        signature = hmac.new(
            settings.ONEPG_SECRET_KEY.encode(),
            values.encode(),
            hashlib.sha512
        ).hexdigest().lower()
        
        data['Signature'] = signature
        
        # Add Basic Auth header
        auth = base64.b64encode(
            f"{settings.ONEPG_API_USERNAME}:{settings.ONEPG_API_PASSWORD}".encode()
        ).decode()
        headers = {
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"Making OnePG status check request for payment {payment.id}")
        response = requests.post(url, json=data, headers=headers)
        response_data = response.json()
        
        logger.info(f"OnePG status check response for payment {payment.id}: {response_data}")
        
        if response_data.get('code') == '0':
            status_data = response_data.get('data', {})
            payment_status = status_data.get('Status', '').lower()
            
            logger.info(f"Processing OnePG status '{payment_status}' for payment {payment.id}")
            
            if payment_status == 'success':
                try:
                    payment.status = 'success'
                    logger.info(f"Updating payment {payment.id} to success status")
                    
                    # Add user to program
                    payment.user.programs.add(payment.program)
                    logger.info(f"Added user {payment.user.email} to program {payment.program.name}")
                    
                    # Add user to course
                    payment.user.courses.add(payment.course)
                    logger.info(f"Added user {payment.user.email} to course {payment.course.name}")
                    
                    # Add user to subjects
                    if payment.subjects.exists():
                        subject_names = [s.name for s in payment.subjects.all()]
                        payment.user.subjects.add(*payment.subjects.all())
                        logger.info(f"Added user {payment.user.email} to subjects: {', '.join(subject_names)}")
                    
                    payment.total_amount = Decimal(status_data.get('Amount', 0)) + Decimal(status_data.get('ServiceCharge', 0))
                    logger.info(f"Updated total amount for payment {payment.id} to {payment.total_amount}")
                    
                    payment.save()
                    logger.info(f"Successfully saved payment {payment.id} with success status")
                    
                except Exception as e:
                    logger.error(f"Error processing successful payment {payment.id}: {str(e)}", exc_info=True)
                    return Response({
                        'status': 'error',
                        'message': 'Error processing payment'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
            elif payment_status == 'fail':
                payment.status = 'failed'
                payment.remarks = status_data.get('CbsMessage', 'Payment failed')
                logger.info(f"Payment {payment.id} failed: {payment.remarks}")
                payment.save()
        
        return Response({
            'status': payment.status,
            'message': 'Payment status retrieved',
            'gateway_txn_id': payment.gateway_txn_id
        })
        
    except Exception as e:
        logger.error(f"Error in check_payment_status: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Error checking payment status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def generate_qr(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)

    # Get optional values from request with defaults
    transaction_amount_str = data.get('transactionAmount', '0.00')
    program_id = data.get('program_id')
    course_id = data.get('course_id')
    subject_ids = data.get('subject_ids', [])

    try:
        transaction_amount = Decimal(transaction_amount_str)
    except ValueError:
        return JsonResponse({'error': 'Invalid transaction amount'}, status=status.HTTP_400_BAD_REQUEST)

    if not program_id or not course_id:
        return JsonResponse({'error': 'Program ID and Course ID are required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        program = Program.objects.get(id=program_id)
        course = Course.objects.get(id=course_id)
        subjects = Subject.objects.filter(id__in=subject_ids) if subject_ids else []
    except (Program.DoesNotExist, Course.DoesNotExist, Subject.DoesNotExist) as e:
        return JsonResponse({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    # Generate a unique bill number
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5)) # 5 chars for max 25 total
    generated_bill_number = f"QR{timestamp}{random_suffix}"
    # Ensure bill_number is exactly 25 characters, truncate if longer
    if len(generated_bill_number) > 25:
        generated_bill_number = generated_bill_number[:25]

    # Create a QrPaymentTransaction record
    try:
        qr_transaction = QrPaymentTransaction.objects.create(
            user=request.user,
            program=program,
            course=course,
            bill_number=generated_bill_number,
            transaction_amount=transaction_amount,
            status='pending',
        )
        if subjects:
            qr_transaction.subjects.set(subjects)
    except Exception as e:
        logger.error(f"Error creating QrPaymentTransaction: {e}")
        return JsonResponse({'error': 'Failed to record QR payment transaction.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Load fixed values from environment
    point_of_initialization = 12
    acquirer_id = settings.NPQR_ACQUIRER_ID
    merchant_id = settings.NPQR_MERCHANT_ID
    merchant_name = settings.NPQR_MERCHANT_NAME
    merchant_category_code = settings.NPQR_MERCHANT_CATEGORY_CODE
    merchant_country = settings.NPQR_MERCHANT_COUNTRY
    merchant_city = settings.NPQR_MERCHANT_CITY
    merchant_postal_code = settings.NPQR_MERCHANT_POSTAL_CODE
    merchant_language = settings.NPQR_MERCHANT_LANGUAGE
    transaction_currency = settings.NPQR_TRANSACTION_CURRENCY
    if not all([point_of_initialization, acquirer_id, merchant_id, merchant_name,
                merchant_category_code, merchant_country, merchant_city,
                merchant_postal_code, merchant_language, transaction_currency]):
        return JsonResponse({'error': 'Missing required configuration values'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Get optional values from request with defaults
    value_of_convenience_fee_fixed = data.get('valueOfConvenienceFeeFixed', '0.00')
    store_label = data.get('storeLabel', '')
    terminal_label = data.get('terminalLabel', '')
    purpose_of_transaction = data.get('purposeOfTransaction', '')

    # Generate token string for dynamic QR
    user_id = settings.NPQR_USER_ID  # Provided by NPI to merchant
    token_string = f"{acquirer_id},{merchant_id},{merchant_category_code},{transaction_currency},{transaction_amount_str},{generated_bill_number},{user_id}"
    with open(settings.NPI_PFX_FILE, "rb") as f:
        pfx_data = f.read()

    # Load the private key from the PFX file
    private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(pfx_data, b"aAkhY@N@c@d3mY")

    signature = private_key.sign(
        token_string.encode(),
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    # Base64 encode the result (this is the token)
    token = base64.b64encode(signature).decode()
    # Construct payload
    payload = {
        "pointOfInitialization": point_of_initialization,
        "acquirerId": acquirer_id,
        "merchantId": merchant_id,
        "merchantName": merchant_name,
        "merchantCategoryCode": merchant_category_code,
        "merchantCountry": merchant_country,
        "merchantCity": merchant_city,
        "merchantPostalCode": merchant_postal_code,
        "merchantLanguage": merchant_language,
        "transactionCurrency": transaction_currency,
        "transactionAmount": transaction_amount_str,
        "valueOfConvenienceFeeFixed": value_of_convenience_fee_fixed,
        "billNumber": generated_bill_number,
        "storeLabel": store_label,
        "terminalLabel": terminal_label,
        "purposeOfTransaction": purpose_of_transaction,
        "token": token
    }

    # Authentication
    username = settings.NPQR_API_USERNAME
    password = settings.NPQR_API_PASSWORD
    if not username or not password:
        return JsonResponse({'error': 'API credentials not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {auth_string}'
    }

    # Make API call
    
    api_url = settings.NPQR_API_BASE_URL + '/qr/generateQR'
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        # response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        return JsonResponse({'error': f'API request failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    response_data = response.json()
    if response_data.get('responseCode') == '000':
        response_data['data']['billNumber'] = generated_bill_number
        return JsonResponse(response_data['data'], status=status.HTTP_200_OK)
    return JsonResponse(response_data, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_qr_payment(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
    bill_number = data.get('billNumber')
    validation_trace_id = data.get('validationTraceId')
    if not bill_number:
        return JsonResponse({'error': 'Bill Number is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        qr_transaction = QrPaymentTransaction.objects.get(bill_number=bill_number)
    except QrPaymentTransaction.DoesNotExist:
        logger.error(f"QrPaymentTransaction with bill_number {bill_number} not found.")
        return JsonResponse({'error': 'Invalid Bill Number.'}, status=status.HTTP_404_NOT_FOUND)

    # Set up authentication headers
    auth_string = base64.b64encode(f"{settings.NPQR_API_USERNAME}:{settings.NPQR_API_PASSWORD}".encode()).decode()
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {auth_string}'
    }
    
    # Make API call to verify transaction status with external gateway
    api_url = f"{settings.NPQR_API_BASE_URL}/nQR/v1/merchanttxnreport"
    payload = {
        "validationTraceId": validation_trace_id,
        "billNumber": bill_number,
        "merchantId": settings.NPQR_MERCHANT_ID,
        "merchantTxnId": bill_number, # Assuming merchantTxnId is the same as billNumber for verification
        "uniqueId": settings.NPQR_USER_ID, # Assuming this is required for verification
        "acquirerId": settings.NPQR_ACQUIRER_ID,
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        # response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"API request failed during QR verification: {e}")
        return JsonResponse({'error': f'API request failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    response_data = response.json()
    logger.info(f"QR verification response for bill_number {bill_number}: {response_data}")
    # Update QrPaymentTransaction status based on external API response
    if response_data.get('responseCode') == '200':
        if response_data and response_data.get('responseStatus') == 'SUCCESS':
            qr_transaction.status = 'success'
            qr_transaction.save()
            return JsonResponse({'status_code': '000', 'message': 'Payment successful.'}, status=status.HTTP_200_OK)
        else:
            # Payment might be pending or failed
            qr_transaction.status = 'pending' # or 'failed' if there's a clear failure status
            qr_transaction.save()
            return JsonResponse({'status_code': response_data.get('responseCode'), 'message': response_data.get('responseDescription','Payment still pending or failed.')}, status=status.HTTP_200_OK)
    else:
        qr_transaction.status = 'failed' # Assuming any non-000 response code from external API means failure
        qr_transaction.save()
        return JsonResponse({'status_code': response_data.get('responseCode'), 'message': response_data.get('responseDescription', 'Payment failed or invalid response from gateway.')}, status=status.HTTP_400_BAD_REQUEST)

# ==========================
# Direct-to-R2 Multipart Upload
# ==========================

def _r2_s3_client():
    """Create an S3 client configured for Cloudflare R2 using settings."""
    return boto3.client(
        's3',
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        endpoint_url=settings.R2_ENDPOINT_URL,
        region_name='auto',
        config=BotoConfig(s3={'addressing_style': 'path'})
    )

def _object_key_from_request(request):
    key = request.data.get('key') or request.query_params.get('key')
    if not key:
        raise ValueError('Missing key')
    # prevent directory traversal
    key = key.lstrip('/')
    return f"media/{key}" if not key.startswith('media/') else key

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def initiate_multipart_upload(request):
    """
    Body: { key: string, contentType?: string, acl?: string }
    Returns: { uploadId, key }
    """
    try:
        key = _object_key_from_request(request)
        content_type = request.data.get('contentType')
        s3 = _r2_s3_client()
        extra = {}
        if content_type:
            extra['ContentType'] = content_type
        # initiate
        resp = s3.create_multipart_upload(
            Bucket=settings.R2_STORAGE_BUCKET_NAME,
            Key=key,
            **extra
        )
        return Response({
            'uploadId': resp['UploadId'],
            'key': key,
        })
    except Exception as e:
        logger.exception('initiate_multipart_upload failed')
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def sign_multipart_upload_part(request):
    """
    Body: { key, uploadId, partNumber, contentLength?(optional) }
    Returns: { url, headers }
    Use presigned URL for PUT of this part.
    """
    try:
        key = _object_key_from_request(request)
        upload_id = request.data.get('uploadId')
        part_number = int(request.data.get('partNumber', '0'))
        if not upload_id or part_number <= 0:
            return Response({'error': 'uploadId and valid partNumber required'}, status=400)
        s3 = _r2_s3_client()
        url = s3.generate_presigned_url(
            'upload_part',
            Params={
                'Bucket': settings.R2_STORAGE_BUCKET_NAME,
                'Key': key,
                'UploadId': upload_id,
                'PartNumber': part_number,
            },
            ExpiresIn=3600,
        )
        return Response({'url': url, 'headers': {}})
    except Exception as e:
        logger.exception('sign_multipart_upload_part failed')
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def complete_multipart_upload(request):
    """
    Body: { key, uploadId, parts: [{ETag, PartNumber}] }
    Returns: { location, key, bucket }
    """
    try:
        key = _object_key_from_request(request)
        upload_id = request.data.get('uploadId')
        raw_parts = request.data.get('parts') or []
        if not upload_id:
            return Response({'error': 'uploadId required'}, status=400)

        s3 = _r2_s3_client()

        # Normalize client-provided parts if present
        parts = []
        missing_etag = False
        for p in raw_parts:
            part_num = int(p.get('PartNumber') or p.get('partNumber') or 0)
            etag = p.get('ETag') or p.get('etag')
            if part_num <= 0:
                continue
            if not etag or etag.startswith('"etag-'):  # Check for fake ETags too
                missing_etag = True
            else:
                # Clean and store the ETag
                clean_etag = str(etag).strip().strip('"')
                if clean_etag:  # Only add if we have a real ETag
                    parts.append({'ETag': f'"{clean_etag}"', 'PartNumber': part_num})

        # If any ETag is missing/fake or parts list is incomplete, fetch from R2
        if missing_etag or not parts or len(parts) != len(raw_parts):
            logger.info(f'Using list_parts fallback for uploadId {upload_id}, missing_etag={missing_etag}, parts_count={len(parts)}, raw_parts_count={len(raw_parts)}')
            listed = s3.list_parts(Bucket=settings.R2_STORAGE_BUCKET_NAME, Key=key, UploadId=upload_id)
            listed_parts = listed.get('Parts', [])
            if not listed_parts:
                return Response({'error': 'No parts found for this uploadId/key'}, status=400)
            parts = [{'ETag': p.get('ETag', ''), 'PartNumber': int(p['PartNumber'])} for p in listed_parts]

        # Ensure correct sorting
        parts.sort(key=lambda p: p['PartNumber'])

        resp = s3.complete_multipart_upload(
            Bucket=settings.R2_STORAGE_BUCKET_NAME,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts},
        )

        # Build a public URL if custom domain exists, otherwise the R2 endpoint URL
        if settings.R2_CUSTOM_DOMAIN:
            location = f"{settings.R2_CUSTOM_DOMAIN}/{quote(key)}"
        else:
            # raw R2 path style may be endpoint/bucket/key
            base = settings.R2_ENDPOINT_URL.rstrip('/')
            location = f"{base}/{settings.R2_STORAGE_BUCKET_NAME}/{quote(key)}"

        return Response({
            'location': location,
            'key': key,
            'bucket': settings.R2_STORAGE_BUCKET_NAME,
        })
    except Exception as e:
        logger.exception('complete_multipart_upload failed')
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def abort_multipart_upload(request):
    """
    Body: { key, uploadId }
    """
    try:
        key = _object_key_from_request(request)
        upload_id = request.data.get('uploadId')
        if not upload_id:
            return Response({'error': 'uploadId required'}, status=400)
        s3 = _r2_s3_client()
        s3.abort_multipart_upload(
            Bucket=settings.R2_STORAGE_BUCKET_NAME,
            Key=key,
            UploadId=upload_id,
        )
        return Response({'aborted': True})
    except Exception as e:
        logger.exception('abort_multipart_upload failed')
        return Response({'error': str(e)}, status=500)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def admin_video_upload(request):
    """
    Admin endpoint to upload videos and create SubjectRecordingVideo entries.
    
    GET: Returns subjects list and upload form
    POST: Creates a new SubjectRecordingVideo with uploaded video
    
    Body for POST: {
        subject_id: required,
        title: required,
        video_description: optional,
        is_free: optional (default: false),
        is_active: optional (default: true),
        video_url: required (URL from completed multipart upload)
    }
    """
    if not request.user.is_staff:
        return Response({'error': 'Staff access required'}, status=403)
    
    if request.method == 'GET':
        # Check if this is an API request via AJAX call or explicit JSON request
        accept_header = request.headers.get('Accept', '')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        content_type = request.headers.get('Content-Type', '')
        
        # If it's an AJAX request or explicitly asks for JSON, return JSON
        if is_ajax or 'application/json' in accept_header or 'application/json' in content_type:
            subjects = Subject.objects.select_related('course').all()
            subjects_data = [
                {
                    'id': subject.id,
                    'name': subject.name,
                    'course_name': subject.course.name,
                    'display_name': f"{subject.name} - {subject.course.name}"
                }
                for subject in subjects
            ]
            return Response({
                'subjects': subjects_data,
                'message': 'Use POST to create a new SubjectRecordingVideo'
            })
        else:
            # Return HTML page for browser requests
            return render(request, 'admin_video_upload.html')
    
    elif request.method == 'POST':
        try:
            # Validate required fields
            subject_id = request.data.get('subject_id')
            title = request.data.get('title')
            video_url = request.data.get('video_url')
            
            if not subject_id:
                return Response({'error': 'subject_id is required'}, status=400)
            if not title:
                return Response({'error': 'title is required'}, status=400)
            if not video_url:
                return Response({'error': 'video_url is required'}, status=400)
            
            # Validate subject exists
            try:
                subject = Subject.objects.get(id=subject_id)
            except Subject.DoesNotExist:
                return Response({'error': f'Subject with id {subject_id} not found'}, status=400)
            
            # Create the SubjectRecordingVideo
            video_data = {
                'subject': subject,
                'title': title,
                'video_url': video_url,
                'video_description': request.data.get('video_description', ''),
                'is_free': request.data.get('is_free', False),
                'is_active': request.data.get('is_active', True),
            }
            
            video = SubjectRecordingVideo.objects.create(**video_data)
            
            # Return the created video data
            return Response({
                'success': True,
                'video': {
                    'id': video.id,
                    'title': video.title,
                    'video_url': video.video_url,
                    'subject_name': video.subject.name,
                    'course_name': video.subject.course.name,
                    'is_free': video.is_free,
                    'is_active': video.is_active,
                    'created_at': video.created_at.isoformat(),
                }
            }, status=201)
            
        except Exception as e:
            logger.exception('admin_video_upload failed')
            return Response({'error': str(e)}, status=500)


def admin_video_upload_page(request):
    """
    Admin page to upload videos and create SubjectRecordingVideo entries.
    Serves the HTML interface for browser-based uploads.
    """
    if not request.user.is_authenticated or not request.user.is_staff:
        return HttpResponseForbidden('Staff access required')
    return render(request, 'admin_video_upload.html')


def multipart_test_page(request):
    """Simple staff-only page to test multipart uploads in browser."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return HttpResponseForbidden('Forbidden')
    return render(request, 'r2_multipart_test.html')


def test_widget_page(request):
    """Test page for the widget with detailed console logging."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return HttpResponseForbidden('Forbidden')
    return render(request, 'test_widget.html')


# Zoom Recording Management Views

@api_view(['POST'])
@permission_classes([AllowAny])
def zoom_webhook(request):
    """
    Webhook endpoint for Zoom to notify about recording events
    """
    from .models import ZoomWebhookLog
    from .zoom_service import ZoomRecordingService
    import hmac
    import hashlib
    
    try:
        # Verify webhook (optional, but recommended for production)
        if not _verify_zoom_webhook(request):
            logger.warning("Invalid Zoom webhook signature")
            return Response({'error': 'Invalid signature'}, status=400)
        
        payload = request.data
        event_type = payload.get('event')
        
        # Handle webhook validation challenge (for simple challenge-response)
        if 'challenge' in payload and not event_type:
            logger.info("Received Zoom webhook validation challenge")
            challenge = payload.get('challenge')
            return Response({
                'challenge': challenge
            }, status=200)
        
        # Handle URL validation
        if event_type == 'endpoint.url_validation':
            plain_token = payload['payload']['plainToken']
            encrypted_token = hmac.new(
                settings.ZOOM_S2S_SECRET_TOKEN.encode('utf-8'),
                plain_token.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            response = {
                'plainToken': plain_token,
                'encryptedToken': encrypted_token
            }
            return Response(response, status=200)
        
        # Extract host email from webhook payload
        host_email = payload.get('payload', {}).get('object', {}).get('host_email', '')
        
        # Log the webhook
        webhook_log = ZoomWebhookLog.objects.create(
            event_type=event_type,
            meeting_id=payload.get('payload', {}).get('object', {}).get('id', ''),
            host_email=host_email,
            payload=payload,
            processed=False
        )
        
        logger.info(f"Received Zoom webhook: {event_type} from host: {host_email}")
        
        # Process recording completed events
        if event_type == 'recording.completed':
            try:
                zoom_service = ZoomRecordingService()
                zoom_recording = zoom_service.sync_recordings_from_webhook(payload)
                
                if zoom_recording:
                    # Process the recording asynchronously (you may want to use Celery for this)
                    zoom_service.process_recording(zoom_recording)
                    webhook_log.processed = True
                    webhook_log.save()
                    
                    logger.info(f"Successfully processed recording from webhook: {zoom_recording.zoom_recording_id}")
                else:
                    logger.warning("No recording created from webhook payload (possibly filtered by host)")
                    
            except Exception as e:
                logger.error(f"Failed to process recording webhook: {str(e)}")
                return Response({'error': 'Processing failed'}, status=500)
        
        return Response({'status': 'success'}, status=200)
        
    except Exception as e:
        logger.error(f"Zoom webhook error: {str(e)}")
        return Response({'error': str(e)}, status=500)
def _verify_zoom_webhook(request) -> bool:
    """
    Verify Zoom webhook signature (optional but recommended)
    You'll need to set up webhook verification in Zoom marketplace app
    """
    # This is a placeholder - implement actual verification if needed
    # For now, we'll skip verification in development
    return True


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def zoom_recordings_list(request):
    """
    List all Zoom recordings with filtering options
    """
    from .models import ZoomRecording
    from django.core.paginator import Paginator
    
    if not request.user.is_staff:
        return Response({'error': 'Staff access required'}, status=403)
    
    try:
        # Get query parameters
        status_filter = request.GET.get('status', None)
        meeting_id = request.GET.get('meeting_id', None)
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        # Build query
        queryset = ZoomRecording.objects.all()
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if meeting_id:
            queryset = queryset.filter(zoom_meeting_id=meeting_id)
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        recordings_page = paginator.get_page(page)
        
        # Serialize data
        recordings_data = []
        for recording in recordings_page:
            data = {
                'id': recording.id,
                'zoom_recording_id': recording.zoom_recording_id,
                'zoom_meeting_id': recording.zoom_meeting_id,
                'status': recording.status,
                'duration_formatted': recording.duration_formatted,
                'file_size_mb': round(recording.file_size / (1024 * 1024), 2),
                'recording_start_time': recording.recording_start_time.isoformat(),
                'r2_storage_url': recording.r2_storage_url,
                'live_class': {
                    'id': recording.live_class.id if recording.live_class else None,
                    'title': recording.live_class.title if recording.live_class else None,
                    'subject': recording.live_class.subject.name if recording.live_class else None
                },
                'subject_recording_video': {
                    'id': recording.subject_recording_video.id if recording.subject_recording_video else None,
                    'title': recording.subject_recording_video.title if recording.subject_recording_video else None
                },
                'created_at': recording.created_at.isoformat(),
                'error_message': recording.error_message
            }
            recordings_data.append(data)
        
        return Response({
            'recordings': recordings_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_records': paginator.count,
                'has_next': recordings_page.has_next(),
                'has_previous': recordings_page.has_previous()
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list Zoom recordings: {str(e)}")
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def process_zoom_recording(request, recording_id):
    """
    Manually trigger processing of a specific Zoom recording
    """
    from .models import ZoomRecording
    from .zoom_service import ZoomRecordingService
    
    if not request.user.is_staff:
        return Response({'error': 'Staff access required'}, status=403)
    
    try:
        recording = get_object_or_404(ZoomRecording, id=recording_id)
        
        if recording.status == 'processing':
            return Response({'error': 'Recording is already being processed'}, status=400)
        
        if recording.status == 'completed':
            return Response({'error': 'Recording has already been processed'}, status=400)
        
        zoom_service = ZoomRecordingService()
        success = zoom_service.process_recording(recording)
        
        if success:
            return Response({
                'status': 'success',
                'message': f'Recording {recording.zoom_recording_id} processed successfully',
                'r2_url': recording.r2_storage_url
            })
        else:
            return Response({
                'status': 'failed',
                'message': f'Failed to process recording {recording.zoom_recording_id}',
                'error': recording.error_message
            }, status=500)
            
    except Exception as e:
        logger.error(f"Failed to process recording {recording_id}: {str(e)}")
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def process_all_pending_recordings(request):
    """
    Process all pending Zoom recordings
    """
    from .zoom_service import ZoomRecordingService
    
    if not request.user.is_staff:
        return Response({'error': 'Staff access required'}, status=403)
    
    try:
        zoom_service = ZoomRecordingService()
        results = zoom_service.process_pending_recordings()
        
        return Response({
            'status': 'completed',
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Failed to process pending recordings: {str(e)}")
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def sync_zoom_recordings(request):
    """
    Manually sync recordings from Zoom for a date range
    """
    from .zoom_service import ZoomRecordingService
    from .models import ZoomRecording, LiveClass
    from datetime import datetime, timedelta
    
    if not request.user.is_staff:
        return Response({'error': 'Staff access required'}, status=403)
    
    try:
        # Get date range from query parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        zoom_service = ZoomRecordingService()
        meetings = zoom_service.get_recordings_by_date_range(start_date, end_date)
        
        synced_count = 0
        for meeting in meetings:
            meeting_id = meeting.get('id')
            meeting_uuid = meeting.get('uuid')
            
            recording_files = meeting.get('recording_files', [])
            
            for recording_file in recording_files:
                if recording_file.get('file_type') in ['MP4', 'mp4']:
                    recording_id = recording_file.get('id')
                    
                    # Check if recording already exists
                    if ZoomRecording.objects.filter(zoom_recording_id=recording_id).exists():
                        continue
                    
                    # Try to find associated live class
                    live_class = None
                    try:
                        live_class = LiveClass.objects.get(zoom_meeting_id=meeting_id)
                    except LiveClass.DoesNotExist:
                        pass
                    
                    # Create ZoomRecording
                    ZoomRecording.objects.create(
                        zoom_meeting_id=meeting_id,
                        zoom_recording_id=recording_id,
                        zoom_meeting_uuid=meeting_uuid,
                        recording_start_time=datetime.fromisoformat(recording_file.get('recording_start').replace('Z', '+00:00')),
                        recording_end_time=datetime.fromisoformat(recording_file.get('recording_end').replace('Z', '+00:00')),
                        duration=recording_file.get('play_time', 0) * 1000,  # Convert to milliseconds
                        file_size=recording_file.get('file_size', 0),
                        file_type=recording_file.get('file_type', 'mp4').lower(),
                        zoom_download_url=recording_file.get('download_url'),
                        download_token=recording_file.get('download_token'),
                        live_class=live_class,
                        status='pending'
                    )
                    synced_count += 1
        
        return Response({
            'status': 'success',
            'synced_recordings': synced_count,
            'date_range': f"{start_date} to {end_date}"
        })
        
    except Exception as e:
        logger.error(f"Failed to sync Zoom recordings: {str(e)}")
        return Response({'error': str(e)}, status=500)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def delete_zoom_recording(request, recording_id):
    """
    Delete a Zoom recording (and optionally from R2 storage)
    """
    from .models import ZoomRecording
    from .zoom_service import ZoomRecordingService
    
    if not request.user.is_staff:
        return Response({'error': 'Staff access required'}, status=403)
    
    try:
        recording = get_object_or_404(ZoomRecording, id=recording_id)
        delete_from_r2 = request.data.get('delete_from_r2', False)
        
        if delete_from_r2 and recording.r2_storage_key:
            zoom_service = ZoomRecordingService()
            try:
                zoom_service.r2_client.delete_object(
                    Bucket=zoom_service.bucket_name,
                    Key=recording.r2_storage_key
                )
                logger.info(f"Deleted recording from R2: {recording.r2_storage_key}")
            except Exception as e:
                logger.warning(f"Failed to delete from R2: {str(e)}")
        
        recording.delete()
        
        return Response({
            'status': 'success',
            'message': f'Recording {recording.zoom_recording_id} deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to delete recording {recording_id}: {str(e)}")
        return Response({'error': str(e)}, status=500)


# ============================
# Zero-Fee Enrollment (instant)
# ============================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def enroll_free(request):
    """
    Instantly enroll the authenticated user when the program/course is free.
    Body: { "program_id": int, ["subject_ids": [int, ...]] }
    """
    try:
        program_id = request.data.get('program_id')
        subject_ids = request.data.get('subject_ids') or []

        if not program_id:
            return Response({'error': 'program_id is required'}, status=400)

        program = get_object_or_404(Program, id=program_id)
        if program.price and Decimal(program.price) > 0:
            return Response({'error': 'Program is not free'}, status=400)

        user = request.user
        course = program.course

        # Enroll
        user.programs.add(program)
        if course:
            user.courses.add(course)
        program.participant_users.add(user)

        # Subjects: if provided use them, else enroll all program subjects
        if subject_ids:
            subjects = Subject.objects.filter(id__in=subject_ids)
            if subjects.exists():
                user.subjects.add(*subjects)
        elif program.subjects.exists():
            user.subjects.add(*program.subjects.all())

        # Send confirmation email
        try:
            from django.core.mail import send_mail
            subject = 'Enrollment Confirmation'
            message = f"Dear {user.first_name or user.username},\n\nYou have been successfully enrolled in {program.name}.\n\nThank you."
            send_mail(subject, message, os.environ.get('EMAIL_HOST_USER', 'billing@aakhyaan.org'), [user.email], fail_silently=True)
        except Exception:
            pass

        return Response({
            'status': 'success',
            'message': 'Enrolled successfully',
            'program_id': program.id,
            'course_id': course.id if course else None,
        })
    except Exception as e:
        logger.error(f"Error in enroll_free: {str(e)}")
        return Response({'error': str(e)}, status=500)


# ============================
# Notification device registration and manual send
# ============================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def register_device_token(request):
    token = request.data.get('token')
    platform = request.data.get('platform', 'android')
    if not token:
        return Response({'error': 'token is required'}, status=400)

    obj, _ = DeviceToken.objects.update_or_create(
        token=token,
        defaults={'user': request.user, 'platform': platform, 'active': True},
    )
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, VersionedJWTAuthentication])
def send_manual_notification(request):
    if not request.user.is_staff:
        return Response({'error': 'Staff access required'}, status=403)
    title = request.data.get('title')
    body = request.data.get('body')
    user_ids = request.data.get('user_ids') or []
    if not title or not body:
        return Response({'error': 'title and body are required'}, status=400)

    from .tasks import notify_manual_to_users
    if user_ids:
        notify_manual_to_users.delay(user_ids, title, body, {})
    else:
        # all active devices
        tokens = list(DeviceToken.objects.filter(active=True).values_list('token', flat=True))
        from .tasks import send_fcm_to_tokens
        send_fcm_to_tokens.delay(tokens, title, body, {})
    return Response({'status': 'queued'})