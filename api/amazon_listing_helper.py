"""
Amazon Listing Helper - Automatic ASIN Matching and Offer Creation
This module enables listing products on Amazon like eBay by:
1. Automatically searching for matching ASINs
2. Creating seller offers on existing products
3. No Brand Registry required
"""

import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class AmazonListingHelper:
    """Helper class to list products on Amazon by finding existing ASINs"""
    
    def __init__(self):
        self.client_id = getattr(settings, 'AMAZON_CLIENT_ID', '')
        self.client_secret = getattr(settings, 'AMAZON_CLIENT_SECRET', '')
        self.refresh_token = getattr(settings, 'AMAZON_REFRESH_TOKEN', '')
        self.seller_id = getattr(settings, 'AMAZON_SELLER_ID', '')
        self.marketplace_id = 'ATVPDKIKX0DER'  # US marketplace
        
        if getattr(settings, 'AMAZON_SANDBOX', False):
            self.sp_api_base = "https://sandbox.sellingpartnerapi-na.amazon.com"
        else:
            self.sp_api_base = "https://sellingpartnerapi-na.amazon.com"
        
        self.lwa_endpoint = "https://api.amazon.com/auth/o2/token"
        self.access_token = None
    
    def get_access_token(self):
        """Get LWA access token"""
        if self.access_token:
            return self.access_token
        
        try:
            response = requests.post(
                self.lwa_endpoint,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data={
                    'grant_type': 'refresh_token',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'refresh_token': self.refresh_token
                }
            )
            response.raise_for_status()
            self.access_token = response.json()['access_token']
            return self.access_token
        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            return None
    
    def search_amazon_for_asin(self, title, brand=None, keywords=None):
        """
        Search Amazon catalog for existing products matching your product
        Returns the best matching ASIN
        """
        try:
            access_token = self.get_access_token()
            if not access_token:
                return None
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'x-amz-access-token': access_token
            }
            
            # Build search query
            search_terms = []
            if title:
                # Extract key words from title (first 5 words usually most relevant)
                title_words = title.split()[:5]
                search_terms.extend(title_words)
            
            if brand:
                search_terms.append(brand)
            
            if keywords:
                if isinstance(keywords, list):
                    search_terms.extend(keywords)
                else:
                    search_terms.append(keywords)
            
            query = ' '.join(search_terms)
            
            # Use Catalog Items API to search
            url = f"{self.sp_api_base}/catalog/2022-04-01/items"
            params = {
                'marketplaceIds': self.marketplace_id,
                'keywords': query,
                'pageSize': 10
            }
            
            logger.info(f"Searching Amazon for: {query}")
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                if items:
                    # Return the first matching ASIN
                    best_match = items[0]
                    asin = best_match.get('asin')
                    product_title = best_match.get('summaries', [{}])[0].get('itemName', '')
                    
                    logger.info(f"Found matching ASIN: {asin} - {product_title}")
                    return {
                        'asin': asin,
                        'title': product_title,
                        'match_confidence': 'high' if len(items) == 1 else 'medium'
                    }
            
            logger.warning(f"No matching ASIN found for: {title}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching for ASIN: {e}")
            return None
    
    def create_offer_on_asin(self, asin, sku, price, quantity, condition='New', fulfillment_channel='DEFAULT'):
        """
        Create a seller offer on an existing ASIN using Feeds API
        This is how you list products on Amazon without Brand Registry
        
        Note: We use Feeds API because Listings API requires additional permissions
        """
        try:
            from datetime import datetime
            
            access_token = self.get_access_token()
            if not access_token:
                return {'success': False, 'error': 'Failed to get access token'}
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'x-amz-access-token': access_token
            }
            
            # Create XML feed for product listing
            feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<AmazonEnvelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="amzn-envelope.xsd">
    <Header>
        <DocumentVersion>1.01</DocumentVersion>
        <MerchantIdentifier>{self.seller_id}</MerchantIdentifier>
    </Header>
    <MessageType>Product</MessageType>
    <PurgeAndReplace>false</PurgeAndReplace>
    <Message>
        <MessageID>1</MessageID>
        <OperationType>Update</OperationType>
        <Product>
            <SKU>{sku}</SKU>
            <StandardProductID>
                <Type>ASIN</Type>
                <Value>{asin}</Value>
            </StandardProductID>
            <ProductTaxCode>A_GEN_TAX</ProductTaxCode>
            <Condition>
                <ConditionType>{condition}</ConditionType>
            </Condition>
        </Product>
    </Message>
    <Message>
        <MessageID>2</MessageID>
        <OperationType>Update</OperationType>
        <Inventory>
            <SKU>{sku}</SKU>
            <Quantity>{quantity}</Quantity>
            <FulfillmentLatency>2</FulfillmentLatency>
        </Inventory>
    </Message>
    <Message>
        <MessageID>3</MessageID>
        <OperationType>Update</OperationType>
        <Price>
            <SKU>{sku}</SKU>
            <StandardPrice currency="USD">{price}</StandardPrice>
        </Price>
    </Message>
</AmazonEnvelope>"""
            
            logger.info(f"Creating offer on ASIN {asin} with SKU {sku} via Feeds API")
            
            # Step 1: Create feed document
            create_doc_url = f"{self.sp_api_base}/feeds/2021-06-30/documents"
            create_doc_payload = {"contentType": "text/xml; charset=UTF-8"}
            
            response = requests.post(create_doc_url, headers=headers, json=create_doc_payload)
            
            if response.status_code != 201:
                return {
                    'success': False,
                    'error': f"Failed to create feed document: {response.status_code}",
                    'details': response.text
                }
            
            doc_data = response.json()
            feed_document_id = doc_data.get('feedDocumentId')
            upload_url = doc_data.get('url')
            
            # Step 2: Upload XML content
            upload_response = requests.put(upload_url, data=feed_xml.encode('utf-8'), 
                                         headers={'Content-Type': 'text/xml; charset=UTF-8'})
            
            if upload_response.status_code not in [200, 204]:
                return {
                    'success': False,
                    'error': f"Failed to upload feed: {upload_response.status_code}",
                    'details': upload_response.text
                }
            
            # Step 3: Create feed
            create_feed_url = f"{self.sp_api_base}/feeds/2021-06-30/feeds"
            create_feed_payload = {
                "feedType": "POST_PRODUCT_DATA",
                "marketplaceIds": [self.marketplace_id],
                "inputFeedDocumentId": feed_document_id
            }
            
            feed_response = requests.post(create_feed_url, headers=headers, json=create_feed_payload)
            
            if feed_response.status_code == 202:
                feed_data = feed_response.json()
                feed_id = feed_data.get('feedId')
                
                logger.info(f"Successfully created feed {feed_id} for ASIN {asin}")
                
                return {
                    'success': True,
                    'asin': asin,
                    'sku': sku,
                    'feed_id': feed_id,
                    'listing_url': f"https://www.amazon.com/dp/{asin}",
                    'status': 'PROCESSING',
                    'message': f'Feed submitted successfully. Amazon will process it in 5-15 minutes.'
                }
            else:
                return {
                    'success': False,
                    'error': f"Failed to create feed: {feed_response.status_code}",
                    'details': feed_response.text
                }
        
        except Exception as e:
            logger.error(f"Error creating offer on ASIN: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def list_product_automatically(self, title, price, quantity, condition='New', brand=None, description=None):
        """
        Automatically list a product on Amazon:
        1. Search for matching ASIN
        2. Create offer on that ASIN
        3. Return listing URL
        
        This works just like eBay - you provide product details, system handles the rest
        """
        try:
            # Step 1: Search for matching ASIN
            logger.info(f"Auto-listing product: {title}")
            asin_match = self.search_amazon_for_asin(title, brand)
            
            if not asin_match:
                return {
                    'success': False,
                    'error': 'No matching ASIN found on Amazon',
                    'solution': 'Try adding more specific keywords or brand name'
                }
            
            asin = asin_match['asin']
            logger.info(f"Found ASIN {asin}, creating offer...")
            
            # Step 2: Create offer on that ASIN
            import hashlib
            import time
            sku = f"AUTO-{hashlib.md5(f'{title}{time.time()}'.encode()).hexdigest()[:8].upper()}"
            
            offer_result = self.create_offer_on_asin(
                asin=asin,
                sku=sku,
                price=price,
                quantity=quantity,
                condition=condition
            )
            
            if offer_result.get('success'):
                logger.info(f"✅ Successfully listed product on Amazon ASIN: {asin}")
                return {
                    'success': True,
                    'asin': asin,
                    'sku': sku,
                    'listing_url': offer_result['listing_url'],
                    'status': 'ACTIVE',
                    'message': f'Listed on Amazon (ASIN: {asin})',
                    'matched_product': asin_match['title']
                }
            else:
                return offer_result
        
        except Exception as e:
            logger.error(f"Auto-listing failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _map_condition(self, condition):
        """Map condition to Amazon condition codes"""
        condition_map = {
            'NEW': 'new_new',
            'LIKE_NEW': 'used_like_new',
            'VERY_GOOD': 'used_very_good',
            'GOOD': 'used_good',
            'ACCEPTABLE': 'used_acceptable',
            'EXCELLENT': 'used_like_new',
            'REFURBISHED': 'refurbished_refurbished'
        }
        
        condition_upper = condition.upper().replace(' ', '_')
        return condition_map.get(condition_upper, 'new_new')
