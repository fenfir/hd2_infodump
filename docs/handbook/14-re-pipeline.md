---
title: "14. The reverse-engineering pipeline & live debugging"
---

# 14. The reverse-engineering pipeline & live debugging

## What it is / how it works

The HD2 has no debugger, no source, and no symbols. We build understanding of
the HR_C7000 firmware from three converging sources and drive fixes back onto
the running radio through a single serial bridge. The static side is a **Ghidra
decompile** of `firmware/hd2_unified_v213.elf` — a multi-segment ELF that stitches
the V2.1.3 app (`0x0300d000`, behind a stage-1 stub at `0x03000000`), the IAP
(`0x03200000`), the 2 KB BOOTROM (`0x00000000`), and IRAM/SAHB (the SoC's System AHB bus,
where peripheral MMIO lives) snapshots into one
image at correct VMAs (the flash region layout is the
[boot chapter](02-boot-flash-pipeline)) (the app is `0x0300d000`, not `0x03000000` — placing it at
the stub base breaks ~3791 xrefs). We script
Ghidra from Python via **pyghidra** (`skills/pyghidra-hd2`), language ID
`CSKY_V2:LE:32:default`. Symbol knowledge is not stored inside the Ghidra project;
it lives as code in **`scripts/labels/<subsystem>.py`** — one module per subsystem,
each exporting a `LABELS` list of `Label(vma, name, source_sha, ...)` entries that
`scripts/apply_labels.py` re-applies idempotently over a fresh analysis. Every label
carries a `source` git short-SHA so `git show <sha>` recovers the rationale. This is
the "labels-as-code" spine: analysis is reproducible and reviewable, not a binary blob.

The live side is the **rtx_tui bridge** (`scripts/rtx_tui.py`): the one process that
owns `/dev/cu.usbserial-1120`, exposing an HTTP API on `127.0.0.1:7777`
(`POST /cmd`, `POST /flash`, `GET /log`). Our OpenRTX loader speaks a tiny binary
op protocol (`R`/`W`/`P`/`Z`/`G`/...) so you can read and write any MMIO register on
the running radio without re-flashing. For the **stock vendor** firmware, the
parallel channel is **DBGSHELL** — a planted stub reached by hijacking a wire-protocol
command, giving read/byte-write/word-write of arbitrary memory on an unmodified image.
The workhorse move is **MMIO diffing**: snapshot the curated register ranges in
state A (idle) and state B (keyed / playing), diff, and the deltas are the
registers the vendor code touched.

## How to implement it

**Prerequisite — install the C-SKY processor.** Stock Ghidra ships **no** C-SKY
module (its `Processors/` dir jumps 6502…SuperH…Z80 with no CSKY), so
`CSKY_V2:LE:32:default` will not appear in the language picker on a fresh install and
every step below fails at `open_program`. You must first add a third-party C-SKY
(CK803 / CSKY V2) Sleigh processor extension to Ghidra — drop it under
`<GHIDRA_INSTALL_DIR>/Ghidra/Processors/` (or use *File → Install Extensions*) and
restart. Confirm it took with the `getLanguageDescriptions` snippet in
`skills/pyghidra-hd2/SKILL.md` (it prints the CSKY language ID once the module is
present).

**Decompile a function by VMA** (`skills/pyghidra-hd2`). Set
`GHIDRA_INSTALL_DIR=/opt/homebrew/opt/ghidra/libexec` (the `libexec` suffix
matters). Open with `pyghidra.open_program(ELF, project_location="tmp/pyghidra_project",
project_name="hd2_v213_fixed", language="CSKY_V2:LE:32:default", analyze=False)` — `analyze=True`
only on the first open (~60 s). Auto-analysis only finds entry-reachable functions; for
one it missed, `fm` (Ghidra's `FunctionManager`, from `currentProgram.getFunctionManager()`)
`.getFunctionContaining(addr)` returns `None` and decompile throws
`NullPointerException` — force it with `flat.createFunction(addr, name_or_None)` first.
Sanity check: a good analysis finds ~1051 functions; ≪500 means wrong language or
unrecognized blocks.

**Add a symbol.** Append a `Label` to the right `scripts/labels/<subsystem>.py`
module (create one if the subsystem is new), then run `scripts/apply_labels.py`
(or `--subsystem <name>`, `--dry-run`, `--list`, `--provenance <name>`). `accept_old`
defaults to `("FUN_",)` so you overwrite Ghidra defaults but never clobber a
human-applied name; use `kind="data"` with `accept_old=('DAT_','LAB_','PTR_')` for
register labels, and `force_demote`/`delete_function` for rodata Ghidra misread as code.

**Live MMIO read/write via the loader.** With the TUI running and the radio in the
loader state:
`POST /cmd {"op":"R","addr":"0x14110000","size":16}` reads, `{"op":"W","addr":"0x14100050","val":"0x1234"}`
writes a u32 LE, `{"op":"P"}` probes (expects `RTX1`), `{"op":"Z"}` jumps to IAP/DFU.
Bit-bisect a register by walking `W` over `1<<i` and asking "any visual change?" — the
method that ruled out LCD chip-enable bits.

**MMIO diff** (`scripts/mmio_snapshot.py`): `snapshot <out.json> [--via=loader|dbgshell]`
captures the curated `RANGES` — socsys `0x11000000`, GPIOA `0x14020000`, GPIOB
`0x14100000`, GPIOC `0x14110000`, SSI0/1/2 `0x140A0000/0x140B0000/0x140E0000`, PWM
`0x140C0000`, ADC `0x140D0000` (u32 stride) — then `diff a.json b.json` prints only
changed regs. Both readers hit the same physical MMIO from the firmware's context.

**DBGSHELL on stock firmware** (`docs/dbgshell_v3_notes.md`). v3 hijacks the bare
`'V'` wire command (VMA `0x0304337e`, inside `wire_protocol_parse` at `0x0304323c`)
and redirects its `bsr` (CK803S "branch to subroutine" — a call instruction) to the planted
stub at VMA `0x030a2000`, leaving the `GetVer`
handler (`0x03043498`) untouched. Wire ops: `V` → 35-B filename reply; `V 0xDD addr:4 size:4`
→ read; `V 0xEE ...` → byte-write (ack = `sum(bytes)&0xff`); `V 0xEF ...` → word-write
via `st.w`, `size&~3` trimmed (ack = `sum(words)&0xff`). Host CLI `scripts/dbgshell.py`.
Firmware ID `V4.0.3-GPS.bin` confirms the patched image is loaded.

## Gotchas & cautions

- **movih/bseti low-addr mis-track.** The v213 decompiler cannot fold the CK803S
  `movih r3,0x1100 ; bseti r3,0xa` address idiom (= `0x11000400`); it drops the
  high half and renders the modem block as **low symbols** `_DAT_0000040x`
  (`DAT_00000408` the GO/arm register, ~81 refs — this is the DMR Layer-2 register
  file of the [DMR TX chapter](06-dmr-tx)). Labels at the real high address
  never touch them. `scripts/labels/modem_lowaddr_alias.py` mirrors names onto the
  low addresses (`0x400/404/408/40c/418/41c/424`). ⚠️ Do **not** take a low
  `DAT_0000xxxx` at face value in a modem function — disassemble the site in the ELF
  to recover the real base first.
- **Bridge op collision — clear TWO layers.** `rtx_tui.py` gates ops at
  `SPECIAL_OPS` (frozenset: `R r W P Z G K k J j l 8 a A F ?`) **and** a hardcoded
  `elif op == "X":` chain in `_dispatch`; only the final `else: _dispatch_generic`
  encodes toml args and reaches firmware. A stale op letter present in both layers
  silently shadows a reused firmware op (the DTMF `'T'` got the backlight arg → `sent=0`).
  Before reusing a letter, grep `rtx_tui.py` for `SPECIAL_OPS`, `op == "<x>"`, and
  `loader_commands.toml`; pick one free in all three. ⚠️ "Absent from the firmware
  diag switch" does NOT prove an op is dead — `Z` (jump-to-IAP) is real bridge-side
  with no diag-switch case.
- **One TUI, one port.** Two `rtx_tui` processes both auto-poll at 1 Hz and both
  corrupt framing; `pgrep -af rtx_tui` before starting. Direct serial access fights
  the poll. `/cmd` single-line replies desync on multi-line output — read the full
  result from `/log`.
- **XOR-encrypt before flashing** (loader builds) — the IAP runs `ApplyXOR` on
  every word, so plaintext flashes as garbage (symptom: "Programming Completed
  Successfully" then dead silence, `bad probe: b''`). Full recipe in the
  [boot & flash chapter](02-boot-flash-pipeline).
- ⚠️ **DBGSHELL v2 was a dead end for pylunce coexistence** — the GetVer hijack
  swallows pylunce's codeplug frames; use v3's bare-`'V'` hijack instead.
- **Don't reset GPIO from `jump_to_iap`.** Overzealously clearing peripheral bits
  before `Z` clears state the IAP needs for DFU key detection; if `Z` "disconnects
  and probes go bad" that's the regression. The IAP does its own init.
- **Clean-room narrative leakage.** A "clean-room" workspace is a copy of the decomp given to
  fresh eyes with our own narrative scrubbed out, so conclusions get re-derived rather than
  copied. Labeled decomp **plate comments** (the per-function header comment block Ghidra/labels
  emit above each renamed function) leak our own conclusions; a fresh-eyes RE workspace must
  `grep` for `OpenRTX|docs/...|the open blocker` and scrub the narrative tails (keep the factual
  register text) — treat existing labels as hypotheses to verify, not ground truth.
- **Test ops must mirror OpMode.** A TX/RX diag op must route through
  `radio_setOpmode`/`radio_enableTx()`/`radio_disableRtx()` like `OpMode_M17::txState()`,
  not hand-poke `FM_PTT`/`AUDIO_CONTROL`/`padrv`. Hand-rolled keying is non-representative
  and a prime fidelity-bug suspect (the M17 LICH-but-no-LSF-lock gap). Pure CPU
  benchmarks (codec2 decode op `J`) are exempt.
- **Comments for future humans.** Match each repo's commit prefix (`HD2:`,
  `openrtx_hd2:`, `kernel:`); write comments stating the invariant + hardware fact +
  live-verified date, not debug-session narration.

## Where the code lives

- `firmware/hd2_unified_v213.elf` — the unified analysis ELF (rebuild:
  `scripts/assemble_full_image.py`, then delete `tmp/pyghidra_project/`).
- `scripts/labels/` — labels-as-code (`_common.py` = `Label` type + `open_program_with_retry`;
  `modem_lowaddr_alias.py`, `dmr_tx.py`, `power_on.py`, `mmio_regs.py`, `hrc7000.py`, ~50 more).
- `scripts/apply_labels.py` — unified idempotent applier.
- `scripts/rtx_tui.py` — the serial bridge + HTTP API; `scripts/loader_commands.toml` — op catalogue.
- `scripts/mmio_snapshot.py` — snapshot/diff MMIO ranges.
- `scripts/dbgshell.py` + `scripts/patch_debug_shell_v3.py` — stock-firmware side channel.
- `src/firmware/include/hrc7000.h` — C mirror of the `0x400..0x424` modem block (carries the mistrack note).
- `docs/renamed_functions.md` — per-variant function rename registry.
- `assets/source_v213/` — the exported labeled decompile mirror.
- `skills/pyghidra-hd2/SKILL.md`, `skills/hd2-tui-and-build/SKILL.md` — the operating manuals.

## Status & deeper reading

**Status: ✅ HW-verified pipeline** — the decompile, labels-as-code, live bridge,
DBGSHELL v3, and MMIO diffing are all in daily use and proven on hardware. The
one open thread (🟡) is DMR-TX: replicating the `0x11000400/0x408` register values
alone does not start the TS_TX engine (needs the vendor DMR task/descriptor
infrastructure) — see `dmr_tx.py`'s note.

Sources distilled here:
- `docs/dbgshell_v2_notes.md`, `docs/dbgshell_v3_notes.md`, `docs/renamed_functions.md`
- `skills/pyghidra-hd2/SKILL.md`, `skills/hd2-tui-and-build/SKILL.md`
- `scripts/labels/_common.py`, `scripts/labels/modem_lowaddr_alias.py`, `scripts/rtx_tui.py`, `scripts/mmio_snapshot.py`
- memory: `hd2-decomp-movih-bseti-lowaddr-mistrack`, `hd2-cleanroom-re-agent-comms-workflow`,
  `hd2-bridge-op-collision`, `feedback-repo-conventions-human-comments`, `feedback-txrx-test-ops-mirror-opmode`
