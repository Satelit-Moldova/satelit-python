"""Whole products as NDJSON (``GET /export/{product}``), Enterprise only (else 402 ``plan_required``)."""

from __future__ import annotations

import asyncio
import json
import socket
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Dict, Iterator, Optional

from ._core import _seg
from ._errors import SatelitError

if TYPE_CHECKING:
    from ._client import AsyncSatelit, Satelit

_DONE: Any = object()


def _lines(chunks: Iterator[bytes]) -> Iterator[bytes]:
    buf = b""
    for chunk in chunks:
        buf += chunk
        *whole, buf = buf.split(b"\n")
        yield from whole
    if buf:
        yield buf


def _rows(
    lines: Iterator[bytes],
    on_meta: Optional[Callable[[Dict[str, Any]], None]],
    on_end: Optional[Callable[[Dict[str, Any]], None]],
) -> Iterator[Dict[str, Any]]:
    end = None
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line.decode("utf-8"))
        if isinstance(row, dict) and "_meta" in row:
            if on_meta:
                on_meta(row["_meta"])
        elif isinstance(row, dict) and "_end" in row:
            end = row["_end"]
            if on_end:
                on_end(end)
        else:
            yield row
    if end is None:
        raise SatelitError(200, "export_incomplete", "The export ended without its `_end` line: the file was cut.")


class ExportApi:
    """One export runs at a time per account (429 ``export_running``)."""

    def __init__(self, client: Satelit) -> None:
        self._c = client

    def stream(self, product: str, *, lang: Optional[str] = None, timeout: Optional[float] = None) -> Iterator[bytes]:
        """The raw NDJSON bytes in chunks, to write into a file. The request goes out on the first ``next()``."""
        res = self._c._raw(f"/export/{_seg(product)}", None, lang=lang, timeout=timeout, accept="application/x-ndjson")
        try:
            yield from res.iter_chunks()
        except (TimeoutError, socket.timeout) as e:
            raise SatelitError(0, "timeout", "The export stalled.") from e

    def rows(
        self,
        product: str,
        *,
        on_meta: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_end: Optional[Callable[[Dict[str, Any]], None]] = None,
        lang: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Iterator[Dict[str, Any]]:
        """The rows, one line at a time (memory stays flat). Raises ``export_incomplete`` if ``_end`` is missing."""
        return _rows(_lines(self.stream(product, lang=lang, timeout=timeout)), on_meta, on_end)


class AsyncExportApi:
    """The async form of :class:`ExportApi`; reading runs in a worker thread."""

    def __init__(self, client: AsyncSatelit) -> None:
        self._c = client

    async def stream(
        self, product: str, *, lang: Optional[str] = None, timeout: Optional[float] = None
    ) -> AsyncIterator[bytes]:
        it = self._c._sync.export.stream(product, lang=lang, timeout=timeout)
        while True:
            chunk = await asyncio.to_thread(next, it, _DONE)
            if chunk is _DONE:
                return
            yield chunk

    async def rows(
        self,
        product: str,
        *,
        on_meta: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_end: Optional[Callable[[Dict[str, Any]], None]] = None,
        lang: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        it = self._c._sync.export.rows(product, on_meta=on_meta, on_end=on_end, lang=lang, timeout=timeout)
        while True:
            row = await asyncio.to_thread(next, it, _DONE)
            if row is _DONE:
                return
            yield row
