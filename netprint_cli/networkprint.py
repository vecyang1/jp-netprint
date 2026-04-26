"""Reverse-engineered client for networkprint.ne.jp/Lite (Sharp Network Print —
Lawson, FamilyMart, MiniStop, Poplar Group convenience-store printers in Japan).

Endpoints discovered via chrome-devtools instrumentation 2026-04-27:

  POST /LiteServer/app/login    body: userAgent=...
                                resp: {authToken, userCode}
  POST /LiteServer/app/upload   multipart: authToken, file, registerName,
                                paperSize, fitToPage, nupSetting, nupBorder,
                                nupOrder, pamphletSetting, password
                                resp: {result: ""}  (empty string = success)
  POST /LiteServer/app/files    body: authToken=...
                                resp: {result, files: [{id, name, size, status,
                                                        pages, previews,
                                                        previewUrls, deleteAt,
                                                        ...}]}

Session is cookie-based (AWS ALB sticky) — `requests.Session` persists them.
status: 0 = processing, 1 = "Print OK". `userCode` (10 alphanumeric) is what
the user types at the Sharp multi-copy kiosk.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests

from .client import NetprintError, RegistrationResult

BASE_URL = "https://networkprint.ne.jp"
LOGIN_URL = f"{BASE_URL}/LiteServer/app/login"
UPLOAD_URL = f"{BASE_URL}/LiteServer/app/upload"
FILES_URL = f"{BASE_URL}/LiteServer/app/files"
PREVIEW_URL = f"{BASE_URL}/Lite/preview"

# networkprint.ne.jp accepts a narrower set than 7-Eleven: JPEG/PNG/PDF/Word.
ALLOWED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}

PAPER_SIZES = ("B5", "A4", "B4", "A3", "Postcard")

FIT_MODES = {
    "fit": "1",
    "actual": "0",
}

STATUS_PROCESSING = 0
STATUS_READY = 1

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)


class NetworkPrintClient:
    """Client for networkprint.ne.jp/Lite (Lawson / FamilyMart / MiniStop / Poplar).

    Auth is bound to the requests.Session (AWS ALB cookies) plus an authToken
    returned by /login. Both must be carried through every subsequent call.
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 60.0,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/Lite/document",
        })
        self.auth_token: Optional[str] = None
        self.user_code: Optional[str] = None

    def _validate_file(self, path: Path) -> None:
        if not path.is_file():
            raise NetprintError(f"file not found: {path}")
        if path.stat().st_size == 0:
            raise NetprintError(f"file is empty: {path}")
        ext = path.suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise NetprintError(
                f"unsupported extension {ext!r} for networkprint — "
                f"allowed: {sorted(ALLOWED_EXTS)}"
            )

    def login(self) -> str:
        resp = self.session.post(
            LOGIN_URL,
            data={"userAgent": self.user_agent},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise NetprintError(
                f"login HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            payload = resp.json()
        except ValueError as e:
            raise NetprintError(f"login non-JSON: {resp.text[:300]}") from e
        if "authToken" not in payload or "userCode" not in payload:
            raise NetprintError(f"login missing fields: {payload}")
        self.auth_token = payload["authToken"]
        self.user_code = payload["userCode"]
        return self.user_code

    def upload(
        self,
        file_path: str | Path,
        *,
        paper: str = "A4",
        fit: str = "fit",
        password: str = "",
    ) -> None:
        if self.auth_token is None:
            self.login()
        path = Path(file_path)
        self._validate_file(path)
        if paper not in PAPER_SIZES:
            raise NetprintError(
                f"invalid paper {paper!r} — choose from {list(PAPER_SIZES)}"
            )
        if fit not in FIT_MODES:
            raise NetprintError(
                f"invalid fit {fit!r} — choose from {list(FIT_MODES)}"
            )

        # The site truncates the registered name to ~30 chars; mirror that.
        register_name = path.name[:30]

        with path.open("rb") as fh:
            files = {"file": (path.name, fh, "application/octet-stream")}
            data = {
                "authToken": self.auth_token,
                "registerName": register_name,
                "paperSize": paper,
                "fitToPage": FIT_MODES[fit],
                "nupSetting": "0",
                "nupBorder": "false",
                "nupOrder": "0",
                "pamphletSetting": "0",
                "password": password,
            }
            resp = self.session.post(
                UPLOAD_URL, data=data, files=files, timeout=self.timeout
            )
        if resp.status_code != 200:
            raise NetprintError(
                f"upload HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            payload = resp.json()
        except ValueError as e:
            raise NetprintError(f"upload non-JSON: {resp.text[:300]}") from e
        if payload.get("result"):
            raise NetprintError(f"upload error: {payload}")

    def list_files(self) -> list[dict]:
        if self.auth_token is None:
            raise NetprintError("not logged in — call login() first")
        resp = self.session.post(
            FILES_URL,
            data={"authToken": self.auth_token},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise NetprintError(
                f"files HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            payload = resp.json()
        except ValueError as e:
            raise NetprintError(f"files non-JSON: {resp.text[:300]}") from e
        return payload.get("files", [])

    def poll(
        self,
        file_name_hint: Optional[str] = None,
        *,
        interval: float = 2.0,
        max_wait: float = 120.0,
    ) -> RegistrationResult:
        deadline = time.monotonic() + max_wait
        last_files: list[dict] = []
        while True:
            last_files = self.list_files()
            target = self._pick_target(last_files, file_name_hint)
            if target is not None and target.get("status") == STATUS_READY:
                return self._to_result(target)
            if time.monotonic() >= deadline:
                raise NetprintError(
                    f"timed out after {max_wait:.0f}s — last files={last_files}"
                )
            time.sleep(interval)

    @staticmethod
    def _pick_target(
        files: list[dict], file_name_hint: Optional[str]
    ) -> Optional[dict]:
        if not files:
            return None
        if file_name_hint:
            matches = [f for f in files if f.get("name") == file_name_hint]
            if matches:
                return max(matches, key=lambda f: f.get("id", 0))
        return max(files, key=lambda f: f.get("id", 0))

    def _to_result(self, file_payload: dict) -> RegistrationResult:
        size_bytes = float(file_payload.get("size", 0))
        raw = dict(file_payload)
        raw["userCode"] = self.user_code
        raw["authToken"] = self.auth_token
        return RegistrationResult(
            print_id=self.user_code or "",
            file_name=file_payload.get("name", ""),
            page_count=int(file_payload.get("pages", 0)),
            file_size_kb=round(size_bytes / 1024.0, 1),
            end_date=file_payload.get("deleteAt", ""),
            detail_url=PREVIEW_URL,
            raw=raw,
        )

    def upload_and_wait(
        self,
        file_path: str | Path,
        *,
        paper: str = "A4",
        fit: str = "fit",
        password: str = "",
        interval: float = 2.0,
        max_wait: float = 120.0,
    ) -> RegistrationResult:
        if self.auth_token is None:
            self.login()
        path = Path(file_path)
        self.upload(path, paper=paper, fit=fit, password=password)
        return self.poll(
            file_name_hint=path.name,
            interval=interval,
            max_wait=max_wait,
        )
