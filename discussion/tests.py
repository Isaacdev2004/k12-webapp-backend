from django.test import TestCase

# Create your tests here.
# /Volumes/projects/Aakhyaan/aakhyaan/server/discussion/tests.py

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from api.models import Program,Subject
from discussion.routing import websocket_urlpatterns
from aakhyaan.routing import application
import json

User = get_user_model()


class DiscussionConsumerTests(TransactionTestCase):
    async def test_subject_consumer(self):
        # Create a user and subject
        user = User.objects.create_user(username='testuser', password='password')
        subject = Subject.objects.create(name='Test Subject', program=None)  # Adjust as per your models

        # Authenticate the user
        communicator = WebsocketCommunicator(
            application,
            f"/ws/discussion/subject/{subject.id}/"
        )
        # Manually set the user in the scope
        communicator.scope['user'] = user

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Send a message
        await communicator.send_to(text_data=json.dumps({
            'action': 'send_message',
            'channel': 'discussion',
            'message': 'Hello, this is a test message.',
            'images': []
        }))

        # Receive the broadcasted message
        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data['action'], 'new_message')
        self.assertEqual(data['message'], 'Hello, this is a test message.')
        self.assertEqual(data['user'], 'testuser')

        # Disconnect
        await communicator.disconnect()

    async def test_program_consumer(self):
        # Create a user and program
        user = User.objects.create_user(username='testuser', password='password')
        program = Program.objects.create(name='Test Program')  # Adjust as per your models

        # Authenticate the user
        communicator = WebsocketCommunicator(
            application,
            f"/ws/discussion/program/{program.id}/"
        )
        # Manually set the user in the scope
        communicator.scope['user'] = user

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Send a message
        await communicator.send_to(text_data=json.dumps({
            'action': 'send_message',
            'channel': 'motivation',
            'message': 'Stay motivated!',
            'images': []
        }))

        # Receive the broadcasted message
        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data['action'], 'new_message')
        self.assertEqual(data['message'], 'Stay motivated!')
        self.assertEqual(data['user'], 'testuser')

        # Disconnect
        await communicator.disconnect()
