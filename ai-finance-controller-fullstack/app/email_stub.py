"""
IMPORTANT — read before assuming this sends real email:
This project has no SMTP server configured (no mail credentials, no
outbound mail service). Rather than fake success silently, this module
logs the "email" to the console/log file AND returns the reset link
directly in the API response so the forgot-password flow is genuinely
testable end-to-end without external infrastructure.

To make this send real email in production: replace send_reset_email()
with a real call to an email provider (SMTP, SendGrid, SES, etc.) using
credentials from environment variables, and stop returning the raw link
in the API response (that's only safe for this local/demo context).
"""
import logging

logger = logging.getLogger('ai_finance_controller.email')


def send_reset_email(to_email: str, reset_url: str) -> None:
    logger.info('[SIMULATED EMAIL] Password reset link for %s: %s', to_email, reset_url)
    print(f'[SIMULATED EMAIL] To: {to_email}\nSubject: Reset your AI Finance Controller password\nLink: {reset_url}\n')
