from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q, Count, Case, When, IntegerField
from .models import Message, PersonalMessage, MessageStatus
from api.models import Program, Subject
from accounts.models import CustomUser


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unseen_counts(request):
    """
    Get unseen message counts for discussions and personal chats - OPTIMIZED
    Fixed to properly handle message status for seen/delivered/sent states
    """
    user = request.user
    
    # OPTIMIZATION: Use select_related and prefetch_related to reduce queries
    discussion_counts = []
    
    # Get user's enrolled programs with optimized query
    enrolled_programs = user.programs.select_related('course').all()
    
    for program in enrolled_programs:
        program_channels = ['notices', 'routine', 'motivation', 'off_topics', 'meme']
        
        # FIXED: Calculate unseen counts properly considering MessageStatus for group messages
        unseen_counts_by_channel = Message.objects.filter(
            program=program,
            channel__in=program_channels
        ).exclude(
            Q(user=user)  # Exclude own messages
        ).exclude(
            # Exclude messages that have been seen by this user
            Q(read_statuses__user=user, read_statuses__seen_at__isnull=False)
        ).values('channel').annotate(
            unseen_count=Count('id')
        )
        
        # Convert to dict for efficient lookup
        channel_counts = {
            item['channel']: item['unseen_count'] 
            for item in unseen_counts_by_channel
        }
        
        for channel in program_channels:
            unseen_count = channel_counts.get(channel, 0)
            if unseen_count > 0:
                discussion_counts.append({
                    'type': 'program',
                    'id': program.id,
                    'name': program.name,
                    'channel': channel,
                    'unseen_count': unseen_count
                })
    
    # Get user's enrolled subjects with optimized query  
    enrolled_subjects = user.subjects.select_related('course').all()
    
    for subject in enrolled_subjects:
        subject_channels = ['notices', 'off_topics', 'discussion', 'assignments']
        
        # FIXED: Calculate unseen counts properly for subjects too
        unseen_counts_by_channel = Message.objects.filter(
            subject=subject,
            channel__in=subject_channels
        ).exclude(
            Q(user=user)  # Exclude own messages
        ).exclude(
            # Exclude messages that have been seen by this user
            Q(read_statuses__user=user, read_statuses__seen_at__isnull=False)
        ).values('channel').annotate(
            unseen_count=Count('id')
        )
        
        # Convert to dict for efficient lookup
        channel_counts = {
            item['channel']: item['unseen_count'] 
            for item in unseen_counts_by_channel
        }
        
        for channel in subject_channels:
            unseen_count = channel_counts.get(channel, 0)
            if unseen_count > 0:
                discussion_counts.append({
                    'type': 'subject',
                    'id': subject.id,
                    'name': subject.name,
                    'channel': channel,
                    'unseen_count': unseen_count
                })
    
    # OPTIMIZATION: More efficient personal chat query using select_related
    personal_chat_counts = PersonalMessage.objects.filter(
        receiver=user,
        status__in=['sent', 'delivered']  # Messages that haven't been seen yet
    ).select_related('sender').values(
        'sender__id', 'sender__username'
    ).annotate(
        unseen_count=Count('id')
    ).order_by('-unseen_count')
    
    # Format personal chat counts
    personal_counts = [
        {
            'user_id': chat['sender__id'],
            'username': chat['sender__username'],
            'unseen_count': chat['unseen_count']
        }
        for chat in personal_chat_counts
    ]
    
    return Response({
        'discussion_counts': discussion_counts,
        'personal_chat_counts': personal_counts,
        'total_unseen_discussions': sum(d['unseen_count'] for d in discussion_counts),
        'total_unseen_personal': sum(p['unseen_count'] for p in personal_counts)
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_channel_unseen_count(request, discussion_type, discussion_id, channel):
    """
    Get unseen count for a specific channel
    """
    user = request.user
    
    try:
        if discussion_type == 'program':
            program = Program.objects.get(id=discussion_id)
            unseen_count = Message.objects.filter(
                program=program,
                channel=channel
            ).exclude(
                Q(user=user) |  # Exclude own messages
                Q(read_statuses__user=user, read_statuses__seen_at__isnull=False)  # Exclude seen messages
            ).count()
        elif discussion_type == 'subject':
            subject = Subject.objects.get(id=discussion_id)
            unseen_count = Message.objects.filter(
                subject=subject,
                channel=channel
            ).exclude(
                Q(user=user) |  # Exclude own messages
                Q(read_statuses__user=user, read_statuses__seen_at__isnull=False)  # Exclude seen messages
            ).count()
        else:
            return Response({'error': 'Invalid discussion type'}, status=400)
            
        return Response({'unseen_count': unseen_count})
        
    except (Program.DoesNotExist, Subject.DoesNotExist):
        return Response({'error': 'Discussion not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_personal_chat_unseen_count(request, other_user_id):
    """
    Get unseen count for personal chat with specific user
    """
    user = request.user
    
    try:
        other_user = CustomUser.objects.get(id=other_user_id)
        unseen_count = PersonalMessage.objects.filter(
            sender=other_user,
            receiver=user,
            status__in=['sent', 'delivered']  # Messages that haven't been seen yet
        ).count()
        
        return Response({
            'unseen_count': unseen_count,
            'other_user': {
                'id': other_user.id,
                'username': other_user.username
            }
        })
        
    except CustomUser.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
