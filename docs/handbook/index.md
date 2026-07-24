---
title: "HD2 Handbook"
---

# The HD2 Handbook

A reverse-engineering and porting handbook for the **Ailunce HD2** — a
single-chip DMR/FM handheld built on the Dahua **HR_C7000** SoC (a T-Head /
C-SKY **CK803S** core). It distils everything learned bringing the radio up on
**OpenRTX + Miosix**: the SoC and its buses, every RF and audio path, the voice
codecs, the kernel port, the OpenRTX target layout, and the RE tooling that made
it all knowable — each chapter paired with the live-verified facts, the working
recipes, and the dead ends not to repeat.

## How to read this

Each chapter is self-contained and follows the same shape — *what it is / how it
works* → *how to implement it* → *gotchas & cautions* → *where the code lives* →
*status & deeper reading*. A few chapters (e.g. 04, 09) also surface a one-line
**Status:** banner above *what it is*, so the verification state is visible at a
glance before the prose; the full status still lives in its section at the end.
Read Part I first for orientation; after that, jump to
whatever subsystem you are working on. New to the RE workflow rather than
building a feature? Start with Part IV — ch.14 (the RE pipeline and the live
bridge) and ch.15 (the vendor RTOS) — then loop back to Part I. Chapters
cross-link where one depends on another, so following a "see chapter NN" link
is usually faster than re-deriving
another, so following a "see chapter NN" link is usually faster than re-deriving
context. The **gotchas** sections are the highest-value part of the book: they
are the multi-day bugs and falsified theories, written so you don't pay for them
twice.

## Status legend

Every claim in this book carries one of three tags:

- ✅ **HW-verified** — proven on real hardware, with a date.
- 🟡 **in-progress** — built and partially working, or RE-derived but not yet
  hardware-confirmed.
- ⚠️ **dead-end / superseded** — a theory that was falsified, or guidance that a
  later finding replaced. Documented so it is not retried.

## Source of truth

> **Authoritative live port** — `vendor/wt-hd2-vp-adpcm` (branch
> `hd2-vp-adpcm`), the minimal FM + IMA-ADPCM-voiceprompt slice that
> `docker/build.sh` actually builds and ships. When a chapter names a file, this
> is the tree it points at unless it says otherwise. The fuller canonical
> feature set (DMR, FM-broadcast, M17, APRS, codeplug) lives in the parallel
> `vendor/OpenRTX` worktree and is called out explicitly where a chapter relies
> on it.
>
> **Ground-truth vendor behavior** — the reverse-engineered V2.1.3 firmware:
> the decompiled mirror `assets/source_v213/`, the C register/API headers under
> `src/firmware/`, and the unified analysis image
> `firmware/hd2_unified_v213.elf`. Every "the vendor does X" statement traces
> back to one of these.

## Setup / prerequisites

Before you start, you will want:

- **Ghidra** with the **C-SKY / CK803S processor plugin** — for the decompiled
  mirror (`assets/source_v213/`) and disassembly of `firmware/hd2_unified_v213.elf`.
- A **Python** environment (pyghidra for scripted analysis; the `scripts/`
  tooling and the `rtx_tui.py` serial bridge run here too).
- **Docker** plus the **`hd2-csky-build`** toolchain image — builds the
  OpenRTX/Miosix app locally via `docker/build.sh`.
- For anything live: a **physical HD2 radio**, a **USB-serial cable**, and the
  macOS serial port (`/dev/cu.usbserial-*`) the `rtx_tui` bridge talks to.

Pure RE (reading the decomp + vendor manuals) needs only the first two;
building needs Docker; keying the radio on air needs the hardware.

## Table of contents

### Part I — Orientation

- [01. The HD2 at a glance](01-device-at-a-glance) — the SoC, the chip
  roster, the register-base + GPIO-pin map.
- [02. Boot, IAP & the build→flash pipeline](02-boot-flash-pipeline) —
  BOOTROM → IAP → app, and the docker-build → encrypt → flash loop.

### Part II — Implementer's handbook

- [03. Audio path & routing](03-audio-path) — the two speaker-amp inputs and
  the PTB17 path-select that governs them.
- [04. FM analog radio (AT1846S)](04-fm-analog) — two-way FM RX/TX, CTCSS/DCS,
  squelch, RSSI.
- [05. FM broadcast receive (RDA5802E)](05-fm-broadcast) — the broadcast
  "FM radio" tuner.
- [06. DMR TX (4FSK on-air)](06-dmr-tx) — the autonomous modem TDMA engine and
  the slot pump.
- [07. Voice codecs & prompts](07-voice-codecs) — software AMBE+2, codec2
  fixed-point, IMA-ADPCM voice prompts.
- [08. M17 TX (MCU-baseband pump)](08-m17-tx) — the native 4FSK PHY and the
  8 kHz FM-TX-RAM pump.
- [09. APRS (AFSK)](09-aprs) — 1200-baud Bell-202 over the analog carrier.
- [10. Buses & peripherals](10-buses-peripherals) — I2C / SPI / i8080, GPIO,
  keypad, GPS, ADC, RTC.
- [11. Display, UI, menus & codeplug](11-display-ui-codeplug) — the ST7735S
  panel, the menu state machine, the vendor codeplug format.

### Part III — Kernel & platform

- [12. The CK803S / C-SKY V2 kernel port (Miosix)](12-kernel-cskyv2) — the
  no-PendSV context switch and tickless timer.
- [13. The OpenRTX port layout & convergence](13-openrtx-port-layout) — the
  three-fork stack, the build split, the weak-HAL override pattern.

### Part IV — RE methodology

- [14. The reverse-engineering pipeline & live debugging](14-re-pipeline) —
  Ghidra + labels-as-code + the rtx_tui bridge + MMIO diffing.
- [15. Firmware crypto, keystream & the vendor RTOS](15-crypto-and-vendor-rtos)
  — the flash keystream DB, DMR AES/RC4, activation, uC/OS-III.

### Part V — Roadmap

- [16. Roadmap & open problems](16-roadmap) — what is built-but-unfinished,
  what is blocked on a hard wall, and the upstreaming plan.
