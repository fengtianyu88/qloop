"""Application configuration using pydantic-settings."""

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 不安全的默认值(生产环境禁止使用)
INSECURE_DEFAULTS = {"change-me-in-production", "minioadmin", "qloop@2026", "admin123"}


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "qloop"
    # 简短名称 (用于侧边栏 logo / 邮件主题前缀)
    # "qloop" = Quality + Loop, 寓意质量与闭环融合, 测试在开发中不断循环完善
    APP_SHORT_NAME: str = "qloop"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    # Refresh token 有效期(P1-9):默认 7 天,用于在 access token 过期后换取新 token
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://qloop:qloop@localhost:5432/qloop"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "qloop"
    MINIO_SECURE: bool = False

    # SMTP / Email (邮件通知配置,超管可在系统设置中开关)
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 25
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@qloop.local"
    SMTP_USE_TLS: bool = True

    # LLM
    LLM_TIMEOUT: int = 300
    LLM_MAX_RETRIES: int = 3
    # P2-2: max_tokens 配置化,可通过环境变量覆盖
    LLM_MAX_TOKENS_OPENAI: int = 8192
    LLM_MAX_TOKENS_ANTHROPIC: int = 4096

    # P2-10: 日志级别配置(可选 DEBUG/INFO/WARNING/ERROR)
    LOG_LEVEL: str = "INFO"

    # P2-11: CORS 允许的源(逗号分隔),通过环境变量配置
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost"

    # P2-12: DEBUG 模式开关(生产环境禁止开启,由 validator 强制校验)
    DEBUG: bool = False

    # 上传文件大小限制
    MAX_UPLOAD_SIZE_MB: int = 200  # 最大上传文件大小(MB)

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """生产环境禁止使用不安全的默认 SECRET_KEY。"""
        if v in INSECURE_DEFAULTS:
            import os
            env = os.getenv("ENV", "development").lower()
            if env == "production":
                raise ValueError("SECRET_KEY 不能使用默认值,请在 .env 中设置安全值")
        return v

    @field_validator("DEBUG")
    @classmethod
    def validate_debug(cls, v: bool) -> bool:
        """P2-12: 生产环境禁止开启 DEBUG 模式,避免暴露调试信息。"""
        import os
        env = os.getenv("ENV", "development").lower()
        if env == "production" and v:
            raise ValueError("生产环境不能开启 DEBUG 模式")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """P2-10: 校验日志级别合法性。"""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL 必须是 {allowed} 之一")
        return upper


settings = Settings()
