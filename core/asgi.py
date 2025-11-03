import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path

# Import your WebSocket consumer
from discussion.consumers import BaseDiscussionConsumer, PersonalMessageConsumer, NotificationConsumer
from .middleware import TokenAuthMiddleware

# Initialize the Django ASGI application early to ensure the app is ready
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        TokenAuthMiddleware(
            URLRouter([
                path('ws/discussion/<str:discussion_type>/<int:discussion_id>/<str:channel>/', BaseDiscussionConsumer.as_asgi()),
                path('ws/personal-chat/<int:user_id>/', PersonalMessageConsumer.as_asgi()),
                path('ws/notifications/', NotificationConsumer.as_asgi()),
            ])
        )
    ),
})
