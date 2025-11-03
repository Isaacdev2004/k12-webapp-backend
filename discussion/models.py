from django.db import models
from accounts.models import CustomUser
from api.models import Program, Subject
from django.utils import timezone




class Message(models.Model):
    CHANNEL_CHOICES_PROGRAM = [
        ('notices', 'Notices'),
        ('routine', 'Routine'),
        ('motivation', 'Motivation'),
        ('off_topics', 'Off Topics'),
        ('meme', 'Meme'),
    ]

    CHANNEL_CHOICES_SUBJECT = [
        ('notices', 'Notices'),
        ('off_topics', 'Off Topics'),
        ('discussion', 'Discussion'),
        ('assignments', 'Assignments'),
    ]

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('seen', 'Seen'),
    ]

    program = models.ForeignKey(Program, related_name='messages_program', null=True, blank=True, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, related_name='messages_subject', null=True, blank=True, on_delete=models.CASCADE)
    channel = models.CharField(max_length=50)
    user = models.ForeignKey(CustomUser, related_name='messages', on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    parent_message = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    
    # Message status tracking fields
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent')
    delivered_at = models.DateTimeField(null=True, blank=True)
    seen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        target = self.subject.name if self.subject else self.program.name
        return f"{self.user.username} in {target} - {self.channel}: {self.content[:20]}"

    def get_participants(self):
        """Get all participants for this message's discussion"""
        if self.program:
            return self.program.users.all()
        elif self.subject:
            return self.subject.users.all()
        return CustomUser.objects.none()

    def update_status_to_delivered(self):
        """Update message status to delivered if not already seen"""
        if self.status == 'sent':
            self.status = 'delivered'
            self.delivered_at = timezone.now()
            self.save(update_fields=['status', 'delivered_at'])

    def update_status_to_seen(self):
        """Update message status to seen"""
        if self.status in ['sent', 'delivered']:
            self.status = 'seen'
            self.seen_at = timezone.now()
            self.save(update_fields=['status', 'seen_at'])


class MessageStatus(models.Model):
    """Track message read status for group chats"""
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_statuses')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    delivered_at = models.DateTimeField(null=True, blank=True)
    seen_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['message', 'user']
    
    def __str__(self):
        return f"{self.user.username} - Message {self.message.id} status"

    def mark_as_delivered(self):
        """Mark message as delivered for this user"""
        if not self.delivered_at:
            self.delivered_at = timezone.now()
            self.save(update_fields=['delivered_at'])

    def mark_as_seen(self):
        """Mark message as seen for this user"""
        if not self.seen_at:
            self.seen_at = timezone.now()
            if not self.delivered_at:
                self.delivered_at = timezone.now()
            self.save(update_fields=['seen_at', 'delivered_at'])


class MessageImage(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='message_images')  # Link to the Message
    image = models.ImageField(upload_to='message_images/')  # Image file

    def __str__(self):
        return f"Image for Message ID: {self.message.id}"


class MessageReaction(models.Model):
    REACTION_CHOICES = [
        ('love', '❤️'),
        ('haha', '😂'),
    ]
    message = models.ForeignKey(Message, related_name='reaction', blank=True, on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    reaction_type = models.CharField(max_length=10, choices=REACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} reacted with {self.reaction_type} in message {self.message.id}"


# models.py #PersonalMessage
class PersonalMessage(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('seen', 'Seen'),
    ]

    sender = models.ForeignKey(CustomUser, related_name='sent_personal_messages', on_delete=models.CASCADE)
    receiver = models.ForeignKey(CustomUser, related_name='received_personal_messages', on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Message status tracking fields
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent')
    delivered_at = models.DateTimeField(null=True, blank=True)
    seen_at = models.DateTimeField(null=True, blank=True)

    def update_status_to_delivered(self):
        """Update message status to delivered if not already seen"""
        if self.status == 'sent':
            self.status = 'delivered'
            self.delivered_at = timezone.now()
            self.save(update_fields=['status', 'delivered_at'])

    def update_status_to_seen(self):
        """Update message status to seen"""
        if self.status in ['sent', 'delivered']:
            self.status = 'seen'
            self.seen_at = timezone.now()
            self.save(update_fields=['status', 'seen_at'])


class PersonalMessageImage(models.Model):
    message = models.ForeignKey(PersonalMessage, on_delete=models.CASCADE, related_name='message_images')  # Link to the Message
    image = models.ImageField(upload_to='message_images/') 

    def __str__(self):
        return f"Image for Message ID: {self.message.id}"

class PersonalMessageReaction(models.Model):
    REACTION_CHOICES = [
        ('love', '❤️'),
        ('haha', '😂'),
    ]
    message = models.ForeignKey(PersonalMessage, related_name='reaction', blank=True, on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    reaction_type = models.CharField(max_length=10, choices=REACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} reacted with {self.reaction_type} in message {self.message.id}"


