"""图片上传路由。"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.services.storage import upload_bytes

router = APIRouter(prefix="/uploads", tags=["uploads"])

_ALLOWED = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@router.post("")
async def upload_image(file: UploadFile = File(...)) -> dict[str, str]:
    if file.content_type not in _ALLOWED:
        from fastapi import HTTPException, status

        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持 JPEG/PNG/GIF/WebP")
    data = await file.read()
    url = upload_bytes(data, content_type=file.content_type or "image/jpeg")
    return {"url": url}
