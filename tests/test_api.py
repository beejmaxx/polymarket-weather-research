from __future__ import annotations

from fastapi.testclient import TestClient

from pwmk.api.app import create_app


def test_api_token_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PWMK_DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("PWMK_API_TOKEN", "secret")
    monkeypatch.setenv("PWMK_ENABLE_SCHEDULER", "false")

    with TestClient(create_app()) as client:
        assert client.get("/api/summary").status_code == 401
        response = client.get("/api/summary", headers={"X-API-Key": "secret"})

    assert response.status_code == 200
