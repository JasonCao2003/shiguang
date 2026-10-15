"""DeepSeek API 客户端。

DeepSeek 兼容 OpenAI 协议，Base URL 为 https://api.deepseek.com。
- deepseek-flash：支持图片输入 + 文本 + JSON 输出（多模态）
- deepseek-v4-pro：文本重推理（不支持视觉）

参考 PDR §10.1。
"""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DeepSeekClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = settings.deepseek_model
        self.reason_model = settings.deepseek_reason_model

    def _extra_body(self, thinking: bool | None) -> dict[str, Any]:
        want = settings.deepseek_thinking if thinking is None else thinking
        # 显式关闭思考模式以省成本/降延迟；开启时由服务端默认处理
        return {} if want else {"thinking": {"type": "disabled"}}

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        thinking: bool | None = None,
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            extra_body=self._extra_body(thinking),
        )
        return resp.choices[0].message.content or ""

    async def complete_json(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        resp = await self._client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
            extra_body=self._extra_body(thinking),
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("DeepSeek 返回非法 JSON: %s", raw[:200])
            return {}

    async def describe_image(
        self, prompt: str, image_urls: list[str], *, thinking: bool | None = None
    ) -> str:
        """图片理解（deepseek-flash）。图片仅允许出现在 user 消息中。"""
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        return await self.complete(
            [{"role": "user", "content": content}],
            model=self.model,
            thinking=thinking,
        )


_client: DeepSeekClient | None = None


def get_llm() -> DeepSeekClient:
    global _client
    if _client is None:
        _client = DeepSeekClient()
    return _client
