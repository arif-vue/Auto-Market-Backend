"""
Management command to refresh eBay tokens that are about to expire
Run this periodically (e.g., via cron job) to prevent token expiration
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import EBayUserToken
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Refresh eBay tokens that are about to expire'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours-before',
            type=int,
            default=2,
            help='Refresh tokens that expire within this many hours (default: 2)'
        )
        
    def handle(self, *args, **options):
        hours_before = options['hours_before']
        
        # Find tokens that expire within the specified hours
        cutoff_time = timezone.now() + timezone.timedelta(hours=hours_before)
        
        tokens_to_refresh = EBayUserToken.objects.filter(
            expires_at__lte=cutoff_time,
            refresh_token__isnull=False
        ).exclude(refresh_token='')
        
        self.stdout.write(f"Found {tokens_to_refresh.count()} tokens to refresh")
        
        refreshed_count = 0
        failed_count = 0
        
        for token in tokens_to_refresh:
            self.stdout.write(f"Refreshing token for user {token.user_id}...")
            
            if token.auto_refresh():
                refreshed_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Successfully refreshed token for user {token.user_id}")
                )
            else:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(f"✗ Failed to refresh token for user {token.user_id}")
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\nRefresh complete: {refreshed_count} successful, {failed_count} failed"
            )
        )
        
        if failed_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    "Failed tokens may require manual re-authorization"
                )
            )