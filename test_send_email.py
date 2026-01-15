#!/usr/bin/env python3
"""
Test script to send a program PDF via email
Usage: python3 test_send_email.py
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from services.email_service import send_program_email
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    """Send test program email"""

    # Email configuration
    to_email = "ambaka.legreg@gmail.com"  # Your Resend account email
    user_name = "Greg"
    program_id = 67
    pdf_path = "programs/program_1c7bd681-1cca-4042-9f5b-6085e725d953_67.pdf"

    print(f"\n{'='*80}")
    print("📧 Sending Program Email Test")
    print(f"{'='*80}")
    print(f"To: {to_email}")
    print(f"Name: {user_name}")
    print(f"Program ID: {program_id}")
    print(f"PDF Path: {pdf_path}")
    print(f"{'='*80}\n")

    # Check if PDF exists
    if not Path(pdf_path).exists():
        print(f"❌ Error: PDF file not found at {pdf_path}")
        print("Please check the file path and try again.")
        sys.exit(1)

    # Check if Resend API key is configured
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print("❌ Error: RESEND_API_KEY environment variable not set")
        print("Please add RESEND_API_KEY to your .env file")
        sys.exit(1)

    # Check if from email is configured
    from_email = os.getenv("RESEND_FROM_EMAIL")
    if not from_email:
        print("❌ Error: RESEND_FROM_EMAIL environment variable not set")
        print("Please add RESEND_FROM_EMAIL to your .env file with a verified domain")
        print("Example: RESEND_FROM_EMAIL=noreply@yourdomain.com")
        print("\nTo verify a domain, visit: https://resend.com/domains")
        sys.exit(1)

    print(f"From: {from_email}")
    print("Sending email...")

    # Send the email
    result = send_program_email(
        to_email=to_email,
        user_name=user_name,
        program_id=program_id,
        pdf_path=pdf_path
    )

    if result:
        print(f"\n✅ Email sent successfully!")
        print(f"Response: {result}")
        print(f"\n📬 Check your inbox at {to_email}")
        print("(Don't forget to check your spam folder!)")
    else:
        print(f"\n❌ Failed to send email")
        print("Check the logs above for error details")
        sys.exit(1)

if __name__ == "__main__":
    main()
