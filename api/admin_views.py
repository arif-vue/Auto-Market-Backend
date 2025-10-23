# Admin Views for Auto Market
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.template.loader import render_to_string
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import random
import logging

logger = logging.getLogger(__name__)

from .models import Product, SubmissionBatch, EBayUserToken
from authentications.models import OTP
from .admin_serializers import (
    AdminLoginSerializer, AdminPasswordResetSerializer, AdminPasswordResetConfirmSerializer,
    AdminDashboardStatsSerializer, AdminProductListItemSerializer, AdminProductDetailSerializer,
    AdminProductActionSerializer, AdminSubmissionBatchListSerializer,
    AdminSubmissionBatchDetailSerializer, AdminActivityTableSerializer
)

User = get_user_model()

def generate_otp():
    """Generate 6-digit OTP"""
    return str(random.randint(100000, 999999))

def send_otp_email(email, otp):
    """Send OTP via email with console fallback"""
    from django.conf import settings
    try:
        subject = 'Admin Password Reset OTP - AutoMarket'
        message = f'Your password reset OTP is: {otp}\n\nThis OTP will expire in 10 minutes.'
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@automarket.com')
        recipient_list = [email]
        
        send_mail(subject, message, from_email, recipient_list)
        print(f"📧 OTP sent to {email}: {otp}")
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        print(f"🔑 ADMIN OTP for {email}: {otp}")

def error_response(code, message="Error", details=None):
    return Response({
        "success": False,
        "message": message,
        "data": details or {}
    }, status=code)

def success_response(message="Success", data=None, code=200):
    return Response({
        "success": True,
        "message": message,
        "data": data or {}
    }, status=code)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login(request):
    """
    Admin login endpoint
    """
    serializer = AdminLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'status': 'success',
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email,
                'role': user.role,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser
            },
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_password_reset(request):
    """
    Admin password reset request - sends OTP to email
    """
    email = request.data.get('email')
    if not email:
        return error_response(
            code=400,
            details={"email": ["This field is required"]}
        )
    
    try:
        user = User.objects.get(email=email)
        if not user.is_staff and not user.is_superuser:
            return error_response(
                code=403,
                details={"email": ["This user does not have admin privileges"]}
            )
    except User.DoesNotExist:
        return error_response(
            code=404,
            details={"email": ["No admin user exists with this email"]}
        )

    # Generate and save OTP
    otp = generate_otp()
    OTP.objects.filter(email=email).delete()  # Remove any existing OTP
    OTP.objects.create(email=email, otp=otp)
    
    try:
        send_otp_email(email=email, otp=otp)
    except Exception as e:
        return error_response(
            code=500,
            message="Failed to send OTP email",
            details={"error": [str(e)]}
        )
    
    return success_response(
        message="OTP sent to your email",
        code=201
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_password_reset_confirm(request):
    """
    Confirm admin password reset with OTP
    """
    email = request.data.get('email')
    otp_value = request.data.get('otp')
    new_password = request.data.get('new_password')

    if not all([email, otp_value, new_password]):
        details = {}
        if not email:
            details["email"] = ["This field is required"]
        if not otp_value:
            details["otp"] = ["This field is required"]
        if not new_password:
            details["new_password"] = ["This field is required"]
        return error_response(code=400, details=details)

    try:
        otp_obj = OTP.objects.get(email=email)
        if otp_obj.otp != otp_value:
            return error_response(
                code=400,
                details={"otp": ["The provided OTP is invalid"]}
            )
        
        user = User.objects.get(email=email)
        if not user.is_staff and not user.is_superuser:
            return error_response(
                code=403,
                details={"email": ["This user does not have admin privileges"]}
            )
            
        try:
            validate_password(new_password, user)
        except ValidationError as e:
            return error_response(
                code=400,
                details={"new_password": e.messages}
            )

        user.set_password(new_password)
        user.save()
        otp_obj.delete()  # Remove used OTP
        
        return success_response(message='Admin password reset successful')
        
    except OTP.DoesNotExist:
        return error_response(
            code=404,
            details={"email": ["No OTP found for this email"]}
        )
    except User.DoesNotExist:
        return error_response(
            code=404,
            details={"email": ["No admin user exists with this email"]}
        )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_dashboard_stats(request):
    """
    Enhanced admin dashboard with comprehensive statistics
    """
    products = Product.objects.all()
    
    # Calculate statistics
    total_products = products.count()
    pending_products = products.filter(listing_status='PENDING').count()
    approved_products = products.filter(listing_status='APPROVED').count()
    listed_products = products.filter(listing_status='LISTED').count()
    not_listed_products = products.filter(
        listing_status__in=['PENDING', 'APPROVED']
    ).count()
    sold_products = products.filter(
        listing_status__in=['EBAY_SOLD', 'AMAZON_SOLD']
    ).count()
    
    # Calculate total revenue
    total_revenue = products.filter(
        sold_price__isnull=False
    ).aggregate(total=Sum('sold_price'))['total'] or 0
    
    stats_data = {
        'total_products': total_products,
        'pending_products': pending_products,
        'approved_products': approved_products,
        'listed_products': listed_products,
        'not_listed_products': not_listed_products,
        'sold_products': sold_products,
        'total_revenue': total_revenue
    }
    
    return Response(stats_data, status=status.HTTP_200_OK)


class AdminProductListView(generics.ListAPIView):
    """
    Enhanced admin product list with filtering and search
    """
    serializer_class = AdminProductListItemSerializer
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        queryset = Product.objects.select_related('submission_batch').prefetch_related('images')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(listing_status=status_filter)
        
        # Search by title or customer name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(submission_batch__full_name__icontains=search) |
                Q(submission_batch__email__icontains=search)
            )
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        return queryset.order_by('-created_at')


class AdminProductDetailView(generics.RetrieveAPIView):
    """
    Detailed admin view of a product with all information
    """
    serializer_class = AdminProductDetailSerializer
    permission_classes = [IsAdminUser]
    queryset = Product.objects.select_related('submission_batch').prefetch_related('images')


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_product_update_status(request, product_id):
    """
    Single endpoint to handle all admin product status updates
    """
    try:
        product = get_object_or_404(Product, id=product_id)
        serializer = AdminProductActionSerializer(data=request.data)
        
        if serializer.is_valid():
            action = serializer.validated_data['action']
            sold_price = serializer.validated_data.get('sold_price')
            listing_price = serializer.validated_data.get('final_price')
            
            # Validate status transitions - more flexible for admin requirements
            current_status = product.listing_status
            valid_transitions = {
                'PENDING': ['approve', 'reject', 'list'],  # Allow direct listing from PENDING
                'APPROVED': ['list', 'reject'],
                'LISTED': ['unlist', 'ebay_sold', 'amazon_sold', 'list'],  # Allow re-listing LISTED products
                'REJECTED': ['approve', 'list'],  # Allow direct listing from REJECTED
                'REMOVED': ['approve', 'list'],  # Allow re-listing removed products
                'EBAY_SOLD': [],  # No actions allowed for sold products
                'AMAZON_SOLD': []  # No actions allowed for sold products
            }
            
            if action not in valid_transitions.get(current_status, []):
                return Response({
                    'success': False,
                    'error': f"Invalid action '{action}' for product with status '{current_status}'"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with transaction.atomic():
                if action == 'approve':
                    product.listing_status = 'APPROVED'
                    message = f'Product "{product.title}" approved successfully'
                    
                elif action == 'reject':
                    product.listing_status = 'REJECTED'
                    message = f'Product "{product.title}" rejected successfully'
                    
                elif action == 'list':
                    # Set listing price and list on both platforms
                    if listing_price:
                        product.final_listing_price = listing_price
                    elif not product.final_listing_price:
                        product.final_listing_price = product.estimated_value
                    
                    # Use MarketplaceService to list on both platforms
                    from .marketplace_service import MarketplaceService
                    marketplace = MarketplaceService()
                    result = marketplace.list_product_on_platform(product, 'BOTH')
                    
                    if result['success']:
                        product.listing_status = 'LISTED'
                        message = f'Product "{product.title}" listed on both eBay and Amazon at ${product.final_listing_price}'
                    else:
                        message = f'Partial listing: {result["message"]}'
                        product.listing_status = 'LISTED'  # Still mark as listed for what worked
                        
                elif action == 'unlist':
                    # Remove from both platforms
                    from .marketplace_service import MarketplaceService
                    marketplace = MarketplaceService()
                    marketplace.unlist_product_from_platform(product, 'BOTH')
                    
                    product.listing_status = 'REMOVED'
                    product.ebay_listing_id = None
                    product.amazon_listing_id = None
                    product.ebay_listing_url = None
                    product.amazon_listing_url = None
                    message = f'Product "{product.title}" unlisted from both platforms successfully'
                    
                elif action == 'ebay_sold':
                    product.listing_status = 'EBAY_SOLD'
                    product.sold_platform = 'EBAY'
                    # Auto-unlist from Amazon
                    if product.amazon_listing_id:
                        from .marketplace_service import MarketplaceService
                        marketplace = MarketplaceService()
                        marketplace.unlist_product_from_platform(product, 'AMAZON')
                        product.amazon_listing_id = None
                        product.amazon_listing_url = None
                    message = f'Product "{product.title}" sold on eBay at ${sold_price} - automatically unlisted from Amazon'
                    
                elif action == 'amazon_sold':
                    product.listing_status = 'AMAZON_SOLD'
                    product.sold_platform = 'AMAZON'
                    # Auto-unlist from eBay
                    if product.ebay_listing_id:
                        from .marketplace_service import MarketplaceService
                        marketplace = MarketplaceService()
                        marketplace.unlist_product_from_platform(product, 'EBAY')
                        product.ebay_listing_id = None
                        product.ebay_listing_url = None
                    message = f'Product "{product.title}" sold on Amazon at ${sold_price} - automatically unlisted from eBay'
                
                if action in ['ebay_sold', 'amazon_sold']:
                    if sold_price:
                        product.sold_price = sold_price
                    product.sold_at = timezone.now()
                
                product.save()
            
            return Response({
                'success': True,
                'message': message,
                'product': {
                    'id': product.id,
                    'title': product.title,
                    'new_status': product.listing_status,
                    'status_display': product.get_listing_status_display(),
                    'final_price': float(product.final_listing_price) if product.final_listing_price else None,
                    'sold_price': float(product.sold_price) if product.sold_price else None,
                    'ebay_listing_id': product.ebay_listing_id,
                    'amazon_listing_id': product.amazon_listing_id
                },
                'auto_actions_performed': _get_auto_actions(action) if action in ['ebay_sold', 'amazon_sold'] else []
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'error': 'Invalid action data',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': f'Failed to update product status: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def _get_auto_actions(action):
    """Helper to describe auto actions performed"""
    if action == 'ebay_sold':
        return ['Automatically unlisted from Amazon']
    elif action == 'amazon_sold':
        return ['Automatically unlisted from eBay']
    return []


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_product_update_price(request, product_id):
    """
    Update product final price
    POST /api/admin/products/{id}/update-price/
    """
    try:
        product = get_object_or_404(Product, id=product_id)
        
        # Import the serializer
        from .admin_serializers import AdminProductPriceUpdateSerializer
        
        serializer = AdminProductPriceUpdateSerializer(data=request.data, context={'product': product})
        
        if serializer.is_valid():
            final_price = serializer.validated_data['final_price']
            
            # Update the product
            old_price = product.final_listing_price
            product.final_listing_price = final_price
            product.save()
            
            # Log the price update
            logger.info(f"Admin updated price for product {product.id} from ${old_price} to ${final_price}")
            
            # If product is listed, automatically update the eBay listing with new price
            update_message = f'Product "{product.title}" price updated to ${final_price}'
            if product.listing_status == 'LISTED' and product.ebay_listing_id:
                try:
                    from .marketplace_service import MarketplaceService
                    marketplace = MarketplaceService()
                    
                    # Use the new price update method to update existing eBay listing
                    result = marketplace.update_listing_price(product, final_price, 'EBAY')
                    
                    if result.get('ebay', {}).get('success'):
                        update_message += ' and eBay listing price updated'
                    else:
                        update_message += ' (eBay price update failed - may need manual re-listing)'
                        logger.warning(f"Failed to update eBay listing price for product {product.id}: {result}")
                        
                except Exception as e:
                    logger.error(f"Error updating eBay listing price for product {product.id}: {e}")
                    update_message += ' (eBay price update failed - may need manual re-listing)'
            
            return Response({
                'success': True,
                'message': update_message,
                'product': {
                    'id': product.id,
                    'title': product.title,
                    'estimated_value': float(product.estimated_value),
                    'final_price': float(product.final_listing_price),
                    'updated_at': product.updated_at.isoformat(),
                    'listing_status': product.listing_status,
                    'ebay_listing_url': product.ebay_listing_url
                }
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'error': 'Invalid data',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': f'Failed to update product price: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_recent_activities(request):
    """
    Admin Activities Table View - 6 sections: ITEM, CUSTOMER, STATUS, PRICE, DATE, ACTIONS
    """
    # Get query parameters
    status_filter = request.query_params.get('status')
    search = request.query_params.get('search')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    page_size = int(request.query_params.get('page_size', 20))
    page = int(request.query_params.get('page', 1))
    
    # Base queryset with related data
    queryset = Product.objects.select_related('submission_batch').prefetch_related('images')
    
    # Apply filters
    if status_filter:
        queryset = queryset.filter(listing_status=status_filter)
    
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) |
            Q(submission_batch__full_name__icontains=search) |
            Q(submission_batch__email__icontains=search)
        )
    
    if date_from:
        queryset = queryset.filter(created_at__gte=date_from)
    
    if date_to:
        queryset = queryset.filter(created_at__lte=date_to)
    
    # Order by most recent first
    queryset = queryset.order_by('-created_at')
    
    # Calculate pagination
    total_count = queryset.count()
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    page_products = queryset[start_index:end_index]
    
    # Serialize data
    serializer = AdminActivityTableSerializer(
        page_products, 
        many=True, 
        context={'request': request}
    )
    
    # Status summary for dashboard
    status_summary = {}
    for choice_value, choice_label in Product.LISTING_STATUS_CHOICES:
        count = Product.objects.filter(listing_status=choice_value).count()
        status_summary[choice_value] = {
            'count': count,
            'label': choice_label
        }
    
    return success_response(
        message="Admin activities retrieved successfully",
        data={
            'products': serializer.data,
            'pagination': {
                'total_count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size,
                'has_next': end_index < total_count,
                'has_previous': page > 1
            },
            'status_summary': status_summary,
            'filters_applied': {
                'status': status_filter,
                'search': search,
                'date_from': date_from,
                'date_to': date_to
            }
        }
    )


# ============================
# SUBMISSION MANAGEMENT VIEWS
# ============================

class AdminSubmissionListView(generics.ListAPIView):
    """
    Admin view to list all submission batches
    """
    permission_classes = [IsAdminUser]
    queryset = SubmissionBatch.objects.all().order_by('-created_at')
    serializer_class = AdminSubmissionBatchListSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(batch_status=status_filter)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        # Search by customer name or email
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) | 
                Q(email__icontains=search)
            )
        
        return queryset


class AdminSubmissionDetailView(generics.RetrieveUpdateAPIView):
    """
    Admin view to get and update submission batch details
    """
    permission_classes = [IsAdminUser]
    queryset = SubmissionBatch.objects.all()
    serializer_class = AdminSubmissionBatchDetailSerializer
    
    def patch(self, request, *args, **kwargs):
        """
        Update submission batch status and admin notes
        """
        submission = self.get_object()
        
        # Update admin notes
        if 'admin_notes' in request.data:
            submission.admin_notes = request.data['admin_notes']
        
        # Update approval status
        if 'batch_status' in request.data:
            submission.batch_status = request.data['batch_status']
            if request.data['batch_status'] in ['APPROVED', 'REJECTED']:
                submission.approved_by = request.user
                submission.approved_at = timezone.now()
        
        submission.save()
        
        serializer = self.get_serializer(submission)
        return Response(serializer.data)


# ============================
# MARKETPLACE INTEGRATION VIEWS
# ============================

@api_view(['POST'])
@permission_classes([IsAdminUser])
def list_product_on_marketplace(request, product_id):
    """
    List a specific product on eBay/Amazon marketplaces
    """
    from .marketplace_service import MarketplaceService
    
    try:
        product = get_object_or_404(Product, id=product_id)
        platform = request.data.get('platform', 'BOTH')  # EBAY, AMAZON, or BOTH
        
        if product.listing_status != 'APPROVED':
            return Response({
                'error': 'Product must be approved before listing'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        marketplace = MarketplaceService()
        result = marketplace.list_product_on_platform(product, platform)
        
        if result['success']:
            return Response({
                'status': 'success',
                'message': result['message'],
                'results': result['results'],
                'product_id': product.id,
                'listing_status': product.listing_status
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': 'error',
                'message': result['message'],
                'error': result.get('error')
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'status': 'error',
            'message': f'Failed to list product: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_marketplace_categories(request):
    """
    Get suggested categories from eBay and Amazon for a product
    """
    from .marketplace_service import MarketplaceService
    
    try:
        product_title = request.query_params.get('title', '')
        platform = request.query_params.get('platform', 'BOTH')
        
        if not product_title:
            return Response({
                'error': 'Product title is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        marketplace = MarketplaceService()
        categories = marketplace.get_suggested_categories(product_title, platform)
        
        return Response({
            'status': 'success',
            'categories': categories,
            'product_title': product_title
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': f'Failed to get categories: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def mark_product_sold(request, product_id):
    """
    Mark a product as sold on a specific platform
    """
    try:
        product = get_object_or_404(Product, id=product_id)
        platform = request.data.get('platform')  # EBAY or AMAZON
        sale_price = request.data.get('sale_price')
        
        if not platform or not sale_price:
            return Response({
                'error': 'Platform and sale price are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if platform not in ['EBAY', 'AMAZON']:
            return Response({
                'error': 'Platform must be either EBAY or AMAZON'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update product status
        if platform == 'EBAY':
            product.listing_status = 'EBAY_SOLD'
        else:
            product.listing_status = 'AMAZON_SOLD'
            
        product.sold_platform = platform
        product.sold_price = sale_price
        product.sold_at = timezone.now()
        product.save()
        
        # Update marketplace inventory (set to 0)
        from .marketplace_service import MarketplaceService
        marketplace = MarketplaceService()
        marketplace.update_inventory(product, quantity=0)
        
        return Response({
            'status': 'success',
            'message': f'Product marked as sold on {platform}',
            'product_id': product.id,
            'sale_price': sale_price,
            'sold_at': product.sold_at
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': f'Failed to mark product as sold: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def marketplace_dashboard_stats(request):
    """
    Get marketplace-specific dashboard statistics
    """
    try:
        # eBay statistics
        ebay_listed = Product.objects.filter(
            ebay_listing_id__isnull=False,
            listing_status='LISTED'
        ).count()
        
        ebay_sold = Product.objects.filter(
            listing_status='EBAY_SOLD'
        ).count()
        
        ebay_revenue = Product.objects.filter(
            listing_status='EBAY_SOLD'
        ).aggregate(
            total=Sum('sold_price')
        )['total'] or 0
        
        # Amazon statistics
        amazon_listed = Product.objects.filter(
            amazon_listing_id__isnull=False,
            listing_status='LISTED'
        ).count()
        
        amazon_sold = Product.objects.filter(
            listing_status='AMAZON_SOLD'
        ).count()
        
        amazon_revenue = Product.objects.filter(
            listing_status='AMAZON_SOLD'
        ).aggregate(
            total=Sum('sold_price')
        )['total'] or 0
        
        # General statistics
        total_listed = Product.objects.filter(
            listing_status='LISTED'
        ).count()
        
        total_sold = Product.objects.filter(
            listing_status__in=['EBAY_SOLD', 'AMAZON_SOLD']
        ).count()
        
        total_revenue = ebay_revenue + amazon_revenue
        
        return Response({
            'ebay': {
                'listed_products': ebay_listed,
                'sold_products': ebay_sold,
                'revenue': float(ebay_revenue)
            },
            'amazon': {
                'listed_products': amazon_listed,
                'sold_products': amazon_sold,
                'revenue': float(amazon_revenue)
            },
            'total': {
                'listed_products': total_listed,
                'sold_products': total_sold,
                'revenue': float(total_revenue)
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': f'Failed to get marketplace stats: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_ebay_status(request):
    """Get eBay integration status for admin"""
    try:
        # Check if admin has eBay token
        try:
            user_token = EBayUserToken.objects.get(user_id=request.user.id)
            is_authorized = not user_token.is_expired()
            expires_at = user_token.expires_at.isoformat() if user_token.expires_at else None
            token_info = {
                'expires_at': expires_at,
                'scope': user_token.scope,
                'created_at': user_token.created_at.isoformat()
            }
        except EBayUserToken.DoesNotExist:
            is_authorized = False
            expires_at = None
            token_info = {}
        
        # Count eBay-related products
        ebay_stats = {
            'listed_products': Product.objects.filter(
                ebay_listing_url__isnull=False,
                listing_status='LISTED'
            ).count(),
            'sold_on_ebay': Product.objects.filter(
                listing_status='EBAY_SOLD'
            ).count(),
            'pending_ebay_listing': Product.objects.filter(
                listing_status='APPROVED',
                ebay_listing_url__isnull=True
            ).count(),
            'total_ebay_revenue': Product.objects.filter(
                listing_status='EBAY_SOLD'
            ).aggregate(total=Sum('sold_price'))['total'] or 0
        }
        
        return Response({
            'success': True,
            'ebay_authorized': is_authorized,
            'environment': settings.EBAY_ENVIRONMENT,
            'redirect_uri': settings.EBAY_REDIRECT_URI,
            'auth_url': f"/api/ebay/auth/start/" if not is_authorized else None,
            'token_info': token_info,
            'statistics': ebay_stats
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': f'Failed to get eBay status: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_ebay_listings(request):
    """Get all products with eBay listing status"""
    try:
        # Get query parameters
        status_filter = request.query_params.get('status', 'all')
        page_size = int(request.query_params.get('page_size', 20))
        page = int(request.query_params.get('page', 1))
        
        # Base queryset
        queryset = Product.objects.all()
        
        # Apply status filter
        if status_filter == 'listed':
            queryset = queryset.filter(
                ebay_listing_url__isnull=False,
                listing_status='LISTED'
            )
        elif status_filter == 'sold':
            queryset = queryset.filter(listing_status='EBAY_SOLD')
        elif status_filter == 'pending':
            queryset = queryset.filter(
                listing_status='APPROVED',
                ebay_listing_url__isnull=True
            )
        
        # Order by most recent
        queryset = queryset.order_by('-created_at')
        
        # Pagination
        start = (page - 1) * page_size
        end = start + page_size
        products = queryset[start:end]
        total_count = queryset.count()
        
        # Serialize products with eBay-specific info
        products_data = []
        for product in products:
            first_image = product.images.first()
            
            products_data.append({
                'id': product.id,
                'title': product.title or f"{product.brand} {product.model}".strip(),
                'brand': product.brand,
                'model': product.model,
                'estimated_price': float(product.estimated_value) if product.estimated_value else None,
                'final_price': float(product.final_listing_price) if product.final_listing_price else None,
                'sold_price': float(product.sold_price) if product.sold_price else None,
                'listing_status': product.listing_status,
                'status_display': product.get_listing_status_display(),
                'ebay_listing_url': product.ebay_listing_url,
                'amazon_listing_url': product.amazon_listing_id,
                'sold_platform': product.sold_platform,
                'sold_at': product.sold_at.isoformat() if product.sold_at else None,
                'created_at': product.created_at.isoformat(),
                'image': {
                    'url': first_image.image.url if first_image else None,
                    'alt': first_image.alt_text if first_image else ''
                } if first_image else None,
                'submission_batch': {
                    'id': product.submission_batch.id,
                    'customer_name': product.submission_batch.full_name,
                    'customer_email': product.submission_batch.email,
                } if product.submission_batch else None,
                'actions': {
                    'can_list_ebay': product.listing_status == 'APPROVED' and not product.ebay_listing_url,
                    'can_end_listing': product.listing_status == 'LISTED' and product.ebay_listing_url,
                    'can_mark_sold': product.listing_status == 'LISTED',
                    'can_edit_price': product.listing_status in ['APPROVED', 'LISTED']
                }
            })
        
        return Response({
            'success': True,
            'products': products_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size,
                'has_next': end < total_count,
                'has_previous': page > 1
            },
            'filters': {
                'current_status': status_filter,
                'available_statuses': [
                    {'value': 'all', 'label': 'All Products'},
                    {'value': 'pending', 'label': 'Pending eBay Listing'},
                    {'value': 'listed', 'label': 'Listed on eBay'},
                    {'value': 'sold', 'label': 'Sold on eBay'}
                ]
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': f'Failed to get eBay listings: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_product_delete(request, product_id):
    """
    Delete a product completely from the system
    DELETE /api/admin/products/{id}/delete/
    """
    try:
        product = get_object_or_404(Product, id=product_id)
        
        # Get product info before deletion for response
        product_title = product.title
        product_status = product.listing_status
        
        # If product is listed on marketplaces, unlist it first
        if product_status == 'LISTED':
            try:
                from .marketplace_service import MarketplaceService
                marketplace = MarketplaceService()
                marketplace.unlist_product_from_platform(product, 'BOTH')
            except Exception as e:
                logger.warning(f"Failed to unlist product {product_id} before deletion: {str(e)}")
        
        # Delete the product (this will cascade delete related images)
        product.delete()
        
        logger.info(f"Admin {request.user.email} deleted product {product_id} ({product_title})")
        
        return Response({
            'success': True,
            'message': f'Product "{product_title}" deleted successfully',
            'deleted_product': {
                'id': product_id,
                'title': product_title,
                'previous_status': product_status
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Failed to delete product {product_id}: {str(e)}")
        return Response({
            'success': False,
            'error': f'Failed to delete product: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)