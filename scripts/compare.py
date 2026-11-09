"""Convert sample HWP/HWPX files through both backends and both plugins and check they agree.

usage: python scripts/compare.py OUT.json FILE [FILE ...] [--docx N] [--errors FILE ...]

Needs: markitdown, markitdown-ttdu-hwp, docling-ttdu-hwp installed; a running local runner
(TTDU_LOCAL_KEY_FILE or TTDU_LOCAL_KEY set); TTDU_API_KEY for the keyed hub calls.
Hub calls: per file 1 keyed (MarkItDown) + 1 without key (Docling, IP quota); plus N keyed DOCX
calls and 1 call without key per error file. With --keyed every hub call uses TTDU_API_KEY.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import time
import zipfile
from pathlib import Path

from docling_ttdu_hwp import convert_hwp
from markitdown import MarkItDown
from ttdu_hwp import HwpClient, HwpError, LimitExceededError, to_markdown


class Recording(HwpClient):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.last = None

    def extract(self, source, name=None):
        self.last = super().extract(source, name)
        return self.last


def doc_xml(docx: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        return z.read("word/document.xml")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--docx", type=int, default=3)
    ap.add_argument("--errors", nargs="*", default=[])
    ap.add_argument("--text-only", action="store_true", help="one hub call per file (no key): /v1/hwp/text via the Docling plugin; Markdown is compared through the shared formatting rules")
    ap.add_argument("--keyed", action="store_true", help="send TTDU_API_KEY on every hub call, including the Docling and error calls (when the IP quota is used up)")
    a = ap.parse_args()
    key = os.environ.pop("TTDU_API_KEY", None)  # removed from the environment so the no-key client really has none
    md_local = MarkItDown(enable_plugins=True, ttdu_hwp_backend="local")
    md_hub = MarkItDown(enable_plugins=True, ttdu_hwp_backend="hub", ttdu_api_key=key)
    local = HwpClient("local")
    hub_nokey = Recording("hub", api_key=(key if a.keyed else ""))
    hub_key = HwpClient("hub", api_key=key)
    rows = []
    for i, f in enumerate(a.files):
        p = Path(f)
        row = {"file": p.parent.name + "/" + p.name, "bytes": p.stat().st_size}
        try:
            t0 = time.time()
            L = local.extract(p)
            row["local_ms"] = int((time.time() - t0) * 1000)
            row["stats"] = L.stats
            lmd = md_local.convert(str(p)).markdown
            row["markdown_chars"] = len(lmd)
            if not a.text_only:
                t0 = time.time()
                hmd = md_hub.convert(str(p)).markdown
                row["hub_markdown_ms"] = int((time.time() - t0) * 1000)
                row["markitdown_hub_equals_local"] = hmd == lmd
            d_local = convert_hwp(p, client=local)
            d_hub = convert_hwp(p, client=hub_nokey)
            H = hub_nokey.last
            # MarkItDown itself normalizes every converter's output (rstrip each line, collapse 3+ newlines),
            # so compare the hub-derived Markdown with the local client's Markdown before that step.
            row["hub_blocks_markdown_equals_local_markdown"] = to_markdown({"blocks": H.blocks}) == local.markdown(p).markdown
            row["hub_text_equals_local"] = H.text == L.text
            row["hub_blocks_equal_local"] = json.dumps(H.blocks, ensure_ascii=False) == json.dumps(L.blocks, ensure_ascii=False)
            row["docling_markdown_equal"] = d_hub.export_to_markdown() == d_local.export_to_markdown()
            row["docling_tables"] = len(d_hub.tables)
            hub_tables = [b for b in (H.blocks or []) if b.get("type") == "table" and b.get("rows")]
            row["docling_tables_match_hub_blocks"] = len(d_hub.tables) == len(hub_tables) and all(
                (t.data.num_rows, t.data.num_cols) == (len(b["rows"]), max(len(r) for r in b["rows"]))
                for t, b in zip(d_hub.tables, hub_tables)
            )
            if i < a.docx and not a.text_only:
                dl = local.docx(p).docx
                dh = hub_key.docx(p).docx
                row["docx_document_xml_equal"] = doc_xml(dl) == doc_xml(dh)
                row["docx_bytes_equal"] = dl == dh
            row["ok"] = all(v for k, v in row.items() if k.endswith(("_equal", "_equals_local", "_equal_local", "_match_hub_blocks", "_xml_equal", "_equals_local_markdown")))
        except Exception as e:  # HwpError, or MarkItDown's FileConversionException wrapping one
            row["error"] = "%s: %s" % (type(e).__name__, str(e)[:400])
            row["ok"] = False
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    errs = []
    for f in a.errors:
        p = Path(f)
        r = {"file": p.parent.name + "/" + p.name}
        for name, c in (("local", local), ("hub", hub_nokey)):
            try:
                c.extract(p)
                r[name] = "no error"
            except HwpError as e:
                r[name] = "%s(%s, %s)" % (type(e).__name__, e.code, e.status)
        r["same"] = r["local"].split("(")[0] == r["hub"].split("(")[0] and r["local"] != "no error"
        errs.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    big = b"\xd0\xcf\x11\xe0" + b"\x00" * (15 * 1024 * 1024 + 1)
    try:
        hub_nokey.extract(big, name="big.hwp")
        errs.append({"file": "15MB+1 (generated)", "hub": "no error", "same": False})
    except LimitExceededError as e:
        errs.append({"file": "15MB+1 (generated)", "hub": "LimitExceededError(before sending, status=%s)" % e.status, "same": e.status is None})
    summary = {
        "files": len(rows),
        "ok": sum(1 for r in rows if r.get("ok")),
        "markitdown_hub_compared": sum(1 for r in rows if "markitdown_hub_equals_local" in r),
        "markitdown_hub_equals_local": sum(1 for r in rows if r.get("markitdown_hub_equals_local")),
        "hub_blocks_markdown_equals_local_markdown": sum(1 for r in rows if r.get("hub_blocks_markdown_equals_local_markdown")),
        "hub_text_equals_local": sum(1 for r in rows if r.get("hub_text_equals_local")),
        "hub_blocks_equal_local": sum(1 for r in rows if r.get("hub_blocks_equal_local")),
        "docling_markdown_equal": sum(1 for r in rows if r.get("docling_markdown_equal")),
        "docling_tables_match_hub_blocks": sum(1 for r in rows if r.get("docling_tables_match_hub_blocks")),
        "docx_compared": sum(1 for r in rows if "docx_document_xml_equal" in r),
        "docx_document_xml_equal": sum(1 for r in rows if r.get("docx_document_xml_equal")),
        "error_cases_same": sum(1 for r in errs if r.get("same")),
        "error_cases": len(errs),
    }
    Path(a.out).write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "summary": summary, "rows": rows, "errors": errs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
