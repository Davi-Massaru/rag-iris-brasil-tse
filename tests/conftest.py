from __future__ import annotations

import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        iris_host="localhost",
        iris_namespace="IRISAPP",
        iris_username="_SYSTEM",
        iris_password="SYS",
        llm_api_key="test-key",
    )
