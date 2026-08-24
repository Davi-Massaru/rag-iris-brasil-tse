from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:52773/api").rstrip("/")
REQUEST_TIMEOUT = (5, 120)
QUESTION_PLACEHOLDER = "Pergunte sobre propostas, atuação pública ou histórico político"
CACHE_TTL_SECONDS = 60
GLOBAL_CANDIDATE_LABEL = "Todos os candidatos"
NOT_INFORMED = "Não informado"

MATCH_STATUS_LABELS = {
    "MATCHED": "Vínculo confirmado com a Câmara",
    "REVIEW": "Vínculo pendente de revisão",
    "UNMATCHED": "Sem vínculo confirmado com a Câmara",
}


class ApiPayloadError(ValueError):
    """Raised when the API response does not satisfy the UI contract."""


def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_candidates() -> list[dict[str, Any]]:
    payload = api_get("/candidates")
    values = payload.get("items")
    if not isinstance(values, list):
        raise ApiPayloadError("GET /candidates returned an invalid items collection")
    if any(not isinstance(item, dict) for item in values):
        raise ApiPayloadError("GET /candidates returned an invalid candidate")
    return values


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_candidate(candidate_id: int) -> dict[str, Any]:
    payload = api_get(f"/candidates/{candidate_id}")
    if not isinstance(payload, dict) or int(payload.get("id", 0)) != candidate_id:
        raise ApiPayloadError("GET /candidates/{id} returned an invalid candidate")
    return payload


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_candidate_propositions(candidate_id: int) -> list[dict[str, Any]]:
    payload = api_get(f"/candidates/{candidate_id}/propositions")
    values = payload.get("items")
    if not isinstance(values, list):
        raise ApiPayloadError(
            "GET /candidates/{id}/propositions returned an invalid items collection"
        )
    if any(not isinstance(item, dict) for item in values):
        raise ApiPayloadError("GET /candidates/{id}/propositions returned an invalid proposition")
    return values


def candidate_index(values: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for item in values:
        try:
            candidate_id = int(item["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiPayloadError("candidate without a valid id") from exc
        if candidate_id <= 0:
            raise ApiPayloadError("candidate without a valid id")
        indexed[candidate_id] = item
    return indexed


def candidate_label(candidate: dict[str, Any]) -> str:
    identity = candidate.get("ballot_name") or candidate.get("name") or NOT_INFORMED
    office = candidate.get("office") or NOT_INFORMED
    party = candidate.get("party") or "sem partido"
    state = candidate.get("state") or "UF não informada"
    number = (
        f" · nº {candidate['candidate_number']}" if candidate.get("candidate_number") else ""
    )
    return f"{identity} — {office} — {party} / {state}{number}"


def format_optional(value: Any) -> str:
    return str(value) if value not in (None, "") else NOT_INFORMED


def format_match_status(value: Any) -> str:
    normalized = str(value).upper() if value not in (None, "") else ""
    return MATCH_STATUS_LABELS.get(normalized, format_optional(value))


def format_confidence(value: Any) -> str:
    if value in (None, ""):
        return NOT_INFORMED
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def valid_web_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def proposition_label(proposition: dict[str, Any]) -> str:
    if proposition.get("title"):
        return str(proposition["title"])
    stem = " ".join(
        str(value) for value in (proposition.get("type"), proposition.get("number")) if value
    )
    year = proposition.get("year")
    if stem and year:
        return f"{stem}/{year}"
    return stem or (f"Proposição {proposition['camaraId']}" if proposition.get("camaraId") else "Proposição")


def render_candidate_profile(container: Any, candidate: dict[str, Any]) -> None:
    identity = candidate.get("ballot_name") or candidate.get("name") or NOT_INFORMED
    container.subheader("Perfil do candidato")
    container.markdown(f"### {identity}")
    container.caption(f"Nome completo: {format_optional(candidate.get('name'))}")
    container.write(
        f"**Cargo e UF:** {format_optional(candidate.get('office'))} · "
        f"{format_optional(candidate.get('state'))}"
    )
    container.write(
        f"**Partido:** {format_optional(candidate.get('party'))} · "
        f"nº {format_optional(candidate.get('party_number'))}"
    )
    container.write(f"**Número do candidato:** {format_optional(candidate.get('candidate_number'))}")
    container.write(f"**Vínculo:** {format_match_status(candidate.get('match_status'))}")
    container.write(
        "**Confiança do vínculo:** "
        f"{format_confidence(candidate.get('match_confidence'))}"
    )
    container.caption("A confiança mede apenas a resolução técnica de identidade TSE–Câmara.")

    with container.expander("Identificadores"):
        container.write(f"**ID interno:** {format_optional(candidate.get('id'))}")
        container.write(f"**ID TSE:** {format_optional(candidate.get('tse_id'))}")
        container.write(
            f"**ID Câmara:** {format_optional(candidate.get('camara_deputy_id'))}"
        )
        container.write(
            f"**Status técnico:** {format_optional(candidate.get('match_status'))}"
        )

    source_url = valid_web_url(candidate.get("source_url"))
    if source_url:
        container.link_button("Abrir fonte oficial", source_url)
    elif candidate.get("source_url"):
        container.caption(f"Fonte informada: {candidate['source_url']}")


def render_candidate_propositions(
    container: Any, propositions: list[dict[str, Any]]
) -> None:
    container.divider()
    container.subheader(f"Propostas ({len(propositions)})")
    if not propositions:
        container.info("Não há proposições armazenadas para este candidato.")
        return

    for proposition in propositions:
        details = container.expander(proposition_label(proposition))
        status = format_optional(proposition.get("status"))
        presentation_date = format_optional(proposition.get("presentationDate"))
        details.caption(f"Situação: {status} · Apresentação: {presentation_date}")
        content = proposition.get("summary") or proposition.get("detailedSummary")
        details.write(format_optional(content))
        identifiers = []
        if proposition.get("camaraId"):
            identifiers.append(f"Câmara: {proposition['camaraId']}")
        if proposition.get("id"):
            identifiers.append(f"ID interno: {proposition['id']}")
        if identifiers:
            details.caption(" · ".join(identifiers))
        source_url = valid_web_url(proposition.get("sourceUrl"))
        if source_url:
            details.link_button("Abrir proposta oficial", source_url)


def render_candidate_selector(values: list[dict[str, Any]]) -> int | None:
    indexed = candidate_index(values)
    options: list[int | None] = [None, *indexed]

    selected_candidate_id = st.selectbox(
        "Filtrar por candidato",
        options,
        format_func=lambda candidate_id: (
            GLOBAL_CANDIDATE_LABEL
            if candidate_id is None
            else candidate_label(indexed[candidate_id])
        ),
        help="Escolha um candidato ou mantenha a busca em toda a base indexada.",
    )

    if not indexed:
        st.info("Nenhum candidato foi carregado. A consulta abrangerá toda a base.")
        return None
    return selected_candidate_id


def render_candidate_sidebar(candidate_id: int) -> None:
    container = st.sidebar

    try:
        profile = load_candidate(candidate_id)
    except (requests.RequestException, ApiPayloadError, TypeError, ValueError) as exc:
        container.error("Não foi possível carregar o perfil do candidato selecionado.")
        container.caption(f"Detalhes técnicos: {exc}")
        return

    render_candidate_profile(container, profile)
    try:
        propositions = load_candidate_propositions(candidate_id)
    except (requests.RequestException, ApiPayloadError, TypeError, ValueError) as exc:
        container.error("Não foi possível carregar as propostas do candidato selecionado.")
        container.caption(f"Detalhes técnicos: {exc}")
        return
    render_candidate_propositions(container, propositions)


def render_sources(sources: list[dict[str, Any]]) -> None:
    if not sources:
        return
    st.markdown("#### Fontes consultadas")
    for position, source in enumerate(sources, 1):
        evidence_id = source.get("evidenceId") or f"E{position}"
        title = source.get("title") or "Fonte"
        with st.expander(f"[{evidence_id}] {title}"):
            metadata = source.get("metadata") or {}
            details = [source.get("sourceType")]
            if metadata.get("fileName"):
                details.append(metadata["fileName"])
            if metadata.get("pageStart"):
                pages = str(metadata["pageStart"])
                if metadata.get("pageEnd") and metadata["pageEnd"] != metadata["pageStart"]:
                    pages += f"–{metadata['pageEnd']}"
                details.append(f"página(s) {pages}")
            st.caption(" · ".join(str(item) for item in details if item))
            st.write(source.get("content", ""))
            if source.get("sourceUrl"):
                st.link_button("Abrir fonte oficial", source["sourceUrl"])


def render_answer(result: dict[str, Any]) -> None:
    candidate = result.get("candidate")
    with st.chat_message("assistant", avatar="🏛️"):
        if candidate:
            st.caption(
                f"Resposta sobre {candidate['name']} · "
                f"{candidate.get('party') or 'sem partido'} / {candidate['state']}"
            )
        st.markdown(result["answer"])
        render_sources(result.get("sources", []))


def main() -> None:
    st.set_page_config(page_title="IRIS Political Insight", page_icon="🏛️")
    st.title("IRIS Political Insight")
    st.caption(
        "Consulte propostas e atuações políticas com respostas baseadas em fontes oficiais "
        "do TSE e da Câmara dos Deputados."
    )
    try:
        candidates = load_candidates()
        selected_candidate_id = render_candidate_selector(candidates)
    except (requests.RequestException, ApiPayloadError, TypeError, ValueError) as exc:
        st.error(
            "A consulta está indisponível no momento. "
            "Verifique se a API está ativa e tente novamente."
        )
        st.caption(f"Detalhes técnicos: {exc}")
        st.stop()

    if selected_candidate_id is not None:
        render_candidate_sidebar(selected_candidate_id)

    st.markdown("### Faça sua pergunta")
    st.caption("Pressione **Enter** para enviar · use **Shift + Enter** para quebrar a linha.")
    question = st.chat_input(
        QUESTION_PLACEHOLDER,
        key="political_question",
        max_chars=4_000,
    )

    if question and question.strip():
        normalized_question = question.strip()
        with st.chat_message("user"):
            st.write(normalized_question)

        payload = {"question": normalized_question, "candidateId": selected_candidate_id}
        try:
            with st.spinner("Consultando fontes oficiais..."):
                render_answer(api_post("/ask", payload))
        except requests.RequestException as exc:
            st.error("Não foi possível concluir a consulta. Tente novamente em alguns instantes.")
            st.caption(f"Detalhes técnicos: {exc}")


if __name__ == "__main__":
    main()
