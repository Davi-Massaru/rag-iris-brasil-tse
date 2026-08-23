from __future__ import annotations

from urllib.parse import urlparse

from app.ingestion.http import ExternalContractError

from .contracts import Link


def next_url(links: tuple[Link, ...]) -> str | None:
    link = next((item for item in links if item.rel == "next"), None)
    if link is None:
        return None
    parsed = urlparse(link.href)
    if parsed.scheme != "https" or parsed.hostname != "dadosabertos.camara.leg.br":
        raise ExternalContractError("unsafe Câmara pagination URL")
    return link.href
