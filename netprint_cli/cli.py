"""Command-line entry point: `netprint upload file.pdf ...`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import (
    COLOR_MODES,
    MARGIN_MODES,
    PAPER_SIZES,
    NetprintClient,
    NetprintError,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="netprint",
        description="Upload a file to かんたん netprint (Japan 7-Eleven multicopy printers).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upload", help="Upload a file and print the reservation number.")
    up.add_argument("file", type=Path, help="PDF/Office/image file to upload.")
    up.add_argument(
        "--paper", choices=list(PAPER_SIZES), default="A4",
        help="Paper size (default: A4).",
    )
    up.add_argument(
        "--color", choices=list(COLOR_MODES), default="bw",
        help="Color mode (default: bw).",
    )
    up.add_argument(
        "--margin", choices=list(MARGIN_MODES), default="noshrink",
        help="Margin handling (default: noshrink).",
    )
    up.add_argument(
        "--secret", default="",
        help="Optional 4-digit PIN required at the kiosk.",
    )
    up.add_argument(
        "--email", default="",
        help="Optional email — netprint sends a reminder + result link.",
    )
    up.add_argument(
        "--qr", type=Path, default=None,
        help="Save a QR-code PNG of the reservation number to this path.",
    )
    up.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Emit machine-readable JSON instead of a friendly summary.",
    )
    up.add_argument(
        "--max-wait", type=float, default=120.0,
        help="Seconds to wait for processing (default: 120).",
    )
    up.add_argument(
        "--interval", type=float, default=2.0,
        help="Polling interval in seconds (default: 2).",
    )
    return p


def _save_qr(text: str, dest: Path) -> None:
    import qrcode

    img = qrcode.make(text)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)


def _print_summary(result, qr_path: Path | None) -> None:
    print(f"Reservation # : {result.print_id}")
    print(f"File           : {result.file_name}")
    print(f"Pages          : {result.page_count}")
    print(f"Size (KB)      : {result.file_size_kb}")
    print(f"Expires        : {result.end_date}")
    print(f"Detail URL     : {result.detail_url}")
    if qr_path is not None:
        print(f"QR saved to    : {qr_path}")
    print()
    print("At a 7-Eleven multicopy printer:")
    print(f"  → choose ネットプリント and type {result.print_id}")
    if qr_path is not None:
        print(f"  → or hold the QR ({qr_path}) over the reader.")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "upload":
        client = NetprintClient()
        try:
            result = client.upload_and_wait(
                args.file,
                paper=args.paper,
                color=args.color,
                margin=args.margin,
                secret_number=args.secret,
                mail_address=args.email,
                interval=args.interval,
                max_wait=args.max_wait,
            )
        except NetprintError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

        qr_path = args.qr
        if qr_path is not None:
            _save_qr(result.print_id, qr_path)

        if args.as_json:
            payload = {
                "reservation_number": result.print_id,
                "file_name": result.file_name,
                "page_count": result.page_count,
                "file_size_kb": result.file_size_kb,
                "expires": result.end_date,
                "detail_url": result.detail_url,
                "qr_png": str(qr_path) if qr_path else None,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_summary(result, qr_path)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
