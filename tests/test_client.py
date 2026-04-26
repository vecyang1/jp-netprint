"""Unit tests with mocked HTTP — no real network calls."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from netprint_cli.client import (
    COLOR_MODES,
    PAPER_SIZES,
    NetprintClient,
    NetprintError,
)


def _make_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4\n%fake\n%%EOF\n")
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
    c = NetprintClient(lite_id="test")
    with pytest.raises(NetprintError, match="invalid paper"):
        c.upload(pdf, paper="A0")


def test_invalid_color(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetprintClient(lite_id="test")
    with pytest.raises(NetprintError, match="invalid color"):
        c.upload(pdf, color="rainbow")


def test_invalid_secret(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetprintClient(lite_id="test")
    with pytest.raises(NetprintError, match="4 digits"):
        c.upload(pdf, secret_number="12")


def test_invalid_email(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetprintClient(lite_id="test")
    with pytest.raises(NetprintError, match="mail_address"):
        c.upload(pdf, mail_address="not-an-email")


def test_unsupported_extension(tmp_path):
    bad = tmp_path / "f.zip"
    bad.write_bytes(b"PK")
    c = NetprintClient(lite_id="test")
    with pytest.raises(NetprintError, match="unsupported extension"):
        c.upload(bad)


def test_empty_file(tmp_path):
    bad = tmp_path / "empty.pdf"
    bad.write_bytes(b"")
    c = NetprintClient(lite_id="test")
    with pytest.raises(NetprintError, match="empty"):
        c.upload(bad)


def test_missing_file(tmp_path):
    c = NetprintClient(lite_id="test")
    with pytest.raises(NetprintError, match="not found"):
        c.upload(tmp_path / "nope.pdf")


def test_upload_and_wait_success(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetprintClient(lite_id="test")
    posted = {}

    def fake_post(url, data, files, timeout):
        posted["url"] = url
        posted["data"] = data
        return _FakeResp(200, {"id": "REGID", "fileName": "x.pdf"})

    status_calls = {"n": 0}

    def fake_get(url, params, timeout):
        status_calls["n"] += 1
        if status_calls["n"] < 2:
            return _FakeResp(200, {"resultCode": 1})
        return _FakeResp(200, {
            "resultCode": 0, "printID": "L3QP5ZYC", "page": 1,
            "fileSize": 0.1, "endDate": "2026/04/28 23:59",
            "detailURL": "https://example/x", "fileName": "x.pdf",
        })

    with patch.object(c.session, "post", side_effect=fake_post), \
         patch.object(c.session, "get", side_effect=fake_get):
        result = c.upload_and_wait(pdf, interval=0.0, max_wait=5.0)

    assert result.print_id == "L3QP5ZYC"
    assert result.page_count == 1
    assert result.end_date == "2026/04/28 23:59"
    assert posted["data"]["paperSize"] == PAPER_SIZES["A4"]
    assert posted["data"]["colorMode"] == COLOR_MODES["bw"]
    assert posted["data"]["mailAddress"] == ""
    assert status_calls["n"] >= 2


def test_upload_error_resultcode(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetprintClient(lite_id="test")

    def fake_post(url, data, files, timeout):
        return _FakeResp(200, {"id": "REGID", "fileName": "x.pdf"})

    def fake_get(url, params, timeout):
        return _FakeResp(200, {"resultCode": 1601, "detailURL": "/web/errors/X"})

    with patch.object(c.session, "post", side_effect=fake_post), \
         patch.object(c.session, "get", side_effect=fake_get):
        with pytest.raises(NetprintError, match="resultCode=1601"):
            c.upload_and_wait(pdf, interval=0.0, max_wait=5.0)


def test_register_http_error(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetprintClient(lite_id="test")

    def fake_post(url, data, files, timeout):
        return _FakeResp(500, "boom")

    with patch.object(c.session, "post", side_effect=fake_post):
        with pytest.raises(NetprintError, match="HTTP 500"):
            c.upload(pdf)


def test_poll_timeout(tmp_path):
    pdf = _make_pdf(tmp_path)
    c = NetprintClient(lite_id="test")

    def fake_post(url, data, files, timeout):
        return _FakeResp(200, {"id": "REGID"})

    def fake_get(url, params, timeout):
        return _FakeResp(200, {"resultCode": 1})

    with patch.object(c.session, "post", side_effect=fake_post), \
         patch.object(c.session, "get", side_effect=fake_get):
        with pytest.raises(NetprintError, match="timed out"):
            c.upload_and_wait(pdf, interval=0.0, max_wait=0.05)
