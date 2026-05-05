# Contacts, group aliases, zones, Radio IDs, and other records

## Structure summary

| Record type | Stride | Max count | Region | Radio addr | File offset (`codeplug.py` const) |
|-------------|--------|-----------|--------|------------|-----------------------------------|
| Priority Contact | 72 B | 14 per block | `channels` | `0x1B84..0x1BCB` | `CONTACT_STRIDE` / `CONTACTS_PER_BLOCK` |
| Address Book Contact | 72 B | 14 per block | `addr_book` | block `0x0000` | `CONTACT_STRIDE` |
| Channel slot | 176 B | 5 per block | `channels` | `0x1BCC..0x1DCF` | `CHANNEL_STRIDE` / `CHANNELS_PER_BLOCK` |
| VFO record | 32 B | 2 (A + B) | `header` | `0x0090`, `0x0140` | (first 32 B of channel layout) |
| Zone | 145 B | 256 | `table_21dx` | `0x2200+` | `ZONE_STRIDE` / `ZONE_MAX_CHANNELS` / `ZONE_MAX_COUNT` |
| RX Group Alias | 142 B | ~28 per block | `table_21dx` | `0x21D8..0x21FF` | `RX_GROUP_STRIDE` |
| Radio ID | 20 B | 16 | `settings` | `0x4000+` | `RADIO_ID_STRIDE` |
| Normal Encryption Key | 2 B | 16 | `settings` | `0x3D00` | `NORMAL_KEY_STRIDE` / `MAX_NORMAL_KEYS` |
| Enhanced Encryption Key | 16 B | 16 | `settings` | `0x3E00` | `ENHANCED_KEY_STRIDE` / `MAX_ENHANCED_KEYS` |
| AES/ARC4 Encryption Key | 49 B | 48 (3×16) | `settings` | `0x5018+` | `ENCRYPT_KEY_STRIDE` / `MAX_ENCRYPT_KEYS` |
| Key Call | 7 B | 6 | `settings` | `0x29D0` | `KEY_CALL_STRIDE` / `NUM_KEY_CALLS` |
| Quick SMS Message | 200 B | 16 | `table_1dfx` | block `0x1DF8` + `0xDC` | `QUICK_MSG_STRIDE` / `MAX_QUICK_MESSAGES` |
| FM Radio preset | 4 B | 32 + VFO | `settings` | `0x3000..0x3087` | (see `settings.md`) |
| DTMF Encode Table | 16 B | 128 | `settings` | `0x4471..0x4C70` | (see `settings.md`) |

All structures are defined as Python dataclasses in [`codeplug.py`](../scripts/codeplug.py)
with `from_bytes()` / `to_bytes()` round-trip methods.

## Priority Contacts @ radio block `0x1B84` (first block of `channels` region)

72-byte records, up to 14 per 1024-byte block. These are the "Priority
Contact" entries in CPS (distinct from Address Book contacts).

```
  [0x00]   4 B   DMR ID (LE uint32; 0xFFFFFFFF = "all call")
  [0x04]   1 B   type     (0x04 = group, 0x05 = private, 0x06 = all)
  [0x05]  16 B   name     (ASCII, null-padded)
  [0x15]  16 B   city     (ASCII, null-padded; zeros when empty)
  [0x25]  16 B   province (ASCII, null-padded; zeros when empty)
  [0x35]  16 B   country  (ASCII, null-padded; zeros when empty)
  [0x45]   3 B   0xFF terminator
```

Total mapped bytes: 0x48 = 72. The remaining bytes within the 72-byte
stride are padding/terminator (the CPS writes 0xFF at `+0x45..+0x47`).

The type byte values correspond to the radio menu enum surfaced in
firmware rodata: `Group` (`0x04`), `Private` (`0x05`), `All` (`0x06`).
The labels `Group` / `Private` / `All` are at v208 menu pool offsets
`0x06e558` / `0x06e560` / `0x06e568` (visible on the radio's contact
detail screen). The Chinese counterparts are 增加联系人 (Add Contact)
and 删除联系人 (Delete Contact) per the contact-management menu.

### Per-field editor and display surface

The 72-byte record carries **four** name fields, but the radio surfaces
only the first one. Use this table to know what's editable from the
radio's keypad versus CPS-only.

| Offset | Field    | Bytes | Editable on radio | Displayed on radio | CPS edit |
|--------|----------|-------|-------------------|--------------------|----------|
| `+0x00`| DMR ID   | 4     | ✓ (Edit ID)       | ✓ (`Priva/Group/All call:` prefix) | ✓ |
| `+0x04`| Type     | 1     | ✓ (Group/Private/All toggle) | ✓ (icon)  | ✓ |
| `+0x05`| Name     | 16    | ✓ (ID Name editor; abc/ABC/123 modes) | ✓ (call screen) | ✓ |
| `+0x15`| City     | 16    | ✗                 | ✗                  | ✓ |
| `+0x25`| Province | 16    | ✗                 | ✗                  | ✓ |
| `+0x35`| Country  | 16    | ✗                 | ✗                  | ✓ |

City / Province / Country are CPS-only metadata; firmware string
search confirms no `City` / `Province` / `Country` labels exist in the
v208 rodata — the radio firmware never surfaces these fields. They
round-trip through the codeplug correctly so a CPS-edited record
keeps its address data intact across radio dump → re-write cycles.

For round-trip codeplug work: treat all four as opaque 16-byte ASCII
fields, null-pad blank entries (the CPS uses 0x00 padding for empty;
not 0xFF — see `0x06d9c4` test data).

## Address Book @ radio b1=0x31 block `0x0000` (`addr_book` region)

Same 72-byte record format as Priority Contacts. 14 entries per 1024-byte
block. Lives in its own `b1=0x31` block at radio address `0x0000`, which
maps to file offset `0x3C00` in the packed `.bin`.

```
  [0x00]   4 B   DMR ID (LE uint32)
  [0x04]   1 B   type     (0x04 = group, 0x05 = private, 0x06 = all)
  [0x05]  16 B   name     (ASCII, null-padded)
  [0x15]  16 B   city     (ASCII, null-padded)
  [0x25]  16 B   province (ASCII, null-padded)
  [0x35]  16 B   country  (ASCII, null-padded)
  [0x45]   3 B   0xFF terminator
```

Differences from Priority Contacts:

- "All Call" entries have **DMR ID = 0** (not `0xFFFFFFFF`).
- The CPS initialises empty slots by zeroing the entire 72 bytes
  (Priority Contacts use 0xFF fill for empty slots).

Write verified: a 7-entry CSV round-tripped through CPS write + radio
readback bit-for-bit. The example builder
(`examples/build_ai5qz_bin.py`) writes a single Germany TG (262, group)
to slot 0.

## RX Group Aliases @ radio block `0x21D8` (`table_21dx` region)

142-byte (`0x8E`) records. These are named RX group lists that map to
sets of contacts.

```
  [0x00]  10 B   name     (ASCII, null-padded)
  [0x0A]   4 B   unknown  (LE uint32; observed values: 100000, 100002)
                     possibly a default contact reference for the group
  [0x0E] 128 B   member list (4-byte LE contact references,
                               0xFFFFFFFF terminated; ~32 entries max)
```

Total mapped bytes: 0x8E = 142.

### Member-list contact reference encoding

The 4-byte LE values in the member list are **not** raw DMR IDs — they
are encoded contact references:

- **Address book contacts** are encoded as their 0-based index (0, 1, 2…).
- **Priority contacts** are encoded as `100000 + index` (100000, 100003…).
- `0` is a VALID value (address book index 0), NOT a terminator. Only
  `0xFFFFFFFF` terminates the list.

### Packing

Records are densely packed starting at block `0x21D8`. The zone region
begins at block `0x2200`, leaving `0x2200 - 0x21D8 = 0x28` = 40 blocks =
40,960 bytes for group aliases. At 142 bytes each that is ~288 records
theoretically, but the practical limit is likely lower (the CPS UI shows
32 as a maximum in the grid).

## Zones @ radio blocks `0x2200+` (`table_21dx` region)

Densely packed records (NOT one zone per 1024-byte block). Stride is
**145 bytes (`0x91`)** per zone slot, starting at the first byte of block
`0x2200`. Verified by creating `TestZone1` (1 channel) and `TestZone2`
(3 channels) in CPS and diffing.

```
  [0x00]   1 B    count        (0xff = empty slot, otherwise 0..64)
  [0x01]  128 B   channel list (count × 2-byte LE channel index, 0-based;
                                trailing bytes 0xff)
  [0x81]  16 B    name         (ASCII, null-padded; 0xff = empty)
```

Total mapped bytes: 0x91 = 145.

Capacity: max **256 zones**, max **64 channels per zone** (UI-confirmed).
256 × 145 = 37,120 bytes ≈ first 36.25 blocks of the zone region.

Empty slots have `count=0xff` and name area=`0xff`. The radio writes
zones into the lowest available slot index when adding a new zone (both
TestZone1 and TestZone2 ended up packed at slots 0 and 1).

The firmware names this menu `Zone` / 区域选择 (zone select) — the
"Default Zone Band A/B" CPS settings (`0x29A4`, `0x29A6` per
`settings.md`) carry a 0-based index into this zone table.

## Radio IDs @ radio `0x4000+` (inside the `settings` region)

20-byte stride. Format per entry:

```
  [0x00]   4 B   DMR ID (uint32 LE)
  [0x04]  16 B   name (ASCII, null-padded)
```

Total mapped bytes: 0x14 = 20.

Up to 16 entries (320 bytes), starting at settings radio `0x4000`.

Confirmed slots in the test codeplug: `radio-1` (1234) at slot 0,
`radio-2` (2345) at slot 1, `radio-3` (3456) at slot 2.

Per-channel selection is **not** stored in the channel slot — it lives in
the settings region. Changing channel 2's Radio ID flipped a single byte
at `settings 0x29A3` from `0x00` → `0x01`, suggesting either:

- a single global "active radio ID index" (most likely), or
- a per-channel index whose location for channel 2 happens to be `0x29A3`.

## Header @ radio `0x0000` (`header` region)

The `header` region is 512 bytes (4 × 128-byte `b1=0x0F` reads from radio
`0x0000..0x017F`). It contains:

| Offset | Size | Content | Notes |
|--------|------|---------|-------|
| `0x0000` | 4 B | DMR ID (LE uint32) | Header DMR ID 1 |
| `0x0004` | 4 B | DMR ID (LE uint32) | Header DMR ID 2 |
| `0x0080` | 4 B | padding | |
| `0x0084` | 12 B | unknown | |
| `0x0090` | 32 B | VFO-A record | See below |
| `0x00B0` | 48 B | unknown | |
| `0x00E0` | 32 B | unknown | |
| `0x0100` | 32 B | unknown | |
| `0x0120` | 32 B | unknown | |
| `0x0140` | 32 B | VFO-B record | See below |
| `0x0160` | 128 B | unknown | |

Only the two VFO records and the two DMR IDs have been decoded.

## VFO-A / VFO-B records (`header` region)

32-byte records at radio `0x0090` (VFO-A) and `0x0140` (VFO-B).
Layout is identical to the trailing portion of a channel slot starting at
channel-offset `0x10` (no marker/name prefix):

```
  [0x00]   4 B  flags     (FM = 0x00002000, DMR = 0x00000000)
  [0x04]   4 B  rx freq   BCD LE, value × 10 Hz
  [0x08]   4 B  tx freq   BCD LE
  [0x0C]   4 B  contact   uint32 LE DMR ID
  [0x10]   4 B  mode / power / scan / GPS bytes
  [0x14]   2 B  rx tone   CTCSS/DCS (0xFFFF = none; FM only)
  [0x16]   2 B  tx tone   CTCSS/DCS (0xFFFF = none; FM only)
  [0x18]   8 B  flags / squelch / TS / CC / etc.
```

Full bit-level decode of `+0x10..+0x1F` is the same as channel
`+0x20..+0x2F` — see [`channels.md`](channels.md) for the complete
bit map.

VFO-B CH-Mode and other VFO-B-only settings appear to live in an unmapped
region, probably radio `0xE800` (CPS reads it during the setup probe).

## Key Calls 1-6 @ settings `0x29D0`

Programmable key-call bindings. 7-byte stride, 6 slots.

```
  [0x00]   1 B   mode        (0 = analog, 1 = digital)
  [0x01]   4 B   contact ref (LE uint32; see encoding below)
  [0x05]   1 B   call type   (0 = unset, 1 = voice, 2 = message)
  [0x06]   1 B   quick msg   (1-based index; 0 = none)
```

Total mapped bytes: 7.

### Contact reference encoding

| Value range        | Meaning                |
|-------------------|------------------------|
| `0`               | unset                  |
| `1..N`            | address book index `N−1` (1 = AB[0]) |
| `100001..100000+N` | priority contact index `N−100001` (100001 = priority[0]) |

The `.present` property is true if either `contact_ref != 0` or
`quick_msg_index != 0`.

## Normal Encryption Keys @ settings `0x3D00`

16 slots, 2 bytes each, big-endian BCD.

```
  [0x00]   2 B   key value  (BE BCD; 0x0000..0xFFFF; all-FF = unused)
```

Total: 32 bytes. Used when channel Encryption Type = `Normal Mode`.

## Enhanced Encryption Keys @ settings `0x3E00`

16 slots, 16 bytes each. Raw key material; exact encoding not
documented (preserved verbatim for round-trip).

```
  [0x00]  16 B   key data  (all-FF = unused)
```

Total: 256 bytes. Used when channel Encryption Type = `Enhanced`.

## AES/ARC4 Encryption Keys @ settings `0x5018`

48 slots organized into three groups of 16, 49-byte stride each.
24-byte header at `0x5000` (contents not documented).

```
  [0x00]  49 B   key data  (all-FF = unused; exact encoding not documented)
```

Total: 48 × 49 = 2,352 bytes. Used when channel Encryption Type = `Special`.

### Key type by slot index

| Slot range | Key type | CPS Encryption Type |
|-----------|----------|---------------------|
| 0..15    | AES256   | `Special`            |
| 16..31   | AES128   | `Special`            |
| 32..47   | ARC4     | `Special`            |

The firmware menu labels the five distinct cipher types: `Normal`,
`Enhanced`, `ARC4`, `AES128`, `AES256`. The CPS `Special` dropdown
covers the last three; the specific cipher is determined by which
slot range the key index falls in.

## Quick SMS Messages @ `table_1dfx` block `0x1DF8` + `0xDC`

Pre-written SMS text messages. 16 slots, 200-byte stride.

```
  [0x00]  200 B  text  (null-terminated ASCII, up to 199 chars;
                  all-0xFF or all-0x00 = unused slot)
```

Total: 16 × 200 = 3,200 bytes.

The first 4 slots fit within block `0x1DF8` (first slot at block offset
`0xDC` = 220). Slots 5-16 spill into block `0x1DF9`.

## FM Radio Presets @ settings `0x3000` (136 bytes)

32 FM broadcast preset channels + VFO frequency. See
[`settings.md`](settings.md) "FM Radio" section for the full layout.

| Offset | Bytes | Meaning |
|--------|-------|---------|
| `0x3000..0x3003` | 4 | Slot bitmap (LE uint32). Bit `i` cleared = slot `i+1` used. |
| `0x3004..0x3083` | 128 | 32 slots × 4 B BCD LE frequency × 10 Hz. Slot N at `0x3004 + (N-1)*4`. |
| `0x3084..0x3087` | 4 | FM Radio VFO frequency (BCD LE × 10 Hz). |

## DTMF Encode Table @ settings `0x4471` (16 bytes × 128 slots)

128 DTMF code slots. Each holds up to 14 DTMF digits. 17-byte header at
`0x4460` (purpose TBD). See [`settings.md`](settings.md) "DTMF Encode
Table" section for the full slot layout and digit encoding.
