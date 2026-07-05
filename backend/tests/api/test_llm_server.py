from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import llm_server


def test_normalize_base_url_rejects_unsafe_values():
    with pytest.raises(ValueError):
        llm_server._normalize_base_url("")
    with pytest.raises(ValueError):
        llm_server._normalize_base_url("ftp://127.0.0.1:18080")
    with pytest.raises(ValueError):
        llm_server._normalize_base_url("http://user:pass@127.0.0.1:18080")

    assert llm_server._normalize_base_url("http://127.0.0.1:18080/") == "http://127.0.0.1:18080"


def _test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(llm_server.router)
    return app


def test_login_proxy_unwraps_sub2api_response(monkeypatch):
    captured: dict = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, **kwargs):
            captured.update({"method": method, "url": url, "headers": kwargs.get("headers")})
            return httpx.Response(
                200,
                json={"code": 0, "message": "success", "data": {"access_token": "tok"}},
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr(llm_server, "_current_base_url", lambda: "http://127.0.0.1:18080")
    monkeypatch.setattr(llm_server.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(_test_app())
    resp = client.post("/api/llm-server/auth/login", json={"email": "u@example.com", "password": "pw"})

    assert resp.status_code == 200
    assert resp.json() == {"access_token": "tok"}
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:18080/api/v1/auth/login"


def test_profile_requires_sub2api_token():
    client = TestClient(_test_app())
    resp = client.get("/api/llm-server/user/profile")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "请先登录 LLM 服务账户"


def test_create_key_proxy_preserves_group_id(monkeypatch):
    captured: dict = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, **kwargs):
            captured.update({
                "method": method,
                "url": url,
                "headers": kwargs.get("headers"),
                "content": kwargs.get("content"),
            })
            return httpx.Response(
                200,
                json={"code": 0, "message": "success", "data": {"id": 1, "name": "OpenTDX", "group_id": 2}},
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr(llm_server, "_current_base_url", lambda: "http://127.0.0.1:18080")
    monkeypatch.setattr(llm_server.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(_test_app())
    resp = client.post(
        "/api/llm-server/keys",
        headers={"Authorization": "Bearer tok"},
        json={"name": "OpenTDX", "group_id": 2},
    )

    assert resp.status_code == 200
    assert resp.json()["group_id"] == 2
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:18080/api/v1/keys"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert json.loads(captured["content"]) == {"name": "OpenTDX", "group_id": 2}
