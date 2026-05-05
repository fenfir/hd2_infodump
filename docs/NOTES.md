# HD1 / HD2 reverse-engineering notes

Detailed reference docs:

- [Wire protocol](docs/protocol.md) — serial settings, frame layouts,
  checksums, read/write families, timing.
- [Address space + bitmap + kill state](docs/address-space.md) — region
  map, packed `.bin` ordering, dual channel-presence bitmap, anti-tamper
  self-destruct.
- [Channel slot format](docs/channels.md) — bit-level channel layout,
  inline Rx List, VFOs.
- [Records: contacts, zones, group aliases, Radio IDs](docs/records.md)
- [Radio settings](docs/settings.md)

## CPS Software Architecture (from HD2 v1.14 decompilation)

The official Windows CPS (`HD2 v1.14.exe`) is a **compiled Visual Basic 6**
application (MSVBVM60.DLL) using **MSCOMM32.OCX** for serial I/O. Key
internal details from Ghidra decompilation of the CPS binary:

| Item | Value |
|------|-------|
| VB6 runtime | MSVBVM60.DLL |
| Serial control | MSCOMM32.OCX (`MSCommLib.MSComm`) |
| Serial module | `ModComm` (port open/close, read/write) |
| Encode/decode module | `modEnDecode_Eliminator` (hex conversion, possibly XOR) |
| Product/model ID | `100020` (referenced internally) |
| Internal codenames | `SLC7000`, `IHD8580`, `JDR380`, `BJDR38` |
| CPS config baud string | `"115200,N,8,1"` (actual wire rate is 119200 — the
  CH340 may map 115200 to 119200 internally) |
| Native file format | `.tw` (binary, VB6 Random Access) |
| Secondary data file | `22.tb3` (in CPS app directory) |
| Temporary file | `tempqfeo.dat` (staging during save) |
| Product string | `"RETEVIS Ailunce HD2 V1.14"` |
| Version resource | `1.01.0004` (embedded in PE) |

The CPS serial port is configured via MSComm properties: CommPort,
Settings (`"115200,N,8,1"`), RThreshold=1024, InputLen=0, DTREnable=True.
Data is sent as hex-encoded ASCII strings internally, though the actual
wire protocol uses binary frames (see protocol.md).

The CPS uses a 3-step initialization handshake before read/write operations:
model ID byte → sub-model byte → config integer, then validates the radio
responds with `"RETEVIS Ailunce HD2 V1.14"`. Several critical protocol
functions (the main state machine, byte-level I/O, and encode/decode) exceed
Ghidra's MAX_INSN limit and could not be fully decompiled — the actual
low-level framing logic is inside COM objects whose internal code was not
resolved.

## Open questions

- VFO-B CH-Mode and other VFO-B-only settings live in an unmapped region
  (probably radio `0xE800`).
- Group Alias `+0x0A` 4-byte field — partial decode (looks like a
  contact reference; "default contact"?).
- `table_4000` (1 KB) beyond Radio IDs — unknown.
- `table_428x` (3 KB) — unknown.
- `table_1dfx` residual — Quick Messages occupy first ~3.2 KB (`0x1DF8+0xDC`,
  200 B × 16 slots); purpose of remaining ~8.8 KB unknown.
- Channel `+0x12` byte's role beyond GPS-contact index — unconfirmed.
- Many settings bytes unmapped — see "Still unmapped" table in `docs/settings.md`.
- DTMF digit-sequence tables (per-channel index is mapped; actual digit
  sequences are not). 2-tone / 5-tone tables also unmapped.
- Emergency Alarm type at `0x299D` bit 1 (clear=Remote, set=Local ✓);
  Emergency key functions at `0x29AE`/`0x29AF` (same enum as Key Define).
- **IARU Region** — the CPS stores band limits in a `b1=0x0E`
  WriteCommit frame (16-byte payload, separate from normal codeplug writes),
  bypassing the `b1=0x0F`/`b1=0x31` address space entirely.
- CPS internally uses product/model ID string `100020` and codenames
  `SLC7000`, `IHD8580`, `JDR380`, `BJDR38`. `IHD8580` matches the
  radio ID string at `0xE800` (see settings.md).
