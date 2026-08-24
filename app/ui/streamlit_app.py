from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:52773/api").rstrip("/")
REQUEST_TIMEOUT = (5, 120)


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
    st.subheader("Fontes")
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


def main() -> None:
    st.set_page_config(page_title="IRIS Political Insight", page_icon="🏛️")
    st.title("IRIS Political Insight")
    st.caption("Respostas baseadas em dados oficiais do TSE e da Câmara dos Deputados.")
    try:
        labels, mapping = candidate_options()
    except requests.RequestException as exc:
        st.error(f"API indisponível: {exc}")
        st.stop()
    selected = st.selectbox("Candidato", labels)
    question = st.text_area(
        "Pergunta",
        placeholder="Quais propostas e atuações públicas constam nas fontes indexadas?",
    )
    if st.button("Perguntar", type="primary", disabled=not question.strip()):
        payload = {"question": question.strip(), "candidateId": mapping[selected]}
        try:
            with st.spinner("Consultando as fontes..."):
                result = api_post("/ask", payload)
            candidate = result.get("candidate")
            if candidate:
                st.caption(
                    f"Resposta sobre {candidate['name']} — "
                    f"{candidate.get('party') or 'sem partido'} / {candidate['state']}"
                )
            st.markdown(result["answer"])
            render_sources(result.get("sources", []))
        except requests.RequestException as exc:
            st.error(f"Não foi possível consultar a API: {exc}")


if __name__ == "__main__":
    main()
