from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import (
    Product, ProductImage, SubmissionBatch, TempProduct, 
    TempProductImage, SellerContactInfo, EBayUserToken
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 50px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = "Preview"


class ProductInline(admin.TabularInline):
    model = Product
    extra = 0
    readonly_fields = ('title', 'condition', 'safe_inline_estimated_value', 'listing_status')
    fields = ('title', 'condition', 'safe_inline_estimated_value', 'listing_status', 'safe_inline_final_price')
    can_delete = False
    
    def safe_inline_estimated_value(self, obj):
        """Safe display of estimated value in inline"""
        try:
            from decimal import Decimal, InvalidOperation
            if obj.estimated_value:
                try:
                    return f"${Decimal(str(obj.estimated_value)):.2f}"
                except InvalidOperation:
                    return "$0.00"
            return "$0.00"
        except:
            return "$0.00"
    safe_inline_estimated_value.short_description = "Est. Value"
    
    def safe_inline_final_price(self, obj):
        """Safe display of final price in inline"""
        try:
            from decimal import Decimal
            if obj.final_listing_price:
                return f"${Decimal(str(obj.final_listing_price)):.2f}"
            return "-"
        except:
            return "-"
    safe_inline_final_price.short_description = "Final Price"


@admin.register(SubmissionBatch)
class SubmissionBatchAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'full_name', 'email', 'batch_status', 'total_items', 
        'safe_total_estimated_value', 'created_at'
    ]
    list_filter = ['batch_status', 'created_at', 'approved_at']
    search_fields = ['full_name', 'email', 'phone']
    readonly_fields = ['user', 'created_at', 'updated_at', 'total_items', 'safe_total_estimated_value']
    inlines = [ProductInline]
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('user', 'full_name', 'email', 'phone')
        }),
        ('Pickup Details', {
            'fields': ('pickup_date', 'pickup_address', 'privacy_policy_accepted')
        }),
        ('Status & Approval', {
            'fields': ('batch_status', 'admin_notes', 'approved_by', 'approved_at')
        }),
        ('Summary', {
            'fields': ('total_items', 'safe_total_estimated_value')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.batch_status in ['APPROVED', 'REJECTED']:
            readonly.extend(['batch_status'])
        return readonly

    actions = ['approve_batches', 'reject_batches']

    def approve_batches(self, request, queryset):
        count = 0
        for batch in queryset.filter(batch_status='PENDING_REVIEW'):
            batch.approve_batch(request.user)
            count += 1
        self.message_user(request, f"Approved {count} batches.")
    approve_batches.short_description = "Approve selected batches"

    def reject_batches(self, request, queryset):
        count = 0
        for batch in queryset.filter(batch_status='PENDING_REVIEW'):
            batch.reject_batch(request.user, "Bulk rejection from admin")
            count += 1
        self.message_user(request, f"Rejected {count} batches.")
    reject_batches.short_description = "Reject selected batches"
    
    def safe_total_estimated_value(self, obj):
        """Safe display of total estimated value to prevent decimal errors"""
        try:
            from decimal import Decimal, InvalidOperation
            total = Decimal('0.00')
            for product in obj.products.all():
                try:
                    if product.estimated_value:
                        val = Decimal(str(product.estimated_value))
                        if val.is_finite():  # Check if value is valid
                            total += val
                except (InvalidOperation, TypeError, ValueError):
                    continue  # Skip problematic values
            return f"${total:.2f}"
        except:
            return "$0.00"
    safe_total_estimated_value.short_description = "Total Estimated Value"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'user', 'submission_batch_link', 'condition', 
        'safe_estimated_value', 'safe_final_listing_price', 'listing_status', 'created_at'
    ]
    list_filter = [
        'listing_status', 'condition', 'confidence', 'created_at',
        'submission_batch__batch_status'
    ]
    search_fields = ['title', 'description', 'user__email']
    readonly_fields = [
        'user', 'submission_batch', 'estimated_value', 'min_price_range', 
        'max_price_range', 'confidence', 'created_at', 'updated_at'
    ]
    inlines = [ProductImageInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'submission_batch', 'title', 'description', 'condition', 'defects')
        }),
        ('AI Pricing Analysis', {
            'fields': ('estimated_value', 'min_price_range', 'max_price_range', 'confidence'),
            'classes': ('collapse',)
        }),
        ('Final Pricing', {
            'fields': ('final_listing_price',)
        }),
        ('Platform Information', {
            'fields': (
                'ebay_listing_id', 'amazon_listing_id', 
                'ebay_category', 'amazon_category'
            ),
            'classes': ('collapse',)
        }),
        ('Status & Sales', {
            'fields': ('listing_status', 'sold_platform', 'sold_price', 'sold_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def submission_batch_link(self, obj):
        if obj.submission_batch:
            url = reverse('admin:api_submissionbatch_change', args=[obj.submission_batch.id])
            return format_html('<a href="{}">{}</a>', url, obj.submission_batch.id)
        return "N/A"
    submission_batch_link.short_description = "Submission Batch"
    
    def safe_estimated_value(self, obj):
        """Safe display of estimated value to prevent decimal errors"""
        try:
            from decimal import Decimal, InvalidOperation
            if obj.estimated_value:
                try:
                    val = Decimal(str(obj.estimated_value))
                    if val.is_finite():  # Check if value is valid
                        return f"${val:.2f}"
                except InvalidOperation:
                    return "$0.00"
            return "$0.00"
        except:
            return "$0.00"
    safe_estimated_value.short_description = "Estimated Value"
    
    def safe_final_listing_price(self, obj):
        """Safe display of final listing price to prevent decimal errors"""
        try:
            from decimal import Decimal, InvalidOperation
            if obj.final_listing_price:
                try:
                    val = Decimal(str(obj.final_listing_price))
                    if val.is_finite():  # Check if value is valid
                        return f"${val:.2f}"
                except InvalidOperation:
                    return "-"
            return "-"
        except:
            return "-"
    safe_final_listing_price.short_description = "Final Price"

    actions = ['mark_as_listed', 'mark_as_removed']

    def mark_as_listed(self, request, queryset):
        count = queryset.filter(listing_status='APPROVED').update(listing_status='LISTED')
        self.message_user(request, f"Marked {count} products as listed.")
    mark_as_listed.short_description = "Mark as listed on platforms"

    def mark_as_removed(self, request, queryset):
        count = queryset.update(listing_status='REMOVED')
        self.message_user(request, f"Marked {count} products as removed.")
    mark_as_removed.short_description = "Mark as removed from platforms"


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'is_primary', 'order', 'image_preview']
    list_filter = ['is_primary', 'product__listing_status']
    search_fields = ['product__title']
    readonly_fields = ['image_preview']

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = "Preview"

# Customize admin site
admin.site.site_header = "Auto Market Administration"
admin.site.site_title = "Auto Market Admin"
admin.site.index_title = "Welcome to Auto Market Administration"


# Additional Model Admins
@admin.register(TempProduct)
class TempProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'condition', 'safe_temp_estimated_value', 'created_at', 'expires_at', 'is_expired']
    list_filter = ['condition', 'confidence', 'created_at', 'expires_at']
    search_fields = ['title', 'description', 'user__email']
    readonly_fields = ['user', 'estimated_value', 'min_price_range', 'max_price_range', 'confidence', 'created_at', 'expires_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'title', 'description', 'condition', 'defects')
        }),
        ('AI Pricing Analysis', {
            'fields': ('estimated_value', 'min_price_range', 'max_price_range', 'confidence'),
            'classes': ('collapse',)
        }),
        ('Temporary Storage', {
            'fields': ('created_at', 'expires_at'),
            'classes': ('collapse',)
        }),
    )

    def safe_temp_estimated_value(self, obj):
        """Safe display of temp estimated value to prevent decimal errors"""
        try:
            from decimal import Decimal
            if obj.estimated_value:
                return f"${Decimal(str(obj.estimated_value)):.2f}"
            return "$0.00"
        except:
            return "$0.00"
    safe_temp_estimated_value.short_description = "Estimated Value"
    
    def is_expired(self, obj):
        if not obj.expires_at:
            return False  # If no expiration date, consider it not expired
        return obj.is_expired()
    is_expired.boolean = True
    is_expired.short_description = "Expired"

    actions = ['delete_expired']

    def delete_expired(self, request, queryset):
        count = queryset.filter(expires_at__lt=timezone.now()).count()
        queryset.filter(expires_at__lt=timezone.now()).delete()
        self.message_user(request, f"Deleted {count} expired temporary products.")
    delete_expired.short_description = "Delete expired temporary products"


@admin.register(TempProductImage)
class TempProductImageAdmin(admin.ModelAdmin):
    list_display = ['temp_product', 'is_primary', 'order', 'image_preview']
    list_filter = ['is_primary']
    search_fields = ['temp_product__title']
    readonly_fields = ['image_preview']

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = "Preview"


@admin.register(SellerContactInfo)
class SellerContactInfoAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'phone', 'pickup_date', 'privacy_policy_accepted', 'submitted_at']
    list_filter = ['privacy_policy_accepted', 'pickup_date', 'submitted_at']
    search_fields = ['full_name', 'email', 'phone']
    readonly_fields = ['user', 'submitted_at']
    filter_horizontal = ['products']
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('user', 'full_name', 'email', 'phone')
        }),
        ('Pickup Details', {
            'fields': ('pickup_date', 'pickup_address', 'privacy_policy_accepted')
        }),
        ('Products', {
            'fields': ('products',)
        }),
        ('Timestamps', {
            'fields': ('submitted_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(EBayUserToken)
class EBayUserTokenAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'token_type', 'expires_at', 'is_expired', 'created_at', 'updated_at']
    list_filter = ['token_type', 'expires_at', 'created_at']
    search_fields = ['user_id']
    readonly_fields = ['user_id', 'created_at', 'updated_at', 'is_token_expired']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user_id',)
        }),
        ('Token Details', {
            'fields': ('access_token', 'refresh_token', 'token_type', 'scope')
        }),
        ('Token Status', {
            'fields': ('expires_at', 'is_token_expired')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def is_expired(self, obj):
        if not obj.expires_at:
            return False  # If no expiration date, consider it not expired
        return obj.is_expired()
    is_expired.boolean = True
    is_expired.short_description = "Token Expired"

    def is_token_expired(self, obj):
        if not obj.expires_at:
            return False  # If no expiration date, consider it not expired
        return obj.is_expired()
    is_token_expired.boolean = True
    is_token_expired.short_description = "Expired"

    actions = ['delete_expired_tokens']

    def delete_expired_tokens(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(expires_at__lt=timezone.now()).count()
        queryset.filter(expires_at__lt=timezone.now()).delete()
        self.message_user(request, f"Deleted {count} expired eBay tokens.")
    delete_expired_tokens.short_description = "Delete expired tokens"
