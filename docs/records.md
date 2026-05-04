# Contacts, group aliases, zones, Radio IDs

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

The type byte values correspond to the radio menu enum surfaced in
firmware rodata: `Group` (`0x04`), `Private` (`0x05`), `All` (`0x06`).
The labels `Group` / `Private` / `All` are at v208 menu pool offsets
`0x06e558` / `0x06e560` / `0x06e568` (visible on the radio's contact
detail screen). The Chinese counterparts are 增加联系人 (Add Contact)
and 删除联系人 (Delete Contact) per the contact-management menu.

The city/province/country fields are CPS-side metadata — they ride along
in the codeplug but the firmware menu only displays `name` on contact
selection. Treating them as opaque ASCII for round-trip is sufficient.

## Address Book @ radio b1=0x31 block `0x0000` (`addr_book` region)

Same 72-byte record format as Priority Contacts. 14 entries per 1024-byte
block. Lives in its own `b1=0x31` block at radio address `0x0000`, which
maps to file offset `0x3C00` in the packed `.bin`.

Differences from Priority Contacts:

- "All Call" entries have **DMR ID = 0** (not `0xFFFFFFFF`).
- The CPS initialises empty slots by zeroing the entire 72 bytes.

Write verified: a 7-entry CSV round-tripped through CPS write + radio
readback bit-for-bit. The example builder
(`examples/build_ai5qz_bin.py`) writes a single Germany TG (262, group)
to slot 0.

## RX Group Aliases @ radio block `0x21D8` (`table_21dx` region)

142-byte (`0x8E`) records. These are named RX group lists that map to
sets of contacts.

```
  [0x00]  10 B   name     (ASCII, null-padded)
  [0x0A]   4 B   unknown  (LE uint32; possibly internal ID — see note)
  [0x0E] 128 B   member list (4-byte LE contact references,
                              0xFFFFFFFF terminated; ~32 entries max)
```

### Member-list contact reference encoding

The 4-byte LE values in the member list are **not** raw DMR IDs — they
are encoded contact references:

- **Address book contacts** are encoded as their 0-based index (0, 1, 2…).
- **Priority contacts** are encoded as `100000 + index` (100000, 100003…).
- `0` is a VALID value (address book index 0), NOT a terminator. Only
  `0xFFFFFFFF` terminates the list.

The `+0x0A` 4-byte field has been only partially decoded — observed
values include `100000` and `100002`, suggesting it's also a contact
reference (perhaps the "default" contact for the group).

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

Confirmed slots in the test codeplug: `radio-1` (1234) at slot 0,
`radio-2` (2345) at slot 1, `radio-3` (3456) at slot 2.

Per-channel selection is **not** stored in the channel slot — it lives in
the settings region. Changing channel 2's Radio ID flipped a single byte
at `settings 0x29A3` from `0x00` → `0x01`, suggesting either:

- a single global "active radio ID index" (most likely), or
- a per-channel index whose location for channel 2 happens to be `0x29A3`.

## Header @ radio `0x0000`

Two 4-byte LE uint32 DMR IDs at offsets 0 and 4.
