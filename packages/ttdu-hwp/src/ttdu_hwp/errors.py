"""Errors raised by the ttdu-hwp client.

Every error carries ``code`` (the service's error code, e.g. ``unsupported``),
``status`` (HTTP status, or ``None`` for client-side checks) and ``details``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


class HwpError(Exception):
    """Base class for all ttdu-hwp errors."""

    code: str = "failed"

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        status: Optional[int] = None,
        details: Optional[Mapping[str, Any]] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        if code:
            self.code = code
        self.status = status
        self.details = dict(details or {})
        self.retry_after = retry_after


class UnsupportedDocumentError(HwpError):
    """The document uses a variant the converter does not read (e.g. protected)."""

    code = "unsupported"


class EncryptedDocumentError(UnsupportedDocumentError):
    """The document is password-protected or distribution-protected (DRM)."""

    code = "unsupported"


class InvalidDocumentError(HwpError):
    """The file is not a readable HWP 5.x / HWPX document (damaged, truncated, other format)."""

    code = "invalid_input"


class LimitExceededError(HwpError):
    """The file is too large, or a damaged file asked for more memory than allowed."""

    code = "resource_limit"


class QuotaExceededError(HwpError):
    """The daily call quota or rate limit was reached. See ``retry_after`` (seconds) when given."""

    code = "rate_limited"


class AuthenticationError(HwpError):
    """The API key (hub) or local key (local runner) was missing or wrong."""

    code = "unauthorized"


class ServiceUnavailableError(HwpError):
    """The service could not be reached or answered with a server error."""

    code = "unavailable"


class ConfigurationError(HwpError):
    """The client settings are invalid (unknown backend, missing local key, ...)."""

    code = "configuration"
