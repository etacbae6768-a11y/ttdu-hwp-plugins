"""Markdown and DOCX-block formatting of extracted HWP content.

This only formats the structured result the service returns (paragraphs and tables in
reading order). It does not read HWP files. The rules are the same as the hosted
``/v1/hwp/markdown`` and ``/v1/hwp/docx`` endpoints, so the local-runner backend gives
the same Markdown as the hub.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping

# Characters ECMAScript String.prototype.trim() removes (WhiteSpace + LineTerminator).
_JS_WS = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_MD_SPECIAL = re.compile(r"([*_`\[\]#<>|])")
_CELL_BREAK = re.compile(r"\r?\n|\t")


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return v if isinstance(v, str) else str(v)


def _trim(s: str) -> str:
    return s.strip(_JS_WS)


def _cut(s: str, n: int) -> str:
    """First n UTF-16 code units (same as JavaScript slice)."""
    if len(s) <= n // 2:
        return s
    b = s.encode("utf-16-le", "surrogatepass")
    if len(b) <= 2 * n:
        return s
    return b[: 2 * n].decode("utf-16-le", "ignore")


def escape(s: Any) -> str:
    s = _s(s).replace("\\", "\\\\")
    return _MD_SPECIAL.sub(r"\\\1", s)


def _cell(s: Any) -> str:
    return escape(_trim(_CELL_BREAK.sub(" ", _s(s))))


def _rows(b: Mapping[str, Any]) -> List[list]:
    return [r for r in (b.get("rows") or []) if isinstance(r, list) and len(r) > 0]


def to_markdown(data: Mapping[str, Any]) -> str:
    """Markdown: paragraphs separated by blank lines, tables as GitHub tables (first row = header row)."""
    out: List[str] = []
    for b in data.get("blocks") or []:
        kind = b.get("type")
        if kind == "paragraph":
            t = _trim(_s(b.get("text") or ""))
            if t:
                out.append("  \n".join(escape(x) for x in t.split("\n")))
            continue
        if kind == "table":
            rows = _rows(b)
            if not rows:
                continue
            w = max(len(r) for r in rows)

            def line(r: list) -> str:
                return "| " + " | ".join(_cell(r[i]) if i < len(r) else "" for i in range(w)) + " |"

            t = [line(rows[0]), "| " + " | ".join("---" for _ in range(w)) + " |"] + [line(r) for r in rows[1:]]
            ni = b.get("nested_in")
            if ni:
                row = ni.get("row") if isinstance(ni, Mapping) else None
                col = ni.get("col") if isinstance(ni, Mapping) else None
                row = 0 if row is None else row
                col = 0 if col is None else col
                out.append("> Table inside a table cell (row " + _s(row + 1) + ", column " + _s(col + 1) + "):")
            out.append("\n".join(t))
    return "\n\n".join(out) + "\n"


def to_docx_blocks(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Blocks for the ``doc.write_docx`` tool: paragraphs and tables (merged cells stay empty)."""
    blocks: List[Dict[str, Any]] = []
    for b in data.get("blocks") or []:
        kind = b.get("type")
        if kind == "paragraph":
            blocks.append({"t": "p", "text": _cut(_s(b.get("text") or ""), 100000)})
            continue
        if kind == "table":
            rows = [[_cut(_s(c), 10000) for c in r[:64]] for r in _rows(b)[:5000]]
            if rows:
                blocks.append({"t": "table", "rows": rows, "header": False})
    return blocks[:20000]


def iter_tables(data: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for b in data.get("blocks") or []:
        if b.get("type") == "table":
            yield b
