"""The HTTP core: auth, query, timeouts, retries and errors, on the standard library only."""

from __future__ import annotations

import datetime as _dt
import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    TypedDict,
    TypeVar,
    Union,
)
from urllib.parse import quote, urlencode

from ._errors import SatelitError
from ._version import __version__

T = TypeVar("T")

#: Answer language. Romanian is the default.
Lang = Literal["ro", "ru", "en", "uk"]

DEFAULT_BASE_URL = "https://api.satelit.md/v1"
USER_AGENT = f"satelit-python/{__version__}"
MAX_RETRIES = 3
#: A ``Retry-After`` longer than this is not waited for: the error is raised.
MAX_WAIT_S = 60.0


class RateInfo(TypedDict):
    """What the rate-limit and credit headers said; ``None`` when a header was absent."""

    limit: Optional[int]
    remaining: Optional[int]
    reset: Optional[int]
    credits_cost: Optional[int]
    credits_limit: Optional[int]
    credits_remaining: Optional[int]
    credits_reset: Optional[str]
    retry_after: Optional[float]


class Response(Generic[T]):
    """One answer: ``data``, ``meta`` (sources, attribution, page) and ``rate`` (credits, limits).

    ``r.data``, ``r.meta``, ``r.rate``; ``r["data"]`` works too.
    """

    __slots__ = ("data", "meta", "rate")

    def __init__(self, data: T, meta: Dict[str, Any], rate: RateInfo) -> None:
        self.data = data
        self.meta = meta
        self.rate = rate

    def __getitem__(self, key: str) -> Any:
        if key not in self.__slots__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[Any]:
        # data, meta, rate = client.rates.list()
        return iter((self.data, self.meta, self.rate))

    def __repr__(self) -> str:
        kind = type(self.data).__name__
        size = f" x{len(self.data)}" if isinstance(self.data, (list, dict)) else ""
        return f"<Response data={kind}{size} credits={self.rate.get('credits_cost')}>"


class RawResponse:
    """What a transport returns: status, lowercase headers, and the body."""

    def __init__(self, status: int, headers: Mapping[str, str], body: Any) -> None:
        self.status = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self._body = body  # a file-like object with read(n) and close(), or bytes

    def read(self) -> bytes:
        if isinstance(self._body, (bytes, bytearray)):
            return bytes(self._body)
        try:
            return self._body.read()
        finally:
            self.close()

    def iter_chunks(self, size: int = 65536) -> Iterator[bytes]:
        if isinstance(self._body, (bytes, bytearray)):
            yield bytes(self._body)
            return
        try:
            while True:
                chunk = self._body.read(size)
                if not chunk:
                    break
                yield chunk
        finally:
            self.close()

    def close(self) -> None:
        close = getattr(self._body, "close", None)
        if close:
            close()


#: ``transport(url, headers, timeout) -> RawResponse``. Raise ``TimeoutError`` or ``OSError`` on failure.
Transport = Callable[[str, Dict[str, str], float], RawResponse]


def urllib_transport(url: str, headers: Dict[str, str], timeout: float) -> RawResponse:
    """The default transport: ``urllib.request`` (honours ``HTTPS_PROXY`` and the system's CA store)."""
    if not url.startswith(("https://", "http://")):
        raise ValueError("only http(s) URLs")
    req = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310 (scheme checked above)
    try:
        f = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 (scheme checked above)
        return RawResponse(f.status, dict(f.headers.items()), f)
    except urllib.error.HTTPError as e:
        return RawResponse(e.code, dict(e.headers.items()) if e.headers else {}, e)


def _num(h: Mapping[str, str], name: str, kind: Callable[[Any], Any] = int) -> Any:
    v = h.get(name)
    if v is None or v == "":
        return None
    try:
        return kind(v)
    except ValueError:
        try:
            return kind(float(v))
        except ValueError:
            return None


def parse_rate(h: Mapping[str, str]) -> RateInfo:
    return {
        "limit": _num(h, "x-ratelimit-limit"),
        "remaining": _num(h, "x-ratelimit-remaining"),
        "reset": _num(h, "x-ratelimit-reset"),
        "credits_cost": _num(h, "x-credits-cost"),
        "credits_limit": _num(h, "x-credits-limit"),
        "credits_remaining": _num(h, "x-credits-remaining"),
        "credits_reset": h.get("x-credits-reset"),
        "retry_after": _num(h, "retry-after", float),
    }


def _seg(v: Union[int, str]) -> str:
    """Encodes one path segment."""
    return quote(str(v), safe="")


def _qval(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    if isinstance(v, (list, tuple, set)):
        return ",".join(_qval(x) for x in v)
    return str(v)


class BaseClient:
    """Shared by :class:`satelit.Satelit`; the namespaces are added on top."""

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
        """
        :param api_key: ``sat_live_…``. Defaults to ``SATELIT_API_KEY``. Pass ``""`` for no key (keyless routes).
        :param lang: default answer language: ``ro`` (default), ``ru``, ``en``, ``uk``.
        :param timeout: seconds to connect and for each read (default 10).
        :param max_retries: retries of 429 ``rate_limited`` and 503 with ``Retry-After``; at most 3 (default 2).
        :param transport: ``transport(url, headers, timeout) -> RawResponse``, for tests or another HTTP stack.
        """
        self.__key = os.environ.get("SATELIT_API_KEY") if api_key is None else api_key
        self.lang = lang
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, min(MAX_RETRIES, max_retries))
        self._transport: Transport = transport or urllib_transport
        self._headers = dict(headers or {})
        #: ``meta`` of the last successful answer.
        self.last_meta: Optional[Dict[str, Any]] = None
        #: Credit and rate info of the last answer, also of an error.
        self.last_rate: Optional[RateInfo] = None
        self._sleep: Callable[[float], None] = time.sleep

    @property
    def has_key(self) -> bool:
        """Whether the client holds a key (the key itself is never exposed)."""
        return bool(self.__key)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} base_url={self.base_url!r} key={'set' if self.has_key else 'none'}>"

    def url(self, path: str, query: Optional[Mapping[str, Any]] = None, lang: Optional[str] = None) -> str:
        """The full URL of a route. Lists join with commas; ``None`` values are left out."""
        pairs: List[Tuple[str, str]] = [(k, _qval(v)) for k, v in (query or {}).items() if v is not None]
        lang = lang or self.lang
        if lang and not any(k == "lang" for k, _ in pairs):
            pairs.append(("lang", lang))
        qs = urlencode(pairs, quote_via=quote)
        return f"{self.base_url}{path if path.startswith('/') else '/' + path}" + (f"?{qs}" if qs else "")

    def get(
        self,
        path: str,
        query: Optional[Mapping[str, Any]] = None,
        *,
        lang: Optional[Lang] = None,
        timeout: Optional[float] = None,
    ) -> Response[Any]:
        """Any GET route as a :class:`Response`: an escape hatch for routes newer than this SDK."""
        return self._get(path, query, lang=lang, timeout=timeout)

    def paginate(
        self, method: Callable[..., Response[List[T]]], *, max_pages: Optional[int] = None, **params: Any
    ) -> Iterator[T]:
        """Walks every page of a paged list (``meta.page``) and yields its items.

        ``for t in client.paginate(client.tours.list, country="Turcia", max_pages=3): ...``
        Each page is one call and costs its credits.
        """
        page = int(params.pop("page", None) or 1)
        n = 0
        while max_pages is None or n < max_pages:
            r = method(page=page, **params)
            yield from r.data
            p = r.meta.get("page")
            if not p or page >= p.get("pages", 0) or not r.data:
                return
            page += 1
            n += 1

    # -- internals

    def _get(
        self, path: str, query: Optional[Mapping[str, Any]], *, lang: Optional[str], timeout: Optional[float]
    ) -> Response[Any]:
        res, rate = self._send(path, query, lang, timeout, "application/json")
        try:
            body = res.read()
        except (TimeoutError, socket.timeout) as e:
            raise self._timeout(timeout) from e
        except OSError as e:
            raise SatelitError(0, "network_error", f"Network error: {e}") from e
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise SatelitError(res.status, "bad_response", "The answer is not JSON.", rate=rate) from e
        if not isinstance(parsed, dict) or "data" not in parsed:
            raise SatelitError(res.status, "bad_response", "The answer has no `data`.", rate=rate)
        meta = parsed.get("meta") or {"credits": 0, "updated_at": None, "sources": [], "attribution": None}
        self.last_meta = meta
        return Response(parsed["data"], meta, rate)

    def _raw(
        self,
        path: str,
        query: Optional[Mapping[str, Any]],
        *,
        lang: Optional[str],
        timeout: Optional[float],
        accept: str,
    ) -> RawResponse:
        res, _ = self._send(path, query, lang, timeout, accept)
        return res

    def _send(
        self, path: str, query: Optional[Mapping[str, Any]], lang: Optional[str], timeout: Optional[float], accept: str
    ) -> Tuple[RawResponse, RateInfo]:
        url = self.url(path, query, lang)
        headers = {"Accept": accept, "User-Agent": USER_AGENT, **self._headers}
        if self.__key:
            headers["Authorization"] = f"Bearer {self.__key}"
        t = self.timeout if timeout is None else timeout
        attempt = 0
        while True:
            try:
                res = self._transport(url, headers, t)
            except (TimeoutError, socket.timeout) as e:
                raise self._timeout(t) from e
            except urllib.error.URLError as e:
                if isinstance(e.reason, (TimeoutError, socket.timeout)):
                    raise self._timeout(t) from e
                raise SatelitError(0, "network_error", f"Network error: {e.reason}") from e
            except OSError as e:
                raise SatelitError(0, "network_error", f"Network error: {e}") from e
            rate = parse_rate(res.headers)
            self.last_rate = rate
            if 200 <= res.status < 300:
                return res, rate
            try:
                err = SatelitError.from_body(res.status, res.read(), rate)
            except (TimeoutError, socket.timeout) as e:
                raise self._timeout(t) from e
            wait = self._retry_wait(err, attempt)
            if wait is None:
                raise err
            self._sleep(wait)
            attempt += 1

    def _retry_wait(self, err: SatelitError, attempt: int) -> Optional[float]:
        # Only 429 rate_limited and 503 with Retry-After are retried, never quota_exceeded.
        if attempt >= self.max_retries:
            return None
        ra = err.retry_after
        if err.status == 429 and err.code == "rate_limited":
            if ra is not None:
                return ra if ra <= MAX_WAIT_S else None
            return float(2**attempt)
        if err.status == 503 and ra is not None:
            return ra if ra <= MAX_WAIT_S else None
        return None

    def _timeout(self, t: Optional[float]) -> SatelitError:
        return SatelitError(0, "timeout", f"No answer in {t if t is not None else self.timeout} s.")
