# jp-konbini-print

One Python CLI / library for **all three** Japanese konbini ("convenience-store")
print services. Upload a file → get a reservation number → walk into any
**7-Eleven, Lawson, FamilyMart, MiniStop, Poplar, Seicomart, or Daily Yamazaki**
and print it from the multicopy machine. No accounts, no apps, no QR scanner
required (a QR is offered as a bonus).

## What's covered

| Backend | Site | Stores covered | API style |
|---|---|---|---|
| **seven** | `lite.printing.ne.jp` (かんたん netprint) | 7-Eleven only (~21k stores) | JSON, `x-nps-lite-id` UUID header |
| **network** | `networkprint.ne.jp/Lite` (Sharp Network Print) | Lawson + FamilyMart + MiniStop + Poplar + Seicomart + Daily Yamazaki (~32k stores) | JSON, AWS-ALB cookie + `authToken` |
| **picchan** | `pic-chan.net/c/` (Value Commitment ID-photo) | All 7 chains (¥200 for 4 ID photos) | PHP wizard — launcher mode (browser finish) |

Every chain in Japan that has a Sharp/Konica-Minolta multicopy printer is
reachable with a single command.

## Install

```bash
uv pip install -e .
# or
pip install -e .
```

## CLI cheat-sheet

```bash
# Default — back-compat 7-Eleven path
netprint upload mydoc.pdf

# Lawson / FamilyMart / MiniStop / Poplar / Seicomart / Daily Yamazaki
netprint upload mydoc.pdf --service network

# Cross-post to BOTH document services in parallel
# (so you have two independent reservation numbers; you can walk into
# whichever konbini is closer)
netprint upload mydoc.pdf --service all

# Smart routing: PDFs go to seven+network; ID-photo intent → pic-chan
netprint upload mydoc.pdf --service auto                       # docs → both
netprint upload selfie.jpg --service auto --intent id_photo    # → pic-chan

# pic-chan ID-photo helper (¥200 / 4 photos, every chain)
netprint upload selfie.jpg --service picchan --picchan-size myca
netprint upload selfie.jpg --service picchan --picchan-open    # opens browser

# Machine-readable output
netprint upload mydoc.pdf --service all --json
```

Real run, same PDF cross-posted in parallel:

```text
$ netprint upload poster.pdf --service all
router → seven + network  (mode=all → every compatible backend for .pdf)

=== seven ===
  Reservation # : BBNN2XUQ
  Pages         : 3
  Expires       : 2026/04/28 23:59
  Detail URL    : https://www.printing.ne.jp/usr/web/NPCP0050.seam?...
  → at any 7-Eleven, choose ネットプリント and type BBNN2XUQ

=== network ===
  User Number   : B57LD4K9WH
  Pages         : 3
  Expires       : 2026-05-05 02:02:20
  → at any Lawson / FamilyMart / MiniStop / Poplar / Seicomart / Daily Yamazaki,
    choose ネットワークプリント and type B57LD4K9WH
```

You now have two cross-checkable reservation numbers covering all 7 chains.

## Routing matrix

`--service auto` maps file + intent → backends:

| File / intent | Default routing |
|---|---|
| `.pdf .docx .xlsx .pptx .rtf .xdw .xps .oxps` | seven + network (cross-post) |
| `.tif .tiff` | seven only (network doesn't accept TIFF) |
| `.jpg .png` (default `intent=any`) | seven + network |
| `.jpg .png` (`--intent id_photo`) | pic-chan |
| `--service all` + `.jpg/.png` | seven + network + picchan |

## Library

```python
from netprint_cli import (
    NetprintClient,         # 7-Eleven
    NetworkPrintClient,     # Lawson / FamilyMart / MiniStop / ...
    picchan_build_launch,   # ID-photo composer
    route,                  # smart router
)

# 7-Eleven
seven = NetprintClient()
r1 = seven.upload_and_wait("doc.pdf", paper="A4", color="bw")
print(r1.print_id, r1.detail_url)

# Lawson family
network = NetworkPrintClient()
r2 = network.upload_and_wait("doc.pdf", paper="A4", fit="fit")
print(r2.print_id)            # 10-char user number, e.g. "B57LD4K9WH"

# pic-chan launcher
launch = picchan_build_launch("selfie.jpg", size="myca")
print(launch.launch_url)      # opens directly into pic-chan step 2

# Router
decision = route("doc.pdf", intent="document")
print(decision.services)      # ('seven', 'network')
```

## Why three backends?

- **7-Eleven** has the widest accepted file types (PDF/Office/JPG/PNG/TIFF/XDW/XPS).
- **networkprint** covers every other major chain in Japan with a single upload.
- **pic-chan** specialises in ID-photo composition (résumé, driver's license,
  passport, visa, My Number card, TOEIC, etc.) and prints at all 7 chains for ¥200.

For ordinary documents, cross-posting to **seven + network** is the killer move:
one command, two receipts, every konbini in Japan as a fallback.

## Options

| Flag | Backend | Values | Default |
|---|---|---|---|
| `--service` | all | `seven network picchan auto all` | `seven` |
| `--intent` | router | `any document id_photo` | `any` |
| `--paper` | seven | `A4 A3 B4 B5 photo postcard` | `A4` |
| `--color` | seven | `bw color ask` | `bw` |
| `--margin` | seven | `noshrink shrink` | `noshrink` |
| `--secret` | seven | 4-digit kiosk PIN | (none) |
| `--email` | seven | result-email address | (none) |
| `--network-paper` | network | `A4 A3 B4 B5 Postcard` | `A4` |
| `--fit` | network | `fit actual` | `fit` |
| `--password` | network | password for encrypted PDF | (none) |
| `--picchan-size` | picchan | `myca passport license resume toeic visa_us visa_uk visa_cn` | `myca` |
| `--picchan-open` | picchan | open launch URL in browser | off |
| `--qr` | all | save QR PNG of reservation # | (none) |
| `--json` | all | machine-readable JSON | off |

## Supported file types

| Backend | Accepted extensions |
|---|---|
| seven | `.pdf .xdw .xps .oxps .doc .docx .rtf .xls .xlsx .ppt .pptx .jpg .jpe .jpeg .png .tif .tiff` |
| network | `.pdf .doc .docx .jpg .jpeg .png` |
| picchan | `.jpg .jpeg .png` (ID-photo only) |

## How it works

### seven (lite.printing.ne.jp)
Two JSON endpoints. Session id = any UUID in the `x-nps-lite-id` header.

```text
POST /api/register-file    multipart       → {id, fileName}
GET  /api/registration-status/{id}         → {resultCode, printID, ...}
```
`resultCode 0` = success, `1` = pending, `≥1000` = error.

### network (networkprint.ne.jp/Lite)
Three endpoints. Session = AWS-ALB sticky cookie + an `authToken` returned by login.

```text
POST /LiteServer/app/login     userAgent=… → {authToken, userCode}
POST /LiteServer/app/upload    multipart   → {result: ""}
POST /LiteServer/app/files     authToken=… → {files: [{status, pages, deleteAt, …}]}
```
`status 0` = processing, `1` = "Print OK". `userCode` is the 10-char kiosk number.

### picchan (pic-chan.net/c/)
6-step PHP wizard with image-cropping UI. The crop step requires a human to
position the face — automating it would mis-crop 100% of the time. We provide
a launcher: pre-fill the size, deep-link to step 2, hand off to the browser.

## Tests

```bash
pytest                    # 41 tests, fully mocked, no live network
```

## License

MIT.
