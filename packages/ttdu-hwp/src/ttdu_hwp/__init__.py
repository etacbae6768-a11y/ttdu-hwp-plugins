"""ttdu-hwp: HWP/HWPX to text, Markdown and DOCX through the Tools That Don't Upload API
or the offline local runner. This package does not contain an HWP parser; it calls one.
"""

__version__ = "0.1.0"

from .errors import (  # noqa: E402
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
from .client import HWP_EXTENSIONS, HWP_MIMETYPES, HwpClient, HwpResult, is_hwp_name, sniff_hwp  # noqa: E402
from .formatting import to_docx_blocks, to_markdown  # noqa: E402

__all__ = [
    "__version__",
    "HwpClient",
    "HwpResult",
    "HWP_EXTENSIONS",
    "HWP_MIMETYPES",
    "is_hwp_name",
    "sniff_hwp",
    "to_markdown",
    "to_docx_blocks",
    "HwpError",
    "UnsupportedDocumentError",
    "EncryptedDocumentError",
    "InvalidDocumentError",
    "LimitExceededError",
    "QuotaExceededError",
    "AuthenticationError",
    "ServiceUnavailableError",
    "ConfigurationError",
]
