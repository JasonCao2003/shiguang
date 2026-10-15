"""对象存储：支持 S3/MinIO 与本地文件系统两种后端。

- STORAGE_BACKEND=s3    → 使用 MinIO / S3（生产）
- STORAGE_BACKEND=local → 存到本地目录并由后端 /media 静态提供（开发/无 S3）
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.client import Config

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _use_local() -> bool:
    return settings.storage_backend.lower() == "local"


def _local_dir() -> Path:
    directory = Path(settings.local_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


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
    if _use_local():
        _local_dir()
        logger.info("使用本地文件存储: %s", settings.local_media_dir)
        return
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:  # noqa: BLE001 - bucket 不存在时创建
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("创建 bucket: %s", settings.s3_bucket)


def _url_prefix() -> str:
    if _use_local():
        return f"{settings.media_base_url.rstrip('/')}/"
    return f"{settings.s3_public_base.rstrip('/')}/{settings.s3_bucket}/"


def public_url(key: str) -> str:
    return f"{_url_prefix()}{key}"


def key_from_url(url: str) -> str | None:
    """从公开 URL 反解对象 key；非本存储的 URL 返回 None（视为外部图片）。"""
    prefix = _url_prefix()
    return url[len(prefix) :] if url.startswith(prefix) else None


def upload_bytes(data: bytes, *, content_type: str, key: str | None = None) -> str:
    """上传字节流，返回可访问 URL。"""
    key = key or f"items/{uuid.uuid4().hex}"
    if _use_local():
        path = _local_dir() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return public_url(key)

    ensure_bucket()
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return public_url(key)


def fetch_bytes(url: str) -> bytes | None:
    """按公开 URL 取回对象字节（本地图片需转 base64 送模型）。"""
    key = key_from_url(url)
    if not key:
        return None
    try:
        if _use_local():
            return (_local_dir() / key).read_bytes()
        obj = _client().get_object(Bucket=settings.s3_bucket, Key=key)
        return obj["Body"].read()
    except Exception as exc:  # noqa: BLE001 - 取不到就跳过 caption
        logger.warning("读取图片失败 key=%s: %s", key, exc)
        return None
