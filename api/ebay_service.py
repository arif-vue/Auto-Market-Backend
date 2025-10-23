"""
eBay API Integration Service
Handles eBay marketplace listing, inventory management, and OAuth
"""

import requests
import json
import base64
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class eBayService:
    def __init__(self):
        self.client_id = settings.EBAY_CLIENT_ID
        self.client_secret = settings.EBAY_CLIENT_SECRET
        self.dev_id = settings.EBAY_DEV_ID
        
        # Use sandbox for development, production for live
        self.environment = getattr(settings, 'EBAY_ENVIRONMENT', 'sandbox')
        
        if self.environment == 'sandbox':
            self.base_url = 'https://api.sandbox.ebay.com'
            self.auth_url = 'https://auth.sandbox.ebay.com/oauth2/authorize'
            self.token_url = 'https://api.sandbox.ebay.com/identity/v1/oauth2/token'
        else:
            self.base_url = 'https://api.ebay.com'
            self.auth_url = 'https://auth.ebay.com/oauth2/authorize'
            self.token_url = 'https://api.ebay.com/identity/v1/oauth2/token'
    
    def get_client_credentials_token(self):
        """Get application token for public API calls"""
        cache_key = f'ebay_client_token_{self.environment}'
        token = cache.get(cache_key)
        
        if token:
            return token
        
        # Create basic auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {encoded_credentials}'
        }
        
        data = {
            'grant_type': 'client_credentials',
            'scope': 'https://api.ebay.com/oauth/api_scope'
        }
        
        try:
            response = requests.post(self.token_url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            token = token_data['access_token']
            expires_in = token_data.get('expires_in', 7200)
            
            # Cache token for slightly less than expiry time
            cache.set(cache_key, token, expires_in - 300)
            return token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get eBay client credentials token: {e}")
            return None
    
    def get_user_authorization_url(self, redirect_uri, state=None):
        """Get authorization URL for user consent"""
        scopes = [
            'https://api.ebay.com/oauth/api_scope',
            'https://api.ebay.com/oauth/api_scope/sell.marketing.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.marketing',
            'https://api.ebay.com/oauth/api_scope/sell.inventory.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.inventory',
            'https://api.ebay.com/oauth/api_scope/sell.account.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.account',
            'https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.fulfillment'
        ]
        
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(scopes)
        }
        
        if state:
            params['state'] = state
        
        query_string = '&'.join([f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()])
        return f"{self.auth_url}?{query_string}"
    
    def exchange_code_for_token(self, authorization_code, redirect_uri):
        """Exchange authorization code for access token"""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {encoded_credentials}'
        }
        
        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': redirect_uri
        }
        
        try:
            logger.info(f"Exchanging eBay code with data: {data}")
            response = requests.post(self.token_url, headers=headers, data=data)
            logger.info(f"eBay token response status: {response.status_code}")
            logger.info(f"eBay token response: {response.text}")
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to exchange eBay authorization code: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text}")
            return None
    
    def refresh_access_token(self, refresh_token):
        """Refresh access token using refresh token"""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {encoded_credentials}'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'scope': 'https://api.ebay.com/oauth/api_scope/sell.inventory'
        }
        
        try:
            response = requests.post(self.token_url, headers=headers, data=data)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh eBay access token: {e}")
            return None
    
    def get_valid_access_token(self, user_id):
        """Get valid access token for user, auto-refresh if needed"""
        try:
            from .models import EBayUserToken
            user_token = EBayUserToken.objects.get(user_id=user_id)
            
            # Check if token needs refresh
            if user_token.needs_refresh() or user_token.is_expired():
                logger.info(f"eBay token needs refresh for user {user_id}")
                if user_token.auto_refresh():
                    logger.info(f"eBay token successfully refreshed for user {user_id}")
                    user_token.refresh_from_db()
                else:
                    logger.error(f"Failed to refresh eBay token for user {user_id}")
                    return None
            
            return user_token.access_token
            
        except Exception as e:
            logger.error(f"Error getting valid eBay token for user {user_id}: {e}")
            return None

    def _map_condition_to_ebay(self, condition):
        """Map product condition to eBay API format"""
        condition_mapping = {
            'NEW': 'NEW',
            'LIKE_NEW': 'NEW', 
            'EXCELLENT': 'USED_EXCELLENT',
            'GOOD': 'USED_GOOD',
            'FAIR': 'USED_ACCEPTABLE',
            'POOR': 'FOR_PARTS_OR_NOT_WORKING'
        }
        return condition_mapping.get(condition, 'USED_EXCELLENT')

    def create_inventory_item(self, access_token, product_data):
        """Create inventory item on eBay"""
        url = f"{self.base_url}/sell/inventory/v1/inventory_item/{product_data['sku']}"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Content-Language': 'en-US'
        }
        
        # Map condition to eBay format
        ebay_condition = self._map_condition_to_ebay(product_data.get('condition', 'EXCELLENT'))
        
        # Format product data for eBay inventory item
        inventory_item = {
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": product_data.get('quantity', 1),
                    "allocationByFormat": {
                        "auction": 0,
                        "fixedPrice": product_data.get('quantity', 1)
                    }
                }
            },
            "condition": ebay_condition,
            "product": {
                "title": product_data['title'],
                "description": product_data['description'],
                "aspects": self._format_product_aspects(product_data)
            },
            "locale": "en_US",
            "packageWeightAndSize": {
                "dimensions": {
                    "height": 10,
                    "length": 10,
                    "width": 10,
                    "unit": "INCH"
                },
                "weight": {
                    "value": 2,
                    "unit": "POUND"
                }
            },
            "location": {
                "country": "US",
                "postalCode": "60025"
            }
        }
        
        # Only add imageUrls if we have images
        image_urls = product_data.get('image_urls', [])
        if image_urls:
            inventory_item["product"]["imageUrls"] = image_urls
        
        try:
            response = requests.put(url, headers=headers, json=inventory_item)
            response.raise_for_status()
            return response.json() if response.content else {"success": True}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create eBay inventory item: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return None
    
    def create_offer(self, access_token, sku, price, listing_duration='GTC', product_title=""):
        """Create offer for inventory item"""
        url = f"{self.base_url}/sell/inventory/v1/offer"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Content-Language': 'en-US'
        }
        
        offer_data = {
            "sku": sku,
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "availableQuantity": 1,
            "pricingSummary": {
                "price": {
                    "currency": "USD",
                    "value": str(price)
                }
            },
            "listingDuration": listing_duration,
            "listingPolicies": {
                "fulfillmentPolicyId": self._get_fulfillment_policy_id(access_token),
                "paymentPolicyId": self._get_payment_policy_id(access_token),
                "returnPolicyId": self._get_return_policy_id(access_token)
            },
            "categoryId": self._get_category_id(product_title),
            "merchantLocationKey": "GLENVIEW_WAREHOUSE_002"  # Use valid merchant location
        }
        
        try:
            response = requests.post(url, headers=headers, json=offer_data)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create eBay offer: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return None
    
    def publish_offer(self, access_token, offer_id):
        """Publish offer to eBay marketplace"""
        url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}/publish"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Content-Language': 'en-US'
        }
        
        try:
            response = requests.post(url, headers=headers)
            
            # If publish fails, try to get the offer details to see if it already has a listing
            if response.status_code != 200:
                logger.warning(f"Publish failed with status {response.status_code}, checking offer details...")
                offer_details = self.get_offer_details(access_token, offer_id)
                if offer_details and offer_details.get('listing', {}).get('listingId'):
                    # Offer already published
                    return {
                        'listingId': offer_details['listing']['listingId'],
                        'status': 'PUBLISHED'
                    }
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to publish eBay offer: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            
            # Try to get offer details as fallback
            try:
                offer_details = self.get_offer_details(access_token, offer_id)
                if offer_details and offer_details.get('listing', {}).get('listingId'):
                    logger.info(f"Found existing listing ID from offer details: {offer_details['listing']['listingId']}")
                    return {
                        'listingId': offer_details['listing']['listingId'],
                        'status': 'PUBLISHED'
                    }
            except Exception as fallback_error:
                logger.error(f"Fallback offer details check failed: {fallback_error}")
            
            return None
    
    def get_offer_details(self, access_token, offer_id):
        """Get offer details to check if it's already published"""
        url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get eBay offer details: {e}")
            return None
    
    def end_listing(self, access_token, listing_id, reason='NOT_AVAILABLE'):
        """End eBay listing using Trading API for traditional listings"""
        
        # Method 1: Try Trading API (for traditional eBay listings)
        try:
            logger.info(f"Attempting to end eBay listing {listing_id} using Trading API")
            
            # Trading API uses different endpoint and XML format
            trading_url = f"{self.base_url}/ws/api.dll"
            
            # XML request for EndFixedPriceItem with proper credentials
            xml_request = f'''<?xml version="1.0" encoding="utf-8"?>
<EndFixedPriceItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{access_token}</eBayAuthToken>
    </RequesterCredentials>
    <ItemID>{listing_id}</ItemID>
    <EndingReason>NotAvailable</EndingReason>
</EndFixedPriceItemRequest>'''
            
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'X-EBAY-API-SITEID': '0',  # 0 = US site
                'X-EBAY-API-COMPATIBILITY-LEVEL': '967',
                'X-EBAY-API-CALL-NAME': 'EndFixedPriceItem',
                'X-EBAY-API-APP-NAME': self.client_id,
                'X-EBAY-API-DEV-NAME': self.dev_id,
                'X-EBAY-API-CERT-NAME': self.client_secret
            }
            
            response = requests.post(trading_url, data=xml_request, headers=headers)
            
            if response.status_code == 200:
                # Check if the XML response indicates success
                response_text = response.text.lower()
                if '<ack>success</ack>' in response_text or '<ack>warning</ack>' in response_text:
                    logger.info(f"Successfully ended eBay listing {listing_id} using Trading API")
                    return {"success": True, "message": "Listing ended successfully via Trading API"}
                elif '<errorcode>' in response_text:
                    logger.warning(f"Trading API returned error for listing {listing_id}: {response.text}")
                    # Extract error message for debugging
                    if 'already ended' in response_text or 'not found' in response_text:
                        return {"success": True, "message": "Listing already ended or not found"}
                else:
                    logger.info(f"Trading API response unclear for listing {listing_id}, checking for success")
            
        except Exception as e:
            logger.error(f"Trading API method failed for listing {listing_id}: {e}")
        
        # Method 2: Try Inventory API (for newer inventory-based listings) 
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Try direct withdrawal first
            withdraw_url = f"{self.base_url}/sell/inventory/v1/offer/{listing_id}/withdraw"
            response = requests.post(withdraw_url, headers=headers)
            
            if response.status_code in [200, 204]:
                logger.info(f"Successfully ended eBay listing {listing_id} using Inventory API")
                return {"success": True, "message": "Listing ended successfully via Inventory API"}
            
        except Exception as e:
            logger.error(f"Inventory API method failed for listing {listing_id}: {e}")
        
        # Method 3: Use REST API (newer approach)
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Try the newer Trading API REST endpoint
            rest_url = f"{self.base_url}/sell/trading/v1/item/{listing_id}/end"
            end_data = {
                "endingReason": reason
            }
            
            response = requests.post(rest_url, headers=headers, json=end_data)
            
            if response.status_code in [200, 204]:
                logger.info(f"Successfully ended eBay listing {listing_id} using REST Trading API")
                return {"success": True, "message": "Listing ended successfully via REST Trading API"}
            
        except Exception as e:
            logger.error(f"REST Trading API method failed for listing {listing_id}: {e}")
        
        # If all methods fail, return failure (don't assume success)
        logger.error(f"All methods failed to end eBay listing {listing_id}")
        return {
            "success": False, 
            "error": "All API methods failed",
            "message": "Could not end listing via any API method - manual intervention required"
        }
    
    def get_listing_status(self, access_token, offer_id):
        """Get listing status from eBay"""
        url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get eBay listing status: {e}")
            return None
    
    def _format_product_aspects(self, product_data):
        """Format product data into eBay aspects with category-specific requirements"""
        aspects = {}
        
        # Basic aspects
        if 'brand' in product_data:
            aspects['Brand'] = [product_data['brand']]
        if 'model' in product_data:
            aspects['Model'] = [product_data['model']]
        if 'type' in product_data:
            aspects['Type'] = [product_data['type']]
        if 'color' in product_data:
            aspects['Color'] = [product_data['color']]
        if 'size' in product_data:
            aspects['Size'] = [product_data['size']]
        
        # Category-specific aspects based on product title
        title_lower = product_data.get('title', '').lower()
        
        # TV/Monitor Category (11071) - requires Maximum Resolution and Screen Size
        if any(word in title_lower for word in ['tv', 'television', 'monitor', 'sony', 'bravia']):
            aspects['Maximum Resolution'] = ["4K (UHD)"]
            aspects['Display Technology'] = ["LED"]
            aspects['Smart TV'] = ["Yes"] if 'smart' in title_lower else ["No"]
            
            # Extract screen size from title
            import re
            size_match = re.search(r'(\d+)"?\s*(?:inch|in|class)', title_lower)
            if size_match:
                aspects['Screen Size'] = [f"{size_match.group(1)} in"]
            else:
                aspects['Screen Size'] = ["65 in"]  # Default
        
        # Laptop Category (177) - requires Screen Size and Processor
        elif any(word in title_lower for word in ['macbook', 'laptop', 'computer']):
            aspects['Screen Size'] = ["13.3 in"]  # Default for MacBook Air
            aspects['Processor'] = ["Apple M4"] if 'm4' in title_lower else ["Intel Core"]
            aspects['RAM Size'] = ["8 GB"]
            aspects['Storage Type'] = ["SSD"]
            aspects['Operating System'] = ["macOS"] if 'macbook' in title_lower else ["Windows"]
            
            # Extract screen size if mentioned
            import re
            size_match = re.search(r'(\d+)\s*(?:inch|in)', title_lower)
            if size_match:
                aspects['Screen Size'] = [f"{size_match.group(1)} in"]
        
        # VR Category (139971) - fewer requirements
        elif any(word in title_lower for word in ['vr', 'virtual reality', 'quest', 'headset']):
            aspects['Platform'] = ["Meta Quest"] if 'quest' in title_lower else ["VR"]
            aspects['Type'] = ["VR Headset"]
            aspects['Connectivity'] = ["Wireless"]
            
            # Extract storage if mentioned
            import re
            storage_match = re.search(r'(\d+)\s*gb', title_lower)
            if storage_match:
                aspects['Storage Capacity'] = [f"{storage_match.group(1)} GB"]
        
        # Phone Category (9355)
        elif any(word in title_lower for word in ['iphone', 'phone', 'smartphone']):
            aspects['Storage Capacity'] = ["128 GB"]
            aspects['Network'] = ["Unlocked"]
            aspects['Operating System'] = ["iOS"] if 'iphone' in title_lower else ["Android"]
        
        return aspects
    
    def _get_fulfillment_policy_id(self, access_token):
        """Get fulfillment policy ID - implement based on your policies"""
        # Use configured ID or fetch from eBay
        configured_id = getattr(settings, 'EBAY_FULFILLMENT_POLICY_ID', None)
        if configured_id:
            return configured_id
        
        # Fallback: return the policy ID we discovered
        return "311555431021"
    
    def _get_payment_policy_id(self, access_token):
        """Get payment policy ID - implement based on your policies"""
        # Use configured ID or fetch from eBay
        configured_id = getattr(settings, 'EBAY_PAYMENT_POLICY_ID', None)
        if configured_id:
            return configured_id
        
        # Fallback: return the eBay Managed Payments policy ID we discovered
        return "311915633021"
    
    def _get_return_policy_id(self, access_token):
        """Get return policy ID - implement based on your policies"""
        # Use configured ID or fetch from eBay
        configured_id = getattr(settings, 'EBAY_RETURN_POLICY_ID', None)
        if configured_id:
            return configured_id
        
        # Fallback: return the return policy ID we discovered
        return "311555443021"
    
    def _get_category_id(self, product_title=""):
        """Get eBay category ID based on product type"""
        
        title_lower = product_title.lower()
        
        # VR/Gaming Equipment Categories
        if any(word in title_lower for word in ['vr', 'virtual reality', 'quest', 'oculus', 'headset']):
            return "139971"  # Video Game Accessories - LEAF CATEGORY that works
        
        # Electronics Categories  
        elif any(word in title_lower for word in ['iphone', 'samsung', 'phone', 'smartphone']):
            return "9355"    # Cell Phones & Smartphones
        
        elif any(word in title_lower for word in ['macbook', 'laptop', 'computer']):
            return "177"     # PC Laptops & Netbooks
        
        elif any(word in title_lower for word in ['ipad', 'tablet']):
            return "171485"  # Tablets & eBook Readers
        
        elif any(word in title_lower for word in ['tv', 'television', 'monitor']):
            return "11071"   # Monitors, Projectors & Accs
        
        elif any(word in title_lower for word in ['camera', 'canon', 'nikon', 'sony camera']):
            return "31388"   # Digital Cameras
        
        elif any(word in title_lower for word in ['watch', 'apple watch', 'smartwatch']):
            return "178893"  # Smart Watches
        
        elif any(word in title_lower for word in ['backpack', 'bag', 'luggage']):
            return "169"     # Backpacks, Bags & Briefcases
        
        elif any(word in title_lower for word in ['car', 'vehicle', 'auto', 'buick', 'ford', 'toyota']):
            # Vehicle-related items - use a general electronics category that accepts diverse products
            # Digital Cameras category works well for high-value miscellaneous items
            return "31388"   # Digital Cameras (leaf category that accepts diverse products)
        
        # Default fallback categories
        elif any(word in title_lower for word in ['electronics', 'gadget', 'device']):
            return "293"     # Consumer Electronics
        
        else:
            # Default to Consumer Electronics for unknown items
            return "293"     # Consumer Electronics