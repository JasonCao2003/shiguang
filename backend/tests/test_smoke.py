"""冒烟测试：应用可导入、路由已注册。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/api/items" in paths
    assert "/api/chat" in paths
    assert "/api/claims" in paths
    assert "/api/admin/claims" in paths
