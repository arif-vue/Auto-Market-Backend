"""
Custom Django Email Backend for Resend
"""
import logging
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings
import resend

logger = logging.getLogger(__name__)

class ResendEmailBackend(BaseEmailBackend):
    """
    Custom email backend that uses Resend API to send emails
    """
    
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        # Initialize Resend with API key
        resend.api_key = getattr(settings, 'RESEND_API_KEY', None)
        
        if not resend.api_key:
            logger.error("RESEND_API_KEY not configured in settings")
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is required for Resend email backend")
    
    def send_messages(self, email_messages):
        """
        Send multiple email messages using Resend API
        """
        if not email_messages:
            return 0
        
        sent_count = 0
        
        for message in email_messages:
            try:
                # Prepare email data for Resend API
                email_data = {
                    "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                    "to": message.to,
                    "subject": message.subject,
                }
                
                # Handle CC and BCC
                if hasattr(message, 'cc') and message.cc:
                    email_data["cc"] = message.cc
                if hasattr(message, 'bcc') and message.bcc:
                    email_data["bcc"] = message.bcc
                
                # Handle message body (HTML vs plain text)
                if hasattr(message, 'alternatives') and message.alternatives:
                    # Look for HTML content in alternatives
                    for content, content_type in message.alternatives:
                        if content_type == 'text/html':
                            email_data["html"] = content
                            break
                    # Always include plain text as fallback
                    if message.body:
                        email_data["text"] = message.body
                else:
                    # Plain text only
                    email_data["text"] = message.body
                
                # Handle attachments
                if hasattr(message, 'attachments') and message.attachments:
                    attachments = []
                    for attachment in message.attachments:
                        if isinstance(attachment, tuple) and len(attachment) >= 2:
                            filename, content, mimetype = attachment[0], attachment[1], attachment[2] if len(attachment) > 2 else None
                            # Resend expects base64 encoded content for attachments
                            import base64
                            if isinstance(content, bytes):
                                content_b64 = base64.b64encode(content).decode('utf-8')
                            else:
                                content_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                            
                            attachment_data = {
                                "filename": filename,
                                "content": content_b64,
                            }
                            if mimetype:
                                attachment_data["type"] = mimetype
                            
                            attachments.append(attachment_data)
                    
                    if attachments:
                        email_data["attachments"] = attachments
                
                # Send email via Resend API
                logger.info(f"Sending email to {email_data['to']} via Resend")
                logger.info(f"Email data: From={email_data['from']}, Subject={email_data['subject']}")
                
                response = resend.Emails.send(email_data)
                
                if response and hasattr(response, 'get') and response.get('id'):
                    logger.info(f"Email sent successfully via Resend. ID: {response.get('id')}")
                    sent_count += 1
                else:
                    logger.error(f"Failed to send email via Resend. Response: {response}")
                    if not self.fail_silently:
                        raise Exception(f"Resend API error: {response}")
                        
            except Exception as e:
                logger.error(f"Error sending email via Resend: {str(e)}")
                if not self.fail_silently:
                    raise e
        
        return sent_count