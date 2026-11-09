import base64
import json
import warnings

import pytest

import ttdu_hwp.client as client_mod
from ttdu_hwp import (
    AuthenticationError,
    ConfigurationError,
    EncryptedDocumentError,
    HwpClient,
    HwpError,
    InvalidDocumentError,
    LimitExceededError,
    QuotaExceededError,
    ServiceUnavailableError,
    sniff_hwp,
    to_markdown,
)

HWPX_HEAD = b"PK\x03\x04" + b"\x00" * 26 + b"mimetypeapplication/hwp+zip"
BLOCKS = [{"type": "paragraph", "text": "제1조 목적"}, {"type": "table", "rows": [["a", "b"], ["c", ""]], "cells": []}]


def hub(svc, **kw):
    return HwpClient("hub", hub_url=svc.url, **kw)


def local(svc, **kw):
    return HwpClient("local", local_url=svc.url, local_key="k" * 40, **kw)


def test_hub_markdown_sends_file_and_key(svc):
    svc.reply = (200, {"ok": True, "format": "hwpx", "markdown": "# x\n"}, {})
    r = hub(svc, api_key="ttdu_test").markdown(HWPX_HEAD, name="공고.hwpx")
    assert r.markdown == "# x\n" and r.backend == "hub"
    call = svc.calls[0]
    assert call["path"] == "/v1/hwp/markdown"
    assert call["headers"]["x-api-key"] == "ttdu_test"
    assert 'name="file"; filename="공고.hwpx"'.encode() in call["body"]


def test_hub_without_key_sends_no_key_header(svc):
    svc.reply = (200, {"ok": True, "text": "t", "blocks": []}, {})
    hub(svc).extract(b"x" * 10, name="a.hwp")
    assert "x-api-key" not in svc.calls[0]["headers"]


def test_local_markdown_uses_tool_route_and_formats_locally(svc):
    svc.reply = (200, {"ok": True, "data": {"format": "hwp", "text": "제1조 목적", "blocks": BLOCKS, "stats": {}}, "outputs": []}, {})
    r = local(svc).markdown(b"x" * 10, name="a.hwp")
    assert svc.calls[0]["path"] == "/v1/tools/hwp.extract_text/run"
    assert svc.calls[0]["headers"]["x-api-key"] == "k" * 40
    assert r.markdown == to_markdown({"blocks": BLOCKS})


def test_local_docx_two_calls(svc):
    def reply(path):
        if path.endswith("hwp.extract_text/run"):
            return 200, {"ok": True, "data": {"format": "hwp", "blocks": BLOCKS}}, {}
        return 200, {"ok": True, "outputs": [{"name": "a.docx", "base64": base64.b64encode(b"PKdocx").decode()}]}, {}

    svc.reply = reply
    r = local(svc).docx(b"x" * 10, name="a.hwp")
    assert r.docx == b"PKdocx" and r.docx_name == "a.docx"
    assert svc.calls[1]["path"] == "/v1/tools/doc.write_docx/run"
    assert b'"file_name": "a"' in svc.calls[1]["body"]


@pytest.mark.parametrize(
    "status,body,exc",
    [
        (422, {"code": "unsupported", "details": {"reason": "encrypted"}}, EncryptedDocumentError),
        (422, {"code": "invalid_input"}, InvalidDocumentError),
        (413, {"code": "resource_limit"}, LimitExceededError),
        (413, {"title": "Payload Too Large"}, LimitExceededError),
        (429, {"title": "Too Many Requests"}, QuotaExceededError),
        (402, {"code": "insufficient_credits"}, QuotaExceededError),
        (401, {"title": "Unauthorized"}, AuthenticationError),
        (503, {"title": "Service Unavailable"}, ServiceUnavailableError),
        (400, {"title": "Bad Request"}, HwpError),
    ],
)
def test_error_mapping(svc, status, body, exc):
    svc.reply = (status, body, {"Retry-After": "30"})
    with pytest.raises(exc) as ei:
        hub(svc).extract(b"x" * 10, name="a.hwp")
    assert ei.value.status == status
    if exc is QuotaExceededError:
        assert ei.value.retry_after == 30.0


def test_non_json_error_body(svc):
    svc.reply = (502, b"<html>bad gateway</html>", {})
    with pytest.raises(ServiceUnavailableError):
        hub(svc).extract(b"x" * 10, name="a.hwp")


def test_size_checked_before_sending(svc, monkeypatch):
    monkeypatch.setattr(client_mod, "HUB_MAX_BYTES", 100)
    with pytest.raises(LimitExceededError) as ei:
        hub(svc).extract(b"x" * 101, name="a.hwp")
    assert ei.value.status is None and svc.calls == []


def test_empty_file_rejected_without_call(svc):
    with pytest.raises(InvalidDocumentError):
        hub(svc).extract(b"", name="a.hwp")
    assert svc.calls == []


def test_unreachable_local_runner():
    c = HwpClient("local", local_url="http://127.0.0.1:9", local_key="k" * 40, timeout=3)
    with pytest.raises(ServiceUnavailableError, match="ttdu serve"):
        c.extract(b"x" * 10, name="a.hwp")


def test_local_url_must_be_this_computer():
    with pytest.raises(ConfigurationError):
        HwpClient("local", local_url="http://192.168.0.10:8790", local_key="k")
    with pytest.raises(ConfigurationError):
        HwpClient("local", local_url="https://example.com", local_key="k")


def test_hub_url_must_be_https():
    with pytest.raises(ConfigurationError):
        HwpClient("hub", hub_url="http://example.com")


def test_unknown_backend():
    with pytest.raises(ConfigurationError):
        HwpClient("cloud")


def test_local_key_required(svc):
    c = HwpClient("local", local_url=svc.url)
    with pytest.raises(ConfigurationError, match="TTDU_LOCAL_KEY"):
        c.extract(b"x" * 10, name="a.hwp")


def test_local_key_file(svc, tmp_path):
    f = tmp_path / "local-api-key.txt"
    f.write_text("ttdu_local_" + "a" * 48 + "\n")
    svc.reply = (200, {"ok": True, "data": {"blocks": []}}, {})
    HwpClient("local", local_url=svc.url, local_key_file=str(f)).extract(b"x" * 10, name="a.hwp")
    assert svc.calls[0]["headers"]["x-api-key"] == "ttdu_local_" + "a" * 48


def test_env_settings(svc, monkeypatch):
    monkeypatch.setenv("TTDU_HWP_BACKEND", "local")
    monkeypatch.setenv("TTDU_LOCAL_URL", svc.url)
    monkeypatch.setenv("TTDU_LOCAL_KEY", "e" * 40)
    c = HwpClient()
    assert c.backend == "local" and c.local_key == "e" * 40


def test_implicit_hub_warns_once(svc, monkeypatch):
    monkeypatch.setattr(client_mod, "_warned_hub", False)
    svc.reply = (200, {"ok": True, "markdown": ""}, {})
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        c = HwpClient(hub_url=svc.url)
        c.markdown(b"x" * 10, name="a.hwp")
        c.markdown(b"x" * 10, name="a.hwp")
    msgs = [str(x.message) for x in w if "sending the document" in str(x.message)]
    assert len(msgs) == 1


def test_explicit_hub_does_not_warn(svc, monkeypatch):
    monkeypatch.setattr(client_mod, "_warned_hub", False)
    svc.reply = (200, {"ok": True, "markdown": ""}, {})
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        hub(svc).markdown(b"x" * 10, name="a.hwp")
    assert not [x for x in w if "sending the document" in str(x.message)]


def test_sniff():
    assert sniff_hwp(HWPX_HEAD) == "hwpx"
    assert sniff_hwp(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100 + b"HWP Document File") == "hwp"
    assert sniff_hwp(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100) is None  # e.g. .doc
    assert sniff_hwp(b"PK\x03\x04" + b"\x00" * 60) is None  # plain zip / docx


def test_markdown_formatting_rules():
    md = to_markdown({"blocks": [
        {"type": "paragraph", "text": "  a|b *c*  "},
        {"type": "table", "rows": [["h1", "h2\nx"], ["v"]], "nested_in": {"row": 1, "col": 0}},
    ]})
    assert md == "a\\|b \\*c\\*\n\n> Table inside a table cell (row 2, column 1):\n\n| h1 | h2 x |\n| --- | --- |\n| v |  |\n"
