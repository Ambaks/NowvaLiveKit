"""
Email service for sending workout programs to users.
Uses Resend API for reliable email delivery.
"""

import os
import logging
from typing import Optional
from pathlib import Path

try:
    import resend
except ImportError:
    resend = None
    logging.warning("Resend package not installed. Email functionality will be disabled.")

# Configure logging
logger = logging.getLogger(__name__)

# Sender address — set RESEND_FROM_EMAIL; the placeholder fallback triggers a
# warning at send time.
_PLACEHOLDER_FROM_EMAIL = "noreply@yourdomain.com"
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", _PLACEHOLDER_FROM_EMAIL)

# One-time initialization guard for initialize_resend()
_resend_initialized = False


def _warn_if_placeholder_sender():
    if FROM_EMAIL == _PLACEHOLDER_FROM_EMAIL:
        logger.warning(
            "RESEND_FROM_EMAIL environment variable not set — "
            f"sending from placeholder address '{_PLACEHOLDER_FROM_EMAIL}'. "
            "Set RESEND_FROM_EMAIL to a verified sender domain."
        )


def initialize_resend():
    """Initialize Resend with API key from environment (one-time)"""
    global _resend_initialized
    if _resend_initialized:
        return True

    if resend is None:
        logger.error("Resend package not installed. Run: pip install resend")
        return False

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        logger.error("RESEND_API_KEY environment variable not set")
        return False

    resend.api_key = api_key
    _resend_initialized = True
    return True


def send_program_email(
    to_email: str,
    user_name: str,
    program_id: int,
    pdf_path: str
) -> Optional[dict]:
    """
    Send workout program PDF via email using Resend.

    Args:
        to_email: Recipient email address
        user_name: User's first name for personalization
        program_id: Program ID for reference
        pdf_path: Path to the PDF file to attach

    Returns:
        dict: Resend API response if successful, None if failed
    """
    if not initialize_resend():
        logger.error("Failed to initialize Resend")
        return None

    try:
        # Validate PDF file exists
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return None

        # Read PDF content
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()

        _warn_if_placeholder_sender()

        # Prepare email parameters
        params = {
            "from": f"Nova <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": "Your Personalized Workout Program is Ready! 💪",
            "html": f"""
                <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, rgba(139, 92, 246, 0.05) 0%, rgba(59, 130, 246, 0.05) 100%); padding: 40px 20px;">
                    <!-- Header with gradient -->
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="background: linear-gradient(135deg, #8B5CF6 0%, #3B82F6 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; font-size: 32px; font-weight: bold; margin: 0;">
                            Your Program is Ready! 🎉
                        </h1>
                    </div>

                    <div style="background: white; border-radius: 16px; padding: 32px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                        <h2 style="color: #171717; font-size: 24px; margin-bottom: 16px;">Hi {user_name}!</h2>

                        <p style="font-size: 16px; line-height: 1.6; color: #555; margin-bottom: 20px;">
                            Thank you for using our AI-powered workout program generator! Your custom program is attached as a PDF and includes:
                        </p>

                        <ul style="font-size: 16px; line-height: 1.8; color: #555; margin-bottom: 24px;">
                            <li><strong>Weekly workout schedule</strong> tailored to your goals</li>
                            <li><strong>Detailed exercise instructions</strong> with proper form cues</li>
                            <li><strong>Sets, reps, and intensity guidance</strong> for optimal results</li>
                            <li><strong>Progression tracking</strong> to monitor your improvements</li>
                        </ul>

                        <!-- Early Adopter Benefits Section -->
                        <div style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%); border-radius: 12px; padding: 24px; margin: 24px 0; border: 2px solid rgba(139, 92, 246, 0.2);">
                            <h3 style="color: #8B5CF6; font-size: 20px; margin: 0 0 12px 0; display: flex; align-items: center;">
                                ✨ Early Adopter Exclusive Benefits
                            </h3>
                            <p style="font-size: 15px; line-height: 1.6; color: #555; margin-bottom: 12px;">
                                As one of our early users, you're not just getting a workout program — you're becoming part of something revolutionary! Here's what's coming your way:
                            </p>
                            <ul style="font-size: 15px; line-height: 1.7; color: #555; margin: 12px 0;">
                                <li><strong style="color: #8B5CF6;">Massive future discounts</strong> on all premium features</li>
                                <li><strong style="color: #3B82F6;">FREE products and equipment</strong> when we launch</li>
                                <li><strong style="color: #8B5CF6;">FREE Workout Station</strong> (valued at over $2,000!) 🎁</li>
                                <li><strong style="color: #3B82F6;">First access</strong> to test products before anyone else</li>
                                <li><strong style="color: #8B5CF6;">Direct input</strong> on product development</li>
                            </ul>
                            <p style="font-size: 14px; line-height: 1.5; color: #737373; margin-top: 12px; font-style: italic;">
                                Your feedback is shaping the future of AI-powered fitness coaching!
                            </p>
                        </div>

                        <!-- What's Coming Section -->
                        <div style="background: #F9FAFB; border-radius: 12px; padding: 24px; margin: 24px 0;">
                            <h3 style="color: #171717; font-size: 18px; margin: 0 0 12px 0;">
                                🚀 What's Coming in the Product
                            </h3>
                            <ul style="font-size: 15px; line-height: 1.7; color: #555; margin: 0;">
                                <li><strong>Real-time AI coaching</strong> with voice feedback during workouts</li>
                                <li><strong>Smart equipment integration</strong> for automatic rep and velocity tracking</li>
                                <li><strong>Adaptive programming</strong> that evolves based on your performance</li>
                                <li><strong>Form analysis</strong> using computer vision</li>
                                <li><strong>Community features</strong> to train with others worldwide</li>
                                <li><strong>Advanced analytics</strong> to optimize your training</li>
                            </ul>
                        </div>

                        <p style="font-size: 16px; line-height: 1.6; color: #555; margin: 24px 0 16px 0;">
                            Ready to crush those goals? Let's get started! 💪
                        </p>

                        <p style="font-size: 16px; line-height: 1.6; color: #555; margin: 16px 0;">
                            If you have any questions or need modifications to your program, feel free to reach out. We'd love to hear your feedback!
                        </p>

                        <p style="font-size: 16px; line-height: 1.6; color: #555; margin-top: 32px;">
                            Best,<br>
                            <strong style="background: linear-gradient(135deg, #8B5CF6 0%, #3B82F6 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">Nova</strong><br>
                            <span style="color: #737373;">Your AI Fitness Coach</span>
                        </p>
                    </div>

                    <div style="text-align: center; margin-top: 20px; padding: 20px;">
                        <p style="font-size: 12px; color: #A3A3A3; line-height: 1.5;">
                            Program ID: {program_id}<br>
                            Stay connected for updates on our product launch!
                        </p>
                    </div>
                </div>
            """,
            "attachments": [{
                "filename": f"workout_program_{program_id}.pdf",
                "content": list(pdf_content)
            }]
        }

        # Send email
        logger.info(f"Sending program email to {to_email} (Program ID: {program_id})")
        response = resend.Emails.send(params)
        logger.info(f"Email sent successfully to {to_email}. Response: {response}")

        return response

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}", exc_info=True)
        return None


def send_test_email(to_email: str) -> Optional[dict]:
    """
    Send a test email to verify Resend configuration.

    Args:
        to_email: Test recipient email address

    Returns:
        dict: Resend API response if successful, None if failed
    """
    if not initialize_resend():
        logger.error("Failed to initialize Resend")
        return None

    try:
        _warn_if_placeholder_sender()

        params = {
            "from": f"Nova <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": "Test Email from Nova - Resend Integration",
            "html": """
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2>✅ Resend Integration Test</h2>
                    <p>This is a test email to verify that Resend is configured correctly.</p>
                    <p>If you received this email, the integration is working!</p>
                    <p>- Nova, Your AI Fitness Coach</p>
                </div>
            """
        }

        logger.info(f"Sending test email to {to_email}")
        response = resend.Emails.send(params)
        logger.info(f"Test email sent successfully. Response: {response}")

        return response

    except Exception as e:
        logger.error(f"Failed to send test email: {str(e)}", exc_info=True)
        return None


if __name__ == "__main__":
    # Test the email service
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s'
    )

    if len(sys.argv) < 2:
        print("Usage: python email_service.py <test_email>")
        print("Example: python email_service.py your@email.com")
        sys.exit(1)

    test_email = sys.argv[1]
    result = send_test_email(test_email)

    if result:
        print(f"✅ Test email sent successfully to {test_email}")
        print(f"Response: {result}")
    else:
        print(f"❌ Failed to send test email to {test_email}")
        print("Check logs for details")
        sys.exit(1)
