from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

pytestmark = pytest.mark.unit


def values() -> dict:
    return {
        "_env_file": None,
        "iris_host": "localhost",
        "iris_namespace": "IRISAPP",
        "iris_username": "_SYSTEM",
        "iris_password": "SYS",
    }


def test_settings_parse_csv_lists() -> None:
    settings = Settings(**values(), ingest_states="sp,rj", ingest_offices="governador")

    assert settings.ingest_states == ("SP", "RJ")
    assert settings.ingest_offices == ("GOVERNADOR",)


def test_settings_enable_hybrid_iris_access_by_default() -> None:
    assert Settings(**values()).iris_data_access_mode == "hybrid"


def test_settings_cover_all_current_camara_matches_by_default() -> None:
    assert Settings(**values()).camara_max_matched_candidates == 50
    assert Settings(**values()).camara_http_workers == 6


def test_settings_reject_vector_dimension_different_from_class() -> None:
    with pytest.raises(ValidationError, match="PoliticalChunk"):
        Settings(**values(), embedding_dimension=768)


def test_settings_reject_unofficial_source_host() -> None:
    with pytest.raises(ValidationError, match="dadosabertos.tse.jus.br"):
        Settings(**values(), tse_ckan_base_url="https://example.org/api")


def test_settings_reject_unbounded_camara_limits() -> None:
    with pytest.raises(ValidationError):
        Settings(**values(), camara_max_matched_candidates=101)
    with pytest.raises(ValidationError):
        Settings(**values(), camara_max_propositions_per_candidate=0)
    with pytest.raises(ValidationError):
        Settings(**values(), camara_max_authors_per_proposition=101)
    with pytest.raises(ValidationError):
        Settings(**values(), camara_http_workers=17)
