import pytest

pytest.importorskip("docling_core")
from docling_ttdu_hwp import HwpAwareConverter, convert_hwp, to_docling_document  # noqa: E402
from ttdu_hwp import EncryptedDocumentError, HwpClient  # noqa: E402

BLOCKS = [
    {"type": "paragraph", "text": "근로계약서"},
    {"type": "paragraph", "text": ""},
    {
        "type": "table",
        "rows": [["성명", "", "홍길동"], ["주소", "서울", ""]],
        "cells": [
            {"row": 0, "col": 0, "row_span": 1, "col_span": 2, "text": "성명"},
            {"row": 0, "col": 2, "row_span": 1, "col_span": 1, "text": "홍길동"},
            {"row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": "주소"},
            {"row": 1, "col": 1, "row_span": 1, "col_span": 2, "text": "서울"},
        ],
    },
    {"type": "table", "rows": [["x"]], "nested_in": {"table": 0, "row": 1, "col": 1}},
]


def test_document_structure():
    doc = to_docling_document({"format": "hwp", "blocks": BLOCKS}, name="계약.hwp", data=b"abc")
    assert doc.name == "계약"
    assert doc.origin.filename == "계약.hwp" and doc.origin.mimetype == "application/x-hwp"
    assert [t.text for t in doc.texts] == ["근로계약서", "Table inside a table cell (row 2, column 2)"]
    assert len(doc.tables) == 2
    t = doc.tables[0].data
    assert (t.num_rows, t.num_cols) == (2, 3)
    first = [c for c in t.table_cells if c.start_row_offset_idx == 0 and c.start_col_offset_idx == 0][0]
    assert first.col_span == 2 and first.text == "성명"
    md = doc.export_to_markdown()
    assert "근로계약서" in md and "홍길동" in md


def test_convert_hwp_via_mock_local(svc, tmp_path):
    svc.reply = (200, {"ok": True, "data": {"format": "hwpx", "blocks": BLOCKS}}, {})
    p = tmp_path / "a.hwpx"
    p.write_bytes(b"PK\x03\x04data")
    doc = convert_hwp(p, backend="local", local_url=svc.url, local_key="k" * 40)
    assert doc.origin.mimetype == "application/hwp+zip"
    assert svc.calls[0]["path"] == "/v1/tools/hwp.extract_text/run"


def test_errors_propagate(svc, tmp_path):
    svc.reply = (422, {"code": "unsupported", "details": {"reason": "encrypted"}}, {})
    p = tmp_path / "a.hwp"
    p.write_bytes(b"xx")
    with pytest.raises(EncryptedDocumentError):
        convert_hwp(p, client=HwpClient("hub", hub_url=svc.url))


def test_aware_converter_routes(svc, tmp_path):
    class Fake:
        def convert(self, source, **kw):
            return "docling:" + str(source)

    svc.reply = (200, {"ok": True, "blocks": BLOCKS}, {})
    h = tmp_path / "b.hwp"
    h.write_bytes(b"xx")
    o = tmp_path / "b.pdf"
    o.write_bytes(b"%PDF")
    conv = HwpAwareConverter(Fake(), client=HwpClient("hub", hub_url=svc.url))
    assert conv.convert(o) == "docling:" + str(o)
    res = conv.convert(h)
    assert res.document.tables and res.status == "success"
