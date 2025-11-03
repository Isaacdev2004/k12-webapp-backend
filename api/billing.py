from io import BytesIO
from datetime import datetime
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas


def _draw_header(c: canvas.Canvas, title: str):
    c.setFont('Helvetica-Bold', 16)
    c.drawString(20 * mm, 280 * mm, title)
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.grey)
    c.line(20 * mm, 278 * mm, 190 * mm, 278 * mm)


def _draw_kv(c: canvas.Canvas, x_mm: float, y_mm: float, key: str, value: str):
    c.setFont('Helvetica', 10)
    c.drawString(x_mm * mm, y_mm * mm, f"{key}:")
    c.setFont('Helvetica-Bold', 10)
    c.drawRightString(190 * mm, y_mm * mm, value)


def generate_invoice_pdf_bytes(*, user_email: str, user_name: str | None, program_name: str | None,
                               course_name: str | None, amount: Decimal, merchant_txn_id: str | None,
                               transaction_id: str | None, payment_kind: str) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    _draw_header(c, 'Invoice / Tax Invoice')

    y = 270
    _draw_kv(c, 20, y, 'Date', datetime.now().strftime('%Y-%m-%d %H:%M'))
    y -= 7
    _draw_kv(c, 20, y, 'Billed To', f"{user_name or ''} <{user_email}>")
    y -= 7
    if program_name:
        _draw_kv(c, 20, y, 'Program', program_name)
        y -= 7
    if course_name:
        _draw_kv(c, 20, y, 'Course', course_name)
        y -= 7
    if merchant_txn_id:
        _draw_kv(c, 20, y, 'Merchant Txn ID', merchant_txn_id)
        y -= 7
    if transaction_id:
        _draw_kv(c, 20, y, 'Gateway Txn ID', transaction_id)
        y -= 7
    _draw_kv(c, 20, y, 'Payment Method', payment_kind.upper())
    y -= 14

    # Amount section
    c.setFont('Helvetica-Bold', 12)
    c.drawString(20 * mm, y * mm, 'Amount Paid (NPR)')
    c.setFont('Helvetica-Bold', 18)
    c.drawRightString(190 * mm, y * mm, f"{Decimal(amount):.2f}")

    # Footer
    c.setFont('Helvetica', 9)
    c.setFillColor(colors.grey)
    c.drawString(20 * mm, 20 * mm, 'Thank you for your purchase from Aakhyaan/K12Nepal.')

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


