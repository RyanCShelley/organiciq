"""What the SE Ranking client may retry.

Several calls are billed per keyword or per prompt, so a retry is a second
charge. It used to retry every exception three times, including a 400 or a 402
that could only ever say the same thing, and a 429 on the last attempt ended in
an AssertionError rather than an error anyone could read.
"""

from __future__ import annotations

import httpx
import pytest

from app.ingestion.seranking import client as se


class _Script:
    """Stands in for httpx.Client, answering from a list and counting calls."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, url, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        status, body, headers = outcome
        return httpx.Response(
            status, json=body, headers=headers, request=httpx.Request(method, url)
        )


@pytest.fixture
def script(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(se.time, "sleep", sleeps.append)
    monkeypatch.setattr(se, "_throttle", lambda: None)

    def install(*outcomes):
        s = _Script(outcomes)
        monkeypatch.setattr(se.httpx, "Client", s)
        s.sleeps = sleeps
        return s

    return install


def _post():
    return se._request(api_key="k", method="POST", path="/keywords/export", json_body={"keywords": ["a"]})


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
def test_a_client_error_is_not_retried(script, status):
    s = script((status, {"detail": "no"}, {}))
    with pytest.raises(httpx.HTTPStatusError):
        _post()
    assert s.calls == 1


@pytest.mark.parametrize("status", [500, 502, 503, 504, 408])
def test_a_server_error_is_retried_then_succeeds(script, status):
    s = script((status, {}, {}), (200, [{"ok": 1}], {}))
    assert _post() == [{"ok": 1}]
    assert s.calls == 2


def test_a_429_is_retried_and_honours_retry_after(script):
    s = script((429, {}, {"Retry-After": "7"}), (200, {"ok": True}, {}))
    assert _post() == {"ok": True}
    assert s.sleeps == [7.0]


def test_a_429_on_the_last_attempt_is_a_readable_error_not_an_assertion(script):
    script(*[(429, {}, {}) for _ in range(3)])
    with pytest.raises(httpx.HTTPStatusError, match="429"):
        _post()


def test_a_billed_post_is_not_repeated_after_a_timeout(script):
    """The request may have been processed; repeating it could charge twice."""
    s = script(httpx.ReadTimeout("slow"))
    with pytest.raises(httpx.ReadTimeout):
        _post()
    assert s.calls == 1


def test_a_connection_that_never_opened_is_safe_to_retry_for_a_post(script):
    s = script(httpx.ConnectError("refused"), (200, {"ok": True}, {}))
    assert _post() == {"ok": True}
    assert s.calls == 2


def test_a_get_is_retried_after_a_timeout(script):
    s = script(httpx.ReadTimeout("slow"), (200, [1], {}))
    assert se._request(api_key="k", method="GET", path="/project-management/sites") == [1]
    assert s.calls == 2
