"""HTTP helpers with retry and backoff for network errors only."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0


class NetworkError(RuntimeError):
    """Raised when every attempt failed with a network-level error."""


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _get_with_retry(
    client: httpx.Client,
    url: str,
    params: Mapping[str, Any] | None,
    *,
    attempts: int,
    base_delay: float,
    sleep: Callable[[float], None],
) -> httpx.Response:
    """GET ``url`` up to ``attempts`` times, retrying transport errors, 429 and 5xx."""
    if attempts < 1:
        raise ValueError(f"attempts must be at least 1, got {attempts}")
    last_error: Exception | None = None
    for attempt in range(attempts):
        if attempt > 0:
            sleep(base_delay * 2 ** (attempt - 1))
        try:
            response = client.get(url, params=params)
        except httpx.TransportError as error:
            last_error = error
            continue
        if _is_retryable_status(response.status_code):
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                last_error = error
            continue
        response.raise_for_status()
        return response
    raise NetworkError(f"GET {url} failed after {attempts} attempts") from last_error


def fetch_json(
    client: httpx.Client,
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Return the decoded JSON body of a GET, retrying network errors."""
    response = _get_with_retry(
        client, url, params, attempts=attempts, base_delay=base_delay, sleep=sleep
    )
    return response.json()


def fetch_bytes(
    client: httpx.Client,
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Return the raw body of a GET, retrying network errors."""
    response = _get_with_retry(
        client, url, params, attempts=attempts, base_delay=base_delay, sleep=sleep
    )
    return response.content
