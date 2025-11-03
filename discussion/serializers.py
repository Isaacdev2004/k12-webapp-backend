from rest_framework import serializers
from .models import Message, MessageImage, MessageReaction, MessageStatus, PersonalMessage
from accounts.models import CustomUser
from api.models import Program, Subject


class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email']


class ProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = ['id', 'name']


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name']


class MessageStatusSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    
    class Meta:
        model = MessageStatus
        fields = ['user', 'delivered_at', 'seen_at']


class MessageSerializer(serializers.ModelSerializer):
    CustomUser = CustomUserSerializer()
    program = ProgramSerializer()
    subject = SubjectSerializer()
    read_statuses = MessageStatusSerializer(many=True, read_only=True)
    
    # Add computed fields for overall status
    overall_status = serializers.SerializerMethodField()
    seen_by_count = serializers.SerializerMethodField()
    delivered_to_count = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'content', 'timestamp', 'CustomUser', 'program', 'subject', 
            'channel', 'status', 'delivered_at', 'seen_at', 'read_statuses',
            'overall_status', 'seen_by_count', 'delivered_to_count'
        ]

    def get_overall_status(self, obj):
        """Calculate overall status for group messages"""
        if hasattr(self.context.get('request'), 'user'):
            current_user = self.context['request'].user
            # If it's the sender's own message, return the message status
            if obj.user == current_user:
                return obj.status
        
        # For recipients, check their individual status
        if hasattr(self.context.get('request'), 'user'):
            current_user = self.context['request'].user
            try:
                user_status = MessageStatus.objects.get(message=obj, user=current_user)
                if user_status.seen_at:
                    return 'seen'
                elif user_status.delivered_at:
                    return 'delivered'
            except MessageStatus.DoesNotExist:
                pass
        
        return 'sent'

    def get_seen_by_count(self, obj):
        """Get count of users who have seen this message"""
        return obj.read_statuses.filter(seen_at__isnull=False).count()

    def get_delivered_to_count(self, obj):
        """Get count of users who have received this message"""
        return obj.read_statuses.filter(delivered_at__isnull=False).count()


class PersonalMessageSerializer(serializers.ModelSerializer):
    sender = CustomUserSerializer(read_only=True)
    receiver = CustomUserSerializer(read_only=True)

    class Meta:
        model = PersonalMessage
        fields = [
            'id', 'content', 'timestamp', 'sender', 'receiver',
            'status', 'delivered_at', 'seen_at'
        ]


class MessageImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageImage
        fields = ['id', 'image', 'message']


class ReactionSerializer(serializers.ModelSerializer):
    CustomUser = CustomUserSerializer()

    class Meta:
        model = MessageReaction
        fields = ['id', 'CustomUser', 'reaction_type', 'message']
