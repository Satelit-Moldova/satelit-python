# Changelog

## 1.0.0 — 2026-11-19

- First release: a typed client for every GET route of the Satelit data API `/v1` (105 methods, `TypedDict`s generated from the OpenAPI document).
- `Satelit` (standard library only) and `AsyncSatelit` (the same methods, awaited).
- `Response` with `data`, `meta`, `rate`; `last_meta` and `last_rate` on the client.
- `SatelitError` with `status`, `code`, `message`, `docs`, `fields`, `retry_after`, `choose`, `rate`.
- 10 s timeout; retries of 429 `rate_limited` and 503 with `Retry-After` only, at most 3.
- `paginate()` over `meta.page`, `feed.iterate()` over `meta.next`, `export.rows()` and `export.stream()` for NDJSON exports.
