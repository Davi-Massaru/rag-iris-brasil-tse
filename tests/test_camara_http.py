from __future__ import annotations

from datetime import date

import pytest
import requests
import responses

from app.config import Settings
from app.ingestion.camara import CamaraClient
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


def test_camara_client_caches_state_search_and_limits_recent_propositions() -> None:
    class HttpStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict | None]] = []

        def get_json(self, url, *, params=None, allowed_hosts=None):  # noqa: ANN001, ANN201
            del allowed_hosts
            self.calls.append((url, params))
            if url.endswith("/deputados"):
                return {
                    "dados": [
                        {
                            "id": 178987,
                            "uri": f"{url}/178987",
                            "nome": "Orlando Silva",
                            "siglaUf": "SP",
                        }
                    ],
                    "links": [],
                }
            return {
                "dados": [
                    {"id": value, "uri": f"{url}/{value}", "dataApresentacao": "2026-01-01"}
                    for value in (1, 2, 3)
                ],
                "links": [],
            }

    settings = Settings(
        _env_file=None,
        camara_max_propositions_per_candidate=2,
    )
    http = HttpStub()
    client = CamaraClient(settings, http)  # type: ignore[arg-type]

    assert client.search_deputies("ORLANDO SILVA", "SP")[0].id == 178987
    assert client.search_deputies("ORLANDO SILVA", "SP")[0].id == 178987
    propositions = list(client.propositions(178987))

    deputy_calls = [call for call in http.calls if call[0].endswith("/deputados")]
    proposition_call = next(call for call in http.calls if call[0].endswith("/proposicoes"))
    params = proposition_call[1] or {}
    assert len(deputy_calls) == 1
    assert len(propositions) == 2
    assert date.fromisoformat(params["dataFim"]) - date.fromisoformat(params["dataInicio"]) <= (
        date.resolution * 92
    )


def test_camara_client_reuses_deputy_detail_and_history() -> None:
    class HttpStub:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_json(self, url, *, params=None, allowed_hosts=None):  # noqa: ANN001, ANN201
            del params, allowed_hosts
            self.calls.append(url)
            if url.endswith("/historico"):
                return {"dados": [{"siglaPartido": "ABC"}], "links": []}
            return {
                "dados": {
                    "id": 99,
                    "nomeCivil": "NOME CIVIL",
                    "ultimoStatus": {"nome": "NOME", "siglaUf": "SP"},
                },
                "links": [],
            }

    http = HttpStub()
    client = CamaraClient(Settings(_env_file=None), http)  # type: ignore[arg-type]

    assert client.deputy(99) is client.deputy(99)
    assert client.history(99) is client.history(99)
    assert len([url for url in http.calls if url.endswith("/deputados/99")]) == 1
    assert len([url for url in http.calls if url.endswith("/historico")]) == 1
