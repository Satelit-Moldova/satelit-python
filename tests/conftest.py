"""A scripted transport for the offline tests: answers in order, records every request."""

from __future__ import annotations

import io
import json
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import parse_qs, urlsplit

import pytest

from satelit import RawResponse

KEY = "sat_live_test_0000"

RATE_HEADERS = {
    "X-RateLimit-Limit": "600",
    "X-RateLimit-Remaining": "599",
    "X-RateLimit-Reset": "42",
    "X-Credits-Cost": "1",
    "X-Credits-Limit": "300000",
    "X-Credits-Remaining": "299000",
    "X-Credits-Reset": "2026-12-19T16:41:51+02:00",
}


def meta(**extra: Any) -> Dict[str, Any]:
    return {"credits": 1, "updated_at": "2026-11-19T10:00:00+02:00", "sources": [], "attribution": None, **extra}


def ok(data: Any = None, headers: Optional[Dict[str, str]] = None, **m: Any) -> Dict[str, Any]:
    return {"status": 200, "body": {"data": data, "meta": meta(**m)}, "headers": headers or {}}


def api_error(status: int, code: str, headers: Optional[Dict[str, str]] = None, **extra: Any) -> Dict[str, Any]:
    body = {
        "error": {
            "code": code,
            "message": f"msg {code}",
            "docs": f"https://developer.satelit.md/en/errors/#{code}",
            **extra,
        }
    }
    return {"status": status, "body": body, "headers": headers or {}}


class Call:
    def __init__(self, url: str, headers: Dict[str, str], timeout: float) -> None:
        self.url = url
        parts = urlsplit(url)
        self.path = parts.path
        self.query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self.headers = headers
        self.timeout = timeout


class FakeTransport:
    """Each answer is a dict {status, body, headers}, bytes chunks via 'chunks', or a callable raising."""

    def __init__(self, answers: List[Union[Dict[str, Any], Callable[[], Any]]]) -> None:
        self.answers = list(answers)
        self.calls: List[Call] = []

    def __call__(self, url: str, headers: Dict[str, str], timeout: float) -> RawResponse:
        self.calls.append(Call(url, dict(headers), timeout))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if callable(a):
            return a()
        if "chunks" in a:
            return RawResponse(a.get("status", 200), a.get("headers", {}), _Chunks(a["chunks"]))
        body = a.get("body")
        raw = body if isinstance(body, (bytes, str)) else json.dumps(body)
        raw = raw.encode("utf-8") if isinstance(raw, str) else raw
        return RawResponse(a.get("status", 200), a.get("headers", {}), io.BytesIO(raw))


class _Chunks:
    """A body that returns the given chunks one read at a time."""

    def __init__(self, chunks: List[bytes]) -> None:
        self.chunks = list(chunks)

    def read(self, n: int = -1) -> bytes:
        if n == -1:
            out, self.chunks = b"".join(self.chunks), []
            return out
        return self.chunks.pop(0) if self.chunks else b""

    def close(self) -> None:
        pass


@pytest.fixture
def no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SATELIT_API_KEY", raising=False)
