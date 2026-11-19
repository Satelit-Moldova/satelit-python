"""Every route has a method, every method calls its own route, and real answers match the schemas."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import typing
from pathlib import Path
from typing import Any, Dict, List

import pytest

import satelit.types
from satelit import AsyncSatelit, Satelit

from conftest import FakeTransport, ok

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "spec/openapi.json").read_text(encoding="utf-8"))
SPEC["components"]["schemas"].update(json.loads((ROOT / "spec/overrides.json").read_text(encoding="utf-8"))["schemas"])
TABLE = json.loads((ROOT / "spec/method-table.json").read_text(encoding="utf-8"))
SAMPLES = json.loads((Path(__file__).parent / "fixtures/samples.json").read_text(encoding="utf-8"))
BY_HAND = {"/export/{product}", "/movies/img/{size}/{file}"}


def resolve(obj: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def required_kwargs(fn: Any) -> Dict[str, Any]:
    sig = inspect.signature(fn)
    return {n: "x" for n, p in sig.parameters.items() if p.kind is p.KEYWORD_ONLY and p.default is p.empty}


def test_every_route_has_a_method() -> None:
    covered = {path for _, path, _, _ in TABLE}
    assert sorted(set(SPEC["paths"]) - covered - BY_HAND) == []


def test_each_method_calls_its_route() -> None:
    t = FakeTransport([ok([])])
    c = Satelit(api_key="sat_live_x", transport=t)
    for name, path, _, _ in TABLE:
        fn = resolve(c, name)
        holes = [f"v{i}" for i, _ in enumerate(re.findall(r"\{\w+\}", path))]
        fn(*holes, **required_kwargs(fn))
        want = "/v1" + path
        for h in holes:
            want = re.sub(r"\{\w+\}", h, want, count=1)
        assert t.calls[-1].path == want, name
    assert len(t.calls) == len(TABLE)


def test_async_methods_mirror_sync() -> None:
    t = FakeTransport([ok([])])
    a = AsyncSatelit(api_key="sat_live_x", transport=t)

    async def run() -> None:
        for name, path, _, _ in TABLE:
            fn = resolve(a, name)
            assert inspect.iscoroutinefunction(fn), name
            holes = [f"v{i}" for i, _ in enumerate(re.findall(r"\{\w+\}", path))]
            await fn(*holes, **required_kwargs(fn))

    asyncio.run(run())
    assert len(t.calls) == len(TABLE)


def test_type_hints_resolve() -> None:
    # Every TypedDict's annotations resolve to real types (no dangling names).
    for name in dir(satelit.types):
        obj = getattr(satelit.types, name)
        if isinstance(obj, type) and issubclass(obj, dict) and hasattr(obj, "__annotations__"):
            typing.get_type_hints(obj)
    hints = typing.get_type_hints(Satelit.__init__)
    assert "api_key" in hints


# -- real answers against the OpenAPI schemas (the source of the TypedDicts)


def validate(schema: Any, value: Any, path: str = "$", out: List[str] | None = None) -> List[str]:
    out = [] if out is None else out
    if not isinstance(schema, dict):
        return out
    if "$ref" in schema:
        return validate(SPEC["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]], value, path, out)
    for s in schema.get("allOf", []):
        validate(s, value, path, out)
    alts = schema.get("oneOf") or schema.get("anyOf")
    if alts:
        if not any(not validate(s, value, path, []) for s in alts):
            out.append(f"{path}: matches none of oneOf")
        return out
    types = schema.get("type")
    types = types if isinstance(types, list) else [types] if types else None
    if types and not any(_is(t, value) for t in types):
        out.append(f"{path}: {str(value)[:60]!r} is not {types}")
        return out
    if "enum" in schema and value is not None and value not in schema["enum"]:
        out.append(f"{path}: {value!r} not in enum")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            if isinstance(v, str) and re.match(r"^\.\.\. \d+ more$", v):
                continue  # samples.json trims lists to 3 items
            validate(schema["items"], v, f"{path}[{i}]", out)
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                out.append(f"{path}: missing {k}")
        for k, v in value.items():
            if k in schema.get("properties", {}):
                validate(schema["properties"][k], v, f"{path}.{k}", out)
            elif isinstance(schema.get("additionalProperties"), dict):
                validate(schema["additionalProperties"], v, f"{path}.{k}", out)
    return out


def _is(t: str, v: Any) -> bool:
    return {
        "null": v is None,
        "string": isinstance(v, str),
        "boolean": isinstance(v, bool),
        "integer": isinstance(v, int) and not isinstance(v, bool),
        "number": isinstance(v, (int, float)) and not isinstance(v, bool),
        "array": isinstance(v, list),
        "object": isinstance(v, dict),
    }.get(t, True)


def route_of(route: str) -> str:
    path = route.split("?")[0]
    if path in SPEC["paths"]:
        return path
    segs = path.split("/")
    for p in SPEC["paths"]:
        t = p.split("/")
        if len(t) == len(segs) and all(a == b or re.match(r"^\{\w+\}$", a) for a, b in zip(t, segs)):
            return p
    raise AssertionError(route)


@pytest.mark.parametrize("route", list(SAMPLES))
def test_sample_matches_schema(route: str) -> None:
    schema = SPEC["paths"][route_of(route)]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert validate(schema, SAMPLES[route]["body"]) == []
