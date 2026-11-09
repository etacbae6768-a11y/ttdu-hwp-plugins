"""MarkItDown plugin: HWP/HWPX (Korean word processor) to Markdown.

The conversion runs in the Tools That Don't Upload service, either the hosted API
(the document is sent to toolsthatdontupload.com) or the offline local runner on this
computer (``TTDU_HWP_BACKEND=local``). See README.md.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, BinaryIO, Dict, Optional, Tuple

from markitdown import DocumentConverter, DocumentConverterResult, MarkItDown, StreamInfo

from ttdu_hwp import HWP_EXTENSIONS, HWP_MIMETYPES, HwpClient, HwpError, sniff_hwp

__version__ = "0.1.0"
__plugin_interface_version__ = 1  # MarkItDown plugin interface

_OPTION_KEYS = {
    "ttdu_hwp_backend": "backend",
    "ttdu_api_key": "api_key",
    "ttdu_hub_url": "hub_url",
    "ttdu_local_url": "local_url",
    "ttdu_local_key": "local_key",
    "ttdu_local_key_file": "local_key_file",
    "ttdu_timeout": "timeout",
}


def _client_options(kwargs: dict) -> dict:
    return {v: kwargs[k] for k, v in _OPTION_KEYS.items() if kwargs.get(k) is not None}


def register_converters(markitdown: MarkItDown, **kwargs: Any) -> None:
    """Called by MarkItDown when plugins are enabled (``enable_plugins=True`` / ``--use-plugins``).

    Optional keyword arguments given to ``MarkItDown(...)``: ttdu_hwp_backend ("hub" | "local"),
    ttdu_api_key, ttdu_hub_url, ttdu_local_url, ttdu_local_key, ttdu_local_key_file, ttdu_timeout.
    Environment variables (TTDU_HWP_BACKEND, TTDU_API_KEY, ...) are used when these are not given.
    """
    markitdown.register_converter(HwpConverter(**_client_options(kwargs)))


class HwpConverter(DocumentConverter):
    """Converts .hwp (HWP 5.x) and .hwpx documents to Markdown (paragraphs and tables)."""

    def __init__(self, client: Optional[HwpClient] = None, **client_options: Any) -> None:
        super().__init__()
        self._client = client
        self._client_options = client_options
        self._failures: Dict[Tuple[str, str], Tuple[float, HwpError]] = {}

    @property
    def client(self) -> HwpClient:
        if self._client is None:
            self._client = HwpClient(**self._client_options)
        return self._client

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        ext = (stream_info.extension or "").lower()
        mime = (stream_info.mimetype or "").lower()
        if ext in HWP_EXTENSIONS or any(mime.startswith(m) for m in HWP_MIMETYPES):
            return True
        # No usable name or type: look at the first bytes, then put the stream back.
        if ext or (mime and mime not in ("application/octet-stream", "application/zip", "application/x-ole-storage", "application/cdfv2")):
            return False
        pos = file_stream.tell()
        try:
            head = file_stream.read(65536)
        finally:
            file_stream.seek(pos)
        return sniff_hwp(head or b"") is not None

    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> DocumentConverterResult:
        client = HwpClient(**{**self._client_options, **_client_options(kwargs)}) if _client_options(kwargs) else self.client
        name = stream_info.filename or ("document" + ((stream_info.extension or "").lower() if (stream_info.extension or "").lower() in HWP_EXTENSIONS else ".hwp"))
        data = file_stream.read()
        # MarkItDown may call a converter once per stream-info guess for the same bytes. Re-raise a
        # recent failure instead of sending the same file again (each hub call counts against the quota).
        key = (hashlib.sha256(data).hexdigest(), client.backend)
        now = time.monotonic()
        for k in [k for k, (t, _) in self._failures.items() if now - t > 60]:
            del self._failures[k]
        if key in self._failures:
            raise self._failures[key][1]
        try:
            result = client.markdown(data, name=name)
        except HwpError as e:
            self._failures[key] = (now, e)
            raise
        return DocumentConverterResult(markdown=result.markdown or "")
