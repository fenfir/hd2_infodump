# HD2 v208 firmware — full analysis summary (May 2026)

Canonical firmware image: **`v208.perword.v32.bin`** (606,432 bytes / 0x940e0).

This document distills every structural finding from the firmware-recovery
session(s) into a single reference. For corruption recovery details see
`project_string_corruption_audit.md` in memory; for the in-depth menu
architecture see `v32_dispatcher_architecture.md`; for chip-level memory
map see `c7000_reference.md`.

---

## 1. Memory layout

Firmware load base: **`0x0300d000`** (LCSFC flash region, see HR_C7000 §4.5.3).

| Range (file)       | Size   | VA range                  | Type           | What's there |
|--------------------|-------:|---------------------------|----------------|---------------|
| `0x00000-0x36000`  | 224 KB | `0x0300d000-0x03043000`   | Code (low)     | App code, vector table, init |
| `0x36000-0x60000`  | 168 KB | `0x03043000-0x0306d000`   | Data/code mix  | Pointer tables + interleaved code |
| `0x60000-0x80000`  | 128 KB | `0x0306d000-0x0308d000`   | Rodata         | Strings, menu pool, lookup tables |
| `0x80000-0x94000`  |  80 KB | `0x0308d000-0x030a1000`   | Code (high)    | DSP / signal processing inner loops |

Padding pattern: `0xf8888888` (a.k.a. `··········` in hex dumps) marks
unused 4-byte slots throughout.

---

## 2. String corruption recovery — done

The firmware uses a per-word XOR encryption: clean 4-byte word `W` becomes
ciphertext `W ⊕ K`, where `K ∈ {KEY_N=0x07777777, KEY_S=0x01111111}` is
chosen by a bitmap. **DIFF** = `KEY_N ⊕ KEY_S = 0x06666606` is the flip
mask used to correct words assigned the wrong key.

Recovery progressed v3 → v17 → v22 → v25 → v27 → v31 → **v32** through
~89 manual flips on top of bulk pattern-sweep + GPU subset search +
cross-firmware crib alignment + GB2312 vocabulary recovery.

**Final canonical-signature sweep (May 4): 0 candidates.** Every standard
0x66/0x66/0x66/0x06 corruption pattern in string context is fixed.

**Notable late-session flips:**

| Offset      | Before     | After      | Recovered                                  |
|-------------|------------|------------|---------------------------------------------|
| `0x06d9a8`  | `WVVK`     | `100M`     | `100Ms` timer label                         |
| `0x06de2c`  | `52'T`     | `STAR`     | `START` (GPS event)                         |
| `0x068504`  | `HCV4`     | `.%02`     | `version %d.%02d` (libjpeg JFIF)            |
| `0x068518`  | `FFCb`     | `  %d`     | `density %dx%d  %d` (libjpeg)               |
| `0x071018`  | `FTFK`     | ` 2 M`     | `LEAPYEAR 2 Month` (date validator)         |
| `0x071020`  | `FT_&`     | ` 29 `     | `29 Day Error`                              |
| `0x071124`  | `56/6`     | `SPI0`     | `SPI0 RX : %d.`                             |
| `0x07113c`  | `56/7`     | `SPI1`     | `SPI1 RX : %d.`                             |
| `0x071334`  | `'"%Y`     | `ADC_`     | `ADC_CONTROL: %x.`                          |
| `0x06f704+` | (26 words) | —          | **IARU region table** (3 regions + `654321` password) |

---

## 3. Subsystem inventory

### 3.1 Menu / UI

**Menu pointer table** at rodata `0x06df00..0x06e500`:
**10 segments / 219 entries** with two layout conventions (post-fix +
pre-fix). Segment 9 is the Chinese-language parallel table (79 items,
70 GB2312 + 9 untranslated).

Handlers live at SRAM addresses `0x055xxxxx..0x0567xxxxx` — see
[§5 Dispatcher findings](#5-menu-dispatcher-architecture-final).

**Menu pool strings** at `0x06c000..0x07200a`: ~1500 ASCII + ~350 GB2312
with full English/Chinese cross-reference. Two distinct Chinese terms
for "Contacts" (联系人 = priority list, 通信录 = address book) match
the codeplug's two contact tables.

### 3.2 Tone tables (radio's full supported tone set)

**CTCSS** at `0x06da3c..0x06daa8` — 31 frequencies, 4-byte stride
(2 BCD-LE × 0.1 Hz tones per word):

```
62.5 67.0 69.3 71.9 74.4 77.0 79.7 82.5 85.4 88.5 91.5 94.8
103.3 117.5 127.5 137.2 145.6 152.2 161.4 166.6 173.8 177.3
199.5 203.5 206.5 210.7 218.1 225.7 229.1 233.6 236.5
```

**DCS** at `0x06daa8..0x06db78` — 103 octal codes, 2-byte BCD-LE:

```
023 025 026 031 032 036 043 047 051 053 054 065 071 072 073 074
114 115 116 122 125 131 132 134 152 155 156 162 165 172 174
205 212 223 225 226 243 244 245 246 251 252 255 261 263 265 266 271 274
306 311 315 325 331 332 343 346 351 356 364 365 371
411 412 413 423 431 432 445 446 452 454 455 462 464 465 466
503 506 516 523 526 532 546 565
606 612 624 627 631 632 645 654 662 664
703 712 723 731 732 734 743
```

Cross-firmware: v207 has CTCSS at `0x06bf2c`, v213 at `0x06dadc`.

### 3.3 IARU region presets

**Band-limit table** at `0x06f704..0x06f7e0` — 3 regions × VHF/UHF TX/RX
ranges, exactly matching `settings.md`'s observed values:

```
IARU1   TX:144-146,430-440        RX:136-174,400-480
IARU2   TX:144-148,222-225,420-450  RX:136-225,400-480   (Region 2 includes 1.25m amateur band)
IARU3   TX:144-148,430-440         RX:136-174,400-480
```

**IARU password / UI** at `0x06f79c..0x06f7e0`:
- `654321` — region selector password (`MENU+6` cold-boot, per manual)
- `777888` — additional factory code (purpose unknown)
- `Select / New Band`, `Input / New Band`, `OK` — UI prompts
- `VHF Tx Low/High`, `UHF Tx Low/High`, `VHF Rx Low/High`, `UHF Rx Low/High` — band-edit field labels

### 3.4 RF / hardware register debug pool

**At `0x070700..0x071400`** — 40+ printf-format strings naming chip
registers and tune-data fields. Reveals hardware architecture:

- `g_tune_data_struct` fields: `VolumeDMR/FMW/FMN`, `u18Brightness[0..9]`,
  `u8QTSampleNormal`
- Flash chip: `JEDEC_ID[0..2]`, `b1FlashIC512M`
- I²C2 bus (ties to `c7000_reference.md` `0x14080000`):
  `IC_FS_SCL_HCNT/LCNT`, `IC_CON`, `IC_TX_TL`, `IC_RX_TL`, `IC_INTR_MASK`,
  `i2c2 timeout`
- SPI: `SPI0 RX : %d.`, `SPI1 RX : %d.`
- Audio path: `u16AF_BIAS_OUTVALUE`
- RF chip control: `ADC_CONTROL`, `DAC_CONTROL`, `RX_IF_FREQ`
- DMR sync: `*SEND_DATA_SYNC_H/L`, `*SEND_RC_SYNC_H/L`,
  `*RECV_MS_SYNC_H/L`, `*RECV_BS_SYNC_H/L`, `*RECV_TDMA1/TDMA2_SYNC_H/L`,
  `*RECV_RC_SYNC_H/L`
- Slot tracking: `@rxslot: %d, txslot: %d`
- Priority scan: `b1PriScan: %d.`, `u16PriScanChannel: %d.`
- Key define: `u8KeyPF3_S/L: %d.`

### 3.5 DMR protocol layer

**Burst-type identifiers** at `0x071700..0x071780`:

```
piheader:     csbk:           csbk: (variant)
terminator:   slot: %x,       rxtypeinfo: %x,
voiceheader:  error.          laterentry:
mbc header:   mbc contin:
```

**Control-plane messages** at `0x071180..0x0712d0`:

```
recv defined msg.    recv radioen.        recv radiodis.
recv radiocheck.     recv radioalarm.     recv callprompt.
recv callmon.        recv radioen ack.    recv radiodis ack.
```

These are standard DMR Tier 2 features: `radioen/radiodis` are
Stun/Kill, `radiocheck` is Radio Check, `radioalarm` is Emergency Alarm.

### 3.6 GPS subsystem

NMEA parser entry at `0x06de14`: `$GPGGA,` — radio parses the GGA
sentence (essential fix data).

Status events: `Satellite Lost`, `START`.

Coord display printf at `0x071ac8..0x071af0`:
```
longitude: %d.%d
latitude: %d.%d
callrx, shutdown, task init, "Radio is not activated"
```

### 3.7 RTC / date validation

At `0x070fec..0x071034`:

```
"year is Error"
"month is Error"
"LEAPYEAR 2 Month 29 Day Error"   (Feb 29 leap-year check)
"UID: %x.%x.%x.%x."               (chip serial number printf)
```

### 3.8 uC/OS-III tasks

Task name table at `0x06d94c..0x06da30`:

```
event / sem / timer / sysint / txslot / rxslot / rxcsbk / rxvoice
txmsg / rxmsg / decrypt / encrypt / 100Ms / 10Ms
Connected / BlueTooth / RTC / rfint / B Band Tx / A Band Tx
Temporary Call / CTCSS: / DCS: / No CTS/DCS
```

Confirmed kernel: μC/OS-III with `OS_CFG_DBG_EN > 0` (per the
`?MUTEX/?Q/?SEM/?TMR/?FLAG` object-name markers we recovered earlier).

### 3.9 libjpeg integration

85+ printf format strings at `0x065600..0x068a90` match upstream
`jerror.h` (`JTRC_*`, `JERR_*`, `JWRN_*` symbol families) byte-for-byte
after recovery. The radio uses libjpeg internally for splash-logo /
icon rendering — confirmed via:
- `JFIF APP0 marker: version %d.%02d, density %dx%d  %d`
- `Quantizing to %d = %d*%d*%d colors`
- `Component %d: %dhx%dv q=%d`

### 3.10 POSIX errno

At `0x065600..0x065e00` — ~25 standard `strerror()` strings (newlib
pattern). The radio has a full POSIX-compatible C library underneath
μC/OS-III. Network error messages (`Network is unreachable`,
`Connection refused`) appear despite no network — likely vestigial
from newlib defaults.

### 3.11 Encryption

5 cipher types, menu segment 0 at `0x06df4c`:

```
Off  Normal  Enhanced  ARC4  AES128  AES256
```

Storage:
- `Normal` keys: `0x3D00` (2 B BCD × 16 slots)
- `Enhanced` keys: `0x3E00` (16 B × 16 slots)
- `ARC4`: `0x5018+` slots 32–47 (49 B × 16)
- `AES128`: `0x5018+` slots 16–31
- `AES256`: `0x5018+` slots 0–15

Channel byte encoding: `+0x28` bits 6:5 = family (Off/Normal/Enhanced/AES);
when family = AES, `+0x11` bits 4:3 select variant (ARC4/AES128/AES256).
Key index in `+0x28` low nibble (radio menu label `Encrypt NO` /
加密组别). Confirmed via debug printf `加密组别 NN: 算法：%x`.

### 3.12 Boot / programmer protocol

At `0x06deac..0x06dee4`:

```
END  Activa  GetUID  GetVer
HD-GPS-HD2PA-C7000-V2.0.7-GPS.bin  ← embedded filename (V2.0.7 even in v208 firmware)
SLC7000  $,"T380  pc  ERROR  Complete
```

The version-string oddity (v208 firmware reports "V2.0.7-GPS.bin"
internally) suggests this filename string is a build-script artifact,
not a runtime version label. v213 firmware has `…-V2.1.3-GPS.bin` at
the equivalent offset.

---

## 4. Headless Ghidra disassembly results

Ran via `pyghidraRun -H` on v32 (CSKY_V2:LE:32:default, base 0x00000000).

| Metric                              | Value     |
|-------------------------------------|-----------|
| Functions identified                | **4,333** |
| Seg A (code low `0x00000-0x60000`)  | 3,550     |
| Seg B (code high `0x70000-0x94000`) | 708       |
| Other (mixed region)                | 75        |
| Named (annotated via metadata.txt)  | 30        |
| Labels applied                      | 272 / 279 |
| Comments added                      | 245       |
| String definitions                  | 204       |
| Auto-analysis time                  | 7 s       |
| Project path                        | `v32_ghidra/v32_proj.gpr` |

**Top 5 most-called functions:**

| Calls | Address      | Notes                                  |
|------:|--------------|----------------------------------------|
| 324   | `0x00027f58` | runtime helper (memcpy/strlen-like)    |
| 230   | `0x00029894` | runtime helper                          |
| 210   | `0x000298b0` | runtime helper                          |
| 103   | `0x000192a0` | utility                                 |
|  75   | `0x00071d88` | `hal_hot_helper_D` (timer-tick decrement) |

Output files:
- `v32_functions.txt` — all 4,333 functions with addresses, sizes, xref counts
- `v32_decompile_top.c` — Ghidra C decompile of top-20 named functions
- `v32_boot_trace.txt` — SRAM-pointer reference analysis
- `v32_dispatcher_callers.txt` — vtable-style code-region SRAM-pointer holders

---

## 5. Menu dispatcher architecture (final)

**The menu dispatcher does NOT live in this firmware.**

The 10 menu pointer-table handlers (`0x0561daee`, `0x0561da2a`,
`0x0561df7e`, `0x0561df46`, `0x0561df76`, `0x0561dfc2`, `0x0561d3a2`,
`0x0561d33e`, `0x05670c82`) are referenced **only from the menu
pointer table itself**. Verified by:

1. Each handler appears exactly once in firmware (or twice for
   `0x05670c82`), all at offsets `0x06df00..0x06efe0`.
2. No memcpy-style `(SRAM_dst, flash_src, plausible_len)` triplet in
   any code region copies these addresses.
3. The 9 code-region literals to nearby `0x0561d...` addresses land in
   tiny (4–10 byte) "function" stubs that Ghidra cannot disassemble —
   they are vtable-like data, not actual code.

**Conclusion:** the C7000 SoC has menu/UI framework code in chip ROM
(or another non-flash memory) at the `0x055xxxxx..0x0567xxxxx` range.
The application firmware (this file) wires labels to that ROM
framework via the menu pointer table, but the framework code itself is
not in the firmware image.

To get dispatcher logic, would need:
1. JTAG/SWD dump of C7000 internal ROM
2. Vendor BSP/SDK from chip maker (Anhui Sunplus or similar)
3. Behavioral reverse-engineering (toggle items, observe response)

See `v32_dispatcher_architecture.md` for full reasoning.

---

## 6. Coverage assessment

| Category                          | Coverage                        |
|-----------------------------------|---------------------------------|
| Strings (rodata text)             | **~100%** recovered, all clean  |
| Tone/freq tables (CTCSS/DCS/IARU) | **100%** byte-decoded           |
| Menu pointer table                | **100%** structure mapped       |
| Pointer-table region (0x36k-60k)  | ~75% identified as ptr/data     |
| Code regions (00–36k + 80k–94k)   | 5–10% functional understanding (via debug-printf anchors) |
| Function bounds                   | **100%** (4,333 via Ghidra)     |
| Function names                    | <1% (272/4,333 named)           |
| Call graph (xref counts)          | **100%** per function           |
| SRAM-resident code (dispatcher)   | **0%** — not in firmware        |
| AMBE+2 vocoder                    | 0% — runs on external chip      |
| Bluetooth stack                   | 0% — runs on external chip      |

Bytewise: **~12% identified** (mostly strings + tables); **~88%
uncategorized** (mostly code that has no string-anchored debug).

Functionally: **15+ subsystems** structurally mapped, ready for
deeper interactive analysis in the Ghidra GUI.

---

## 7. Files in this directory (post-session)

### Canonical firmware
- `v208.perword.v32.bin` — current converged state (~89 flips from v22)
- `v207.perword.v22.bin`, `v213.perword.v22.bin` — sibling firmwares (v22-equivalent)

### Analysis outputs
- `v32_menu_decompile.txt` — full pointer-table dump, 10 segments, 219 items
- `v32_menu_review.txt` — EN ↔ CH translation pairs for review
- `v32_functions.txt` — Ghidra function inventory (4,333 functions)
- `v32_decompile_top.c` — top-20 named functions decompiled
- `v32_boot_trace.txt` — SRAM-reference analysis
- `v32_dispatcher_callers.txt` — code-region literal-pool entries
- `v32_dispatcher_architecture.md` — menu dispatcher findings (final)
- `v32_firmware_summary.md` — this document
- `c7000_reference.md` — HR_C7000 chip reference (memory map, MMIO)

### Ghidra projects
- `v32_ghidra/v32_proj.gpr` — fully analyzed v32 project (re-openable in GUI)
- `v208.perword.v22.bin_ghidra/` — older v22 project (deprecated)

### Scripts
- `ghidra-export/ghidra_setup_memory.py` — memory layout + segment disasm
- `ghidra-export/ghidra_apply_metadata.py` — applies 793 metadata entries
- `ghidra-export/dump_summary.py` — function inventory + decompile
- `ghidra-export/trace_boot_copy2.py` — SRAM-pointer reference trace
- `ghidra-export/inspect_dispatcher_callers.py` — code-region SRAM literal analysis
- `ghidra-export/metadata*.txt` — 793 hand-curated annotations (4 files)

### Logs
- `v32_pyghidra.log` — full headless analysis log
- `v32_metadata.log` — metadata-application log
- `v32_dump_summary.log` — function dump log
- `v32_boot_trace.log` — boot trace log
