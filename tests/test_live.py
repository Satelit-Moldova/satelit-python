"""Live smoke test against https://api.satelit.md/v1. Runs only with SATELIT_API_KEY set:

    SATELIT_API_KEY=sat_live_… pytest tests/test_live.py -s

Spends about 60 credits (one Movies call is 40). Prints what it saw, never the key.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from satelit import AsyncSatelit, Satelit, SatelitError

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("SATELIT_API_KEY"), reason="SATELIT_API_KEY is not set"),
]


@pytest.fixture(scope="module")
def s() -> Satelit:
    return Satelit(lang="en")


def seen(label: str, r) -> None:
    rate = r.rate
    left = f"remaining {rate['credits_remaining']}, rate {rate['remaining']}/{rate['limit']}"
    print(f"  {label}: credits {rate['credits_cost']}, {left}")


def test_keyless_routes_accept_the_sdk_user_agent() -> None:
    k = Satelit(api_key="")
    sample = k.sample()
    assert sample.data["rates"]
    assert sample.rate["credits_cost"] == 0
    assert k.status().data["ok"] is True
    assert k.plans().data["plans"]
    board = k.movies.board(lang="en")
    print(f"  sample, status, plans, movies.board: 200, {len(board.data['cinemas'])} cinemas on {board.data['day']}")


def test_me(s: Satelit) -> None:
    r = s.me()
    assert isinstance(r.data["plan"], str)
    assert r.rate["credits_cost"] == 0
    print(f"  plan {r.data['plan']}, used {r.data['credits']['used']} of {r.data['credits']['limit']}")


def test_rates(s: Satelit) -> None:
    r = s.rates.list()
    eur = next(x for x in r.data if x["code"] == "EUR")
    assert 10 < eur["value"] < 40
    assert "bnm.md" in (r.meta["attribution"] or "")
    assert s.last_rate["credits_cost"] == 1
    seen(f"rates.list EUR {eur['value']} on {eur['date']}", r)
    h = s.rates.history(code="EUR", days=30)
    assert h.data["code"] == "EUR" and len(h.data["points"]) > 5
    seen(f"rates.history {len(h.data['points'])} points", h)


def test_fuel(s: Satelit) -> None:
    r = s.fuel.today()
    assert len(r.data["networks"]) > 3
    seen(f"fuel.today {r.data['date']}: A95 from {r.data['range']['a95']['min']} ({r.data['cheapest']['a95']})", r)


def test_prices_and_paginate(s: Satelit) -> None:
    r = s.prices.search(q="lapte")
    assert r.data and r.meta["page"]["pages"] >= 1
    first = r.data[0]
    seen(
        f"prices.search lapte: {r.meta['page']['total']} products, first {first['name']} from {first['min_price']}",
        r,
    )
    items = list(s.paginate(s.prices.search, q="lapte", max_pages=2))
    assert len(items) > len(r.data)
    print(f"  paginate prices.search: {len(items)} items over 2 pages")


def test_news_power_jokes_companies(s: Satelit) -> None:
    news = s.news.list(per=3)
    assert len(news.data) == 3
    seen(f"news.list: {news.meta['page']['total']} stories", news)
    power = s.power.day()
    assert power.data["hours"]
    seen(
        f"power.day {power.data['date']}: base {power.data['base']} {power.data['currency']}/{power.data['unit']}",
        power,
    )
    joke = s.jokes.today(lang="ro")
    assert isinstance(joke.data["text"], str)
    seen("jokes.today", joke)
    co = s.companies.search(q="moldtelecom")
    assert co.data
    seen(f"companies.search moldtelecom: {co.data[0]['name']}", co)


def test_movies(s: Satelit) -> None:
    g = s.movies.genres()
    assert len(g.data["genres"]) > 5 and g.rate["credits_cost"] == 0
    r = s.movies.search(q="matrix", kind="movie")
    assert r.data["results"] and r.rate["credits_cost"] == 40
    seen(f"movies.search matrix: {r.data['total']} results, first {r.data['results'][0].get('title')}", r)


def test_async_client() -> None:
    async def go():
        async with AsyncSatelit(lang="en") as a:
            return await asyncio.gather(a.rates.list(), a.tariffs.list(), a.me())

    rates, tariffs, me = asyncio.run(go())
    assert rates.data and tariffs.data and me.data["plan"]
    print(f"  async gather: {len(rates.data)} rates, {len(tariffs.data)} tariffs, plan {me.data['plan']}")


def test_errors(s: Satelit) -> None:
    with pytest.raises(SatelitError) as ei:
        s.rates.history(code="")
    e = ei.value
    assert (e.status, e.code, e.fields) == (422, "invalid", ["code"])
    print(f"  422 {e.code} fields={e.fields} docs={e.docs}")
    plan = s.me().data["plan"]
    if plan not in ("business", "companies"):
        with pytest.raises(SatelitError) as ei:
            s.feed.list()
        assert (ei.value.status, ei.value.code) == (402, "plan_required")
        with pytest.raises(SatelitError) as ei:
            next(s.export.rows("rates"))
        assert ei.value.code == "plan_required"
        print(f"  feed and export on {plan}: 402 plan_required")
    with pytest.raises(SatelitError) as ei:
        Satelit(api_key="sat_live_not_a_real_key_000000", max_retries=0).rates.list()
    assert (ei.value.status, ei.value.code) == (401, "key_invalid")
    print(f"  bad key: 401 {ei.value.code}")
