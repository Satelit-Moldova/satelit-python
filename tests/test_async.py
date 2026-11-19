from __future__ import annotations

import asyncio
import json

import pytest

from satelit import AsyncSatelit, SatelitError

from conftest import KEY, RATE_HEADERS, FakeTransport, api_error, ok


def run(coro):
    return asyncio.run(coro)


def test_async_call_and_last_rate() -> None:
    t = FakeTransport([ok([{"code": "EUR"}], headers=RATE_HEADERS)])

    async def go():
        async with AsyncSatelit(api_key=KEY, transport=t, lang="en") as c:
            r = await c.rates.list()
            return c, r

    c, r = run(go())
    assert r.data == [{"code": "EUR"}]
    assert c.last_rate["credits_cost"] == 1
    assert t.calls[0].query["lang"] == "en"
    assert KEY not in repr(c)


def test_async_error() -> None:
    t = FakeTransport([api_error(422, "invalid", fields=["code"])])

    async def go():
        await AsyncSatelit(api_key=KEY, transport=t).rates.history(code="")

    with pytest.raises(SatelitError) as ei:
        run(go())
    assert ei.value.fields == ["code"]


def test_async_paginate_and_feed() -> None:
    def page(n):
        return ok([n], page={"page": n, "per": 1, "total": 2, "pages": 2})

    t = FakeTransport([page(1), page(2), ok([{"id": "e1"}], next="c1", has_more=False)])

    async def go():
        c = AsyncSatelit(api_key=KEY, transport=t)
        items = [x async for x in c.paginate(c.tours.list, country="Grecia")]
        events = [e async for e in c.feed.iterate()]
        return items, events

    items, events = run(go())
    assert items == [1, 2]
    assert events == [{"id": "e1"}]


def test_async_export_rows() -> None:
    body = b"".join(
        json.dumps(r).encode() + b"\n" for r in ({"_meta": {}}, {"a": 1}, {"_end": {"rows": 1, "complete": True}})
    )
    t = FakeTransport([{"chunks": [body[:7], body[7:]]}])

    async def go():
        c = AsyncSatelit(api_key=KEY, transport=t)
        return [r async for r in c.export.rows("rates")]

    assert run(go()) == [{"a": 1}]


def test_async_runs_calls_at_once() -> None:
    t = FakeTransport([ok([1])])

    async def go():
        c = AsyncSatelit(api_key=KEY, transport=t)
        return await asyncio.gather(c.rates.list(), c.fuel.today(), c.tariffs.list())

    assert [r.data for r in run(go())] == [[1], [1], [1]]
    assert sorted(x.path for x in t.calls) == ["/v1/fuel", "/v1/rates", "/v1/tariffs"]
