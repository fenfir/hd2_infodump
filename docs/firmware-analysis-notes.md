# HD2 Firmware Analysis Notes (v208 primary target)

## 0. macOS disassembly toolchain (2026-05-12)

CSKY V2 disassembly on macOS works via an in-tree
`binutils-gdb` build (target `csky-elfabiv2`):

```
binutils-gdb/binutils/objdump -b binary -m csky:ck803 -EL \
    --adjust-vma=0x03000000 <plaintext.bin>
```

Brew's stock `objdump` decodes CSKY but does **not** combine 32-bit
halfword pairs correctly — use the in-tree build for any analysis
that depends on full-width instruction decoding (e.g. the
integrity-check function `FUN_0304d564` at `0x0304d564..0x0304d830`,
documented in [fw_update](fw_update) "Integrity-check fall-through
patch").

## 1. KEY-SWAP BUGS — Confirmed bitmap errors

The perword decryption uses a 1-bit/word bitmap to select KEY_N vs KEY_S.
Some words in pointer tables were decoded with the wrong key, producing
0x0562xxxx (RAM-mirror base) instead of 0x030xxxxx (code execution base).

### 1A. Dispatch table #1 — "Private Call / DMR service" table
**Region: 0x06f2b4..0x06f4d8** (mixed code pointers + key-swap errors)

This is a function-pointer dispatch table with ~150 entries. Most point to
the 0x049xxx code range. The default no-op handler is at 0x0490ac.

| Offset | Current (wrong) | Corrected | Target fn | Key bit |
|--------|----------------|-----------|-----------|---------|
| 0x06f2b4 | 0x0562f460 | 0x03049206 | fn_049206 | 0→1 |
| 0x06f2d8 | 0x0562f6ca | 0x030490ac | default   | 0→1 |
| 0x06f2e0 | 0x0562f6ca | 0x030490ac | default   | 0→1 |
| 0x06f2e8 | 0x0562f6ca | 0x030490ac | default   | 0→1 |
| 0x06f328 | 0x0562f75a | 0x0304913c | fn_04913c | 0→1 |
| 0x06f32c | 0x0562f6ca | 0x030490ac | default   | 0→1 |
| 0x06f420 | 0x0562f6ca | 0x030490ac | default   | 0→1 |
| 0x06f438 | 0x0562f786 | 0x030491e0 | fn_0491e0 | 1→0 |
| 0x06f468 | 0x0562f49a | 0x030492fc | fn_0492fc | 0→1 |
| 0x06f470 | 0x0562f48c | 0x030492ea | fn_0492ea | 0→1 |
| 0x06f490 | 0x0562f5e8 | 0x0304938e | fn_04938e | 0→1 |
| 0x06f494 | 0x0562f226 | 0x03049440 | fn_049440 | 0→1 |
| 0x06f4a0 | 0x0562f5e8 | 0x0304938e | fn_04938e | 1→0 |
| 0x06f4ac | 0x0562f5e8 | 0x0304938e | fn_04938e | 1→0 |
| 0x06f4d8 | 0x0562f5e8 | 0x0304938e | fn_04938e | 1→0 |

Note: Most need bit 0→1 (KEY_N→KEY_S), but 4 need bit 1→0.

### 1B. GPS / Channel settings table
**Region: 0x06f880..0x06f9cc** (~80 function pointers)

Points to handlers in the 0x04cxxx–0x04fxxx range. ~25 entries need key swaps.
Key targets: fn_04ce24 (default), fn_04ce8e, fn_04cea2, fn_04cee0, fn_04d2ee,
fn_04f208, fn_04f26a, fn_04f288, fn_04f22c.

### 1C. Band/channel settings dispatch table
**Region: 0x06d750..0x06d808** (~28 entries)

Points to handlers in 0x039b32–0x03ca20. ~22 entries are wrong-key.
Targets: fn_039b32 (default), fn_039ba0, fn_03af38, fn_03bd80,
fn_03bcb6, fn_03bd0c, fn_03c082..fn_03ca20.

### 1D. Bottom dispatch table (main menu handlers)
**Region: 0x06fb38..0x06fc54**

3 key-swap errors at the start, then correctly-decoded 0x04axxx–0x04cxx
function pointers (display/UI handlers).

### 1E. JPEG decoder dispatch table
**Region: 0x066620..0x066b30** (~53 entries)

Points to JPEG/image processing functions in 0x013d9a–0x01aa44 range.
This is NOT in the libjpeg error string region — it's a separate function
dispatch table for the JPEG codec. ~53 entries need key swaps.
Targets: fn_013d9a (dominant), fn_013db0, fn_014858, fn_014912, fn_01518a, fn_0161a0, fn_01aa44, etc.

### 1F. libjpeg/string format dispatch
**Region: 0x0672ec..0x0675c8** (~12 entries)

Points to string-format / libjpeg functions in 0x027bb0–0x02c1d8 range.

### 1G. Shutdown struct (ALREADY FIXED)
0x06f184..0x06f18c: Three code pointers that were previously identified and
corrected. Current values are correct (0x030482dc, 0x030482d0, 0x030482c4).

## 2. COMPLETE FUNCTIONS — Analysis

### 2A. Shutdown handler (0x0482c4)
- 3 entry points: 0x0482c4 (main), 0x0482d0 (skip r3 test), 0x0482dc (skip more)
- ~72 bytes, C-SKY V2 code
- Allocates 96 bytes of stack
- Referenced from "Powering"/"Down" splash string struct at 0x06f170
- **Purpose**: Radio power-down sequence — displays "Powering" then "Down" on the 160x128 TFT, then executes hardware shutdown via HAL callbacks

### 2B. HAL hot helpers (Segment B)

**hal_hot_helper_A** @ 0x071cb8 (20B, 43 refs)
- MMIO read primitive: loads from a computed peripheral address, returns value

**hal_hot_helper_B** @ 0x071cc8 (6B, 58 refs)
- Tightest wrapper (6 bytes): `ldw r0, (r0); jmp r15` — single register indirection
- Reads a 32-bit value from the address in r0 and returns it
- **Purpose**: `uint32_t mmio_read32(uint32_t *addr)`

**hal_hot_helper_C** @ 0x071d58 (28B, 42 refs)
- MMIO read with offset computation: computes addr+constant, reads, returns
- Slightly longer due to offset addition

**hal_hot_helper_D** @ 0x071d88 (24B, 67 refs)
- Most-called seg-B function. MMIO write primitive.
- Takes address and value, stores value to computed peripheral address
- **Purpose**: `void mmio_write32(uint32_t *addr, uint32_t val)`

### 2C. Largest Segment B functions

**fn_08d2d4** (218B, LARGEST seg-B function)
- No obvious 0x0562xxxx suspects in its body
- Appears to be a complex peripheral initialization sequence
- Multiple subroutine calls (e9xx = jsri or bsri patterns)
- Likely an I2C or SPI transfer function (multiple register reads/writes)

**fn_072a38** (168B, 2nd largest)
- Contains a loop structure (branch-back patterns visible)
- Calls helper functions
- Likely a flash read/write routine (JEDEC SPI operations)

**fn_080675** (161B)
- Register-heavy operations with computed addresses
- Possible DMA configuration function

### 2D. Dispatch table target functions

**fn_0490ac** (default handler, ~70 references from dispatch table)
- ~64 bytes of code
- Appears to be a "no-op" or "return without action" stub
- Used for unimplemented/unused dispatch slots

**fn_04938e** (2nd most referenced, ~16 refs)
- Active handler with string references
- Likely displays a menu item or sets a channel parameter

## 3. STRUCTURAL FINDINGS

### 3A. Multiple function pointer tables discovered

| Region | Size | Target range | Likely purpose |
|--------|------|-------------|----------------|
| 0x06f2b4..0x06f4d8 | ~150 entries | 0x049xxx | DMR call-type / channel dispatch |
| 0x06f880..0x06f9cc | ~80 entries | 0x04cxxx–0x04fxxx | GPS/rxGPS/txGPS handlers |
| 0x06fb7c..0x06fc54 | ~40 entries | 0x04axxx–0x04cxx | Main menu item handlers |
| 0x06d750..0x06d808 | ~28 entries | 0x039xxx–0x03cxxx | Band/channel settings handlers |
| 0x066620..0x066b30 | ~53 entries | 0x013d9a–0x01aa44 | JPEG codec dispatch |
| 0x0672ec..0x0675c8 | ~12 entries | 0x027bb0–0x02c1d8 | libjpeg format functions |

### 3B. v213 cross-validation

v213 has the same dispatch tables at slightly different offsets (rodata is shifted
by ~0xa8 bytes). v213 has its own set of key-swap errors in the equivalent tables,
but different specific words are affected. The same pattern holds: 0x0562fxxx values
that should be 0x030xxxxx.

### 3C. Total suspected key-swap errors (v208, rodata only)

- Dispatch table #1: 15 confirmed
- GPS table: ~25 confirmed
- Band settings: ~22 confirmed
- Bottom table: 3 confirmed
- JPEG table: ~53 confirmed
- libjpeg dispatch: ~12 confirmed
- Other scattered: ~59 entries (some may be coincidental data)
- **Total: ~189 words in rodata with 0x0562xxxx values**

Not all 189 are necessarily pointer-table errors — some may be data that
coincidentally falls in the 0x0562xxxx range. But the ~130 in identified
pointer tables are confirmed with high confidence.

### 3D. Code region suspects

SEG_A has 54 words with 0x0562xxxx values (literal pool entries in code).
SEG_B has 24 words with 0x0562xxxx values. These are embedded in instruction
literal pools and should be reviewed individually.

## 4. KEY PATTERN

The key-swap bug manifests as: encrypted word decoded with KEY_N produces
0x0562xxxx instead of the correct 0x030xxxxx (or vice versa). The XOR
difference between these bases is exactly 0x06666666 (= KEY_N XOR KEY_S).

For any 0x0562xxxx value in a known pointer table, the correct value is:
```
correct = suspect ^ 0x06666666
```

In the keybits bitmap, the affected word needs its bit flipped:
- If currently bit=0 (KEY_N was used): flip to bit=1 (use KEY_S)
- If currently bit=1 (KEY_S was used): flip to bit=0 (use KEY_N)

Most errors are bit=0→1 (should have used KEY_S but KEY_N was selected).
