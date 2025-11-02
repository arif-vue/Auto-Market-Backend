"""
Email services for Auto-Market using Resend API
Handles item submission notifications and other product-related emails
"""
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)


class ItemSubmissionEmailService:
    """Service for sending item submission emails via Resend"""
    
    @staticmethod
    def send_customer_confirmation(user_email, user_name, submitted_items, contact_info):
        """
        Send confirmation email to customer about their item submission
        """
        try:
            total_items = len(submitted_items)
            total_estimated_value = sum(float(item.get('estimated_value', 0)) for item in submitted_items)
            
            # Create items list for customer
            items_list = ""
            for idx, item in enumerate(submitted_items, 1):
                items_list += f"""
                {idx}. {item.get('title', 'N/A')}
                   - Estimated Value: ${float(item.get('estimated_value', 0)):.2f}
                   - Condition: {item.get('condition', 'N/A').title()}
                   - Confidence Level: {item.get('confidence', 'Medium').title()}
                """
            
            # Pickup date formatting
            pickup_date = contact_info.get('pickup_date', '')
            if pickup_date:
                from django.utils.dateparse import parse_datetime
                try:
                    if isinstance(pickup_date, str):
                        pickup_dt = parse_datetime(pickup_date)
                        if pickup_dt:
                            pickup_date = pickup_dt.strftime('%B %d, %Y at %I:%M %p')
                except:
                    pass
            
            subject = f"✅ Submission Confirmed: {total_items} Items (${total_estimated_value:.2f})"
            message = f"""
Dear {user_name},

Thank you for submitting your items to Auto Market! We have successfully received your submission and it is now under review.

SUBMISSION CONFIRMATION
==========================================

Your Contact Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 Name: {contact_info.get('full_name', 'N/A')}
📧 Email: {contact_info.get('email', user_email or 'N/A')}
📱 Phone: {contact_info.get('phone', 'N/A')}
📅 Pickup Date: {pickup_date}
📍 Pickup Address: {contact_info.get('pickup_address', 'N/A')}

Submission Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 Total Items: {total_items}
💰 Total Estimated Value: ${total_estimated_value:.2f}
📋 Privacy Policy: ✅ Accepted

Your Submitted Items:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{items_list}

What Happens Next:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 🔍 Our team will review and evaluate your items
2. 📧 You'll receive an email with our approval decision
3. 🤝 We'll contact you to confirm pickup details
4. 🚚 Schedule pickup for approved items
5. 💰 Items will be listed on eBay and Amazon
6. 📊 You'll receive updates on sales and earnings

Contact Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Questions? Email us at: alecgold808@gmail.com
🌐 Website: https://bluberryhq.com
⏰ Response Time: Within 24 hours

Thank you for choosing Auto Market for your marketplace needs!

Best regards,
The Auto Market Team

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This confirmation was sent via Resend API
Auto Market - Your Marketplace Solution
            """
            
            # Send to customer using Resend
            from django.core.mail import send_mail
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user_email],
                fail_silently=False,
            )
            
            logger.info(f"Customer confirmation sent for {total_items} item submission to {user_email}")
            
            return {
                'success': True,
                'message': 'Customer confirmation sent successfully'
            }
            
        except Exception as e:
            logger.error(f"Error sending customer confirmation: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def send_admin_notification(submitted_items, contact_info, user_email=None):
        """
        Send notification to admin about new item submission
        """
        try:
            total_items = len(submitted_items)
            total_estimated_value = sum(float(item.get('estimated_value', 0)) for item in submitted_items)
            
            # Create items list for admin
            items_list = ""
            for idx, item in enumerate(submitted_items, 1):
                items_list += f"""
                {idx}. {item.get('title', 'N/A')}
                   - Description: {item.get('description', 'N/A')[:100]}...
                   - Estimated Value: ${float(item.get('estimated_value', 0)):.2f}
                   - Condition: {item.get('condition', 'N/A').title()}
                   - Confidence: {item.get('confidence', 'Medium').title()}
                   - Defects: {item.get('defects', 'None')}
                """
            
            # Pickup date formatting
            pickup_date = contact_info.get('pickup_date', '')
            if pickup_date:
                from django.utils.dateparse import parse_datetime
                try:
                    if isinstance(pickup_date, str):
                        pickup_dt = parse_datetime(pickup_date)
                        if pickup_dt:
                            pickup_date = pickup_dt.strftime('%B %d, %Y at %I:%M %p')
                except:
                    pass
            
            subject = f"🚨 New Item Submission: {total_items} Items (${total_estimated_value:.2f})"
            message = f"""
            NEW ITEM SUBMISSION RECEIVED
            ==========================================
            
            CUSTOMER INFORMATION:
            - Name: {contact_info.get('full_name', 'N/A')}
            - Email: {contact_info.get('email', user_email or 'N/A')}
            - Phone: {contact_info.get('phone', 'N/A')}
            - Pickup Date: {pickup_date}
            - Pickup Address: {contact_info.get('pickup_address', 'N/A')}
            
            SUBMISSION SUMMARY:
            - Total Items: {total_items}
            - Total Estimated Value: ${total_estimated_value:.2f}
            - Privacy Policy Accepted: {contact_info.get('privacy_policy_accepted', False)}
            
            SUBMITTED ITEMS:
            {items_list}
            
            ACTION REQUIRED:
            1. Review and approve/reject items
            2. Contact customer to confirm pickup details
            3. Schedule pickup for approved items
            
            Customer Email: {contact_info.get('email', user_email or 'N/A')}
            Customer Phone: {contact_info.get('phone', 'N/A')}
            
            Login to admin panel to process this submission.
            """
            
            # Send to admin using existing send_admin_email function
            from django.core.mail import send_mail
            
            admin_email = getattr(settings, 'ADMIN_EMAIL', 'alecgold808@gmail.com')
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin_email],
                fail_silently=False,
            )
            
            logger.info(f"Admin notification sent for {total_items} item submission")
            
            return {
                'success': True,
                'message': 'Admin notification sent successfully'
            }
            
        except Exception as e:
            logger.error(f"Error sending admin notification: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


def send_item_submission_emails(user_email, user_name, submitted_items, contact_info):
    """
    Main function to send both customer confirmation and admin notification emails
    """
    results = {
        'customer_email': None,
        'admin_email': None
    }
    
    try:
        # Send customer confirmation email
        customer_result = ItemSubmissionEmailService.send_customer_confirmation(
            user_email=user_email,
            user_name=user_name,
            submitted_items=submitted_items,
            contact_info=contact_info
        )
        results['customer_email'] = customer_result
        
        # Send admin notification email  
        admin_result = ItemSubmissionEmailService.send_admin_notification(
            submitted_items=submitted_items,
            contact_info=contact_info,
            user_email=user_email
        )
        results['admin_email'] = admin_result
        
        return results
        
    except Exception as e:
        logger.error(f"Error in send_item_submission_emails: {str(e)}")
        return {
            'customer_email': {'success': False, 'error': str(e)},
            'admin_email': {'success': False, 'error': str(e)}
        }
