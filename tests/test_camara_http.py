from __future__ import annotations

import pytest
import requests
import responses

from app.ingestion.camara.contracts import Link
from app.ingestion.camara.pagination import next_url
from app.ingestion.http import ExternalContractError, HttpClient

pytestmark = pytest.mark.unit


def test_next_link_must_remain_on_official_host() -> None:
    with pytest.raises(ExternalContractError, match="unsafe Câmara"):
        next_url((Link(rel="next", href="https://example.org/page/2"),))


@responses.activate
def test_http_400_is_not_retried() -> None:
    url = "https://dadosabertos.camara.leg.br/api/v2/deputados"
    responses.add(responses.GET, url, status=400)
    client = HttpClient(1, 1, 4)

    with pytest.raises(requests.HTTPError):
        client.get(url, allowed_hosts={"dadosabertos.camara.leg.br"})

    assert len(responses.calls) == 1


def test_http_rejects_plain_http_before_request() -> None:
    client = HttpClient(1, 1, 1)

    with pytest.raises(ExternalContractError, match="unsafe external URL"):
        client.get(
            "http://dadosabertos.camara.leg.br/api/v2/deputados",
            allowed_hosts={"dadosabertos.camara.leg.br"},
        )
