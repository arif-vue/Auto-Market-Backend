from django.urls import path, include
from . import views
from .legal_views import privacy_policy, terms_of_service, about_page

app_name = 'api'

# Import test view removed - file doesn't exist

urlpatterns = [
    # Root API endpoint
    path('', views.api_root, name='api-root'),
    
    # Test endpoint removed - view doesn't exist
    
    # User submission endpoints (No authentication required)
    path('submissions/', views.SubmissionBatchCreateView.as_view(), name='create-submission'),
    path('submissions/list/', views.SubmissionBatchListView.as_view(), name='list-submissions'),
    path('submissions/<int:pk>/', views.SubmissionBatchDetailView.as_view(), name='submission-detail'),
    path('submissions/<int:batch_id>/status/', views.check_submission_status, name='check-submission-status'),
    
    # User product endpoints
    path('products/', views.UserProductListView.as_view(), name='list-products'),
    path('products/<int:pk>/', views.UserProductDetailView.as_view(), name='product-detail'),
    
    # User dashboard
    path('dashboard/', views.user_dashboard, name='user-dashboard'),
    
    # AI Service endpoints
    path('ai/price-estimate/', views.ai_price_estimate, name='ai-price-estimate'),
    path('ai/detect-category/', views.ai_detect_category, name='ai-detect-category'),
    path('ai/market-insights/', views.ai_market_insights, name='ai-market-insights'),
    
    # Two-step submission flow
    path('items/estimate/', views.item_price_estimate_with_images, name='item-estimate-with-images'),
    path('submissions/contact-only/', views.contact_only_submission, name='contact-only-submission'),
    
    # Temporary products management
    path('temp-products/cancel/', views.cancel_temp_items, name='cancel-temp-items'),
    
    # Enhanced Admin API
    path('admin/', include('api.admin_urls')),
    
    # eBay Integration
    path('ebay/', include('api.ebay_urls')),
    
    # Amazon SP-API Integration
    path('amazon/', include('api.amazon_urls')),
    
    # Dual Marketplace Operations
    path('marketplace/', include('api.marketplace_urls')),
    
    # Legal Pages
    path('privacy/', privacy_policy, name='privacy-policy'),
    path('terms/', terms_of_service, name='terms-of-service'),
    path('about/', about_page, name='about-page'),
]