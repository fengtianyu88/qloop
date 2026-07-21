"""邮件发送服务。

支持 SMTP 发送,可在系统设置中开关。
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy import select

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """发送邮件,返回是否成功。

    会先检查系统设置中的 email_notification_enabled 开关,
    再检查 SMTP 主机是否已正确配置。
    """
    # 检查系统设置中邮件总开关(延迟导入避免循环依赖)
    from app.database import async_session_factory
    from app.models.system_settings import SystemSettings

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(SystemSettings).limit(1))
            sys_settings = result.scalar_one_or_none()
            if sys_settings and not getattr(
                sys_settings, "email_notification_enabled", False
            ):
                logger.info("邮件通知未启用,跳过发送")
                return False
    except Exception as exc:
        # 查询系统设置失败时不阻塞,继续按 config 中的 SMTP 配置发送
        logger.warning("查询邮件开关失败,继续尝试发送: %s", exc)

    # 检查 SMTP 是否已配置(默认 localhost 视为未配置)
    if not settings.SMTP_ENABLED:
        logger.info("SMTP_ENABLED=False,跳过发送邮件")
        return False

    if not settings.SMTP_HOST or settings.SMTP_HOST == "localhost":
        logger.warning("SMTP 未配置,跳过发送邮件")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # 根据 SMTP_USE_TLS 选择 SSL 或普通 SMTP
        if settings.SMTP_USE_TLS:
            server = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=30
            )
        else:
            server = smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=30
            )

        try:
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())
        finally:
            server.quit()

        logger.info("邮件发送成功: %s - %s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("邮件发送失败: %s", exc)
        return False


# 通知模板
NOTIFICATION_TEMPLATES = {
    "review_triggered": {
        "subject": "【QLoop】{review_type}评审已触发 - {release_number}",
        "body": (
            "<h3>评审已触发</h3>"
            "<p>版本:<strong>{release_number}</strong></p>"
            "<p>评审类型:{review_type}</p>"
            "<p>触发人:{triggered_by}</p>"
            "<p>请前往 QLoop 查看评审进度</p>"
        ),
    },
    "review_completed": {
        "subject": "【QLoop】{review_type}评审完成 - {release_number}",
        "body": (
            "<h3>评审完成</h3>"
            "<p>版本:<strong>{release_number}</strong></p>"
            "<p>评审类型:{review_type}</p>"
            "<p>结果:<strong>{result}</strong></p>"
            "<p>总分:{total_score}</p>"
            "<p>请前往 QLoop 查看详情</p>"
        ),
    },
    "release_confirmed": {
        "subject": "【QLoop】版本已释放 - {release_number}",
        "body": (
            "<h3>版本已释放</h3>"
            "<p>版本:<strong>{release_number}</strong></p>"
            "<p>确认人:{confirmed_by}</p>"
            "<p>下载链接已生成,请前往 QLoop 获取</p>"
        ),
    },
    "task_assigned": {
        "subject": "【QLoop】您有新任务 - {release_number}",
        "body": (
            "<h3>新任务通知</h3>"
            "<p>版本:<strong>{release_number}</strong></p>"
            "<p>当前阶段:{stage}</p>"
            "<p>请前往 QLoop 处理</p>"
        ),
    },
}


async def notify_user(email: str, template_key: str, context: dict) -> bool:
    """基于模板发送邮件通知。

    Args:
        email: 收件人邮箱。
        template_key: NOTIFICATION_TEMPLATES 中的模板键。
        context: 模板变量上下文。

    Returns:
        是否发送成功。
    """
    template = NOTIFICATION_TEMPLATES.get(template_key)
    if not template:
        logger.warning("未知邮件模板: %s", template_key)
        return False
    try:
        subject = template["subject"].format(**context)
        body = template["body"].format(**context)
    except KeyError as exc:
        logger.error("邮件模板变量缺失: %s", exc)
        return False
    return await send_email(email, subject, body)
