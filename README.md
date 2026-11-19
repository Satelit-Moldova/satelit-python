# Satelit SDK for Python

The official Python client for the [Satelit data API](https://developer.satelit.md/en/docs/): Moldova's official exchange rates, fuel prices, household tariffs, shop prices and deals, laws, news, companies, courts, tours, flights, cinemas and more, through one key.

```
$ python examples/price_search.py
"lapte": 100 products, the first 5:

  Lapte Casuta Mea 2.5% 1 l: from 15.99 MDL in 4 shops
  Lapte JLC 2.5% 1 l: from 16.99 MDL in 4 shops
  ...
Offers for Lapte Casuta Mea 2.5% 1 l:
  METRO              15.99 MDL (was 17.90)
  Bonus              18.30 MDL, out of stock
  Linella            18.99 MDL
  MegaAlina          18.99 MDL

Source: Bonus, Linella, METRO, MegaAlina | Data: Satelit (satelit.md)
```

- No dependencies: the standard library only (`urllib`, `json`, `asyncio`).
- `Satelit` for plain code, `AsyncSatelit` for `asyncio`, with the same methods.
- Answers are plain `dict`s and `list`s, typed with `TypedDict`s generated from the API's OpenAPI document (`py.typed` included).
- `r.data`, `r.meta`, `r.rate` from every call: the data, its sources and attribution, and the credits and rate limit left.
- One exception, `SatelitError`, with the API's `code`, `message`, `docs` link, `fields` and `retry_after`.
- Timeouts on every call, bounded retries only where the API says to wait, page and feed iterators, and a streaming NDJSON export reader.

## Quick start

```python
from satelit import Satelit

satelit = Satelit()  # reads SATELIT_API_KEY
r = satelit.rates.list()
print(next(x["value"] for x in r.data if x["code"] == "EUR"), r.meta["attribution"])
```

## Requirements

- Python 3.10 or newer.
- A Satelit API key (`sat_live_…`) from the [console](https://developer.satelit.md/en/console/). The API is paid: see [pricing](https://developer.satelit.md/en/pricing/). To look before you buy, the keyless routes (`sample`, `products`, `plans`, `status`, `stats`, `movies.board`) work without a key.

## Install

```sh
pip install git+https://github.com/Satelit-Moldova/satelit-python
```

The import name is `satelit`.

## Configure

```python
from satelit import Satelit

satelit = Satelit(
    api_key=None,          # None: SATELIT_API_KEY from the environment; "" for no key
    lang="en",             # ro (default), ru, en, uk; per call too: lang="ru"
    timeout=10.0,          # seconds to connect and for each read
    max_retries=2,         # 429 rate_limited and 503 with Retry-After only; at most 3
    base_url="https://api.satelit.md/v1",
)
```

Keep the key on the server: in an environment variable or your secret store, never in a repository, a log or a page sent to a browser. `repr(satelit)` shows only whether a key is set. The client goes through `urllib`, so `HTTPS_PROXY` and the system's certificates apply as usual.

## Usage

Every method returns a `Response` with `data`, `meta` and `rate`:

```python
r = satelit.prices.search(q="lapte", in_stock=True)
r.data                         # list of PriceItem dicts
r.meta["page"]                 # {'page': 1, 'per': 20, 'total': 100, 'pages': 5}
r.meta["sources"]              # [{'name': ..., 'url': ..., 'license': ...}]
r.meta["attribution"]          # a line to show with the data, or None
r.rate["credits_cost"]         # 3
r.rate["credits_remaining"]    # credits left this period
data, meta, rate = r           # unpacks too
satelit.last_meta, satelit.last_rate   # of the last answer (last_rate also after an error)
```

Path parameters are positional, query parameters are keyword arguments (`from` is `from_`):

```python
satelit.rates.history(code="EUR", days=30)
satelit.law.act(12345)
satelit.law.acts(q="impozit", from_="2026-01-01", important=True)
satelit.news.events.comments("e_123", sort="top", per=10, lang="ru")
satelit.movies.today(city="Chișinău", timeout=5)
```

### Async

```python
import asyncio
from satelit import AsyncSatelit

async def main():
    async with AsyncSatelit(lang="en") as satelit:
        rates, fuel = await asyncio.gather(satelit.rates.list(), satelit.fuel.today())
        async for tour in satelit.paginate(satelit.tours.list, country="Turcia", max_pages=2):
            print(tour["hotel"], tour["price_mdl"])

asyncio.run(main())
```

`AsyncSatelit` needs nothing extra: each call runs the standard-library client in a worker thread (`asyncio.to_thread`). For hundreds of calls at once, size the default executor to match.

### Pages

Paged lists carry `meta["page"]`. `paginate` walks them and yields the items. Every page is a call and costs its credits, so bound it with `max_pages`:

```python
for tour in satelit.paginate(satelit.tours.list, country="Turcia", max_pages=3):
    print(tour["hotel"], tour["price_mdl"])
```

### Feed (Business and Enterprise)

```python
cursor = load_cursor()  # keep it between runs
for event in satelit.feed.iterate(after=cursor, types=["rates.updated"], on_cursor=save_cursor):
    handle(event)
```

### Export (Enterprise)

```python
for row in satelit.export.rows("fuel", on_end=print):
    ...

with open("rates.ndjson", "wb") as f:      # or the raw NDJSON bytes
    for chunk in satelit.export.stream("rates"):
        f.write(chunk)
```

`export.rows` raises `export_incomplete` when the stream ends without its `_end` line (the file was cut).

### Any other route

`satelit.get(path, query)` calls any GET route with the same auth, retries and errors, for routes newer than this SDK.

## Methods

Every route of the API (generated from [`spec/openapi.json`](spec/openapi.json) by `python scripts/generate.py`). Credits are as the API documents them; `r.rate["credits_cost"]` is the exact figure of each answer. `…` stands for the optional keyword arguments.

<!-- methods:start -->
| Method | Route | Credits |
|---|---|---|
| `rates.list()` | `/rates` | Costs 1 credit |
| `rates.history(code=…, …)` | `/rates/history` | Costs 1 credit per started 30 days |
| `fuel.today()` | `/fuel` | Costs 1 credit |
| `fuel.stations(…)` | `/fuel/stations` | Costs 5 credits per page |
| `fuel.history(fuel=…, …)` | `/fuel/history` | Costs 2 credits per started 30 days |
| `tariffs.list()` | `/tariffs` | Costs 1 credit |
| `indexes.basket(…)` | `/indexes/basket` | Costs per day, across shops, with no shop named |
| `indexes.moves(…)` | `/indexes/moves` | Costs 2 credits |
| `law.acts(…)` | `/law/acts` | Costs 3 credits with `q`, else 2 |
| `law.act(id)` | `/law/acts/{id}` | Costs 1 credit |
| `law.digests(…)` | `/law/digests` | Costs 2 credits |
| `law.digest(date)` | `/law/digests/{date}` | Costs 2 credits |
| `news.list(…)` | `/news` | Costs 2 credits |
| `news.now(…)` | `/news/now` | Costs 2 credits |
| `news.search(q=…, …)` | `/news/search` | Costs 3 credits |
| `news.day(date, …)` | `/news/days/{date}` | Costs 10 credits |
| `news.categories()` | `/news/categories` | Costs 1 credit |
| `news.regions()` | `/news/regions` | Costs 1 credit |
| `news.outlets()` | `/news/outlets` | Costs 1 credit |
| `news.get(id)` | `/news/{id}` | Costs 1 credit |
| `news.reaction(id)` | `/news/{id}/reaction` | Costs 1 credit |
| `news.comments(id, …)` | `/news/{id}/comments` | Costs 3 credits |
| `news.events.list(…)` | `/news/events` | Costs 2 credits |
| `news.events.get(id)` | `/news/events/{id}` | Costs 1 credit |
| `news.events.comments(id, …)` | `/news/events/{id}/comments` | Costs 3 credits |
| `places.list(…)` | `/places` | Costs 2 credits per page |
| `recipes.list()` | `/recipes` | Costs at today's prices: one total, no shop behind it |
| `recipes.get(slug)` | `/recipes/{slug}` | Costs 1 credit |
| `prices.stores()` | `/prices/stores` | Costs 1 credit |
| `prices.search(q=…, …)` | `/prices/search` | Costs 3 credits |
| `prices.groups(…)` | `/prices/groups` | Costs 2 credits |
| `prices.group(id)` | `/prices/groups/{id}` | Costs 3 credits |
| `prices.item(id)` | `/prices/items/{id}` | Costs 2 credits |
| `prices.item_history(id, …)` | `/prices/items/{id}/history` | Costs 5 credits per started 30 days |
| `deals.list(…)` | `/deals` | Costs 5 credits per page |
| `tours.list(…)` | `/tours` | Costs 3 credits per page |
| `tours.countries()` | `/tours/countries` | Costs 1 credit |
| `tours.get(id)` | `/tours/{id}` | Costs on each day we saw it |
| `flights.destinations()` | `/flights/destinations` | Costs 2 credits |
| `flights.destination(code)` | `/flights/destinations/{code}` | Costs 3 credits |
| `flights.board(…)` | `/flights/board` | Costs 2 credits |
| `rest.list(…)` | `/rest` | Costs 3 credits per page |
| `estate.get(…)` | `/estate` | Costs 3 credits |
| `power.day(…)` | `/power` | Costs 1 credit |
| `power.history(…)` | `/power/history` | Costs 2 credits per started 30 days |
| `power.bilateral(…)` | `/power/bilateral` | Costs 1 credit |
| `market.categories()` | `/market/categories` | Costs 2 credits |
| `market.prices(…)` | `/market/prices` | Costs 2 credits per 50 rows |
| `market.history(…)` | `/market/history` | Costs 3 credits per started 30 days |
| `market.sellers(…)` | `/market/sellers` | Costs 3 credits per 50 rows |
| `market.seller(id)` | `/market/sellers/{id}` | Costs 2 credits |
| `feed.list(…)` | `/feed` | Business and Enterprise plans only. Costs nothing on a contract plan |
| `jokes.list(…)` | `/jokes` | Costs 1 credit per 20 rows, 2 with `q` |
| `jokes.today(…)` | `/jokes/today` | Costs 1 credit |
| `jokes.random(…)` | `/jokes/random` | Costs 1 credit |
| `jokes.topics(…)` | `/jokes/topics` | Costs 1 credit |
| `jokes.get(id)` | `/jokes/{id}` | Costs 1 credit |
| `courts.courts()` | `/courts/courts` | Costs 1 credit |
| `courts.search(q=…, …)` | `/courts/search` | Costs 3 credits per 20 rows |
| `courts.hearings(…)` | `/courts/hearings` | Costs 2 credits per 50 rows |
| `courts.case(number=…, …)` | `/courts/case` | Costs 1 credit |
| `courts.judge(slug)` | `/courts/judges/{slug}` | Costs 1 credit |
| `courts.name(kind, slug, …)` | `/courts/names/{kind}/{slug}` | Costs 3 credits per 20 rows |
| `courts.stats(…)` | `/courts/stats` | Costs 2 credits |
| `citizenship.lookup(q=…)` | `/citizenship/lookup` | Costs 1 credit |
| `citizenship.stats(…)` | `/citizenship/stats` | Costs 2 credits |
| `citizenship.years()` | `/citizenship/years` | Costs 1 credit |
| `citizenship.year(slug, …)` | `/citizenship/years/{slug}` | Costs 2 credits per 200 rows |
| `citizenship.orders(…)` | `/citizenship/orders` | Costs 2 credits per 50 rows |
| `citizenship.order(order, …)` | `/citizenship/orders/{order}` | Costs 2 credits per 200 rows |
| `citizenship.oath()` | `/citizenship/oath` | Costs 1 credit |
| `companies.search(q=…, …)` | `/companies` | Costs 3 credits per 20 rows |
| `companies.stats()` | `/companies/stats` | Costs 2 credits |
| `companies.licences(…)` | `/companies/licences` | Costs 2 credits per 50 rows |
| `companies.notices(…)` | `/companies/notices` | Costs 2 credits per 50 rows |
| `companies.get(idno)` | `/companies/{idno}` | Costs 2 credits |
| `companies.contracts(idno, …)` | `/companies/{idno}/contracts` | Costs 2 credits per 50 rows |
| `companies.licences_of(idno)` | `/companies/{idno}/licences` | Costs 1 credit |
| `companies.notices_of(idno)` | `/companies/{idno}/notices` | Costs 1 credit |
| `delivery.terms(…)` | `/delivery` | Costs 2 credits |
| `insurance.insurers()` | `/insurance/insurers` | Costs 2 credits |
| `insurance.market()` | `/insurance/market` | Costs 2 credits |
| `insurance.tariffs(…)` | `/insurance/tariffs` | Costs 1 credit |
| `geo.search(q=…, …)` | `/geo/search` | Costs 1 credit |
| `geo.streets(q=…, …)` | `/geo/streets` | Costs 2 credits per 50 rows |
| `catalog.tree()` | `/catalog/tree` | Costs 0 credits |
| `movies.search(q=…, …)` | `/movies/search` | Costs 40 credits |
| `movies.title(id)` | `/movies/titles/{id}` | Costs 40 credits |
| `movies.title_full(id)` | `/movies/titles/{id}/full` | Costs 55 credits |
| `movies.showtimes(id, …)` | `/movies/titles/{id}/showtimes` | Costs 40 credits |
| `movies.person(id)` | `/movies/people/{id}` | Costs 40 credits |
| `movies.discover(…)` | `/movies/discover` | Costs 40 credits |
| `movies.trending(…)` | `/movies/trending` | Costs 40 credits |
| `movies.in_cinemas(…)` | `/movies/cinema` | Costs 40 credits |
| `movies.genres(…)` | `/movies/genres` | Costs nothing |
| `movies.cinemas(…)` | `/movies/cinemas` | Costs 40 credits |
| `movies.cinema_schedule(id, …)` | `/movies/cinemas/{id}/schedule` | Costs 40 credits |
| `movies.today(…)` | `/movies/cinemas/today` | Costs 40 credits |
| `movies.board()` | `/movies/board` | No key, 0 credits |
| `me()` | `/me` | Costs nothing |
| `products()` | `/products` | No key, 0 credits |
| `plans()` | `/plans` | No key, 0 credits |
| `status()` | `/status` | No key, 0 credits |
| `stats()` | `/stats` | No key, 0 credits |
| `sample()` | `/sample` | No key, 0 credits |
<!-- methods:end -->

Plus `paginate(method, max_pages=…, **params)`, `feed.iterate(…)`, `export.rows(product)`, `export.stream(product)` and `get(path, query)`.

## Errors

Every failure raises `SatelitError`:

| Attribute | |
|---|---|
| `status` | HTTP status; `0` for a timeout or a network error |
| `code` | the API's code, or `timeout`, `network_error`, `bad_response`, `export_incomplete` |
| `message` | the API's message, in the call's language |
| `docs` | the error's page, such as `https://developer.satelit.md/en/errors/#invalid` |
| `fields` | for `invalid`: the parameters that were wrong, such as `['code']` |
| `retry_after` | seconds, from `Retry-After` |
| `choose` | for `plan_required` without a plan: the pricing page |
| `rate` | the credit and rate headers of the failed answer |

| Status | `code` | What to do |
|---|---|---|
| 401 | `auth_required`, `key_invalid` | check the key |
| 402 | `plan_required` | the plan does not include this. See `choose` or the pricing page |
| 403 | `not_available`, `account_suspended` | the product is closed, or the account is |
| 404 | `not_found` | no such id |
| 422 | `invalid` | fix `fields` |
| 429 | `rate_limited` | retried for you after `Retry-After` (at most 3 times) |
| 429 | `quota_exceeded` | out of credits this period: never retried. Buy a pack or wait for the reset |
| 429 | `export_running` | one export at a time per account |
| 503 | `busy` | retried for you when `Retry-After` is given |

```python
from satelit import SatelitError

try:
    satelit.rates.history(code="")
except SatelitError as e:
    print(e.status, e.code, e.fields, e.docs)
    # 422 invalid ['code'] https://developer.satelit.md/en/errors/#invalid
```

A `Retry-After` over 60 seconds is not waited for. More: [errors](https://developer.satelit.md/en/errors/), [rate limits](https://developer.satelit.md/en/rate-limits/).

## Caching and credits

A credit is charged only on a 2xx answer. Most calls cost 1 to 5 credits; **every Movies call costs 40** (`movies.title_full` 55), except `movies.genres` (0) and the keyless `movies.board`. Keep answers and reuse them. The sources do not change faster than this:

| Data | Keep it for |
|---|---|
| rates (BNM publishes once a working day) | 1 to 6 h |
| fuel | 1 to 3 h |
| shop prices, deals | 1 to 6 h |
| news | 10 to 15 min |
| cinema schedules | 1 to 3 h |
| a film's or person's details | 24 h or more |

The examples use a small file cache ([`examples/_cache.py`](examples/_cache.py)). In an app, use the cache you have (Django's cache, Redis, `functools.lru_cache` with a time bucket). Read `r.rate["credits_remaining"]` to watch the balance, or call `satelit.me()` (free).

**Attribution.** Wherever you show the data, show `meta["attribution"]` when it is not `None` (rates carry BNM's line `Sursa: Banca Națională a Moldovei, bnm.md, CC BY 4.0`, OpenStreetMap places their ODbL line) and a small "Data: Satelit (satelit.md)" link. Show the shop's name with every shop price.

## Examples

| Script | Shows | Credits per fresh run |
|---|---|---|
| [`examples/rates_table.py`](examples/rates_table.py) | today's BNM rates as a table | 1 |
| [`examples/fuel_cheapest.py`](examples/fuel_cheapest.py) | the cheapest network per fuel, next to ANRE's cap | 1 |
| [`examples/price_search.py`](examples/price_search.py) `lapte` | product search, then every shop's offer | 5 |
| [`examples/cinema_today.py`](examples/cinema_today.py) `[city]` | today's sessions in every cinema | 0 (keyless) |

```sh
export SATELIT_API_KEY=sat_live_…   # PowerShell: $env:SATELIT_API_KEY = "sat_live_…"
python examples/rates_table.py
```

Real output of `python examples/rates_table.py` on 19 Nov 2026:

```
code  name                 MDL per unit  7 days %  30 days %  date
EUR   Euro                      20.1411      -0.1        0.2  2026-11-19
USD   US dollar                 18.3744       1.5        2.5  2026-11-19
RON   Romanian leu               3.7671      -0.1       -0.2  2026-11-19
UAH   Ukrainian hryvnia          0.4067       1.8        2.2  2026-11-19
Sursa: Banca Națională a Moldovei, bnm.md, CC BY 4.0 | Data: Satelit (satelit.md)
The same data is free at bnm.md.
```

## Development

```sh
pip install -e ".[dev]"
python scripts/generate.py && ruff format src   # types.py, _resources.py and the table above, from spec/
ruff check . && ruff format --check . && mypy src/satelit
pytest                                          # offline: a scripted transport, plus real answers checked against the schemas
SATELIT_API_KEY=sat_live_… pytest tests/test_live.py -s   # about 60 credits
```

To follow a newer API: `curl -o spec/openapi.json https://api.satelit.md/openapi.json`, add any new route to `spec/methods.json`, then regenerate.

## Tested with

| | Versions | What ran |
|---|---|---|
| Python | 3.13.3, 3.11.0 | offline tests, live tests against api.satelit.md (sync and async) |
| Python | 3.11.0 | `pip install git+file://…` of this repository in a fresh virtualenv, then keyless calls |
| Python | 3.13.3 | the four examples, live |
| ruff | 0.17.5 | lint and format |
| mypy | 2.4.1 | `mypy src/satelit`, no issues |
| OS | Windows 11 | all of the above |

CI runs the offline tests and ruff on Python 3.10, 3.11, 3.12 and 3.13; 3.10 and 3.12 were not run on a local machine. The SDK's `User-Agent` (`satelit-python/1.0.0`) was accepted by the API's edge on every live call.

## Troubleshooting

- **401 `auth_required`**: no key reached the API. Set `SATELIT_API_KEY` or pass `api_key`.
- **402 `plan_required`** on `feed` or `export`: those need Business (feed) or Enterprise (export).
- **429 `quota_exceeded`**: this period's credits are spent; `rate["credits_reset"]` says when they return.
- **`timeout`**: the default is 10 s to connect and per read. Raise `timeout` for heavy calls.
- **`network_error` with a certificate message**: the machine's CA store is out of date (on macOS, run Python's `Install Certificates.command`).

## Links

[Docs](https://developer.satelit.md/en/docs/) · [API reference](https://developer.satelit.md/en/reference/) · [Errors](https://developer.satelit.md/en/errors/) · [Rate limits](https://developer.satelit.md/en/rate-limits/) · [Authentication](https://developer.satelit.md/en/authentication/) · [Webhooks](https://developer.satelit.md/en/webhooks/) · [MCP](https://developer.satelit.md/en/mcp/) · [Pricing](https://developer.satelit.md/en/pricing/) · [Console](https://developer.satelit.md/en/console/) · [OpenAPI](https://api.satelit.md/openapi.json)

## Pe scurt (română)

SDK-ul oficial Python pentru API-ul de date Satelit: cursurile BNM, carburanți, tarife, prețuri în magazine, legi, știri, companii, instanțe, filme și cinematografe. Fără dependențe (doar biblioteca standard), Python 3.10+, client sincron `Satelit` și asincron `AsyncSatelit`. Instalare: `pip install git+https://github.com/Satelit-Moldova/satelit-python`. Cheia (`sat_live_…`) se ia din [consolă](https://developer.satelit.md/en/console/) și se ține doar pe server. Fiecare apel întoarce `r.data`, `r.meta`, `r.rate`. Erorile sunt `SatelitError` cu `status`, `code`, `message`, `docs`. Păstrați răspunsurile în cache (cursurile câteva ore, știrile 10-15 minute): un apel Movies costă 40 de credite. Afișați `meta["attribution"]` și „Date: Satelit (satelit.md)” lângă date.

## License

MIT, see [LICENSE](LICENSE).
