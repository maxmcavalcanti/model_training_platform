"""Tests for the retrying HTTP helpers in ``ingestion.http`` (plan 14, cases 1 to 14).

No test touches the network: every client uses ``httpx.MockTransport`` and the backoff sleep is
replaced by a function that only records the requested delay.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from ingestion.http import NetworkError, fetch_bytes, fetch_json

URL = "https://example.test/data"
PAYLOAD = {"value": 1}

Step = Callable[[httpx.Request], httpx.Response]


def _json_response(payload=PAYLOAD) -> Step:
    return lambda request: httpx.Response(200, json=payload)


def _status(code: int) -> Step:
    return lambda request: httpx.Response(code)


def _raises(exception_type: type[httpx.TransportError]) -> Step:
    def step(request: httpx.Request) -> httpx.Response:
        raise exception_type("boom", request=request)

    return step


class Harness:
    """Client whose n-th request is answered by the n-th step; records requests and sleeps."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.steps[min(len(self.requests), len(self.steps)) - 1](request)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


# Case 1
def test_first_success_returns_json_without_waiting():
    harness = Harness([_json_response()])

    result = fetch_json(harness.client, URL, sleep=harness.sleep)

    assert result == PAYLOAD
    assert len(harness.requests) == 1
    assert harness.sleeps == []


# Case 2
def test_connect_errors_are_retried_with_exponential_backoff():
    harness = Harness([_raises(httpx.ConnectError), _raises(httpx.ConnectError), _json_response()])

    result = fetch_json(harness.client, URL, base_delay=1.0, sleep=harness.sleep)

    assert result == PAYLOAD
    assert len(harness.requests) == 3
    assert harness.sleeps == [1.0, 2.0]


# Case 3
def test_read_timeout_is_retried():
    harness = Harness([_raises(httpx.ReadTimeout), _json_response()])

    result = fetch_json(harness.client, URL, sleep=harness.sleep)

    assert result == PAYLOAD
    assert len(harness.requests) == 2


# Case 4
def test_persistent_503_raises_network_error_with_status_cause():
    harness = Harness([_status(503)])

    with pytest.raises(NetworkError) as error_info:
        fetch_json(harness.client, URL, base_delay=1.0, sleep=harness.sleep)

    assert len(harness.requests) == 3
    assert harness.sleeps == [1.0, 2.0]
    assert URL in str(error_info.value)
    assert isinstance(error_info.value.__cause__, httpx.HTTPStatusError)


# Case 5
def test_persistent_connect_error_raises_network_error_with_transport_cause():
    harness = Harness([_raises(httpx.ConnectError)])

    with pytest.raises(NetworkError) as error_info:
        fetch_json(harness.client, URL, sleep=harness.sleep)

    assert len(harness.requests) == 3
    assert isinstance(error_info.value.__cause__, httpx.ConnectError)


# Case 6
def test_429_is_retried():
    harness = Harness([_status(429), _json_response()])

    result = fetch_json(harness.client, URL, sleep=harness.sleep)

    assert result == PAYLOAD
    assert len(harness.requests) == 2


# Case 7
def test_500_and_502_are_retried():
    harness = Harness([_status(500), _status(502), _json_response()])

    result = fetch_json(harness.client, URL, sleep=harness.sleep)

    assert result == PAYLOAD
    assert len(harness.requests) == 3


# Case 8
def test_400_fails_immediately_as_http_status_error():
    harness = Harness([_status(400)])

    with pytest.raises(httpx.HTTPStatusError) as error_info:
        fetch_json(harness.client, URL, sleep=harness.sleep)

    assert not isinstance(error_info.value, NetworkError)
    assert len(harness.requests) == 1
    assert harness.sleeps == []


# Case 9
def test_404_fails_immediately_as_http_status_error():
    harness = Harness([_status(404)])

    with pytest.raises(httpx.HTTPStatusError):
        fetch_json(harness.client, URL, sleep=harness.sleep)

    assert len(harness.requests) == 1


# Case 10
def test_invalid_json_body_is_not_a_network_error_and_is_not_retried():
    harness = Harness([lambda request: httpx.Response(200, content=b"<html>not json</html>")])

    with pytest.raises(json.JSONDecodeError) as error_info:
        fetch_json(harness.client, URL, sleep=harness.sleep)

    assert not isinstance(error_info.value, NetworkError)
    assert len(harness.requests) == 1


# Case 11
def test_custom_attempts_and_base_delay_shape_the_backoff():
    harness = Harness([_status(503)])

    with pytest.raises(NetworkError):
        fetch_json(harness.client, URL, attempts=5, base_delay=0.5, sleep=harness.sleep)

    assert len(harness.requests) == 5
    assert harness.sleeps == [0.5, 1.0, 2.0, 4.0]


# Case 12
def test_zero_attempts_is_rejected_before_any_request():
    harness = Harness([_json_response()])

    with pytest.raises(ValueError):
        fetch_json(harness.client, URL, attempts=0, sleep=harness.sleep)

    assert harness.requests == []


# Case 13
def test_params_are_sent_in_the_query_string():
    harness = Harness([_json_response()])

    fetch_json(harness.client, URL, {"a": "1"}, sleep=harness.sleep)

    assert harness.requests[0].url.params["a"] == "1"


# Case 14
def test_fetch_bytes_retries_and_returns_the_raw_body():
    harness = Harness([_status(503), lambda request: httpx.Response(200, content=b"\x00\x01")])

    result = fetch_bytes(harness.client, URL, sleep=harness.sleep)

    assert result == b"\x00\x01"
    assert len(harness.requests) == 2
