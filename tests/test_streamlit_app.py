from __future__ import annotations

from typing import Any

import pytest
import requests

from app.ui import streamlit_app as ui

pytestmark = pytest.mark.unit

CANDIDATE = {
    "id": 1,
    "tse_id": "TSE1",
    "name": "MARIA SILVA",
    "ballot_name": "MARIA",
    "party": "ABC",
    "party_number": 10,
    "office": "DEPUTADO FEDERAL",
    "state": "SP",
    "candidate_number": 1010,
    "camara_deputy_id": 99,
    "match_status": "MATCHED",
    "match_confidence": 100.0,
    "source_url": "https://dadosabertos.tse.jus.br/fonte",
}
PROPOSITION = {
    "id": 8,
    "camaraId": 900,
    "type": "PL",
    "number": 10,
    "year": 2026,
    "title": "PL 10/2026",
    "summary": "Amplia o acesso à educação.",
    "detailedSummary": "Detalhamento da proposta.",
    "presentationDate": "2026-02-10",
    "status": "Em análise",
    "sourceUrl": "https://dadosabertos.camara.leg.br/fonte",
}


class FakeContainer:
    def __init__(self, selected: int | None = None) -> None:
        self.selected = selected
        self.options: list[int | None] = []
        self.labels: list[str] = []
        self.messages: list[tuple[str, str]] = []
        self.links: list[tuple[str, str]] = []

    def __enter__(self) -> FakeContainer:
        return self

    def __exit__(self, *_args: Any) -> None:
        pass

    def header(self, value: str) -> None:
        self.messages.append(("header", value))

    def subheader(self, value: str) -> None:
        self.messages.append(("subheader", value))

    def markdown(self, value: str) -> None:
        self.messages.append(("markdown", value))

    def caption(self, value: str) -> None:
        self.messages.append(("caption", value))

    def write(self, value: str) -> None:
        self.messages.append(("write", value))

    def info(self, value: str) -> None:
        self.messages.append(("info", value))

    def error(self, value: str) -> None:
        self.messages.append(("error", value))

    def divider(self) -> None:
        self.messages.append(("divider", ""))

    def expander(self, label: str) -> FakeContainer:
        self.messages.append(("expander", label))
        return self

    def link_button(self, label: str, url: str) -> None:
        self.links.append((label, url))

    def selectbox(
        self,
        _label: str,
        options: list[int | None],
        *,
        format_func: Any,
        help: str,
    ) -> int | None:
        assert help
        self.options = options
        self.labels = [format_func(value) for value in options]
        return self.selected


class FakeStreamlit:
    def __init__(self, question: str) -> None:
        self.question = question
        self.messages: list[tuple[str, str]] = []

    def set_page_config(self, **_kwargs: Any) -> None:
        pass

    def title(self, value: str) -> None:
        self.messages.append(("title", value))

    def caption(self, value: str) -> None:
        self.messages.append(("caption", value))

    def markdown(self, value: str, **_kwargs: Any) -> None:
        self.messages.append(("markdown", value))

    def write(self, value: str) -> None:
        self.messages.append(("write", value))

    def error(self, value: str) -> None:
        self.messages.append(("error", value))

    def chat_input(self, *_args: Any, **_kwargs: Any) -> str:
        return self.question

    def chat_message(self, *_args: Any, **_kwargs: Any) -> FakeStreamlit:
        return self

    def spinner(self, *_args: Any, **_kwargs: Any) -> FakeStreamlit:
        return self

    def __enter__(self) -> FakeStreamlit:
        return self

    def __exit__(self, *_args: Any) -> None:
        pass


def test_candidate_index_preserves_distinct_ids_for_equal_labels() -> None:
    second = {**CANDIDATE, "id": 2, "tse_id": "TSE2"}

    indexed = ui.candidate_index([CANDIDATE, second])

    assert list(indexed) == [1, 2]
    assert ui.candidate_label(indexed[1]) == ui.candidate_label(indexed[2])


def test_candidate_selector_uses_main_area_and_preserves_distinct_ids(monkeypatch) -> None:  # noqa: ANN001
    second = {**CANDIDATE, "id": 2, "tse_id": "TSE2"}
    container = FakeContainer(selected=2)
    monkeypatch.setattr(ui, "st", container)

    selected = ui.render_candidate_selector([CANDIDATE, second])

    assert selected == 2
    assert container.options == [None, 1, 2]
    assert container.labels[0] == ui.GLOBAL_CANDIDATE_LABEL
    assert container.labels[1] == container.labels[2]


def test_sidebar_loads_selected_candidate_and_propositions(monkeypatch) -> None:  # noqa: ANN001
    container = FakeContainer()
    requested_profiles: list[int] = []
    requested_propositions: list[int] = []
    monkeypatch.setattr(ui.st, "sidebar", container)

    def load_profile(candidate_id: int) -> dict[str, Any]:
        requested_profiles.append(candidate_id)
        return CANDIDATE

    def load_propositions(candidate_id: int) -> list[dict[str, Any]]:
        requested_propositions.append(candidate_id)
        return [PROPOSITION]

    monkeypatch.setattr(ui, "load_candidate", load_profile)
    monkeypatch.setattr(ui, "load_candidate_propositions", load_propositions)

    ui.render_candidate_sidebar(1)

    assert requested_profiles == [1]
    assert requested_propositions == [1]
    rendered = "\n".join(value for _kind, value in container.messages)
    for expected in (
        "MARIA SILVA",
        "DEPUTADO FEDERAL",
        "ABC",
        "1010",
        "Vínculo confirmado",
        "100.0%",
        "TSE1",
        "99",
        "MATCHED",
        "Propostas (1)",
        "PL 10/2026",
        "Amplia o acesso à educação.",
        "Em análise",
    ):
        assert expected in rendered
    assert container.links == [
        ("Abrir fonte oficial", "https://dadosabertos.tse.jus.br/fonte"),
        ("Abrir proposta oficial", "https://dadosabertos.camara.leg.br/fonte"),
    ]


def test_candidate_detail_failure_is_local_to_sidebar(monkeypatch) -> None:  # noqa: ANN001
    container = FakeContainer()
    monkeypatch.setattr(ui.st, "sidebar", container)

    def unavailable(_candidate_id: int) -> dict[str, Any]:
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(ui, "load_candidate", unavailable)

    ui.render_candidate_sidebar(1)
    assert (
        "error",
        "Não foi possível carregar o perfil do candidato selecionado.",
    ) in container.messages


@pytest.mark.parametrize("candidate_id", [None, 1])
def test_main_sends_sidebar_candidate_id_to_ask(monkeypatch, candidate_id) -> None:  # noqa: ANN001
    fake_st = FakeStreamlit("  Quais são as propostas?  ")
    payloads: list[dict[str, Any]] = []
    sidebar_calls: list[int] = []

    monkeypatch.setattr(ui, "st", fake_st)
    monkeypatch.setattr(ui, "load_candidates", lambda: [CANDIDATE])
    monkeypatch.setattr(ui, "render_candidate_selector", lambda _values: candidate_id)
    monkeypatch.setattr(ui, "render_candidate_sidebar", sidebar_calls.append)

    def post(_path: str, payload: dict[str, Any]) -> dict[str, Any]:
        payloads.append(payload)
        return {"answer": "Resposta", "sources": []}

    monkeypatch.setattr(ui, "api_post", post)

    ui.main()

    assert payloads == [
        {"question": "Quais são as propostas?", "candidateId": candidate_id}
    ]
    assert sidebar_calls == ([] if candidate_id is None else [candidate_id])
    assert ("title", "TSE Public Data RAG Explorer") in fake_st.messages


def test_profile_formats_missing_values_and_rejects_invalid_source() -> None:
    container = FakeContainer()
    candidate: dict[str, Any] = {key: None for key in CANDIDATE}
    candidate.update({"id": 1, "name": "CANDIDATO", "source_url": "javascript:alert(1)"})

    ui.render_candidate_profile(container, candidate)

    rendered = "\n".join(value for _kind, value in container.messages)
    assert ui.NOT_INFORMED in rendered
    assert "Fonte informada: javascript:alert(1)" in rendered
    assert container.links == []
