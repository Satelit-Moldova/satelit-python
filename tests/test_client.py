from __future__ import annotations

import datetime as dt
import json
import socket
import urllib.error

import pytest

from satelit import Satelit, SatelitError, __version__

from conftest import KEY, RATE_HEADERS, FakeTransport, api_error, ok


def client(t: FakeTransport, **kw) -> Satelit:
    c = Satelit(api_key=KEY, transport=t, **kw)
    c._sleep = lambda s: None  # no real waiting in tests
    return c


def test_sends_key_user_agent_lang_and_query() -> None:
    t = FakeTransport([ok([])])
    client(t, lang="en").news.list(region="chisinau", per=5, page=None, from_="2026-11-01")
    c = t.calls[0]
    assert c.url.startswith("https://api.satelit.md/v1/news?")
    assert c.query == {"region": "chisinau", "per": "5", "from": "2026-11-01", "lang": "en"}
    assert c.headers["Authorization"] == f"Bearer {KEY}"
    assert c.headers["User-Agent"] == f"satelit-python/{__version__}"
    assert c.headers["Accept"] == "application/json"
    assert c.timeout == 10.0


def test_lang_per_call_lists_booleans_dates_and_path_encoding() -> None:
    t = FakeTransport([ok([])])
    c = client(t, lang="ro")
    c.jokes.random(exclude_flags=["dark", "adult"], seen="a,b", lang="ru")
    c.prices.search(q="lapte 2.5%", in_stock=True)
    c.recipes.get("plăcintă/x")
    c.news.day(dt.date(2026, 11, 19).isoformat())
    c.courts.hearings(date=dt.date(2026, 11, 19))
    assert t.calls[0].query["exclude_flags"] == "dark,adult"
    assert t.calls[0].query["lang"] == "ru"
    assert t.calls[1].query == {"q": "lapte 2.5%", "in_stock": "true", "lang": "ro"}
    assert t.calls[2].path == "/v1/recipes/pl%C4%83cint%C4%83%2Fx"
    assert t.calls[3].path == "/v1/news/days/2026-11-19"
    assert t.calls[4].query["date"] == "2026-11-19"


def test_response_data_meta_rate_and_last() -> None:
    t = FakeTransport([ok([{"code": "EUR", "value": 19.5}], headers=RATE_HEADERS, attribution="Sursa: BNM")])
    c = client(t)
    r = c.rates.list()
    assert r.data == [{"code": "EUR", "value": 19.5}]
    assert r["data"] is r.data
    data, m, rate = r
    assert data is r.data
    assert m["attribution"] == "Sursa: BNM"
    assert rate == {
        "limit": 600,
        "remaining": 599,
        "reset": 42,
        "credits_cost": 1,
        "credits_limit": 300000,
        "credits_remaining": 299000,
        "credits_reset": "2026-12-19T16:41:51+02:00",
        "retry_after": None,
    }
    assert c.last_meta == m
    assert c.last_rate["credits_remaining"] == 299000
    assert "credits=1" in repr(r)


def test_env_key_default_and_empty_key(no_env_key, monkeypatch) -> None:
    t = FakeTransport([ok({})])
    Satelit(transport=t).sample()
    assert "Authorization" not in t.calls[0].headers
    monkeypatch.setenv("SATELIT_API_KEY", "sat_live_from_env")
    c = Satelit(transport=t)
    assert c.has_key
    c.status()
    assert t.calls[1].headers["Authorization"] == "Bearer sat_live_from_env"
    Satelit(api_key="", transport=t).status()
    assert "Authorization" not in t.calls[2].headers


def test_key_never_in_repr() -> None:
    c = client(FakeTransport([ok()]))
    assert KEY not in repr(c)
    assert KEY not in str(c)
    assert "key=set" in repr(c)


def test_422_fields_docs_rate() -> None:
    t = FakeTransport([api_error(422, "invalid", RATE_HEADERS, fields=["code"])])
    with pytest.raises(SatelitError) as ei:
        client(t).rates.history(code="")
    e = ei.value
    assert (e.status, e.code, e.fields, e.message) == (422, "invalid", ["code"], "msg invalid")
    assert e.docs == "https://developer.satelit.md/en/errors/#invalid"
    assert e.rate["credits_limit"] == 300000
    assert str(e) == "422 invalid: msg invalid"
    assert len(t.calls) == 1


def test_402_choose() -> None:
    t = FakeTransport([api_error(402, "plan_required", choose="https://developer.satelit.md/en/pricing/")])
    with pytest.raises(SatelitError) as ei:
        client(t).feed.list()
    assert ei.value.choose == "https://developer.satelit.md/en/pricing/"


def test_error_without_json_and_200_without_json() -> None:
    t = FakeTransport([{"status": 502, "body": b"<html>Bad gateway</html>"}])
    with pytest.raises(SatelitError) as ei:
        client(t).rates.list()
    assert (ei.value.status, ei.value.code) == (502, "http_502")
    t = FakeTransport([{"status": 200, "body": b"not json"}])
    with pytest.raises(SatelitError) as ei:
        client(t).rates.list()
    assert ei.value.code == "bad_response"


def test_retries_rate_limited_after_retry_after() -> None:
    t = FakeTransport([api_error(429, "rate_limited", {"Retry-After": "2"}), ok([1])])
    c = client(t)
    waits = []
    c._sleep = waits.append
    assert c.rates.list().data == [1]
    assert waits == [2.0]
    assert len(t.calls) == 2


def test_503_retry_after_gives_up_after_max_retries() -> None:
    t = FakeTransport([api_error(503, "busy", {"Retry-After": "0"})])
    with pytest.raises(SatelitError) as ei:
        client(t, max_retries=2).rates.list()
    assert ei.value.code == "busy"
    assert ei.value.retry_after == 0
    assert len(t.calls) == 3


def test_max_retries_capped_at_3_and_zero_turns_off() -> None:
    t = FakeTransport([api_error(503, "busy", {"Retry-After": "0"})])
    with pytest.raises(SatelitError):
        client(t, max_retries=10).rates.list()
    assert len(t.calls) == 4
    t = FakeTransport([api_error(429, "rate_limited", {"Retry-After": "0"})])
    with pytest.raises(SatelitError):
        client(t, max_retries=0).rates.list()
    assert len(t.calls) == 1


@pytest.mark.parametrize(
    "answer",
    [
        api_error(429, "quota_exceeded", {"Retry-After": "0"}),
        api_error(429, "export_running", {"Retry-After": "0"}),
        api_error(503, "busy"),
        api_error(429, "rate_limited", {"Retry-After": "3600"}),
        api_error(401, "key_invalid"),
        api_error(500, "server_error"),
    ],
)
def test_never_retried(answer) -> None:
    t = FakeTransport([answer])
    with pytest.raises(SatelitError) as ei:
        client(t).rates.list()
    assert ei.value.code == answer["body"]["error"]["code"]
    assert len(t.calls) == 1


def test_rate_limited_without_retry_after_backs_off() -> None:
    t = FakeTransport([api_error(429, "rate_limited"), api_error(429, "rate_limited"), ok([])])
    c = client(t)
    waits = []
    c._sleep = waits.append
    c.rates.list()
    assert waits == [1.0, 2.0]


@pytest.mark.parametrize("exc", [socket.timeout("timed out"), TimeoutError(), urllib.error.URLError(socket.timeout())])
def test_timeouts(exc) -> None:
    def boom():
        raise exc

    with pytest.raises(SatelitError) as ei:
        client(FakeTransport([boom]), timeout=3).rates.list()
    assert (ei.value.status, ei.value.code) == (0, "timeout")


def test_network_error() -> None:
    def boom():
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    with pytest.raises(SatelitError) as ei:
        client(FakeTransport([boom])).rates.list()
    assert ei.value.code == "network_error"
    assert isinstance(ei.value.__cause__, urllib.error.URLError)


def test_per_call_timeout() -> None:
    t = FakeTransport([ok([])])
    client(t).rates.list(timeout=2.5)
    assert t.calls[0].timeout == 2.5


def test_paginate_walks_pages_and_max_pages() -> None:
    def page(n):
        return ok([f"a{n}", f"b{n}"], page={"page": n, "per": 2, "total": 6, "pages": 3})

    t = FakeTransport([page(1), page(2), page(3)])
    c = client(t)
    assert list(c.paginate(c.tours.list, country="Turcia")) == ["a1", "b1", "a2", "b2", "a3", "b3"]
    assert [x.query["page"] for x in t.calls] == ["1", "2", "3"]
    assert t.calls[2].query["country"] == "Turcia"
    t = FakeTransport([page(1), page(2), page(3)])
    c = client(t)
    assert len(list(c.paginate(c.deals.list, max_pages=2))) == 4
    assert len(t.calls) == 2


def test_paginate_without_page_meta_is_one_call() -> None:
    t = FakeTransport([ok([1, 2])])
    c = client(t)
    assert list(c.paginate(c.prices.search, q="lapte")) == [1, 2]
    assert len(t.calls) == 1


def test_feed_iterate_follows_next() -> None:
    t = FakeTransport(
        [
            ok([{"id": "1"}, {"id": "2"}], next="c2", has_more=True),
            ok([{"id": "3"}], next="c3", has_more=False),
        ]
    )
    cursors = []
    ids = [
        e["id"]
        for e in client(t).feed.iterate(types=["news.published", "rates.updated"], limit=2, on_cursor=cursors.append)
    ]
    assert ids == ["1", "2", "3"]
    assert cursors == ["c2", "c3"]
    assert "after" not in t.calls[0].query
    assert t.calls[0].query["types"] == "news.published,rates.updated"
    assert t.calls[1].query["after"] == "c2"


def _ndjson(*rows) -> bytes:
    return b"".join(json.dumps(r, ensure_ascii=False).encode("utf-8") + b"\n" for r in rows)


def test_export_rows_across_chunk_edges() -> None:
    data = _ndjson(
        {"_meta": {"product": "rates"}},
        {"code": "EUR", "name": "Euro ă"},
        {"code": "USD"},
        {"_end": {"rows": 2, "complete": True}},
    )
    cut = data.index("ă".encode()) + 1  # inside the two bytes of "ă"
    t = FakeTransport([{"chunks": [data[:10], data[10:cut], data[cut:]]}])
    seen = {}
    rows = list(
        client(t).export.rows("rates", on_meta=lambda m: seen.update(meta=m), on_end=lambda e: seen.update(end=e))
    )
    assert rows == [{"code": "EUR", "name": "Euro ă"}, {"code": "USD"}]
    assert seen == {"meta": {"product": "rates"}, "end": {"rows": 2, "complete": True}}
    assert t.calls[0].path == "/v1/export/rates"
    assert t.calls[0].headers["Accept"] == "application/x-ndjson"


def test_export_incomplete() -> None:
    t = FakeTransport([{"chunks": [_ndjson({"_meta": {}}, {"a": 1})]}])
    rows = []
    with pytest.raises(SatelitError) as ei:
        for r in client(t).export.rows("fuel"):
            rows.append(r)
    assert rows == [{"a": 1}]
    assert ei.value.code == "export_incomplete"


def test_export_error_before_rows() -> None:
    t = FakeTransport([api_error(402, "plan_required")])
    with pytest.raises(SatelitError) as ei:
        next(client(t).export.stream("rates"))
    assert ei.value.code == "plan_required"


def test_get_escape_hatch_and_base_url() -> None:
    t = FakeTransport([ok({"ok": True})])
    c = client(t, base_url="http://localhost:8080/v1/")
    assert c.get("/some/new/route", {"a": 1}).data == {"ok": True}
    assert t.calls[0].url == "http://localhost:8080/v1/some/new/route?a=1"


def test_context_manager() -> None:
    with client(FakeTransport([ok(1)])) as c:
        assert c.me().data == 1
