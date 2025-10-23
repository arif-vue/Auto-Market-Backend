from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class SubmissionBatch(models.Model):
    """Groups multiple products submitted together with contact info"""
    BATCH_STATUS_CHOICES = (
        ('PENDING_REVIEW', 'Pending Admin Review'),
        ('PARTIALLY_PROCESSED', 'Some Products Processed'),
        ('APPROVED', 'All Products Approved'),
        ('REJECTED', 'All Products Rejected'),
        ('PROCESSING', 'Items Being Listed'),
        ('COMPLETED', 'All Items Processed'),
    )
    
    # Optional user - can be null for anonymous submissions
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    batch_status = models.CharField(max_length=20, choices=BATCH_STATUS_CHOICES, default='PENDING_REVIEW')
    
    # Contact Information
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    pickup_date = models.DateTimeField()
    pickup_address = models.TextField()
    privacy_policy_accepted = models.BooleanField(default=False)
    
    # Admin notes
    admin_notes = models.TextField(blank=True, help_text="Admin notes for approval/rejection")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_batches'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Batch {self.id} - {self.full_name} ({self.batch_status})"

    @property
    def total_items(self):
        return self.products.count()

    @property
    def total_estimated_value(self):
        return sum(product.estimated_value for product in self.products.all())

    def approve_batch(self, admin_user):
        """Admin approves the entire batch"""
        self.batch_status = 'APPROVED'
        self.approved_by = admin_user
        self.approved_at = timezone.now()
        self.save()
        
        # Update all products in batch
        self.products.update(listing_status='APPROVED')

    def reject_batch(self, admin_user, reason=""):
        """Admin rejects the entire batch"""
        self.batch_status = 'REJECTED'
        self.approved_by = admin_user
        self.admin_notes = reason
        self.save()


class Product(models.Model):
    LISTING_STATUS_CHOICES = (
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved for Listing'),
        ('LISTED', 'Listed on Both Platforms'),
        ('EBAY_SOLD', 'Sold on eBay'),
        ('AMAZON_SOLD', 'Sold on Amazon'),
        ('REMOVED', 'Removed from Listings'),
        ('REJECTED', 'Rejected by Admin'),
    )
    
    ITEM_CONDITION_CHOICES = (
        ("NEW", "New"),
        ("LIKE_NEW", "Like New"),
        ("EXCELLENT", "Excellent"),
        ("GOOD", "Good"),
        ("FAIR", "Fair"),
        ("POOR", "Poor")
    )
    
    CONFIDENCE_CHOICES = (
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low")
    )
    
    # Link to submission batch
    submission_batch = models.ForeignKey(
        SubmissionBatch, 
        on_delete=models.CASCADE, 
        related_name='products',
        null=True, 
        blank=True
    )
    
    # Basic Information
    # Optional user - can be null for anonymous submissions
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    condition = models.CharField(max_length=20, choices=ITEM_CONDITION_CHOICES, default="GOOD")
    defects = models.TextField(blank=True)
    
    # AI-detected pricing
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_price_range = models.DecimalField(max_digits=10, decimal_places=2)
    max_price_range = models.DecimalField(max_digits=10, decimal_places=2)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default="MEDIUM")
    
    # Final listing price (after admin review)
    final_listing_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Platform-specific fields
    # Marketplace listing IDs and URLs
    ebay_listing_id = models.CharField(max_length=100, blank=True, null=True, help_text="eBay listing ID")
    amazon_listing_id = models.CharField(max_length=100, blank=True, null=True, help_text="Amazon ASIN or listing ID") 
    ebay_listing_url = models.URLField(blank=True, null=True, help_text="eBay listing URL")
    amazon_listing_url = models.URLField(blank=True, null=True, help_text="Amazon listing URL")
    
    # Marketplace categories
    ebay_category = models.CharField(max_length=50, blank=True, null=True, help_text="eBay category ID")
    amazon_category = models.CharField(max_length=50, blank=True, null=True, help_text="Amazon product category")
    
    # Status tracking
    listing_status = models.CharField(
        max_length=20, 
        choices=LISTING_STATUS_CHOICES, 
        default='PENDING'
    )
    
    # Sale information
    sold_platform = models.CharField(max_length=20, blank=True, null=True)
    sold_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sold_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.get_listing_status_display()}"

    def mark_sold(self, platform, sale_price=None):
        """Mark item as sold on specific platform and update status accordingly"""
        from django.utils import timezone
        
        if platform.upper() == 'EBAY':
            self.listing_status = 'EBAY_SOLD'
            self.sold_platform = 'EBAY'
        elif platform.upper() == 'AMAZON':
            self.listing_status = 'AMAZON_SOLD'
            self.sold_platform = 'AMAZON'
        
        if sale_price:
            self.sold_price = sale_price
        self.sold_at = timezone.now()
        self.save()

    def list_on_platforms(self, ebay_id=None, amazon_id=None):
        """Mark as listed on both platforms"""
        self.listing_status = 'LISTED'
        if ebay_id:
            self.ebay_listing_id = ebay_id
        if amazon_id:
            self.amazon_listing_id = amazon_id
        self.save()

    def clean(self):
        """Custom validation for Product model"""
        super().clean()
        # Validate image count after product is saved
        if self.pk:  # Only validate if product already exists
            image_count = self.images.count()
            if image_count < 3:
                raise ValidationError("Each product must have at least 3 images.")
            if image_count > 8:
                raise ValidationError("Each product can have maximum 8 images.")


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_images/')
    is_primary = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Image {self.order} for {self.product.title}"


# Temporary models for two-step submission process
class TempProduct(models.Model):
    """Temporary storage for product data during two-step submission"""
    ITEM_CONDITION_CHOICES = (
        ("NEW", "New"),
        ("LIKE_NEW", "Like New"),
        ("EXCELLENT", "Excellent"),
        ("GOOD", "Good"),
        ("FAIR", "Fair"),
        ("POOR", "Poor")
    )
    
    CONFIDENCE_CHOICES = (
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low")
    )
    
    # Basic Information
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    condition = models.CharField(max_length=20, choices=ITEM_CONDITION_CHOICES, default="GOOD")
    defects = models.TextField(blank=True)
    
    # AI-detected pricing
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_price_range = models.DecimalField(max_digits=10, decimal_places=2)
    max_price_range = models.DecimalField(max_digits=10, decimal_places=2)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default="MEDIUM")
    
    # Temporary storage management
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            # Auto-expire after 30 minutes (reduced from 24 hours for faster cleanup)
            self.expires_at = timezone.now() + timezone.timedelta(minutes=30)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Temp: {self.title} (expires {self.expires_at})"
    
    def is_expired(self):
        if not self.expires_at:
            return False  # If no expiration date set, consider it not expired
        return timezone.now() > self.expires_at
    
    class Meta:
        verbose_name = "Temporary Product"
        verbose_name_plural = "Temporary Products"
        

class TempProductImage(models.Model):
    """Temporary storage for product images during two-step submission"""
    temp_product = models.ForeignKey(TempProduct, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='temp_product_images/')
    is_primary = models.BooleanField(default=False)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        verbose_name = "Temporary Product Image"
        verbose_name_plural = "Temporary Product Images"
    
    def __str__(self):
        return f"Temp Image {self.order} for {self.temp_product.title}"


# Legacy model - keeping for backward compatibility but functionality moved to SubmissionBatch
class SellerContactInfo(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    pickup_date = models.DateTimeField()
    pickup_address = models.TextField()
    products = models.ManyToManyField(Product, related_name="contact_info")
    privacy_policy_accepted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} - {self.email}"

    class Meta:
        verbose_name = "Legacy Seller Contact Info"
        verbose_name_plural = "Legacy Seller Contact Info"


class EBayUserToken(models.Model):
    """Store eBay OAuth tokens for users"""
    user_id = models.IntegerField(unique=True)  # Using integer to handle anonymous users
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    token_type = models.CharField(max_length=50, default='Bearer')
    expires_at = models.DateTimeField()
    scope = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def is_expired(self):
        """Check if token is expired"""
        if not self.expires_at:
            return False  # If no expiration date set, consider it not expired
        return timezone.now() >= self.expires_at
    
    def needs_refresh(self):
        """Check if token needs refresh (expires in less than 1 hour)"""
        if not self.expires_at:
            return False
        return timezone.now() >= (self.expires_at - timezone.timedelta(hours=1))
    
    def auto_refresh(self):
        """Automatically refresh token if needed"""
        if not self.refresh_token or not self.needs_refresh():
            return False
            
        from .ebay_service import eBayService
        ebay_service = eBayService()
        
        try:
            token_data = ebay_service.refresh_access_token(self.refresh_token)
            if token_data and 'access_token' in token_data:
                self.access_token = token_data['access_token']
                self.expires_at = timezone.now() + timezone.timedelta(
                    seconds=token_data.get('expires_in', 7200)
                )
                if 'refresh_token' in token_data:
                    self.refresh_token = token_data['refresh_token']
                self.save()
                return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to auto-refresh eBay token: {e}")
            
        return False
    
    def __str__(self):
        return f"eBay Token for User {self.user_id}"
    
    class Meta:
        verbose_name = "eBay User Token"
        verbose_name_plural = "eBay User Tokens"

