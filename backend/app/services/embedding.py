"""BGE-M3 向量化客户端。

DeepSeek 不提供 embedding 接口，故自建 BGE-M3 服务（见 embedding_service/）。
此客户端通过 HTTP 调用该服务。
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.embedding_service_url).rstrip("/")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.base_url}/embed", json={"texts": texts})
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"]

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0] if vectors else []

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False


_client: EmbeddingClient | None = None


def get_embedder() -> EmbeddingClient:
    global _client
    if _client is None:
        _client = EmbeddingClient()
    return _client
