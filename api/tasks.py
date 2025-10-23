# Simplified Tasks for Core Marketplace Operations
"""
Essential task functions for marketplace integration.
Simplified for basic workflow: user submission → admin approval → dual listing → cross-platform removal
"""

import logging
from django.utils import timezone
from .models import Product
from .marketplace_service import MarketplaceService

logger = logging.getLogger(__name__)


def remove_from_other_platform_when_sold(product_id, sold_platform):
    """
    Simple function to remove listing from other platform when product is sold
    This is the core automation needed for your workflow
    """
    try:
        product = Product.objects.get(id=product_id)
        marketplace = MarketplaceService()
        
        if sold_platform == 'EBAY' and product.amazon_listing_id:
            # Product sold on eBay, remove from Amazon
            marketplace.remove_listing(product, 'AMAZON')
            logger.info(f"Removed product {product_id} from Amazon after eBay sale")
            
        elif sold_platform == 'AMAZON' and product.ebay_listing_id:
            # Product sold on Amazon, remove from eBay  
            marketplace.remove_listing(product, 'EBAY')
            logger.info(f"Removed product {product_id} from eBay after Amazon sale")
            
        return {'success': True, 'message': f'Removed from other platform after {sold_platform} sale'}
        
    except Exception as e:
        logger.error(f"Failed to remove product {product_id} from other platform: {str(e)}")
        return {'success': False, 'error': str(e)}


def list_product_on_both_platforms(product_id):
    """
    Simple function to list an approved product on both eBay and Amazon
    """
    try:
        product = Product.objects.get(id=product_id)
        marketplace = MarketplaceService()
        
        # List on both platforms
        result = marketplace.list_on_both_platforms(product)
        
        if result.get('success'):
            logger.info(f"Successfully listed product {product_id} on both platforms")
            return {'success': True, 'message': 'Product listed on both platforms'}
        else:
            logger.error(f"Failed to list product {product_id}: {result.get('error')}")
            return {'success': False, 'error': result.get('error')}
            
    except Exception as e:
        logger.error(f"Failed to list product {product_id}: {str(e)}")
        return {'success': False, 'error': str(e)}


# Optional: Celery task decorators for background processing (if Celery is installed)
try:
    from celery import shared_task
    
    @shared_task
    def remove_from_other_platform_task(product_id, sold_platform):
        return remove_from_other_platform_when_sold(product_id, sold_platform)
    
    @shared_task
    def list_product_task(product_id):
        return list_product_on_both_platforms(product_id)
        
except ImportError:
    # Celery not available, tasks will run synchronously
    logger.info("Celery not available, using synchronous task execution")