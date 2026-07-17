"""Celery tasks for sending email notifications.

Two tasks are exposed:

* :func:`send_email` - a low-level task that sends a plain-text (and
  optional HTML) email via SMTP.
* :func:`send_release_notification` - a higher-level task that renders a
  release notification email (including a download link and expiry) and
  delegates to :func:`send_email`.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="send_email")
def send_email(
    to_email: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> dict:
    """Send an email via SMTP.

    SMTP connection details are read from :mod:`app.config.settings`.

    Args:
        to_email: The recipient email address.
        subject: The email subject.
        body: The plain-text body.
        html: Optional HTML body. When provided the email is sent as a
            ``multipart/alternative`` message.

    Returns:
        A dict with ``status`` ("ok" or "error") and, on error, an
        ``error`` field describing the failure.
    """
    from_addr = settings.SMTP_FROM

    if html:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(body, "plain", "utf-8"))
        message.attach(MIMEText(html, "html", "utf-8"))
    else:
        message = MIMEMultipart("mixed")
        message.attach(MIMEText(body, "plain", "utf-8"))

    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to_email

    try:
        # Use SMTP_SSL when the port indicates an implicit-TLS port (465),
        # otherwise use STARTTLS on the standard port.
        if settings.SMTP_PORT == 465:
            smtp_cls = smtplib.SMTP_SSL
            server = smtp_cls(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
            try:
                server.starttls()
            except smtplib.SMTPException:
                # Server may not support STARTTLS; continue unencrypted.
                logger.debug("STARTTLS not supported by %s, continuing", settings.SMTP_HOST)

        try:
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(from_addr, [to_email], message.as_string())
        finally:
            server.quit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send email to %s: %s", to_email, exc)
        return {"status": "error", "error": str(exc)}

    return {"status": "ok"}


@celery_app.task(name="send_release_notification")
def send_release_notification(
    to_email: str,
    recipient_name: str,
    project_name: str,
    version_number: str,
    download_link: str,
    expiry_hours: int,
) -> dict:
    """Send a release notification email with a download link.

    Args:
        to_email: The recipient email address.
        recipient_name: The recipient's display name.
        project_name: The project name.
        version_number: The version number being released.
        download_link: The presigned download URL.
        expiry_hours: Number of hours until the link expires.

    Returns:
        The result dict from :func:`send_email`.
    """
    greeting = f"尊敬的 {recipient_name}，您好！" if recipient_name else "您好！"

    plain_body = (
        f"{greeting}\n\n"
        f"项目「{project_name}」的版本 {version_number} 已完成评审并正式释放。\n\n"
        f"下载链接（请在 {expiry_hours} 小时内下载，逾期失效）：\n"
        f"{download_link}\n\n"
        f"如链接已过期，请联系项目管理员重新生成。\n\n"
        f"—— BMS SOX 算法软件交付管理系统"
    )

    html_body = (
        f"<p>{greeting}</p>"
        f"<p>项目「<b>{project_name}</b>」的版本 "
        f"<b>{version_number}</b> 已完成评审并正式释放。</p>"
        f"<p>下载链接（请在 <b>{expiry_hours} 小时</b>内下载，逾期失效）：</p>"
        f"<p><a href=\"{download_link}\">{download_link}</a></p>"
        f"<p style=\"color:#888;\">如链接已过期，请联系项目管理员重新生成。</p>"
        f"<hr><p style=\"color:#888;font-size:12px;\">BMS SOX 算法软件交付管理系统</p>"
    )

    subject = f"【版本释放通知】{project_name} - {version_number}"

    # Delegate to the low-level send_email task (synchronous call so the
    # whole send happens within this worker task).
    return send_email(
        to_email=to_email,
        subject=subject,
        body=plain_body,
        html=html_body,
    )
