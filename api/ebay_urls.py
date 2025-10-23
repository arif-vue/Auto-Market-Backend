"""
eBay Integration URL Configuration
"""

from django.urls import path
from . import ebay_views

app_name = 'ebay'

urlpatterns = [
    # OAuth flow
    path('auth/test/', ebay_views.ebay_auth_test, name='auth-test'),
    path('auth/start/', ebay_views.ebay_auth_start, name='auth-start'),
    path('auth/declined/', ebay_views.ebay_auth_declined, name='auth-declined'),
    path('callback/', ebay_views.ebay_auth_callback, name='auth-callback'),
    
    # Product listing management
    path('list-product/', ebay_views.ebay_list_product, name='list-product'),
    path('end-listing/', ebay_views.ebay_end_listing, name='end-listing'),
    
    # Status and management
    path('status/', ebay_views.ebay_status, name='status'),
]