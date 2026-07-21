---
title: HD2 Infodump
---

# HD2 Infodump

Reverse-engineered tools and documentation for the **Ailunce HD1 / HD2 DMR radio**
(firmware `HD-GPS-HD2PA-C7000-V2.1.3-GPS.bin`).

The radio's CPS (Windows-only) uses a simple USB-serial protocol that is
partially documented upstream, but with incorrect details (wrong baud rate,
wrong frame semantics for large reads, no checksum formula). These tools
reproduce the real protocol observed in USB pcaps, verified against a live
radio.

## Codeplug Documentation

| Document | Description |
|----------|-------------|
| [Wire Protocol](docs/protocol) | Serial protocol: frames, checksums, read/write families, timing |
| [Address Space](docs/address-space) | Region map, packed `.bin` ordering, dual-bitmap, kill state |
| [Channel Format](docs/channels) | Channel slot bit-level layout, inline Rx List, VFOs |
| [Records](docs/records) | All record types: contacts, zones, Radio IDs, encryption keys, key calls, SMS, FM presets, DTMF |
| [Settings](docs/settings) | Radio-wide settings byte table |
| [Menu Tree](docs/menu-tree) | Complete radio menu hierarchy with firmware cross-reference |
| [CPS CSV Format](docs/cps-csv-format) | CPS channel import/export CSV column reference |
| [Firmware Update](docs/fw_update) | Firmware update protocol, YMODEM transfer, HR_C7000 architecture |
| [Diff Tests](docs/diff-tests) | Diff-driven reverse engineering test plan |
| [NOTES](docs/NOTES) | Project notes and protocol/format index |

## Firmware Reverse Engineering

| Document | Description |
|----------|-------------|
| [Firmware Summary](docs/firmware-summary) | Full analysis: memory layout, subsystem inventory, tone tables, IARU presets, DMR layer, GPS, encryption, Ghidra results |
| [HR_C7000 Reference Tables](docs/firmware-c7000-reference) | Memory map, PIC interrupts, baseband sub-interrupts, IO pin mux, boot flow |
| [HR_C7000 BGA Pinmap](docs/firmware-c7000-pinmap) | Full pin map with JTAG, UART0, SPI, USB, power pins |
| [Menu Dispatcher Architecture](docs/firmware-dispatcher-architecture) | How the menu pointer table dispatches to ROM-resident handlers |
| [Firmware Analysis Notes](docs/firmware-analysis-notes) | Key-swap decryption bugs, function pointer tables, structural findings |
| [Ghidra Import Kit](docs/firmware-ghidra-README) | Memory map, decryption reproducibility, coverage stats |
| [Ghidra Quickstart](docs/firmware-ghidra-quickstart) | Step-by-step Ghidra import, metadata scripts, navigation tips |
| [Open Questions](docs/firmware-open-questions) | Unresolved codeplug questions vs. firmware analysis status |

## OpenRTX Implementation Notes

Notes from the [OpenRTX](https://openrtx.org/) port to the HD2 (Miosix / CK803S):
how the reverse-engineered hardware is actually driven, with HW-verified register
sequences.

| Document | Description |
|----------|-------------|
| [Audio — PCM Playback](docs/openrtx-audio) | CPU→speaker codec-DAC path: SAHB PCM bridge, bring-up sequence, the PTB17 path-select bit, and the codec/SOCSYS register reference |

## Scripts {#scripts}

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

## Hardware {#hardware}

- USB-serial chip: **CH340** (VID `0x1A86`, PID `0x7523`)
- Baud rate: **119200** 8N1 (non-standard)
- SoC: HR_C7000 (C-SKY CK803S core, 192 MHz) — [User Manual (Scribd)](https://www.scribd.com/document/577386066/HR-C7000-User-Manual)
- Flash: Winbond W25Q512 (64 MB SPI NOR)
- Reference hardware: [DR5800 Service Manual (PDF)](https://www.connectsystems.com/products/top/radios/CS120D/DR5800-2%20ServiceManua01.pdf) (same C7000 platform)
- HR_C7000 datasheet: [HR_C7000 Document 2 (PDF)](https://www.connectsystems.com/products/top/radios/CS120D/HR_C7000%20Document%202.pdf)

---

## Firmware cross-references (2026-05-13)

Cross-referenced against the V2.1.3 firmware decompile (`assets/source_v213/`
in the hd2-clean working tree). Settings.md / NOTES.md open questions
that the firmware analysis can answer or constrain:

### Resolved: codeplug `0xE800` returns a hardcoded model-ID stub

The CPS reads `0xE800` during write-session setup; pylunce notes it
isn't in any of the 8 dumped regions. **Firmware confirmation:** the
wire-protocol READ handler (`wire_cmd00_read_handler` at V2.1.3 VMA
`0x03042814`, line ~70540 of the app decompile) special-cases this one
address by writing 7 hardcoded bytes (`I H D 8 5 8 0`) directly into
the response buffer instead of reading from the small-settings bank at
`0x790000 + offset`. So `0xE800` isn't a real codeplug address — it's
a probe slot the firmware answers with a fixed model identifier. There
is no settings data behind it; no codeplug content is "missing" from
the dump.

### Constrained: `+0x12` per-channel byte is GPS contact index only

pylunce/channels.md marks "`+0x12` byte's role beyond GPS-contact
unconfirmed." Firmware confirms `+0x12` is **only** the GPS contact
index (1-based; 0 = none). No other firmware path reads this byte.

### Resolved: per-channel settings setter ↔ flash settings address map

The on-radio menu's per-setting handlers are now named in the v213
project (`setting_set_*` family, mostly in `0x0304b1a0..0x0304b550`).
Each setter writes one byte/bit of the in-RAM `g_state` mirror; the
flash backing store is at `0x790000+` (b1=0x0F, 128-byte stride).
Firmware-side bit-mappings agree with settings.md for the following
items (high-confidence cross-check; firmware setter at left, flash
address from settings.md at right):

| Firmware setter                          | Flash settings addr | Field         |
|------------------------------------------|---------------------|---------------|
| `setting_set_squelch`                    | `0x2970`            | Squelch (0..9)|
| `setting_set_voice_at_0x25_b5`           | `0x2971` bit 5      | Voice prompt  |
| `setting_set_roger_beep`                 | `0x2971` bit 1      | Roger beep    |
| `setting_set_keylock`                    | `0x2971` bit 2      | Auto key lock |
| `setting_set_backlight`                  | `0x2972`            | Backlight     |
| `setting_set_scanmode`                   | `0x2973` bit 0      | Scan Mode     |
| `setting_set_save_mode`                  | `0x2973` bits 7:5   | Power Save    |
| `setting_set_double_ptt`                 | `0x2973` bit 3      | Double PTT    |
| `setting_set_ab_time`                    | `0x2974`            | A/B Time      |
| `setting_set_fm_tx_beep`                 | `0x2975` bit 4      | DMR TX Beep   |
| `setting_set_keybeep`                    | `0x2977` bit 7      | Key Beep      |
| `setting_set_micgain`                    | `0x299B`            | Mic Gain      |
| `setting_set_brightness`                 | `0x299C`            | Brightness    |
| `setting_set_sd_mode`                    | `0x299D` bit 2      | S/D Mode      |
| `setting_set_menu_exit_timeout`          | `0x299E`            | Menu Exit     |
| `setting_set_lockmode`                   | `0x299F` bits 6:5   | Lock Mode     |
| `setting_set_step_remapped`              | `0x297F`            | VFO Step      |
| `keydefine_dispatch_assign`              | `0x29A8..0x29AB`+   | PF key actions|

### Constrained: Kill/Wakeup codes live in the channel record, not in `0x29AC`

pylunce/NOTES.md flagged "Emergency Alarm encoding at `0x29AC` —
address confirmed, encoding unknown." The firmware decompile has
`dmr_tx_csbk_kill_wakeup` (`0x0305219c`) reading **`+0xAC` (kill
code)** and **`+0xAE` (wakeup code)** from the per-channel record.
Both are 1-byte 1-based **contact indices** (0 = none); the channels.md
description (already correct) matches the firmware. The `0x29AC`
settings byte is a separate global emergency-alarm config — its
firmware setter has not been pinned down yet.

### SRAM-resident menu handlers — clarification

settings.md's appendix claims menu segment handlers live in SRAM
`0x055xxxxx..0x056xxxxx`. The specific handler addresses listed
(`0x0561daee`, `0x05670c82`, …) do NOT appear as 4-byte literal
pointers in either the v208 or v213 firmware `.bin`. Two
possibilities, both consistent:
- The handler-pointer values listed in the table were captured from a
  live debug session of an older firmware revision and don't
  represent stable v2.1.3 entry points.
- The handlers are constructed by indirect dispatch in code we already
  have at `0x0304bxxx` (the `setting_set_*` family), and the
  "segment handler" pointer field is consumed by a dispatcher that
  treats out-of-app-range values as opaque cookies.

The 32-entry key-define action enum that settings.md lists (`0x00..0x23`)
matches the v2.1.3 firmware's behaviour empirically (the on-radio
"Key Define" menu offers the same actions), but the runtime enum→action
dispatcher cannot be statically resolved without dumping that SRAM
region.

### Wire-protocol firmware case table (informational)

The wire-protocol command parser in firmware (`wire_protocol_parse` at
V2.1.3 VMA `0x0304323c`) implements 5 sync-framed (`0x68`-prefix)
command paths plus 5 unsynced ASCII probes. Beyond what pylunce
already documents, the firmware-recovered cases are:

- `cmd=0x07 sub=0x01`: READ RTC datetime (10-byte response from the
  internal RTC mirror buffer at IRAM `0x00040504`).
- `cmd=0x07 sub=0x02`: exit programming mode (calls `screen_destroy`).
- `cmd=0x03 b1=0x09`: RF alignment / test-tone (writes modem MMIO
  `0x11000100 = 0x73`).
- Single-byte `V` probe: alias of `GetVer`.
- `SLC7001` probe: sibling of `SLC7000`, replies `BJDR380`.

See `hd2_infodump/docs/protocol.md` (or `pylunce/docs/protocol.md`)
§"Firmware-recovered commands" for the full bit-level details.

### Activa probe is more than an identity check

pylunce notes the `Activa` ASCII probe and that it returns the UID.
Reality is more involved: the **6-byte probe** form returns the
8-byte UID (same as `GetUID`). The **270-byte form** (keyword + token
+ fill payload) is the radio's activation transaction — it writes
NVRAM slots (`g1/g3/g11/g12/g21/g22/g50`) and unlocks RX. See
`activa_tests/test_38_uid_buf_g22.py` / `test_39_uid_0a92.py` for the
full payload structure.

