"""HWP/HWPX (Korean word processor) input for Docling.

Docling has no HWP input format and its plugin system covers OCR, layout and table engines
only, so this package builds a ``DoclingDocument`` directly from the structured result of the
Tools That Don't Upload service (hosted API, or the offline local runner on this computer).
The resulting document works with Docling's exporters and chunkers like any other.

    from docling_ttdu_hwp import convert_hwp
    doc = convert_hwp("notice.hwp")          # DoclingDocument
    print(doc.export_to_markdown())

    from docling_ttdu_hwp import HwpAwareConverter   # needs `docling`
    doc = HwpAwareConverter().convert("any.pdf_or_hwp").document
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from docling_core.types.doc import DocItemLabel, DoclingDocument, TableCell, TableData
from docling_core.types.doc.document import DocumentOrigin

from ttdu_hwp import HwpClient, HwpResult, is_hwp_name, sniff_hwp

__version__ = "0.1.0"

_MIME = {"hwp": "application/x-hwp", "hwpx": "application/hwp+zip"}
# Let docling-core's MIME check (based on the mimetypes registry) accept the HWP types.
mimetypes.add_type("application/x-hwp", ".hwp")
mimetypes.add_type("application/hwp+zip", ".hwpx")


def _table_data(block: Mapping[str, Any]) -> Optional[TableData]:
    rows = [r for r in (block.get("rows") or []) if isinstance(r, list) and r]
    if not rows:
        return None
    n_rows, n_cols = len(rows), max(len(r) for r in rows)
    cells: List[TableCell] = []
    src = block.get("cells")
    if isinstance(src, list) and src:
        for c in src:
            r0, c0 = int(c.get("row", 0)), int(c.get("col", 0))
            rs, cs = max(1, int(c.get("row_span", 1) or 1)), max(1, int(c.get("col_span", 1) or 1))
            if r0 >= n_rows or c0 >= n_cols:
                continue
            rs, cs = min(rs, n_rows - r0), min(cs, n_cols - c0)
            cells.append(
                TableCell(
                    text=str(c.get("text") or ""),
                    row_span=rs,
                    col_span=cs,
                    start_row_offset_idx=r0,
                    end_row_offset_idx=r0 + rs,
                    start_col_offset_idx=c0,
                    end_col_offset_idx=c0 + cs,
                    column_header=False,
                    row_header=False,
                )
            )
    else:
        for i, r in enumerate(rows):
            for j in range(n_cols):
                cells.append(
                    TableCell(
                        text=str(r[j]) if j < len(r) and r[j] is not None else "",
                        start_row_offset_idx=i,
                        end_row_offset_idx=i + 1,
                        start_col_offset_idx=j,
                        end_col_offset_idx=j + 1,
                    )
                )
    return TableData(num_rows=n_rows, num_cols=n_cols, table_cells=cells)


def to_docling_document(result: Union[HwpResult, Mapping[str, Any]], name: str = "document", data: Optional[bytes] = None) -> DoclingDocument:
    """Build a DoclingDocument from an extraction result (``HwpClient.extract``)."""
    blocks = result.blocks if isinstance(result, HwpResult) else result.get("blocks")
    fmt = result.format if isinstance(result, HwpResult) else result.get("format")
    stem = Path(name).stem or "document"
    doc = DoclingDocument(name=stem)
    if data is not None:
        h = int.from_bytes(hashlib.sha256(data).digest()[:8], "big")
        try:
            doc.origin = DocumentOrigin(mimetype=_MIME.get(fmt or "", "application/x-hwp"), binary_hash=h, filename=Path(name).name)
        except ValueError:  # older docling-core without the HWP types registered
            doc.origin = DocumentOrigin(mimetype="application/octet-stream", binary_hash=h, filename=Path(name).name)
    for b in blocks or []:
        kind = b.get("type")
        if kind == "paragraph":
            text = str(b.get("text") or "")
            if text.strip():
                doc.add_text(label=DocItemLabel.TEXT, text=text)
        elif kind == "table":
            td = _table_data(b)
            if td is None:
                continue
            caption = None
            ni = b.get("nested_in")
            if isinstance(ni, Mapping):
                caption = doc.add_text(
                    label=DocItemLabel.CAPTION,
                    text="Table inside a table cell (row %d, column %d)" % (int(ni.get("row") or 0) + 1, int(ni.get("col") or 0) + 1),
                )
            doc.add_table(data=td, caption=caption)
    return doc


def convert_hwp(source: Union[str, Path, bytes], *, name: Optional[str] = None, client: Optional[HwpClient] = None, **client_options: Any) -> DoclingDocument:
    """Convert one .hwp/.hwpx file to a DoclingDocument.

    ``client_options`` are passed to ``ttdu_hwp.HwpClient`` (backend="hub"|"local", api_key, ...).
    With the hub backend the document is sent to toolsthatdontupload.com.
    """
    if isinstance(source, (str, Path)):
        data, name = Path(source).read_bytes(), name or Path(source).name
    else:
        data, name = bytes(source), name or "document.hwp"
    c = client or HwpClient(**client_options)
    return to_docling_document(c.extract(data, name=name), name=name, data=data)


def is_hwp(source: Union[str, Path]) -> bool:
    p = Path(source)
    if is_hwp_name(p.name):
        return True
    try:
        with open(p, "rb") as f:
            return sniff_hwp(f.read(65536)) is not None
    except OSError:
        return False


class HwpConversionResult:
    """Minimal stand-in for docling's ConversionResult for HWP inputs (``.document``, ``.input``)."""

    def __init__(self, document: DoclingDocument, source: str) -> None:
        self.document = document
        self.input = source
        self.status = "success"
        self.errors: List[Any] = []


class HwpAwareConverter:
    """Wraps docling's DocumentConverter: .hwp/.hwpx go to the TTDU service, everything else to Docling."""

    def __init__(self, converter: Any = None, *, client: Optional[HwpClient] = None, **client_options: Any) -> None:
        if converter is None:
            from docling.document_converter import DocumentConverter  # requires the `docling` package

            converter = DocumentConverter()
        self.converter = converter
        self.client = client or HwpClient(**client_options)

    def convert(self, source: Union[str, Path], **kwargs: Any) -> Any:
        if isinstance(source, (str, Path)) and not str(source).startswith(("http://", "https://")) and is_hwp(source):
            return HwpConversionResult(convert_hwp(source, client=self.client), str(source))
        return self.converter.convert(source, **kwargs)


__all__ = ["convert_hwp", "to_docling_document", "is_hwp", "HwpAwareConverter", "HwpConversionResult", "__version__"]
