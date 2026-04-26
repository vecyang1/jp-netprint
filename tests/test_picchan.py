"""Unit tests for the pic-chan launcher."""
from __future__ import annotations

from pathlib import Path

import pytest

from netprint_cli.client import NetprintError
from netprint_cli.picchan import (
    SIZES,
    PicChanLaunch,
    build_launch,
    list_sizes,
)


def _make_jpg(tmp_path: Path) -> Path:
    p = tmp_path / "face.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIFfake")
    return p


def test_list_sizes_includes_common_aliases():
    sizes = list_sizes()
    for alias in ("myca", "passport", "license", "resume", "toeic",
                  "visa_us", "visa_uk", "visa_cn"):
        assert alias in sizes


def test_build_launch_default_myca(tmp_path):
    jpg = _make_jpg(tmp_path)
    launch = build_launch(jpg)
    assert isinstance(launch, PicChanLaunch)
    assert launch.size_alias == "myca"
    assert launch.size_token == SIZES["myca"][0]
    assert launch.launch_url.startswith("https://pic-chan.net/c/navi/")
    assert "use1=35_45_myca" in launch.launch_url
    assert launch.photo_path == jpg


def test_build_launch_passport(tmp_path):
    jpg = _make_jpg(tmp_path)
    launch = build_launch(jpg, size="passport")
    assert launch.size_alias == "passport"
    assert "passport" in launch.size_token
    assert "use1=" in launch.launch_url


def test_build_launch_invalid_size(tmp_path):
    jpg = _make_jpg(tmp_path)
    with pytest.raises(NetprintError, match="invalid size"):
        build_launch(jpg, size="bogus")


def test_build_launch_unsupported_ext(tmp_path):
    bad = tmp_path / "doc.pdf"
    bad.write_bytes(b"%PDF-1.4\n%fake\n%%EOF\n")
    with pytest.raises(NetprintError, match="unsupported extension"):
        build_launch(bad)


def test_build_launch_missing_file(tmp_path):
    with pytest.raises(NetprintError, match="not found"):
        build_launch(tmp_path / "nope.jpg")


def test_build_launch_empty_file(tmp_path):
    p = tmp_path / "empty.jpg"
    p.write_bytes(b"")
    with pytest.raises(NetprintError, match="empty"):
        build_launch(p)


def test_as_dict_has_price(tmp_path):
    jpg = _make_jpg(tmp_path)
    launch = build_launch(jpg, size="resume")
    d = launch.as_dict()
    assert d["price_yen"] == 200
    assert d["size_alias"] == "resume"
    assert d["launch_url"].startswith("https://pic-chan.net/c/navi/")
