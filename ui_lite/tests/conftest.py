from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import EXAMPLE_PATH, load_settings
from app.main import create_app
from mock_backend import server as mock


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SSE_API_HOST", "http://backend")
    return load_settings(EXAMPLE_PATH)


@pytest.fixture
def backend_log():
    mock.REQUEST_LOG.clear()
    mock.CHATS.clear()
    return mock.REQUEST_LOG


@pytest.fixture
def client(settings, backend_log):
    app = create_app(settings, transport=httpx.ASGITransport(app=mock.app))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def logged(client):
    r = client.post("/login", data={"username": "anna", "password": "demo"}, follow_redirects=False)
    assert r.status_code == 303
    return client


def calls(log, path_end):
    return [e for e in log if e["path"].endswith("/" + path_end)]
