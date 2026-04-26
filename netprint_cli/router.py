"""Service router — picks which konbini-print backend(s) to use for a file.

Three backends:
  - seven    → lite.printing.ne.jp  (7-Eleven only; widest file-type support)
  - network  → networkprint.ne.jp/Lite (Lawson/FamilyMart/MiniStop/Poplar/
               Seicomart/Daily Yamazaki — ~32k stores)
  - picchan  → pic-chan.net/c/ (ID-photo composer; works at all 7 chains
               for ¥200 / 4 photos)

Routing rules (`mode="auto"` default):

  intent == "id_photo"        → picchan
  intent == "document"        → seven + network (cross-check)
  intent == "any" + doc ext   → seven + network
  intent == "any" + image ext → seven + network if both accept; else whichever
                                does

`mode="all"` returns every backend that can accept the file, useful when the
user wants two or three reservation numbers as redundancy.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import client as _seven
from . import networkprint as _network
from . import picchan as _picchan

DOC_EXTS = {".pdf", ".doc", ".docx", ".rtf", ".xls", ".xlsx", ".ppt", ".pptx",
            ".xdw", ".xps", ".oxps"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jpe"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class RouteDecision:
    services: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict:
        return {"services": list(self.services), "reason": self.reason}


def route(
    file_path: str | Path,
    *,
    intent: str = "any",
    mode: str = "auto",
) -> RouteDecision:
    """Decide which backend(s) to use.

    intent: "any" (default), "id_photo", "document"
    mode:   "auto" (smart routing) or "all" (every compatible backend)
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    seven_ok = ext in _seven.ALLOWED_EXTS
    network_ok = ext in _network.ALLOWED_EXTS
    picchan_ok = ext in _picchan.ALLOWED_EXTS

    if mode == "all":
        chosen: list[str] = []
        if seven_ok:
            chosen.append("seven")
        if network_ok:
            chosen.append("network")
        if picchan_ok and intent in ("any", "id_photo"):
            chosen.append("picchan")
        if not chosen:
            raise ValueError(
                f"no backend accepts extension {ext!r}. "
                f"seven supports {sorted(_seven.ALLOWED_EXTS)}; "
                f"network supports {sorted(_network.ALLOWED_EXTS)}; "
                f"picchan supports {sorted(_picchan.ALLOWED_EXTS)}."
            )
        return RouteDecision(
            services=tuple(chosen),
            reason=f"mode=all → every compatible backend for {ext}",
        )

    if intent == "id_photo":
        if not picchan_ok:
            raise ValueError(
                f"id_photo intent requires JPG/PNG — got {ext!r}"
            )
        return RouteDecision(
            services=("picchan",),
            reason="intent=id_photo → pic-chan (¥200 / 4 photos, all 7 chains)",
        )

    if intent == "document" or ext in DOC_EXTS:
        chosen2: list[str] = []
        if seven_ok:
            chosen2.append("seven")
        if network_ok:
            chosen2.append("network")
        if not chosen2:
            raise ValueError(f"no document backend accepts {ext!r}")
        return RouteDecision(
            services=tuple(chosen2),
            reason=(
                f"document → cross-post to {' + '.join(chosen2)} "
                f"so the user has two cross-checkable reservation numbers"
            ),
        )

    if seven_ok and network_ok:
        return RouteDecision(
            services=("seven", "network"),
            reason=f"image {ext} → cross-post (covers all 7 chains)",
        )
    if seven_ok:
        return RouteDecision(
            services=("seven",),
            reason=f"image {ext} → 7-Eleven (only chain that accepts {ext})",
        )
    if network_ok:
        return RouteDecision(
            services=("network",),
            reason=f"image {ext} → networkprint (Lawson/FM/MiniStop/Poplar)",
        )
    if picchan_ok:
        return RouteDecision(
            services=("picchan",),
            reason=f"only pic-chan accepts {ext}",
        )

    raise ValueError(f"no backend accepts extension {ext!r}")
