# Codeplug address space

`hd1_dump.py` walks 8 regions, packing the payloads into a single `.bin`
in the order below. The "Family" column refers to the read protocol family
documented in [`protocol.md`](protocol.md).

## Region table

| Region        | Radio addr            | Family | Chunk  | Stride          | Length        | Notes |
|---------------|-----------------------|--------|--------|-----------------|---------------|-------|
| `header`      | `0x0000..0x0180`      | 0x0F   | 128 B  | 128 (byte addr) | 0x00200       | DMR IDs |
| `vfo_config`  | `0x2000..0x2300`      | 0x0F   | 128 B  | 128 (byte addr) | 0x00380       | VFO-A/B + dual channel-presence bitmap |
| `settings`    | `0x2900..0x5F00`      | 0x0F   | 128 B  | 128 (byte addr) | 0x03680       | Radio settings + Radio IDs |
| `addr_book`   | `0x0000` (b1=0x31)    | 0x31   | 1024 B | 1 (block index) | 0x00400       | 14 × 72-byte address-book contacts |
| `channels`    | `0x1B84..0x1DCF`      | 0x31   | 1024 B | 1 (block index) | 0x93000       | Priority contacts + channel slots |
| `table_1dfx`  | `0x1DF8..0x1E03`      | 0x31   | 1024 B | 1 (block index) | 0x03000       | (purpose unknown — mostly 0xFF) |
| `table_21dx`  | `0x21D8..0x22FF`      | 0x31   | 1024 B | 1 (block index) | 0x4A000       | RX Group Aliases + Zones |
| `table_4000`  | `0x4000` (b1=0x31)    | 0x31   | 1024 B | 1 (block index) | 0x00400       | (purpose unknown beyond Radio IDs) |
| `table_428x`  | `0x4280..0x4282`      | 0x31   | 1024 B | 1 (block index) | 0x00C00       | (purpose unknown) |

Total: 8 regions, 0xE5000 / 938,000 bytes packed.

> The CPS pcap (`hd2_read.pcapng`) shows only 7 regions — the `addr_book`
> b1=0x31 read at block 0x0000 was added later after observing CPS write
> traffic. Earlier versions of `hd1_dump.py` produced ~715,776-byte bins
> (without `addr_book`, with `settings` ending at 0x5B00, and with
> `table_21dx` ending at 0x2227); `codeplug.py` recognises both the
> `MEDIUM_SIZE` and `LEGACY_SIZE` layouts for backwards compatibility.

## Ordering in the packed `.bin`

`hd1_dump.py` concatenates the payloads in the order above with no gaps:

| File offset | Radio region          | Length    |
|-------------|-----------------------|-----------|
| `0x000000`  | `header`              | `0x00200` |
| `0x000200`  | `vfo_config`          | `0x00380` |
| `0x000580`  | `settings`            | `0x03680` |
| `0x003C00`  | `addr_book`           | `0x00400` |
| `0x004000`  | `channels`            | `0x93000` |
| `0x097000`  | `table_1dfx`          | `0x03000` |
| `0x09A000`  | `table_21dx`          | `0x4A000` |
| `0x0E4000`  | `table_4000`          | `0x00400` |
| `0x0E4400`  | `table_428x`          | `0x00C00` |
| *total*     |                       | `0xE5000` |

`codeplug.py` exports the same table as the `REGIONS` constant and
exposes `radio_to_file(name, radio_addr)` for converting between the two
address spaces.

## Channel-presence dual bitmap @ file `0x0200..0x04ED`

A **750-byte region** in `vfo_config` containing TWO IDENTICAL 375-byte
bitmaps (a primary + parity copy). One bit per channel slot, **bit set =
slot empty, bit clear = slot populated**. 375 × 8 = 3000 bits = 3000 max
channels.

Layout:

| File offset       | Size   | Purpose                       |
|-------------------|--------|-------------------------------|
| `0x0200..0x0376`  | 375 B  | bm1 — primary bitmap          |
| `0x0377..0x04ED`  | 375 B  | bm2 — duplicate (parity copy) |

`bm1[i]` always equals `bm2[i]`. Mismatch is treated as anti-tamper and
triggers self-destruct (see "Kill state" below). Within a byte, bit 0 =
lowest-numbered channel of that group of 8.

### vfo_config layout

The `vfo_config` region is 896 bytes (file `0x0200..0x057F`). Only the
first 750 bytes are decoded:

| File offset | Size | Purpose |
|-------------|------|---------|
| `0x0200..0x0376` | 375 B | bm1 — primary channel-presence bitmap |
| `0x0377..0x04ED` | 375 B | bm2 — duplicate (parity copy) |
| `0x04EF..0x057F` | 145 B | **Unknown** — possibly channel metadata or unused |

The 145 trailing bytes (`0x04EF..0x057F`) have not been decoded. They do
not appear to contain VFO-A/B records (those live in the `header` region
at file `0x0090` and `0x0140`).

Confirmed across all dumps:

| State                 | bm1[4] / bm2[4] | Populated chans | Notes |
|-----------------------|-----------------|-----------------|-------|
| factory (never CPS)   | `0xFF` / `0xFF` | (auto)          | bitmap not yet written |
| 37 chans (cp_e0both)  | `0xE0` / `0xE0` | 37              | bits 5,6,7 set → chans 37,38,39 empty |
| 38 chans (cp_clean_*) | `0xC0` / `0xC0` | 38              | bits 6,7 set → chans 38,39 empty |
| 3000 chans (writemax) | `0x00` / `0x00` | 3000            | all bits clear |

The "manifest bytes" formerly described at `0x0204` and `0x037B` are
just `bm1[4]` and `bm2[4]` — the byte covering channels 32..39.
`0x037B - 0x0377 = 4 = 0x0204 - 0x0200`, confirming dual-bitmap layout.

The CPS writes the entire bitmap region near the start of a full upload
(writes #19 and #23 of ~150 push the first 128B of bm1 and bm2). Surgical
writes that add channel slots without updating both bitmaps leave the new
slots **invisible** to the radio — the bitmap still says "empty".

### Bitmap-vs-slot consistency check (anti-tamper)

The firmware enforces consistency between the bitmap and actual slot data
on each boot. **Bit clear (populated) MUST correspond to a valid channel
record at that slot.** Mismatch → kill state.

Confirmed by experiment: starting from a 3000-channel CPS upload (all
3000 slots valid + bitmap = all 0x00), flipping `bm1[5..374]` and
`bm2[5..374]` to `0xFF` (claiming chans 40-2999 empty) while leaving the
slot data intact → kill on next boot.

This is why a "surgical" reduction in visible channel count requires
either:
- Wiping the slot markers for the now-hidden range (slow), OR
- Only ever flipping bits to "populated" while writing real slot data.

### Surgical channel injection recipe

To make slot N (0-indexed) visible:

1. Write a complete, valid channel record into slot N (marker `0xFFFFFFFF`,
   name, freqs, etc.) at the correct location in the channels region.
2. Clear bit `(N % 8)` in **both** `bm1[N // 8]` and `bm2[N // 8]`.
3. Issue both 128 B writes that contain the modified bitmap bytes.
4. Power-cycle.

## Kill state (anti-tamper self-destruct)

If the two manifest bytes disagree (e.g. one is changed by a surgical
write and the other isn't), or if either is set to a value the firmware
considers invalid, the radio enters a **purple "Radio State / Killed"**
screen on next boot.

The kill action **wipes flash regions on the radio side**:

- `file 0x0377..0x037B` (5 B) — the partner manifest byte and a few
  bytes ahead of it.
- `file 0x05D0..0x062F` (96 B) — the password / model-string area
  (`123456123456HDHD1A...` config block at radio `0x2950..0x29B0`).

Recovery requires writing back **both** the manifest pair AND the wiped
config region in the same session, before the radio reboots again. Until
then the radio displays the kill screen but still accepts USB writes.

To stay alive when modifying the manifest:

1. Compute the new value.
2. Write `radio 0x2000` (128 B) **and** `radio 0x2100` (128 B) in the
   same session, with both bytes set to the same value.
3. Power-cycle.

### Surgical recovery (no CPS needed)

The radio still accepts USB writes while in kill state. Recovery procedure:

1. Dump current `vfo_config` to see bitmap state.
2. Build a recovery bitmap that **agrees with actual slot data** in flash
   (e.g. if all 3000 slots are valid, bitmap = all `0x00`).
3. Write the affected vfo_config blocks (radio `0x2000`, `0x2080`, `0x2100`,
   `0x2180`, `0x2200`, `0x2280` — 6 × 128 B).
4. Restore the config block by writing settings blocks `0x2900` and `0x2980`
   from a known-good baseline (e.g. `samples/cp_factory.bin`).
5. Power-cycle.

Total: 8 × 128 B writes (~1 sec). See `fix_bitmap.py`.
