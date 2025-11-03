import hashlib
import json
import logging
import os
from typing import Dict, Any, Optional

import requests

from .models import NCHLPayment

logger = logging.getLogger(__name__)


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name, default)
    if value is None:
        logger.warning(f"Environment variable {name} not set; using default {default}")
    return value


NCHL_BASE_URL = _get_env('NCHL_BASE_URL', 'https://uat.connectips.com')
NCHL_USERNAME = _get_env('NCHL_USERNAME')
NCHL_PASSWORD = _get_env('NCHL_PASSWORD')


def _sha256_hash(payload: Dict[str, Any], secret: str) -> str:
    """
    Create a SHA256 hash of the payload according to ConnectIPS doc guidance.
    Strategy: sort keys, concatenate as key=value joined by |, append secret, then SHA256 hex.
    """
    # Flatten to primitives and ignore nested structures for signature base
    items = []
    for key in sorted(payload.keys()):
        value = payload[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, separators=(',', ':'), ensure_ascii=False)
        items.append(f"{key}={value}")
    base = "|".join(items) + f"|{secret}"
    digest = hashlib.sha256(base.encode('utf-8')).hexdigest()
    return digest


def initiate_payment(nchl_payment: NCHLPayment, success_url: str, failure_url: str) -> Dict[str, Any]:
    """
    Initiate a payment with ConnectIPS.
    Returns the gateway response; caller should persist response payload and redirectUrl if present.
    """
    endpoint = f"{NCHL_BASE_URL.rstrip('/')}/connectips/v1/initiatePayment"

    request_payload = {
        'merchantTxnId': nchl_payment.merchant_txn_id,
        'amount': str(nchl_payment.amount),
        'successUrl': success_url,
        'failureUrl': failure_url,
        'username': NCHL_USERNAME,
    }
    signature = _sha256_hash(request_payload, NCHL_PASSWORD or '')
    request_payload['signature'] = signature

    logger.info("NCHL initiate payload: %s", {k: (v if k != 'signature' else '***') for k, v in request_payload.items()})
    try:
        resp = requests.post(endpoint, json=request_payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.exception("Error calling NCHL initiatePayment: %s", str(e))
        return {'error': str(e)}

    return data


def verify_payment(merchant_txn_id: str, transaction_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify a payment status with ConnectIPS.
    """
    endpoint = f"{NCHL_BASE_URL.rstrip('/')}/connectips/v1/verifyPayment"
    request_payload = {
        'merchantTxnId': merchant_txn_id,
        'transactionId': transaction_id or '',
        'username': NCHL_USERNAME,
    }
    signature = _sha256_hash(request_payload, NCHL_PASSWORD or '')
    request_payload['signature'] = signature

    logger.info("NCHL verify payload: %s", {k: (v if k != 'signature' else '***') for k, v in request_payload.items()})
    try:
        resp = requests.post(endpoint, json=request_payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.exception("Error calling NCHL verifyPayment: %s", str(e))
        return {'error': str(e)}

    return data


def parse_callback(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle NCHL callback; verify signature and return parsed info.
    """
    provided_signature = payload.get('signature')
    calc_signature = _sha256_hash({k: v for k, v in payload.items() if k != 'signature'}, NCHL_PASSWORD or '')
    valid = provided_signature == calc_signature
    return {
        'valid': valid,
        'merchantTxnId': payload.get('merchantTxnId'),
        'transactionId': payload.get('transactionId'),
        'status': payload.get('status'),
        'raw': payload,
    }


