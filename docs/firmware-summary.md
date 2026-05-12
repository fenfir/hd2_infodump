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
chosen by a bitmap. **DIFF** = `KEY_N ⊕ KEY_S = 0x06666666` is the flip
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

**CTCSS** at `0x06da3c..0x06daa8` — 31 frequencies (v208 rodata).
**DCS** at `0x06daa8..0x06db78` — 103 octal codes (v208 rodata).
Cross-firmware: v207 has CTCSS at `0x06bf2c`, v213 at `0x06dadc`.

Full frequency/code lists and channel-byte encoding: see [channels](channels) "Tone field encoding" and "Firmware tone tables".

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

#### 3.11.1 Channel-level cipher types

Cipher list, menu segment 0 at `0x06df4c`: `Off Normal Enhanced ARC4 AES128 AES256`.
Channel byte encoding and key storage regions: see [channels](channels) and [settings](settings) encryption sections.

#### 3.11.2 Boot-time integrity checks (`加密组别`, "encryption group")

A separate mechanism from the channel ciphers. On every boot,
`FUN_0304d564` (the integrity-check function) runs **7** sequential
checks against values in the activation NVRAM block. A failure prints
`加密组别 NN: 算法：%x,读取：%x` and (pre-patch) early-returns; if all
7 pass, the radio finishes initialisation and operates normally.

Format-string offsets in rodata:

| Group | Format-string offset | NVRAM slot (after `Activa`)         | Algo (UID `0.0.1d.5e`) | UID-dependent? |
|-------|----------------------|-------------------------------------|------------------------|----------------|
| g1    | `0x71044`            | `token[0..3]` -> LE u32             | `0x001c0d93`           | yes            |
| g3    | `0x71064`            | `token[7]` + `fill[0..2]` -> LE u32 | `0x54871eab`           | no             |
| g11   | `0x71084`            | `fill[24..27]` LE u32               | `0x45589210`           | yes            |
| g12   | `0x710a4`            | `fill[28..31]` LE u32               | `0x00000246`           | no (constant)  |
| g21   | `0x710c4`            | `fill[64..67]` LE u32               | `0x4d0b3476`           | yes            |
| g22   | (further on)         | `fill[68..75]` (8 B @ `0x7ae04c`)   | UID-derived (formula)  | yes (formula)  |
| g50   | (further on)         | `fill[184..187]` LE u32             | `0x00000aa6`           | no (constant)  |

g1, g3, g11, g12, g21, g50 are flat 32-bit constant compares against
their NVRAM slot. **g22 is different**: it reads 8 bytes from
`0x7ae04c` (in the activation block) and compares each byte against a
per-byte transform of the 8-byte chip-UID buffer at `0x48350`
(disassembly `0x0304d7c4..0x0304d824`; both `puVar2` and
`DAT_0304d87c` resolve to `0x00048350`):

```
resp[0] = buf[5] + 0x12      resp[1] = buf[6] + 0x23
resp[2] = buf[0] + 0x3f      resp[3] = buf[2] - 0x2c
resp[4] = buf[3] - 0x39      resp[5] = buf[7] + 0x50
resp[6] = buf[1] - 0x67      resp[7] = buf[4] + 0xaa
```

The "算法" printed in `加密组别22:` is the expected byte at the
*first* mismatching position (not necessarily byte 0).

For UID `0.0.1d.5e` (`buf = 00 00 00 00 00 00 1d 5e`), the computed
g22 response is `12 40 3f d4 c7 ae 99 aa`.

Authoritative payload mapping and Ghidra decompile:
`scripts/patch_crypto_check.py`,
`activa_tests/test_38_uid_buf_g22.py`, and
`assets/crypto_init_decomp.c`. Patch + protocol details:
[fw_update](fw_update) "Integrity-check fall-through patch" and
[protocol](protocol) "`Activa` — radio activation".

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

The four ASCII command keywords `END`, `Activa`, `GetUID`, `GetVer`
are accepted by the application firmware over the debug/CPS UART:
- `END` — reboot
- `Activa` — write activation token + fill into NVRAM, self-reboot
  (recoverable; see [protocol](protocol) "`Activa`")
- `GetUID` — return 8-byte chip UID (only the trailing 4 bytes show
  up in the boot-log printf, but the wire response is 8 bytes)
- `GetVer` — return firmware ID string

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

**The menu dispatcher does NOT live in this firmware.** The handler
addresses (`0x0561d...` range) are ROM-resident C7000 chip services.
Full reasoning: see [Dispatcher Architecture](firmware-dispatcher-architecture).

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
