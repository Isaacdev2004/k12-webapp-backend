from django.contrib import admin
from .models import Message, MessageImage, MessageReaction, PersonalMessage, PersonalMessageImage, PersonalMessageReaction, MessageStatus

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'content', 'user', 'channel', 'program', 'subject', 'timestamp', 'status')
    list_filter = ('channel', 'timestamp', 'status')
    search_fields = ('content', 'program__name', 'subject__name')
    ordering = ('-timestamp',)

@admin.register(MessageStatus)
class MessageStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'message', 'user', 'delivered_at', 'seen_at')
    list_filter = ('delivered_at', 'seen_at')
    search_fields = ('message__content', 'user__username')
    ordering = ('-message__timestamp',)

@admin.register(MessageImage)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'image', 'message')
    search_fields = ('image',)

@admin.register(MessageReaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'reaction_type', 'timestamp')
    list_filter = ('reaction_type',)
    search_fields = ('user__username',)

@admin.register(PersonalMessage)
class PersonalMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'receiver', 'content', 'timestamp', 'status')
    list_filter = ('timestamp', 'status')
    search_fields = ('content', 'sender__username', 'receiver__username')
    ordering = ('-timestamp',)

# @admin.register(PersonalMessageImage)
# class PersonalMessageImageAdmin(admin.ModelAdmin):
#     list_display = ('id', 'image', 'message')
#     search_fields = ('image',)

# @admin.register(PersonalMessageReaction)
# class PersonalMessageReactionAdmin(admin.ModelAdmin):
#     list_display = ('id', 'user', 'reaction_type', 'timestamp')
#     list_filter = ('reaction_type',)
#     search_fields = ('user__username',)

