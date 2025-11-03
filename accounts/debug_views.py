from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def google_auth_callback_debug(request):
    """
    Debug version of Google OAuth callback with detailed logging
    """
    if request.method == 'OPTIONS':
        # Handle CORS preflight
        response = JsonResponse({'status': 'CORS preflight OK'})
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        response["Access-Control-Allow-Credentials"] = "true"
        return response
    
    # Log everything for debugging
    print("=" * 50)
    print("🔍 DEBUG - Google Auth Callback")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Content-Type: {request.content_type}")
    
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        print(f"Data: {data}")
    except Exception as e:
        print(f"Error parsing data: {e}")
        data = {}
    
    print("=" * 50)
    
    # Return the data for inspection
    response = JsonResponse({
        'debug': True,
        'method': request.method,
        'headers': dict(request.headers),
        'data': data,
        'status': 'Debug endpoint working'
    })
    
    # Add CORS headers
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Credentials"] = "true"
    
    return response
