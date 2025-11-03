import base64
import hashlib
import hmac
import time

def generate_zoom_signature(meeting_number, sdk_key, sdk_secret, role):
    api_key = sdk_key
    api_secret = sdk_secret
    meeting_number = str(meeting_number)
    role = str(role)

    # Calculate the timestamp
    timestamp = int(time.time() * 1000) - 30000

    # Create the message to sign
    message = api_key + meeting_number + str(timestamp) + role

    # Create the signature
    signature = hmac.new(api_secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()

    # Return the final signature
    return base64.b64encode(f"{api_key}.{meeting_number}.{timestamp}.{role}.{signature}".encode('utf-8')).decode('utf-8')
