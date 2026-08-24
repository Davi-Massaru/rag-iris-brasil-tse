from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:52773/api").rstrip("/")
REQUEST_TIMEOUT = (5, 120)
QUESTION_PLACEHOLDER = "Pergunte sobre propostas, atuação pública ou histórico político"


def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def candidate_options() -> tuple[list[str], dict[str, int | None]]:
    values = api_get("/candidates").get("items", [])
    mapping: dict[str, int | None] = {"Todos os candidatos": None}
    for item in values:
        identity = item.get("ballot_name") or item["name"]
        number = f" · nº {item['candidate_number']}" if item.get("candidate_number") else ""
        label = (
            f"{identity} — {item['office']} — "
            f"{item.get('party') or 'sem partido'} / {item['state']}{number}"
        )
        mapping[label] = int(item["id"])
    return list(mapping), mapping


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
        labels, mapping = candidate_options()
    except requests.RequestException as exc:
        st.error(
            "A consulta está indisponível no momento. "
            "Verifique se a API está ativa e tente novamente."
        )
        st.caption(f"Detalhes técnicos: {exc}")
        st.stop()

    selected = st.selectbox(
        "Filtrar por candidato",
        labels,
        help="Escolha um candidato ou mantenha a busca em toda a base indexada.",
    )

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

        payload = {"question": normalized_question, "candidateId": mapping[selected]}
        try:
            with st.spinner("Consultando fontes oficiais..."):
                render_answer(api_post("/ask", payload))
        except requests.RequestException as exc:
            st.error("Não foi possível concluir a consulta. Tente novamente em alguns instantes.")
            st.caption(f"Detalhes técnicos: {exc}")


if __name__ == "__main__":
    main()
