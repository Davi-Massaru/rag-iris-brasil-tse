from __future__ import annotations

import random
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import requests
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter


class ExternalContractError(ValueError):
    pass


class RetryableHttpError(requests.HTTPError):
    pass


class HttpClient:
    RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        connect_timeout: int,
        read_timeout: int,
        max_attempts: int,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = (connect_timeout, read_timeout)
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "tse-public-data-rag-explorer/1.0"}
        )
        self.retrying = Retrying(
            stop=stop_after_attempt(max_attempts),
            wait=self._wait,
            retry=retry_if_exception_type(
                (requests.ConnectionError, requests.Timeout, RetryableHttpError)
            ),
            reraise=True,
        )

    def get(
        self,
        url: str,
        *,
        allowed_hosts: set[str],
        params: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> requests.Response:
        self._validate_url(url, allowed_hosts)
        for attempt in self.retrying:
            with attempt:
                response = self.session.get(url, params=params, timeout=self.timeout, stream=stream)
                self._validate_redirects(response, allowed_hosts)
                if response.status_code in self.RETRYABLE_STATUS:
                    error = RetryableHttpError(
                        f"retryable HTTP {response.status_code}", response=response
                    )
                    response.close()
                    raise error
                response.raise_for_status()
                return response
        raise RuntimeError("HTTP retry loop ended unexpectedly")

    def get_json(
        self,
        url: str,
        *,
        allowed_hosts: set[str],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.get(url, allowed_hosts=allowed_hosts, params=params)
        try:
            payload = response.json()
        except requests.JSONDecodeError as exc:
            raise ExternalContractError(f"invalid JSON from {url}") from exc
        finally:
            response.close()
        if not isinstance(payload, dict):
            raise ExternalContractError("JSON root must be an object")
        return payload

    def close(self) -> None:
        self.session.close()

    @staticmethod
    def chunks(response: requests.Response, size: int = 1024 * 1024) -> Iterator[bytes]:
        yield from (chunk for chunk in response.iter_content(size) if chunk)

    @staticmethod
    def _validate_url(url: str, allowed_hosts: set[str]) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            raise ExternalContractError(f"unsafe external URL: {url}")

    def _validate_redirects(self, response: requests.Response, allowed_hosts: set[str]) -> None:
        for item in [*response.history, response]:
            self._validate_url(item.url, allowed_hosts)

    @staticmethod
    def _wait(retry_state) -> float:  # noqa: ANN001
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exception, RetryableHttpError) and exception.response is not None:
            retry_after = exception.response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                return float(retry_after)
        base = wait_exponential_jitter(initial=1, max=8)(retry_state)
        return base + random.uniform(0, 0.25)
