"""
Optional welcome email for self-serve signup.

Sends via SendGrid when SENDGRID_API_KEY is set; otherwise no-op (or log).
"""

import logging
import os

logger = logging.getLogger(__name__)


def send_welcome_email(
    to_email: str,
    org_name: str,
    api_key_prefix: str,
) -> bool:
    """Send a welcome email after signup. Returns True if sent, False if skipped or failed.

    Requires SENDGRID_API_KEY. No payment/transactional dependency for MVP.
    """
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key or not to_email or "@" not in to_email:
        if to_email and "@" in to_email:
            logger.info(
                "Welcome email skipped (no SENDGRID_API_KEY)",
                extra={"to": to_email, "org_name": org_name},
            )
        return False

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
    except ImportError:
        logger.warning(
            "Welcome email skipped (sendgrid not installed)",
            extra={"to": to_email},
        )
        return False

    message = Mail(
        from_email=os.environ.get("ASAHI_FROM_EMAIL", "noreply@asahi.example.com"),
        to_emails=to_email,
        subject="Welcome to Asahi",
        plain_text_content=(
            f"Your organisation \"{org_name}\" is set up.\n\n"
            f"Your API key prefix: {api_key_prefix}\n"
            "Store the full key securely; it was shown only once at signup.\n\n"
            "Docs: see your deployment's /docs or API_CONTRACT.md."
        ),
    )
    try:
        SendGridAPIClient(api_key).send(message)
        logger.info("Welcome email sent", extra={"to": to_email, "org_name": org_name})
        return True
    except Exception as e:
        logger.warning(
            "Welcome email failed",
            extra={"to": to_email, "error": str(e)},
        )
        return False
