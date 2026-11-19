"""``Satelit`` (sync, standard library only) and ``AsyncSatelit`` (the same calls, awaited)."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable, Dict, Mapping, Optional

from ._core import DEFAULT_BASE_URL, BaseClient, Lang, RateInfo, Response, Transport
from ._export import AsyncExportApi, ExportApi
from ._resources import _async_attach, _AsyncNamespaces, _AsyncTopLevel, _attach, _Namespaces, _TopLevel

__all__ = ["AsyncSatelit", "Satelit"]


class Satelit(BaseClient, _TopLevel, _Namespaces):
    """The Satelit data API client.

    >>> satelit = Satelit()  # the key from SATELIT_API_KEY
    >>> r = satelit.rates.list()
    >>> r.data[0]["code"], r.meta["attribution"], r.rate["credits_remaining"]
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        lang: Optional[Lang] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        max_retries: int = 2,
        transport: Optional[Transport] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(
            api_key,
            lang=lang,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
            headers=headers,
        )
        _attach(self)
        #: Whole products as NDJSON (Enterprise).
        self.export = ExportApi(self)

    def __enter__(self) -> Satelit:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class AsyncSatelit(_AsyncTopLevel, _AsyncNamespaces):
    """The same client for ``asyncio``: every method is awaited and runs in a worker thread.

    No extra dependency. For hundreds of calls at once, size the default executor
    (``loop.set_default_executor``) to match.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        lang: Optional[Lang] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        max_retries: int = 2,
        transport: Optional[Transport] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._sync = Satelit(
            api_key,
            lang=lang,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
            headers=headers,
        )
        _async_attach(self)
        #: Whole products as NDJSON (Enterprise).
        self.export = AsyncExportApi(self)

    def __repr__(self) -> str:
        return "<Async" + repr(self._sync)[1:]

    @property
    def has_key(self) -> bool:
        return self._sync.has_key

    @property
    def last_meta(self) -> Optional[Dict[str, Any]]:
        return self._sync.last_meta

    @property
    def last_rate(self) -> Optional[RateInfo]:
        return self._sync.last_rate

    def url(self, path: str, query: Optional[Mapping[str, Any]] = None, lang: Optional[str] = None) -> str:
        return self._sync.url(path, query, lang)

    async def get(
        self,
        path: str,
        query: Optional[Mapping[str, Any]] = None,
        *,
        lang: Optional[Lang] = None,
        timeout: Optional[float] = None,
    ) -> Response[Any]:
        """Any GET route: an escape hatch for routes newer than this SDK."""
        return await self._aget(path, query, lang=lang, timeout=timeout)

    async def paginate(
        self, method: Callable[..., Any], *, max_pages: Optional[int] = None, **params: Any
    ) -> AsyncIterator[Any]:
        """``async for t in client.paginate(client.tours.list, country="Turcia"): ...``"""
        page = int(params.pop("page", None) or 1)
        n = 0
        while max_pages is None or n < max_pages:
            r = await method(page=page, **params)
            for item in r.data:
                yield item
            p = r.meta.get("page")
            if not p or page >= p.get("pages", 0) or not r.data:
                return
            page += 1
            n += 1

    async def _aget(
        self, path: str, query: Optional[Mapping[str, Any]], *, lang: Optional[str], timeout: Optional[float]
    ) -> Response[Any]:
        return await asyncio.to_thread(self._sync._get, path, query, lang=lang, timeout=timeout)

    async def __aenter__(self) -> AsyncSatelit:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None
