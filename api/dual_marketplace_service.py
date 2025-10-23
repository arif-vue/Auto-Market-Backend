"""
Production-Level Dual Marketplace Listing Service
Handles eBay + Amazon listing, unlisting, and cross-platform synchronization
"""

import json
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from .models import Product
from .marketplace_service import EbayAPIService
from .amazon_sp_service import AmazonSPAPIService

logger = logging.getLogger(__name__)


class DualMarketplaceService:
    """
    Production-level service for managing products across eBay and Amazon
    """
    
    def __init__(self):
        self.ebay_api = EbayAPIService()
        self.amazon_service = AmazonSPAPIService()
        
    def list_product_both_platforms(self, product_id):
        """
        List a product on both eBay and Amazon simultaneously
        Returns live listing URLs for production use
        """
        try:
            product = Product.objects.get(id=product_id)
            
            if product.listing_status != 'APPROVED':
                return {
                    'success': False,
                    'error': 'Product must be approved before listing',
                    'product_status': product.listing_status
                }
            
            logger.info(f"Starting dual platform listing for product {product_id}: {product.title}")
            
            # Prepare listing data
            listing_data = self._prepare_listing_data(product)
            
            results = {
                'success': True,
                'product_id': product_id,
                'product_title': product.title,
                'listings': {},
                'errors': []
            }
            
            # List on eBay
            ebay_result = self._list_on_ebay(product, listing_data)
            results['listings']['ebay'] = ebay_result
            
            # List on Amazon
            amazon_result = self._list_on_amazon(product, listing_data)
            results['listings']['amazon'] = amazon_result
            
            # Update product status based on listing results
            self._update_product_status(product, ebay_result, amazon_result)
            
            # Check if both platforms succeeded
            ebay_success = ebay_result.get('success', False)
            amazon_success = amazon_result.get('success', False)
            
            if ebay_success and amazon_success:
                results['status'] = 'LISTED_BOTH'
                results['message'] = 'Successfully listed on both eBay and Amazon'
            elif ebay_success or amazon_success:
                results['status'] = 'LISTED_PARTIAL'
                results['message'] = 'Listed on one platform, check errors for the other'
                if not ebay_success:
                    results['errors'].append(f"eBay: {ebay_result.get('error', 'Unknown error')}")
                if not amazon_success:
                    results['errors'].append(f"Amazon: {amazon_result.get('error', 'Unknown error')}")
            else:
                results['success'] = False
                results['status'] = 'FAILED'
                results['message'] = 'Failed to list on both platforms'
                results['errors'].extend([
                    f"eBay: {ebay_result.get('error', 'Unknown error')}",
                    f"Amazon: {amazon_result.get('error', 'Unknown error')}"
                ])
            
            return results
            
        except Product.DoesNotExist:
            return {
                'success': False,
                'error': 'Product not found',
                'product_id': product_id
            }
        except Exception as e:
            logger.error(f"Error in dual platform listing: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'product_id': product_id
            }
    
    def _prepare_listing_data(self, product):
        """Prepare standardized listing data for both platforms"""
        
        # Get product images
        images = []
        for img in product.images.all():
            if img.image and hasattr(img.image, 'url'):
                # Convert to absolute URL if needed
                image_url = img.image.url
                if image_url.startswith('/'):
                    # Assuming you have a base URL configured
                    base_url = getattr(settings, 'SITE_BASE_URL', 'http://10.10.12.15:8000')
                    image_url = f"{base_url}{image_url}"
                images.append(image_url)
        
        return {
            'title': product.title,
            'description': self._format_description(product),
            'price': float(product.final_listing_price or product.estimated_value),
            'condition': self._map_condition(product.condition),
            'images': images,
            'category': self._determine_category(product),
            'brand': self._extract_brand(product.title, product.description),
            'sku': f"AUTO-{product.id}",
            'quantity': 1,
            'defects': product.defects
        }
    
    def _list_on_ebay(self, product, listing_data):
        """List product on eBay and return result with live URL"""
        try:
            logger.info(f"Listing on eBay: {product.title}")
            
            # Use the eBay API service to create listing
            ebay_listing = self.ebay_api.create_listing(product)
            
            if ebay_listing.get('success'):
                # Update product with eBay listing info
                product.ebay_listing_id = ebay_listing['listing_id']
                product.ebay_listing_url = ebay_listing['listing_url']
                product.save()
                
                return {
                    'success': True,
                    'platform': 'eBay',
                    'listing_id': ebay_listing['listing_id'],
                    'listing_url': ebay_listing['listing_url'],
                    'status': 'ACTIVE',
                    'listed_at': timezone.now().isoformat()
                }
            else:
                return {
                    'success': False,
                    'platform': 'eBay',
                    'error': ebay_listing.get('error', 'Unknown eBay listing error')
                }
                
        except Exception as e:
            logger.error(f"eBay listing error: {str(e)}")
            return {
                'success': False,
                'platform': 'eBay',
                'error': f'eBay API error: {str(e)}'
            }
    
    def _list_on_amazon(self, product, listing_data):
        """List product on Amazon using automatic ASIN matching (like eBay)"""
        try:
            logger.info(f"Listing on Amazon using SP-API: {product.title}")
            
            # Import the automatic listing helper
            from .amazon_listing_helper import AmazonListingHelper
            amazon_helper = AmazonListingHelper()
            
            # Prepare data
            title = product.title
            price = float(product.final_listing_price or product.estimated_value)
            condition = product.condition or 'NEW'
            brand = self._extract_brand(product.title, product.description)
            description = self._format_description(product)
            quantity = 1
            
            # Use automatic listing (searches for ASIN and creates offer)
            amazon_listing = amazon_helper.list_product_automatically(
                title=title,
                price=price,
                quantity=quantity,
                condition=condition,
                brand=brand,
                description=description
            )
            
            if amazon_listing.get('success'):
                # Update product with Amazon listing info
                listing_id = amazon_listing.get('asin')
                listing_url = amazon_listing.get('listing_url')
                
                product.amazon_listing_id = listing_id
                product.amazon_listing_url = listing_url
                product.save()
                
                logger.info(f"✅ Amazon listing successful: ASIN {listing_id}")
                
                return {
                    'success': True,
                    'platform': 'Amazon',
                    'listing_id': listing_id,
                    'listing_url': listing_url,
                    'status': 'ACTIVE',
                    'listed_at': timezone.now().isoformat(),
                    'message': f"Listed on Amazon (matched to {amazon_listing.get('matched_product', 'existing product')})",
                    'sku': amazon_listing.get('sku')
                }
            else:
                logger.error(f"Amazon listing failed: {amazon_listing.get('error', 'Unknown error')}")
                return {
                    'success': False,
                    'platform': 'Amazon',
                    'error': amazon_listing.get('error', 'Unknown Amazon listing error'),
                    'solution': amazon_listing.get('solution', '')
                }
                
        except Exception as e:
            logger.error(f"Amazon listing error: {str(e)}")
            return {
                'success': False,
                'platform': 'Amazon',
                'error': f'Amazon SP-API error: {str(e)}'
            }
    
    def unlist_product_both_platforms(self, product_id):
        """
        Remove product listing from both eBay and Amazon
        """
        try:
            product = Product.objects.get(id=product_id)
            logger.info(f"Unlisting from both platforms: {product.title}")
            
            results = {
                'success': True,
                'product_id': product_id,
                'product_title': product.title,
                'unlistings': {},
                'errors': []
            }
            
            # Unlist from eBay
            if product.ebay_listing_id:
                ebay_result = self._unlist_from_ebay(product)
                results['unlistings']['ebay'] = ebay_result
            else:
                results['unlistings']['ebay'] = {
                    'success': True,
                    'message': 'No eBay listing found to unlist'
                }
            
            # Unlist from Amazon
            if product.amazon_listing_id:
                amazon_result = self._unlist_from_amazon(product)
                results['unlistings']['amazon'] = amazon_result
            else:
                results['unlistings']['amazon'] = {
                    'success': True,
                    'message': 'No Amazon listing found to unlist'
                }
            
            # Update product status
            product.listing_status = 'REMOVED'
            product.save()
            
            return results
            
        except Product.DoesNotExist:
            return {
                'success': False,
                'error': 'Product not found',
                'product_id': product_id
            }
        except Exception as e:
            logger.error(f"Error unlisting product: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'product_id': product_id
            }
    
    def mark_sold_and_unlist_other(self, product_id, sold_platform, sale_price=None):
        """
        Mark product as sold on one platform and automatically unlist from the other
        """
        try:
            product = Product.objects.get(id=product_id)
            sold_platform = sold_platform.upper()
            
            logger.info(f"Product {product.title} sold on {sold_platform}, unlisting from other platform")
            
            # Mark as sold
            product.mark_sold(sold_platform, sale_price)
            
            results = {
                'success': True,
                'product_id': product_id,
                'product_title': product.title,
                'sold_platform': sold_platform,
                'sale_price': sale_price,
                'cross_platform_unlisting': {}
            }
            
            # Unlist from the other platform
            if sold_platform == 'EBAY' and product.amazon_listing_id:
                # Sold on eBay, unlist from Amazon
                amazon_result = self._unlist_from_amazon(product)
                results['cross_platform_unlisting']['amazon'] = amazon_result
                
            elif sold_platform == 'AMAZON' and product.ebay_listing_id:
                # Sold on Amazon, unlist from eBay
                ebay_result = self._unlist_from_ebay(product)
                results['cross_platform_unlisting']['ebay'] = ebay_result
            
            return results
            
        except Product.DoesNotExist:
            return {
                'success': False,
                'error': 'Product not found',
                'product_id': product_id
            }
        except Exception as e:
            logger.error(f"Error in sold/unlist operation: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'product_id': product_id
            }
    
    def _unlist_from_ebay(self, product):
        """Unlist product from eBay"""
        try:
            result = self.ebay_api.end_listing(product.ebay_listing_id)
            if result.get('success'):
                product.ebay_listing_id = None
                product.ebay_listing_url = None
                product.save()
                return {
                    'success': True,
                    'platform': 'eBay',
                    'message': 'Successfully unlisted from eBay'
                }
            else:
                return {
                    'success': False,
                    'platform': 'eBay',
                    'error': result.get('error', 'Failed to unlist from eBay')
                }
        except Exception as e:
            return {
                'success': False,
                'platform': 'eBay',
                'error': f'eBay unlisting error: {str(e)}'
            }
    
    def _unlist_from_amazon(self, product):
        """Unlist product from Amazon"""
        try:
            result = self.amazon_service.delete_product_listing(product.amazon_listing_id)
            if result.get('success'):
                product.amazon_listing_id = None
                product.amazon_listing_url = None
                product.save()
                return {
                    'success': True,
                    'platform': 'Amazon',
                    'message': 'Successfully unlisted from Amazon'
                }
            else:
                return {
                    'success': False,
                    'platform': 'Amazon',
                    'error': result.get('error', 'Failed to unlist from Amazon')
                }
        except Exception as e:
            return {
                'success': False,
                'platform': 'Amazon',
                'error': f'Amazon unlisting error: {str(e)}'
            }
    
    def _update_product_status(self, product, ebay_result, amazon_result):
        """Update product listing status based on platform results"""
        ebay_success = ebay_result.get('success', False)
        amazon_success = amazon_result.get('success', False)
        
        if ebay_success and amazon_success:
            product.listing_status = 'LISTED'
        elif ebay_success:
            product.listing_status = 'EBAY_ONLY'
        elif amazon_success:
            product.listing_status = 'AMAZON_ONLY'
        else:
            product.listing_status = 'FAILED'
        
        product.save()
    
    def _format_description(self, product):
        """Format product description for marketplace listing"""
        description = product.description
        
        if product.defects:
            description += f"\n\nCondition Notes: {product.defects}"
        
        # Add auto-generated footer
        description += "\n\n--- Listed via AutoMarket ---"
        description += "\nFast shipping and secure packaging guaranteed!"
        
        return description
    
    def _map_condition(self, condition):
        """Map internal condition to marketplace standards"""
        condition_mapping = {
            'NEW': {'ebay': 'New', 'amazon': 'New'},
            'LIKE_NEW': {'ebay': 'Like New', 'amazon': 'Used - Like New'},
            'EXCELLENT': {'ebay': 'Excellent', 'amazon': 'Used - Very Good'},
            'GOOD': {'ebay': 'Good', 'amazon': 'Used - Good'},
            'FAIR': {'ebay': 'Fair', 'amazon': 'Used - Acceptable'},
            'POOR': {'ebay': 'Poor', 'amazon': 'Used - Acceptable'}
        }
        
        return condition_mapping.get(condition, {
            'ebay': 'Good',
            'amazon': 'Used - Good'
        })
    
    def _determine_category(self, product):
        """Determine appropriate category for each platform"""
        # This would typically use AI or keyword matching
        # For now, return default electronics category
        return {
            'ebay': '293',  # Cell Phones & Accessories
            'amazon': 'Electronics'
        }
    
    def _extract_brand(self, title, description):
        """Extract brand from product title/description"""
        common_brands = [
            'Apple', 'Samsung', 'Google', 'Sony', 'LG', 'Huawei', 'OnePlus',
            'Dell', 'HP', 'Lenovo', 'ASUS', 'Acer', 'MSI', 'Canon', 'Nikon'
        ]
        
        text = f"{title} {description}".lower()
        
        for brand in common_brands:
            if brand.lower() in text:
                return brand
        
        return 'Generic'
    
    def get_listing_status(self, product_id):
        """Get current listing status across both platforms"""
        try:
            product = Product.objects.get(id=product_id)
            
            status = {
                'product_id': product_id,
                'product_title': product.title,
                'overall_status': product.listing_status,
                'platforms': {
                    'ebay': {
                        'listed': bool(product.ebay_listing_id),
                        'listing_id': product.ebay_listing_id,
                        'listing_url': product.ebay_listing_url
                    },
                    'amazon': {
                        'listed': bool(product.amazon_listing_id),
                        'listing_id': product.amazon_listing_id,
                        'listing_url': product.amazon_listing_url
                    }
                }
            }
            
            return status
            
        except Product.DoesNotExist:
            return {
                'error': 'Product not found',
                'product_id': product_id
            }