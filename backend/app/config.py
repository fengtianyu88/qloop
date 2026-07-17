"""Application configuration using pydantic-settings."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "项目开发测试管理系统"
    # 简短名称 (用于侧边栏 logo / 邮件主题前缀), 不含「系统」二字
    APP_SHORT_NAME: str = "项目开发测试"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://bms:bms@localhost:5432/bms_sox"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "bms-sox"
    MINIO_SECURE: bool = False

    # SMTP / Email
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 25
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@bms-sox.local"

    # LLM
    LLM_TIMEOUT: int = 300
    LLM_MAX_RETRIES: int = 3


settings = Settings()
