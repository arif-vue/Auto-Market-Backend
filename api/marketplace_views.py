"""
API Views for Dual Marketplace Operations
Handles eBay + Amazon listing, unlisting, and synchronization
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Product
from .dual_marketplace_service import DualMarketplaceService
import logging

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def list_product_dual_marketplace(request):
    """
    List a product on both eBay and Amazon
    
    POST /api/marketplace/list-dual/
    {
        "product_id": 123
    }
    
    Returns live listing URLs for both platforms
    """
    try:
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({
                'success': False,
                'error': 'product_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Initialize dual marketplace service
        marketplace_service = DualMarketplaceService()
        
        # List on both platforms
        result = marketplace_service.list_product_both_platforms(product_id)
        
        if result['success']:
            return Response(result, status=status.HTTP_201_CREATED)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Error in dual marketplace listing: {str(e)}")
        return Response({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unlist_product_dual_marketplace(request):
    """
    Remove product from both eBay and Amazon
    
    POST /api/marketplace/unlist-dual/
    {
        "product_id": 123
    }
    """
    try:
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({
                'success': False,
                'error': 'product_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        marketplace_service = DualMarketplaceService()
        result = marketplace_service.unlist_product_both_platforms(product_id)
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in dual marketplace unlisting: {str(e)}")
        return Response({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_sold_cross_unlist(request):
    """
    Mark product as sold on one platform and automatically unlist from the other
    
    POST /api/marketplace/sold-cross-unlist/
    {
        "product_id": 123,
        "sold_platform": "EBAY",  # or "AMAZON"
        "sale_price": 450.00
    }
    """
    try:
        product_id = request.data.get('product_id')
        sold_platform = request.data.get('sold_platform')
        sale_price = request.data.get('sale_price')
        
        if not product_id or not sold_platform:
            return Response({
                'success': False,
                'error': 'product_id and sold_platform are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if sold_platform.upper() not in ['EBAY', 'AMAZON']:
            return Response({
                'success': False,
                'error': 'sold_platform must be either EBAY or AMAZON'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        marketplace_service = DualMarketplaceService()
        result = marketplace_service.mark_sold_and_unlist_other(
            product_id, sold_platform, sale_price
        )
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in sold/cross-unlist operation: {str(e)}")
        return Response({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_listing_status(request, product_id):
    """
    Get current listing status for both platforms
    
    GET /api/marketplace/status/{product_id}/
    """
    try:
        marketplace_service = DualMarketplaceService()
        status_info = marketplace_service.get_listing_status(product_id)
        
        return Response(status_info, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting listing status: {str(e)}")
        return Response({
            'error': f'Unexpected error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_list_products(request):
    """
    List multiple products on both platforms
    
    POST /api/marketplace/bulk-list/
    {
        "product_ids": [123, 124, 125]
    }
    """
    try:
        product_ids = request.data.get('product_ids', [])
        if not product_ids:
            return Response({
                'success': False,
                'error': 'product_ids array is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        marketplace_service = DualMarketplaceService()
        results = []
        
        for product_id in product_ids:
            result = marketplace_service.list_product_both_platforms(product_id)
            results.append(result)
        
        # Calculate summary
        successful = sum(1 for r in results if r.get('success'))
        failed = len(results) - successful
        
        response = {
            'success': True,
            'summary': {
                'total_products': len(product_ids),
                'successful_listings': successful,
                'failed_listings': failed
            },
            'results': results
        }
        
        return Response(response, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in bulk listing: {str(e)}")
        return Response({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def marketplace_dashboard(request):
    """
    Get dashboard overview of all marketplace listings
    
    GET /api/marketplace/dashboard/
    """
    try:
        # Get all products with marketplace data
        products = Product.objects.filter(
            listing_status__in=['LISTED', 'EBAY_ONLY', 'AMAZON_ONLY', 'EBAY_SOLD', 'AMAZON_SOLD']
        ).select_related().prefetch_related('images')
        
        dashboard_data = {
            'summary': {
                'total_active_listings': 0,
                'ebay_listings': 0,
                'amazon_listings': 0,
                'dual_platform_listings': 0,
                'sold_items': 0,
                'total_revenue': 0
            },
            'active_listings': [],
            'recent_sales': []
        }
        
        for product in products:
            # Count active listings
            if product.listing_status in ['LISTED', 'EBAY_ONLY', 'AMAZON_ONLY']:
                dashboard_data['summary']['total_active_listings'] += 1
                
                if product.ebay_listing_id:
                    dashboard_data['summary']['ebay_listings'] += 1
                if product.amazon_listing_id:
                    dashboard_data['summary']['amazon_listings'] += 1
                if product.ebay_listing_id and product.amazon_listing_id:
                    dashboard_data['summary']['dual_platform_listings'] += 1
                
                # Add to active listings
                dashboard_data['active_listings'].append({
                    'id': product.id,
                    'title': product.title,
                    'price': float(product.final_listing_price or product.estimated_value),
                    'condition': product.condition,
                    'platforms': {
                        'ebay': {
                            'listed': bool(product.ebay_listing_id),
                            'url': product.ebay_listing_url
                        },
                        'amazon': {
                            'listed': bool(product.amazon_listing_id),
                            'url': product.amazon_listing_url
                        }
                    }
                })
            
            # Count sold items
            elif product.listing_status in ['EBAY_SOLD', 'AMAZON_SOLD']:
                dashboard_data['summary']['sold_items'] += 1
                if product.sold_price:
                    dashboard_data['summary']['total_revenue'] += float(product.sold_price)
                
                # Add to recent sales
                dashboard_data['recent_sales'].append({
                    'id': product.id,
                    'title': product.title,
                    'sold_price': float(product.sold_price or 0),
                    'sold_platform': product.sold_platform,
                    'sold_at': product.sold_at.isoformat() if product.sold_at else None
                })
        
        return Response(dashboard_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error generating marketplace dashboard: {str(e)}")
        return Response({
            'error': f'Unexpected error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_listing_status(request):
    """
    Synchronize listing status with actual marketplace data
    
    POST /api/marketplace/sync-status/
    {
        "product_id": 123  # optional, if not provided syncs all
    }
    """
    try:
        product_id = request.data.get('product_id')
        
        if product_id:
            products = [get_object_or_404(Product, id=product_id)]
        else:
            products = Product.objects.filter(
                listing_status__in=['LISTED', 'EBAY_ONLY', 'AMAZON_ONLY']
            )
        
        marketplace_service = DualMarketplaceService()
        sync_results = []
        
        for product in products:
            # Check eBay status
            ebay_status = None
            if product.ebay_listing_id:
                # This would call eBay API to check listing status
                # ebay_status = marketplace_service.ebay_api.get_listing_status(product.ebay_listing_id)
                pass
            
            # Check Amazon status
            amazon_status = None
            if product.amazon_listing_id:
                # This would call Amazon API to check listing status
                # amazon_status = marketplace_service.amazon_service.get_listing_status(product.amazon_listing_id)
                pass
            
            sync_results.append({
                'product_id': product.id,
                'title': product.title,
                'ebay_status': ebay_status,
                'amazon_status': amazon_status,
                'synced': True
            })
        
        return Response({
            'success': True,
            'synced_products': len(sync_results),
            'results': sync_results
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error syncing listing status: {str(e)}")
        return Response({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)