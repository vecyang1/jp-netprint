# Changelog

All notable changes to `jp-konbini-print` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-04-27

### Added
- Sharp Network Print integration (`--service network`) covering ~32,000 stores across Lawson, FamilyMart, MiniStop, Poplar, Seicomart, and Daily Yamazaki.
- `pic-chan` ID-photo wizard automation launcher (`--service picchan`).
- Unified service router supporting parallel multi-chain upload (`--service all`) generating independent reservation numbers simultaneously.
- Automatic QR code generation and CLI ASCII rendering for fast multicopy scanner scanning.

## [1.0.0] - 2026-04-27

### Added
- Initial release of Python CLI and library for Japan 7-Eleven かんたん netprint (`lite.printing.ne.jp`).
- Zero-account upload: file dispatch yielding 8-digit reservation number and expiration dates.
- PDF and image validation, page dimension constraints, and color mode flags.
