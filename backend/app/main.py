"""FastAPI application entry point for qloop."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
        version="1.3.1",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
            "version": "1.3.1",
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
