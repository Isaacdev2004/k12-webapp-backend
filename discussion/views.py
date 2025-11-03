from datetime import timezone
from rest_framework import viewsets
from rest_framework.response import Response
from .models import Message, MessageReaction, MessageImage, MessageStatus, PersonalMessage
from .serializers import MessageSerializer, MessageImageSerializer, ReactionSerializer
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated,AllowAny
from rest_framework.exceptions import NotFound
from api.models import Program, Subject
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.core.files.storage import default_storage
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async
import logging
import traceback
import os

logger = logging.getLogger(__name__)

class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    permission_classes = [AllowAny]

    # Custom method to get messages for a specific program and channel
    @action(detail=False, methods=['get'], url_path='program/(?P<program_id>\d+)/(?P<channel>\w+)')
    def get_program_messages(self, request, program_id=None, channel=None):
        try:
            program = Program.objects.get(id=program_id)
        except Program.DoesNotExist:
            raise NotFound(detail="Program not found")
        
        messages = Message.objects.filter(program=program, channel=channel)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    # Custom method to get messages for a specific subject and channel
    @action(detail=False, methods=['get'], url_path='subject/(?P<subject_id>\d+)/(?P<channel>\w+)')
    def get_subject_messages(self, request, subject_id=None, channel=None):
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            raise NotFound(detail="Subject not found")
        
        messages = Message.objects.filter(subject=subject, channel=channel)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)


class MessageImageViewSet(viewsets.ModelViewSet):
    queryset = MessageImage.objects.all()
    serializer_class = MessageImageSerializer
    permission_classes = [IsAuthenticated]


class ReactionViewSet(viewsets.ModelViewSet):
    queryset = MessageReaction.objects.all()
    serializer_class = ReactionSerializer
    permission_classes = [IsAuthenticated]


class MessageStatusViewSet(viewsets.ViewSet):
    """ViewSet for handling message status updates"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='mark-delivered')
    def mark_delivered(self, request):
        """Mark messages as delivered for the current user"""
        message_ids = request.data.get('message_ids', [])
        discussion_type = request.data.get('discussion_type')
        discussion_id = request.data.get('discussion_id')
        channel = request.data.get('channel')

        if not message_ids:
            return Response(
                {'error': 'message_ids are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                updated_messages = []
                
                for message_id in message_ids:
                    try:
                        message = Message.objects.get(
                            id=message_id,
                            **self._get_discussion_filter(discussion_type, discussion_id),
                            channel=channel
                        )
                        
                        # Don't update status for sender's own messages
                        if message.user != request.user:
                            # Create or update MessageStatus
                            message_status, created = MessageStatus.objects.get_or_create(
                                message=message,
                                user=request.user
                            )
                            
                            if not message_status.delivered_at:
                                message_status.mark_as_delivered()
                                updated_messages.append(message_id)
                    
                    except Message.DoesNotExist:
                        continue

                # Broadcast status updates via WebSocket
                if updated_messages:
                    self._broadcast_status_update(
                        discussion_type, discussion_id, channel,
                        updated_messages, 'delivered', request.user
                    )

                return Response({
                    'status': 'success',
                    'updated_messages': updated_messages
                })

        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='mark-seen')
    def mark_seen(self, request):
        """Mark messages as seen for the current user"""
        message_ids = request.data.get('message_ids', [])
        discussion_type = request.data.get('discussion_type')
        discussion_id = request.data.get('discussion_id')
        channel = request.data.get('channel')

        if not message_ids:
            return Response(
                {'error': 'message_ids are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                updated_messages = []
                
                for message_id in message_ids:
                    try:
                        message = Message.objects.get(
                            id=message_id,
                            **self._get_discussion_filter(discussion_type, discussion_id),
                            channel=channel
                        )
                        
                        # Don't update status for sender's own messages
                        if message.user != request.user:
                            try:
                                # Create or update MessageStatus
                                message_status, created = MessageStatus.objects.get_or_create(
                                    message=message,
                                    user=request.user
                                )
                                
                                if not message_status.seen_at:
                                    message_status.mark_as_seen()
                                    updated_messages.append(message_id)
                                    
                                    # Check if all participants have seen the message
                                    self._update_group_message_status(message)
                            except Exception as e:
                                logger.error(f"Error marking message {message_id} as seen: {e}")
                                continue
                    
                    except Message.DoesNotExist:
                        logger.warning(f"Message {message_id} not found")
                        continue
                    except Exception as e:
                        logger.error(f"Error processing message {message_id}: {e}")
                        continue

                # Broadcast status updates via WebSocket (outside transaction)
                if updated_messages:
                    try:
                        self._broadcast_status_update(
                            discussion_type, discussion_id, channel,
                            updated_messages, 'seen', request.user
                        )
                    except Exception as e:
                        logger.error(f"Failed to broadcast status update: {e}")
                        # Don't fail the entire request if broadcast fails

                return Response({
                    'status': 'success',
                    'updated_messages': updated_messages
                })

        except Exception as e:
            logger.error(f"Error in mark_seen: {e}")
            return Response(
                {'error': f'Failed to mark messages as seen: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_discussion_filter(self, discussion_type, discussion_id):
        """Get filter for discussion type"""
        if discussion_type == 'program':
            return {'program_id': discussion_id, 'subject': None}
        elif discussion_type == 'subject':
            return {'subject_id': discussion_id, 'program': None}
        return {}

    def _update_group_message_status(self, message):
        """Update the overall message status based on all participants"""
        participants = message.get_participants().exclude(id=message.user.id)
        total_participants = participants.count()
        
        if total_participants == 0:
            return
            
        seen_count = MessageStatus.objects.filter(
            message=message,
            user__in=participants,
            seen_at__isnull=False
        ).count()
        
        delivered_count = MessageStatus.objects.filter(
            message=message,
            user__in=participants,
            delivered_at__isnull=False
        ).count()
        
        # Update message status based on group participation
        if seen_count == total_participants:
            message.update_status_to_seen()
        elif delivered_count == total_participants:
            message.update_status_to_delivered()

    def _broadcast_status_update(self, discussion_type, discussion_id, channel, message_ids, new_status, user):
        """Broadcast message status updates via WebSocket"""
        try:
            channel_layer = get_channel_layer()
            group_name = f"{discussion_type}_{discussion_id}_{channel}"
            
            # Use async_to_sync safely
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'message_status_update',
                    'message_ids': message_ids,
                    'status': new_status,
                    'user_id': user.id,
                    'username': user.username
                }
            )
        except Exception as e:
            logger.error(f"Failed to broadcast status update: {e}")
            # Don't fail the entire request if WebSocket broadcast fails


class PersonalMessageStatusViewSet(viewsets.ViewSet):
    """ViewSet for handling personal message status updates"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='mark-delivered')
    def mark_delivered(self, request):
        """Mark personal messages as delivered"""
        message_ids = request.data.get('message_ids', [])
        other_user_id = request.data.get('other_user_id')

        if not message_ids or not other_user_id:
            return Response(
                {'error': 'message_ids and other_user_id are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                updated_messages = []
                
                for message_id in message_ids:
                    try:
                        message = PersonalMessage.objects.get(
                            id=message_id,
                            sender_id=other_user_id,
                            receiver=request.user
                        )
                        
                        if message.status == 'sent':
                            message.update_status_to_delivered()
                            updated_messages.append(message_id)
                    
                    except PersonalMessage.DoesNotExist:
                        continue

                # Broadcast status updates via WebSocket
                if updated_messages:
                    self._broadcast_personal_status_update(
                        request.user.id, other_user_id,
                        updated_messages, 'delivered'
                    )

                return Response({
                    'status': 'success',
                    'updated_messages': updated_messages
                })

        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='mark-seen')
    def mark_seen(self, request):
        """Mark personal messages as seen"""
        message_ids = request.data.get('message_ids', [])
        other_user_id = request.data.get('other_user_id')

        if not message_ids or not other_user_id:
            return Response(
                {'error': 'message_ids and other_user_id are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                updated_messages = []
                
                for message_id in message_ids:
                    try:
                        message = PersonalMessage.objects.get(
                            id=message_id,
                            sender_id=other_user_id,
                            receiver=request.user
                        )
                        
                        if message.status in ['sent', 'delivered']:
                            message.update_status_to_seen()
                            updated_messages.append(message_id)
                    
                    except PersonalMessage.DoesNotExist:
                        continue

                # Broadcast status updates via WebSocket
                if updated_messages:
                    self._broadcast_personal_status_update(
                        request.user.id, other_user_id,
                        updated_messages, 'seen'
                    )

                return Response({
                    'status': 'success',
                    'updated_messages': updated_messages
                })

        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _broadcast_personal_status_update(self, user_id, other_user_id, message_ids, new_status):
        """Broadcast personal message status updates via WebSocket"""
        channel_layer = get_channel_layer()
        user_ids = sorted([str(user_id), str(other_user_id)])
        room_name = f"personal_chat_{user_ids[0]}_{user_ids[1]}"
        
        async_to_sync(channel_layer.group_send)(
            room_name,
            {
                'type': 'personal_message_status_update',
                'message_ids': message_ids,
                'status': new_status,
                'user_id': user_id
            }
        )

