"""Reverse-engineered client for lite.printing.ne.jp (かんたん netprint)."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

BASE_URL = "https://lite.printing.ne.jp"
REGISTER_URL = f"{BASE_URL}/api/register-file"
STATUS_URL = f"{BASE_URL}/api/registration-status"

ALLOWED_EXTS = {
    ".xdw", ".pdf", ".xps", ".oxps",
    ".doc", ".docx", ".rtf",
    ".xls", ".xlsx",
    ".ppt", ".pptx",
    ".jpg", ".jpe", ".jpeg", ".png",
    ".tif", ".tiff",
}

PAPER_SIZES = {
    "A4": "0",
    "A3": "1",
    "B4": "2",
    "B5": "3",
    "photo": "4",
    "postcard": "5",
}

COLOR_MODES = {
    "ask": "0",
    "color": "1",
    "bw": "2",
}

MARGIN_MODES = {
    "noshrink": "0",
    "shrink": "1",
}

# resultCode meanings observed:
# 0  = success — printID + detailURL + endDate present
# 1  = still processing
# >=1000 = error (e.g. 1601 = invalid file)
RESULT_PENDING = 1
RESULT_OK = 0


class NetprintError(RuntimeError):
    """Raised when the netprint API returns an error or unexpected payload."""


@dataclass(frozen=True)
class RegistrationResult:
    print_id: str          # 8-char reservation number, e.g. "L3QP5ZYC"
    file_name: str
    page_count: int
    file_size_kb: float    # netprint reports size in KB, rounded up
    end_date: str          # "YYYY/MM/DD HH:MM"
    detail_url: str
    raw: dict


class NetprintClient:
    """Stateful client. The site identifies a session via x-nps-lite-id (any UUID)."""

    def __init__(self, lite_id: Optional[str] = None, timeout: float = 30.0):
        self.lite_id = lite_id or str(uuid.uuid4())
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"x-nps-lite-id": self.lite_id})

    def _validate_file(self, path: Path) -> None:
        if not path.is_file():
            raise NetprintError(f"file not found: {path}")
        if path.stat().st_size == 0:
            raise NetprintError(f"file is empty: {path}")
        ext = path.suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise NetprintError(
                f"unsupported extension {ext!r} — allowed: {sorted(ALLOWED_EXTS)}"
            )

    def upload(
        self,
        file_path: str | Path,
        *,
        paper: str = "A4",
        color: str = "bw",
        margin: str = "noshrink",
        secret_number: str = "",
        mail_address: str = "",
    ) -> str:
        """Upload a file and return the registration id (opaque, used for polling)."""
        path = Path(file_path)
        self._validate_file(path)

        if paper not in PAPER_SIZES:
            raise NetprintError(f"invalid paper {paper!r} — choose from {list(PAPER_SIZES)}")
        if color not in COLOR_MODES:
            raise NetprintError(f"invalid color {color!r} — choose from {list(COLOR_MODES)}")
        if margin not in MARGIN_MODES:
            raise NetprintError(f"invalid margin {margin!r} — choose from {list(MARGIN_MODES)}")
        if secret_number and (not secret_number.isdigit() or len(secret_number) != 4):
            raise NetprintError("secret_number must be exactly 4 digits")
        if mail_address and "@" not in mail_address:
            raise NetprintError("mail_address must look like an email")

        with path.open("rb") as fh:
            files = {"fileBody": (path.name, fh)}
            data = {
                "paperSize": PAPER_SIZES[paper],
                "colorMode": COLOR_MODES[color],
                "margin": MARGIN_MODES[margin],
                "mailAddress": mail_address,
                "secretNumber": secret_number,
            }
            resp = self.session.post(
                REGISTER_URL, data=data, files=files, timeout=self.timeout
            )

        if resp.status_code != 200:
            raise NetprintError(
                f"register-file returned HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            payload = resp.json()
        except ValueError as e:
            raise NetprintError(f"register-file returned non-JSON: {resp.text[:300]}") from e
        if "id" not in payload:
            raise NetprintError(f"register-file missing id: {payload}")
        return payload["id"]

    def poll(
        self,
        registration_id: str,
        *,
        interval: float = 2.0,
        max_wait: float = 120.0,
    ) -> RegistrationResult:
        """Poll registration-status until the job is no longer pending."""
        deadline = time.monotonic() + max_wait
        last_payload: dict = {}
        while True:
            url = f"{STATUS_URL}/{registration_id}"
            resp = self.session.get(
                url, params={"_": str(int(time.time() * 1000))}, timeout=self.timeout
            )
            if resp.status_code != 200:
                raise NetprintError(
                    f"registration-status HTTP {resp.status_code}: {resp.text[:300]}"
                )
            try:
                last_payload = resp.json()
            except ValueError as e:
                raise NetprintError(
                    f"registration-status non-JSON: {resp.text[:300]}"
                ) from e
            code = last_payload.get("resultCode")
            if code != RESULT_PENDING:
                break
            if time.monotonic() >= deadline:
                raise NetprintError(
                    f"timed out after {max_wait:.0f}s waiting for registration; "
                    f"last payload={last_payload}"
                )
            time.sleep(interval)

        if last_payload.get("resultCode") != RESULT_OK:
            raise NetprintError(
                f"netprint returned error resultCode={last_payload.get('resultCode')}; "
                f"detail={last_payload}"
            )

        return RegistrationResult(
            print_id=last_payload["printID"],
            file_name=last_payload.get("fileName", ""),
            page_count=int(last_payload.get("page", 0)),
            file_size_kb=float(last_payload.get("fileSize", 0)),
            end_date=last_payload.get("endDate", ""),
            detail_url=last_payload.get("detailURL", ""),
            raw=last_payload,
        )

    def upload_and_wait(
        self,
        file_path: str | Path,
        *,
        paper: str = "A4",
        color: str = "bw",
        margin: str = "noshrink",
        secret_number: str = "",
        mail_address: str = "",
        interval: float = 2.0,
        max_wait: float = 120.0,
    ) -> RegistrationResult:
        rid = self.upload(
            file_path,
            paper=paper,
            color=color,
            margin=margin,
            secret_number=secret_number,
            mail_address=mail_address,
        )
        result = self.poll(rid, interval=interval, max_wait=max_wait)
        result.raw["registrationId"] = rid
        return result
