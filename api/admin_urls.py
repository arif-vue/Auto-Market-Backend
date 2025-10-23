# Admin URLs for Auto Market
from django.urls import path
from . import admin_views

app_name = 'admin_api'

urlpatterns = [
    # Admin Authentication
    path('auth/login/', admin_views.admin_login, name='admin-login'),
    path('auth/password-reset/request/', admin_views.admin_password_reset, name='admin-password-reset-request'),
    path('auth/password-reset/confirm/', admin_views.admin_password_reset_confirm, name='admin-password-reset-confirm'),
    
    # Admin Dashboard
    path('dashboard/stats/', admin_views.admin_dashboard_stats, name='admin-dashboard-stats'),
    path('dashboard/activities/', admin_views.admin_recent_activities, name='admin-recent-activities'),
    
    # Submission Management
    path('submissions/', admin_views.AdminSubmissionListView.as_view(), name='admin-submission-list'),
    path('submissions/<int:pk>/', admin_views.AdminSubmissionDetailView.as_view(), name='admin-submission-detail'),
    
    # Product Management
    path('products/', admin_views.AdminProductListView.as_view(), name='admin-product-list'),
    path('products/<int:pk>/', admin_views.AdminProductDetailView.as_view(), name='admin-product-detail'),
    path('products/<int:product_id>/update-status/', admin_views.admin_product_update_status, name='admin-product-update-status'),
    path('products/<int:product_id>/update-price/', admin_views.admin_product_update_price, name='admin-product-update-price'),
    path('products/<int:product_id>/delete/', admin_views.admin_product_delete, name='admin-product-delete'),
    path('products/<int:product_id>/action/', admin_views.admin_product_update_status, name='admin-product-action'),  # Backward compatibility
    
    # Marketplace Integration
    path('products/<int:product_id>/list-marketplace/', admin_views.list_product_on_marketplace, name='admin-list-marketplace'),
    path('marketplace/categories/', admin_views.get_marketplace_categories, name='admin-marketplace-categories'),
    path('products/<int:product_id>/mark-sold/', admin_views.mark_product_sold, name='admin-mark-sold'),
    path('marketplace/dashboard/', admin_views.marketplace_dashboard_stats, name='admin-marketplace-dashboard'),
    
    # eBay Integration Management
    path('ebay/status/', admin_views.admin_ebay_status, name='admin-ebay-status'),
    path('ebay/listings/', admin_views.admin_ebay_listings, name='admin-ebay-listings'),
]