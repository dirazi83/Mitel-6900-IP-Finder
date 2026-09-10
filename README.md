# Mitel 6900 IP Phone Finder

[![Release](https://img.shields.io/github/v/release/dirazi83/Mitel-6900-SIP-IP-Finder?sort=semver)](https://github.com/dirazi83/Mitel-6900-SIP-IP-Finder/releases)
[![Build](https://github.com/dirazi83/Mitel-6900-SIP-IP-Finder/actions/workflows/release.yml/badge.svg)](https://github.com/dirazi83/Mitel-6900-SIP-IP-Finder/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#requirements)

Find every Mitel 6900-series IP phone on a subnet — IP address, MAC address,
model and firmware — from a single Windows executable.

No Nmap. No Npcap. No WinPcap. No Python on the target PC. No administrator
rights. Discovery uses nothing but ordinary TCP/UDP sockets and the Windows
ARP cache.

Example output (illustrative):

```
IP address        | MAC address       | Vendor              | Model | Firmware      | Ports  | Evidence
------------------+-------------------+---------------------+-------+---------------+--------+---------------------------------------
192.168.100.164   | 14:2b:d2:3a:91:0c | Mitel candidate     | 6915  | 6.4.0.140     | 80,443 | MAC prefix 14:2b; web signature (80)
192.168.100.171   | 08:00:0f:1a:44:e2 | Mitel Corporation   | 6930  | 6.4.0.140     | 80,443 | OUI: Mitel Corporation; SIP OPTIONS reply
```

---

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Usage](#usage)
- [How detection works](#how-detection-works)
- [MAC prefixes](#mac-prefixes)
- [Requirements](#requirements)
- [Build from source](#build-from-source)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Legal and safety](#legal-and-safety)
- [License](#license)

---

## Features

- **Zero install** — one portable `.exe`, nothing to deploy on the machine you run it from.
- **No packet driver, no admin rights** — plain sockets and `arp -a`, so it runs on a locked-down corporate laptop.
- **Fast** — a /24 subnet sweeps in about 3 seconds with 128 threads.
- **Real identification, not guesswork** — reads the phone's HTTP realm (`Mitel 6915`) and SIP `User-Agent` (`Mitel-6920-SIP/6.4.0.140`) to report the exact model and firmware.
- **Configurable MAC filter** — defaults to the `14` prefix, accepts any list (`14, 08:00:0f`), or leave it blank to match on web/SIP signature alone.
- **GUI and CLI in one binary** — double-click for the window, or pass a subnet on the command line for scripting.
- **CSV export** — results straight into an inventory spreadsheet.
- **Read-only** — no credentials are used, no phone configuration is touched, no calls are placed.

## Quick start

1. Download `MitelPhoneFinder.exe` from the [latest release](https://github.com/dirazi83/Mitel-6900-SIP-IP-Finder/releases/latest).
2. Run it. Windows SmartScreen may warn about an unsigned binary — choose **More info → Run anyway**, or build it yourself (see [Build from source](#build-from-source)).
3. Pick the subnet (local interfaces are detected automatically), then **Start scan**.

For MAC addresses to appear, run it from a PC on the **same VLAN as the phones** — usually the voice VLAN. Across a router, MAC discovery is impossible by design; the HTTP and SIP fingerprints still work.

## Usage

### GUI

| Control | Meaning |
|---|---|
| **Subnet, range or IP** | `192.168.100.0/24`, `10.0.2.10-60`, or a single address. Local interfaces are pre-filled, default-route interface first. |
| **MAC starts with** | Comma-separated prefixes, e.g. `14, 08:00:0f`. Blank matches any MAC. |
| **HTTP/HTTPS fingerprint** | Reads `Server` and the `WWW-Authenticate` realm on ports 80/443. |
| **SIP OPTIONS probe** | One UDP packet to 5060; returns model and firmware. |
| **MAC matches only** | Suppresses hosts that matched by web signature alone. |
| **Timeout / Threads** | Per-port connect timeout and socket concurrency. Raise the timeout on slow WAN links. |

Click any cell to copy it. Double-click a row to open that phone's web interface. **Export CSV…** saves the table.

### Command line

The same executable takes arguments:

```bat
MitelPhoneFinder.exe 192.168.100.0/24
MitelPhoneFinder.exe 10.0.2.10-60 --mac 14,08:00:0f --csv phones.csv
MitelPhoneFinder.exe 192.168.100.164 --no-sip
```

| Option | Default | Description |
|---|---|---|
| `--mac PREFIXES` | `14` | Comma-separated MAC prefixes to match. |
| `--mac-only` | off | Report only MAC matches; ignore web-only signatures. |
| `--no-web` | off | Skip HTTP/HTTPS fingerprinting. |
| `--no-sip` | off | Skip the SIP OPTIONS probe. |
| `--timeout SECONDS` | `0.6` | Per-port connect timeout. |
| `--threads N` | `128` | Concurrent sockets. |
| `--csv FILE` | — | Write results to CSV. |
| `--version` | — | Print the version and exit. |

Exit code is `0` on success, `1` on error, `130` if cancelled.

## How detection works

| Step | Method | Works through a router |
|---|---|---|
| 1. Sweep | TCP connect to ports 80 and 443 on every address. The attempt also forces the OS to ARP-resolve on-link hosts, so the ARP cache fills even for phones whose web server is closed. | Port state: yes. ARP: no. |
| 2. MAC | `arp -a` is read back and mapped IP → MAC, then filtered by prefix and by known Mitel OUIs. | No — same VLAN only. |
| 3. HTTP | `GET /` returns `Server: Aragorn` and `WWW-Authenticate: Basic realm="Mitel 6915"`. The realm names the exact model. | Yes. |
| 4. SIP | A single `OPTIONS` request to UDP 5060 returns `User-Agent: Mitel-6920-SIP/6.4.0.140` — model and firmware. | Yes. |

Every host is reported with the evidence that matched it, so a MAC-prefix guess is never presented as a confirmed phone.

## MAC prefixes

The IEEE-registered Mitel OUIs are **`08:00:0F`** (Mitel Corporation) and **`00:08:5D`** (Mitel/Aastra). The tool also recognises Aastra-era and adjacent vendor prefixes.

`14` is **not** a registered Mitel OUI. It is supported because some fleets are provisioned on hardware in that range, but it is treated as a user-supplied filter rather than proof of vendor. The HTTP realm and the SIP `User-Agent` are the authoritative identification — trust those columns first.

## Requirements

**To run the release binary:** Windows 10 or 11, x64. Nothing else.

**To run from source:** Python 3.9+ and PySide6 (GUI only — the scan engine in `scanner.py` imports nothing outside the standard library, so CLI mode works on a bare Python install).

## Build from source

```bat
git clone https://github.com/dirazi83/Mitel-6900-SIP-IP-Finder.git
cd Mitel-6900-SIP-IP-Finder
python -m venv env
env\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
env\Scripts\python.exe main.py
```

Produce the standalone executable:

```bat
env\Scripts\python.exe -m PyInstaller --noconfirm --clean MitelPhoneFinder.spec
```

The result is `dist\MitelPhoneFinder.exe`. Pushing a `v*` tag runs the same build on GitHub Actions and attaches the binary to the release.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Hosts respond but the MAC column shows `-` | You are not on the phones' VLAN. ARP does not cross a router — scan the voice VLAN subnet from a PC on that VLAN. |
| No results at all | Phones are usually on a dedicated voice VLAN. Check the subnet, then raise **Timeout** to `1.5 s` for slow links. |
| Phone found but **Model** is `-` | Its web server is disabled or SIP is on a non-default port. The MAC match still identifies it. |
| Scan is slow | Lower the timeout, raise the threads, or scan a range (`10.0.2.10-60`) instead of a full /24. |
| SmartScreen blocks the download | The binary is unsigned. Verify the SHA-256 published with the release, or build it yourself. |
| Antivirus flags the `.exe` | PyInstaller bundles are a common false positive. Build from source if your policy forbids unsigned bundles. |

## Limitations

- MAC discovery is Layer 2: same Ethernet segment/VLAN only.
- A phone with its web interface disabled *and* SIP on a non-standard port is detectable by MAC only.
- Windows only. The engine is portable Python, but interface enumeration and the ARP read use Windows commands.
- A MAC prefix match is a candidate, not proof. Confirm with the model column.
- An empty result does not prove there are no phones on the network.

## Legal and safety

This tool performs read-only network discovery: TCP connection attempts, one HTTP `GET /`, and one SIP `OPTIONS` request. It never authenticates, never changes phone configuration and never places a call.

Scan only networks you own or are authorised to administer. Unauthorised network scanning may violate your organisation's policy or local law.

## License

[MIT](LICENSE) © 2026 dirazi83
