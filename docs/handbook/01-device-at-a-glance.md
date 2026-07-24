---
title: "01. The HD2 at a glance"
---

# 01. The HD2 at a glance

## What it is / how it works

The Ailunce HD2 is a single-chip DMR/FM handheld built around the **Dahua HR_C7000**
SoC. The C7000 is the whole radio brain: it integrates a 32-bit MCU core, a 4FSK
DMR baseband/modem, an analog audio codec (AFE), and the full peripheral set (GPIO,
I2C, UART, SPI, I80/LCD, PWM, ADC/DAC, SDIO, USB, RTC, WDT, timers). Only the RF
front-end, the SPI-NOR flash, the display, and a handful of analog
chips sit outside the die. The MCU our firmware executes on is a **T-Head / C-SKY
CK803S** — CSKY V2 ISA, 32-bit, **no FPU**, and (per the kernel work) **no PendSV**;
exceptions run through the CSKY VBR/PSR/trap/`rte` model.

The chip is organized as two clock/bus domains behind a 2:1 bridge. The **system
AHB** carries the CK803S core, the on-chip SRAMs, the modem, USB, SDIO, and the I80
LCD bus. The **APB** carries the "character" peripherals (GPIO A/B/C, I2C, UART, SPI,
PWM, ADC/DAC, timers, WDT, RTC). Crucially, the **modem, DMR physical/link layers,
FM block, clock manager, reset, pin-mux, and system-control registers all share one
AHB window at `0x11000000`, distinguished only by sub-offset** — while the character
peripherals live at `0x14xx_xxxx`. Firmware runs XIP — execute-in-place, code fetched straight from flash with no
copy to RAM — from SPI-NOR at `0x03000000` (app) / `0x03200000` (IAP) via the
**LCSFC** (the on-chip flash-XIP controller that maps SPI-NOR into the code
space), with on-chip IRAM used for `.data/.bss`/stack/heap
(the boot chain through these regions is the [boot & IAP chapter](02-boot-flash-pipeline)).

The external chip roster is short and well-documented: **Winbond W25Q512JV** SPI-NOR
(codeplug/storage), **AT1846S** RF transceiver (2-way VHF/UHF FM + the analog path
for DMR), **RDA5802E** broadcast-FM tuner (the "FM radio" feature), and **ST7735S** 160×128 color
TFT controller. Everything else on the board is analog (mic, speaker/amp, PA, GPS).
All speech codecs run in software on the CK803S core; there is no hardware vocoder
(see [voice codecs](07-voice-codecs)).

## How to implement it

**Register-base map (greppable).** AHB system/modem window and APB peripherals:

| Base          | Block                                              | Bus  |
|---------------|----------------------------------------------------|------|
| `0x00000000`  | BOOTROM (mask ROM, ~2 KB; UART0 `$`/`serial-boot`) | —    |
| `0x00010000`+ | IRAM (on-chip SRAM; ELF segment `0x00010000..0x00058000` — IRAM code + AES lib, `.data`/`.bss`, PIC table `0x00050D70`, stack/heap) | AHB |
| `0x03000000`  | APP firmware, XIP from SPI-NOR via LCSFC           | —    |
| `0x03200000`  | IAP loader (YMODEM update)                          | —    |
| `0x11000000`  | **Modem + socsys** (reset/clock/PLL, pin-mux DIPLEX0/1/2, DMR PHY/LINK, FM) | AHB |
| `0x12000000`  | I80 (Intel-8080 / LCD parallel controller)         | AHB  |
| `0x14000000`  | Timer (×6)                                          | APB  |
| `0x14010000`  | Watchdog (WDT)                                      | APB  |
| `0x14020000`  | GPIOA                                               | APB  |
| `0x14030000`  | UART0 (boot/debug console, 115200)                 | APB  |
| `0x14040000` / `0x14050000` | UART1 / UART2 (UART2 = DBGSHELL; IAP handoff 57600) | APB |
| `0x14060000` / `0x14070000` / `0x14080000` | I2C0 / I2C1 / I2C2 (I2C2 → internal RTC) | APB |
| `0x140A0000` / `0x140B0000` | SPI Master 0 (NFC_SPI, NOR flash, QuadSPI) / SPI Master 1 | APB |
| `0x140C0000`  | PWM (×3 — backlight, beeps)                         | APB  |
| `0x140D0000`  | ADC (8-ch, battery/low-speed; `adc_controller_init`) | APB |
| `0x140E0000`  | SPI Master 2                                        | APB  |
| `0x140F0000`  | DAC (3-ch, 12-bit; AF-bias + TX-APC ramp; `dac_controller_init`) | APB |
| `0x14100000` / `0x14110000` | GPIOB / GPIOC                        | APB  |
| `0x14150000`  | SPI Master 3 — unused on HD2                       | APB  |
| `0x15000000`  | SDIO                                                | AHB  |
| `0x16000000`  | Modem Buffer (voice-frame staging, 64 KB aperture) | —    |
| `0x1600_09C0` | Codec (analog AFE control)                          | —    |
| `0x17000000`  | **PIC** (interrupt controller — the one the app uses) | AHB |
| `0x18000000`  | SAHB SRAM (32 KB, MCU↔modem shared; RX-audio capture buffer) | AHB |

**Interrupts.** The app installs handlers into a 64-entry PIC vector table at IRAM
`0x00050D70` (indexed by `vec - 0x20`) via `app_pic_register_handler` (`0x0306ecbc`);
unregistered slots point at `isr_unexpected` (`0x0306ecac`). The PIC MMIO is at
`0x17000000` (mask-low `+0x04`, enable-low `+0x08`, enable-high `+0x68`). Vectors of
interest: `0x21` timer1 (100 Hz), `0x22` RTC, `0x23` systick, `0x3b/0x3c` PCM rd/wr,
`0x3d` DMR sysint, `0x3e/0x3f` TS TX/RX, `0x40/0x41` RF TX/RX. See `system.h`
(`enum pic_vec`). Note the CK803S also has its own tightly-coupled VIC/CoreTim at
`0xE000E010`/`0xE000E100`, but the running firmware drives the `0x17000000` PIC.
(Our kernel port's autovector/dispatch through this PIC is the
[kernel chapter](12-kernel-cskyv2).)

**External-chip wiring (verified):**
- **W25Q512JV** — now on **HW SPI0** at `0x140A0000` (CTRLR0=7, BAUDR=4, CS held as GPIO, DIPLEX1=0x007). FIFOs are 8 deep, not the manual's 128. JEDEC ID `ef 40 20`. (Details: [buses](10-buses-peripherals).)
- **AT1846S** — now on the **HW DesignWare I2C1 controller** at `0x14070000` (SCL=PTA7/SDA=PTA8), 8-bit device addr `0xE2` (`at1846s_chip_init`); the earlier GPIOA bit-bang is historical. (Details: [FM analog](04-fm-analog), [buses](10-buses-peripherals).)
- **RDA5802E** — same PTA7/PTA8 I2C bus, 8-bit write addr `0x20` (7-bit `0x10`, sequential mode). (Details: [FM broadcast](05-fm-broadcast).)
- **ST7735S** — 8080 parallel bus on the I80 controller at `0x12000000`; pads on **GPIOC** (PTC2–14: NRESET/CS/RS/WR/RD + DB0–7). Works at reset defaults (INDEX=cmd, DATA=data byte).
- **Key GPIOB control pins:** **PTB17** = speaker-amp input path-select (LOW = codec DAC for MCU playback, HIGH = AT1846S analog RX; see [audio path](03-audio-path)). **PTB11** = PTT (active-low). **PTB19** = VHF/UHF band select. Park **PTB15** (GPS rail) low at boot.

## Gotchas & cautions

- ⚠️ **`0x11000000` is not "the modem" — it's the whole system control plane.** socsys registers `0x00..0x3c` (reset, clock/PLL, IO_DIPLEX0/1/2 pin-mux) live in the *same* window as the DMR modem regs (`0x70..0x3b0`). Don't assume an offset is modem-only.
- ⚠️ The v213 Ghidra decomp **mis-tracks the `movih r3,0x1100; bseti` base** for the modem sub-block (`0x11000400+x`), rendering it as low-address `_DAT_000004xx`. Don't trust those low `DAT_` addresses — they are real MMIO at `0x1100040x`. Full mechanics + the re-alias script in the [RE pipeline chapter](14-re-pipeline).
- ⚠️ **The manual's modem-side AES key port (reg `0x88`) is unused on this die.** MMIO `0x11000088` is `pcm_handshake` (busy/ready), not a key port. DMR crypto is a CPU-side IRAM AES/RC4/EP library at `0x00015620..0x00017380`.
- ⚠️ **Heap is tight.** A single static buffer larger than ~12–16 KB hangs boot (thread stacks are heap-starved → UI splash hangs while diag stays alive). Stream, don't buffer; prefer static over large stack locals.
- ✅ **ADC and DAC are separate blocks.** ADC = `0x140D0000` (battery/low-speed), CPU DAC = `0x140F0000` (`DAC_DATA_C` at `0x140f0010`). The manual's Register Table Directory misprints both at `0x140D0000`; the v213 decomp (`dac_controller_init`) and the live `registers.h` (`ADC_HW`/`DAC_HW`) confirm the split.

## Where the code lives

- Register/API headers: `src/firmware/include/hrc7000.h` (modem + socsys map, MMIO `0x11000000`, buffer `0x16000000`), `src/firmware/include/system.h` (boot, PIC table, RTOS tasks, ISRs).
- Decompiled mirror: `assets/source_v213/00010000_iram.c`, `0300d000_v2_1_3_app.c`, `030a3000_lcsfc_tail.c`, `03200000_iap.c` (`INDEX.md` is the map).
- OpenRTX device drivers (HD2 port, live tree): `vendor/wt-hd2-vp-adpcm/platform/drivers/baseband/AT1846S_HD2.cpp`, `.../display/ST7735S_HD2.c`, `.../NVM/W25Qx.c` (W25Q on SPI0). ⚠️ The broadcast-FM driver `RDA5802E_HD2.c/.h` (`fm_broadcast_HD2`) is **not** in the vp-adpcm branch; it lives only in the FM branch (`vendor/OpenRTX/platform/drivers/baseband/RDA5802E_HD2.*`).
- Label/alias scripts: `scripts/labels/modem_lowaddr_alias.py`, `scripts/labels/dmr_tx.py`, `scripts/labels/power_on.py`.

## Status & deeper reading

**Status: ✅ HW-verified** for the SoC/core identity, the chip roster, and the
register-base + GPIO-pin map (all buses — I2C, SPI0, I80/LCD — have been migrated
to hardware controllers and verified on-device).

Deeper reading:
- `docs/hr_c7000_architecture.md` — full block/bus/signal-chain diagrams.
- `docs/peripherals.md` — chip + on-SoC peripheral inventory with confidence tags.
- `docs/device_subsystem.md` — CPU-side AES/crypto path.
- `docs/peripheral_drivers.md` — Timer/PIC driver survey.
- `docs/hrc7000_full_register_reference.md` — modem/codec/PLL register tables.
- `vendor/docs/index.md` → `hr_c7000` (primary SoC manual), `ck803s` (core VIC/CoreTim/cache), `csky_arch`/`csky_abiv2` (ISA/ABI).
- Memory: `hd2-fm-rx-audio-modem-wall` (PTB17), `hd2-w25q-hw-spi0-migration`, `hd2-lcd-i8080-migration`, `hd2-decomp-movih-bseti-lowaddr-mistrack`, `hd2-memory-constraints`, `hd2-dmr-voice-sw-ambe-codec`.
