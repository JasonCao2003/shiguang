"""应用配置（pydantic-settings，从环境变量 / .env 读取）。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 应用
    app_name: str = "拾光"
    environment: str = "dev"
    debug: bool = True
    # 是否打印 SQL（与 debug 解耦，避免日志刷屏）
    db_echo: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api"

    # 数据库
    database_url: str = "postgresql+asyncpg://shiguang:shiguang@localhost:5432/shiguang"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_reason_model: str = "deepseek-v4-pro"
    deepseek_thinking: bool = True

    # BGE-M3 向量化服务
    embedding_service_url: str = "http://localhost:8001"
    embedding_dim: int = 1024
    embedding_model: str = "BAAI/bge-m3"

    # 对象存储
    storage_backend: str = "s3"  # s3 | local
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "shiguang-media"
    s3_region: str = "us-east-1"
    s3_public_base: str = "http://localhost:9000"
    # 本地存储后端（STORAGE_BACKEND=local 时生效）
    local_media_dir: str = ".data/media"
    media_base_url: str = "http://localhost:8000/media"

    # 认证
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # 匹配参数
    match_recall_k: int = 20
    match_high_threshold: float = 0.75
    match_mid_threshold: float = 0.50

    # 数据留存
    retention_days_after_claim: int = 7

    # 可观测
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
