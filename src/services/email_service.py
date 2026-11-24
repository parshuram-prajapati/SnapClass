import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Tuple
from src.database.config import get_secret

logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    """Checks whether SMTP email credentials have been configured."""
    user = get_secret("SMTP_USER", get_secret("SMTP_EMAIL", ""))
    password = get_secret("SMTP_PASSWORD", get_secret("SMTP_PASS", ""))
    return bool(user and password)


def send_password_reset_email(to_email: str, reset_token: str, recipient_name: str = "Teacher") -> Tuple[bool, str]:
    """
    Sends an automated, branded HTML password reset email to the recipient.
    Reads configuration from .streamlit/secrets.toml or environment variables:
    - SMTP_HOST (default: smtp.gmail.com)
    - SMTP_PORT (default: 587)
    - SMTP_USER / SMTP_EMAIL
    - SMTP_PASSWORD / SMTP_PASS
    - SMTP_SENDER_NAME (default: SnapClass AI)
    - APP_BASE_URL (default: http://localhost:8501)
    
    Returns: (success: bool, message: str)
    """
    smtp_host = get_secret("SMTP_HOST", get_secret("SMTP_SERVER", "smtp.gmail.com"))
    smtp_port_raw = get_secret("SMTP_PORT", "587")
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 587

    smtp_user = get_secret("SMTP_USER", get_secret("SMTP_EMAIL", "")).strip()
    smtp_pass = get_secret("SMTP_PASSWORD", get_secret("SMTP_PASS", "")).strip()
    app_base_url = get_secret("APP_BASE_URL", "http://localhost:8501").rstrip("/")
    sender_name = get_secret("SMTP_SENDER_NAME", "SnapClass AI")

    if not smtp_user or not smtp_pass:
        return False, "SMTP credentials are not configured in .streamlit/secrets.toml."

    reset_url = f"{app_base_url}/?reset_token={reset_token}"

    subject = "SnapClass AI - Password Reset Request"

    # Plain text version
    text_content = f"""Hello {recipient_name},

We received a request to reset the password for your SnapClass AI account.

To reset your password, visit the following link (valid for 15 minutes):
{reset_url}

If you did not request this password reset, please ignore this email. Your account remains secure.

Best regards,
The SnapClass AI Team
"""

    # Modern, responsive HTML email version matching SnapClass styling
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Reset Your Password - SnapClass AI</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F4F6FB; margin: 0; padding: 30px;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(88, 101, 242, 0.15);">
    <!-- Header -->
    <tr>
      <td style="background-color: #5865F2; padding: 35px 30px; text-align: center;">
        <h1 style="color: #ffffff; margin: 0; font-size: 28px; letter-spacing: 1px; font-weight: 800;">SNAPCLASS AI</h1>
        <p style="color: #E0E3FF; margin: 6px 0 0; font-size: 14px;">Smart Attendance Management System</p>
      </td>
    </tr>
    <!-- Body -->
    <tr>
      <td style="padding: 40px 35px;">
        <h2 style="color: #1F2937; margin: 0 0 16px; font-size: 20px;">Password Reset Request</h2>
        <p style="color: #4B5563; font-size: 15px; line-height: 1.6; margin: 0 0 24px;">
          Hi <strong>{recipient_name}</strong>,<br><br>
          We received a request to reset your password. Click the button below to choose a new password. This link is single-use and will expire in <strong>15 minutes</strong>.
        </p>
        <div style="text-align: center; margin: 30px 0;">
          <a href="{reset_url}" style="background-color: #EB459E; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 50px; font-weight: 700; font-size: 16px; display: inline-block; box-shadow: 0 4px 12px rgba(235, 69, 158, 0.3);">
            Reset My Password
          </a>
        </div>
        <p style="color: #6B7280; font-size: 13px; line-height: 1.5; margin: 25px 0 0;">
          If the button above does not work, copy and paste this link into your browser:<br>
          <a href="{reset_url}" style="color: #5865F2; word-break: break-all;">{reset_url}</a>
        </p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 30px 0;">
        <p style="color: #9CA3AF; font-size: 12px; margin: 0; line-height: 1.4;">
          If you didn't request a password reset, you can safely ignore this email. No changes will be made to your account.
        </p>
      </td>
    </tr>
    <!-- Footer -->
    <tr>
      <td style="background-color: #F9FAFB; padding: 20px 35px; text-align: center; color: #9CA3AF; font-size: 12px;">
        &copy; SnapClass AI &bull; Smart AI-Powered Attendance
      </td>
    </tr>
  </table>
</body>
</html>
"""

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{smtp_user}>"
    message["To"] = to_email

    part1 = MIMEText(text_content, "plain")
    part2 = MIMEText(html_content, "html")
    message.attach(part1)
    message.attach(part2)

    try:
        if smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=15) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, to_email, message.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, to_email, message.as_string())

        return True, f"Password reset email has been sent successfully to {to_email}."
    except Exception as e:
        logger.error(f"Failed to send email via SMTP: {e}")
        return False, f"Could not deliver email: {str(e)}"
