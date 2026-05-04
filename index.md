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
| [HD2 Manual](docs/Ailuncehd2_manual.html) | Official HD2 user's manual (extracted text) |

## Key Scripts

| Script | Description |
|--------|-------------|
| [`codeplug.py`](scripts/codeplug.py) | Round-trip parser: `.bin` to/from Python dataclasses (channels, zones, contacts, IDs) |
| [`hd1_dump.py`](scripts/hd1_dump.py) | Full codeplug dump (8 regions: settings + addr book + channels + zones + tables) |
| [`hd1_codeplug_write.py`](scripts/hd1_codeplug_write.py) | Write a modified `.bin` back to the radio (diff-only by default) |
| [`fix_bitmap.py`](scripts/fix_bitmap.py) | Repair the dual channel-presence bitmap (kill-state recovery without CPS) |
| [`tweak_settings.py`](scripts/tweak_settings.py) | One-shot helper for small radio-settings changes |
| [`cps_diff.py`](scripts/cps_diff.py) | Diff two `.bin` dumps to find changed bytes |

## Hardware

- USB-serial chip: **CH340** (VID `0x1A86`, PID `0x7523`)
- Baud rate: **119200** 8N1 (non-standard)
- SoC: HR_C7000 (C-SKY CK803S core, 192 MHz)
- Flash: Winbond W25Q512 (64 MB SPI NOR)

## Source

Documentation extracted from the [pylunce](https://github.com/anomalyco/pylunce) project.
