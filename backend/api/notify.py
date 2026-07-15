"""
Email notification endpoint for BOM approval workflow.
Uses smtplib with SMTP settings from config, or logs to console when
SMTP is not configured (development mode).
"""
from __future__ import annotations
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

from config import get_settings

router = APIRouter(prefix="/api/notify", tags=["notify"])
log = logging.getLogger(__name__)


class EmailRequest(BaseModel):
    to: List[str]
    subject: str
    body: str
    bom_id: Optional[str] = None


@router.post("/email")
async def send_email(req: EmailRequest):
    """Send an email notification for BOM approval events."""
    settings = get_settings()

    # Build the full HTML + plain-text email
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    plain_body = f"{req.body}\n\n---\nSent by IT Contracting Dashboard · {timestamp}"

    html_body = f"""
<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#1F2937;line-height:1.6">
<div style="max-width:640px;margin:0 auto;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden">
  <div style="background:#D04A02;padding:16px 24px">
    <h2 style="color:white;margin:0;font-size:18px">IT Contracting Dashboard</h2>
    <p style="color:#FFD4B3;margin:4px 0 0;font-size:13px">BOM Approval Notification</p>
  </div>
  <div style="padding:24px">
    <h3 style="color:#1F2937;margin-top:0">{req.subject}</h3>
    <pre style="background:#F9FAFB;padding:16px;border-radius:6px;border:1px solid #E5E7EB;font-size:13px;white-space:pre-wrap;font-family:inherit">{req.body}</pre>
    <p style="font-size:12px;color:#9CA3AF;margin-top:24px;border-top:1px solid #F3F4F6;padding-top:12px">
      Sent automatically by IT Contracting Dashboard &middot; {timestamp}
      {f'<br>BOM ID: {req.bom_id}' if req.bom_id else ''}
    </p>
  </div>
</div>
</body></html>
"""

    smtp_host = getattr(settings, "smtp_host", None)
    smtp_port = getattr(settings, "smtp_port", 587)
    smtp_user = getattr(settings, "smtp_user", None)
    smtp_pass = getattr(settings, "smtp_password", None)
    sender    = getattr(settings, "smtp_from", "noreply@it-contracting-dashboard.com")

    if not smtp_host:
        # Development mode — log to console and return success
        log.info("=== EMAIL NOTIFICATION (no SMTP configured) ===")
        log.info("To: %s", ", ".join(req.to))
        log.info("Subject: %s", req.subject)
        log.info("Body:\n%s", req.body)
        log.info("==============================================")
        return {"status": "logged", "message": "SMTP not configured — email logged to console"}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = req.subject
        msg["From"]    = sender
        msg["To"]      = ", ".join(req.to)

        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body,  "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.ehlo()
            if smtp_port != 25:
                smtp.starttls()
            if smtp_user and smtp_pass:
                smtp.login(smtp_user, smtp_pass)
            smtp.sendmail(sender, req.to, msg.as_string())

        log.info("Email sent to %s: %s", req.to, req.subject)
        return {"status": "sent", "recipients": req.to}

    except Exception as exc:
        log.error("Failed to send email: %s", exc)
        # Don't raise — email is best-effort, approval was already recorded
        return {"status": "failed", "error": str(exc)}
