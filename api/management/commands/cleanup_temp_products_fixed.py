"""
Django management command to clean up expired temporary products and images
Reduces auto-delete time from 24 hours to 30 minutes for faster cleanup
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import TempProduct, TempProductImage
import os
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Delete temporary products and images that are expired (older than 30 minutes)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes',
            type=int,
            default=30,
            help='Delete temp products older than this many minutes (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        minutes = options['minutes']
        dry_run = options['dry_run']
        
        try:
            # Calculate cutoff time
            cutoff_time = timezone.now() - timedelta(minutes=minutes)
            
            # Find expired temp products
            expired_products = TempProduct.objects.filter(expires_at__lt=cutoff_time)
            product_count = expired_products.count()
            
            if product_count == 0:
                self.stdout.write(
                    self.style.SUCCESS(f'[OK] No expired temporary products found (older than {minutes} minutes)')
                )
                return
            
            deleted_images = 0
            image_errors = 0
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'🔍 DRY RUN: Would delete {product_count} expired temporary products')
                )
                
                for product in expired_products:
                    self.stdout.write(f'  - {product.title} (ID: {product.id}, expired: {product.expires_at})')
                    
                    # Count images that would be deleted
                    for img in product.images.all():
                        if img.image and os.path.isfile(img.image.path):
                            deleted_images += 1
                            self.stdout.write(f'    └── Image: {img.image.name}')
                
                self.stdout.write(f'🔍 Would also delete {deleted_images} image files')
                return
            
            # Actually delete products and images
            self.stdout.write(f'🗑️  Deleting {product_count} expired temporary products...')
            
            for product in expired_products:
                self.stdout.write(f'  [PROCESSING] Processing: {product.title} (ID: {product.id})')
                
                # Delete associated images from filesystem
                for img in product.images.all():
                    if img.image and os.path.isfile(img.image.path):
                        try:
                            os.remove(img.image.path)
                            deleted_images += 1
                            self.stdout.write(f'    [OK] Deleted image: {img.image.name}')
                        except Exception as e:
                            image_errors += 1
                            self.stdout.write(
                                self.style.ERROR(f'    [ERROR] Error deleting image {img.image.name}: {str(e)}')
                            )
                
                # Delete the temp product (this also deletes TempProductImage records via CASCADE)
                product.delete()
                self.stdout.write(f'    [OK] Deleted product: {product.title}')
            
            # Summary
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('🎉 Cleanup completed successfully!'))
            self.stdout.write(f'  📦 Deleted products: {product_count}')
            self.stdout.write(f'  🖼️  Deleted images: {deleted_images}')
            
            if image_errors > 0:
                self.stdout.write(self.style.WARNING(f'  ⚠️  Image deletion errors: {image_errors}'))
            
            # Log the cleanup
            logger.info(
                f'Temp product cleanup completed: {product_count} products, {deleted_images} images deleted'
            )
            
        except Exception as e:
            error_msg = f'[ERROR] Error during temp product cleanup: {str(e)}'
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
            raise e