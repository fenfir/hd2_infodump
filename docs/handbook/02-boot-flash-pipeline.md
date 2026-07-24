---
title: "02. Boot, IAP & the build→flash pipeline"
---

# 02. Boot, IAP & the build→flash pipeline

## What it is / how it works

The HD2's HR_C7000 SoC (single CK803S / C-SKY V2 core, up to 192 MHz) boots through **three
code regions in flash**, chained by a magic-word handshake. A 2 KB silicon **BOOTROM** at VMA
(virtual memory address — where the CPU sees code mapped, not its offset in the flash file)
`0x00000000` runs first (only 564 bytes of real code). It brings up UART0 at `0x14030000`
(115200 8N1), prints a `$` prompt, and either drops into a UART debug protocol or does a
**Flash-boot**: it reads `flash[0x03000000]`, checks it equals the `DH_FLAG` magic
`0x0c646874` ("thd\x0c"), and jumps to the pointer at `flash[0x03000004]`. The BOOTROM checks
*only* `0x03000000`; it never touches the IAP (In-Application Programming loader, defined next
paragraph) directly and polls **no GPIO** — the "hold a key
to enter the boot menu" behaviour lives in the stage-1 stub (flash `0x03000000..0x0300d000`,
not present in distributed `.bin` files) or the IAP.

The **IAP** (In-Application Programming loader) lives at `0x03200000` (entry `0x03201000`). It
is the *unmodified* Dahua HR_C7000 reference IAP — a full uC/OS-III application (banner: "HR_C7000
In-Application Programming Application (Version 1.0.0) By YUFENG 2017/07/21"). It re-inits the
PLL and drops UART to **57600 baud**, then prints a 3-option menu: (1) UART download, (2) USB
download, (3) execute the new program. Option 1 receives a firmware image over a **modified
YMODEM** (1029-byte STX packets, CRC-16/CCITT poly `0x1021`), XOR-decrypts each word via
`AilunceFW::ApplyXOR`, and programs it to flash at `0x03000000`. **The application firmware**
lives at VMA `0x03000000` (app crt0 `crt0_app_entry @ 0x0300d000` in current builds; the app
proper starts at `0x0300d000` after the header). After crt0 (data-copy + bss-clear) it tail-calls
IRAM `main_iram_init @ 0x00030c04`, which runs `OSInit` and `OSStart`; a single prio-`0x19`
bootstrap task then does all hardware init, spawns ~21 worker tasks (the vendor uC/OS-III
task inventory + kernel struct layouts are the [crypto & vendor RTOS chapter](15-crypto-and-vendor-rtos)),
paints the first UI screen, and idles. Note: there is **no separate modem CPU** — the "HR_C7000 modem" is a hardware DSP/FSM
peripheral on the same AHB, so there is no per-boot firmware blob to upload (see gotchas).

Our development loop replaces the app image at `0x03000000` with our OpenRTX build (whose own
reset / kernel-init path — `Reset_Handler` → `IRQmemoryAndClockInit` → kernel boot — is the
[kernel chapter](12-kernel-cskyv2)): **docker build
→ objcopy → pad to 614400 B → XOR-encrypt + YMODEM-frame → POST to the TUI `/flash` → the IAP
auto-boots it.**

## How to implement it

**The verified end-to-end flash pipeline** (flashed `hd2-fm` and it booted, 2026-07-23):

1. **Build the ELF in docker.** `docker/build.sh` builds the
   `vendor/wt-hd2-vp-adpcm/platform/targets/HD2/build-docker` tree (its `BUILD_DIR`; the
   source-tree layout is the [OpenRTX port chapter](13-openrtx-port-layout)) with
   the `hd2-csky-build` image (carries the full `/opt/csky-miosix-elf` toolchain — no llama-farm
   needed), consuming the kernel from `vendor/miosix-kernel` (`-DMIOSIX_KPATH=…/vendor/miosix-kernel/miosix`).
   It runs `cmake -S … -B build-docker` then `make openrtx_hd2`, then
   `csky-miosix-elf-objcopy -O binary openrtx_hd2.elf openrtx_hd2.bin`. Extra `-D` flags pass
   through (e.g. `docker/build.sh -DHD2_CODEPLUG_STUB=ON`). For a *different worktree*, run the
   image directly against that worktree's `platform/targets/HD2/build-docker` — `docker/build.sh`
   only builds the `vendor/wt-hd2-vp-adpcm` worktree tree its `BUILD_DIR` points at.
2. **Pad the raw bin to exactly 614400 B** with `0xff` fill (`600 × 1024`; must match the linker
   FLASH region). `docker/build.sh` does this automatically → `docker/out/openrtx_hd2.padded.bin`.
   `assert len(data) <= 614400` first.
3. **XOR-encrypt + YMODEM-frame** (mandatory, from `hd2-clean/`):
   `python3 scripts/fw_crypto.py encrypt <padded.bin> -o OUT.ymodem-framed.bin --frame`
   → **617400 B = 600 packets × 1029**. `fw_crypto.apply_buffer` is radio_tool's symmetric
   `ApplyXOR` (`KEY_N=0x07777777`, `KEY_S=0x01111111`, bit-28 selects the key; `0x00`/`0xff`
   words invert). The IAP runs `ApplyXOR` on every word it receives, so plaintext would be written
   as garbage — you **must** encrypt before framing.
4. **(optional) Validate:** `python3 scripts/fw_flash.py validate OUT.ymodem-framed.bin`
   (expect 600/600 STX/seq/CRC ok).
5. **Enter physical DFU** (Device Firmware Update mode): power knob off → hold **PTT + SK1 (Side-1)** → power on → the IAP menu
   appears. Do this **after** the framed payload is built (see gotchas — the IAP menu times out).
6. **Flash via the running TUI bridge:**
   `curl -sS -X POST --data-binary @OUT.ymodem-framed.bin --max-time 200 http://127.0.0.1:7777/flash`.
   Success = `{"ok":true,"packets":600,"elapsed_s":~131}`. The TUI's `_run_flash` sends `'1'` to
   enter UART download, waits for `'C'`, streams the 600 frames, waits for
   "Programming Completed Successfully!" + ≥1 s of banner silence, then sends `'3'` to launch the
   app. **The IAP auto-boots — no separate boot step.**
7. **Confirm the flashed build booted.** Which check depends on which build you flashed:
   - **Minimal ADPCM build** (what steps 1–6 produce): it has no loader, so there is no `P` op.
     Confirm positively by observing that it came up — the **UI splash** paints on the LCD, and
     `hd2_glue.cpp`'s **raw UART0 trace** prints on the serial port at 57600 (watch it in the TUI
     log: `GET http://127.0.0.1:7777/log`, or scrolling in the TUI itself). Silence on both after
     `Execute The Program` = the app didn't start (first suspect: forgot the XOR-encrypt — see
     gotchas).
   - **Diag build** (`vendor/OpenRTX`): additionally confirm with the loader `P` op (version string
     baked from `__DATE__`/`__TIME__`) — *not* `/status.fw_version` (stale cached probe). ⚠️ `P`
     only answers from the diag build (see *Where the code lives*); if you need *programmatic*
     confirmation of the exact image, flash that build.

**TUI topology:** `scripts/rtx_tui.py --port /dev/cu.usbserial-XXXX` is the **only** process that
opens the serial port; it exposes an HTTP bridge on `127.0.0.1:7777` (`GET /status`, `GET /log`,
`POST /cmd`, `POST /flash`, `POST /pause_poll`). Ops over `POST /cmd`: `P` probe (→`RTX1`),
`R`/`r` MMIO/RAM read, `W` word write, `T` DTMF-tx, `B` APRS-tx (and more — the firmware side lives
in `hd2_diag.cpp`, not `main.cpp`). `Z` (jump-to-IAP / software DFU) is a **bridge-side** op in
`rtx_tui.py` (it just writes the byte `'Z'`); `G` is a CPS-protocol `GetVer` byte, not a standalone
diag op. The app baud and bootloader baud are both **57600** here.

## Gotchas & cautions

- **DFU timing is the #1 failure.** Use **physical DFU** (PTT+SK1 held at power-on). ⚠️ **Don't
  rely on the `Z` software-DFU** — it's a coin-flip; the poll worker races the IAP auto-boot.
- **The IAP menu times out during the ~1-min build+frame step.** Enter DFU *after* the framed
  payload is built, right before the POST. Symptom of a stale/timed-out DFU:
  `{"ok":false,"error":"timeout: no 'C' from bootloader"}` — just re-enter DFU and re-POST (the
  image is already built, so it's instant).
- ⚠️ **XOR-encrypt is mandatory and easy to forget.** Skip it and the flash *completes*, prints
  "Programming Completed Successfully", `Execute The Program` fires, then **dead silence** — no
  UART from your code. Always `apply_buffer` (encrypt) *before* framing.
- **Pad to the full 614400 B partition**, not just chunk-aligned. Partial-page writes near the end
  of `.text`/`.data` can interact badly with the IAP's sector handling.
- **Don't reset GPIO state from the jump-to-IAP path.** History of over-zealously clearing bits the IAP
  needs for its own key detection; if `Z` "just disconnects and probes go bad," suspect that.
  The IAP does its own init.
- **Only one TUI at a time** (`pgrep -af rtx_tui`). Two TUIs both poll at 1 Hz and both corrupt
  framing. Any external script opening the port between the flash's banner-wait and the `'3'`
  launch injects keystrokes → "Invalid Number" loops.
- **`/flash` rejects anything not a multiple of 1029.** If you get `size N not a multiple of 1029`,
  you sent `.padded.bin` instead of `.ymodem-framed.bin`.
- **RAM is tight — big static buffers hang boot.** A ~16 KB static array pushes `_end`/`_bss_end`
  up, shrinks the heap (`[_end, _heap_end=0x4f000]`, ~78 KB) below what Miosix needs to allocate
  the UI thread's stack → **splash-screen hang** (power-cycle won't help; it's the build). ~4–12 KB
  extra static is fine; ~16 KB is not. Signature: **hung UI + responsive diag port** (the diag
  thread's stack is allocated earlier). ⚠️ **Don't buffer large data — stream-process it.** Check
  headroom with `nm` (`_end` vs `0x4f000`).
- **The diag/loader thread stack is small.** Large *stack* locals in a diag-op handler fault the
  radio (warm reboot on op entry). A 96 B local is fine; ~400+ B overflows. Make big buffers in
  diag/decoder paths **static**, not stack-local.
- ⚠️ **Dead end: there is no modem-firmware loader.** The HR_C7000 "modem" is a fixed-function
  hardware peripheral, not a second CPU — no boot-time blob upload exists. Don't hunt for
  `modem_firmware_load` / `g_modem_firmware_blob`; they have no referent. The only writer of the
  `0x16000000` aperture (`hrc7000_modem_buf_write @ 0x03258a24`) stages 36-byte DMR voice bursts,
  not firmware.
- ⚠️ **Vendor stock firmware does NOT go through the TUI.** `firmware/HD-GPS-…V2.1.3*.bin` flashes
  via `scripts/fw_flash.py` directly — the TUI assumes the post-flash app speaks our binary loader
  protocol.

## Where the code lives

- `docker/build.sh` — the canonical build → objcopy → pad-to-614400 pipeline (image
  `hd2-csky-build`; toolchain in `docker/Dockerfile.toolchain`).
- `scripts/fw_crypto.py` — `apply_buffer` (ApplyXOR), `frame_payload`/`unframe_payload`
  (YMODEM 1029-byte packets, CRC-16/CCITT), CLI `encrypt --frame`.
- `scripts/fw_flash.py` — direct stock-firmware flasher + `validate` sub-command.
- `scripts/rtx_tui.py` — serial-owning TUI + HTTP bridge on `:7777` (`_run_flash` drives the IAP
  YMODEM upload and the `'1'`/`'C'`/`'3'` handshake).
- `vendor/wt-hd2-vp-adpcm/platform/targets/HD2/` — the HD2 app source `docker/build.sh` actually
  builds (`build-docker/` is its cmake `BUILD_DIR`; kernel from `vendor/miosix-kernel`). This branch
  is the **minimal OpenRTX threaded bring-up**: `main.cpp` is an 18-line entry stub
  (`openrtx_init` → `openrtx_run`) plus `hd2_glue.cpp` (raw UART0 trace). No `jump_to_iap()` symbol
  exists — the software-DFU jump is `rtx_tui.py` writing the `'Z'` byte (see gotchas: prefer physical DFU).
- ⚠️ **The UART loader/diag ops** (`P`→`RTX1`, `R`/`r`, `W`, `T`/`B`, …) are **not** in the ADPCM
  worktree above — that build won't answer `P`. They live in `hd2_diag.cpp` in the separate,
  fuller `vendor/OpenRTX/platform/targets/HD2/` diag build (`main.cpp` there is a ~28-line stub).
  Step 7's `P`-op confirm and the interactive TUI ops require *that* build flashed.
- Decompiled boot references (not built, RE only): `assets/source_v213/0300d000_v2_1_3_app.c`,
  `assets/source_v213/00010000_iram.c`, `firmware/hd2_unified_v213.elf`.

## Status & deeper reading

**Status: ✅ HW-verified** — the build→flash pipeline is proven end-to-end (booted `hd2-fm`,
2026-07-23). Boot-flow / IAP internals are ✅ verified by disassembly of the BOOTROM and IAP.
🟡 in-progress / open: the stage-1 stub at `flash[0x03000000..0x0300d000]` has never been
captured; the BOOTROM host-handshake literals (`0xff0000ff`/`0x02000003`) are untested live; the
IAP YMODEM dispatcher and flash-write subroutine VMAs are not pinned.

Distills:
- `docs/boot_flow.md` — BOOTROM/IAP/app disassembly, DH_FLAG, YMODEM protocol, integrity checks.
- `docs/modem_firmware_loader.md` — the "no modem CPU / no loader" negative finding.
- `tmp/boot_post_ui_init.md` — the post-`OSStart` bootstrap-task call chain.
- `docker/build.sh`, `scripts/fw_crypto.py`, `skills/hd2-tui-and-build/SKILL.md`.
- Memory: `hd2-flashing-dfu-reality`, `hd2-local-docker-build`, `hd2-memory-constraints`.
