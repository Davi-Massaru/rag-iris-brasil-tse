from __future__ import annotations

from collections.abc import Sequence

from app.domain import SearchResult

POLICY = """Você responde sobre dados políticos brasileiros.
Use somente as evidências fornecidas.
Não invente fatos, recomende voto, avalie candidato ou determine ideologia.
Diferencie fato de inferência.
Não trate ausência de informação como evidência de ausência.
Quando o contexto for insuficiente, declare explicitamente a insuficiência.
Cite as evidências pelos identificadores [E1], [E2] etc.
Responda em português do Brasil."""


def build_prompt(question: str, evidence: Sequence[SearchResult]) -> str:
    blocks = [
        f"[E{index}]\nTítulo: {item.title}\nTipo: {item.source_type}\nFonte: {item.source_url}\nTrecho: {item.content}"
        for index, item in enumerate(evidence, 1)
    ]
    return f"Pergunta: {question}\n\nEvidências:\n\n" + "\n\n".join(blocks)
