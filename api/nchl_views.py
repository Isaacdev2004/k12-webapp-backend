import logging
from typing import Optional, List

from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Program, Course, Subject, NCHLPayment
from .serializers import NCHLPaymentSerializer
from . import nchl_service

logger = logging.getLogger(__name__)


class NCHLInitiatePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        try:
            user = request.user
            program_id = request.data.get('program_id')
            course_id = request.data.get('course_id')
            subject_ids: Optional[List[int]] = request.data.get('subject_ids') or []
            amount = request.data.get('amount')
            success_url = request.data.get('success_url')
            failure_url = request.data.get('failure_url')

            if not amount or not success_url or not failure_url:
                return Response({'error': 'amount, success_url and failure_url are required'}, status=status.HTTP_400_BAD_REQUEST)

            program = get_object_or_404(Program, id=program_id) if program_id else None
            course = get_object_or_404(Course, id=course_id) if course_id else (program.course if program else None)
            subjects = Subject.objects.filter(id__in=subject_ids) if subject_ids else []

            nchl_payment = NCHLPayment.objects.create(
                user=user,
                program=program,
                course=course,
                amount=amount,
                status='pending',
            )
            if subjects:
                nchl_payment.subjects.set(subjects)

            gateway_resp = nchl_service.initiate_payment(nchl_payment, success_url, failure_url)
            nchl_payment.response_payload = gateway_resp

            # If gateway returns identifiers, store them
            nchl_payment.gateway_txn_id = gateway_resp.get('gatewayTxnId') or gateway_resp.get('transactionId')
            if gateway_resp.get('transactionId'):
                nchl_payment.transaction_id = gateway_resp.get('transactionId')

            # Derive status if explicitly failed
            if gateway_resp.get('error'):
                nchl_payment.status = 'failed'

            nchl_payment.save()

            if gateway_resp.get('redirectUrl'):
                return Response({
                    'payment_url': gateway_resp['redirectUrl'],
                    'merchant_txn_id': nchl_payment.merchant_txn_id,
                    'payment': NCHLPaymentSerializer(nchl_payment).data
                }, status=status.HTTP_200_OK)

            return Response({
                'message': 'Initiation response received',
                'response': gateway_resp,
                'payment': NCHLPaymentSerializer(nchl_payment).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception('Error initiating NCHL payment: %s', str(e))
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NCHLVerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        try:
            merchant_txn_id = request.data.get('merchant_txn_id')
            transaction_id = request.data.get('transaction_id')
            if not merchant_txn_id:
                return Response({'error': 'merchant_txn_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            payment = get_object_or_404(NCHLPayment, merchant_txn_id=merchant_txn_id, user=request.user)
            verify_resp = nchl_service.verify_payment(merchant_txn_id, transaction_id)

            # Update payment record
            payment.response_payload = verify_resp
            if verify_resp.get('status') in ['success', 'SUCCESS', 'completed', 'COMPLETED']:
                payment.status = 'success'
            elif verify_resp.get('status') in ['failed', 'FAILED'] or verify_resp.get('error'):
                payment.status = 'failed'
            payment.gateway_txn_id = verify_resp.get('gatewayTxnId') or payment.gateway_txn_id
            payment.transaction_id = verify_resp.get('transactionId') or payment.transaction_id
            payment.save()

            return Response({
                'status': payment.status,
                'payment': NCHLPaymentSerializer(payment).data,
                'response': verify_resp
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('Error verifying NCHL payment: %s', str(e))
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NCHLCallbackView(APIView):
    permission_classes = []  # callbacks are from NCHL; validate signature instead

    @transaction.atomic
    def post(self, request):
        try:
            parsed = nchl_service.parse_callback(request.data)
            merchant_txn_id = parsed.get('merchantTxnId')
            payment = get_object_or_404(NCHLPayment, merchant_txn_id=merchant_txn_id)

            payment.response_payload = parsed.get('raw')
            if parsed.get('valid') and parsed.get('status') in ['success', 'SUCCESS', 'completed', 'COMPLETED']:
                payment.status = 'success'
            elif parsed.get('status') in ['failed', 'FAILED']:
                payment.status = 'failed'
            payment.transaction_id = parsed.get('transactionId') or payment.transaction_id
            payment.save()

            return Response({'ok': True}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception('Error handling NCHL callback: %s', str(e))
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


