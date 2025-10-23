"""
URL Configuration for Dual Marketplace Operations
"""

from django.urls import path
from . import marketplace_views

app_name = 'marketplace'

urlpatterns = [
    # Dual platform operations
    path('list-dual/', marketplace_views.list_product_dual_marketplace, name='list-dual'),
    path('unlist-dual/', marketplace_views.unlist_product_dual_marketplace, name='unlist-dual'),
    path('sold-cross-unlist/', marketplace_views.mark_sold_cross_unlist, name='sold-cross-unlist'),
    
    # Status and monitoring
    path('status/<int:product_id>/', marketplace_views.get_listing_status, name='listing-status'),
    path('dashboard/', marketplace_views.marketplace_dashboard, name='dashboard'),
    path('sync-status/', marketplace_views.sync_listing_status, name='sync-status'),
    
    # Bulk operations
    path('bulk-list/', marketplace_views.bulk_list_products, name='bulk-list'),
]