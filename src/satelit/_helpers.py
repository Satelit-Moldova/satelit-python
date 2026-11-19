"""``feed.iterate()``, mixed into the generated feed namespaces."""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Dict, Iterator, Optional, Sequence, Union


class _FeedHelpers:
    list: Callable[..., Any]

    def iterate(
        self,
        *,
        after: Optional[str] = None,
        types: Optional[Union[str, Sequence[str]]] = None,
        limit: Optional[int] = None,
        on_cursor: Optional[Callable[[str], None]] = None,
        max_pages: Optional[int] = None,
        lang: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yields events oldest first, following ``meta.next`` until ``meta.has_more`` is false.

        Keep the last cursor (``on_cursor`` gets every one) and start from it next time.
        Business and Enterprise plans; others get 402 ``plan_required``.
        """
        n = 0
        while max_pages is None or n < max_pages:
            r = self.list(after=after, types=types, limit=limit, lang=lang, timeout=timeout)
            yield from r.data
            nxt = r.meta.get("next")
            if nxt:
                after = nxt
                if on_cursor:
                    on_cursor(nxt)
            if not r.meta.get("has_more") or not nxt or not r.data:
                return
            n += 1


class _AsyncFeedHelpers:
    list: Callable[..., Any]

    async def iterate(
        self,
        *,
        after: Optional[str] = None,
        types: Optional[Union[str, Sequence[str]]] = None,
        limit: Optional[int] = None,
        on_cursor: Optional[Callable[[str], None]] = None,
        max_pages: Optional[int] = None,
        lang: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """The async form of ``feed.iterate``."""
        n = 0
        while max_pages is None or n < max_pages:
            r = await self.list(after=after, types=types, limit=limit, lang=lang, timeout=timeout)
            for ev in r.data:
                yield ev
            nxt = r.meta.get("next")
            if nxt:
                after = nxt
                if on_cursor:
                    on_cursor(nxt)
            if not r.meta.get("has_more") or not nxt or not r.data:
                return
            n += 1
