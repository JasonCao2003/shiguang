"""BGE-M3 向量化服务。

DeepSeek API 不提供 embedding 接口，故自建本服务（PDR §6 / §10.1）。
- 模型：BAAI/bge-m3（1024 维，中文友好）
- 接口：POST /embed {texts:[...]} -> {embeddings:[[...]], dim}
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

# 必须在导入 sentence_transformers / huggingface_hub 之前设置镜像端点
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from sentence_transformers import SentenceTransformer  # noqa: E402

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
_model: SentenceTransformer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _model
    print(f"[embedding] loading model: {MODEL_NAME}")
    _model = SentenceTransformer(MODEL_NAME)
    if hasattr(_model, "get_sentence_embedding_dimension"):
        print(f"[embedding] dim = {_model.get_sentence_embedding_dimension()}")
    yield


app = FastAPI(title="Find Embedding Service", lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str] = Field(default_factory=list)


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    dim: int


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest) -> EmbedResponse:
    if not req.texts:
        return EmbedResponse(embeddings=[], dim=0)
    assert _model is not None, "模型未加载"
    vectors = _model.encode(
        req.texts, normalize_embeddings=True, batch_size=16
    )
    return EmbedResponse(embeddings=[v.tolist() for v in vectors], dim=len(vectors[0]))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": MODEL_NAME, "loaded": str(_model is not None)}
