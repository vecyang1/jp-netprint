"""Mocked unit tests for NetworkPrintClient — no real network calls."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from netprint_cli.client import NetprintError
from netprint_cli.networkprint import (
    FIT_MODES,
    PAPER_SIZES,
    NetworkPrintClient,
)


def _make_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4\n%fake\n%%EOF\n")
    return p


def _make_jpg(tmp_path: Path) -> Path:
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIFfake")
    return p


class _FakeResp:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body
        self.text = body if isinstance(body, str) else str(body)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


def test_invalid_paper(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetworkPrintClient()

    def fake_post(url, data=None, files=None, timeout=None):
        return _FakeResp(200, {"authToken": "T", "userCode": "TESTUSER01"})

    with patch.object(c.session, "post", side_effect=fake_post):
        with pytest.raises(NetprintError, match="invalid paper"):
            c.upload(pdf, paper="A0")


def test_invalid_fit(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetworkPrintClient()

    def fake_post(url, data=None, files=None, timeout=None):
        return _FakeResp(200, {"authToken": "T", "userCode": "TESTUSER01"})

    with patch.object(c.session, "post", side_effect=fake_post):
        with pytest.raises(NetprintError, match="invalid fit"):
            c.upload(pdf, fit="stretch")


def test_unsupported_extension(tmp_path):
    bad = tmp_path / "x.xls"
    bad.write_bytes(b"junk")
    c = NetworkPrintClient()
    with patch.object(c.session, "post",
                      return_value=_FakeResp(200,
                          {"authToken": "T", "userCode": "U"})):
        with pytest.raises(NetprintError, match="unsupported extension"):
            c.upload(bad)


def test_empty_file(tmp_path):
    bad = tmp_path / "empty.pdf"
    bad.write_bytes(b"")
    c = NetworkPrintClient()
    with patch.object(c.session, "post",
                      return_value=_FakeResp(200,
                          {"authToken": "T", "userCode": "U"})):
        with pytest.raises(NetprintError, match="empty"):
            c.upload(bad)


def test_missing_file(tmp_path):
    c = NetworkPrintClient()
    with patch.object(c.session, "post",
                      return_value=_FakeResp(200,
                          {"authToken": "T", "userCode": "U"})):
        with pytest.raises(NetprintError, match="not found"):
            c.upload(tmp_path / "nope.pdf")


def test_login_http_error():
    c = NetworkPrintClient()
    with patch.object(c.session, "post",
                      return_value=_FakeResp(500, "boom")):
        with pytest.raises(NetprintError, match="login HTTP 500"):
            c.login()


def test_upload_and_wait_success(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetworkPrintClient()
    posted: dict = {}
    files_call_count = {"n": 0}

    def fake_post(url, data=None, files=None, timeout=None):
        posted.setdefault("urls", []).append(url)
        if "/login" in url:
            return _FakeResp(200, {
                "authToken": "test-00000000-0000-0000-0000-000000000000",
                "userCode": "TESTUSER01",
            })
        if "/upload" in url:
            posted["upload_data"] = dict(data)
            posted["upload_filename"] = files["file"][0] if files else None
            return _FakeResp(200, {"result": ""})
        if "/files" in url:
            files_call_count["n"] += 1
            if files_call_count["n"] < 2:
                return _FakeResp(200, {"result": "", "files": [
                    {"id": 1, "name": "doc.pdf", "size": 4096, "status": 0,
                     "pages": 0, "deleteAt": "2026-05-05 01:50:15"}
                ]})
            return _FakeResp(200, {"result": "", "files": [
                {"id": 1, "name": "doc.pdf", "size": 4096, "status": 1,
                 "pages": 3, "deleteAt": "2026-05-05 01:50:15",
                 "previews": 3, "previewUrls": []}
            ]})
        raise AssertionError(f"unexpected url {url}")

    with patch.object(c.session, "post", side_effect=fake_post):
        result = c.upload_and_wait(pdf, interval=0.0, max_wait=5.0)

    assert result.print_id == "TESTUSER01"
    assert result.page_count == 3
    assert result.file_size_kb == 4.0
    assert posted["upload_data"]["paperSize"] == "A4"
    assert posted["upload_data"]["fitToPage"] == FIT_MODES["fit"]
    assert posted["upload_data"]["authToken"] == "test-00000000-0000-0000-0000-000000000000"
    assert posted["upload_filename"] == "doc.pdf"
    assert files_call_count["n"] >= 2


def test_upload_error_result_field(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetworkPrintClient()

    def fake_post(url, data=None, files=None, timeout=None):
        if "/login" in url:
            return _FakeResp(200, {"authToken": "T", "userCode": "U"})
        if "/upload" in url:
            return _FakeResp(200, {"result": "ERROR_INVALID_FILE"})
        raise AssertionError(url)

    with patch.object(c.session, "post", side_effect=fake_post):
        with pytest.raises(NetprintError, match="upload error"):
            c.upload_and_wait(pdf, max_wait=1.0)


def test_poll_timeout(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetworkPrintClient()

    def fake_post(url, data=None, files=None, timeout=None):
        if "/login" in url:
            return _FakeResp(200, {"authToken": "T", "userCode": "U"})
        if "/upload" in url:
            return _FakeResp(200, {"result": ""})
        if "/files" in url:
            return _FakeResp(200, {"result": "", "files": [
                {"id": 1, "name": "doc.pdf", "size": 1, "status": 0,
                 "pages": 0, "deleteAt": "2026-05-05 01:00:00"}
            ]})
        raise AssertionError(url)

    with patch.object(c.session, "post", side_effect=fake_post):
        with pytest.raises(NetprintError, match="timed out"):
            c.upload_and_wait(pdf, interval=0.0, max_wait=0.05)


def test_paper_sizes_constant():
    assert "A4" in PAPER_SIZES
    assert "A3" in PAPER_SIZES
    assert "Postcard" in PAPER_SIZES


def test_jpg_supported(tmp_path):
    jpg = _make_jpg(tmp_path)
    c = NetworkPrintClient()
    c.auth_token = "T"
    c._validate_file(jpg)  # should not raise
