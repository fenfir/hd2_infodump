---
title: "10. Buses & peripherals"
---

# 10. Buses & peripherals

The HD2's off-SoC devices hang off four physical buses plus a handful of
discrete GPIO and one on-chip ADC. **All three shipping serial buses run on
HR_C7000 hardware controllers** — I2C1 live-verified 2026-07-23, SPI0/W25Q and
the LCD i8080 in 2026-05/06. The bit-bang predecessors that plagued early
bring-up are retired; the old `CSKY_V2` bit-bang tree is gone. This chapter is
the pin/register cheat-sheet for each.

The recurring theme: these are custom DesignWare-derived blocks. The vendor
manual's FIFO depths, ID registers, and pad-mux semantics are **not reliably
accurate** — every one of them was corrected against silicon. The shared
playbook that cracked all three migrations: prove the controller with host-paced
diag-bridge pokes first, use whole-register constants for the pad-mux (never
RMW), and watch static-ctor-vs-`platform_init` mux ordering.

## What it is / how it works

**Pad mux is the master key.** Three `SOCSYS_IO_DIPLEXn` registers at base
`0x11000000` select GPIO vs. peripheral function per pin. `IO_DIPLEX0`
(`0x11000034`) covers the I2C1 and UART2 pins; `IO_DIPLEX1` the SPI0 pins;
`IO_DIPLEX2` the LCD i8080 bus and the ADC input pins. **Several of these have
write-only upper bits that read back as zero** — RMW silently corrupts them.
This one fact is behind more than one multi-day bug in this codebase.

The bus roster:

| Bus | Controller @ | Pins | Slaves |
|---|---|---|---|
| I2C1 (radio) | `0x14070000` (DesignWare) | SCL=PTA7, SDA=PTA8 | AT1846S (0xE2 / 7-bit 0x71), RDA5802E (0x20 / 0x10) |
| I2C2 (RTC) | `0x14080000` (DesignWare, `rtc_hd2.c` + manual 4.12.3; the older `0x04000000` in `i2c_dev_0xE0.md` is superseded) | — | RTC-like timekeeper at 0xE0 (7-bit 0x70) |
| SPI0 (flash) | `0x140A0000` (DW-SSI variant) | SCLK/MOSI/MISO muxed; CS=PTA18 GPIO | W25Q512 SPI-NOR (JEDEC ef4020) |
| LCD i8080 | `0x12000000` | PTC bus, shared with keypad matrix | ST7735S TFT |
| UART2 (GPS) | `0x14050000` (DW 16550) | RXD=PTA11, TXD=PTA12 | GPS module, 9600 8N1 |
| UART0 (PC/diag) | `0x14030000` | — | programming cable / diag bridge |
| ADC | `0x140D0000` (on-chip) | DIPLEX2 bits 19-21 | battery on channel 2 |

GPIO banks: **GPIOA=`0x14020000`, GPIOB=`0x14100000`, GPIOC=`0x14110000`**,
DesignWare layout (`+0x00` DR, `+0x04` DDR, `+0x50` EXT_PORT/DIN). `gpio_hrc7000.c`
serves all three banks through the gpio-native API — `gpio_setMode(port, pin,
mode)` takes the bank's `GPIO_TypeDef*` (`GPIOA`/`B`/`C`) directly.

## How it works — the verified recipes

### HW I2C1 (radio bus) — `i2c1_hd2.c`

This is the shared bus for the two RF chips: the AT1846S transceiver (the
[FM analog chapter](04-fm-analog)) and the RDA5802E broadcast tuner (the
[FM broadcast chapter](05-fm-broadcast)). **Note the naming:** this one I2C1
controller's public API carries a legacy `i2c0_` prefix — `i2c0_init`,
`i2c0_write`, `i2c0_lockDeviceBlocking` (and the internal `i2c1_*` helpers) all
operate the *same* `0x14070000` I2C1 block; there is no separate "i2c0"
controller. Controller config mirrors the proven
RTC I2C2 driver: `IC_CON=0x65`
(master/7-bit/FS/restart), 400 kHz off the 42 MHz APB (`IC_FS_SCL_HCNT=0x2c`,
`IC_FS_SCL_LCNT=0x34`). Registers: `IC_TAR +0x04`, `IC_DATA_CMD +0x10`,
`IC_ENABLE +0x6c`, `IC_STATUS +0x70`, `IC_TX_ABRT_SRC +0x80`,
`IC_CLR_TX_ABRT +0x54` (read-to-clear), `IC_ENABLE_STATUS +0x9c`, and the
**HR_C7000-specific `IC_START +0xa0`** trigger.

Ordered transfer (`i2c1_xfer` / `i2c0_write`):
1. `i2c1_set_target()` — set `IC_TAR` only while `IC_ENABLE=0`; toggle enable
   ONLY when the target changes, then leave it enabled.
2. Load **the entire** write+read command sequence into the FIFO.
3. Assert `IC_START=1` — the controller transfers whatever is loaded. Asserting
   mid-load fragments the transfer silently.
4. Drain RX; then `I2C1_WAIT_IDLE()` spins on `IC_STATUS` ACTIVITY clear before
   `IC_START=0` (TFE alone does not mean the STOP finished on the wire).
5. `i2c1_check_recover()` after every transfer: healthy = TFE set + ACTIVITY
   clear + `IC_TX_ABRT_SRC==0`; otherwise clear the abort latch, `IC_ENABLE=0`
   to flush both FIFOs, drop the TAR cache. `I2C1_SPIN_LIMIT=0x2000` (was
   0x40000 — a dead bus must cost ms, not seconds of thread starvation).

`i2c0_init()` clears `IO_DIPLEX0` bits 7/8 (`i2c1_scl_sel`/`i2c1_sda_sel`) via
RMW to route PTA7/8 to the controller. Long writes (RDA5802E 64-byte init) that
exceed the FIFO start once the FIFO fills, then keep feeding.

### HW SPI0 (W25Q flash) — `spi_hd2.c` + `flash_w25q_HD2.c`

Registers (`SSI_BASE 0x140A0000`): `CTRLR0 +0x00`, `SSIENR +0x08`, `SER +0x10`,
`BAUDR +0x14`, `RXFLR +0x24`, `SR +0x28`, `IMR +0x2c`, `DR +0x60`. Init
sequence: `SSIENR=0`, `CTRLR0=7` (TMOD=00 full-duplex, DFS=7/8-bit, mode 0),
`BAUDR=4` (42 MHz/4 = 10.5 MHz SCLK), `IMR=0`, `SER=1`, `SSIENR=1`.

`platform_init` muxes SCLK/MOSI/MISO to the controller via `DIPLEX1=0x007`;
**CS stays GPIO (PTA18)** driven by the flash driver — this dodges the
DesignWare auto-CS-deassert-on-FIFO-empty behaviour and keeps `flash_w25q_HD2.c`
owning CS. `flashXfer` wraps each transaction: `hd2_irq_save`, CS low (clear
GPIOA.18), transfer, CS high, `hd2_irq_restore`. **Bursts are chunked to 8
frames** (the measured FIFO depth). W25Q opcodes are 4-byte-address:
READ=`0x13`, PROG=`0x12`, ERASE-4K=`0x21`, plus WREN `0x06`, RDSR1 `0x05`,
JEDEC `0x9F`, wakeup `0xAB`.

### LCD i8080 — `0x12000000`

Reset-default config just works: `INDEX(+0x00)` write = one command cycle,
`DATA(+0x04)` write = one 8-bit data cycle, `WCFG(+0x10)=0x020202` (2/2/2 strobes
≈143 ns), `SCFG(+0x20)=0`, `AC_MODE(+0x2c)=0`. The controller generates CS/RS/WR.
Pad mux (`DIPLEX2`, upper bits write-only): `HD2_DIPLEX2_LCD_I80=0x3ff80003`
(bits 3..18 = lcd func), `HD2_DIPLEX2_PTC_GPIO=0x3ffffffb`. Panel RESET (PTC2)
stays a GPIO on the latch path.

### Keypad matrix — `keyboard_HD2.c`

The shipping driver is a **4×4 matrix + discrete side keys**: rows = GPIOC
bits 7..10 (input during scan), cols = GPIOC bits 11..14 (driven low one at a
time). These pins are shared with the LCD data bus, so `hd2_kbd_scan_raw()`
saves/restores GPIOC DR+DDR and swaps `DIPLEX2` (`PTC_GPIO` → scan →
`LCD_I80`) around each scan. Rows need "alt-func B" set once in `kbd_init` via
the vendor-custom selector at **`GPIOC+0x78`** (`|= KBD_ROW_MASK`, bits 7..10 →
`0x780`). Verified keymap (col0={1,2,3,*}, col1={4,5,6,0}, col2={7,8,9,#},
col3={MENU,UP,DOWN,EXIT}); active-low, 0 = pressed. Side keys read from GPIOB
EXT_PORT: **bit 9 = SK1, bit 7 = EMER** (active-low). SK2 is NOT a GPIO — it
grounds the row0 sense line wholesale (all-columns-row0-low = the "0xeeee
phantom"), decoded specially as KEY_F3. Rotary encoder polled on GPIOA bits 0/1
(quadrature, TODO-verify pins).

### GPS (UART2) — `gps_HD2.c`

UART2 @ `0x14050000`, DW 16550, 32-bit word-spaced registers, IRQ 43 (0x2b),
9600 8N1 (divisor = 42 MHz / (16·baud)). Enable path (`gps_HD2_enable`, called
by core `gps_task` only when `state.settings.gps_enabled`): drive **GPS power
GPIOB.15 high**; `FCR=0x67` (FIFO+reset); `IER=0`; set baud; clear `IO_DIPLEX0`
bits 11/12 (`uart2_rxd/txd_sel`) to mux PTA11/12 to UART2 and **leave them
muxed** for polled RX; send 5 UBX CFG-MSG trims (GLL/GSA/GSV/RMC/VTG off, GGA
only); drain into `nmeaRbuf`. Disable parks GPIOB.15 low and bits 11/12 back to
GPIO. PTA11/12 are shared with MODEM SPI on non-GPS models — hence the passive
`init`, gated hardware setup.

### Battery ADC — `adcHrc7000.c`

On-chip ADC @ `0x140D0000` (`ADC_HW` accessor). `adcHrc7000_init()` is the
reset-release pulse `CTRL=0; CTRL=8` (PD_FORCE soft-reset — **the step the early
driver missed; without it DATA reads 0**); `CTRL_STOP=2`; wait idle; `CTRL=0`;
`SEOC_TIME=0xa20`; `P2S_EN/INTR/CH_VLD=0`. `adcHrc7000_sample(ch)`:
`CH_VLD(+0x24)=(1<<ch)`, `START(+0x14)=1`, wait busy then spin on
`CTRL_STATE(+0x18)` (bit0 BUSY, bits[5:1] FSM) clear, read
`DATA_AB/CD/EF/GH` (+0x30/34/38/3c), even ch = bits[9:0], odd = bits[25:16].
**Battery = channel 2** → `DATA_CD` bits[9:0]. `platform_getVbat()` converts via
`adc_getVoltage(&adc1, ADC_VBAT_CH) * 3 / 1000` (µV→mV behind the 1:3 pack
divider); the state task low-pass-filters it, so no averaging in the driver.

### RTC (I2C 0xE0)

Single-byte register accesses only. Time regs are **binary, not BCD**: 0x00 HH,
0x01 MM, 0x02 SS, 0x03/0x04 16-bit day counter (anchored `days/365 + 0x7B2` ≈
Gregorian year, `0x7B2 = 1970`). Set sequence: stop (0x12←0) → write shadows
(0x0C..0x10) → start (0x12←1) → commit (0x11 |= 4). Part number unknown; use
neutral `rtc_*` naming.

## Gotchas & cautions

- ⚠️ **`IO_DIPLEX0` bit 8 (`i2c1_sda_sel`) is write-only / reads-as-zero.**
  Never RMW expecting bit 8 to survive; readback cannot verify the SDA mux.
- ⚠️ **`DIPLEX2` upper bits (3..18) are write-only.** Use the whole-register
  constants `HD2_DIPLEX2_LCD_I80`/`HD2_DIPLEX2_PTC_GPIO` in
  `platform/targets/HD2/pinmap.h`; never RMW. The old '8' diag op's `~0x7ff00` mask
  missed CS/RS/WR (bits 3-7) — that dead end wasted the early LCD exploration.
- ⚠️ **SPI0 FIFOs are 8 deep, NOT the manual's 128.** Bursting >8 silently
  drops frames — symptom is "reads fine, saves silently skipped" (≤8-byte ops
  work, bulk fails). Host-paced probes can't catch it (FIFO drains between
  pokes). Always chunk to 8.
- ⚠️ **SPI0 EEPROM-read TMOD (11) is broken on this variant** — the slave's
  reply dies after one byte. Don't retry it; use plain full-duplex TX&RX with
  dummy frames.
- ⚠️ **Don't assert `IC_START` mid-load on I2C1.** The HR_C7000 quirk transfers
  whatever is in the FIFO; starting after the first byte fragments the write
  and it silently does nothing (no abort) — this was the original HW-I2C wedge.
- ⚠️ **`platform_init` mux ordering.** The AT1846S constructor runs `i2c0_init()`
  at static-init (pre-`main`), so `platform_init`'s later `IO_DIPLEX0` write must
  not re-steal PTA7/8 — the original wedge was a `0x1e0` write that re-muxed them
  to GPIO. Fixed: `platform.c` writes the whole-register baseline `IO_DIPLEX0=0x60`
  (bits 7/8 clear → I2C1 controller owns the pins), and `AT1846S::init()` re-asserts
  `i2c_init()` (→ `i2c0_init()`, idempotent) defensively at bring-up.
- The bit-bang SPI/GPIO paths need a `sync` barrier (`MMIO_BARRIER()`) between
  back-to-back GPIOA DR writes or the store buffer drops them at MCU speed.
- ⚠️ Settings persist only on the **clean knob-off shutdown path** — an unplug
  skips the flash save.
- GPS: if no bytes echo (build with `-DHD2_GPS_DEBUG`), suspect UART2 RX / GPS
  power PTB15 / the DIPLEX0 RXD mux. If NMEA flows but no fix, it's antenna /
  sky-view / cold-start. Don't set DIPLEX0 bits 11/12 back after TX — that
  re-muxes RXD to GPIO and kills polled RX.
- ⚠️ **0xE0 is an RTC, not a PMU/codec/charger** — don't re-investigate it for
  those. Backlight GPIO/PWM, the audio codec, and the charger gauge remain
  unmapped I2C-wise (all likely SoC-internal, not I2C devices).
- ⚠️ **The `0x140d0034` "keypad row sense ADC" is a dead end** for reading the
  matrix; rows are read straight from GPIOC EXT_PORT bits 7..10.

## Where the code lives

- I2C1 radio bus: `vendor/wt-hd2-vp-adpcm/platform/mcu/HR_C7000/drivers/i2c1_hd2.c`
- Keypad: `vendor/wt-hd2-vp-adpcm/platform/drivers/keyboard/keyboard_HD2.c`
- GPS UART2: `vendor/wt-hd2-vp-adpcm/platform/drivers/GPS/gps_HD2.c`
- ADC: `vendor/wt-hd2-vp-adpcm/platform/drivers/ADC/adcHrc7000.c`
- GPIO: `vendor/wt-hd2-vp-adpcm/platform/drivers/GPIO/gpio_hrc7000.c`
- LCD: `vendor/wt-hd2-vp-adpcm/platform/drivers/display/ST7735S_HD2.c`
  (see the [display chapter](11-display-ui-codeplug))
- Pad-mux + register aliases: `platform/mcu/HR_C7000/registers.h`
  (`SOCSYS->IO_DIPLEX0/1/2`, `HD2_DIPLEX2_*`, the `I2C_TypeDef`/`GPIO_TypeDef`
  offsets, `GPIOA`/`B`/`C`, `I2C1`/`I2C2` bases)
- ⚠️ SPI0 transport (`spi_hd2.c`) + W25Q flash (`flash_w25q_HD2.c`) live only in
  `vendor/OpenRTX/platform/drivers/{SPI,NVM}/` — the `vp-adpcm` build stubs NVM
  (`nvmem_stub.c`), so those sources are absent from the live worktree. The HW-SPI0
  facts in this chapter were verified on the `hd2-w25q-hw-spi0-migration` branch.

## Status & deeper reading

**Status: ✅ HW-verified** for I2C1 (2026-07-23), SPI0/W25Q, LCD i8080, keypad
matrix, GPS, and battery ADC (2026-05/06). 🟡 in-progress: rotary
encoder GPIOA pin numbers (0/1) and the full vendor keycode LUT are unverified;
the docs describe a vendor 4×6 matrix while the driver ships a 4×4 + discrete
side keys (see open questions).

Source docs and memory this chapter distills:
- `docs/TASK_hw_i2c_migration.md` — the HW-I2C1 migration handoff
- `docs/i2c_dev_0xE0.md` — the 0xE0 RTC identification
- `docs/keypad.md` — vendor keypad-matrix decomp
- `docs/gps_power_renames.md` — GPS/UART + power-management renames
- memory `hd2-hw-i2c-wedge-solved` — DIPLEX0 bit8 write-only + mux-theft wedge
- memory `hd2-w25q-hw-spi0-migration` — 8-deep FIFO + broken EEPROM TMOD
- memory `hd2-lcd-i8080-migration` — i8080 config + keypad re-mux dance
