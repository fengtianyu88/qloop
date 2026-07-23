"""Release management service."""

import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import ExternalRecipient, Project, Release, ReleaseStatus, Version
from app.storage.minio_client import (
    minio_delete_object,
    minio_generate_presigned_url,
    minio_upload_file,
)
from app.models.notification import NotificationType
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 文件类型白名单 + 文件名 sanitize(P1-2 / P1-3)
# ---------------------------------------------------------------------------
# 各业务文件类型允许的扩展名(小写,带点)
ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    'code_package': {'.zip', '.tar', '.gz', '.tgz', '.rar', '.7z'},
    'test_report': {'.pdf', '.doc', '.docx', '.xlsx', '.xls', '.csv', '.zip'},
    'review_report': {'.pdf', '.doc', '.docx', '.zip'},
}

# 文件名中允许的字符:字母/数字/下划线/点/减号/中文,其余替换为 _
_SAFE_NAME_RE = re.compile(r"[^\w.\-\u4e00-\u9fa5]")


def validate_file_type(file_type: str, filename: str) -> bool:
    """校验文件类型是否在白名单中。

    Args:
        file_type: 业务文件类型,可选 ``code_package`` / ``test_report`` /
            ``review_report``。
        filename: 待校验文件名。

    Returns:
        扩展名是否在白名单中。
    """
    ext = PurePath(filename).suffix.lower()
    allowed = ALLOWED_EXTENSIONS.get(file_type, set())
    return ext in allowed


def sanitize_filename(filename: str) -> str:
    """生成安全文件名:UUID 前缀 + 清洗后的原文件名。

    - 仅取 basename,防止路径穿越(如 ``../../etc/passwd``)
    - 替换非白名单字符为 ``_``,保留中文/字母/数字/点/减号/下划线
    - 前置 UUID 防止重名/碰撞,同时保留原文件名以便展示

    Returns:
        形如 ``<uuid_hex>_<原文件名>`` 的安全文件名。
    """
    base = PurePath(filename).name
    if not base:
        base = 'upload'
    safe = _SAFE_NAME_RE.sub('_', base).strip('._') or 'upload'
    return f"{uuid.uuid4().hex}_{safe}"


def calculate_sha256(content: bytes) -> str:
    """计算字节内容的 SHA256 摘要(功能3)。"""
    return hashlib.sha256(content).hexdigest()


async def verify_access_token(
    db: AsyncSession, token: str, release_id: uuid.UUID
) -> Optional[ExternalRecipient]:
    """校验外部接收方的 access_token(功能2.2)。

    校验规则:
    - token 必须存在于 external_recipients 表
    - token 对应的 version 必须与 release 的 version 一致
    - token 未过期
    - 下载次数未超上限

    返回匹配的 ExternalRecipient,否则返回 None。
    """
    result = await db.execute(
        select(ExternalRecipient).where(ExternalRecipient.access_token == token)
    )
    recipient = result.scalar_one_or_none()
    if recipient is None:
        return None

    # 校验过期
    if (
        recipient.token_expires_at is not None
        and recipient.token_expires_at < datetime.now(timezone.utc)
    ):
        return None

    # 校验下载次数
    if recipient.download_count >= recipient.max_downloads:
        return None

    # 校验 token 对应的 version 与 release 的 version 一致
    release_result = await db.execute(
        select(Release).where(Release.id == release_id)
    )
    release = release_result.scalar_one_or_none()
    if release is None or release.version_id != recipient.version_id:
        return None

    return recipient


async def increment_download_count(
    db: AsyncSession, recipient: ExternalRecipient
) -> None:
    """增加下载计数(功能2.2)。"""
    recipient.download_count = (recipient.download_count or 0) + 1
    await db.commit()


async def get_release_by_id(
    db: AsyncSession, release_id: uuid.UUID
) -> Optional[Release]:
    """Get a release by ID with version eagerly loaded."""
    result = await db.execute(
        select(Release)
        .options(selectinload(Release.version))
        .where(Release.id == release_id)
    )
    return result.scalar_one_or_none()


async def _get_version_project_for_notify(
    db: AsyncSession, version_id: uuid.UUID
) -> Optional[tuple]:
    """查询版本的版本号、各角色 user_id 和 PM user_id(用于通知)。

    返回 (version_number, developer_id, tester_id, expert_id, pm_user_id),
    若版本不存在返回 None。commit 之后 release.version 关系可能已过期,
    因此单独查询避免 async 懒加载错误。
    """
    result = await db.execute(
        select(Version, Project.pm_user_id)
        .join(Project, Project.id == Version.project_id)
        .where(Version.id == version_id)
    )
    row = result.first()
    if row is None:
        return None
    ver, pm_user_id = row
    return (
        ver.version_number,
        ver.developer_id,
        ver.tester_id,
        ver.expert_id,
        pm_user_id,
    )


async def upload_code_package(
    db: AsyncSession,
    release_id: uuid.UUID,
    file_data: bytes,
    file_name: str,
    content_type: str,
    change_notes: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
) -> Optional[Release]:
    """Upload a code package to MinIO and update the release status.

    Args:
        db: The async database session.
        release_id: The release ID.
        file_data: The file content as bytes.
        file_name: The original file name.
        content_type: The MIME content type.
        change_notes: Optional change notes to attach.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    # 空文件检查(P1-4)
    if not file_data:
        raise ValueError("文件内容为空,请上传有效的文件")

    # 校验文件类型(白名单,P1-2)
    if not validate_file_type('code_package', file_name):
        raise ValueError(
            f"不支持的代码包文件类型,允许: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS['code_package']))}"
        )
    # 生成安全文件名(防止路径穿越/特殊字符,P1-3)
    safe_name = sanitize_filename(file_name)
    object_name = f"releases/{release_id}/code_package/{safe_name}"
    minio_upload_file(object_name, file_data, len(file_data), content_type)

    release.code_package_path = object_name
    # 计算并保存 SHA256(功能3.2)
    release.code_package_sha256 = calculate_sha256(file_data)
    release.status = ReleaseStatus.CODE_PENDING_REVIEW
    if change_notes is not None:
        release.change_notes = change_notes
    if user_id is not None:
        release.code_package_uploaded_by = user_id
        release.code_package_uploaded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(release)

    # 通知 PM:代码包已上传,请触发代码评审
    try:
        info = await _get_version_project_for_notify(db, release.version_id)
        if info is not None:
            version_no, _dev, _tester, _expert, pm_uid = info
            if pm_uid is not None:
                await create_notification(
                    db, pm_uid, NotificationType.YOUR_TURN,
                    "代码包已上传",
                    f"{version_no} 代码包已上传，请触发代码评审",
                    f"/releases/{release.id}",
                )
    except Exception:
        # 通知失败不影响主流程
        pass

    return release


async def upload_test_report(
    db: AsyncSession,
    release_id: uuid.UUID,
    file_data: bytes,
    file_name: str,
    content_type: str,
    user_id: Optional[uuid.UUID] = None,
) -> Optional[Release]:
    """Upload a test report to MinIO and update the release status.

    Args:
        db: The async database session.
        release_id: The release ID.
        file_data: The file content as bytes.
        file_name: The original file name.
        content_type: The MIME content type.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    # 空文件检查(P1-4)
    if not file_data:
        raise ValueError("文件内容为空,请上传有效的文件")

    # 校验文件类型(白名单,P1-2)
    if not validate_file_type('test_report', file_name):
        raise ValueError(
            f"不支持的测试报告文件类型,允许: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS['test_report']))}"
        )
    # 生成安全文件名(防止路径穿越/特殊字符,P1-3)
    safe_name = sanitize_filename(file_name)
    object_name = f"releases/{release_id}/test_report/{safe_name}"
    minio_upload_file(object_name, file_data, len(file_data), content_type)

    release.test_report_path = object_name
    # 计算并保存 SHA256(功能3.2)
    release.test_report_sha256 = calculate_sha256(file_data)
    release.status = ReleaseStatus.TEST_PENDING_REVIEW
    if user_id is not None:
        release.test_report_uploaded_by = user_id
        release.test_report_uploaded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(release)

    # 通知 PM:测试报告已上传,请触发测试报告评审
    try:
        info = await _get_version_project_for_notify(db, release.version_id)
        if info is not None:
            version_no, _dev, _tester, _expert, pm_uid = info
            if pm_uid is not None:
                await create_notification(
                    db, pm_uid, NotificationType.YOUR_TURN,
                    "测试报告已上传",
                    f"{version_no} 测试报告已上传，请触发测试报告评审",
                    f"/releases/{release.id}",
                )
    except Exception:
        # 通知失败不影响主流程
        pass

    return release


async def upload_review_report(
    db: AsyncSession,
    release_id: uuid.UUID,
    file_data: bytes,
    file_name: str,
    content_type: str,
    user_id: Optional[uuid.UUID] = None,
) -> Optional[Release]:
    """Upload a review/expert report to MinIO and update the release status.

    Args:
        db: The async database session.
        release_id: The release ID.
        file_data: The file content as bytes.
        file_name: The original file name.
        content_type: The MIME content type.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    # 空文件检查(P1-4)
    if not file_data:
        raise ValueError("文件内容为空,请上传有效的文件")

    # 校验文件类型(白名单,P1-2)
    if not validate_file_type('review_report', file_name):
        raise ValueError(
            f"不支持的评审报告文件类型,允许: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS['review_report']))}"
        )
    # 生成安全文件名(防止路径穿越/特殊字符,P1-3)
    safe_name = sanitize_filename(file_name)
    object_name = f"releases/{release_id}/review_report/{safe_name}"
    minio_upload_file(object_name, file_data, len(file_data), content_type)

    release.review_report_path = object_name
    # 计算并保存 SHA256(功能3.2)
    release.review_report_sha256 = calculate_sha256(file_data)
    release.status = ReleaseStatus.EXPERT_PENDING_REVIEW
    if user_id is not None:
        release.review_report_uploaded_by = user_id
        release.review_report_uploaded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(release)

    # 通知 PM:专家评审报告已上传,请触发专家报告评审
    try:
        info = await _get_version_project_for_notify(db, release.version_id)
        if info is not None:
            version_no, _dev, _tester, _expert, pm_uid = info
            if pm_uid is not None:
                await create_notification(
                    db, pm_uid, NotificationType.YOUR_TURN,
                    "专家评审报告已上传",
                    f"{version_no} 专家评审报告已上传，请触发专家报告评审",
                    f"/releases/{release.id}",
                )
    except Exception:
        # 通知失败不影响主流程
        pass

    return release


async def confirm_release(
    db: AsyncSession, release_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[Release]:
    """Confirm a release, setting status to RELEASED.

    Generates a presigned download link with a default 168-hour expiry.

    Args:
        db: The async database session.
        release_id: The release ID.
        user_id: The ID of the user confirming the release.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    # 锁定 release 行,防止双重释放
    result = await db.execute(
        select(Release).where(Release.id == release_id).with_for_update()
    )
    release = result.scalar_one_or_none()
    if release is None:
        return None

    if release.status != ReleaseStatus.PENDING_CONFIRM:
        raise ValueError("当前状态不允许释放")

    # v1.5.1: 检查是否曾经被特批放行(任何评审阶段被特批)
    # 如果有特批放行的评审,状态设为 RELEASED_FORCED(已特批释放),否则 RELEASED(已释放)
    from app.models.review import LLMReview
    force_passed_count_stmt = select(LLMReview).where(
        LLMReview.release_id == release_id,
        LLMReview.force_passed == True,  # noqa: E712
    )
    force_passed_reviews = (await db.execute(force_passed_count_stmt)).scalars().all()

    if len(force_passed_reviews) > 0:
        release.status = ReleaseStatus.RELEASED_FORCED
    else:
        release.status = ReleaseStatus.RELEASED
    release.confirmed_by = user_id
    release.confirmed_at = datetime.now(timezone.utc)

    # 功能3.3: 确保所有已上传文件的 SHA256 已记录(释放时完整性校验)
    # 如果 SHA256 缺失(老数据),此处不阻塞释放,仅依赖上传时已计算
    sha256_summary = {
        "code_package": release.code_package_sha256,
        "test_report": release.test_report_sha256,
        "review_report": release.review_report_sha256,
    }

    # Generate a presigned download link for the code package
    if release.code_package_path:
        try:
            download_link = minio_generate_presigned_url(
                release.code_package_path, expiry_hours=168
            )
            release.download_link = download_link
            release.link_expiry = datetime.now(timezone.utc) + timedelta(hours=168)
        except Exception as exc:
            # If presigned URL generation fails, still mark as released
            logger.warning("生成下载链接失败: %s", exc)

    # 功能2.3: 为该版本的所有 ExternalRecipient 生成 access_token
    try:
        recipients_result = await db.execute(
            select(ExternalRecipient).where(
                ExternalRecipient.version_id == release.version_id
            )
        )
        recipients = list(recipients_result.scalars().all())
        now_utc = datetime.now(timezone.utc)
        for recipient in recipients:
            # 仅在未生成 token 或 token 已过期时重新生成
            need_new = (
                not recipient.access_token
                or (
                    recipient.token_expires_at is not None
                    and recipient.token_expires_at < now_utc
                )
            )
            if need_new:
                recipient.access_token = secrets.token_urlsafe(32)
                recipient.token_expires_at = now_utc + timedelta(
                    hours=recipient.link_expiry_hours or 168
                )
                recipient.download_count = 0
        # recipients 已在 session 中,commit 时会一起保存
    except Exception:
        # 生成 token 失败不阻塞释放流程
        pass

    await db.commit()
    await db.refresh(release)

    # 通知所有相关人员(developer/tester/expert/PM):版本已释放
    try:
        info = await _get_version_project_for_notify(db, release.version_id)
        if info is not None:
            version_no, dev_id, tester_id, expert_id, pm_uid = info
            link_url = f"/releases/{release.id}"
            for uid in (dev_id, tester_id, expert_id, pm_uid):
                if uid is None:
                    continue
                await create_notification(
                    db, uid, NotificationType.RELEASE_COMPLETED,
                    "版本已释放",
                    f"{version_no} 已成功释放",
                    link_url,
                )
    except Exception:
        # 通知失败不影响主流程
        pass

    return release


async def handle_review_failure(
    db: AsyncSession, release_id: uuid.UUID
) -> Optional[Release]:
    """Handle a review failure by setting the release status to REVIEW_FAILED.

    Args:
        db: The async database session.
        release_id: The release ID.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    release.status = ReleaseStatus.REVIEW_FAILED

    await db.commit()
    await db.refresh(release)
    return release


async def advance_release_after_review(
    db: AsyncSession, release_id: uuid.UUID
) -> Optional[Release]:
    """Advance the release status after an LLM review passes.

    Transitions:
        - CODE_PENDING_REVIEW -> TEST_PENDING_REVIEW
        - TEST_PENDING_REVIEW -> EXPERT_PENDING_REVIEW
        - EXPERT_PENDING_REVIEW -> PENDING_CONFIRM

    Args:
        db: The async database session.
        release_id: The release ID.

    Returns:
        The updated Release object, or ``None`` if not found.

    Raises:
        ValueError: If the current status does not allow advancement.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    status_transitions = {
        ReleaseStatus.CODE_PENDING_REVIEW: ReleaseStatus.TEST_PENDING_REVIEW,
        ReleaseStatus.TEST_PENDING_REVIEW: ReleaseStatus.EXPERT_PENDING_REVIEW,
        ReleaseStatus.EXPERT_PENDING_REVIEW: ReleaseStatus.PENDING_CONFIRM,
    }

    next_status = status_transitions.get(release.status)
    if next_status is None:
        raise ValueError(
            f"Cannot advance release in status '{release.status.value}'"
        )

    release.status = next_status

    await db.commit()
    await db.refresh(release)
    return release



async def delete_artifact(
    db: AsyncSession,
    release_id: uuid.UUID,
    file_type: str,
) -> Optional[Release]:
    """Delete an artifact from MinIO and clear its fields on the release.

    Args:
        db: The async database session.
        release_id: The release ID.
        file_type: One of 'code_package', 'test_report', 'review_report'.

    Returns:
        The updated Release object, or None if release not found.

    Raises:
        ValueError: If file_type is invalid, or if the release is already
            released (released releases are immutable).
    """
    # 锁定 release 行,防止并发删除/修改
    result = await db.execute(
        select(Release).where(Release.id == release_id).with_for_update()
    )
    release = result.scalar_one_or_none()
    if release is None:
        return None

    if release.status in (ReleaseStatus.RELEASED, ReleaseStatus.RELEASED_FORCED):
        raise ValueError("Cannot delete artifact: release is already released")

    field_map = {
        "code_package": ("code_package_path", "code_package_uploaded_by", "code_package_uploaded_at"),
        "test_report": ("test_report_path", "test_report_uploaded_by", "test_report_uploaded_at"),
        "review_report": ("review_report_path", "review_report_uploaded_by", "review_report_uploaded_at"),
    }
    if file_type not in field_map:
        raise ValueError(f"Invalid file_type: {file_type}")

    path_attr, uploader_attr, uploaded_at_attr = field_map[file_type]
    object_name = getattr(release, path_attr)
    if object_name:
        try:
            minio_delete_object(object_name)
        except Exception:
            # Best-effort: log but continue to clear DB fields
            pass

    setattr(release, path_attr, None)
    setattr(release, uploader_attr, None)
    setattr(release, uploaded_at_attr, None)

    # If deleting code_package, also clear change_notes? No - change_notes may
    # be a project-level field; leave it alone.
    await db.commit()
    await db.refresh(release)
    return release



async def skip_review(
    db: AsyncSession, release_id: uuid.UUID
) -> Optional[Release]:
    """Skip the current LLM review and advance to the next stage.

    Same transition logic as :func:`advance_release_after_review` but
    does not require an actual review to have been performed.

    Transitions:
        - CODE_PENDING_REVIEW -> TEST_PENDING_REVIEW
        - TEST_PENDING_REVIEW -> EXPERT_PENDING_REVIEW
        - EXPERT_PENDING_REVIEW -> PENDING_CONFIRM

    Returns:
        The updated Release object, or None if not found.
    Raises:
        ValueError: If the current status does not allow skipping.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    status_transitions = {
        ReleaseStatus.CODE_PENDING_REVIEW: ReleaseStatus.TEST_PENDING_REVIEW,
        ReleaseStatus.TEST_PENDING_REVIEW: ReleaseStatus.EXPERT_PENDING_REVIEW,
        ReleaseStatus.EXPERT_PENDING_REVIEW: ReleaseStatus.PENDING_CONFIRM,
    }

    next_status = status_transitions.get(release.status)
    if next_status is None:
        raise ValueError(
            f"Cannot skip review in status '{release.status.value}'"
        )

    release.status = next_status
    await db.commit()
    await db.refresh(release)
    return release


async def force_advance(
    db: AsyncSession, release_id: uuid.UUID, forced_by: Optional[uuid.UUID] = None
) -> Optional[Release]:
    """Force-advance a release to the next stage, bypassing reviews.

    - In review stages (code/test/expert pending_review): advance to next stage.
    - In pending_confirm: force-release (set status to RELEASED, generate download link).
    - In review_failed: special-approval advance based on the failed review stage
      (功能7 - PM/admin can override LLM review failures).
    - In draft: not allowed (must upload code package first).

    Args:
        db: Async database session.
        release_id: Release ID.
        forced_by: Optional user ID of the approver (PM/admin) who triggered
            the force-advance. Recorded on the release for audit/display.

    Returns:
        The updated Release object, or None if not found.
    Raises:
        ValueError: If the current status does not allow force-advance.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    if release.status == ReleaseStatus.DRAFT:
        raise ValueError("Cannot force-advance a draft release (upload code package first)")
    if release.status == ReleaseStatus.RELEASED:
        raise ValueError("Release is already released")
    if release.status == ReleaseStatus.RELEASED_FORCED:
        raise ValueError("Release is already released (forced)")

    # 功能7: REVIEW_FAILED 状态下,PM/管理员可特批放行,根据失败阶段决定推进目标
    if release.status == ReleaseStatus.REVIEW_FAILED:
        # 查询最近一次失败的 LLMReview,判断失败发生在哪个阶段
        from app.models.review import LLMReview, ReviewResult, ReviewType
        from sqlalchemy import select as _select

        fail_stmt = (
            _select(LLMReview)
            .where(
                LLMReview.release_id == release_id,
                LLMReview.result.in_([ReviewResult.FAILED, ReviewResult.ERROR]),
            )
            .order_by(LLMReview.created_at.desc())
            .limit(1)
        )
        failed_review = (await db.execute(fail_stmt)).scalars().first()

        if failed_review is None:
            # 没有失败的 review 记录,默认推进到下一阶段(保守:进入 pending_confirm)
            next_status = ReleaseStatus.PENDING_CONFIRM
        else:
            # 根据失败的 review_type 决定推进目标
            failed_type_to_next = {
                ReviewType.CODE_REVIEW: ReleaseStatus.TEST_PENDING_REVIEW,
                ReviewType.TEST_REPORT_REVIEW: ReleaseStatus.EXPERT_PENDING_REVIEW,
                ReviewType.EXPERT_REPORT_REVIEW: ReleaseStatus.PENDING_CONFIRM,
            }
            next_status = failed_type_to_next.get(
                failed_review.review_type, ReleaseStatus.PENDING_CONFIRM
            )

        release.status = next_status
        if forced_by is not None:
            release.force_advanced_by = forced_by
            release.force_advanced_at = datetime.now(timezone.utc)

        # v1.5.1: 标记失败的 LLMReview 为 force_passed=True(特批放行)
        if failed_review is not None and not failed_review.force_passed:
            failed_review.force_passed = True
            failed_review.force_passed_by = forced_by
            failed_review.force_passed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(release)
        # 通知下一角色:已特批放行
        try:
            info = await _get_version_project_for_notify(db, release.version_id)
            if info is not None:
                version_no, dev_id, tester_id, expert_id, pm_uid = info
                next_role_user = {
                    ReleaseStatus.TEST_PENDING_REVIEW: tester_id,
                    ReleaseStatus.EXPERT_PENDING_REVIEW: expert_id,
                    ReleaseStatus.PENDING_CONFIRM: pm_uid,
                }.get(next_status)
                if next_role_user is not None:
                    await create_notification(
                        db, next_role_user, NotificationType.YOUR_TURN,
                        "已特批放行",
                        f"{version_no} 已特批放行到下一阶段",
                        f"/releases/{release.id}",
                    )
        except Exception:
            pass
        return release

    if release.status == ReleaseStatus.PENDING_CONFIRM:
        # Force-release: same as confirm_release but bypassing checks
        # v1.5.1: 特批放行释放,状态设为 RELEASED_FORCED(已特批释放)
        release.status = ReleaseStatus.RELEASED_FORCED
        release.confirmed_at = datetime.now(timezone.utc)
        if forced_by is not None:
            release.force_advanced_by = forced_by
            release.force_advanced_at = datetime.now(timezone.utc)
        # Generate download link
        if release.code_package_path:
            try:
                release.download_link = minio_generate_presigned_url(
                    release.code_package_path, expiry_hours=168
                )
                release.link_expiry = datetime.now(timezone.utc) + timedelta(hours=168)
            except Exception as exc:
                logger.warning("生成下载链接失败: %s", exc)
        # 功能2.3: 为 ExternalRecipient 生成 access_token(force-advance 路径)
        try:
            recipients_result = await db.execute(
                select(ExternalRecipient).where(
                    ExternalRecipient.version_id == release.version_id
                )
            )
            recipients = list(recipients_result.scalars().all())
            now_utc = datetime.now(timezone.utc)
            for recipient in recipients:
                if (
                    not recipient.access_token
                    or (
                        recipient.token_expires_at is not None
                        and recipient.token_expires_at < now_utc
                    )
                ):
                    recipient.access_token = secrets.token_urlsafe(32)
                    recipient.token_expires_at = now_utc + timedelta(
                        hours=recipient.link_expiry_hours or 168
                    )
                    recipient.download_count = 0
        except Exception:
            pass
        await db.commit()
        await db.refresh(release)
        return release

    # Review stages: advance to next stage
    status_transitions = {
        ReleaseStatus.CODE_PENDING_REVIEW: ReleaseStatus.TEST_PENDING_REVIEW,
        ReleaseStatus.TEST_PENDING_REVIEW: ReleaseStatus.EXPERT_PENDING_REVIEW,
        ReleaseStatus.EXPERT_PENDING_REVIEW: ReleaseStatus.PENDING_CONFIRM,
    }

    next_status = status_transitions.get(release.status)
    if next_status is None:
        raise ValueError(
            f"Cannot force-advance in status '{release.status.value}'"
        )

    # v1.5.1: 在修改 status 之前保存原状态(用于查找对应阶段的 review_type)
    original_status = release.status

    release.status = next_status
    if forced_by is not None:
        release.force_advanced_by = forced_by
        release.force_advanced_at = datetime.now(timezone.utc)

    # v1.5.1: 标记对应阶段最近的 LLMReview 为 force_passed=True(特批放行)
    # 用原状态(特批放行前)查找 review_type,而不是新状态
    status_to_review_type = {
        ReleaseStatus.CODE_PENDING_REVIEW: "code_review",
        ReleaseStatus.TEST_PENDING_REVIEW: "test_report_review",
        ReleaseStatus.EXPERT_PENDING_REVIEW: "expert_report_review",
    }
    current_review_type = status_to_review_type.get(original_status)
    if current_review_type is not None:
        from app.models.review import LLMReview, ReviewType as _RT
        try:
            rt_enum = _RT(current_review_type)
        except ValueError:
            rt_enum = None
        if rt_enum is not None:
            review_stmt = (
                select(LLMReview)
                .where(
                    LLMReview.release_id == release_id,
                    LLMReview.review_type == rt_enum,
                )
                .order_by(LLMReview.created_at.desc())
                .limit(1)
            )
            latest_review = (await db.execute(review_stmt)).scalars().first()
            if latest_review is not None and not latest_review.force_passed:
                latest_review.force_passed = True
                latest_review.force_passed_by = forced_by
                latest_review.force_passed_at = datetime.now(timezone.utc)
            elif latest_review is None:
                # v1.5.1: 如果该阶段没有 LLMReview,创建一个 force_passed=True 的占位 review
                # 用于在前端显示"特批放行"标签(满足需求:每个评审阶段特批放行后都可见)
                from app.models.review import ReviewResult as _RR
                placeholder_review = LLMReview(
                    release_id=release_id,
                    review_type=rt_enum,
                    review_round=1,
                    result=_RR.FAILED,
                    conclusion="特批放行-该阶段未触发LLM评审",
                    triggered_by=forced_by,
                    force_passed=True,
                    force_passed_by=forced_by,
                    force_passed_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
                db.add(placeholder_review)

    await db.commit()
    await db.refresh(release)
    # 通知下一角色:已特批放行
    try:
        info = await _get_version_project_for_notify(db, release.version_id)
        if info is not None:
            version_no, dev_id, tester_id, expert_id, pm_uid = info
            next_role_user = {
                ReleaseStatus.TEST_PENDING_REVIEW: tester_id,
                ReleaseStatus.EXPERT_PENDING_REVIEW: expert_id,
                ReleaseStatus.PENDING_CONFIRM: pm_uid,
            }.get(next_status)
            if next_role_user is not None:
                await create_notification(
                    db, next_role_user, NotificationType.YOUR_TURN,
                    "已特批放行",
                    f"{version_no} 已特批放行到下一阶段",
                    f"/releases/{release.id}",
                )
    except Exception:
        pass
    return release

