# pylunce2 open questions — firmware-analysis status

Cross-reference of unresolved codeplug-format questions against what
the v32 firmware string + Ghidra analysis can tell us.

## Summary

Of 9 open questions, the firmware analysis directly resolves **0**,
partially informs **2**, and leaves **7** still requiring either
behavioral diff sessions or interactive Ghidra exploration.

The fundamental limit: the radio reads codeplug data through a
serial-protocol layer that abstracts addresses behind block-read
commands. The firmware uses internal RAM offsets, not codeplug-side
radio addresses, when applying settings. So bare `0x29AC` /
`0x4280` / `0x1DF8` constants do not appear in firmware code.

To answer most of these, you need either:
1. **Behavioral diff** — toggle the setting, re-dump the codeplug,
   find the changed byte (the existing `pylunce/CLAUDE.md` workflow).
2. **Interactive Ghidra** — open `v32_ghidra/v32_proj.gpr`, find the
   protocol-handler function, trace data-flow to feature-specific
   handlers.

---

## Question-by-question

### 1. VFO-B CH-Mode and other VFO-B-only settings live in an unmapped region (probably radio 0xE800).

**Status: cannot answer from firmware analysis.**

Radio address `0xE800` is in the protocol-side address space (read via
`b1=0x0F`); it's not directly addressable as a flash offset, so it
won't appear as a bare constant in code. Firmware accesses it via the
abstract block-read protocol.

**Recommendation:** behavioral diff session. Toggle VFO-B CH-Mode in
CPS, dump radio `0xE800` block before+after, diff.

### 2. Group Alias +0x0A 4-byte field — partial decode (looks like a contact reference; "default contact"?).

**Status: cannot answer directly. Hint from firmware: "default
contact" interpretation is plausible.**

The firmware has menu strings `Add(Priority)` (`0x06feb0`),
`Add(Local)` (`0x06feb8`), `Local` / `Priority` selectors, and a clear
distinction between `联系人` (priority list) vs `通信录` (address
book) — both backing the existing dual-table architecture. Within a
group alias record, a "default contact" pointing at one of these two
tables fits the encoding pattern (`100000 + index` for priority,
`0..N` for address book).

**Recommendation:** open the Ghidra project, find a function that
parses the 142-byte group-alias record, trace what it does with bytes
at `+0x0A..+0x0D`. The 0x4000 constant appears 16 times in firmware
which suggests there's a "lookup contact by reference" function
candidate.

### 3. table_4000 residual (1 KB beyond Radio IDs).

**Status: cannot answer from firmware analysis.**

Radio IDs occupy `0x4000..0x4280` (32 entries × 20 bytes = 640 B).
The remaining `0x4280..0x4400` (384 B) is unknown.

The firmware references address `0x4000` 16 times as a 16-bit LE
constant, suggesting it's the base address for some lookup. But the
specific tail-region usage isn't visible in strings.

**Recommendation:** behavioral diff. Modify radio settings until
something writes into the `0x4280..0x43FF` window.

### 4. table_428x (3 KB at radio 0x4280) — unknown.

**Status: cannot answer. Speculative possibilities:**

Looking at adjacent regions:
- `0x4400` is the DTMF Config Header (7 bytes)
- `0x4407` starts DTMF Code Fields (Self ID / Kill / Stun / Wake Up / BOT / EOT)
- `0x4471` is the DTMF Encode Table (16 B × 128 slots)
- `0x5018` is AES/ARC4 keys

So `0x4280..0x4400` (3 KB) sits between the Radio IDs table and the
DTMF subsystem. Likely candidates:
- DMR-specific identification table (e.g., privacy preset keys)
- Per-channel DMR slot/color-code mask
- Factory tuning data (alternate to `0x070700+` reflection)
- Reserved padding

The firmware has `g_tune_data_struct` referenced via debug printfs,
but the actual struct address isn't visible from strings.

**Recommendation:** diff session — write a `0xAA` pattern across
0x4280-0x43FF, observe radio behavior or factory-mode dumps for
changes.

### 5. table_1dfx residual (~8.8 KB beyond Quick Messages).

**Status: cannot answer.**

Quick Messages occupy `0x1DF8 + 0xDC..0x1DF8 + 0xDC + 200×16` (200 B
per slot × 16 slots = 3200 B). Total `table_1dfx` is 12 KB; ~8.8 KB
unaccounted.

No firmware string hints. Possibilities: encrypted message storage,
DMR session state, OTA-receive scratch buffer, factory test data.

**Recommendation:** diff session.

### 6. Channel +0x12 byte's role beyond GPS-contact index.

**Status: partially informed by firmware findings.**

Firmware has `1:1`, `1:2`, `1:3`, `1:4`, `Off`, `Scan` strings at
`0x06ead4`, immediately following GPS-related menu items
(`Local GPS`, `Receive GPS`, `Missed`, `Answered`, `Outgoing`). These
are likely **GPS report frequency ratios** — "every 1st transmission",
"every 2nd", etc. A natural fit for a 1-byte field on the channel.

Whether this lives at `+0x12` (combining with GPS-contact index) or a
separate channel byte: still unverified.

**Recommendation:** diff session — set GPS Outgoing ratio to 1:2 vs
1:4, find the differing channel byte. If it's `+0x12`, then `+0x12`
encodes both the GPS-contact 1-based index AND the report ratio (most
likely as separate nibbles).

### 7. Many settings bytes unmapped.

**Status: cannot answer in bulk.**

Each unmapped byte requires its own diff session. The firmware
analysis doesn't shortcut this — settings bytes are accessed via RAM
offsets (after a block-read into a buffer), not by their codeplug
address.

**Recommendation:** the existing `pylunce/CLAUDE.md` "Diff-driven
reverse engineering workflow" is the right approach, one byte at a
time.

### 8. DTMF digit-sequence tables; 2-tone / 5-tone tables.

**Status: DTMF largely answered already; 2-tone/5-tone genuinely
absent.**

DTMF format is already documented (16 B × 128 slots at `0x4471`,
14 digit bytes + length + pad). Per-channel index at `+0x10` low
7 bits. **Question is mostly already-answered.**

For 2-tone / 5-tone:
- Firmware has no strings mentioning "2-tone", "5-tone", "select tone",
  or similar.
- The CPS UI mentions these but they're absent from radio rodata.
- Either they're feature-flag-disabled in this firmware, or they
  share a region with another feature (e.g., DTMF table).

**Recommendation:** if the radio actually supports 2-tone / 5-tone
encoding (per CPS UI), check whether these tone settings appear as
extensions in the DTMF Encode Table region (`0x4471 + 16×128 = 0x4C71`)
or elsewhere. May also be CPS-only metadata that the radio firmware
doesn't read.

### 9. Emergency Alarm encoding at 0x29AC — local/remote enum unknown.

**Status: cannot answer from firmware. Address note: `0x29AC` is
"Priority Scan Channel" per settings.md, not Emergency Alarm.**

Emergency-related settings actually live at:
- `0x299D` bit 1 — Emergency Alarm **type** (clear=Remote, set=Local) ✓
- `0x29AE` — Emergency key short-press function (Key Define enum)
- `0x29AF` — Emergency key long-press function
- `0x2990` — Alarm TX Time (`value/2` seconds)
- `0x2991` — Alarm Idle Time (`value-5` seconds)

The doc's clear=Remote / set=Local for `0x299D` bit 1 is marked "✓"
which means it IS verified by diff session. So this question may
already be answered (the open question text might be about the
*0x29AC* address by typo).

If the question is really about `0x29AC` (Priority Scan Channel):
that's clearly documented (`0x00`=CH1, `0x02`=CH3 confirmed by diff).

If it's really about Emergency Alarm: encoding is at `0x299D` bit 1
and is verified.

No firmware-side help either way; both are CPS-protocol-side bytes
not directly accessed by code as bare constants.

---

## What the firmware analysis DID resolve (not in the open questions list)

These are doc-improvements that DID flow from firmware analysis:

- **Key Define unknowns 0x0D and 0x0F**: filled in as Stun and TX-DSW
  (from menu pointer table segment 4 indexing).
- **Long-press extras enum values**: M-MONI=0x10, Tx1000-2100=0x11..0x14
  (alias for Analog Monitor / 1000-2100Hz).
- **Encryption Type 5-cipher list**: Normal / Enhanced / ARC4 / AES128
  / AES256 (from menu pointer table segment 0).
- **DMR Mode 3-value enum**: Simplex / Repeater / Double Slot.
- **Tx Authority firmware naming**: Forbid / Impolite / Polite to CC /
  Polite to All.
- **Power 4-value enum**: Low / Middle / High / Extra low.
- **CTCSS/DCS supported lists** (31 + 103 entries) — used to validate
  channel tone bytes are in the radio's supported set.
- **IARU region presets**: 3 region tables in firmware match the
  observed band-limit data exactly.
- **Step Forbid option**: confirmed `Forbid` is a valid enum value.
- **Slot 1 / Slot 2 spelling**: firmware uses spaces, CSV uses none.
- **`Encrypt NO` Chinese label = `加密组别`**: 4-bit key index meaning
  confirmed by debug printf `加密组别 NN: 算法：%x`.

All of these are now in `pylunce/docs/` (and ready to sync to
`pylunce2/`).

---

## What the Ghidra disassembly opens up (not yet acted on)

The 4,333-function disassembled project at
`v32_ghidra/v32_proj.gpr` enables interactive workflow:

1. Open in Ghidra GUI: `ghidraRun v32_ghidra/v32_proj.gpr`
2. Find the b1=0x0F protocol read handler — likely loads from RAM
   buffer at known offsets after a block-read.
3. Trace where the buffer contents get applied to hardware /
   menu state. That's the path to mapping every settings byte to
   its code-side use.

This is the next-level workflow that would resolve many of the
unmapped-bytes questions without needing diff sessions for each.
