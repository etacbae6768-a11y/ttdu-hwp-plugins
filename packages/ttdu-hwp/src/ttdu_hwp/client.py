"""Small HTTP client for HWP/HWPX conversion.

Two backends:

* ``hub``   - the hosted API at https://toolsthatdontupload.com/v1/hwp/{text,markdown,docx}.
              **The document is sent to that server** (processed in memory for the one request,
              not stored). Without a key: 20 calls a day per IP address. With a key: 20 free file
              calls a day, then credits (see https://toolsthatdontupload.com/docs/hwp/).
* ``local`` - the offline runner on this computer (``ttdu serve``, 127.0.0.1 only). Nothing leaves
              the computer.

Settings (argument > environment variable > default):

==================  =========================  =====================================
argument            environment variable       default
==================  =========================  =====================================
backend             TTDU_HWP_BACKEND           ``hub`` (warns once until set)
api_key             TTDU_API_KEY               none (IP quota)
hub_url             TTDU_HUB_URL               https://toolsthatdontupload.com
local_url           TTDU_LOCAL_URL             http://127.0.0.1:8790
local_key           TTDU_LOCAL_KEY             read from ``local_key_file``
local_key_file      TTDU_LOCAL_KEY_FILE        none
timeout             TTDU_HWP_TIMEOUT           120 seconds
==================  =========================  =====================================

Only the Python standard library is used.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import uuid
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Mapping, Optional, Tuple, Union
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlsplit

from . import __version__
from .errors import (
    AuthenticationError,
    ConfigurationError,
    EncryptedDocumentError,
    HwpError,
    InvalidDocumentError,
    LimitExceededError,
    QuotaExceededError,
    ServiceUnavailableError,
    UnsupportedDocumentError,
)
from .formatting import to_docx_blocks, to_markdown

DEFAULT_HUB_URL = "https://toolsthatdontupload.com"
DEFAULT_LOCAL_URL = "http://127.0.0.1:8790"
HUB_MAX_BYTES = 15 * 1024 * 1024
LOCAL_MAX_BYTES = 200 * 1024 * 1024
HWP_EXTENSIONS = (".hwp", ".hwpx")
HWP_MIMETYPES = (
    "application/x-hwp",
    "application/haansofthwp",
    "application/vnd.hancom.hwp",
    "application/hwp",
    "application/vnd.hancom.hwpx",
    "application/haansofthwpx",
    "application/hwp+zip",
    "application/x-hwpx",
)
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
_ENCRYPTED_REASONS = {"encrypted", "password", "drm", "distribution", "distribution_protected"}
_warned_hub = False

Source = Union[bytes, bytearray, memoryview, str, "os.PathLike[str]", BinaryIO]


@dataclass
class HwpResult:
    """Result of one conversion."""

    format: Optional[str]
    stats: Dict[str, Any] = field(default_factory=dict)
    engine: Dict[str, Any] = field(default_factory=dict)
    text: Optional[str] = None
    blocks: Optional[List[Dict[str, Any]]] = None
    markdown: Optional[str] = None
    docx: Optional[bytes] = None
    docx_name: Optional[str] = None
    backend: str = "hub"


def _env(name: str) -> Optional[str]:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None


def _read_source(source: Source, name: Optional[str]) -> Tuple[bytes, str]:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source), name or "document.hwp"
    if isinstance(source, (str, os.PathLike)):
        p = Path(source)
        return p.read_bytes(), name or p.name
    if hasattr(source, "read"):
        data = source.read()
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("file object must be opened in binary mode")
        guess = getattr(source, "name", None)
        return bytes(data), name or (os.path.basename(guess) if isinstance(guess, str) else "document.hwp")
    raise TypeError("source must be bytes, a path or a binary file object")


def _multipart(fields: List[Tuple[str, Any]]) -> Tuple[bytes, str]:
    """fields: (name, str) for text, (name, (filename, bytes)) for files."""
    boundary = "----ttdu-hwp-" + uuid.uuid4().hex
    out = bytearray()
    for key, value in fields:
        out += b"--" + boundary.encode() + b"\r\n"
        if isinstance(value, tuple):
            fname = value[0].replace("\\", "_").replace('"', "_").replace("\r", " ").replace("\n", " ")
            out += ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (key, fname)).encode("utf-8")
            out += b"Content-Type: application/octet-stream\r\n\r\n" + value[1] + b"\r\n"
        else:
            out += ('Content-Disposition: form-data; name="%s"\r\n\r\n' % key).encode("utf-8")
            out += str(value).encode("utf-8") + b"\r\n"
    out += b"--" + boundary.encode() + b"--\r\n"
    return bytes(out), "multipart/form-data; boundary=" + boundary


def _retry_after(headers: Any) -> Optional[float]:
    for h in ("Retry-After", "RateLimit-Reset", "X-RateLimit-Reset"):
        v = headers.get(h) if headers is not None else None
        if v:
            try:
                return float(v)
            except ValueError:
                pass
    return None


def _raise_for(status: int, body: bytes, headers: Any, backend: str) -> None:
    try:
        j = json.loads(body.decode("utf-8"))
    except Exception:
        j = {}
    if not isinstance(j, dict):
        j = {}
    code = j.get("code")
    if not code and isinstance(j.get("error"), dict):
        code = j["error"].get("code")
    details = j.get("details") if isinstance(j.get("details"), dict) else {}
    detail = j.get("detail") or j.get("message") or j.get("title") or ("HTTP %d" % status)
    where = "local runner" if backend == "local" else "hub API"
    msg = "%s: %s" % (where, detail)
    kw = dict(code=code, status=status, details=details)
    reason = str(details.get("reason") or "").lower()
    if code == "unsupported":
        if reason in _ENCRYPTED_REASONS or not reason:
            raise EncryptedDocumentError(
                "%s: the document is password- or distribution-protected (or another unsupported variant); "
                "save it without protection and try again." % where,
                **kw,
            )
        raise UnsupportedDocumentError(msg, **kw)
    if code == "invalid_input":
        raise InvalidDocumentError("%s: the file is damaged or is not an HWP 5.x / HWPX document." % where, **kw)
    if code == "resource_limit" or status == 413:
        raise LimitExceededError(
            "%s: the file is too large or a damaged file asked for too much memory (%s)." % (where, detail), **kw
        )
    if status in (402, 429) or code in ("rate_limited", "quota_exceeded", "insufficient_credits", "credits_exhausted"):
        raise QuotaExceededError(
            "%s: the call quota was reached (%s). Wait, add an API key with credits, or use the local runner." % (where, detail),
            retry_after=_retry_after(headers),
            **kw,
        )
    if status in (401, 403):
        hint = "check TTDU_LOCAL_KEY / local-api-key.txt" if backend == "local" else "check TTDU_API_KEY"
        raise AuthenticationError("%s (%s)" % (msg, hint), **kw)
    if status >= 500:
        raise ServiceUnavailableError(msg, **kw)
    raise HwpError(msg, **kw)


class HwpClient:
    """Convert HWP/HWPX through the hub API or the local runner."""

    def __init__(
        self,
        backend: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        hub_url: Optional[str] = None,
        local_url: Optional[str] = None,
        local_key: Optional[str] = None,
        local_key_file: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        explicit = backend or _env("TTDU_HWP_BACKEND")
        self.backend = (explicit or "hub").lower()
        if self.backend not in ("hub", "local"):
            raise ConfigurationError("backend must be 'hub' or 'local', got %r" % self.backend)
        self._explicit_backend = bool(explicit)
        self.api_key = api_key or _env("TTDU_API_KEY")
        self.hub_url = (hub_url or _env("TTDU_HUB_URL") or DEFAULT_HUB_URL).rstrip("/")
        self.local_url = (local_url or _env("TTDU_LOCAL_URL") or DEFAULT_LOCAL_URL).rstrip("/")
        self._local_key = local_key or _env("TTDU_LOCAL_KEY")
        self._local_key_file = local_key_file or _env("TTDU_LOCAL_KEY_FILE")
        self.timeout = float(timeout or _env("TTDU_HWP_TIMEOUT") or 120)
        self._check_urls()

    # ---- settings -------------------------------------------------------------------------
    def _check_urls(self) -> None:
        h = urlsplit(self.hub_url)
        if h.scheme != "https" and (h.hostname or "") not in _LOCAL_HOSTS:
            raise ConfigurationError("hub_url must use https (got %s)" % self.hub_url)
        l = urlsplit(self.local_url)
        if l.scheme != "http" or (l.hostname or "") not in _LOCAL_HOSTS:
            raise ConfigurationError(
                "local_url must be http://127.0.0.1:<port> (the local runner answers only on this computer), got %s"
                % self.local_url
            )

    @property
    def local_key(self) -> str:
        if self._local_key:
            return self._local_key
        if self._local_key_file:
            try:
                k = Path(self._local_key_file).read_text(encoding="utf-8").strip()
            except OSError as e:
                raise ConfigurationError("cannot read local key file %s: %s" % (self._local_key_file, e))
            if k:
                self._local_key = k
                return k
        raise ConfigurationError(
            "the local runner needs its key: set TTDU_LOCAL_KEY, or TTDU_LOCAL_KEY_FILE to the path of local-api-key.txt"
        )

    def _note_hub(self) -> None:
        global _warned_hub
        if not self._explicit_backend and not _warned_hub:
            _warned_hub = True
            warnings.warn(
                "ttdu-hwp: sending the document to %s for conversion (processed in memory, not stored). "
                "Set TTDU_HWP_BACKEND=hub to confirm and silence this, or TTDU_HWP_BACKEND=local to use the "
                "offline runner on this computer." % self.hub_url,
                UserWarning,
                stacklevel=4,
            )

    # ---- HTTP -----------------------------------------------------------------------------
    def _post(self, url: str, body: bytes, ctype: str, headers: Mapping[str, str]) -> Dict[str, Any]:
        h = {"Content-Type": ctype, "Accept": "application/json", "User-Agent": "ttdu-hwp/%s (python)" % __version__}
        h.update(headers)
        req = urlrequest.Request(url, data=body, headers=h, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urlerror.HTTPError as e:
            _raise_for(e.code, e.read() or b"", e.headers, self.backend)
            raise  # pragma: no cover
        except (urlerror.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            reason = getattr(e, "reason", e)
            hint = " Is `ttdu serve` running?" if self.backend == "local" else ""
            raise ServiceUnavailableError("cannot reach %s: %s.%s" % (url, reason, hint)) from e
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise ServiceUnavailableError("unexpected response from %s" % url) from e

    def _check_size(self, data: bytes) -> None:
        limit = LOCAL_MAX_BYTES if self.backend == "local" else HUB_MAX_BYTES
        if len(data) > limit:
            raise LimitExceededError(
                "the file is %.1f MB; the %s accepts up to %d MB" % (len(data) / 1048576, "local runner" if self.backend == "local" else "hub API", limit // 1048576),
                status=None,
                details={"bytes": len(data), "limit": limit},
            )
        if not data:
            raise InvalidDocumentError("the file is empty", status=None)

    def _hub(self, op: str, data: bytes, name: str) -> Dict[str, Any]:
        self._note_hub()
        body, ctype = _multipart([("file", (name, data))])
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        j = self._post(self.hub_url + "/v1/hwp/" + op, body, ctype, headers)
        if not j.get("ok"):
            _raise_for(422, json.dumps(j).encode(), None, "hub")
        return j

    def _local_tool(self, tool: str, files: List[Tuple[str, bytes]], options: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        fields: List[Tuple[str, Any]] = [("files", f) for f in files]
        if options is not None:
            fields.append(("options", json.dumps(options, ensure_ascii=False)))
        body, ctype = _multipart(fields)
        j = self._post(self.local_url + "/v1/tools/" + tool + "/run", body, ctype, {"X-API-Key": self.local_key})
        if not j.get("ok"):
            _raise_for(422, json.dumps(j).encode(), None, "local")
        return j

    # ---- public API -----------------------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        """Local runner only: GET /v1/health."""
        try:
            with urlrequest.urlopen(self.local_url + "/v1/health", timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            raise ServiceUnavailableError("local runner not reachable at %s: %s" % (self.local_url, e)) from e

    def extract(self, source: Source, name: Optional[str] = None) -> HwpResult:
        """Text plus structured blocks (paragraphs, tables with merged-cell spans)."""
        data, name = _read_source(source, name)
        self._check_size(data)
        if self.backend == "hub":
            j = self._hub("text", data, name)
            return HwpResult(j.get("format"), j.get("stats") or {}, j.get("engine") or {}, j.get("text"), j.get("blocks"), backend="hub")
        d = self._local_tool("hwp.extract_text", [(name, data)])["data"] or {}
        return HwpResult(d.get("format"), d.get("stats") or {}, d.get("engine") or {}, d.get("text"), d.get("blocks"), backend="local")

    def markdown(self, source: Source, name: Optional[str] = None) -> HwpResult:
        data, name = _read_source(source, name)
        self._check_size(data)
        if self.backend == "hub":
            j = self._hub("markdown", data, name)
            return HwpResult(j.get("format"), j.get("stats") or {}, j.get("engine") or {}, markdown=j.get("markdown"), backend="hub")
        r = self.extract(data, name)
        r.markdown = to_markdown({"blocks": r.blocks or []})
        return r

    def docx(self, source: Source, name: Optional[str] = None) -> HwpResult:
        """Editable DOCX (paragraphs and tables). ``result.docx`` holds the bytes."""
        data, name = _read_source(source, name)
        self._check_size(data)
        if self.backend == "hub":
            j = self._hub("docx", data, name)
            o = (j.get("outputs") or [{}])[0]
            return HwpResult(j.get("format"), j.get("stats") or {}, j.get("engine") or {}, docx=base64.b64decode(o.get("base64") or ""), docx_name=o.get("name"), backend="hub")
        r = self.extract(data, name)
        stem = _stem(name)
        j = self._local_tool("doc.write_docx", [], {"blocks": to_docx_blocks({"blocks": r.blocks or []}), "file_name": stem})
        o = (j.get("outputs") or [{}])[0]
        r.docx, r.docx_name = base64.b64decode(o.get("base64") or ""), o.get("name")
        return r


def _stem(name: str) -> str:
    import re

    s = re.sub(r"\.[^.]+$", "", str(name))
    s = re.sub(r'[\\/:*?"<>|\u0000-\u001f]+', "_", s)[:100]
    return s or "document"


def is_hwp_name(name: Optional[str]) -> bool:
    return bool(name) and str(name).lower().endswith(HWP_EXTENSIONS)


def sniff_hwp(head: bytes) -> Optional[str]:
    """Best-effort format sniff from the first bytes: 'hwpx', 'hwp' or None.

    HWP 5.x is an OLE compound file whose FileHeader stream starts with "HWP Document File";
    HWPX is a ZIP whose first entry is "mimetype" = application/hwp+zip.
    """
    if head[:4] == b"PK\x03\x04" and b"mimetype" in head[:64] and b"application/hwp+zip" in head[:200]:
        return "hwpx"
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" and b"HWP Document File" in head:
        return "hwp"
    return None
