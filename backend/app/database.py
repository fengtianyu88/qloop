"""Database engine, session factory, and Base declarative model."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Async engine
# 连接池配置(P1-7):
#   pool_pre_ping:每次取连接前 ping 一下,自动剔除失效连接,避免长连接断开后报错
#   pool_size:常驻连接数
#   max_overflow:超出常驻后允许临时扩展的连接数
#   pool_timeout:获取连接的等待超时(秒),超时抛 TimeoutError
#   pool_recycle:连接最大复用时长(秒),防止数据库/中间件主动断开空闲连接
#
# P2-13: 事务隔离级别保持 PostgreSQL 默认 READ COMMITTED,
#   全局使用 REPEATABLE READ 可能导致死锁,故仅在关键路径上加
#   with_for_update() 行锁(已在 P0 实现),这里不全局调整。
#
# P2-14: 通过 connect_args.server_settings 设置 statement_timeout=60000ms,
#   防止单条 SQL 长时间运行拖垮连接池(60 秒后 PG 主动取消查询)。
#   仅对 PostgreSQL 生效(asyncpg 支持 server_settings)。
import re as _re

_connect_args: dict = {}
if _re.search(r"postgresql(?:\+[a-z]+)?://", settings.DATABASE_URL, _re.IGNORECASE):
    _connect_args["server_settings"] = {"statement_timeout": "60000"}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
    connect_args=_connect_args,
)

# Async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Backwards-compatible alias used by the LLM review engine and Celery tasks.
async_session = async_session_factory


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session.

    P2-14: 每次取 session 时显式 SET statement_timeout = 60s,
    防止长事务拖垮连接池。若数据库不支持该参数(非 PG)则忽略异常。
    """
    from sqlalchemy import text
    async with async_session_factory() as session:
        try:
            # 60 秒语句超时,防止长事务/慢查询占用连接
            await session.execute(text("SET statement_timeout = 60000"))
        except Exception:
            # 非 PG 后端或不支持 statement_timeout 时静默忽略
            pass
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
