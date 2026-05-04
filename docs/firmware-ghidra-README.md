# HD2 firmware — Ghidra import kit

Self-contained package to reproduce the current HD2 reverse-engineering state
in Ghidra on any machine.

Firmware platform: **Ailunce HD2** DMR radio, C-SKY V2 MCU, 32-bit LE.

## Contents

| file | purpose |
|---|---|
| `v207.perword.bin` | Decrypted firmware HD-HD2PA-C7000-V2.0.7 (non-GPS), 585 KB |
| `v208.perword.bin` | Decrypted firmware HD-GPS-HD2PA-C7000-V2.0.8-GPS, 592 KB |
| `v213.perword.bin` | Decrypted firmware HD-GPS-HD2PA-C7000-V2.1.3-GPS, 592 KB |
| `v{207,208,213}.keybits.bin` | Packed per-word N/S key bitmaps (for reproducibility; not needed for Ghidra) |
| `metadata.txt` | 413 annotations (IARU band tables, module markers, menu text, etc.) |
| `metadata_menu.txt` | 313 menu-item string offsets (Main Set / Band Set / Radio ID / etc.) |
| `metadata_hal.txt` | Segment boundaries + known HAL helper / shutdown-handler labels |
| `metadata_dmr_fns_broad.txt` | DMR sync/frame printf function refs |
| `ghidra_setup_memory.py` | Ghidra script — configures memory + disassembles both code segments |
| `ghidra_apply_metadata.py` | Ghidra script — applies all metadata as labels + comments |

Tested with **Ghidra 12.0.4 public**.

## Memory map (decrypted firmware)

```
0x00000 ─┬─ SEG_A_START   application code
         │                 (4159 functions detected)
0x5FFFF ─┴─ SEG_A_END
0x60000 ─┬─ RODATA_START  strings, pointer tables, rodata
         │                 (menu text, IARU band table, uC/OS library strings,
         │                  libjpeg strings, DMR sync labels, etc.)
0x6FFFF ─┴─ RODATA_END
0x70000 ─┬─ SEG_B_START   HAL / peripheral layer
         │                 (588 functions; mostly <32B MMIO primitives)
0x93FFF ─┴─ SEG_B_END     (v208 file ends just past 0x940E0)
```

### Aliased bases (same bytes, different addresses)

Code pointers in this firmware use three base addresses that all refer to the
same flash bytes:

- **0x00000000** — the import base (flash view, what Ghidra sees)
- **0x03000000** — the execute base (0x03000000 + offset == code at offset)
- **0x05620000** — the RAM-mirror base (code copied / aliased to SRAM)

An `lrw r0, 0x0307a594` in a function means *code at file offset 0x7a594*.
Ghidra will create cross-memory references automatically; you don't need
separate overlay blocks.

## Quickstart — import + configure

1. **Launch Ghidra 12.0.4**. Create or open a project.
2. **File → Import File** → pick `v208.perword.bin` (recommended primary target).
3. In the import dialog:
   - **Format**: Raw Binary
   - **Language**: click the ellipsis, type `csky`, pick **`CSKY_V2:LE:32:default`**
     (processor *C-SKY*, variant *CSKY_V2*, endian *little*, size *32*, compiler *default*)
   - **Options → Base Address**: `0x00000000`
   - Accept import. When asked whether to analyze, click **No** — we'll do it via script.
4. **Copy the two Ghidra scripts** into your Ghidra scripts directory:
   - Linux/Mac: `~/ghidra_scripts/`
   - Windows: `%USERPROFILE%\ghidra_scripts\`

   (Or, from **Window → Script Manager**, click the red **+** at the top and add this
   directory to the script search path.)
5. Keep `metadata*.txt` files alongside `ghidra_apply_metadata.py` (same directory).

## Run the scripts

**Window → Script Manager**, expand the **HD2** category.

### Step 1 — `ghidra_setup_memory.py`

Configures the memory block as R+X, disassembles Segment A and Segment B,
seeds a handful of known function entry points (shutdown handler, hot HAL
helpers), then runs auto-analysis. Expected runtime: 2–5 minutes.

After this completes you should see roughly:
- ~4,900 functions in the Function List
- ~494 KB of bytes disassembled (81% of the 606 KB file)

### Step 2 — `ghidra_apply_metadata.py`

Applies every annotation from `metadata*.txt` matching the firmware version
(auto-detected from the program name, or prompted). Applies:
- A **label** at each offset (browsable via Window → Symbol Tree)
- An **EOL comment** with the free-text note
- String data type for string-prefixed labels (`str_`, `menu_`, `m_`, etc.)

Expected: 200–400 labels, 200–400 comments, 50–150 ASCII strings defined.

## Navigating the result

Press **G** to jump to a label. High-value targets:

| label | what it opens |
|---|---|
| `SEG_B_START` | Start of the HAL / peripheral layer |
| `fn_shutdown_main` | Shutdown handler (3 entries at 0x0482c4/0x0482d0/0x0482dc) |
| `hal_hot_helper_D` | Most-called HAL primitive (67 refs, 24B body) |
| `m_BandSet_Vox` | Menu string with 23 xrefs — every caller is a menu handler |
| `menu_MainSet` | "Main Set" top-level menu header |
| `mod_dmr_sync_printf` | Boot-time DMR sync-word init reference site |
| `IARU_R1_RxA` | First entry of the IARU band-limit BCD table |

### Finding menu handlers

1. Go to `m_BandSet_Vox` (`G`, type `m_BandSet_Vox`, Enter).
2. Right-click → **References → Show References to Address**.
3. Each reference is a different function that loads this string — follow them
   to locate the menu-handler functions.

### Exploring segment B (the HAL)

The hot helpers at 0x071cb8–0x071d88 are probably peripheral register
read/write/bit-op primitives. Their callers (in segment A) are the higher-level
drivers. Suggested workflow:

1. Jump to `hal_hot_helper_D` (0x071d88).
2. Decompile (Ctrl-E) — expect 1–3 lines of `*(int*)ptr = val` or similar MMIO.
3. Right-click → **References → Show References to This Function** — the
   callers are driver-level code that uses this primitive.

## Known facts / dead ends (don't re-investigate)

- **`mod_libjpeg_errors` is dead rodata**. Zero code xrefs in any firmware.
  libjpeg strings survived as linker garbage; the functions were stripped.
- **`mod_ucosiii` task names are dead rodata**. Even with both code segments
  disassembled, zero code loads `uC/OS-III Idle Task` / `Tick Task` / etc.
  The RTOS kernel itself is not in this flash image (either MCU mask ROM, a
  separate partition, or a custom RTOS that happens to include uC/OS-III
  string labels from a HAL port).
- **No "Powering Down" three-liner** — it's just "Powering" / "Down", 2 lines.
- **Display is 160x128 TFT**, not a 2-line LCD. The inter-string marker
  `\x88\x88\x88\xf8` is string-table padding (0xFF flash-erased bytes XORed
  with the N key), not a line-break character.

## Cross-firmware notes

- **v207 is non-GPS**; v208 and v213 are GPS variants.
- v208 and v213 share ~62% of code byte-identically; top 38% of each file is
  the byte-identical shared bootloader/library region.
- **v209 is identical to v208** (same hash); no separate build exists.
- 326 canonical string clusters were cross-validated across all three; strings
  decrypt consistently in all versions.

## Decryption reproducibility

The `.keybits.bin` files are packed per-word N/S bitmaps (1 bit per 4-byte word
of the raw encrypted firmware). Used with keys:
```
KEY_N = [0x77, 0x77, 0x77, 0x07]
KEY_S = [0x11, 0x11, 0x11, 0x01]
DIFF  = KEY_N XOR KEY_S = [0x66, 0x66, 0x66, 0x06] = 0x06666666
```
Decryption is XOR per 4-byte word, choosing KEY_N or KEY_S based on the bitmap bit.
You don't need these to use the `.perword.bin` files — they're included only for
reproducing / extending the decryption work from scratch.

## Coverage snapshot (as of export)

| metric | v208 |
|---|---|
| File size | 606,432 B (592 KB) |
| Disassembled | 494 KB (81%) |
| In recognized function bodies | 85 KB (14%) |
| In meaningful functions (≥32B) | 41 KB (7%) |
| Total functions | 4,936 |
| Meaningful functions (≥32B) | 730 |
| Seg A functions | 4,159 |
| Seg B functions | 588 |
| Functions with ≥1 xref | 83% |
| Semantically labeled | ~3% (141 functions named) |
