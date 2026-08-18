"""
Best-effort email delivery, layered on top of the existing in-app
notifications rather than replacing them. Controlled by env vars:

  EMAIL_NOTIFICATIONS_ENABLED=true
  SMTP_HOST=smtp.example.com
  SMTP_PORT=587
  SMTP_USER=...
  SMTP_PASSWORD=...
  SMTP_FROM_EMAIL=noreply@example.com

Without real credentials, this just logs what it would have sent instead
of failing. Send errors are caught and logged too, never raised -- a
broken mail server should never break the request action that triggered it.
"""
import os
import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("expense_tracker.email")


def _is_configured() -> bool:
    if os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() != "true":
        return False
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL"))


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not _is_configured():
        logger.info("[email disabled] Would send to %s: %s", to_email, subject)
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = os.getenv("SMTP_FROM_EMAIL")
        msg["To"] = to_email
        msg.set_content(body)

        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASSWORD")

        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False
