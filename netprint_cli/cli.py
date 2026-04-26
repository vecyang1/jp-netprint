"""Command-line entry point: `netprint upload file.pdf [--service ...]`.

Three konbini-print backends, one CLI:
  --service seven    →  7-Eleven (lite.printing.ne.jp)
  --service network  →  Lawson / FamilyMart / MiniStop / Poplar / Seicomart
                        / Daily Yamazaki (networkprint.ne.jp/Lite)
  --service picchan  →  pic-chan.net ID-photo composer (¥200, 4 photos)
  --service auto     →  router picks the best backend(s) for the file
  --service all      →  cross-post to every compatible backend
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .client import (
    COLOR_MODES,
    MARGIN_MODES,
    PAPER_SIZES as SEVEN_PAPER_SIZES,
    NetprintClient,
    NetprintError,
    RegistrationResult,
)
from .networkprint import (
    PAPER_SIZES as NETWORK_PAPER_SIZES,
    FIT_MODES as NETWORK_FIT_MODES,
    NetworkPrintClient,
)
from .picchan import (
    PicChanLaunch,
    build_launch as picchan_build_launch,
    list_sizes as picchan_list_sizes,
    open_in_browser as picchan_open,
)
from .router import route as router_route

SERVICE_CHOICES = ["seven", "network", "picchan", "auto", "all"]
INTENT_CHOICES = ["any", "document", "id_photo"]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="netprint",
        description=(
            "Upload a file to a Japanese konbini print service "
            "(7-Eleven netprint, Sharp Network Print, or pic-chan ID photos). "
            "Returns a reservation number you type at the multicopy kiosk."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upload", help="Upload a file and get a reservation number.")
    up.add_argument("file", type=Path, help="PDF/Office/image file to upload.")
    up.add_argument(
        "--service",
        choices=SERVICE_CHOICES,
        default="seven",
        help=(
            "Which backend(s) to use. seven=7-Eleven, network=Lawson family, "
            "picchan=ID photos, auto=router picks, all=cross-post everywhere "
            "(default: seven for back-compat)."
        ),
    )
    up.add_argument(
        "--intent",
        choices=INTENT_CHOICES,
        default="any",
        help="Hint for --service auto: any | document | id_photo",
    )

    # 7-Eleven options.
    up.add_argument("--paper", choices=list(SEVEN_PAPER_SIZES), default="A4")
    up.add_argument("--color", choices=list(COLOR_MODES), default="bw")
    up.add_argument("--margin", choices=list(MARGIN_MODES), default="noshrink")
    up.add_argument("--secret", default="",
                    help="Optional 4-digit PIN required at the kiosk (7-Eleven only).")
    up.add_argument("--email", default="",
                    help="Optional email for receipt (7-Eleven only).")

    # networkprint options.
    up.add_argument("--network-paper", choices=list(NETWORK_PAPER_SIZES),
                    default="A4")
    up.add_argument("--fit", choices=list(NETWORK_FIT_MODES), default="fit",
                    help="networkprint: fit-to-page or actual size.")
    up.add_argument("--password", default="",
                    help="Password for encrypted PDFs (networkprint only).")

    # picchan options.
    up.add_argument("--picchan-size", choices=picchan_list_sizes(),
                    default="myca",
                    help="ID-photo size alias for pic-chan (default: myca).")
    up.add_argument("--picchan-open", action="store_true",
                    help="Open the pic-chan launch URL in your browser.")

    # output options.
    up.add_argument("--qr", type=Path, default=None,
                    help="Save a QR-code PNG of the reservation number(s).")
    up.add_argument("--json", dest="as_json", action="store_true",
                    help="Emit machine-readable JSON.")
    up.add_argument("--max-wait", type=float, default=120.0)
    up.add_argument("--interval", type=float, default=2.0)
    return p


def _save_qr(text: str, dest: Path) -> None:
    import qrcode
    img = qrcode.make(text)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)


def _print_seven(result: RegistrationResult) -> None:
    print(f"  Reservation # : {result.print_id}")
    print(f"  File          : {result.file_name}")
    print(f"  Pages         : {result.page_count}")
    print(f"  Size (KB)     : {result.file_size_kb}")
    print(f"  Expires       : {result.end_date}")
    print(f"  Detail URL    : {result.detail_url}")


def _print_network(result: RegistrationResult) -> None:
    print(f"  User Number   : {result.print_id}")
    print(f"  File          : {result.file_name}")
    print(f"  Pages         : {result.page_count}")
    print(f"  Size (KB)     : {result.file_size_kb}")
    print(f"  Expires       : {result.end_date}")
    print(f"  Manage page   : {result.detail_url}  (cookie-bound to this session)")


def _print_picchan(launch: PicChanLaunch) -> None:
    print(f"  Size          : {launch.size_label}")
    print(f"  Launch URL    : {launch.launch_url}")
    print(f"  {launch.note}")


def _run_seven(args) -> RegistrationResult:
    client = NetprintClient()
    return client.upload_and_wait(
        args.file,
        paper=args.paper,
        color=args.color,
        margin=args.margin,
        secret_number=args.secret,
        mail_address=args.email,
        interval=args.interval,
        max_wait=args.max_wait,
    )


def _run_network(args) -> RegistrationResult:
    client = NetworkPrintClient()
    return client.upload_and_wait(
        args.file,
        paper=args.network_paper,
        fit=args.fit,
        password=args.password,
        interval=args.interval,
        max_wait=args.max_wait,
    )


def _run_picchan(args) -> PicChanLaunch:
    launch = picchan_build_launch(args.file, size=args.picchan_size)
    if args.picchan_open:
        picchan_open(launch)
    return launch


SERVICE_HANDLERS = {
    "seven": _run_seven,
    "network": _run_network,
    "picchan": _run_picchan,
}

KIOSK_TIPS = {
    "seven": "  → at any 7-Eleven, choose ネットプリント and type {pid}",
    "network":
        "  → at any Lawson / FamilyMart / MiniStop / Poplar / Seicomart / "
        "Daily Yamazaki, choose ネットワークプリント and type {pid}",
    "picchan":
        "  → finish the wizard in your browser to receive a print number "
        "(any of the 7 chains, ¥200 / 4 photos)",
}


def _resolve_services(args) -> list[str]:
    if args.service in ("seven", "network", "picchan"):
        return [args.service]
    decision = router_route(
        args.file, intent=args.intent,
        mode="all" if args.service == "all" else "auto",
    )
    print(f"router → {' + '.join(decision.services)}  ({decision.reason})",
          file=sys.stderr)
    return list(decision.services)


def _execute(services: list[str], args) -> dict[str, Any]:
    """Run each requested service; return mapping of service → result-or-error."""
    out: dict[str, Any] = {}
    if len(services) == 1:
        svc = services[0]
        try:
            out[svc] = SERVICE_HANDLERS[svc](args)
        except NetprintError as e:
            out[svc] = {"error": str(e)}
        return out

    # Two or three services in parallel — saves the user time when cross-posting.
    with ThreadPoolExecutor(max_workers=len(services)) as pool:
        futures = {pool.submit(SERVICE_HANDLERS[svc], args): svc
                   for svc in services}
        for fut in as_completed(futures):
            svc = futures[fut]
            try:
                out[svc] = fut.result()
            except NetprintError as e:
                out[svc] = {"error": str(e)}
            except Exception as e:  # pragma: no cover
                out[svc] = {"error": f"{type(e).__name__}: {e}"}
    return out


def _to_json_payload(results: dict[str, Any], qr_path: Path | None) -> dict:
    payload: dict[str, Any] = {"results": {}}
    for svc, res in results.items():
        if isinstance(res, dict) and "error" in res:
            payload["results"][svc] = {"ok": False, **res}
            continue
        if svc == "picchan":
            payload["results"][svc] = {"ok": True, **res.as_dict()}
        else:
            payload["results"][svc] = {
                "ok": True,
                "reservation_number": res.print_id,
                "file_name": res.file_name,
                "page_count": res.page_count,
                "file_size_kb": res.file_size_kb,
                "expires": res.end_date,
                "detail_url": res.detail_url,
            }
    if qr_path:
        payload["qr_png"] = str(qr_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "upload":
        return 2

    services = _resolve_services(args)
    results = _execute(services, args)

    qr_path: Path | None = None
    if args.qr:
        # QR encodes the first non-error reservation #, or the picchan URL.
        qr_text: str | None = None
        for svc in ("seven", "network", "picchan"):
            if svc not in results:
                continue
            res = results[svc]
            if isinstance(res, dict) and "error" in res:
                continue
            qr_text = res.launch_url if svc == "picchan" else res.print_id
            break
        if qr_text:
            _save_qr(qr_text, args.qr)
            qr_path = args.qr

    if args.as_json:
        print(json.dumps(_to_json_payload(results, qr_path),
                         ensure_ascii=False, indent=2))
    else:
        any_ok = False
        for svc in services:
            res = results.get(svc)
            print(f"\n=== {svc} ===")
            if isinstance(res, dict) and "error" in res:
                print(f"  ERROR: {res['error']}")
                continue
            any_ok = True
            if svc == "seven":
                _print_seven(res)
            elif svc == "network":
                _print_network(res)
            elif svc == "picchan":
                _print_picchan(res)
            tip = KIOSK_TIPS[svc]
            pid = (res.print_id if hasattr(res, "print_id")
                   else res.launch_url if hasattr(res, "launch_url") else "")
            print(tip.format(pid=pid))
        if qr_path:
            print(f"\nQR saved to: {qr_path}")
        if not any_ok:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
