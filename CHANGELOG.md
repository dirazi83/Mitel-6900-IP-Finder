# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-09-10

### Changed
- Application icon replaced with the project's desk-phone artwork. The build
  script now keys the flattened checkerboard out of the source PNG, trims and
  squares the artwork, and packs it into the multi-resolution `.ico`.

## [1.0.1] - 2026-09-10

### Added
- Application icon: a multi-resolution `.ico` (16-256 px) embedded in the
  executable and used as the window icon, generated reproducibly by
  `tools/make_icon.py`.

### Changed
- Application name and version are registered with Qt at start-up.

## [1.0.0] - 2026-09-10

First public release.

### Added
- Standalone Windows executable (`MitelPhoneFinder.exe`) — no Python, no Nmap,
  no Npcap and no administrator rights required on the machine that runs it.
- PySide6 desktop GUI: auto-detected local subnets (default-route interface
  first), editable MAC-prefix filter, live result rows, cancel, click-to-copy,
  double-click to open a phone's web interface, and CSV export.
- Command-line mode in the same binary, with `--mac`, `--mac-only`, `--no-web`,
  `--no-sip`, `--timeout`, `--threads`, `--csv` and `--version`.
- Discovery engine (`scanner.py`) using only the Python standard library:
  - threaded TCP connect sweep on ports 80/443 that also fills the ARP cache;
  - ARP cache read-back mapping IP to MAC, filtered by prefix and known Mitel OUIs;
  - HTTP/HTTPS fingerprinting via `Server` and the `WWW-Authenticate` realm,
    which reports the exact 6900-series model;
  - SIP `OPTIONS` probe on UDP 5060 returning model and firmware.
- Per-host evidence column, so MAC-prefix candidates are never presented as
  confirmed phones.
- GitHub Actions workflow that builds the executable and publishes it, with a
  SHA-256 checksum, on every `v*` tag.

### Notes
- Replaces an earlier Nmap-based prototype; the Nmap and Npcap dependencies are
  gone entirely.
- `14` is not an IEEE-registered Mitel OUI; it is supported as a user-supplied
  filter. The registered Mitel OUIs are `08:00:0F` and `00:08:5D`.

[1.0.2]: https://github.com/dirazi83/Mitel-6900-SIP-IP-Finder/releases/tag/v1.0.2
[1.0.1]: https://github.com/dirazi83/Mitel-6900-SIP-IP-Finder/releases/tag/v1.0.1
[1.0.0]: https://github.com/dirazi83/Mitel-6900-SIP-IP-Finder/releases/tag/v1.0.0
