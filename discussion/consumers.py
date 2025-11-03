import json
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone
from django.db.models import Q, Count
from django.db import models
from .models import Message, MessageImage, MessageReaction, PersonalMessage, PersonalMessageImage, PersonalMessageReaction, MessageStatus
from api.models import Program, Subject
from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth.models import AnonymousUser
from accounts.models import CustomUser
import base64
from django.core.files.base import ContentFile
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta
import logging

# Configure logger
logger = logging.getLogger(__name__)




class BaseDiscussionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Extract token from query string
        query_params = parse_qs(self.scope['query_string'].decode())
        token = query_params.get('token', [None])[0]

        if token:
            try:
                validated_token = AccessToken(token)
                user_id = validated_token['user_id']
                user = await database_sync_to_async(CustomUser.objects.get)(id=user_id)
                self.scope['user'] = user
            except Exception as e:
                await self.close(code=4001, reason="Invalid token.")
                return
        else:
            self.scope['user'] = AnonymousUser()

        # Proceed with normal connection logic after authentication
        self.discussion_type = self.scope['url_route']['kwargs'].get('discussion_type')
        self.discussion_id = self.scope['url_route']['kwargs'].get('discussion_id')
        self.channel = self.scope['url_route']['kwargs'].get('channel')

        # Determine valid channels based on the discussion type
        if self.discussion_type == 'subject':
            self.valid_channels = ['notices', 'off_topics', 'discussion', 'assignments']
        elif self.discussion_type == 'program':
            self.valid_channels = ['notices', 'routine', 'motivation', 'off_topics', 'meme']
        else:
            await self.close(code=4000, reason='Invalid discussion type.')
            return

        # Check if the channel is valid
        if self.channel not in self.valid_channels:
            await self.close(code=4002, reason='Invalid channel for the discussion type.')
            return

        # Check if the user is authenticated
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close(code=4001, reason='Authentication required.')
            return

        # Join the appropriate group based on discussion type and channel
        self.group_name = f"{self.discussion_type}_{self.discussion_id}_{self.channel}"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

        # Send a simple connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'WebSocket connection successful',
            'group': self.group_name
        }))
        
        # # Mark messages as delivered first
        # try:
        #     await self.mark_messages_as_delivered()
        #     print(f"📦 Messages marked as delivered for {self.group_name}")
        # except Exception as e:
        #     print(f"❌ Error marking messages as delivered: {e}")
        
        # Then send initial messages with updated statuses
        try:
            await self.send_initial_messages()
        except Exception:
            pass
            await self.send(text_data=json.dumps({
                'type': 'initial_messages',
                'messages': [],
            }))
        
        try:
            await self.mark_messages_as_seen()
        except Exception:
            pass

    async def disconnect(self, close_code):
        # Leave the group upon disconnection if group_name is set
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    @database_sync_to_async
    def get_target(self):
        try:
            if self.discussion_type == 'subject':
                target = Subject.objects.select_related('course').get(id=self.discussion_id)
                return {
                    'type': 'subject',
                    'id': target.id,
                    'name': target.name,
                    'course_id': target.course_id
                }
            elif self.discussion_type == 'program':
                target = Program.objects.select_related('course').get(id=self.discussion_id)
                return {
                    'type': 'program',
                    'id': target.id,
                    'name': target.name,
                    'course_id': target.course_id
                }
            return None
        except ObjectDoesNotExist:
            return None

    @database_sync_to_async
    def create_message(self, content, user, target_info, images=None, parent_message_id=None):
        if target_info['type'] == 'program':
            message = Message.objects.create(
                program_id=target_info['id'],
                subject=None,
                channel=self.channel,
                user=user,
                content=content,
                timestamp=timezone.now(),
                parent_message_id=parent_message_id
            )
        elif target_info['type'] == 'subject':
            message = Message.objects.create(
                program=None,
                subject_id=target_info['id'],
                channel=self.channel,
                user=user,
                content=content,
                timestamp=timezone.now(),
                parent_message_id=parent_message_id
            )
        else:
            raise ValueError('Invalid target type.')

        # Create MessageStatus objects for all participants except the sender
        if target_info['type'] == 'program':
            from api.models import Program
            program = Program.objects.get(id=target_info['id'])
            participants = program.users.exclude(id=user.id)
        elif target_info['type'] == 'subject':
            from api.models import Subject
            subject = Subject.objects.get(id=target_info['id'])
            participants = subject.users.exclude(id=user.id)
        
        # Create unseen MessageStatus for each participant
        for participant in participants:
            MessageStatus.objects.get_or_create(
                message=message,
                user=participant,
                defaults={'seen_at': None}  # This means it's unseen
            )
        


        # Handle image uploads if present
        if images:
            for image_data in images:
                try:
                    # Extract the base64 data
                    format, imgstr = image_data.split(';base64,')
                    ext = format.split('/')[-1]
                    
                    # Create a ContentFile from the base64 data
                    image_content = ContentFile(base64.b64decode(imgstr), name=f'message_image_{message.id}.{ext}')
                    
                    # Create MessageImage instance
                    MessageImage.objects.create(
                        message=message,
                        image=image_content
                    )
                except Exception:
                    pass

        return message.id

    @database_sync_to_async
    def get_message_with_images(self, message_id):
        message = Message.objects.get(id=message_id)
        images = [img.image.url for img in message.message_images.all()]
        
        # Get reaction counts
        reaction_counts = {}
        for reaction in MessageReaction.REACTION_CHOICES:
            count = message.reaction.filter(reaction_type=reaction[0]).count()
            if count > 0:
                reaction_counts[reaction[0]] = count

        # Get reply information
        reply_info = None
        if message.parent_message:
            reply_info = {
                'id': message.parent_message.id,
                'content': message.parent_message.content[:100],  # First 100 chars
                'username': message.parent_message.user.username
            }

        # Get read statuses for own messages
        current_user = self.scope['user']
        read_statuses = []
        if message.user == current_user:
            # Only include read statuses for own messages
            read_statuses = [
                {
                    'user': {
                        'id': status.user.id,
                        'username': status.user.username,
                        'email': status.user.email
                    },
                    'delivered_at': status.delivered_at.isoformat() if status.delivered_at else None,
                    'seen_at': status.seen_at.isoformat() if status.seen_at else None
                }
                for status in message.read_statuses.select_related('user').all()
            ]
                
        return {
            'id': message.id,
            'message': message.content,
            'username': message.user.username,
            'timestamp': message.timestamp.isoformat(),
            'images': images,
            'reactions': reaction_counts,
            'reply_to': reply_info,
            # Status fields
            'status': message.status,
            'delivered_at': message.delivered_at.isoformat() if message.delivered_at else None,
            'seen_at': message.seen_at.isoformat() if message.seen_at else None,
            'overall_status': message.status,
            'read_statuses': read_statuses,
            'seen_by_count': len([s for s in read_statuses if s['seen_at']]),
            'delivered_to_count': len([s for s in read_statuses if s['delivered_at']])
        }

    async def receive(self, text_data):
        try:
            # print(f"Received message data: {text_data}")
            text_data_json = json.loads(text_data)
        except json.JSONDecodeError:
            # print("Failed to decode JSON message")
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Invalid JSON format.'}))
            return

        message_type = text_data_json.get('type', 'message')

        # Handle message seen events
        if message_type == 'mark_seen':
            await self.handle_mark_seen(text_data_json)
            return

        if message_type == 'reaction':
            # Handle reaction
            message_id = text_data_json.get('message_id')
            reaction_type = text_data_json.get('reaction_type')
            
            if not message_id or not reaction_type:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Missing message_id or reaction_type'
                }))
                return

            reaction_data = await self.handle_reaction(message_id, reaction_type)
            if reaction_data:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'reaction_message',
                        **reaction_data
                    }
                )
            return

        content = text_data_json.get('message', '').strip()
        images = text_data_json.get('images', [])
        parent_message_id = text_data_json.get('reply_to')

        # print(f"Parsed message: content={content}, images={len(images) if images else 0}")
        user = self.scope['user']
        # print(f"User: {user.username}")

        # Validate message content
        if not content and not images:
            # print("Empty message and no images")
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Cannot send empty message without images.'}))
            return

        # Retrieve target info
        target_info = await self.get_target()
        if not target_info:
            # print(f"Invalid discussion type or target not found: {self.discussion_type}")
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Invalid discussion type or target not found.'}))
            return

        # print(f"Found target: {target_info['name']}")

        # Create and save the message with images
        try:
            message_id = await self.create_message(content, user, target_info, images, parent_message_id)
            message_data = await self.get_message_with_images(message_id)
        except Exception as e:
            await self.send(text_data=json.dumps({'type': 'error', 'message': f'Failed to create message: {str(e)}'}))
            return

        # Broadcast the message to the group
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'chat_message',
                **message_data
            }
        )
        
        # Broadcast unseen count updates to other participants
        await self.broadcast_unseen_count_update(user.id)

    async def chat_message(self, event):
        # Send the message data back to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'id': event.get('id'),
            'message': event.get('message', ''),
            'username': event.get('username', ''),
            'timestamp': event.get('timestamp', ''),
            'images': event.get('images', []),
            'reactions': event.get('reactions', {}),
            'reply_to': event.get('reply_to'),
            # Status fields
            'status': event.get('status', 'sent'),
            'delivered_at': event.get('delivered_at'),
            'seen_at': event.get('seen_at'),
            'overall_status': event.get('overall_status', 'sent')
        }))

    async def send_initial_messages(self):
        try:
            # Fetch existing messages from the database
            messages = await database_sync_to_async(self.get_past_messages)()

            # Send the messages as a batch to the client
            await self.send(text_data=json.dumps({
                'type': 'initial_messages',
                'messages': messages,
            }))
            # print each message sent with all fields
        except Exception:
            pass
            # Send empty messages list on error to prevent connection drop
            await self.send(text_data=json.dumps({
                'type': 'initial_messages',
                'messages': [],
            }))

    def get_past_messages(self):
        try:
            # Retrieve messages ordered by timestamp with optimized queries
            if self.discussion_type == 'program':
                messages = Message.objects.filter(
                    program_id=self.discussion_id,
                    channel=self.channel
                ).select_related('user', 'parent_message', 'parent_message__user').prefetch_related(
                    'message_images', 'reaction', 'read_statuses__user'
                ).order_by('timestamp')[:50]
            elif self.discussion_type == 'subject':
                messages = Message.objects.filter(
                    subject_id=self.discussion_id,
                    channel=self.channel
                ).select_related('user', 'parent_message', 'parent_message__user').prefetch_related(
                    'message_images', 'reaction', 'read_statuses__user'
                ).order_by('timestamp')[:50]
            else:
                messages = Message.objects.none()

            serialized_messages = []
            for msg in messages:
                # Reactions
                reactions = {}
                try:
                    reaction_counts = msg.reaction.values('reaction_type').annotate(
                        count=Count('reaction_type')
                    )
                    for reaction in reaction_counts:
                        reactions[reaction['reaction_type']] = reaction['count']
                except:
                    reactions = {}

                # Images
                images = []
                try:
                    images = [img.image.url for img in msg.message_images.all()]
                except:
                    images = []

                # Reply info
                reply_to = None
                if msg.parent_message:
                    try:
                        reply_to = {
                            'id': msg.parent_message.id,
                            'content': msg.parent_message.content[:100],
                            'username': msg.parent_message.user.username
                        }
                    except:
                        reply_to = None

                # Read statuses
                read_statuses = []
                delivered_to_count = 0
                seen_by_count = 0
                if msg.user == self.scope['user']:
                    try:
                        for status in msg.read_statuses.select_related('user').all():
                            read_statuses.append({
                                'username': status.user.username,   
                                'delivered_at': status.delivered_at.isoformat() if status.delivered_at else None,
                                'seen_at': status.seen_at.isoformat() if status.seen_at else None
                            })
                            if status.delivered_at:
                                delivered_to_count += 1
                            if status.seen_at:
                                seen_by_count += 1
                    except Exception as e:
                        pass

                overall_status = getattr(msg, 'status', 'sent')

                serialized_messages.append({
                    'id': msg.id,
                    'message': msg.content,
                    'username': msg.user.username,
                    'timestamp': msg.timestamp.isoformat(),
                    'images': images,
                    'reactions': reactions,
                    'reply_to': reply_to,
                    'status': overall_status,
                    'delivered_at': msg.delivered_at.isoformat() if getattr(msg, 'delivered_at', None) else None,
                    'seen_at': msg.seen_at.isoformat() if getattr(msg, 'seen_at', None) else None,
                    'overall_status': overall_status,
                    'read_statuses': read_statuses,  # Only populated for own messages
                    'seen_by_count': seen_by_count,
                    'delivered_to_count': delivered_to_count
                })
        except Exception as e:
            pass
            serialized_messages = []

        return serialized_messages
    @database_sync_to_async
    def handle_reaction(self, message_id, reaction_type):
        try:
            message = Message.objects.get(id=message_id)
            user = self.scope['user']
            
            # Check if user already reacted with this type
            existing_reaction = MessageReaction.objects.filter(
                message=message,
                user=user,
                reaction_type=reaction_type
            ).first()

            if existing_reaction:
                # Remove reaction if it already exists
                existing_reaction.delete()
                action = 'removed'
            else:
                # Create new reaction
                MessageReaction.objects.create(
                    message=message,
                    user=user,
                    reaction_type=reaction_type
                )
                action = 'added'

            # Get updated reaction counts
            reaction_counts = {}
            for reaction in MessageReaction.REACTION_CHOICES:
                count = MessageReaction.objects.filter(
                    message=message,
                    reaction_type=reaction[0]
                ).count()
                if count > 0:
                    reaction_counts[reaction[0]] = count

            return {
                'type': 'reaction_update',
                'message_id': message_id,
                'reaction_type': reaction_type,
                'action': action,
                'user': user.username,
                'reaction_counts': reaction_counts
            }
        except Message.DoesNotExist:
            return None

    async def reaction_message(self, event):
        # Send reaction update to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'reaction_update',
            'message_id': event['message_id'],
            'reaction_type': event['reaction_type'],
            'action': event['action'],
            'user': event['user'],
            'reaction_counts': event['reaction_counts']
        }))

    @database_sync_to_async
    def get_message_with_images_and_reactions(self, message_id):
        message = Message.objects.get(id=message_id)
        images = [img.image.url for img in message.message_images.all()]
        
        # Get reaction counts
        reaction_counts = {}
        for reaction in MessageReaction.REACTION_CHOICES:
            count = message.reaction.filter(reaction_type=reaction[0]).count()
            if count > 0:
                reaction_counts[reaction[0]] = count

        return {
            'id': message.id,
            'message': message.content,
            'username': message.user.username,
            'timestamp': message.timestamp.isoformat(),
            'images': images,
            'reactions': reaction_counts
        }

    async def mark_messages_as_delivered(self):
        """Automatically mark undelivered messages as delivered when user connects"""
        user = self.scope['user']
        
        # Get recent messages that haven't been delivered to this user
        recent_messages = await self.get_undelivered_messages(user)
        
        if recent_messages:
            # Mark them as delivered
            await self.bulk_mark_delivered(recent_messages, user)
            
            # Broadcast delivery status updates
            message_ids = [msg.id for msg in recent_messages]
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'message_status_update',
                    'message_ids': message_ids,
                    'status': 'delivered',
                    'user_id': user.id,
                    'username': user.username
                }
            )

    @database_sync_to_async
    def get_undelivered_messages(self, user):
        """Get messages that haven't been delivered to this user"""
        
        from datetime import timedelta
        
        # Get messages from last 7 days to avoid marking very old messages
        cutoff_date = timezone.now() - timedelta(days=7)
        
        if self.discussion_type == 'program':
            messages = Message.objects.filter(
                program_id=self.discussion_id,
                channel=self.channel,
                timestamp__gte=cutoff_date
            ).exclude(user=user)
        else:
            messages = Message.objects.filter(
                subject_id=self.discussion_id,
                channel=self.channel,
                timestamp__gte=cutoff_date
            ).exclude(user=user)
        

        

        # Filter messages that haven't been delivered to this user
        undelivered = []
        for message in messages:
            try:
                status_obj = MessageStatus.objects.get(message=message, user=user)

                if status_obj.delivered_at == None:
                    undelivered.append(message)
            except MessageStatus.DoesNotExist:
                undelivered.append(message)
        # Get undelivered messages
        return undelivered

    @database_sync_to_async
    def bulk_mark_delivered(self, messages, user):
        """Mark multiple messages as delivered for a user"""
        for message in messages:
            status_obj, created = MessageStatus.objects.get_or_create(
                message=message,
                user=user
            )
            if not status_obj.delivered_at:
                status_obj.mark_as_delivered()

    @database_sync_to_async
    def get_discussion_participants(self):
        """Get all participants in this discussion"""
        try:
            if self.discussion_type == 'program':
                program = Program.objects.get(id=self.discussion_id)
                return list(program.users.all())
            elif self.discussion_type == 'subject':
                subject = Subject.objects.get(id=self.discussion_id)
                return list(subject.users.all())
            return []
        except (Program.DoesNotExist, Subject.DoesNotExist):
            return []
    
    async def broadcast_unseen_count_update(self, message_sender_id):
        """Broadcast unseen count updates to all participants except the sender - OPTIMIZED"""
        participants = await self.get_discussion_participants()
        
        # OPTIMIZATION: Batch calculate unseen counts for all participants at once
        participant_ids = [p.id for p in participants if p.id != message_sender_id]
        
        if not participant_ids:
            return
            
        # Calculate unseen counts for all participants in a single query
        unseen_counts_map = await self.batch_calculate_unseen_counts(participant_ids)
        
        # Get discussion name for the notification
        discussion_name = await self.get_discussion_name()
        
        # Broadcast updates to all participants
        for participant in participants:
            if participant.id != message_sender_id:
                unseen_count = unseen_counts_map.get(participant.id, 0)
                user_channel = f"user_{participant.id}_notifications"
                
                # Broadcast to user's personal notification channel
                await self.channel_layer.group_send(
                    user_channel,
                    {
                        'type': 'discussion_unseen_count_update',
                        'discussion_type': self.discussion_type,
                        'discussion_id': self.discussion_id,
                        'channel': self.channel,
                        'discussion_name': discussion_name,
                        'unseen_count': unseen_count,
                        'increment': True  # This is a new message
                    }
                )
    
    @database_sync_to_async
    def batch_calculate_unseen_counts(self, participant_ids):
        """OPTIMIZED: Calculate unseen counts for multiple users in a single query"""
        from django.db.models import Count, Q, Case, When, IntegerField
        
        if self.discussion_type == 'program':
            # Single query to get unseen counts for all participants
            unseen_counts = Message.objects.filter(
                program_id=self.discussion_id,
                channel=self.channel
            ).exclude(
                user_id__in=participant_ids  # Exclude messages from any of the participants
            ).values('id').annotate(
                **{
                    f'unseen_by_{pid}': Case(
                        When(
                            read_statuses__user_id=pid,
                            read_statuses__seen_at__isnull=False,
                            then=0
                        ),
                        default=1,
                        output_field=IntegerField()
                    )
                    for pid in participant_ids
                }
            ).aggregate(
                **{
                    f'total_unseen_{pid}': Count(
                        Case(
                            When(**{f'unseen_by_{pid}': 1}, then=1),
                            output_field=IntegerField()
                        )
                    )
                    for pid in participant_ids
                }
            )
            
        elif self.discussion_type == 'subject':
            # Single query to get unseen counts for all participants  
            unseen_counts = Message.objects.filter(
                subject_id=self.discussion_id,
                channel=self.channel
            ).exclude(
                user_id__in=participant_ids  # Exclude messages from any of the participants
            ).values('id').annotate(
                **{
                    f'unseen_by_{pid}': Case(
                        When(
                            read_statuses__user_id=pid,
                            read_statuses__seen_at__isnull=False,
                            then=0
                        ),
                        default=1,
                        output_field=IntegerField()
                    )
                    for pid in participant_ids
                }
            ).aggregate(
                **{
                    f'total_unseen_{pid}': Count(
                        Case(
                            When(**{f'unseen_by_{pid}': 1}, then=1),
                            output_field=IntegerField()
                        )
                    )
                    for pid in participant_ids
                }
            )
        else:
            return {}
        
        # Convert to simple dict mapping user_id -> unseen_count
        return {
            pid: unseen_counts.get(f'total_unseen_{pid}', 0)
            for pid in participant_ids
        }

    @database_sync_to_async
    def calculate_unseen_count_for_user_fallback(self, user):
        """FIXED: Calculate accurate unseen count for user considering proper message status"""
        if self.discussion_type == 'program':
            # Count messages that user hasn't seen (no MessageStatus entry with seen_at)
            unseen_count = Message.objects.filter(
                program_id=self.discussion_id,
                channel=self.channel
            ).exclude(
                Q(user=user)  # Exclude own messages
            ).exclude(
                # Exclude messages that have been seen by this user
                Q(read_statuses__user=user, read_statuses__seen_at__isnull=False)
            ).count()
        elif self.discussion_type == 'subject':
            # Count messages that user hasn't seen (no MessageStatus entry with seen_at)
            unseen_count = Message.objects.filter(
                subject_id=self.discussion_id,
                channel=self.channel
            ).exclude(
                Q(user=user)  # Exclude own messages
            ).exclude(
                # Exclude messages that have been seen by this user
                Q(read_statuses__user=user, read_statuses__seen_at__isnull=False)
            ).count()
        else:
            unseen_count = 0
        
        return unseen_count
    
    async def handle_mark_seen(self, data):
        """Handle marking messages as seen and broadcast unseen count updates"""
        message_ids = data.get('message_ids', [])
        user = self.scope['user']
        if not message_ids:
            return
        updated_messages = []
        for message_id in message_ids:
            try:
                message = await self.get_message_for_status_update(message_id)
                if message and message.user != user:  # Only mark messages from other users
                    status_updated = await self.mark_message_seen(message, user)
                    if status_updated:
                        updated_messages.append(message_id)
            except Exception as e:
                logger.error(f"Error marking message {message_id} as seen: {e}")
        
        if updated_messages:
            # Broadcast status update
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'message_status_update',
                    'message_ids': updated_messages,
                    'status': 'seen',
                    'user_id': user.id,
                    'username': user.username
                }
            )
            
            # Broadcast unseen count decrease to the user who marked as seen
            user_channel = f"user_{user.id}_notifications"
            await self.channel_layer.group_send(
                user_channel,
                {
                    'type': 'discussion_unseen_count_update',
                    'discussion_type': self.discussion_type,
                    'discussion_id': self.discussion_id,
                    'channel': self.channel,
                    'unseen_count': await self.calculate_unseen_count_for_user_fallback(user),
                    'increment': False  # This is marking as seen, so decrement
                }
            )

    @database_sync_to_async
    def get_message_for_status_update(self, message_id):
        """Get message for status update"""
        try:
            if self.discussion_type == 'program':
                return Message.objects.get(
                    id=message_id,
                    program_id=self.discussion_id,
                    channel=self.channel
                )
            elif self.discussion_type == 'subject':
                return Message.objects.get(
                    id=message_id,
                    subject_id=self.discussion_id,
                    channel=self.channel
                )
            return None
        except Message.DoesNotExist:
            return None
    
    @database_sync_to_async
    def mark_message_seen(self, message, user):
        """Mark a message as seen for a specific user"""
        try:
            status, created = MessageStatus.objects.get_or_create(
                message=message,
                user=user
            )
            if not status.seen_at:
                status.mark_as_seen()
                return True
            return False
        except Exception as e:
            logger.error(f"Error marking message as seen: {e}")
            return False
    
    async def message_status_update(self, event):
        """Handle message status update events"""
        await self.send(text_data=json.dumps({
            'type': 'message_status_update',
            'message_ids': event['message_ids'],
            'status': event['status'],
            'user_id': event['user_id'],
            'username': event.get('username', '')
        }))

    @database_sync_to_async
    def get_discussion_name(self):
        """Get the name of the current discussion"""
        try:
            if self.discussion_type == 'program':
                program = Program.objects.get(id=self.discussion_id)
                return program.name
            elif self.discussion_type == 'subject':
                subject = Subject.objects.get(id=self.discussion_id)
                return subject.name
            return ''
        except (Program.DoesNotExist, Subject.DoesNotExist):
            return ''


    async def message_status_update(self, event):
        """Handle message status update events and send to the client"""
        await self.send(text_data=json.dumps({
            'type': 'message_status_update',
            'message_ids': event['message_ids'],
            'status': event['status'],
            'user_id': event['user_id'],
            'username': event.get('username', '')
        }))
    
    async def mark_messages_as_seen(self):
        """Mark unseen messages as seen when user connects"""
        user = self.scope['user']
        
        # Get recent messages that haven't been seen by this user
        recent_messages = await self.get_unseen_messages(user)
        
        if recent_messages:
            # Mark them as seen
            await self.bulk_mark_seen(recent_messages, user)
            
            # Broadcast seen status updates to the group
            message_ids = [msg.id for msg in recent_messages]
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'message_status_update',
                    'message_ids': message_ids,
                    'status': 'seen',
                    'user_id': user.id,
                    'username': user.username
                }
            )
            
            # Also send the status update directly to the connecting user
            await self.send(text_data=json.dumps({
                'type': 'message_status_update',
                'message_ids': message_ids,
                'status': 'seen',
                'user_id': user.id,
                'username': user.username
            }))

    async def get_unseen_messages(self, user):
        """Get messages that haven't been seen by the user"""
        cutoff = timezone.now() - timedelta(days=7)
        
        # Build the query based on discussion type
        query = {
            'channel': self.channel,
            'timestamp__gte': cutoff,
        }
        if self.discussion_type == 'program':
            query['program_id'] = self.discussion_id
        elif self.discussion_type == 'subject':
            query['subject_id'] = self.discussion_id
        else:
            return []

        messages = await database_sync_to_async(
            lambda: list(Message.objects.filter(
                **query
            ).exclude(
                read_statuses__user=user,
                read_statuses__seen_at__isnull=False
            ).exclude(
                user=user  # Exclude user's own messages
            ).select_related('user', 'parent_message').order_by('timestamp')[:50])
        )()
        return messages

    async def bulk_mark_seen(self, messages, user):
        """Bulk mark messages as seen for a user"""
        message_ids = [msg.id for msg in messages]
        await database_sync_to_async(
            lambda: [
                status.mark_as_seen()
                for status in MessageStatus.objects.filter(
                    message_id__in=message_ids,
                    user=user
                )
            ]
        )()

class PersonalMessageConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Extract token from query string
        query_params = parse_qs(self.scope['query_string'].decode())
        token = query_params.get('token', [None])[0]

        if token:
            try:
                validated_token = AccessToken(token)
                user_id = validated_token['user_id']
                user = await database_sync_to_async(CustomUser.objects.get)(id=user_id)
                self.scope['user'] = user
            except Exception as e:
                await self.close(code=4001, reason="Invalid token.")
                return
        else:
            self.scope['user'] = AnonymousUser()

        # Check if the user is authenticated
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close(code=4001, reason='Authentication required.')
            return

        # Get the chat room name (combination of both user IDs)
        self.other_user_id = self.scope['url_route']['kwargs'].get('user_id')
        if not self.other_user_id:
            await self.close(code=4002, reason='Other user ID not provided.')
            return

        # Create a unique room name by sorting user IDs
        user_ids = sorted([str(user.id), str(self.other_user_id)])
        self.room_name = f"personal_chat_{user_ids[0]}_{user_ids[1]}"

        # Join the room
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )

        await self.accept()
        
        # Send initial messages
        await self.send_initial_messages()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_name'):
            await self.channel_layer.group_discard(
                self.room_name,
                self.channel_name
            )

    @database_sync_to_async
    def create_personal_message(self, content, sender, receiver, images=None):
        message = PersonalMessage.objects.create(
            sender=sender,
            receiver=receiver,
            content=content,
            timestamp=timezone.now()
        )

        # Handle image uploads if present
        if images:
            for image_data in images:
                try:
                    # Extract the base64 data
                    format, imgstr = image_data.split(';base64,')
                    ext = format.split('/')[-1]
                    
                    # Create a ContentFile from the base64 data
                    image_content = ContentFile(base64.b64decode(imgstr), name=f'personal_message_image_{message.id}.{ext}')
                    
                    # Create PersonalMessageImage instance
                    PersonalMessageImage.objects.create(
                        message=message,
                        image=image_content
                    )
                except Exception as e:
                    logger.error(f"Error saving image: {str(e)}")

        return message.id

    @database_sync_to_async
    def get_message_with_images(self, message_id):
        message = PersonalMessage.objects.get(id=message_id)
        images = [img.image.url for img in message.message_images.all()]
        
        # Get reaction counts
        reaction_counts = {}
        for reaction in PersonalMessageReaction.REACTION_CHOICES:
            count = message.reaction.filter(reaction_type=reaction[0]).count()
            if count > 0:
                reaction_counts[reaction[0]] = count
                
        return {
            'id': message.id,
            'message': message.content,
            'sender': message.sender.username,
            'receiver': message.receiver.username,
            'timestamp': message.timestamp.isoformat(),
            'images': images,
            'reactions': reaction_counts,
            # Status fields
            'status': message.status,
            'delivered_at': message.delivered_at.isoformat() if message.delivered_at else None,
            'seen_at': message.seen_at.isoformat() if message.seen_at else None
        }

    async def receive(self, text_data):
        try:
            # print(f"Received data: {text_data}")
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')

            # Handle message seen events
            if message_type == 'mark_seen':
                await self.handle_personal_mark_seen(text_data_json)
                return

            if message_type == 'reaction':
                # Handle reaction
                message_id = text_data_json.get('message_id')
                reaction_type = text_data_json.get('reaction_type')
                
                if not message_id or not reaction_type:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Missing message_id or reaction_type'
                    }))
                    return

                reaction_data = await self.handle_reaction(message_id, reaction_type)
                if reaction_data:
                    await self.channel_layer.group_send(
                        self.room_name,
                        {
                            'type': 'reaction_message',
                            **reaction_data
                        }
                    )
                return

            content = text_data_json.get('message', '').strip()
            images = text_data_json.get('images', [])

            if not content and not images:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Cannot send empty message without images.'
                }))
                return

            sender = self.scope['user']
            receiver = await database_sync_to_async(CustomUser.objects.get)(id=self.other_user_id)

            try:
                message_id = await self.create_personal_message(content, sender, receiver, images)
                message_data = await self.get_message_with_images(message_id)
                
                # Send to the group
                await self.channel_layer.group_send(
                    self.room_name,
                    {
                        'type': 'chat_message',
                        **message_data
                    }
                )
                
                # Broadcast unseen count update to the receiver
                receiver_channel = f"user_{receiver.id}_notifications"
                await self.channel_layer.group_send(
                    receiver_channel,
                    {
                        'type': 'personal_unseen_count_update',
                        'sender_id': sender.id,
                        'sender_username': sender.username,
                        'increment': True  # This is a new message
                    }
                )
            except Exception as e:
                # print(f"Error creating message: {str(e)}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Failed to create message: {str(e)}'
                }))
                return

        except json.JSONDecodeError as e:
            # print(f"JSON decode error: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format.'
            }))
        except Exception as e:
            # print(f"Unexpected error: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Unexpected error: {str(e)}'
            }))

    async def chat_message(self, event):
        # Send the message data back to WebSocket
        try:
            await self.send(text_data=json.dumps({
                'type': 'chat_message',
                'id': event.get('id'),
                'message': event.get('message', ''),
                'sender': event.get('sender', ''),
                'receiver': event.get('receiver', ''),
                'timestamp': event.get('timestamp', ''),
                'images': event.get('images', []),
                'reactions': event.get('reactions', {}),
                # Status fields
                'status': event.get('status', 'sent'),
                'delivered_at': event.get('delivered_at'),
                'seen_at': event.get('seen_at')
            }))
        except Exception as e:
            logger.error(f"Error sending chat message: {str(e)}")

    async def send_initial_messages(self):
        messages = await database_sync_to_async(self.get_past_messages)()
        await self.send(text_data=json.dumps({
            'type': 'initial_messages',
            'messages': messages,
        }))

    def get_past_messages(self):
        user_ids = [self.scope['user'].id, int(self.other_user_id)]
        messages = PersonalMessage.objects.filter(
            sender_id__in=user_ids,
            receiver_id__in=user_ids
        ).order_by('timestamp')

        serialized_messages = [
            {
                'id': msg.id,
                'message': msg.content,
                'sender': msg.sender.username,
                'receiver': msg.receiver.username,
                'timestamp': msg.timestamp.isoformat(),
                'images': [img.image.url for img in msg.message_images.all()],
                'reactions': {
                    reaction[0]: msg.reaction.filter(reaction_type=reaction[0]).count()
                    for reaction in PersonalMessageReaction.REACTION_CHOICES
                    if msg.reaction.filter(reaction_type=reaction[0]).exists()
                },
                # Status fields
                'status': msg.status,
                'delivered_at': msg.delivered_at.isoformat() if msg.delivered_at else None,
                'seen_at': msg.seen_at.isoformat() if msg.seen_at else None
            }
            for msg in messages
        ]
        return serialized_messages

    @database_sync_to_async
    def handle_reaction(self, message_id, reaction_type):
        try:
            message = PersonalMessage.objects.get(id=message_id)
            user = self.scope['user']
            
            # Check if user already reacted with this type
            existing_reaction = PersonalMessageReaction.objects.filter(
                message=message,
                user=user,
                reaction_type=reaction_type
            ).first()

            if existing_reaction:
                # Remove reaction if it already exists
                existing_reaction.delete()
                action = 'removed'
            else:
                # Create new reaction
                PersonalMessageReaction.objects.create(
                    message=message,
                    user=user,
                    reaction_type=reaction_type
                )
                action = 'added'

            # Get updated reaction counts
            reaction_counts = {}
            for reaction in PersonalMessageReaction.REACTION_CHOICES:
                count = PersonalMessageReaction.objects.filter(
                    message=message,
                    reaction_type=reaction[0]
                ).count()
                if count > 0:
                    reaction_counts[reaction[0]] = count

            return {
                'type': 'reaction_update',
                'message_id': message_id,
                'reaction_type': reaction_type,
                'action': action,
                'user': user.username,
                'reaction_counts': reaction_counts
            }
        except PersonalMessage.DoesNotExist:
            return None

    async def reaction_message(self, event):
        # Send reaction update to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'reaction_update',
            'message_id': event['message_id'],
            'reaction_type': event['reaction_type'],
            'action': event['action'],
            'user': event['user'],
            'reaction_counts': event['reaction_counts']
        }))
    
    async def handle_personal_mark_seen(self, data):
        """Handle marking personal messages as seen"""
        message_ids = data.get('message_ids', [])
        user = self.scope['user']
        
        if not message_ids:
            return
        
        updated_messages = []
        for message_id in message_ids:
            try:
                message = await self.get_personal_message_for_status_update(message_id)
                if message and message.sender_id != user.id:  # Only mark messages from other user
                    status_updated = await self.mark_personal_message_seen(message_id)
                    if status_updated:
                        updated_messages.append(message_id)
            except Exception as e:
                logger.error(f"Error marking personal message {message_id} as seen: {e}")
        
        if updated_messages:
            await self.channel_layer.group_send(
                self.room_name,
                {
                    'type': 'personal_message_status_update',
                    'message_ids': updated_messages,
                    'status': 'seen',
                    'user_id': user.id
                }
            )
            
            # Broadcast unseen count decrease to the user who marked as seen
            user_channel = f"user_{user.id}_notifications"
            await self.channel_layer.group_send(
                user_channel,
                {
                    'type': 'personal_unseen_count_update',
                    'sender_id': int(self.other_user_id),
                    'sender_username': '',
                    'increment': False,
                    'count': len(updated_messages)
                }
            )

    @database_sync_to_async
    def get_personal_message_for_status_update(self, message_id):
        """Get personal message for status update"""
        try:
            user_ids = [self.scope['user'].id, int(self.other_user_id)]
            return PersonalMessage.objects.get(
                id=message_id,
                sender_id__in=user_ids,
                receiver_id__in=user_ids
            )
        except PersonalMessage.DoesNotExist:
            return None

    async def mark_personal_message_seen(self, message_id):
        """Mark a personal message as seen (async safe)"""
        try:
            return await self._mark_personal_message_seen_db(message_id)
        except Exception as e:
            logger.error(f"Error marking personal message as seen: {e}")
            return False

    @database_sync_to_async
    def _mark_personal_message_seen_db(self, message_id):
        """Mark a personal message as seen in the database"""
        try:
            message = PersonalMessage.objects.get(id=message_id)
            if message.status in ['sent', 'delivered']:
                message.status = 'seen'
                message.seen_at = timezone.now()
                message.save(update_fields=['status', 'seen_at'])
                return True
            return False
        except PersonalMessage.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error in _mark_personal_message_seen_db: {e}")
            return False

    async def personal_message_status_update(self, event):
        """Handle personal message status update broadcasts"""
        await self.send(text_data=json.dumps({
            'type': 'personal_message_status_update',
            'message_ids': event['message_ids'],
            'status': event['status'],
            'user_id': event['user_id']
        }))

class NotificationConsumer(AsyncWebsocketConsumer):
    """Consumer for handling real-time notifications including unseen count updates"""
    
    async def connect(self):
        # Extract token from query string
        query_params = parse_qs(self.scope['query_string'].decode())
        token = query_params.get('token', [None])[0]

        if token:
            try:
                validated_token = AccessToken(token)
                user_id = validated_token['user_id']
                user = await database_sync_to_async(CustomUser.objects.get)(id=user_id)
                self.scope['user'] = user
                self.user_id = user_id
                logger.debug(f"NotificationConsumer: Authenticated user {user.username} (ID: {user_id})")
            except Exception as e:
                logger.error(f"NotificationConsumer: Authentication failed: {e}")
                await self.close(code=4001, reason="Invalid token.")
                return
        else:
            logger.warning(f"NotificationConsumer: No token provided")
            await self.close(code=4001, reason="Token required.")
            return

        # Join user's personal notification group
        self.notification_group = f"user_{self.user_id}_notifications"
        await self.channel_layer.group_add(
            self.notification_group,
            self.channel_name
        )
        logger.debug(f"NotificationConsumer: Added user {self.user_id} to group {self.notification_group}")

        await self.accept()
        logger.debug(f"NotificationConsumer: Connection accepted for user {self.user_id}")

    async def disconnect(self, close_code):
        # Leave the notification group
        if hasattr(self, 'notification_group'):
            await self.channel_layer.group_discard(
                self.notification_group,
                self.channel_name
            )
            logger.debug(f"NotificationConsumer: User {getattr(self, 'user_id', 'unknown')} disconnected from {self.notification_group}")
        else:
            logger.debug(f"NotificationConsumer: Connection closed (code: {close_code})")

    async def receive(self, text_data):
        # Handle any client messages if needed
        try:
            data = json.loads(text_data)
            # You can add handlers for client requests here if needed
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Invalid JSON format.'}))

    async def discussion_unseen_count_update(self, event):
        """Handle discussion unseen count updates"""
        logger.debug(f"NotificationConsumer: Sending discussion unseen count update to user {self.user_id}")
        await self.send(text_data=json.dumps({
            'type': 'discussion_unseen_count_update',
            'discussion_type': event['discussion_type'],
            'discussion_id': event['discussion_id'],
            'channel': event['channel'],
            'discussion_name': event.get('discussion_name', ''),
            'unseen_count': event.get('unseen_count', 0),
            'increment': event['increment']
        }))

    async def personal_unseen_count_update(self, event):
        """Handle personal chat unseen count updates"""
        logger.debug(f"NotificationConsumer: Sending personal unseen count update to user {self.user_id}")
        await self.send(text_data=json.dumps({
            'type': 'personal_unseen_count_update',
            'sender_id': event['sender_id'],
            'sender_username': event.get('sender_username', ''),
            'increment': event['increment'],
            'count': event.get('count', 1)
        }))

    @database_sync_to_async
    def get_discussion_name(self):
        """Get the name of the current discussion"""
        try:
            if self.discussion_type == 'program':
                program = Program.objects.get(id=self.discussion_id)
                return program.name
            elif self.discussion_type == 'subject':
                subject = Subject.objects.get(id=self.discussion_id)
                return subject.name
            return ''
        except (Program.DoesNotExist, Subject.DoesNotExist):
            return ''
