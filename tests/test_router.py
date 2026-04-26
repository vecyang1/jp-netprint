"""Unit tests for the service router."""
from __future__ import annotations

from pathlib import Path

import pytest

from netprint_cli.router import RouteDecision, route


def _touch(tmp_path: Path, name: str, content: bytes = b"x") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_pdf_auto_picks_seven_and_network(tmp_path):
    pdf = _touch(tmp_path, "a.pdf")
    decision = route(pdf)
    assert decision.services == ("seven", "network")
    assert "cross-post" in decision.reason


def test_jpg_auto_cross_posts(tmp_path):
    jpg = _touch(tmp_path, "a.jpg")
    decision = route(jpg)
    assert "seven" in decision.services
    assert "network" in decision.services


def test_id_photo_intent_picks_picchan(tmp_path):
    jpg = _touch(tmp_path, "a.jpg")
    decision = route(jpg, intent="id_photo")
    assert decision.services == ("picchan",)


def test_id_photo_intent_rejects_pdf(tmp_path):
    pdf = _touch(tmp_path, "a.pdf")
    with pytest.raises(ValueError, match="id_photo"):
        route(pdf, intent="id_photo")


def test_document_intent_pdf(tmp_path):
    pdf = _touch(tmp_path, "a.pdf")
    decision = route(pdf, intent="document")
    assert "seven" in decision.services
    assert "network" in decision.services


def test_mode_all_pdf(tmp_path):
    pdf = _touch(tmp_path, "a.pdf")
    decision = route(pdf, mode="all")
    assert "seven" in decision.services
    assert "network" in decision.services
    assert "picchan" not in decision.services


def test_mode_all_jpg_includes_picchan(tmp_path):
    jpg = _touch(tmp_path, "a.jpg")
    decision = route(jpg, mode="all")
    assert "seven" in decision.services
    assert "network" in decision.services
    assert "picchan" in decision.services


def test_seven_only_extension(tmp_path):
    tif = _touch(tmp_path, "a.tif")
    decision = route(tif)
    assert decision.services == ("seven",)


def test_doc_extension_routes_as_document(tmp_path):
    rtf = _touch(tmp_path, "report.rtf")
    decision = route(rtf)
    assert "seven" in decision.services


def test_unknown_extension_raises(tmp_path):
    junk = _touch(tmp_path, "a.exe")
    with pytest.raises(ValueError, match="no backend accepts"):
        route(junk)


def test_route_decision_as_dict(tmp_path):
    pdf = _touch(tmp_path, "a.pdf")
    decision = route(pdf)
    d = decision.as_dict()
    assert isinstance(d["services"], list)
    assert isinstance(d["reason"], str)
