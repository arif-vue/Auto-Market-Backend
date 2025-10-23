# Admin Authentication and Management API
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Product, SubmissionBatch

User = get_user_model()


class AdminLoginSerializer(serializers.Serializer):
    """Serializer for admin login"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            try:
                user = User.objects.get(email=email)
                if not user.check_password(password):
                    raise serializers.ValidationError('Invalid credentials')
                if not user.is_staff:
                    raise serializers.ValidationError('User is not an admin')
                attrs['user'] = user
            except User.DoesNotExist:
                raise serializers.ValidationError('Invalid credentials')
        else:
            raise serializers.ValidationError('Email and password are required')

        return attrs


class AdminPasswordResetSerializer(serializers.Serializer):
    """Serializer for admin password reset"""
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
            if not user.is_staff:
                raise serializers.ValidationError('User is not an admin')
        except User.DoesNotExist:
            raise serializers.ValidationError('Admin with this email does not exist')
        return value


class AdminPasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for confirming password reset"""
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        password = attrs.get('new_password')
        confirm_password = attrs.get('confirm_password')

        if password != confirm_password:
            raise serializers.ValidationError("Passwords don't match")

        # Validate password strength
        validate_password(password)
        return attrs


class AdminDashboardStatsSerializer(serializers.Serializer):
    """Serializer for admin dashboard statistics"""
    total_products = serializers.IntegerField()
    pending_products = serializers.IntegerField()
    approved_products = serializers.IntegerField()
    listed_products = serializers.IntegerField()
    not_listed_products = serializers.IntegerField()
    sold_products = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=15, decimal_places=2)


class AdminProductListItemSerializer(serializers.ModelSerializer):
    """Serializer for product list items in admin dashboard"""
    customer_name = serializers.CharField(source='submission_batch.full_name', read_only=True)
    customer_email = serializers.CharField(source='submission_batch.email', read_only=True)
    customer_phone = serializers.CharField(source='submission_batch.phone', read_only=True)
    customer_address = serializers.CharField(source='submission_batch.pickup_address', read_only=True)
    submission_date = serializers.DateTimeField(source='submission_batch.created_at', read_only=True)
    primary_image = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_listing_status_display', read_only=True)
    condition_display = serializers.CharField(source='get_condition_display', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'title', 'condition', 'condition_display', 'defects', 'estimated_value',
            'final_listing_price', 'listing_status', 'status_display', 'sold_price',
            'sold_at', 'customer_name', 'customer_email', 'customer_phone', 
            'customer_address', 'submission_date', 'primary_image', 'ebay_listing_id',
            'amazon_listing_id', 'created_at'
        ]

    def get_primary_image(self, obj):
        primary_image = obj.images.filter(is_primary=True).first()
        if primary_image:
            request = self.context.get('request')
            return request.build_absolute_uri(primary_image.image.url) if request else primary_image.image.url
        return None


class AdminProductDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for admin product view"""
    customer_info = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_listing_status_display', read_only=True)
    condition_display = serializers.CharField(source='get_condition_display', read_only=True)
    submission_batch_info = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'title', 'description', 'condition', 'condition_display', 'defects',
            'estimated_value', 'min_price_range', 'max_price_range', 'confidence',
            'final_listing_price', 'listing_status', 'status_display', 'sold_platform',
            'sold_price', 'sold_at', 'ebay_listing_id', 'amazon_listing_id',
            'ebay_category', 'amazon_category', 'customer_info', 'images',
            'submission_batch_info', 'created_at', 'updated_at'
        ]

    def get_customer_info(self, obj):
        if obj.submission_batch:
            return {
                'name': obj.submission_batch.full_name,
                'email': obj.submission_batch.email,
                'phone': obj.submission_batch.phone,
                'address': obj.submission_batch.pickup_address,
                'pickup_date': obj.submission_batch.pickup_date,
                'privacy_policy_accepted': obj.submission_batch.privacy_policy_accepted
            }
        return None

    def get_images(self, obj):
        request = self.context.get('request')
        images = []
        for image in obj.images.all():
            image_url = request.build_absolute_uri(image.image.url) if request else image.image.url
            images.append({
                'id': image.id,
                'url': image_url,
                'is_primary': image.is_primary,
                'order': image.order
            })
        return images

    def get_submission_batch_info(self, obj):
        if obj.submission_batch:
            return {
                'id': obj.submission_batch.id,
                'status': obj.submission_batch.batch_status,
                'submitted_date': obj.submission_batch.created_at,
                'admin_notes': obj.submission_batch.admin_notes,
                'approved_by': obj.submission_batch.approved_by.username if obj.submission_batch.approved_by else None,
                'approved_at': obj.submission_batch.approved_at
            }
        return None


class AdminProductActionSerializer(serializers.Serializer):
    """Serializer for single admin product status update endpoint"""
    action = serializers.ChoiceField(choices=[
        'approve', 'reject', 'list', 'unlist', 'ebay_sold', 'amazon_sold'
    ])
    sold_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    def validate(self, attrs):
        action = attrs.get('action')
        
        if action in ['ebay_sold', 'amazon_sold']:
            if not attrs.get('sold_price'):
                raise serializers.ValidationError("Sold price is required when marking as sold")
        
        if action == 'list':
            # Allow listing without final_price if product already has a final_listing_price
            # or if we can fall back to estimated_value
            if not attrs.get('final_price'):
                # This validation will be handled in admin_views.py which can access the product
                # and set final_listing_price = estimated_value if needed
                pass
        
        return attrs


class AdminProductPriceUpdateSerializer(serializers.Serializer):
    """Serializer for updating product final price"""
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    
    def validate_final_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Final price must be greater than 0")
        return value
    
    def validate(self, attrs):
        """Validate price updates - allow for LISTED products but block for sold products"""
        # Get product from context (passed by view)
        product = self.context.get('product')
        if product and hasattr(product, 'listing_status'):
            current_status = product.listing_status
            
            # Only block price updates for sold products (final states)
            blocked_statuses = ['EBAY_SOLD', 'AMAZON_SOLD']
            
            if current_status in blocked_statuses:
                raise serializers.ValidationError({
                    "final_price": [
                        f"Cannot update price for {current_status} products. "
                        "Product has already been sold."
                    ],
                    "current_status": current_status
                })
            
            # LISTED products can have price updates (will auto-sync to eBay)
            if current_status == 'LISTED':
                attrs['_status_note'] = "Price will be updated on active eBay listing"
        
        return attrs


class AdminActivityTableSerializer(serializers.ModelSerializer):
    """Serializer for admin activities table view"""
    
    # ITEM section
    item = serializers.SerializerMethodField()
    
    # CUSTOMER section
    customer = serializers.SerializerMethodField()
    
    # STATUS section
    status = serializers.SerializerMethodField()
    
    # PRICE section
    price = serializers.SerializerMethodField()
    
    # DATE section
    date = serializers.SerializerMethodField()
    
    # ACTIONS section
    actions = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = ['id', 'item', 'customer', 'status', 'price', 'date', 'actions']
    
    def get_item(self, obj):
        """ITEM: title, condition, defects, description, ebay_listing_id, amazon_listing_id, all images"""
        return {
            'title': obj.title,
            'description': obj.description,
            'condition': obj.get_condition_display(),
            'defects': obj.defects or 'None',
            'ebay_listing_id': obj.ebay_listing_id,
            'amazon_listing_id': obj.amazon_listing_id,
            'images': self._get_all_images(obj)
        }
    
    def get_customer(self, obj):
        """CUSTOMER: name + email + phone + pickup_date + pickup_address"""
        if obj.submission_batch:
            return {
                'name': obj.submission_batch.full_name,
                'email': obj.submission_batch.email,
                'phone': obj.submission_batch.phone,
                'pickup_date': obj.submission_batch.pickup_date,
                'pickup_address': obj.submission_batch.pickup_address
            }
        return {
            'name': 'N/A',
            'email': 'N/A', 
            'phone': 'N/A',
            'pickup_date': None,
            'pickup_address': 'N/A'
        }
    
    def get_status(self, obj):
        """STATUS: listing status"""
        return {
            'current': obj.listing_status,
            'display': obj.get_listing_status_display(),
            'updated_at': obj.updated_at
        }
    
    def get_price(self, obj):
        """PRICE: estimated and final prices"""
        return {
            'estimated_value': float(obj.estimated_value),
            'final_price': float(obj.final_listing_price) if obj.final_listing_price else float(obj.estimated_value),
            'sold_price': float(obj.sold_price) if obj.sold_price else None,
            'min_range': float(obj.min_price_range),
            'max_range': float(obj.max_price_range)
        }
    
    def get_date(self, obj):
        """DATE: relevant dates"""
        return {
            'created_at': obj.created_at,
            'updated_at': obj.updated_at,
            'sold_at': obj.sold_at,
            'pickup_date': obj.submission_batch.pickup_date if obj.submission_batch else None
        }
    
    def get_actions(self, obj):
        """ACTIONS: available actions based on current status"""
        current_status = obj.listing_status
        available_actions = []
        
        if current_status == 'PENDING':
            available_actions = [
                {
                    'action': 'approve',
                    'label': 'Approve',
                    'button_class': 'btn-success'
                },
                {
                    'action': 'reject',
                    'label': 'Reject',
                    'button_class': 'btn-danger'
                }
            ]
        elif current_status == 'APPROVED':
            available_actions = [
                {
                    'action': 'list',
                    'label': 'List on Both Platforms',
                    'button_class': 'btn-primary'
                }
            ]
        elif current_status == 'LISTED':
            available_actions = [
                {
                    'action': 'unlist',
                    'label': 'Unlist from Both Platforms',
                    'button_class': 'btn-warning'
                },
                {
                    'action': 'ebay_sold',
                    'label': 'Mark Sold on eBay',
                    'button_class': 'btn-info'
                },
                {
                    'action': 'amazon_sold',
                    'label': 'Mark Sold on Amazon',
                    'button_class': 'btn-info'
                }
            ]
        elif current_status in ['REJECTED', 'REMOVED']:
            available_actions = [
                {
                    'action': 'approve',
                    'label': 'Re-approve',
                    'button_class': 'btn-success'
                }
            ]
        # EBAY_SOLD and AMAZON_SOLD have no actions (final states)
        
        return {
            'available_actions': available_actions,
            'endpoint': f'/api/admin/products/{obj.id}/update-status/'
        }
    
    def _get_all_images(self, obj):
        """Helper to get all product images with details"""
        images = []
        for image in obj.images.all().order_by('order'):
            image_data = {
                'id': image.id,
                'is_primary': image.is_primary,
                'order': image.order
            }
            
            if image.image:
                request = self.context.get('request')
                if request:
                    image_data['url'] = request.build_absolute_uri(image.image.url)
                else:
                    image_data['url'] = image.image.url
            else:
                image_data['url'] = None
                
            images.append(image_data)
        
        return images


# ============================
# SUBMISSION MANAGEMENT SERIALIZERS
# ============================

class AdminSubmissionBatchListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing submission batches in admin panel
    """
    customer_name = serializers.CharField(source='full_name', read_only=True)
    products_count = serializers.IntegerField(source='total_items', read_only=True)
    submitted_at = serializers.DateTimeField(source='created_at', read_only=True)
    
    class Meta:
        model = SubmissionBatch
        fields = [
            'id', 'customer_name', 'email', 'phone', 'batch_status',
            'products_count', 'submitted_at', 'pickup_date', 'pickup_address'
        ]


class AdminProductInSubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for products within a submission batch
    """
    class Meta:
        model = Product
        fields = [
            'id', 'title', 'description', 'condition', 'defects',
            'estimated_value', 'min_price_range', 'max_price_range',
            'confidence', 'listing_status', 'final_listing_price',
            'sold_platform', 'sold_price', 'sold_at',
            'ebay_listing_id', 'amazon_listing_id'
        ]


class AdminSubmissionBatchDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed submission batch view in admin panel
    """
    products = AdminProductInSubmissionSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='full_name', read_only=True)
    products_count = serializers.IntegerField(source='total_items', read_only=True)
    submitted_at = serializers.DateTimeField(source='created_at', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.full_name', read_only=True)
    
    class Meta:
        model = SubmissionBatch
        fields = [
            'id', 'customer_name', 'email', 'phone', 'batch_status',
            'products_count', 'submitted_at', 'pickup_date', 'pickup_address',
            'privacy_policy_accepted', 'admin_notes', 'approved_by_name',
            'approved_at', 'products'
        ]