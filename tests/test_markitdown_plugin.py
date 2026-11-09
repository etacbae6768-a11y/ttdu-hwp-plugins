import io

import pytest

markitdown = pytest.importorskip("markitdown")
from markitdown import FileConversionException, MarkItDown, StreamInfo  # noqa: E402

from markitdown_ttdu_hwp import HwpConverter  # noqa: E402

HWPX_HEAD = b"PK\x03\x04" + b"\x00" * 26 + b"mimetypeapplication/hwp+zip" + b"\x00" * 100


def md_for(svc):
    return MarkItDown(enable_plugins=True, ttdu_hwp_backend="hub", ttdu_hub_url=svc.url)


def test_plugin_is_registered():
    from importlib.metadata import entry_points

    names = [e.name for e in entry_points(group="markitdown.plugin")]
    assert "ttdu_hwp" in names


def test_convert_hwp_by_extension(svc, tmp_path):
    svc.reply = (200, {"ok": True, "markdown": "제1조\n"}, {})
    p = tmp_path / "공고.hwp"
    p.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 50)
    assert md_for(svc).convert(str(p)).markdown == "제1조\n"
    assert svc.calls[0]["path"] == "/v1/hwp/markdown"


def test_convert_hwpx_stream_without_name_is_sniffed(svc):
    svc.reply = (200, {"ok": True, "markdown": "ok\n"}, {})
    out = md_for(svc).convert_stream(io.BytesIO(HWPX_HEAD))
    assert out.markdown == "ok\n"


def test_other_files_untouched(svc, tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    assert md_for(svc).convert(str(p)).markdown.strip() == "hello"
    assert svc.calls == []


def test_accepts_does_not_move_stream():
    c = HwpConverter(backend="hub")
    s = io.BytesIO(HWPX_HEAD)
    s.seek(3)
    c.accepts(s, StreamInfo())
    assert s.tell() == 3


def test_error_reported_and_file_sent_once(svc, tmp_path):
    svc.reply = (422, {"code": "unsupported", "details": {"reason": "encrypted"}}, {})
    p = tmp_path / "secret.hwp"
    p.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 50)
    with pytest.raises(FileConversionException, match="password"):
        md_for(svc).convert(str(p))
    assert len(svc.calls) == 1  # MarkItDown retried with a second guess; the plugin did not resend
