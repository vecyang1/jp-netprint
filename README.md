# jp-netprint

Tiny Python CLI / library for **かんたん netprint** (`lite.printing.ne.jp`) —
the no-account-needed upload service for **7-Eleven** multicopy printers in Japan.

Upload a file → get a **reservation number** (e.g. `L3QP5ZYC`) → walk to any
7-Eleven and either type the number or scan the QR.

## Install

```bash
uv pip install -e .
# or
pip install -e .
```

## CLI

```bash
netprint upload mydoc.pdf                              # bw, A4, no shrink
netprint upload poster.pdf --paper A3 --color color
netprint upload report.pdf --secret 1234 --email me@example.com
netprint upload mydoc.pdf --qr ./reservation.png       # also save a QR PNG
netprint upload mydoc.pdf --json                       # machine-readable
```

Output:

```
Reservation # : T34H8UNJ
File           : real.pdf
Pages          : 1
Size (MB)      : 2.0
Expires        : 2026/04/28 23:59
Detail URL     : https://www.printing.ne.jp/usr/web/...
```

The reservation number is valid for ~24 hours.

## Library

```python
from netprint_cli import NetprintClient

c = NetprintClient()
result = c.upload_and_wait("doc.pdf", paper="A4", color="bw")
print(result.print_id, result.end_date)
```

## Options

| Flag       | Values                                | Default   |
|------------|---------------------------------------|-----------|
| `--paper`  | `A4 A3 B4 B5 photo postcard`          | `A4`      |
| `--color`  | `bw color ask`                        | `bw`      |
| `--margin` | `noshrink shrink`                     | `noshrink`|
| `--secret` | 4-digit PIN required at the kiosk     | (none)    |
| `--email`  | Email for the result link             | (none)    |
| `--qr`     | Save reservation QR PNG to this path  | (none)    |
| `--json`   | Emit JSON instead of human summary    | off       |

## Supported file types

`.pdf .xdw .xps .oxps .doc .docx .rtf .xls .xlsx .ppt .pptx .jpg .jpeg .jpe .png .tif .tiff`

## How it works

The site is a Next.js SPA that talks to two endpoints:

1. `POST /api/register-file` (multipart) → `{id, fileName}`
2. `GET  /api/registration-status/{id}` (poll) → `{resultCode, printID, ...}`

Both require an `x-nps-lite-id` header — any UUID works; the server treats it as
a session key. No authentication, no captcha.

## Tests

```bash
pytest
```

All tests are mocked — they don't hit the live API.
