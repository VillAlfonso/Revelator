"""Email delivery utilities for verification, password reset, and sign-in codes."""

import smtplib
import logging
import ssl
from html import escape
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL,
    API_URL, FRONTEND_URL, APP_NAME,
)
from .operations import record_event

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email and record delivery failures without logging message contents."""
    if not _smtp_configured():
        record_event(
            "email_delivery_failure",
            "SMTP email delivery failed (not configured)",
            severity="error",
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL or SMTP_USER
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(
                SMTP_HOST,
                SMTP_PORT,
                timeout=15,
                context=ssl.create_default_context(),
            )
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
        with server:
            if SMTP_PORT != 465:
                server.starttls(context=ssl.create_default_context())
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("SMTP delivery failed (%s)", type(exc).__name__)
        record_event(
            "email_delivery_failure",
            f"SMTP email delivery failed ({type(exc).__name__})",
            severity="error",
        )
        return False


def _verification_html(link: str) -> str:
    safe_link = escape(link, quote=True)
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#07120b;font-family:Arial,Helvetica,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#07120b;padding:32px 0;">
      <tr><td align="center">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#0c1a12;border:1px solid #173a25;border-radius:6px;padding:36px;">
          <tr><td align="center" style="padding-bottom:20px;">
            <h1 style="margin:0;color:#00ff66;letter-spacing:6px;font-size:26px;">{APP_NAME.upper()}</h1>
            <p style="margin:8px 0 0;color:#6dba85;font-size:11px;letter-spacing:3px;">
              [ CONFIRM YOUR EMAIL ]
            </p>
          </td></tr>
          <tr><td style="color:#cfe9d8;font-size:14px;line-height:1.6;padding:8px 0 24px;">
            Thanks for registering. To activate your account, confirm this email
            address by clicking the button below. This link expires in 24 hours.
          </td></tr>
          <tr><td align="center" style="padding-bottom:28px;">
            <a href="{safe_link}"
               style="display:inline-block;background:#00ff66;color:#04140a;
                      text-decoration:none;font-weight:bold;font-size:14px;
                      padding:14px 32px;border-radius:4px;letter-spacing:1px;">
              CONFIRM EMAIL
            </a>
          </td></tr>
          <tr><td style="color:#5f8a6e;font-size:12px;line-height:1.6;border-top:1px solid #173a25;padding-top:18px;">
            If the button doesn't work, paste this link into your browser:<br>
            <span style="color:#86efac;word-break:break-all;">{safe_link}</span>
          </td></tr>
          <tr><td style="color:#3f6e4a;font-size:11px;padding-top:20px;">
            If you didn't create a {APP_NAME} account, you can safely ignore this email.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def send_verification_email(to_email: str, token: str) -> bool:
    """Send an email verification link."""
    link = f"{API_URL}/api/auth/verify-email?token={quote(token, safe='')}"
    subject = f"Confirm your {APP_NAME} account"
    return send_email(to_email, subject, _verification_html(link))


def _reset_html(link: str) -> str:
    safe_link = escape(link, quote=True)
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#07120b;font-family:Arial,Helvetica,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#07120b;padding:32px 0;">
      <tr><td align="center">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#0c1a12;border:1px solid #173a25;border-radius:6px;padding:36px;">
          <tr><td align="center" style="padding-bottom:20px;">
            <h1 style="margin:0;color:#00ff66;letter-spacing:6px;font-size:26px;">{APP_NAME.upper()}</h1>
            <p style="margin:8px 0 0;color:#6dba85;font-size:11px;letter-spacing:3px;">
              [ RESET YOUR PASSWORD ]
            </p>
          </td></tr>
          <tr><td style="color:#cfe9d8;font-size:14px;line-height:1.6;padding:8px 0 24px;">
            We received a request to reset your password. Click the button below to
            choose a new one. This link expires in 1 hour.
          </td></tr>
          <tr><td align="center" style="padding-bottom:28px;">
            <a href="{safe_link}"
               style="display:inline-block;background:#00ff66;color:#04140a;
                      text-decoration:none;font-weight:bold;font-size:14px;
                      padding:14px 32px;border-radius:4px;letter-spacing:1px;">
              RESET PASSWORD
            </a>
          </td></tr>
          <tr><td style="color:#5f8a6e;font-size:12px;line-height:1.6;border-top:1px solid #173a25;padding-top:18px;">
            If the button doesn't work, paste this link into your browser:<br>
            <span style="color:#86efac;word-break:break-all;">{safe_link}</span>
          </td></tr>
          <tr><td style="color:#3f6e4a;font-size:11px;padding-top:20px;">
            If you didn't request a password reset, you can safely ignore this email -
            your password won't change.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def send_reset_email(to_email: str, token: str) -> bool:
    """Send a password reset link."""
    link = f"{FRONTEND_URL}/reset-password?token={quote(token, safe='')}"
    subject = f"Reset your {APP_NAME} password"
    return send_email(to_email, subject, _reset_html(link))


def _twofa_html(code: str, ttl_minutes: int) -> str:
    spaced = " ".join(list(code))  # render the digits with a little air
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#07120b;font-family:Arial,Helvetica,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#07120b;padding:32px 0;">
      <tr><td align="center">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#0c1a12;border:1px solid #173a25;border-radius:6px;padding:36px;">
          <tr><td align="center" style="padding-bottom:20px;">
            <h1 style="margin:0;color:#00ff66;letter-spacing:6px;font-size:26px;">{APP_NAME.upper()}</h1>
            <p style="margin:8px 0 0;color:#6dba85;font-size:11px;letter-spacing:3px;">
              [ SIGN-IN VERIFICATION ]
            </p>
          </td></tr>
          <tr><td style="color:#cfe9d8;font-size:14px;line-height:1.6;padding:8px 0 20px;">
            Someone is signing in to your {APP_NAME} account. Enter this code to
            finish signing in. It expires in {ttl_minutes} minutes.
          </td></tr>
          <tr><td align="center" style="padding-bottom:24px;">
            <div style="display:inline-block;background:#04140a;border:1px solid #00ff66;
                        border-radius:6px;padding:16px 28px;color:#00ff66;font-weight:bold;
                        font-size:32px;letter-spacing:12px;font-family:'Courier New',monospace;">
              {spaced}
            </div>
          </td></tr>
          <tr><td style="color:#3f6e4a;font-size:12px;line-height:1.6;border-top:1px solid #173a25;padding-top:18px;">
            If you didn't try to sign in, someone may have your password. Change it
            as soon as you can - this code alone won't let them in.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def send_2fa_code_email(to_email: str, code: str, ttl_minutes: int = 10) -> bool:
    """Send the 2FA login code.

    Returns True if the email was actually sent. The caller uses this to decide
    whether it can require the code (never lock a user out when mail is down)."""
    subject = f"Your {APP_NAME} sign-in code"
    return send_email(to_email, subject, _twofa_html(code, ttl_minutes))


def send_registration_code_email(to_email: str, code: str) -> bool:
    return send_email(to_email, f"Your {APP_NAME} registration code",
        f"<h2>Verify your email</h2><p>Enter this code to create your {escape(APP_NAME)} account:</p>"
        f"<p style='font-size:32px;letter-spacing:6px'><strong>{escape(code)}</strong></p>"
        "<p>This code expires in 10 minutes. Do not share it.</p>"
        "<p>If you did not register, you can ignore this email.</p>")
