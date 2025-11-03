from io import BytesIO
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage

from .models import OnePGPayment, NCHLPayment, QrPaymentTransaction, BillingHistory
from .billing import generate_invoice_pdf_bytes


def _create_and_send_invoice(*, user, program, course, amount, payment_kind, merchant_txn_id=None, transaction_id=None, payment_pk=None):
    # Skip if invoice already exists
    if BillingHistory.objects.filter(payment_kind=payment_kind, payment_id=payment_pk).exists():
        return

    pdf_bytes = generate_invoice_pdf_bytes(
        user_email=user.email,
        user_name=f"{user.first_name} {user.last_name}".strip() or user.username,
        program_name=getattr(program, 'name', None) if program else None,
        course_name=getattr(course, 'name', None) if course else None,
        amount=amount,
        merchant_txn_id=merchant_txn_id,
        transaction_id=transaction_id,
        payment_kind=payment_kind,
    )

    billing = BillingHistory.objects.create(
        user=user,
        program=program,
        course=course,
        amount=amount,
        payment_kind=payment_kind,
        payment_id=payment_pk or 0,
        merchant_txn_id=merchant_txn_id,
        transaction_id=transaction_id,
    )
    billing.invoice_pdf.save(f"invoice_{billing.id}.pdf", ContentFile(pdf_bytes), save=True)

    # Email the invoice
    subject = 'Your Invoice'
    body = 'Please find your invoice attached.'
    email = EmailMessage(subject, body, to=[user.email])
    email.from_email = None  # use DEFAULT_FROM_EMAIL
    email.attach(f"invoice_{billing.id}.pdf", pdf_bytes, 'application/pdf')
    try:
        email.send(fail_silently=True)
    except Exception:
        pass


@receiver(post_save, sender=OnePGPayment)
def generate_invoice_onepg(sender, instance: OnePGPayment, created, **kwargs):
    if instance.status == 'success':
        _create_and_send_invoice(
            user=instance.user,
            program=instance.program,
            course=instance.course,
            amount=instance.total_amount or instance.amount,
            payment_kind='onepg',
            merchant_txn_id=instance.merchant_txn_id,
            transaction_id=instance.gateway_txn_id,
            payment_pk=instance.pk,
        )


@receiver(post_save, sender=NCHLPayment)
def generate_invoice_nchl(sender, instance: NCHLPayment, created, **kwargs):
    if instance.status == 'success':
        _create_and_send_invoice(
            user=instance.user,
            program=instance.program,
            course=instance.course,
            amount=instance.amount,
            payment_kind='nchl',
            merchant_txn_id=instance.merchant_txn_id,
            transaction_id=instance.transaction_id or instance.gateway_txn_id,
            payment_pk=instance.pk,
        )


@receiver(post_save, sender=QrPaymentTransaction)
def generate_invoice_qr(sender, instance: QrPaymentTransaction, created, **kwargs):
    if instance.status == 'success':
        _create_and_send_invoice(
            user=instance.user,
            program=instance.program,
            course=instance.course,
            amount=instance.transaction_amount,
            payment_kind='qr',
            merchant_txn_id=instance.bill_number,
            transaction_id=None,
            payment_pk=instance.pk,
        )


