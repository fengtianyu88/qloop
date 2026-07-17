"""Celery task that runs an LLM review asynchronously.

The review engine (:func:`app.llm.reviewer.execute_review`) is async and
uses an async SQLAlchemy session. Celery tasks are synchronous, so each
task creates a brand new event loop and runs the coroutine to completion
inside it.

IMPORTANT: A fresh async engine with ``NullPool`` is created per task
invocation. The globally-shared engine in ``app.database`` binds its
connection pool to whatever event loop first uses it, which is
incompatible with Celery's prefork model — reusing that engine inside a
task-created event loop raises
``RuntimeError: ... attached to a different loop``. ``NullPool`` avoids
the issue by opening a brand new database connection each time and never
pooling it across loops.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings
from app.llm.reviewer import execute_review
from app.models.review import ReviewType
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run a coroutine in a dedicated event loop and return its result.

    A fresh event loop is created for each task invocation so the task is
    safe to run inside Celery's prefork pool (where the loop cannot be
    shared across worker processes).
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_session_factory() -> "async_sessionmaker[AsyncSession]":
    """Build a single-use async session factory bound to a NullPool engine.

    ``NullPool`` means every session opens a fresh DB connection that lives
    only for the duration of the current event loop, eliminating any
    cross-loop binding issues with asyncpg.
    """
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@celery_app.task(name="run_llm_review")
def run_llm_review(
    release_id: str,
    review_type: str,
    triggered_by: str,
) -> dict:
    """Trigger and execute an LLM review for a release.

    Args:
        release_id: The release ID (as a string UUID).
        review_type: One of the :class:`ReviewType` values (e.g.
            ``"code_review"``).
        triggered_by: The user ID that triggered the review (string UUID).

    Returns:
        A dict with ``review_id`` (str), ``result`` (the review result
        value, e.g. ``"passed"``/``"failed"``) and ``total_score`` (float).
    """
    release_uuid = uuid.UUID(release_id)
    triggered_by_uuid = uuid.UUID(triggered_by)

    try:
        rt = ReviewType(review_type)
    except ValueError as exc:
        logger.error("Unknown review_type '%s': %s", review_type, exc)
        return {
            "review_id": None,
            "result": "error",
            "total_score": 0.0,
            "error": f"Unknown review_type: {review_type}",
        }

    session_factory = _make_session_factory()

    async def _run() -> dict:
        async with session_factory() as db:
            review = await execute_review(
                db=db,
                release_id=release_uuid,
                review_type=rt,
                triggered_by=triggered_by_uuid,
            )
            return {
                "review_id": str(review.id),
                "result": review.result.value if review.result else "unknown",
                "total_score": float(review.total_score or 0.0),
            }

    try:
        return _run_async(_run())
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_llm_review failed: %s", exc)
        return {
            "review_id": None,
            "result": "error",
            "total_score": 0.0,
            "error": str(exc),
        }
