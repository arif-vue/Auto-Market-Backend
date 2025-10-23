"""
Amazon SP-API OAuth Views
Handles Amazon seller authorization flow for SP-API access
"""
from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
import json
import logging
from datetime import datetime
import urllib.parse
import requests

logger = logging.getLogger(__name__)


def exchange_code_for_tokens(authorization_code):
    """Exchange Amazon authorization code for access and refresh tokens"""
    try:
        # Amazon LWA token endpoint
        token_url = "https://api.amazon.com/auth/o2/token"
        
        # Prepare token request
        token_data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'client_id': settings.AMAZON_CLIENT_ID,
            'client_secret': settings.AMAZON_CLIENT_SECRET,
            'redirect_uri': f"https://bluberryhq.com/api/amazon/callback/"
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Make token request
        response = requests.post(token_url, data=token_data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            token_info = response.json()
            
            return {
                'success': True,
                'access_token': token_info.get('access_token'),
                'refresh_token': token_info.get('refresh_token'),
                'expires_in': token_info.get('expires_in', 3600),
                'token_type': token_info.get('token_type', 'bearer')
            }
        else:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            return {
                'success': False,
                'error': f'Token exchange failed: {response.text}'
            }
            
    except Exception as e:
        logger.error(f"Error exchanging code for tokens: {e}")
        return {
            'success': False,
            'error': f'Token exchange error: {str(e)}'
        }


def amazon_login(request):
    """Start Amazon SP-API OAuth flow"""
    try:
        # Generate state parameter for security
        state = f"amazon_auth_{datetime.now().timestamp()}"
        request.session['amazon_oauth_state'] = state
        
        # Amazon LWA authorization URL
        base_url = "https://www.amazon.com/ap/oa"
        
        params = {
            'client_id': settings.AMAZON_CLIENT_ID,
            'scope': 'sellingpartnerapi::notifications sellingpartnerapi::migration',
            'response_type': 'code',
            'redirect_uri': f"https://bluberryhq.com/api/amazon/callback/",
            'state': state
        }
        
        # Build authorization URL
        auth_url = f"{base_url}?{urllib.parse.urlencode(params)}"
        
        return HttpResponseRedirect(auth_url)
        
    except Exception as e:
        logger.error(f"Error starting Amazon auth: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to start Amazon authorization'
        }, status=500)


@csrf_exempt
def amazon_callback(request):
    """Handle Amazon OAuth callback"""
    try:
        # Get authorization code from callback
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        
        if error:
            return JsonResponse({
                'success': False,
                'error': f'Amazon authorization failed: {error}'
            }, status=400)
        
        if not code:
            return JsonResponse({
                'success': False,
                'error': 'No authorization code received'
            }, status=400)
        
        # Verify state parameter
        session_state = request.session.get('amazon_oauth_state')
        if state != session_state:
            return JsonResponse({
                'success': False,
                'error': 'Invalid state parameter'
            }, status=400)
        
        # Exchange authorization code for tokens
        token_response = exchange_code_for_tokens(code)
        
        if token_response['success']:
            # Store tokens securely (you might want to save to database)
            request.session['amazon_access_token'] = token_response['access_token']
            request.session['amazon_refresh_token'] = token_response['refresh_token']
            
            return JsonResponse({
                'success': True,
                'message': 'Amazon OAuth completed successfully! 🎉',
                'access_token': token_response['access_token'][:20] + '...',
                'refresh_token': token_response['refresh_token'][:20] + '...',
                'expires_in': token_response.get('expires_in', 3600),
                'status': 'Your Amazon SP-API integration is now fully functional!'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Token exchange failed: {token_response["error"]}'
            }, status=400)
        
    except Exception as e:
        logger.error(f"Error handling Amazon callback: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)