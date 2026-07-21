# -*- coding: utf-8 -*-
# Redis client for qloop.
import logging

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

# 全局连接池(惰性初始化)
_redis_pool: "redis.ConnectionPool | None" = None


async def get_redis() -> redis.Redis:
    """获取 Redis 客户端(复用全局连接池)。"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL)
    return redis.Redis(connection_pool=_redis_pool)
