#!/usr/bin/env python3
"""
CTF Credentials Distribution Script - All-in-One

This script handles sending CTF team and user credentials via email.
Supports Gmail, SendGrid, and custom SMTP servers.

USAGE:
    python3 send_credentials.py <credentials_csv> [options]

OPTIONS:
    --dry-run              Preview emails without sending
    --provider gmail       Use Gmail (requires EMAIL_FROM, EMAIL_PASSWORD env vars)
    --provider sendgrid    Use SendGrid (requires SENDGRID_API_KEY, EMAIL_FROM env vars)
    --provider smtp        Use custom SMTP (default)
    --platform-url URL     Set platform URL (default: http://localhost/chat)
    --support-email EMAIL  Set support email (default: EMAIL_FROM)
    --delay SECONDS        Set delay between emails (default: 0.5)

EXAMPLES:

1. Preview (dry-run):
    python3 send_credentials.py credentials.csv --dry-run

2. Gmail:
    export EMAIL_FROM=contest@gmail.com
    export EMAIL_PASSWORD=your-app-password
    python3 send_credentials.py credentials.csv --provider gmail

3. SendGrid:
    export SENDGRID_API_KEY=sg_xxxxx
    export EMAIL_FROM=noreply@domain.com
    python3 send_credentials.py credentials.csv --provider sendgrid

4. SMTP:
    export SMTP_HOST=mail.domain.com
    export SMTP_PORT=587
    export EMAIL_FROM=admin@domain.com
    export EMAIL_PASSWORD=your-password
    python3 send_credentials.py credentials.csv --provider smtp

CONFIGURATION:

Environment Variables:
    EMAIL_PROVIDER      'gmail', 'sendgrid', or 'smtp' (default: smtp)
    EMAIL_FROM          Sender email address (REQUIRED)
    EMAIL_PASSWORD      Password for Gmail/SMTP
    SENDGRID_API_KEY    API key for SendGrid
    SMTP_HOST           SMTP server hostname (default: smtp.gmail.com)
    SMTP_PORT           SMTP port (default: 587)
    SMTP_USE_TLS        Use TLS for SMTP (default: true)
    PLATFORM_URL        CTF platform URL
    SUPPORT_EMAIL       Support contact email
    EMAIL_DELAY         Delay between emails (default: 0.5)

GMAIL SETUP:
    1. Go to https://myaccount.google.com/apppasswords
    2. Select Mail and your device
    3. Copy the 16-character password
    4. Use it in EMAIL_PASSWORD

SENDGRID SETUP:
    1. Create account at https://sendgrid.com
    2. Create API key: Settings > API Keys
    3. Verify sender: Settings > Sender Authentication
    4. Use API key in SENDGRID_API_KEY

SMTP SETUP:
    1. Use your organization's mail server
    2. Example: mail.university.edu:587
    3. Set EMAIL_PASSWORD to your SMTP password

TROUBLESHOOTING:
    Connection refused:
        - Check SMTP_HOST and SMTP_PORT
        - Try port 25, 465, or 587

    Authentication failed:
        - Gmail: Use App Password, not regular password
        - Verify credentials are correct
        - Check firewall settings

    SendGrid issues:
        - Verify email in Sender Authentication
        - Check API key is correct

NOTES:
    - Use --dry-run first to preview emails
    - Never commit credentials to git
    - Use environment variables, not hardcoding
    - Adjust --delay for rate limiting
"""

import csv
import os
import sys
import time
import argparse
from typing import Optional, List, Dict

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import requests
except ImportError:
    print("❌ requests library not found. Install with: pip install requests")
    sys.exit(1)

# Load environment variables from .env file
if load_dotenv:
    load_dotenv()


# ============================================================================
# EMAIL TEMPLATE
# ============================================================================
EMAIL_TEMPLATE = """
Hello {user_name},

Welcome to the CTF Challenge! Here are your login credentials:

──────────────────────────────────────────────────────
TEAM LOGIN
──────────────────────────────────────────────────────
Team Name:     {team_name}
Team Password: {team_password}

INDIVIDUAL LOGIN
──────────────────────────────────────────────────────
Username: {username}
Password: {user_password}

──────────────────────────────────────────────────────

🔗 Platform URL: {platform_url}

📝 Instructions:
1. Go to the platform URL above
2. Log in with your username and password
3. Join your team using the team name and password
4. Start solving challenges!

⚠️  Security Note:
- Do NOT share your credentials with others
- Change your password after first login
- Report any suspicious activity to the admin

If you have any issues, please contact: {support_email}

Good luck! 🚀
""".strip()


# ============================================================================
# CONFIGURATION & UTILITIES
# ============================================================================
class EmailConfig:
    """Email configuration manager."""

    def __init__(self, provider: str = None, args: argparse.Namespace = None):
        self.provider = (provider or os.getenv("EMAIL_PROVIDER", "smtp")).lower()
        self.email_from = os.getenv("EMAIL_FROM")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.reply_to = os.getenv("EMAIL_REPLY_TO", self.email_from)
        self.platform_url = (
            args.platform_url
            if args and args.platform_url
            else os.getenv("PLATFORM_URL", "http://localhost/chat")
        )
        self.support_email = (
            args.support_email
            if args and args.support_email
            else os.getenv("SUPPORT_EMAIL", self.email_from or "admin@example.com")
        )
        self.email_delay = (
            args.delay
            if args and args.delay
            else float(os.getenv("EMAIL_DELAY", "0.5"))
        )

    def validate(self) -> bool:
        """Validate configuration."""
        if not self.email_from:
            print("❌ EMAIL_FROM environment variable not set")
            return False

        if self.provider == "gmail":
            if not self.email_password:
                print("❌ EMAIL_PASSWORD required for Gmail")
                print("   Get from: https://myaccount.google.com/apppasswords")
                return False
        elif self.provider == "sendgrid":
            if not self.sendgrid_api_key:
                print("❌ SENDGRID_API_KEY environment variable not set")
                print("   Get from: https://app.sendgrid.com/settings/api_keys")
                return False
        elif self.provider == "smtp":
            if not self.email_password:
                print("❌ EMAIL_PASSWORD required for SMTP")
                return False
        else:
            print(f"❌ Unknown EMAIL_PROVIDER: {self.provider}")
            print("   Supported: gmail, sendgrid, smtp")
            return False

        return True

    def show(self):
        """Display configuration."""
        print(f"📧 Email Provider: {self.provider.upper()}")
        print(f"📬 From: {self.email_from}")
        if self.provider == "smtp":
            print(f"🔗 SMTP: {self.smtp_host}:{self.smtp_port}")
        print(f"🔗 Platform URL: {self.platform_url}\n")


# ============================================================================
# EMAIL SENDING
# ============================================================================
def send_via_smtp(config: EmailConfig, to_email: str, subject: str, body: str) -> bool:
    """Send email via SMTP."""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.email_from
        msg["To"] = to_email
        if config.reply_to:
            msg["Reply-To"] = config.reply_to

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as server:
            if config.smtp_use_tls:
                server.starttls()
            server.login(config.email_from, config.email_password)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"   ❌ SMTP Error: {e}")
        return False


def send_via_sendgrid(
    config: EmailConfig, to_email: str, subject: str, body: str
) -> bool:
    """Send email via SendGrid API."""
    try:
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {config.sendgrid_api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": config.email_from},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }
        if config.reply_to:
            data["reply_to"] = {"email": config.reply_to}

        response = requests.post(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"   ❌ SendGrid Error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def send_email(config: EmailConfig, to_email: str, subject: str, body: str) -> bool:
    """Send email using configured provider."""
    if config.provider in ("smtp", "gmail"):
        return send_via_smtp(config, to_email, subject, body)
    elif config.provider == "sendgrid":
        return send_via_sendgrid(config, to_email, subject, body)
    return False


# ============================================================================
# CSV & DATA PROCESSING
# ============================================================================
def read_credentials_csv(filename: str) -> List[Dict]:
    """Read credentials CSV file."""
    try:
        rows = []
        with open(filename, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        print(f"✅ Read {len(rows)} credentials from {filename}\n")
        return rows
    except FileNotFoundError:
        print(f"❌ File not found: {filename}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        sys.exit(1)


def extract_name_from_email(email: str) -> str:
    """Extract name from email (e.g., john.doe@example.com -> John Doe)."""
    local_part = email.split("@")[0]
    name = local_part.replace(".", " ").replace("-", " ")
    return " ".join(word.capitalize() for word in name.split())


def group_credentials_by_email(credentials: List[Dict]) -> Dict[str, List[Dict]]:
    """Group credentials by email to avoid duplicate emails."""
    grouped = {}
    for cred in credentials:
        email = cred.get("Email", "").strip()
        if not email:
            print(f"⚠️  Skipping row with missing email: {cred}")
            continue
        if email not in grouped:
            grouped[email] = []
        grouped[email].append(cred)
    return grouped


# ============================================================================
# MAIN
# ============================================================================
def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Send CTF credentials via email",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("credentials_csv", help="CSV file with credentials")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview emails without sending"
    )
    parser.add_argument(
        "--provider",
        choices=["gmail", "sendgrid", "smtp"],
        help="Email provider (default: smtp)",
    )
    parser.add_argument("--platform-url", help="Platform URL for participants")
    parser.add_argument("--support-email", help="Support email address")
    parser.add_argument("--delay", type=float, help="Delay between emails (seconds)")

    args = parser.parse_args()

    # Setup config
    config = EmailConfig(provider=args.provider, args=args)
    dry_run = args.dry_run

    if not dry_run and not config.validate():
        print("\n📋 Configuration Guide:")
        print(f"   EMAIL_PROVIDER: {config.provider}")
        print(f"   EMAIL_FROM: {config.email_from}")
        print("\n💡 For testing, use: python3 send_credentials.py <file> --dry-run")
        sys.exit(1)

    config.show()

    if dry_run:
        print("🔍 DRY RUN MODE - No emails will be sent\n")

    # Read credentials
    credentials = read_credentials_csv(args.credentials_csv)

    if not credentials:
        print("❌ No credentials found in CSV")
        sys.exit(1)

    # Group by email
    grouped = group_credentials_by_email(credentials)

    if not grouped:
        print("❌ No valid emails found in CSV")
        sys.exit(1)

    print(f"📨 Processing {len(grouped)} emails...\n")

    subject = "CTF Challenge Credentials"
    successful = 0
    failed = 0

    # Send emails
    for idx, (email, email_creds) in enumerate(grouped.items(), 1):
        user_name = extract_name_from_email(email)
        cred = email_creds[0]  # Use first credential for this email

        body = EMAIL_TEMPLATE.format(
            user_name=user_name,
            team_name=cred.get("Team Name", "N/A"),
            team_password=cred.get("Team Password", "N/A"),
            username=cred.get("Username", "N/A"),
            user_password=cred.get("User Password", "N/A"),
            platform_url=config.platform_url,
            support_email=config.support_email,
        )

        if dry_run:
            print(f"[{idx}] 📧 TO: {email}")
            print(f"    👤 Name: {user_name}")
            print(f"    📝 Subject: {subject}")
            print(f"    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(body)
            print(f"    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            successful += 1
        else:
            print(f"[{idx}] 📧 Sending to {email}...", end=" ", flush=True)
            if send_email(config, email, subject, body):
                print("✅")
                successful += 1
            else:
                print("❌")
                failed += 1

            if idx < len(grouped):
                time.sleep(config.email_delay)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"📊 Summary:")
    print(f"   Total recipients: {len(grouped)}")
    print(f"   ✅ Successful: {successful}")
    if not dry_run and failed > 0:
        print(f"   ❌ Failed: {failed}")
    if dry_run:
        print(f"   (Dry run - no emails sent)")
    print(f"{'=' * 60}")

    if not dry_run and failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
