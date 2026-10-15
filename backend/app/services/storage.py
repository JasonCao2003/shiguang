"""对象存储（MinIO / S3）。"""

from __future__ import annotations

import uuid
from functools import lru_cache

import boto3
from botocore.client import Config

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:  # noqa: BLE001 - bucket 不存在时创建
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("创建 bucket: %s", settings.s3_bucket)


def upload_bytes(data: bytes, *, content_type: str, key: str | None = None) -> str:
    """上传字节流，返回可访问 URL。"""
    key = key or f"items/{uuid.uuid4().hex}"
    ensure_bucket()
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return public_url(key)


def public_url(key: str) -> str:
    return f"{settings.s3_public_base.rstrip('/')}/{settings.s3_bucket}/{key}"
