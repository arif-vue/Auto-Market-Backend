from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
import logging

from .models import CustomUser, OTP, RequestService, Review, Contact

logger = logging.getLogger(__name__)

# =============================================================================
# AUTHENTICATION EMAILS (TO USERS)
# =============================================================================

@receiver(post_save, sender=CustomUser)
def send_welcome_email(sender, instance, created, **kwargs):
    """Send welcome email when user signs up via Resend"""
    if created:
        try:
            subject = "Welcome to Auto Market! 🎉"
            message = f"""
Dear {instance.full_name},

Welcome to Auto Market! Your account has been successfully created.

Account Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Email: {instance.email}
👤 Name: {instance.full_name}
🎯 Role: {instance.get_role_display()}
✅ Status: Active

Getting Started:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛍️ List items on eBay and Amazon
🤖 Get AI-powered price estimates  
📊 Manage inventory efficiently
💰 Track sales and earnings

Platform Features:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Dual marketplace integration
✓ Automated listing management
✓ Real-time price optimization
✓ Inventory tracking
✓ Sales analytics

Need Help?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Support: alecgold808@gmail.com
🌐 Platform: Your marketplace dashboard
📞 Questions? We're here to help!

Best regards,
The Auto Market Team

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This email was sent via Resend API
Auto Market - Your Marketplace Solution
            """
            
            # Send TO USER via Resend
            send_mail(
                subject=subject,
                message=message,
                from_email='noreply@bluberryhq.com',  # Use your verified domain
                recipient_list=[instance.email],
                fail_silently=False
            )
            
            logger.info(f"Welcome email sent via Resend to {instance.email}")
            
        except Exception as e:
            logger.error(f"Failed to send welcome email via Resend: {str(e)}")

@receiver(post_save, sender=OTP)
def send_otp_email(sender, instance, created, **kwargs):
    """Send OTP email for password reset via Resend"""
    if created:
        try:
            subject = "Password Reset Code - Auto Market"
            message = f"""
Password Reset Request

Hello,

You requested to reset your password for your Auto Market account.

Your verification code: {instance.otp}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔒 Security Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ This code expires in 5 minutes
🚫 Don't share this code with anyone
🛡️ If you didn't request this reset, ignore this email
🔐 Use this code only on the official Auto Market website

Instructions:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Go to the password reset page
2. Enter this OTP code: {instance.otp}
3. Create your new password
4. Login with your new credentials

Need help? Contact us at alecgold808@gmail.com

Best regards,
Auto Market Security Team

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This email was sent securely via Resend API
Auto Market - Your Marketplace Solution
            """
            
            # Send TO USER via Resend
            send_mail(
                subject=subject,
                message=message,
                from_email='noreply@bluberryhq.com',  # Use your verified domain
                recipient_list=[instance.email],
                fail_silently=False
            )
            
            logger.info(f"OTP email sent via Resend to {instance.email}")
            
        except Exception as e:
            logger.error(f"Failed to send OTP email via Resend: {str(e)}")

# =============================================================================
# FORM SUBMISSION EMAILS (TO ADMIN)
# =============================================================================

@receiver(post_save, sender=RequestService)
def send_service_request_notification(sender, instance, created, **kwargs):
    """Send service request data TO admin via Resend"""
    if created:
        try:
            subject = f"🔔 New Service Request #{instance.id} - {instance.full_name}"
            message = f"""
NEW SERVICE REQUEST RECEIVED

Customer Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 Full Name: {instance.full_name}
📧 Email: {instance.email}
📱 Phone: {instance.phone_number}
📍 Location: {instance.city}, {instance.state} {instance.zip_code}

Service Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 Service Type: {instance.service_type}
📦 Items: {instance.types_of_items}
💰 Estimated Value: {instance.estimated_total_value}
⏰ Timeframe: {instance.preferred_timeframe}

Additional Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{instance.additional_information or '📝 No additional information provided'}

Request Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆔 Request ID: #{instance.id}
📅 Submitted: {instance.created_at.strftime('%B %d, %Y at %I:%M %p')}
🌐 Platform: Auto Market

ACTION REQUIRED:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Contact customer within 24 hours
✅ Schedule evaluation/consultation
✅ Provide detailed service quote
✅ Update customer on progress
✅ Follow up on service delivery

Quick Contact:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Email: {instance.email}
📱 Phone: {instance.phone_number}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This notification was sent via Resend API
Auto Market - Service Request System
            """
            
            # Send TO ADMIN via Resend (currently limited to verified email)
            send_mail(
                subject=subject,
                message=message,
                from_email='onboarding@resend.dev',  # Use verified Resend domain
                recipient_list=['alecgold808@gmail.com'],  # Resend verified email (for now)
                fail_silently=False
            )
            
            logger.info(f"Service request #{instance.id} notification sent via Resend to admin")
            
        except Exception as e:
            logger.error(f"Failed to send service request notification via Resend: {str(e)}")

@receiver(post_save, sender=Review)
def send_review_notification(sender, instance, created, **kwargs):
    """Send review data TO admin via Resend"""
    if created:
        try:
            stars = '⭐' * instance.rating
            subject = f"⭐ New Review #{instance.id} - {instance.rating} Stars from {instance.your_name}"
            message = f"""
NEW CUSTOMER REVIEW RECEIVED

Customer Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 Name: {instance.your_name}
📧 Email: {instance.email}
🌟 Rating: {stars} ({instance.rating}/5 Stars)

Review Content:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 "{instance.your_review}"

Review Analysis:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{'🎉 Excellent feedback!' if instance.rating == 5 else 
 '👍 Great feedback!' if instance.rating == 4 else
 '👌 Good feedback' if instance.rating == 3 else
 '⚠️ Needs attention' if instance.rating == 2 else
 '🚨 Urgent attention required'}

Review Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆔 Review ID: #{instance.id}
📅 Submitted: {instance.created_at.strftime('%B %d, %Y at %I:%M %p')}
🌐 Platform: Auto Market

RECOMMENDED ACTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{'✅ Share on social media\n✅ Feature on website homepage\n✅ Thank customer personally\n✅ Request testimonial' if instance.rating >= 4 else
 '✅ Thank customer for feedback\n✅ Address any concerns\n✅ Follow up for improvement\n✅ Monitor service quality'}

Customer Contact:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Email: {instance.email}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This notification was sent via Resend API
Auto Market - Review Management System
            """
            
            # Send TO ADMIN via Resend (currently limited to verified email)
            send_mail(
                subject=subject,
                message=message,
                from_email='onboarding@resend.dev',  # Use verified Resend domain
                recipient_list=['alecgold808@gmail.com'],  # Resend verified email (for now)
                fail_silently=False
            )
            
            logger.info(f"Review #{instance.id} notification sent via Resend to admin")
            
        except Exception as e:
            logger.error(f"Failed to send review notification via Resend: {str(e)}")

@receiver(post_save, sender=Contact)
def send_contact_notification(sender, instance, created, **kwargs):
    """Send contact message data TO admin via Resend"""
    if created:
        try:
            subject = f"📧 New Contact Message #{instance.id} from {instance.your_name}"
            message = f"""
NEW CONTACT MESSAGE RECEIVED

Customer Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 Name: {instance.your_name}
📧 Email: {instance.your_email}

Message Content:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 "{instance.your_message}"

Message Analysis:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Length: {len(instance.your_message)} characters
🏷️ Type: {'Question' if '?' in instance.your_message else
         'Support Request' if any(word in instance.your_message.lower() for word in ['help', 'problem', 'issue', 'bug']) else
         'Inquiry' if any(word in instance.your_message.lower() for word in ['price', 'cost', 'service', 'how']) else
         'General Message'}

Message Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆔 Message ID: #{instance.id}
📅 Submitted: {instance.created_at.strftime('%B %d, %Y at %I:%M %p')}
🌐 Platform: Auto Market

ACTION REQUIRED:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Respond within 24 hours
✅ Address their specific inquiry
✅ Provide helpful information
✅ Follow up if needed
✅ Add to customer database

Quick Actions:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 REPLY TO: {instance.your_email}
📱 Call if urgent
📝 Update CRM system

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This notification was sent via Resend API
Auto Market - Contact Management System
            """
            
            # Send TO ADMIN via Resend (currently limited to verified email)
            send_mail(
                subject=subject,
                message=message,
                from_email='onboarding@resend.dev',  # Use verified Resend domain
                recipient_list=['alecgold808@gmail.com'],  # Resend verified email (for now)
                fail_silently=False
            )
            
            logger.info(f"Contact message #{instance.id} notification sent via Resend to admin")
            
        except Exception as e:
            logger.error(f"Failed to send contact notification via Resend: {str(e)}")