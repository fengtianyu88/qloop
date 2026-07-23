"""FastAPI application entry point for qloop."""

import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from app.api.imports import router as imports_router
from app.api.my_tasks import router as my_tasks_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.llm_config import router as llm_config_router
from app.api.notifications import router as notifications_router
from app.api.organizations import router as organizations_router, org_type_router
from app.api.projects import router as projects_router
from app.api.releases import router as releases_router
from app.api.reviews import router as reviews_router
from app.api.search import router as search_router
from app.api.system_settings import router as system_settings_router
from app.api.users import router as users_router
from app.config import settings
from app.database import async_session_factory
from app.services.init_service import ensure_default_review_rules

# P2-10: 启动时配置日志级别(可通过 LOG_LEVEL 环境变量调整)
logging.basicConfig(level=settings.LOG_LEVEL)
if settings.LOG_LEVEL == "DEBUG":
    # DEBUG 模式下开启 SQLAlchemy 引擎日志,便于排查 SQL 问题
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# 轻量级 HTTP 计数器(模块级,不引入 prometheus-client)
_http_counters = {"requests_total": 0, "errors_total": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    Called at startup and shutdown. Used to ensure default data exists.
    """
    # Startup: ensure default review rules exist
    try:
        await ensure_default_review_rules()
    except Exception as exc:
        # 启动时初始化失败不应阻塞应用启动,只记录日志
        logger.error("ensure_default_review_rules 启动失败: %s", exc, exc_info=True)
    yield
    # Shutdown: nothing to clean up


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            f"{settings.APP_NAME} 后端 API — 质量闭环 · 测试驱动开发。"
            f"覆盖项目管理、版本释放流程、LLM 评审与审计日志等能力。"
        ),
        version="1.5.4",
        lifespan=lifespan,
    )

    # P2-11: CORS 允许源改为从环境变量读取(逗号分隔)
    cors_origins = [
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # P2-5: 安全响应头中间件(CSP / X-Frame-Options 等)
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """为所有响应附加安全相关 HTTP 头部。

        - CSP 允许内联脚本/样式(Vue 运行需要 unsafe-eval)
        - X-Frame-Options DENY 防止被嵌套点击劫持
        - X-Content-Type-Options nosniff 阻止 MIME 嗅探
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # CSP 策略:允许内联脚本和样式,因为 Vue 运行时需要
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' ws: wss:;"
        )
        return response

    # trace_id 中间件:为每个请求生成唯一 trace_id,便于日志追踪
    @app.middleware("http")
    async def add_trace_id(request: Request, call_next):
        """为每个请求生成 trace_id 并附加到响应头 X-Trace-Id。"""
        request.state.trace_id = str(uuid4())[:8]
        response = await call_next(request)
        response.headers["X-Trace-Id"] = request.state.trace_id
        return response

    # HTTP 计数中间件:统计请求数与错误数(供 /metrics 使用)
    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        """统计请求总数与错误总数(模块级计数器,非线程安全,仅用于轻量监控)。"""
        _http_counters["requests_total"] += 1
        try:
            response = await call_next(request)
        except Exception:
            _http_counters["errors_total"] += 1
            raise
        if response.status_code >= 500:
            _http_counters["errors_total"] += 1
        return response

    # Register all API routers
    app.include_router(imports_router)
    app.include_router(my_tasks_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(organizations_router)
    app.include_router(org_type_router)
    app.include_router(projects_router)
    app.include_router(releases_router)
    app.include_router(search_router)
    app.include_router(notifications_router)
    app.include_router(audit_router)
    app.include_router(llm_config_router)
    app.include_router(reviews_router)
    app.include_router(system_settings_router)

    # Health check endpoint
    @app.get("/api/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": "1.5.4",
        }

    @app.get("/api/ready", tags=["health"])
    async def ready_check():
        """Readiness probe: 检查 DB / Redis / MinIO / Celery 连通性。

        任一组件不可用返回 503,全部正常返回 200。
        """
        checks: dict[str, bool] = {
            "db": False,
            "redis": False,
            "minio": False,
            "celery": False,
        }

        # DB: SELECT 1
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            checks["db"] = True
        except Exception as exc:
            logger.warning("Readiness check DB failed: %s", exc)

        # Redis: ping
        try:
            from app.redis_client import get_redis

            redis = await get_redis()
            await redis.ping()
            checks["redis"] = True
        except Exception as exc:
            logger.warning("Readiness check Redis failed: %s", exc)

        # MinIO: bucket_exists
        try:
            from app.storage.minio_client import minio_client

            if minio_client.bucket_exists(settings.MINIO_BUCKET):
                checks["minio"] = True
            else:
                logger.warning(
                    "Readiness check MinIO: bucket %s does not exist",
                    settings.MINIO_BUCKET,
                )
        except Exception as exc:
            logger.warning("Readiness check MinIO failed: %s", exc)

        # Celery: inspect.ping
        try:
            from app.tasks.celery_app import celery_app

            inspect = celery_app.control.inspect(timeout=1)
            ping_result = inspect.ping()
            if ping_result is not None:
                checks["celery"] = True
            else:
                logger.warning("Readiness check Celery: no workers responded")
        except Exception as exc:
            logger.warning("Readiness check Celery failed: %s", exc)

        all_ok = all(checks.values())
        if not all_ok:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "checks": checks},
            )
        return {"status": "ready", "checks": checks}

    @app.get("/api/metrics", tags=["monitoring"])
    async def metrics():
        """Prometheus 兼容的轻量级 metrics 端点(text exposition format)。

        仅暴露 HTTP 请求总数与错误总数,无需 prometheus-client 依赖。
        """
        lines = [
            "# HELP http_requests_total Total HTTP requests",
            "# TYPE http_requests_total counter",
            f"http_requests_total {_http_counters['requests_total']}",
            "# HELP http_errors_total Total HTTP errors (5xx / exceptions)",
            "# TYPE http_errors_total counter",
            f"http_errors_total {_http_counters['errors_total']}",
        ]
        return PlainTextResponse(
            content="\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4",
        )

    # 全局异常处理器:兜底未捕获异常,避免向前端泄露内部栈
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "Unhandled exception: %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误，请联系管理员"},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
