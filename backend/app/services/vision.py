"""图片理解：为物品照片生成 caption（供向量化）。

要点：本地 MinIO 图片在 DeepSeek 侧不可达，需取回字节转 base64 data URL 再送模型。
"""

from __future__ import annotations

import base64

from app.core.logging import get_logger
from app.services.llm import get_llm
from app.services.storage import fetch_bytes, key_from_url

logger = get_logger(__name__)

_CAPTION_PROMPT = (
    "用一句简洁中文描述这张物品照片的关键视觉特征：物品类别、颜色、品牌或文字、"
    "材质、磨损或独特标记。只输出描述本身，不要额外说明。"
)

# 单图上限：base64 会膨胀约 1/3，控制在请求体限制内
_MAX_BYTES = 8 * 1024 * 1024


def to_model_image(url: str) -> str | None:
    """把图片引用转成模型可访问的形式。

    - 本地存储的图片 → base64 data URL（DeepSeek 无法访问 localhost）
    - 外部 http(s) → 原样返回
    - 取不到或过大 → None
    """
    if key_from_url(url) is None:
        return url
    data = fetch_bytes(url)
    if not data:
        return None
    if len(data) > _MAX_BYTES:
        logger.warning("图片过大，跳过: %s bytes", len(data))
        return None
    # DeepSeek 按内容识别格式，MIME 可统一用 image/jpeg
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def to_model_images(urls: list[str]) -> list[str]:
    out: list[str] = []
    for url in urls:
        converted = to_model_image(url)
        if converted:
            out.append(converted)
    return out


async def caption_image(url: str) -> str:
    """为单张图片生成 caption；失败返回空串（不阻断登记）。"""
    target = to_model_image(url)
    if not target:
        return ""
    try:
        return (await get_llm().describe_image(_CAPTION_PROMPT, [target], thinking=False)).strip()
    except Exception as exc:  # noqa: BLE001 - caption 失败不应影响登记
        logger.warning("生成图片描述失败: %s", exc)
        return ""


async def caption_images(urls: list[str]) -> list[str]:
    """批量生成 caption（顺序执行，避免并发打爆限流）。"""
    out: list[str] = []
    for url in urls:
        out.append(await caption_image(url))
    return out
