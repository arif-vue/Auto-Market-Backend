from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse
import logging
import os

from .models import Product, SubmissionBatch, TempProduct
from .serializers import (
    SubmissionBatchSerializer, SubmissionBatchListSerializer,
    ProductSerializer, ProductStatusUpdateSerializer,
    TempProductSerializer, ContactOnlySerializer
)
from .ai_service import AutoMarketAIService

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([])
def api_root(request):
    """
    API Root endpoint - provides available endpoints information
    """
    return Response({
        'message': 'Auto Market API',
        'version': '1.0',
        'authentication_required': False,
        'endpoints': {
            # Two-step submission flow
            'item_estimate': '/api/items/estimate/',  # Step 1: Get price estimation
            'submissions': '/api/submissions/',        # Step 2: Submit with contact info
            
            # Other endpoints
            'products': '/api/products/',
            'ai_price_estimate': '/api/ai/price-estimate/',
            'ai_detect_category': '/api/ai/detect-category/',
            'ai_market_insights': '/api/ai/market-insights/',
            'dashboard': '/api/dashboard/',
            'admin': '/api/admin/'
        },
        'two_step_submission_flow': {
            'description': 'Optimized for frontend state management',
            'step_1': {
                'endpoint': 'POST /api/items/estimate/',
                'purpose': 'Get AI price estimation for display to user',
                'required_fields': ['title', 'description', 'condition', 'uploaded_images (3-8 images)'],
                'returns': 'Price estimation only - no database save',
                'frontend_action': 'Show price to user, store item data in state'
            },
            'step_2': {
                'endpoint': 'POST /api/submissions/',
                'purpose': 'Submit complete data (item + contact) together',
                'required_fields': ['full_name', 'email', 'phone', 'pickup_address', 'pickup_date', 'privacy_policy_accepted', 'products'],
                'returns': 'Submission confirmation with tracking ID',
                'frontend_action': 'Send all data together after user provides contact info'
            },
            'flow_benefits': ['No complex tokens', 'No cache expiration', 'Simple state management', 'User can review price before committing']
        },
        'submissions_api_help': {
            'endpoint': 'POST /api/submissions/',
            'authentication': '❌ NO AUTHENTICATION REQUIRED',
            'method': 'POST',
            'content_type': 'application/json',
            'required_fields': {
                'full_name': 'string - Customer full name',
                'email': 'string - Customer email address',
                'phone': 'string - Customer phone number',
                'pickup_date': 'string - Future date in ISO format (2025-12-30T14:00:00Z)',
                'pickup_address': 'string - Complete pickup address',
                'privacy_policy_accepted': 'boolean - Must be true',
                'products': 'array - Array of product objects'
            },
            'product_fields': {
                'title': 'string - Product title (min 5 chars)',
                'description': 'string - Product description (min 10 chars)',
                'condition': 'string - EXCELLENT, GOOD, FAIR, or POOR',
                'defects': 'string - Description of defects or "None"',
                'uploaded_images': 'array - 1-8 base64 encoded images (data:image/jpeg;base64,...)'
            },
            'example_request': {
                'full_name': 'John Smith',
                'email': 'john@example.com',
                'phone': '+1234567890',
                'pickup_date': '2025-12-30T14:00:00Z',
                'pickup_address': '123 Main St, City, State 12345',
                'privacy_policy_accepted': True,
                'products': [
                    {
                        'title': 'iPhone 14 Pro 256GB',
                        'description': 'Excellent condition iPhone with all accessories',
                        'condition': 'EXCELLENT',
                        'defects': 'Minor scratches on back case',
                        'uploaded_images': ['data:image/jpeg;base64,/9j/4AAQ...']
                    }
                ]
            }
        }
    })


class SubmissionBatchCreateView(generics.CreateAPIView):
    """
    Create a new submission batch with multiple products - No authentication required
    """
    serializer_class = SubmissionBatchSerializer
    permission_classes = []

    def perform_create(self, serializer):
        # Save with user if authenticated, otherwise save as anonymous
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)
    
    def create(self, request, *args, **kwargs):
        """Override create to provide clearer error messages"""
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            # Create a more user-friendly error response
            error_response = {
                'status': 'error',
                'message': '🚨 VALIDATION ERROR: Missing or invalid fields (NOT an authentication issue)',
                'authentication_required': False,
                'errors': serializer.errors,
                'required_fields': {
                    'submission': [
                        'full_name', 'email', 'phone', 'pickup_date', 
                        'pickup_address', 'privacy_policy_accepted', 'products'
                    ],
                    'each_product': [
                        'title', 'description', 'condition', 'defects', 'uploaded_images'
                    ],
                    'notes': {
                        'uploaded_images': 'Must contain 1-8 base64 encoded images per product',
                        'condition': 'Must be one of: EXCELLENT, GOOD, FAIR, POOR',
                        'pickup_date': 'Must be a future date in ISO format (2025-12-30T14:00:00Z)',
                        'privacy_policy_accepted': 'Must be true'
                    }
                }
            }
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)
        
        return super().create(request, *args, **kwargs)
    
    def handle_exception(self, exc):
        """Override to ensure no authentication errors are returned"""
        response = super().handle_exception(exc)
        
        # If it's a 401 Unauthorized, convert it to a clear message
        if response.status_code == 401:
            response.data = {
                'status': 'error',
                'message': '🚨 This endpoint does NOT require authentication. Check your request data format.',
                'authentication_required': False,
                'hint': 'Make sure you are sending proper JSON with all required fields'
            }
            response.status_code = 400
        
        return response


class SubmissionBatchListView(generics.ListAPIView):
    """
    List all submission batches - Authentication optional
    If authenticated, shows user's batches; if not authenticated, requires email parameter
    """
    serializer_class = SubmissionBatchListSerializer
    permission_classes = []

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return SubmissionBatch.objects.filter(user=self.request.user).order_by('-created_at')
        else:
            # For anonymous users, require email parameter to view their submissions
            email = self.request.query_params.get('email')
            if email:
                return SubmissionBatch.objects.filter(email=email, user__isnull=True).order_by('-created_at')
            return SubmissionBatch.objects.none()


class SubmissionBatchDetailView(generics.RetrieveAPIView):
    """
    Get detailed view of a submission batch including all products - Authentication optional
    """
    serializer_class = SubmissionBatchSerializer
    permission_classes = []

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return SubmissionBatch.objects.filter(user=self.request.user)
        else:
            # For anonymous users, show all batches (they can access by ID if they know it)
            # In production, you might want to add email verification
            return SubmissionBatch.objects.filter(user__isnull=True)


# User-facing views
@api_view(['GET'])
@permission_classes([])
def check_submission_status(request, batch_id):
    """
    Check submission status by batch ID and email - No authentication required
    """
    email = request.query_params.get('email')
    if not email:
        return Response({
            'error': 'Email parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        batch = SubmissionBatch.objects.get(id=batch_id, email=email)
        serializer = SubmissionBatchSerializer(batch)
        return Response(serializer.data)
    except SubmissionBatch.DoesNotExist:
        return Response({
            'error': 'Submission not found or email does not match'
        }, status=status.HTTP_404_NOT_FOUND)


class UserProductListView(generics.ListAPIView):
    """
    List all products for the authenticated user
    """
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(user=self.request.user).order_by('-created_at')


class UserProductDetailView(generics.RetrieveAPIView):
    """
    Get detailed view of a specific product
    """
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(user=self.request.user)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_dashboard(request):
    """
    Dashboard endpoint providing summary data for the user
    """
    user = request.user
    
    # Get user's submission batches summary
    batches = SubmissionBatch.objects.filter(user=user)
    products = Product.objects.filter(user=user)
    
    dashboard_data = {
        'total_submissions': batches.count(),
        'pending_submissions': batches.filter(batch_status='PENDING_REVIEW').count(),
        'approved_submissions': batches.filter(batch_status='APPROVED').count(),
        'total_products': products.count(),
        'listed_products': products.filter(listing_status='LISTED').count(),
        'sold_products': products.filter(
            listing_status__in=['EBAY_SOLD', 'AMAZON_SOLD']
        ).count(),
        'total_earnings': sum(
            p.sold_price for p in products.filter(sold_price__isnull=False)
        ) or 0,
        'recent_submissions': SubmissionBatchListSerializer(
            batches.order_by('-created_at')[:5], many=True
        ).data
    }
    
    return Response(dashboard_data)

# AI Service Views
@api_view(['POST'])
@permission_classes([])  # Allow public access for testing
def ai_price_estimate(request):
    """
    AI Price Estimation endpoint (Legacy - for simple text-based estimation)
    """
    try:
        product_name = request.data.get('product_name', '')
        condition = request.data.get('condition', 'GOOD')
        category = request.data.get('category', None)
        brand = request.data.get('brand', None)
        
        if not product_name:
            return Response(
                {'error': 'product_name is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ai_service = AutoMarketAIService()
        result = ai_service.estimate_price(
            item_name=product_name,
            description=f"Category: {category or 'Unknown'}, Brand: {brand or 'Unknown'}",
            condition=condition,
            defects="",
            images=None,
            pickup_address=""
        )
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'AI service error: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([])
def item_price_estimate_with_images(request):
    """
    Step 1: Submit item(s) data, get price estimation, save temporarily
    
    Supports both single product and multiple products in one request
    
    POST /api/items/estimate/
    
    Single Product:
    {
        "title": "iPhone 14 Pro",
        "description": "Excellent condition iPhone 14 Pro",
        "condition": "EXCELLENT", 
        "defects": "Minor scratches on the back",
        "uploaded_images": ["data:image/jpeg;base64,/9j/4AAQ...", ...]
    }
    
    Multiple Products:
    {
        "products": [
            {
                "title": "iPhone 14 Pro",
                "description": "Excellent condition iPhone 14 Pro",
                "condition": "EXCELLENT", 
                "defects": "Minor scratches on the back",
                "uploaded_images": ["data:image/jpeg;base64,/9j/4AAQ...", ...]
            },
            {
                "title": "MacBook Pro",
                "description": "MacBook Pro with M2 chip",
                "condition": "GOOD", 
                "defects": "Minor scuffs on bottom",
                "uploaded_images": ["data:image/jpeg;base64,/9j/4AAQ...", ...]
            }
        ]
    }
    
    Returns: item_id(s) and price estimation(s) for Step 2
    """
    try:
        # Check if request contains multiple products or single product
        if 'products' in request.data or 'items' in request.data:
            # Handle multiple products
            products_data = request.data.get('products') or request.data.get('items', [])
            if not isinstance(products_data, list) or not products_data:
                return Response({
                    'status': 'error',
                    'message': 'Products must be a non-empty array'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            temp_product_ids = []
            products_summary = []
            total_estimated_value = 0
            
            for i, product_data in enumerate(products_data):
                # Validate each product
                serializer = TempProductSerializer(data=product_data, context={'request': request})
                if not serializer.is_valid():
                    return Response({
                        'status': 'error',
                        'message': f'Validation failed for product {i+1}: {product_data.get("title", "Unknown")}',
                        'errors': serializer.errors,
                        'product_index': i
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Save temporary product
                temp_product = serializer.save()
                
                # Get AI price estimation
                ai_service = AutoMarketAIService()
                
                # Prepare product data for AI analysis
                product_analysis_data = {
                    'title': temp_product.title,
                    'description': temp_product.description,
                    'condition': temp_product.condition,
                    'defects': temp_product.defects
                }
                
                # Get image paths for AI analysis
                image_paths = [img.image.path for img in temp_product.images.all()]
                
                # Get pricing analysis using new AI service
                final_estimate = ai_service.estimate_price(
                    item_name=temp_product.title,
                    description=temp_product.description,
                    condition=temp_product.condition,
                    defects=temp_product.defects,
                    images=image_paths,
                    pickup_address=""
                )
                
                # Update temporary product with AI estimates
                temp_product.estimated_value = final_estimate.get('estimated_price', 0)
                temp_product.min_price_range = final_estimate.get('price_range_min', 0)
                temp_product.max_price_range = final_estimate.get('price_range_max', 0)
                temp_product.confidence = final_estimate.get('confidence', 'MEDIUM')
                temp_product.save()
                
                temp_product_ids.append(temp_product.id)
                total_estimated_value += float(temp_product.estimated_value)
                
                products_summary.append({
                    'temp_product_id': temp_product.id,
                    'title': temp_product.title,
                    'condition': temp_product.condition,
                    'estimated_value': float(temp_product.estimated_value),
                    'price_range': f"${temp_product.min_price_range} - ${temp_product.max_price_range}",
                    'confidence_level': temp_product.confidence,
                    'image_count': temp_product.images.count()
                })
            
            return Response({
                'status': 'success',
                'message': f'{len(products_data)} items saved temporarily with price estimation',
                'temp_product_ids': temp_product_ids,
                'products_summary': {
                    'total_products': len(products_data),
                    'total_estimated_value': round(total_estimated_value, 2),
                    'average_condition': 'GOOD',  # Calculate based on actual conditions
                    'highest_value_item': max(products_summary, key=lambda x: x['estimated_value'])['title'] if products_summary else None,
                    'processing_completed': True
                },
                'individual_products': products_summary,
                'temp_storage': {
                    'expires_at': temp_product.expires_at.isoformat() if temp_product else None,
                    'expires_in_hours': 24,
                    'storage_status': 'temporary'
                },
                'next_step': {
                    'endpoint': '/api/submissions/contact-only/',
                    'method': 'POST',
                    'instruction': 'Use all temp_product_ids in Step 2 with contact information',
                    'expires_in_hours': 24
                }
            }, status=status.HTTP_201_CREATED)
        
        else:
            # Handle single product (existing logic)
            serializer = TempProductSerializer(data=request.data, context={'request': request})
            
            if not serializer.is_valid():
                return Response({
                    'status': 'error',
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            # Save temporary product
            temp_product = serializer.save()
            
            # Get AI price estimation
            ai_service = AutoMarketAIService()
            
            # Prepare product data for AI analysis
            product_data = {
                'title': temp_product.title,
                'description': temp_product.description,
                'condition': temp_product.condition,
                'defects': temp_product.defects
            }
            
            # Get image paths for AI analysis
            image_paths = [img.image.path for img in temp_product.images.all()]
            
            # Get pricing analysis using the existing estimate_price method
            final_estimate = ai_service.estimate_price(
                item_name=temp_product.title,
                description=temp_product.description,
                condition=temp_product.condition,
                defects=temp_product.defects,
                images=image_paths,
                pickup_address=""
            )
            
            # Update temporary product with AI estimates
            temp_product.estimated_value = final_estimate.get('estimated_price', 0)
            temp_product.min_price_range = final_estimate.get('price_range_min', 0)
            temp_product.max_price_range = final_estimate.get('price_range_max', 0)
            temp_product.confidence = final_estimate.get('confidence', 'MEDIUM')
            temp_product.save()
            
            # For backward compatibility, create image_analysis from the final estimate
            image_analysis = {
                'condition_assessment': temp_product.condition,
                'confidence_level': temp_product.confidence,
                'estimated_value': float(temp_product.estimated_value)
            }
            
            response_data = {
                'status': 'success',
                'message': 'Item saved temporarily with price estimation',
                'item_id': temp_product.id,
                'expires_at': temp_product.expires_at.isoformat(),
                'item_data': {
                    'title': temp_product.title,
                    'description': temp_product.description,
                    'condition': temp_product.condition,
                    'defects': temp_product.defects,
                    'image_count': temp_product.images.count()
                },
                'pricing_estimate': {
                    'estimated_value': float(temp_product.estimated_value),
                    'min_price_range': float(temp_product.min_price_range),
                    'max_price_range': float(temp_product.max_price_range),
                    'confidence': temp_product.confidence
                },
                'image_analysis': image_analysis,
                'next_step': {
                    'endpoint': '/api/submissions/contact-only/',
                    'method': 'POST',
                    'instruction': 'Use item_id in temp_product_ids array with contact information',
                    'expires_in_hours': 24
                },
                'user_display': {
                    'estimated_value': f"${temp_product.estimated_value:.2f}",
                    'price_range': f"${temp_product.min_price_range:.2f} - ${temp_product.max_price_range:.2f}",
                    'confidence_level': temp_product.confidence
                }
            }
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': f'Error processing item: {str(e)}',
            'error_type': 'processing_error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([])  # Allow public access for testing
def ai_detect_category(request):
    """
    AI Category Detection endpoint
    """
    try:
        product_name = request.data.get('product_name', '')
        description = request.data.get('description', '')
        
        if not product_name:
            return Response(
                {'error': 'product_name is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ai_service = AutoMarketAIService()
        result = ai_service.detect_category(
            product_name=product_name,
            description=description
        )
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'AI service error: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([])  # Allow public access for testing  
def ai_market_insights(request):
    """
    AI Market Insights endpoint
    """
    try:
        category = request.data.get('category', '')
        product_name = request.data.get('product_name', '')
        location = request.data.get('location', None)
        
        if not category or not product_name:
            return Response(
                {'error': 'category and product_name are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ai_service = AutoMarketAIService()
        result = ai_service.get_market_insights(
            category=category,
            product_name=product_name,
        )
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'AI service error: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([])
def contact_only_submission(request):
    """
    Step 2: Contact-only submission with temporary product IDs
    
    Takes contact information and list of temp_product_ids from Step 1,
    creates final submission batch with complete data, and sends confirmation emails.
    
    POST /api/submissions/contact-only/
    
    Expected payload:
    {
        "temp_product_ids": [1, 2, 3],  // IDs from Step 1
        "full_name": "John Doe",
        "email": "john@example.com",
        "phone": "555-0123",
        "pickup_date": "2025-01-15T14:00:00Z",
        "pickup_address": "123 Main St, City, State",
        "privacy_policy_accepted": true
    }
    
    Returns: Complete submission data with all products
    """
    try:
        # Validate and create final submission
        serializer = ContactOnlySerializer(data=request.data, context={'request': request})
        
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create final submission batch
        submission_batch = serializer.save()
        
        # Prepare email data
        contact_info = {
            'full_name': submission_batch.full_name,
            'email': submission_batch.email,
            'phone': submission_batch.phone,
            'pickup_date': submission_batch.pickup_date.isoformat(),
            'pickup_address': submission_batch.pickup_address,
            'privacy_policy_accepted': submission_batch.privacy_policy_accepted
        }
        
        # Get submitted items data for email
        submitted_items = []
        for product in submission_batch.products.all():
            submitted_items.append({
                'title': product.title,
                'description': product.description,
                'estimated_value': float(product.estimated_value),
                'condition': product.condition,
                'confidence': product.confidence,
                'defects': product.defects or 'None'
            })
        
        # Send confirmation emails (customer + admin) via Resend
        email_results = {'customer_email': None, 'admin_email': None}
        try:
            from .email_services import send_item_submission_emails
            
            email_results = send_item_submission_emails(
                user_email=submission_batch.email,
                user_name=submission_batch.full_name,
                submitted_items=submitted_items,
                contact_info=contact_info
            )
            
            logger.info(f"Emails sent for submission {submission_batch.id}: {email_results}")
            
        except Exception as email_error:
            logger.error(f"Email sending failed for submission {submission_batch.id}: {str(email_error)}")
            # Don't fail the submission if email fails
        
        # Return complete submission data
        batch_serializer = SubmissionBatchSerializer(submission_batch)
        
        response_data = {
            'status': 'success',
            'message': 'Submission completed successfully',
            'submission_id': submission_batch.id,
            'submission_data': batch_serializer.data,
            'summary': {
                'batch_id': submission_batch.id,
                'contact_name': submission_batch.full_name,
                'email': submission_batch.email,
                'total_items': submission_batch.total_items,
                'total_estimated_value': float(submission_batch.total_estimated_value),
                'pickup_date': submission_batch.pickup_date.isoformat(),
                'batch_status': submission_batch.batch_status,
                'created_at': submission_batch.created_at.isoformat()
            },
            'email_status': {
                'customer_email_sent': email_results.get('customer_email', {}).get('success', False),
                'admin_email_sent': email_results.get('admin_email', {}).get('success', False),
                'customer_email_error': email_results.get('customer_email', {}).get('error'),
                'admin_email_error': email_results.get('admin_email', {}).get('error')
            },
            'next_steps': {
                'admin_review': 'Your submission is pending admin review',
                'notification': 'You will receive email updates on the status',
                'tracking': f'Reference ID: {submission_batch.id}',
                'email_confirmation': 'Check your email for submission confirmation'
            }
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': f'Error creating submission: {str(e)}',
            'error_type': 'submission_error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Simple test views
@api_view(['GET'])
@permission_classes([])
def api_test(request):
    """Simple test endpoint"""
    return JsonResponse({
        'status': 'success',
        'message': 'Django API is working correctly',
        'timestamp': timezone.now().isoformat(),
        'server': 'Django 5.2.5'
    })


@api_view(['POST'])
@permission_classes([])
def cancel_temp_items(request):
    """
    Cancel/delete all temporary products for a specific user or all expired ones
    
    POST /api/temp-products/cancel/
    
    Optional payload:
    {
        "user_id": 123,  // Cancel all temp products for this user
        "temp_product_ids": [1, 2, 3]  // Cancel specific temp products
    }
    
    If no payload provided, deletes all expired temp products
    """
    try:
        user_id = request.data.get('user_id')
        temp_product_ids = request.data.get('temp_product_ids', [])
        
        deleted_products = 0
        deleted_images = 0
        
        if temp_product_ids:
            # Delete specific temp products
            temp_products = TempProduct.objects.filter(id__in=temp_product_ids)
            action = f"specific temp products (IDs: {temp_product_ids})"
            
        elif user_id:
            # Delete all temp products for a specific user
            temp_products = TempProduct.objects.filter(user_id=user_id)
            action = f"all temp products for user {user_id}"
            
        else:
            # Delete all expired temp products
            temp_products = TempProduct.objects.filter(expires_at__lt=timezone.now())
            action = "all expired temp products"
        
        if not temp_products.exists():
            return Response({
                'status': 'success',
                'message': f'No temp products found to cancel ({action})',
                'deleted_products': 0,
                'deleted_images': 0
            }, status=status.HTTP_200_OK)
        
        # Delete images and products
        for temp_product in temp_products:
            # Delete associated image files
            for img in temp_product.images.all():
                if img.image and os.path.isfile(img.image.path):
                    try:
                        os.remove(img.image.path)
                        deleted_images += 1
                    except Exception as e:
                        logger.error(f"Error deleting image {img.image.path}: {str(e)}")
            
            deleted_products += 1
        
        # Delete all temp products (CASCADE will delete TempProductImage records)
        temp_products.delete()
        
        logger.info(f"Manual temp product cleanup: {deleted_products} products, {deleted_images} images deleted")
        
        return Response({
            'status': 'success',
            'message': f'Successfully cancelled {action}',
            'deleted_products': deleted_products,
            'deleted_images': deleted_images,
            'action': action
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = f'Error cancelling temp products: {str(e)}'
        logger.error(error_msg)
        return Response({
            'status': 'error',
            'message': error_msg,
            'error_type': 'cancellation_error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def ebay_test_page(request):
    """Test page for eBay integration"""
    return render(request, 'ebay_test.html')
