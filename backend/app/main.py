"""FastAPI application entry point for qloop."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app.api.imports import router as imports_router
from app.api.my_tasks import router as my_tasks_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.llm_config import router as llm_config_router
from app.api.notifications import router as notifications_router
from app.api.organizations import router as organizations_router
from app.api.projects import router as projects_router
from app.api.releases import router as releases_router
from app.api.reviews import router as reviews_router
from app.api.search import router as search_router
from app.api.system_settings import router as system_settings_router
from app.api.users import router as users_router
from app.config import settings
from app.services.init_service import ensure_default_review_rules

# P2-10: 启动时配置日志级别(可通过 LOG_LEVEL 环境变量调整)
logging.basicConfig(level=settings.LOG_LEVEL)
if settings.LOG_LEVEL == "DEBUG":
    # DEBUG 模式下开启 SQLAlchemy 引擎日志,便于排查 SQL 问题
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


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
        version="1.4.3",
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

    # Register all API routers
    app.include_router(imports_router)
    app.include_router(my_tasks_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(organizations_router)
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
            "version": "1.4.3",
        }

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
