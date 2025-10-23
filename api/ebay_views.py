"""
eBay Integration Views
Handles OAuth flow, product listing, and marketplace management
"""

from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from django.conf import settings
import json
import logging
from datetime import datetime, timedelta

from .ebay_service import eBayService
from .models import Product, SellerContactInfo, EBayUserToken
from .serializers import ProductSerializer

logger = logging.getLogger(__name__)


def ebay_auth_test(request):
    """Test eBay OAuth configuration - no login required"""
    try:
        ebay_service = eBayService()
        
        # Generate state parameter for security  
        state = f"ebay_test_{datetime.now().timestamp()}"
        request.session['ebay_oauth_state'] = state
        
        # Get authorization URL - use configured redirect URI
        redirect_uri = settings.EBAY_REDIRECT_URI
        auth_url = ebay_service.get_user_authorization_url(redirect_uri, state)
        
        return JsonResponse({
            'success': True,
            'auth_url': auth_url,
            'redirect_uri': redirect_uri,
            'state': state,
            'instructions': 'Visit the auth_url to test eBay OAuth flow'
        })
        
    except Exception as e:
        logger.error(f"Error generating eBay auth URL: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to generate eBay auth URL: {str(e)}'
        }, status=500)

@staff_member_required
def ebay_auth_start(request):
    """Start eBay OAuth flow"""
    try:
        ebay_service = eBayService()
        
        # Generate state parameter for security
        state = f"ebay_auth_{request.user.id}_{datetime.now().timestamp()}"
        request.session['ebay_oauth_state'] = state
        
        # Get authorization URL - use configured redirect URI
        redirect_uri = settings.EBAY_REDIRECT_URI
        auth_url = ebay_service.get_user_authorization_url(redirect_uri, state)
        
        return HttpResponseRedirect(auth_url)
        
    except Exception as e:
        logger.error(f"Error starting eBay auth: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to start eBay authorization'
        }, status=500)


def ebay_auth_declined(request):
    """Handle eBay OAuth declined"""
    return JsonResponse({
        'success': False,
        'message': 'eBay authorization was declined',
        'redirect': '/admin/'
    })


@csrf_exempt
@require_http_methods(["GET"])
def ebay_auth_callback(request):
    """Handle eBay OAuth callback"""
    try:
        # DEBUG: Log all parameters received from eBay
        logger.info(f"eBay callback received - Method: {request.method}")
        logger.info(f"GET parameters: {dict(request.GET)}")
        logger.info(f"POST parameters: {dict(request.POST)}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        # Get authorization code from callback
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        
        # DEBUG: Return detailed info for debugging
        debug_info = {
            'method': request.method,
            'get_params': dict(request.GET),
            'post_params': dict(request.POST),
            'code_present': bool(code),
            'state_present': bool(state),
            'error_present': bool(error)
        }
        
        if error:
            logger.error(f"eBay OAuth error: {error}")
            return JsonResponse({
                'success': False,
                'error': f'eBay authorization failed: {error}',
                'debug': debug_info
            }, status=400)
        
        if not code:
            return JsonResponse({
                'success': False,
                'error': 'No authorization code received',
                'debug': debug_info,
                'help': 'Check eBay app configuration: Redirect URI must match exactly'
            }, status=400)
        
        # Verify state parameter (allow test scenarios without state)
        session_state = request.session.get('ebay_oauth_state')
        if state and session_state and session_state != state:
            return JsonResponse({
                'success': False,
                'error': 'Invalid state parameter'
            }, status=400)
        elif not state:
            # Test scenario - log for debugging but allow to proceed
            logger.info("OAuth callback received without state parameter (test mode)")
        
        # Exchange code for token
        ebay_service = eBayService()
        # Use the configured callback URL that matches eBay RuName configuration
        callback_url = settings.EBAY_REDIRECT_URI
        
        logger.info(f"Using callback URL for token exchange: {callback_url}")
        token_data = ebay_service.exchange_code_for_token(
            code, 
            callback_url
        )
        
        if not token_data:
            return JsonResponse({
                'success': False,
                'error': 'Failed to exchange authorization code'
            }, status=500)
        
        # Store token in database (for testing, use a default user ID if not authenticated)
        user_id = request.user.id if request.user.is_authenticated else 999  # Test user ID
        
        user_token, created = EBayUserToken.objects.get_or_create(
            user_id=user_id,
            defaults={
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token', ''),
                'expires_at': datetime.now() + timedelta(seconds=token_data.get('expires_in', 7200)),
                'token_type': token_data.get('token_type', 'Bearer'),
                'scope': token_data.get('scope', '')
            }
        )
        
        if not created:
            # Update existing token
            user_token.access_token = token_data['access_token']
            user_token.refresh_token = token_data.get('refresh_token', user_token.refresh_token)
            user_token.expires_at = datetime.now() + timedelta(seconds=token_data.get('expires_in', 7200))
            user_token.token_type = token_data.get('token_type', 'Bearer')
            user_token.scope = token_data.get('scope', '')
            user_token.save()
        
        # Clear session state
        request.session.pop('ebay_oauth_state', None)
        
        return JsonResponse({
            'success': True,
            'message': 'eBay authorization successful',
            'expires_at': user_token.expires_at.isoformat()
        })
        
    except Exception as e:
        import traceback
        logger.error(f"Error in eBay callback: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ebay_list_product(request):
    """List a product on eBay"""
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        custom_price = data.get('price')  # Optional custom price
        
        if not product_id:
            return JsonResponse({
                'success': False,
                'error': 'Product ID is required'
            }, status=400)
        
        # Get product
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Product not found'
            }, status=404)
        
        # Check if product is approved (allow PENDING for testing)
        if product.listing_status not in ['APPROVED', 'PENDING']:
            return JsonResponse({
                'success': False,
                'error': f'Product status is {product.listing_status}. Only APPROVED or PENDING products can be listed.'
            }, status=400)
        
        # Get eBay access token with auto-refresh
        ebay_service = eBayService()
        user_id = request.user.id if request.user.is_authenticated else 999
        
        access_token = ebay_service.get_valid_access_token(user_id)
        if not access_token:
            return JsonResponse({
                'success': False,
                'error': 'eBay authorization required or token refresh failed. Please re-authorize.'
            }, status=401)
        
        # Prepare product data for eBay
        product_images = []
        for image in product.images.all():
            # Convert relative path to full URL
            image_url = request.build_absolute_uri(image.image.url)
            
            # For production, ensure HTTPS
            if hasattr(settings, 'EBAY_ENVIRONMENT') and settings.EBAY_ENVIRONMENT == 'production':
                image_url = image_url.replace('http://', 'https://')
            
            # For development, convert localhost URLs to publicly accessible dev tunnel
            if 'localhost' in image_url or '127.0.0.1' in image_url:
                # Replace localhost with dev tunnel URL that eBay can access
                dev_tunnel_url = 'https://bluberryhq.com'
                if '127.0.0.1:8000' in image_url:
                    image_url = image_url.replace('http://127.0.0.1:8000', dev_tunnel_url)
                    image_url = image_url.replace('https://127.0.0.1:8000', dev_tunnel_url)
                elif 'localhost:8000' in image_url:
                    image_url = image_url.replace('http://localhost:8000', dev_tunnel_url)
                    image_url = image_url.replace('https://localhost:8000', dev_tunnel_url)
                
            product_images.append(image_url)
        
        # Map product condition to eBay condition
        condition_mapping = {
            'NEW': 'NEW',
            'LIKE_NEW': 'USED_EXCELLENT', 
            'EXCELLENT': 'USED_EXCELLENT',
            'GOOD': 'USED_GOOD',
            'FAIR': 'USED_ACCEPTABLE',
            'POOR': 'USED_ACCEPTABLE'
        }
        ebay_condition = condition_mapping.get(product.condition, 'USED_EXCELLENT')
        
        # Add placeholder image if no images exist
        if not product_images:
            product_images = ['https://via.placeholder.com/800x600.jpg?text=Product+Image']
        
        # Determine category for dynamic aspects
        category_id = ebay_service._get_category_id(product.title)
        
        # Set category-specific aspects
        if category_id == 139971:  # Video Game Accessories (VR headsets, gaming accessories)
            brand = 'Meta' if 'meta' in product.title.lower() else 'Generic'
            model = product.title.replace('Meta Quest', 'Quest').replace('3s', '3S')[:30]  # Clean model name
            product_type = 'VR Headset' if 'vr' in product.title.lower() or 'headset' in product.title.lower() else 'Gaming Accessory'
        elif category_id == 9355:  # Cell Phones & Smartphones
            brand = 'Generic'  # Extract from title if possible
            model = f"{product.title[:25]} Model"
            product_type = 'Smartphone'
        elif category_id == 177:  # PC Laptops & Netbooks
            brand = 'Generic'  # Extract from title if possible  
            model = f"{product.title[:25]} Model"
            product_type = 'Laptop'
        else:  # Default to camera aspects for other categories
            brand = 'Generic'
            model = f"{product.title[:25]} Model"
            product_type = 'Digital Camera'
        
        # Generate unique SKU with seconds and microseconds to avoid conflicts
        from datetime import datetime
        import random
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        random_suffix = random.randint(100, 999)
        unique_sku = f"AM_{product.id}_{timestamp}_{random_suffix}"
        
        product_data = {
            'sku': unique_sku,
            'title': product.title,
            'description': product.description or f"Quality {product.title}",
            'image_urls': product_images[:12],  # eBay allows max 12 images
            'condition': ebay_condition,
            'quantity': 1,
            # Dynamic eBay product aspects based on category
            'brand': brand,
            'model': model,
            'type': product_type
        }
        
        # Create inventory item
        logger.info(f"Creating eBay inventory item with SKU: {product_data['sku']}")
        inventory_result = ebay_service.create_inventory_item(
            access_token, 
            product_data
        )
        
        if not inventory_result:
            logger.error(f"Failed to create eBay inventory item for product {product.id}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to create eBay inventory item'
            }, status=500)
        
        # Create offer
        # Use custom price if provided, otherwise use final listing price, fallback to estimated value
        if custom_price:
            listing_price = float(custom_price)
            logger.info(f"Using custom price for product {product.id}: ${listing_price}")
        elif product.final_listing_price:
            listing_price = float(product.final_listing_price)
            logger.info(f"Using final listing price for product {product.id}: ${listing_price}")
        else:
            listing_price = float(product.estimated_value or 0)
            logger.info(f"Using estimated value for product {product.id}: ${listing_price}")
        
        logger.info(f"eBay listing - Product: {product.title}, Price: ${listing_price}, Images: {len(product_images)}")
            
        logger.info(f"Creating eBay offer with price ${listing_price}")
        offer_result = ebay_service.create_offer(
            access_token,
            product_data['sku'],
            listing_price,
            product_title=product.title
        )
        
        if not offer_result:
            logger.error(f"Failed to create eBay offer for product {product.id} at ${listing_price}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to create eBay offer'
            }, status=500)
        
        # Publish offer
        offer_id = offer_result.get('offerId')
        if offer_id:
            logger.info(f"Publishing eBay offer {offer_id}")
            publish_result = ebay_service.publish_offer(access_token, offer_id)
            
            if publish_result:
                listing_id = publish_result.get('listingId')
                # Update product with eBay listing info
                product.ebay_listing_url = listing_id
                product.listing_status = 'LISTED'  # Use correct field name
                product.ebay_category = ebay_service._get_category_id(product.title)
                product.save()
                
                logger.info(f"eBay listing successful - Product {product.id} listed as {listing_id} at ${listing_price}")
                return JsonResponse({
                    'success': True,
                    'message': 'Product listed on eBay successfully',
                    'listing_id': listing_id,
                    'sku': product_data['sku'],
                    'price_used': listing_price
                })
            else:
                logger.error(f"Failed to publish eBay offer {offer_id} for product {product.id}")
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to publish eBay offer'
                }, status=500)
        else:
            return JsonResponse({
                'success': False,
                'error': 'No offer ID returned from eBay'
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error listing product on eBay: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def ebay_end_listing(request):
    """End eBay listing"""
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        
        if not product_id:
            return JsonResponse({
                'success': False,
                'error': 'Product ID is required'
            }, status=400)
        
        # Get product
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Product not found'
            }, status=404)
        
        if not product.ebay_listing_url:
            return JsonResponse({
                'success': False,
                'error': 'Product is not listed on eBay'
            }, status=400)
        
        # Get eBay access token with auto-refresh
        ebay_service = eBayService()
        access_token = ebay_service.get_valid_access_token(request.user.id)
        
        if not access_token:
            return JsonResponse({
                'success': False,
                'error': 'eBay authorization required or token refresh failed. Please re-authorize.'
            }, status=401)
        
        # End listing
        end_result = ebay_service.end_listing(
            access_token,
            product.ebay_listing_url
        )
        
        if end_result:
            # Update product status
            product.listing_status = 'REMOVED'
            product.save()
            
            return JsonResponse({
                'success': True,
                'message': 'eBay listing ended successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to end eBay listing'
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error ending eBay listing: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


@staff_member_required
def ebay_status(request):
    """Get eBay integration status"""
    try:
        # Check if user has valid token
        try:
            user_token = EBayUserToken.objects.get(user_id=request.user.id)
            is_authorized = not user_token.is_expired()
            expires_at = user_token.expires_at.isoformat() if user_token.expires_at else None
        except EBayUserToken.DoesNotExist:
            is_authorized = False
            expires_at = None
        
        # Count listings
        listed_count = Product.objects.filter(
            listing_status='LISTED',
            ebay_listing_url__isnull=False
        ).count()
        
        return JsonResponse({
            'success': True,
            'ebay_authorized': is_authorized,
            'token_expires_at': expires_at,
            'environment': settings.EBAY_ENVIRONMENT,
            'listed_products': listed_count
        })
        
    except Exception as e:
        logger.error(f"Error getting eBay status: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get eBay status'
        }, status=500)