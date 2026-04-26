"""Launcher for pic-chan.net/c/ — Value Commitment's konbini ID-photo service.

pic-chan is a six-step PHP wizard (size → upload → crop/position → confirm →
email → reservation #) that bakes a single phone photo into a 4-up ID-photo
sheet you print on any 7-Eleven / Lawson / FamilyMart / MiniStop / Poplar /
Seicomart / Daily Yamazaki machine for ¥200.

The crop step requires a human dragging the face into the frame, so this
module does not try to drive all six steps. Instead it:

  1. Validates the input file is a JPEG/PNG.
  2. Resolves the size token from a small catalogue of common ID-photo specs.
  3. Returns a `PicChanLaunch` with a deep-link URL the caller can open in the
     user's browser to land directly on step 2 with the size pre-selected.

Reverse-engineered via chrome-devtools 2026-04-27. Form action observed:

  POST https://pic-chan.net/c/navi/index.php?p=step3#navi
  hidden: visa, size, use, use1, op
  file:   img_path

The site keeps state in a PHP session cookie (`picchan=...`) — without it,
posting straight to step3 throws away the size selection. Hence "launcher".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .client import NetprintError

BASE_URL = "https://pic-chan.net/c"
NAVI_URL = f"{BASE_URL}/navi/"
STEP2_URL = f"{BASE_URL}/navi/index.php?p=step2#navi"

ALLOWED_EXTS = {".jpg", ".jpeg", ".png"}

# Size tokens map to the `use1` form value pic-chan stores in PHP session.
# Keys are short human-friendly aliases; values are (token, label).
SIZES: dict[str, tuple[str, str]] = {
    "resume":   ("40_30_resume",   "Résumé / CV / residence card (40×30 mm)"),
    "license":  ("30_25_license",  "Driver's license (30×25 mm)"),
    "myca":     ("35_45_myca",     "My Number card (45×35 mm)"),
    "passport": ("45_35_passport", "Passport / generic 45×35 mm"),
    "toeic":    ("40_30_toeic",    "TOEIC (40×30 mm)"),
    "visa_us":  ("51_51_us",       "USA visa (51×51 mm)"),
    "visa_uk":  ("45_35_uk",       "UK visa (45×35 mm)"),
    "visa_cn":  ("48_33_cn",       "China visa (48×33 mm)"),
}

PRINT_PRICE_YEN = 200


@dataclass(frozen=True)
class PicChanLaunch:
    """A pre-filled launch URL for pic-chan.net's wizard."""
    photo_path: Path
    size_alias: str
    size_token: str
    size_label: str
    launch_url: str
    note: str

    def as_dict(self) -> dict:
        return {
            "photo_path": str(self.photo_path),
            "size_alias": self.size_alias,
            "size_token": self.size_token,
            "size_label": self.size_label,
            "launch_url": self.launch_url,
            "note": self.note,
            "price_yen": PRINT_PRICE_YEN,
        }


def list_sizes() -> list[str]:
    return sorted(SIZES.keys())


def build_launch(
    photo_path: str | Path,
    size: str = "myca",
) -> PicChanLaunch:
    """Validate a photo and return a deep-link to pic-chan with size preset.

    The caller is expected to:
      1. Open `launch_url` in the user's browser
      2. Upload `photo_path` (the user does this in the file picker)
      3. Crop, confirm, register email, receive print number

    Why not automate the upload? The crop step requires a human positioning
    the face inside the frame. Driving it programmatically without seeing the
    face would produce mis-cropped output 100% of the time.
    """
    path = Path(photo_path)
    if not path.is_file():
        raise NetprintError(f"file not found: {path}")
    if path.stat().st_size == 0:
        raise NetprintError(f"file is empty: {path}")
    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise NetprintError(
            f"unsupported extension {ext!r} for pic-chan — "
            f"allowed: {sorted(ALLOWED_EXTS)}"
        )
    if size not in SIZES:
        raise NetprintError(
            f"invalid size alias {size!r} — choose from {list_sizes()}"
        )

    size_token, size_label = SIZES[size]
    launch_url = f"{STEP2_URL}&use1={size_token}"
    note = (
        f"Open {launch_url}, upload {path.name}, crop, register email — "
        f"pic-chan will email you a print number good at any 7-Eleven / "
        f"Lawson / FamilyMart / MiniStop / Poplar / Seicomart / Daily "
        f"Yamazaki kiosk. ¥{PRINT_PRICE_YEN} prints 4 photos."
    )
    return PicChanLaunch(
        photo_path=path,
        size_alias=size,
        size_token=size_token,
        size_label=size_label,
        launch_url=launch_url,
        note=note,
    )


def open_in_browser(launch: PicChanLaunch) -> bool:
    """Best-effort: open the launch URL in the user's default browser."""
    import webbrowser
    return webbrowser.open(launch.launch_url)
