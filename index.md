# pylunce

Reverse-engineered tools and documentation for the **Ailunce HD1 / HD2 DMR radio**
(firmware `HD-GPS-HD2PA-C7000-V2.1.3-GPS.bin`).

The radio's CPS (Windows-only) uses a simple USB-serial protocol that is
partially documented upstream, but with incorrect details (wrong baud rate,
wrong frame semantics for large reads, no checksum formula). These tools
reproduce the real protocol observed in USB pcaps, verified against a live
radio.

## Protocol & Format Reference

| Document | Description |
|----------|-------------|
| [Wire Protocol](docs/protocol.html) | Serial protocol: frames, checksums, read/write families, timing |
| [Address Space](docs/address-space.html) | Region map, packed `.bin` ordering, dual-bitmap, kill state |
| [Channel Format](docs/channels.html) | Channel slot bit-level layout, inline Rx List, VFOs |
| [Records](docs/records.html) | Contacts, group aliases, zones, Radio IDs |
| [Settings](docs/settings.html) | Radio-wide settings byte table |
| [Menu Tree](docs/menu-tree.html) | Complete radio menu hierarchy with firmware cross-reference |
| [CPS CSV Format](docs/cps-csv-format.html) | CPS channel import/export CSV column reference |
| [Firmware Update](docs/fw_update.html) | Firmware update protocol, YMODEM transfer, HR_C7000 architecture |
| [Diff Tests](docs/diff-tests.html) | Diff-driven reverse engineering test plan |
| [HD2 Manual (PDF)](https://www.ailunce.com/Assets/file/AilunceHD2-Multi-language%20Manual-A0-Ailunce%20website.pdf) | Official Ailunce HD2 multi-language manual (external PDF) |
| [NOTES](docs/NOTES.html) | Project notes and protocol/format index |

## All Scripts

| Script | Description |
|--------|-------------|
| [`codeplug.py`](scripts/codeplug.py) | Round-trip parser: `.bin` to/from Python dataclasses (channels, zones, contacts, IDs) |
| [`hd1_dump.py`](scripts/hd1_dump.py) | Full codeplug dump (8 regions: settings + addr book + channels + zones + tables) |
| [`hd1_codeplug_write.py`](scripts/hd1_codeplug_write.py) | Write a modified `.bin` back to the radio (diff-only by default) |
| [`hd1_codeplug_csv.py`](scripts/hd1_codeplug_csv.py) | Parse dumped `.bin` into hex / strings / decoded CSVs |
| [`hd1_scan.py`](scripts/hd1_scan.py) | Walk 16-bit address space at 128 B/block to map populated regions |
| [`hd1_block_scan.py`](scripts/hd1_block_scan.py) | Walk 1024-byte block address space for unmapped tables |
| [`hd1_probe_scan.py`](scripts/hd1_probe_scan.py) | Probe scan for radio responses |
| [`hd1_subcmd_scan.py`](scripts/hd1_subcmd_scan.py) | Subcommand scan |
| [`hd1_replay.py`](scripts/hd1_replay.py) | Replay captured OUT frame stream from tshark text dump |
| [`hd1_set_clock.py`](scripts/hd1_set_clock.py) | Set the radio's real-time clock |
| [`hd1_write_test.py`](scripts/hd1_write_test.py) | Write test harness |
| [`hd1_logo.py`](scripts/hd1_logo.py) | Dump the 40 KiB boot-logo image |
| [`hd1_logo_write.py`](scripts/hd1_logo_write.py) | Write a new 160x128 boot logo (RGB565 LE) |
| [`logo_render.py`](scripts/logo_render.py) | Reconstruct a BMP from a logo `.raw`, `.rgb565`, or USB pcap |
| [`fix_bitmap.py`](scripts/fix_bitmap.py) | Repair the dual channel-presence bitmap (kill-state recovery without CPS) |
| [`tweak_settings.py`](scripts/tweak_settings.py) | One-shot helper for small radio-settings changes |
| [`cps_diff.py`](scripts/cps_diff.py) | Diff two `.bin` dumps to find changed bytes |
| [`cps_tree.py`](scripts/cps_tree.py) | Tree view of codeplug structure |
| [`cps_walk.py`](scripts/cps_walk.py) | Walk codeplug regions |
| [`diff_zones.py`](scripts/diff_zones.py) | Diff the zones region between two `.bin` dumps |
| [`fw_scan.py`](scripts/fw_scan.py) | Scan firmware binary for strings and patterns |
| [`fw_analyze.py`](scripts/fw_analyze.py) | Firmware analysis (PyGhidra) |
| [`fw_analyze_mcore.py`](scripts/fw_analyze_mcore.py) | Firmware analysis (multi-core variant) |

## Hardware

- USB-serial chip: **CH340** (VID `0x1A86`, PID `0x7523`)
- Baud rate: **119200** 8N1 (non-standard)
- SoC: HR_C7000 (C-SKY CK803S core, 192 MHz) — [User Manual (Scribd)](https://www.scribd.com/document/577386066/HR-C7000-User-Manual)
- Flash: Winbond W25Q512 (64 MB SPI NOR)
- Reference hardware: [DR5800 Service Manual (PDF)](https://www.connectsystems.com/products/top/radios/CS120D/DR5800-2%20ServiceManua01.pdf) (same C7000 platform)

## Source

Documentation extracted from the [pylunce](https://github.com/anomalyco/pylunce) project.
