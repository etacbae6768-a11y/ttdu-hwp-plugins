"""Command line: ttdu-hwp FILE [--to markdown|text|json|docx] [-o OUT] [--backend hub|local]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import HwpClient, HwpError, __version__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ttdu-hwp", description="Convert HWP/HWPX with the hub API or the local runner.")
    ap.add_argument("file")
    ap.add_argument("--to", choices=["markdown", "text", "json", "docx"], default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--backend", choices=["hub", "local"])
    ap.add_argument("--version", action="version", version="ttdu-hwp " + __version__)
    a = ap.parse_args(argv)
    c = HwpClient(a.backend)
    try:
        if a.to == "docx":
            r = c.docx(a.file)
            out = Path(a.output or (Path(a.file).with_suffix(".docx").name))
            out.write_bytes(r.docx or b"")
            print(str(out), file=sys.stderr)
            return 0
        if a.to == "markdown":
            s = c.markdown(a.file).markdown or ""
        else:
            r = c.extract(a.file)
            s = (r.text or "") if a.to == "text" else json.dumps(
                {"format": r.format, "stats": r.stats, "engine": r.engine, "text": r.text, "blocks": r.blocks}, ensure_ascii=False, indent=1
            )
    except HwpError as e:
        print("error [%s]: %s" % (e.code, e), file=sys.stderr)
        return 2
    if a.output:
        Path(a.output).write_text(s, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
