from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from ._core import RateInfo

__all__ = ["SatelitError"]


class SatelitError(Exception):
    """Every failure of a call.

    ``status`` is 0 for a timeout or a network error. ``code`` is the API's code
    (``auth_required``, ``key_invalid``, ``plan_required``, ``not_available``, ``account_suspended``,
    ``not_found``, ``invalid``, ``rate_limited``, ``quota_exceeded``, ``export_running``, ``busy``,
    ``server_error``) or the SDK's own (``timeout``, ``network_error``, ``bad_response``,
    ``export_incomplete``).
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        docs: Optional[str] = None,
        fields: Optional[List[str]] = None,
        retry_after: Optional[float] = None,
        choose: Optional[str] = None,
        rate: Optional[RateInfo] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        #: Link to the error's page in the docs.
        self.docs = docs
        #: For 422 ``invalid``: the parameters that were wrong.
        self.fields = fields
        #: Seconds to wait (``Retry-After``), on 429 and 503.
        self.retry_after = retry_after if retry_after is not None else (rate["retry_after"] if rate else None)
        #: For 402 ``plan_required`` without a plan: the pricing page.
        self.choose = choose
        #: Credit and rate headers of the failed answer.
        self.rate = rate

    def __str__(self) -> str:
        return f"{self.status} {self.code}: {self.message}"

    def __repr__(self) -> str:
        return f"SatelitError(status={self.status!r}, code={self.code!r}, message={self.message!r})"

    @classmethod
    def from_body(cls, status: int, body: bytes, rate: RateInfo) -> SatelitError:
        """Builds the error from a non-2xx answer (``{"error": {code, message, docs, fields?, choose?}}``)."""
        err: Any = None
        try:
            parsed = json.loads(body.decode("utf-8"))
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
                err = parsed["error"]
        except (ValueError, UnicodeDecodeError):
            err = None
        err = err or {}

        def s(v: Any) -> Optional[str]:
            return v if isinstance(v, str) else None

        fields = err.get("fields")
        return cls(
            status,
            s(err.get("code")) or f"http_{status}",
            s(err.get("message")) or f"HTTP {status}",
            docs=s(err.get("docs")),
            fields=[str(f) for f in fields] if isinstance(fields, list) else None,
            choose=s(err.get("choose")),
            retry_after=rate.get("retry_after"),
            rate=rate,
        )
