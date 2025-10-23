from rest_framework import serializers
from .models import Product, ProductImage, SubmissionBatch, TempProduct, TempProductImage
from django.utils import timezone
from django.core.files.base import ContentFile
import base64
import uuid


class Base64ImageField(serializers.Field):
    """Custom field to handle base64 image data and regular file uploads"""
    
    def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith('data:image'):
            # Handle base64 image
            try:
                # Extract the base64 string and format
                header, base64_string = data.split(',', 1)
                format_part = header.split(';')[0].split('/')[1]  # e.g., 'jpeg', 'png'
                
                # Validate image format
                if format_part.lower() not in ['jpeg', 'jpg', 'png', 'webp']:
                    raise serializers.ValidationError("Unsupported image format. Use JPEG, PNG, or WEBP.")
                
                # Decode base64
                image_data = base64.b64decode(base64_string)
                
                # Validate file size (min 800 bytes, max 5MB) - reject tiny placeholder images
                if len(image_data) < 800:  # Minimum 800 bytes to reject placeholder images
                    raise serializers.ValidationError(
                        f"Image is too small ({len(image_data)} bytes). Minimum size is 800 bytes. "
                        "Please upload a proper product image, not a placeholder."
                    )
                if len(image_data) > 5 * 1024 * 1024:
                    raise serializers.ValidationError("Image is too large. Maximum size is 5MB.")
                
                # Create a file-like object
                file_extension = 'jpg' if format_part.lower() in ['jpeg', 'jpg'] else format_part.lower()
                file_name = f"image_{uuid.uuid4()}.{file_extension}"
                file_obj = ContentFile(image_data, name=file_name)
                
                return file_obj
            except Exception as e:
                raise serializers.ValidationError(f"Invalid base64 image data: {str(e)}")
        elif hasattr(data, 'read'):
            # Handle regular file upload
            if data.size < 800:  # Minimum 800 bytes to reject placeholder images
                raise serializers.ValidationError(
                    f"Image is too small ({data.size} bytes). Minimum size is 800 bytes. "
                    "Please upload a proper product image, not a placeholder."
                )
            if data.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Image is too large. Maximum size is 5MB.")
            return data
        else:
            raise serializers.ValidationError("Invalid image format. Use base64 string or file upload.")


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_primary', 'order']
        read_only_fields = ['id']


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=Base64ImageField(),
        write_only=True,
        required=True,
        min_length=3,    # Minimum 3 images required (as per model validation)
        max_length=8,    # Maximum 8 images allowed
        help_text="Upload 3-8 images for the product (base64 strings or file uploads)"
    )

    class Meta:
        model = Product
        fields = [
            'id', 'title', 'description', 'condition', 'defects',
            'estimated_value', 'min_price_range', 'max_price_range', 'confidence',
            'final_listing_price', 'listing_status', 'sold_platform', 'sold_price', 'sold_at',
            'ebay_listing_id', 'amazon_listing_id', 'ebay_category', 'amazon_category',
            'images', 'uploaded_images', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'listing_status', 'sold_platform', 'sold_price', 'sold_at',
            'ebay_listing_id', 'amazon_listing_id', 'estimated_value', 
            'min_price_range', 'max_price_range', 'confidence',
            'created_at', 'updated_at'
        ]

    def validate_uploaded_images(self, value):
        """Validate image uploads with clear error messages"""
        if not value:
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'uploaded_images' is required. "
                "Please provide 1-8 base64 encoded images for this product. "
                "Format: data:image/jpeg;base64,/9j/4AAQ..."
            )
        
        if len(value) < 3:
            raise serializers.ValidationError(
                "🚨 VALIDATION ERROR: At least 3 images are required per product. "
                "Please add base64 encoded images to uploaded_images array."
            )
        
        if len(value) > 8:
            raise serializers.ValidationError(
                "🚨 TOO MANY IMAGES: Maximum 8 images allowed per product. "
                f"You provided {len(value)} images."
            )
        
        return value
    
    def validate_title(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'title' is required. "
                "Please provide a descriptive title for the product."
            )
        if len(value.strip()) < 5:
            raise serializers.ValidationError(
                "🚨 VALIDATION ERROR: Title must be at least 5 characters long. "
                f"You provided: '{value}' ({len(value.strip())} characters)"
            )
        return value.strip()
    
    def validate_description(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'description' is required. "
                "Please provide a detailed description of the product."
            )
        if len(value.strip()) < 10:
            raise serializers.ValidationError(
                "🚨 VALIDATION ERROR: Description must be at least 10 characters long. "
                f"You provided {len(value.strip())} characters."
            )
        return value.strip()
    
    def validate_condition(self, value):
        valid_conditions = ['EXCELLENT', 'GOOD', 'FAIR', 'POOR']
        if not value:
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'condition' is required. "
                f"Please choose one of: {', '.join(valid_conditions)}"
            )
        if value not in valid_conditions:
            raise serializers.ValidationError(
                f"🚨 INVALID VALUE: 'condition' must be one of: {', '.join(valid_conditions)}. "
                f"You provided: '{value}'"
            )
        return value
    
    def validate_defects(self, value):
        if value is None:
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'defects' is required. "
                "Please describe any defects or write 'None' if no defects."
            )
        return value

    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        user = None
        if 'request' in self.context and self.context['request'].user.is_authenticated:
            user = self.context['request'].user
        submission_batch = self.context.get('submission_batch')
        
        # Create product with default AI values (will be updated by AI service)
        product = Product.objects.create(
            user=user,
            submission_batch=submission_batch,
            estimated_value=0.00,  # Will be updated by AI
            min_price_range=0.00,  # Will be updated by AI
            max_price_range=0.00,  # Will be updated by AI
            confidence='MEDIUM',   # Default confidence
            **validated_data
        )
        
        # Create product images
        for index, image in enumerate(uploaded_images):
            ProductImage.objects.create(
                product=product,
                image=image,
                order=index,
                is_primary=(index == 0)  # First image is primary
            )
        
        # TODO: Call AI service to estimate price and update product
        # This would be done asynchronously in production
        
        return product


class SubmissionBatchSerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True)
    total_items = serializers.ReadOnlyField()
    total_estimated_value = serializers.ReadOnlyField()

    class Meta:
        model = SubmissionBatch
        fields = [
            'id', 'batch_status', 'full_name', 'email', 'phone', 'pickup_date',
            'pickup_address', 'privacy_policy_accepted', 'admin_notes',
            'approved_by', 'approved_at', 'products', 'total_items', 
            'total_estimated_value', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'batch_status', 'admin_notes', 'approved_by', 'approved_at',
            'created_at', 'updated_at'
        ]

    def create(self, validated_data):
        products_data = validated_data.pop('products')
        # Remove user from validated_data since we'll handle it separately
        validated_data.pop('user', None)
        
        user = None
        if 'request' in self.context and self.context['request'].user.is_authenticated:
            user = self.context['request'].user
        
        # Create submission batch (can be anonymous)
        batch = SubmissionBatch.objects.create(user=user, **validated_data)
        
        # Create products for this batch
        for product_data in products_data:
            product_serializer = ProductSerializer(
                data=product_data, 
                context={'request': self.context['request'], 'submission_batch': batch}
            )
            if product_serializer.is_valid():
                product_serializer.save()
        
        return batch

    def validate_pickup_date(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError(
                "🚨 INVALID DATE: Pickup date must be in the future. "
                f"You provided: {value}. Current time: {timezone.now()}. "
                "Please use format: 2025-12-30T14:00:00Z"
            )
        return value

    def validate_products(self, value):
        if not value:
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'products' array is required. "
                "Please provide at least one product with title, description, condition, defects, and uploaded_images."
            )
        if len(value) > 50:
            raise serializers.ValidationError(
                f"🚨 TOO MANY PRODUCTS: Maximum 50 products per submission. "
                f"You provided {len(value)} products."
            )
        return value
    
    def validate_privacy_policy_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "🚨 REQUIRED FIELD: privacy_policy_accepted must be true. "
                "Customer must accept privacy policy to proceed."
            )
        return value
    
    def validate_full_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'full_name' is required. "
                "Please provide the customer's full name."
            )
        return value.strip()
    
    def validate_email(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'email' is required. "
                "Please provide a valid email address."
            )
        return value.strip()
    
    def validate_phone(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'phone' is required. "
                "Please provide a valid phone number."
            )
        return value.strip()
    
    def validate_pickup_address(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "🚨 MISSING FIELD: 'pickup_address' is required. "
                "Please provide the complete pickup address."
            )
        return value.strip()


class SubmissionBatchListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing submissions"""
    total_items = serializers.ReadOnlyField()
    total_estimated_value = serializers.ReadOnlyField()

    class Meta:
        model = SubmissionBatch
        fields = [
            'id', 'batch_status', 'full_name', 'email', 'pickup_date',
            'total_items', 'total_estimated_value', 'created_at', 'updated_at'
        ]

class ProductStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating product status"""
    platform = serializers.ChoiceField(choices=['EBAY', 'AMAZON'])
    action = serializers.ChoiceField(choices=['sold', 'listed', 'removed'])
    sale_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    listing_id = serializers.CharField(max_length=100, required=False)

    def validate(self, data):
        if data['action'] == 'sold' and not data.get('sale_price'):
            raise serializers.ValidationError("Sale price is required when marking as sold.")
        if data['action'] == 'listed' and not data.get('listing_id'):
            raise serializers.ValidationError("Listing ID is required when marking as listed.")
        return data


class ItemEstimationSerializer(serializers.Serializer):
    """
    Serializer for Step 1: Item estimation with images (before submission)
    
    This validates the item data before getting AI price estimation
    """
    title = serializers.CharField(
        max_length=200,
        help_text="Product title (e.g., 'iPhone 14 Pro 256GB Space Black')"
    )
    description = serializers.CharField(
        max_length=1000,
        help_text="Detailed product description including condition details"
    )
    condition = serializers.ChoiceField(
        choices=Product.ITEM_CONDITION_CHOICES,
        help_text="Product condition: EXCELLENT, GOOD, FAIR, or POOR"
    )
    defects = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Any known defects or issues (optional)"
    )
    uploaded_images = serializers.ListField(
        child=Base64ImageField(),
        min_length=3,
        max_length=8,
        help_text="3-8 base64 encoded images for accurate price estimation"
    )
    
    def validate_title(self, value):
        """Validate title is descriptive enough"""
        if len(value.strip()) < 5:
            raise serializers.ValidationError(
                "Title must be at least 5 characters long for accurate estimation"
            )
        return value.strip()
    
    def validate_description(self, value):
        """Validate description provides enough detail"""
        if len(value.strip()) < 10:
            raise serializers.ValidationError(
                "Description must be at least 10 characters long for accurate estimation"
            )
        return value.strip()
    
    def validate_uploaded_images(self, value):
        """Validate images for estimation"""
        if len(value) < 3:
            raise serializers.ValidationError(
                "Minimum 3 images required for accurate price estimation"
            )
        if len(value) > 8:
            raise serializers.ValidationError(
                "Maximum 8 images allowed for accurate price estimation"
            )
        return value


# Temporary serializers for two-step submission
class TempProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TempProductImage
        fields = ['id', 'image', 'is_primary', 'order']
        read_only_fields = ['id']


class TempProductSerializer(serializers.ModelSerializer):
    """Serializer for temporary product storage in Step 1"""
    images = TempProductImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=Base64ImageField(),
        write_only=True,
        required=True,
        min_length=3,
        max_length=8,
        help_text="Upload 3-8 images for price estimation"
    )
    
    class Meta:
        model = TempProduct
        fields = [
            'id', 'title', 'description', 'condition', 'defects',
            'estimated_value', 'min_price_range', 'max_price_range', 'confidence',
            'images', 'uploaded_images', 'created_at', 'expires_at'
        ]
        read_only_fields = [
            'id', 'estimated_value', 'min_price_range', 'max_price_range',
            'confidence', 'created_at', 'expires_at'
        ]
    
    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        user = None
        if 'request' in self.context and self.context['request'].user.is_authenticated:
            user = self.context['request'].user
        
        # Create temporary product with AI pricing (will be updated by AI service)
        temp_product = TempProduct.objects.create(
            user=user,
            estimated_value=0.00,  # Will be updated by AI
            min_price_range=0.00,  # Will be updated by AI
            max_price_range=0.00,  # Will be updated by AI
            confidence='MEDIUM',   # Default confidence
            **validated_data
        )
        
        # Create temporary product images
        for index, image in enumerate(uploaded_images):
            TempProductImage.objects.create(
                temp_product=temp_product,
                image=image,
                order=index,
                is_primary=(index == 0)  # First image is primary
            )
        
        return temp_product


class ContactOnlySerializer(serializers.Serializer):
    """
    Serializer for Step 2: Contact-only submission
    Takes contact info and temp_product_ids, creates final submission
    """
    temp_product_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=50,
        help_text="List of temporary product IDs from Step 1"
    )
    full_name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    pickup_date = serializers.DateTimeField()
    pickup_address = serializers.CharField(max_length=500)
    privacy_policy_accepted = serializers.BooleanField()
    
    def validate_temp_product_ids(self, value):
        """Validate temporary product IDs exist and are not expired"""
        temp_products = TempProduct.objects.filter(id__in=value)
        
        if temp_products.count() != len(value):
            missing_ids = set(value) - set(temp_products.values_list('id', flat=True))
            raise serializers.ValidationError(
                f"Temporary products not found: {list(missing_ids)}. "
                "Please complete Step 1 first for all items."
            )
        
        # Check for expired products
        expired_products = [tp for tp in temp_products if tp.is_expired()]
        if expired_products:
            expired_ids = [tp.id for tp in expired_products]
            raise serializers.ValidationError(
                f"Temporary products have expired: {expired_ids}. "
                "Please complete Step 1 again for these items."
            )
        
        return value
    
    def validate_pickup_date(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError(
                "Pickup date must be in the future."
            )
        return value
    
    def validate_privacy_policy_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "Privacy policy must be accepted to proceed."
            )
        return value
    
    def create(self, validated_data):
        """Create final submission batch from temporary products and contact info"""
        temp_product_ids = validated_data.pop('temp_product_ids')
        
        user = None
        if 'request' in self.context and self.context['request'].user.is_authenticated:
            user = self.context['request'].user
        
        # Create submission batch
        batch = SubmissionBatch.objects.create(
            user=user,
            **validated_data
        )
        
        # Convert temporary products to permanent products
        temp_products = TempProduct.objects.filter(id__in=temp_product_ids)
        for temp_product in temp_products:
            # Create permanent product
            product = Product.objects.create(
                user=user,
                submission_batch=batch,
                title=temp_product.title,
                description=temp_product.description,
                condition=temp_product.condition,
                defects=temp_product.defects,
                estimated_value=temp_product.estimated_value,
                min_price_range=temp_product.min_price_range,
                max_price_range=temp_product.max_price_range,
                confidence=temp_product.confidence
            )
            
            # Copy images from temporary to permanent
            for temp_image in temp_product.images.all():
                ProductImage.objects.create(
                    product=product,
                    image=temp_image.image,
                    is_primary=temp_image.is_primary,
                    order=temp_image.order
                )
            
            # Delete temporary product (cascade will delete images)
            temp_product.delete()
        
        return batch