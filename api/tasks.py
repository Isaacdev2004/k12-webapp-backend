import os
import logging
import requests
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone
from django.db.models import Q

from accounts.models import DeviceToken, CustomUser
from .models import LiveClass, MCQ, MockTest

logger = logging.getLogger(__name__)


def _get_fcm_key() -> str:
    return os.environ.get('FCM_SERVER_KEY', '')


def _chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_fcm_to_tokens(self, token_list: list, title: str, body: str, data: dict | None = None):
    if not token_list:
        return {'sent': 0}

    server_key = _get_fcm_key()
    if not server_key:
        logger.warning('FCM_SERVER_KEY not configured')
        return {'sent': 0, 'error': 'missing_key'}

    headers = {
        'Authorization': f'key={server_key}',
        'Content-Type': 'application/json',
    }

    sent = 0
    for batch in _chunk(token_list, 900):  # FCM allows up to 1000 tokens per request
        payload = {
            'registration_ids': batch,
            'notification': {
                'title': title,
                'body': body,
            },
            'data': data or {},
            'priority': 'high',
        }
        try:
            resp = requests.post('https://fcm.googleapis.com/fcm/send', json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            res_json = resp.json()
            sent += res_json.get('success', 0)
        except Exception as e:
            logger.exception('FCM send error: %s', str(e))
    return {'sent': sent}


@shared_task
def notify_manual_to_users(user_ids: list[int], title: str, body: str, data: dict | None = None):
    tokens = list(DeviceToken.objects.filter(user_id__in=user_ids, active=True).values_list('token', flat=True))
    return send_fcm_to_tokens.delay(tokens, title, body, data or {})


@shared_task
def notify_upcoming_live_classes():
    now = timezone.localtime()
    in_five = now + timedelta(minutes=5)
    weekday = now.weekday()  # 0=Monday

    # Live classes that are active today and start in ~5 minutes
    classes = LiveClass.objects.filter(
        is_active=True,
    ).filter(
        Q(days_of_week__contains=[weekday]) | Q(day_of_week=weekday)
    )

    to_notify_users = set()
    for live in classes:
        if not live.start_time:
            continue
        today = now.date()
        start_dt = datetime.combine(today, live.start_time).replace(tzinfo=now.tzinfo)
        # handle next-day wrap if needed
        if start_dt < now:
            continue
        if 0 <= (start_dt - in_five).total_seconds() <= 60:  # within a minute of t-5
            to_notify_users.update(live.subject.course.programs.values_list('participant_users__id', flat=True))

    user_ids = [uid for uid in to_notify_users if uid]
    tokens = list(DeviceToken.objects.filter(user_id__in=user_ids, active=True).values_list('token', flat=True))
    if tokens:
        send_fcm_to_tokens.delay(tokens, 'Class starts soon', 'Your live class starts in 5 minutes', {'type': 'live_class_soon'})


@shared_task
def notify_upcoming_tests():
    now = timezone.localtime()
    in_five = now + timedelta(minutes=5)

    # MCQs scheduled
    mcqs = MCQ.objects.filter(is_active=True, scheduled_start_time__range=(now, in_five))
    mock_tests = MockTest.objects.filter(is_active=True, scheduled_start_time__range=(now.date(), in_five.date()))

    user_ids = set()
    for mcq in mcqs:
        user_ids.update(mcq.topic.chapter.subject.programs.values_list('participant_users__id', flat=True))
    for mt in mock_tests:
        user_ids.update(mt.course.programs.values_list('participant_users__id', flat=True))

    user_ids = [uid for uid in user_ids if uid]
    tokens = list(DeviceToken.objects.filter(user_id__in=user_ids, active=True).values_list('token', flat=True))
    if tokens:
        send_fcm_to_tokens.delay(tokens, 'Test starts soon', 'Your test starts in 5 minutes', {'type': 'test_soon'})


