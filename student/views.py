from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    DashboardStatsSerializer, SubjectSerializer, CourseSerializer, 
    MockTestResultSerializer, SubjectContentsSerializer, PaymentSerializer,
    SubjectVideoSerializer, UserProfileSerializer, LiveClassSerializer,
    SubjectNoteSerializer, ChatUserSerializer, DiscussionChannelSerializer,
    MockTestSerializer, McqResultSerializer, SubjectWithNotesSerializer,
    EnhancedChatUserSerializer, OnePGPaymentSerializer, QrPaymentTransactionSerializer
)
from api.models import Subject, Program, Course, MockTestResult, PaymentPicture, LiveClass, MCQ, MockTest, McqResult, OnePGPayment, QrPaymentTransaction
from accounts.models import CustomUser
from discussion.models import PersonalMessage
import logging
from datetime import datetime, timedelta
from django.db.models import Q, Count, Max, Case, When, IntegerField, OuterRef, Subquery, Value

logger = logging.getLogger(__name__)

class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            
            # Get user's enrolled items using direct relationships
            subjects = user.subjects.all().order_by('-id')
            courses = user.courses.all().order_by('-id')
            mocktest_results = user.mocktest_results_api.all().order_by('-completed_at')[:10]  # Get last 10 results
            programs = user.programs.all()
            
            # Calculate counts
            subjects_enrolled = subjects.count()
            programs_enrolled = programs.count()
            mocktest_results_count = mocktest_results.count()
            
            # Prepare data dictionary
            dashboard_stats = {
                'total_subjects_enrolled': subjects_enrolled,
                'total_programs_enrolled': programs_enrolled,
                'total_mocktest_results': mocktest_results_count,
                'subjects': subjects,
                'courses': courses,
                'mocktest_results': mocktest_results
            }
            
            # Serialize the data
            serializer = DashboardStatsSerializer(dashboard_stats)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Dashboard Error for user {request.user.id}: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'An error occurred while fetching dashboard data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ContentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching contents for user {user.id}")
            
            try:
                # Get user's enrolled subjects with all related data
                subjects = user.subjects.all()
                logger.info(f"Found {subjects.count()} subjects")
                
                # Prefetch related data with correct related names
                subjects = subjects.prefetch_related(
                    'subject_chapters',  # Changed from 'chapters' to match model
                    'subject_chapters__topics',
                    'subject_chapters__topics__contents',
                    'subject_chapters__topics__videos',
                    'subject_chapters__topics__mcqs'
                ).order_by('-id')
                
                logger.info("Successfully prefetched related data")
                
                # Serialize the data
                try:
                    serializer = SubjectContentsSerializer(
                        subjects, 
                        many=True,
                        context={'request': request}
                    )
                    data = serializer.data
                    logger.info("Successfully serialized data")
                    return Response(data, status=status.HTTP_200_OK)
                except Exception as se:
                    logger.error(f"Serialization error: {str(se)}", exc_info=True)
                    return Response(
                        {'detail': 'Error serializing data.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                    
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying database.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Contents Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching contents data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching all payment types for user {user.id}")
            
            try:
                # Get user's payment pictures
                payment_pictures = PaymentPicture.objects.filter(
                    user=user
                ).select_related(
                    'course',
                    'program'
                ).prefetch_related(
                    'subject'
                ).order_by('-date')
                
                # Get user's OnePG payments
                onepg_payments = OnePGPayment.objects.filter(
                    user=user
                ).select_related(
                    'course',
                    'program'
                ).prefetch_related(
                    'subjects'
                ).order_by('-transaction_date')
                
                # Get user's QR payment transactions
                qr_payments = QrPaymentTransaction.objects.filter(
                    user=user
                ).select_related(
                    'course',
                    'program'
                ).prefetch_related(
                    'subjects'
                ).order_by('-transaction_date')
                
                logger.info(f"Found {payment_pictures.count()} payment pictures, {onepg_payments.count()} OnePG payments, {qr_payments.count()} QR payments")
                
                # Serialize all payment types
                try:
                    payment_pictures_data = PaymentSerializer(
                        payment_pictures, 
                        many=True,
                        context={'request': request}
                    ).data
                    
                    onepg_payments_data = OnePGPaymentSerializer(
                        onepg_payments,
                        many=True,
                        context={'request': request}
                    ).data
                    
                    qr_payments_data = QrPaymentTransactionSerializer(
                        qr_payments,
                        many=True,
                        context={'request': request}
                    ).data
                    
                    # Combine all payments and sort by date
                    all_payments = payment_pictures_data + onepg_payments_data + qr_payments_data
                    
                    # Sort by date (most recent first)
                    all_payments.sort(key=lambda x: x['date'], reverse=True)
                    
                    logger.info(f"Successfully combined and sorted {len(all_payments)} total payments")
                    return Response(all_payments, status=status.HTTP_200_OK)
                    
                except Exception as se:
                    logger.error(f"Serialization error: {str(se)}", exc_info=True)
                    return Response(
                        {'detail': 'Error serializing payment data.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                    
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying payment data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Payment Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching payment data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MockTestResultsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching mock test results for user {user.id}")
            
            try:
                # Get user's mock test results
                mocktest_results = MockTestResult.objects.filter(
                    user=user
                ).select_related(
                    'mock_test',
                    'mock_test__course'
                ).order_by('-completed_at')
                
                logger.info(f"Found {mocktest_results.count()} mock test results")
                
                # Serialize the data
                try:
                    serializer = MockTestResultSerializer(
                        mocktest_results, 
                        many=True,
                        context={'request': request}
                    )
                    data = serializer.data
                    logger.info("Successfully serialized mock test result data")
                    return Response(data, status=status.HTTP_200_OK)
                except Exception as se:
                    logger.error(f"Serialization error: {str(se)}", exc_info=True)
                    return Response(
                        {'detail': 'Error serializing mock test result data.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                    
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying mock test result data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Mock Test Results Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching mock test result data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class McqResultsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching MCQ results for user {user.id}")
            
            try:
                # Get user's MCQ results
                mcq_results = McqResult.objects.filter(
                    user=user
                ).select_related(
                    'mcq',
                    'mcq__topic',
                    'mcq__topic__chapter',
                    'mcq__topic__chapter__subject',
                    'mcq__topic__chapter__subject__course'
                ).order_by('-completed_at')
                
                logger.info(f"Found {mcq_results.count()} MCQ results")
                
                # Serialize the data (same as MockTestResultsView)
                serializer = McqResultSerializer(
                    mcq_results,
                    many=True,
                    context={'request': request}
                )
                data = serializer.data
                logger.info("Successfully serialized MCQ results data")
                return Response(data, status=status.HTTP_200_OK)
            except Exception as se:
                logger.error(f"Serialization error: {str(se)}", exc_info=True)
                return Response(
                    {'detail': 'Error serializing MCQ result data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        except Exception as e:
            logger.error(
                f"MCQ Results Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching MCQ result data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class RecordingVideoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching recording videos for user {user.id}")
            
            try:
                # Log the user's subjects
                subjects = user.subjects.all()
                logger.info(f"User has {subjects.count()} subjects")
                
                # Log each subject's videos before prefetch
                for subject in subjects:
                    logger.info(f"Subject {subject.id} - {subject.name}: {subject.subject_recording_videos.count()} videos")
                
                # Get user's enrolled subjects with videos
                subjects = subjects.prefetch_related(
                    'subject_recording_videos'
                ).order_by('-id')
                
                logger.info(f"Successfully prefetched related data for {subjects.count()} subjects")
                
                # Serialize the data
                try:
                    serializer = SubjectVideoSerializer(
                        subjects, 
                        many=True,
                        context={'request': request}
                    )
                    data = serializer.data
                    logger.info("Successfully serialized recording video data")
                    
                    # Log the serialized data structure
                    for subject_data in data:
                        logger.info(f"Subject {subject_data['id']} has {len(subject_data.get('subject_recording_videos', []))} videos")
                    
                    return Response(data, status=status.HTTP_200_OK)
                except Exception as se:
                    logger.error(
                        f"Serialization error in RecordingVideoView:\n"
                        f"Error type: {type(se).__name__}\n"
                        f"Error details: {str(se)}\n"
                        f"Traceback:", exc_info=True
                    )
                    return Response(
                        {'detail': 'Error serializing recording video data.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                    
            except Exception as qe:
                logger.error(
                    f"Query error in RecordingVideoView:\n"
                    f"Error type: {type(qe).__name__}\n"
                    f"Error details: {str(qe)}\n"
                    f"Traceback:", exc_info=True
                )
                return Response(
                    {'detail': 'Error querying recording video data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Recording Video Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}\n"
                f"Traceback:", exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching recording video data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            serializer = UserProfileSerializer(request.user, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching user profile: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'Error fetching user profile.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request):
        try:
            serializer = UserProfileSerializer(
                request.user,
                data=request.data,
                context={'request': request},
                partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error updating user profile: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'Error updating user profile.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class LiveClassView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching live classes for user {user.id}")
            
            try:
                # Get user's enrolled subjects
                subjects = user.subjects.all()
                
                # Get all live classes for these subjects
                live_classes = LiveClass.objects.filter(
                    subject__in=subjects
                ).select_related(
                    'subject',
                    'host'
                ).order_by('start_time')
                
                logger.info(f"Found {live_classes.count()} live classes")
                
                # Serialize the data
                serializer = LiveClassSerializer(
                    live_classes,
                    many=True,
                    context={'request': request}
                )
                data = serializer.data
                logger.info("Successfully serialized live class data")
                
                return Response(data, status=status.HTTP_200_OK)
                
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying live class data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Live Class Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching live class data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class NotesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching notes for user {user.id}")
            
            try:
                # Get user's enrolled subjects with notes
                subjects = user.subjects.prefetch_related(
                    'subject_notes'
                ).order_by('-id')
                
                logger.info(f"Found {subjects.count()} subjects")
                
                # Serialize the data
                serializer = SubjectWithNotesSerializer(
                    subjects,
                    many=True,
                    context={'request': request}
                )
                data = serializer.data
                logger.info("Successfully serialized notes data")
                
                return Response(data, status=status.HTTP_200_OK)
                
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying notes data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Notes Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching notes data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching chat users for user {user.id}")
            
            try:
                # Check if user has any programs or subjects
                programs = user.programs.all()
                subjects = user.subjects.all()
                
                if not programs.exists() and not subjects.exists():
                    logger.warning(f"User {user.id} has no programs or subjects enrolled")
                    return Response(
                        {'detail': 'You must be enrolled in at least one program or subject to access chat.'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Get user type from query params, default to both admin and teacher
                user_types = request.query_params.get('user_type', 'admin,teacher').split(',')
                
                # Get all admin and teacher users
                chat_users = CustomUser.objects.filter(
                    user_type__in=user_types
                ).exclude(
                    id=user.id  # Exclude the current user
                ).order_by(
                    'first_name', 'last_name'
                )
                
                logger.info(f"Found {chat_users.count()} chat users")
                
                # Serialize the data
                serializer = ChatUserSerializer(
                    chat_users,
                    many=True,
                    context={'request': request}
                )
                data = serializer.data
                logger.info("Successfully serialized chat users data")
                
                return Response(data, status=status.HTTP_200_OK)
                
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying chat users data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Chat Users Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching chat users data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DiscussionChannelsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching discussion channels for user {user.id}")
            
            try:
                # Get user's enrolled programs and subjects
                programs = user.programs.all()
                subjects = user.subjects.all()
                
                # Prepare channels data
                channels = []
                
                # Add program channels
                for program in programs:
                    program_channels = [
                        {
                            'id': program.id,
                            'name': program.name,
                            'channel_type': 'program',
                            'channel_type_name': 'Program',
                            'key': channel_key
                        }
                        for channel_key in ['notices', 'routine', 'motivation', 'off_topics', 'meme']
                    ]
                    channels.extend(program_channels)
                
                # Add subject channels
                for subject in subjects:
                    subject_channels = [
                        {
                            'id': subject.id,
                            'name': subject.name,
                            'channel_type': 'subject',
                            'channel_type_name': 'Subject',
                            'key': channel_key
                        }
                        for channel_key in ['notices', 'off_topics', 'discussion', 'assignments']
                    ]
                    channels.extend(subject_channels)
                
                logger.info(f"Found {len(channels)} discussion channels")
                
                # Serialize the data
                serializer = DiscussionChannelSerializer(channels, many=True)
                data = serializer.data
                logger.info("Successfully serialized discussion channels data")
                
                return Response(data, status=status.HTTP_200_OK)
                
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying discussion channels data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Discussion Channels Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching discussion channels data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MockTestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching mock tests for user {user.id}")
            
            try:
                # Get user's enrolled courses
                courses = user.courses.all()
                
                # Get all mock tests for these courses
                mock_tests = MockTest.objects.filter(
                    course__in=courses,
                    is_active=True
                ).select_related(
                    'course'
                ).order_by('-created_at')  # Order by creation date
                
                logger.info(f"Found {mock_tests.count()} mock tests")
                
                # Serialize the data
                serializer = MockTestSerializer(
                    mock_tests,
                    many=True,
                    context={'request': request}
                )
                data = serializer.data
                logger.info("Successfully serialized mock test data")
                
                return Response(data, status=status.HTTP_200_OK)
                
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying mock test data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Mock Test Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching mock test data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class EnhancedChatView(APIView):
    """Enhanced chat view with sorting by unseen messages and last message time"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"Fetching enhanced chat users for user {user.id}")
            
            try:
                # Check if user has any programs or subjects
                programs = user.programs.all()
                subjects = user.subjects.all()
                
                if not programs.exists() and not subjects.exists():
                    logger.warning(f"User {user.id} has no programs or subjects enrolled")
                    return Response(
                        {'detail': 'You must be enrolled in at least one program or subject to access chat.'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Get user type from query params, default to both admin and teacher
                user_types = request.query_params.get('user_type', 'admin,teacher').split(',')
                
                # Subquery to get last message timestamp for each user
                last_message_subquery = PersonalMessage.objects.filter(
                    Q(sender=OuterRef('pk'), receiver=user) |
                    Q(sender=user, receiver=OuterRef('pk'))
                ).order_by('-timestamp').values('timestamp')[:1]
                
                # Subquery to get last message content
                last_message_content_subquery = PersonalMessage.objects.filter(
                    Q(sender=OuterRef('pk'), receiver=user) |
                    Q(sender=user, receiver=OuterRef('pk'))
                ).order_by('-timestamp').values('content')[:1]
                
                # Subquery to get last message sender
                last_message_sender_subquery = PersonalMessage.objects.filter(
                    Q(sender=OuterRef('pk'), receiver=user) |
                    Q(sender=user, receiver=OuterRef('pk'))
                ).order_by('-timestamp').values('sender__username')[:1]
                
                # Get all admin and teacher users with additional metadata
                chat_users = CustomUser.objects.filter(
                    user_type__in=user_types
                ).exclude(
                    id=user.id  # Exclude the current user
                ).annotate(
                    unseen_count=Count(
                        'sent_personal_messages',
                        filter=Q(
                            sent_personal_messages__receiver=user,
                            sent_personal_messages__status__in=['sent', 'delivered']
                        )
                    ),
                    last_message_time=Subquery(last_message_subquery),
                    last_message_content=Subquery(last_message_content_subquery),
                    last_message_sender=Subquery(last_message_sender_subquery),
                    # Add a field to handle NULL last_message_time properly
                    has_messages=Case(
                        When(last_message_time__isnull=True, then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField()
                    )
                ).order_by(
                    # First sort by unseen messages (descending - more unseen first)
                    '-unseen_count',
                    # Then sort by whether user has any messages (users with messages first)
                    '-has_messages',
                    # Then by last message time (descending - more recent first)
                    '-last_message_time',
                    # Finally by name for users with no messages
                    'first_name', 'last_name'
                )
                
                logger.info(f"Found {chat_users.count()} enhanced chat users")
                
                # Serialize the data
                serializer = EnhancedChatUserSerializer(
                    chat_users,
                    many=True,
                    context={'request': request}
                )
                data = serializer.data
                logger.info("Successfully serialized enhanced chat users data")
                
                return Response(data, status=status.HTTP_200_OK)
                
            except Exception as qe:
                logger.error(f"Query error: {str(qe)}", exc_info=True)
                return Response(
                    {'detail': 'Error querying enhanced chat users data.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(
                f"Enhanced Chat Users Error for user {request.user.id}:\n"
                f"Error type: {type(e).__name__}\n"
                f"Error details: {str(e)}",
                exc_info=True
            )
            return Response(
                {'detail': 'An error occurred while fetching enhanced chat users data.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
