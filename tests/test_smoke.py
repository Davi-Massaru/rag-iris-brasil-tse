from __future__ import annotations

import os

import pytest
import requests

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.getenv("RUN_SMOKE_TESTS") != "1",
        reason="set RUN_SMOKE_TESTS=1 with Docker Compose running",
    ),
]


def test_api_health() -> None:
    response = requests.get("http://localhost:52773/api/health", timeout=10)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_streamlit_health() -> None:
    response = requests.get("http://localhost:8501/_stcore/health", timeout=10)

    assert response.status_code == 200
    assert response.text.strip() == "ok"
