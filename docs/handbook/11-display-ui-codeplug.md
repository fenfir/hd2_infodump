---
title: "11. Display, UI, menus & codeplug"
---

# 11. Display, UI, menus & codeplug

The HD2 stacks four layers between the LCD glass and the flash codeplug: a
byte-banged/parallel ST7735S driver, a uGFX-style widget/screen renderer, a
table-driven menu state machine, and a vendor-format codeplug backend that the
OpenRTX port reads and writes in place. This chapter distils the settled model
of each, with the OpenRTX driver as the working reference and the vendor
firmware RE as the ground truth for layout.

## What it is / how it works

**Panel.** A 160×128 RGB565 **ST7735S** TFT. On the HD2 it is not wired to SPI
— the vendor firmware bit-bangs an 8080-style 8-bit parallel bus through a
single 32-bit GPIO latch, and the SoC also exposes a **hardware i8080
controller at `0x12000000`** that drives the same panel far faster (one
register write = one bus cycle). The shipping driver (`ST7735S_HD2.c` in the
live `wt-hd2-vp-adpcm` tree) is **HW-i8080 only**; the GPIO-latch bit-bang
survives only as a compile-time fallback (`#if HD2_LCD_BITBANG`) in the
`vendor/OpenRTX` reference tree. Both share the canonical ST7735S init sequence
(frame-rate B1/B2/B3, power C0–C5, 16-byte +/- gamma E0/E1, `MADCTL=0xA0`
landscape, `COLMOD=0x05` RGB565). There is no DMA and, in the OpenRTX build, no
driver-side framebuffer — the graphics layer owns the single 40 KiB `.bss` and
pushes strips down via `display_renderRows()`.

**Backlight** is a separate PWM subsystem, not an LCD command: **PWM channel 0
at `0x140C0000`**. Brightness is a LUT-driven duty cycle applied on a 100 ms
tick with sleep/wake inactivity gating (see the brightness chain below).

**UI stack.** Above the driver sits a uGFX-2.x-style widget framework
(`widget_create`, `widget_find_by_id`, per-widget draw callbacks, a 32-byte
palette block at widget `+0x28`) driven by an event-pump task
(`task_display_entry @ 0x030444e4`). The real screen state machine is
**`menu_main_dispatcher @ 0x0304f560`** reading a 3-byte `g_screen_state`
struct at IRAM `0x000432c8`: byte `+0` = top-level mode, `+1` = menu section
(0..21), `+2` = screen index. Rendering and key handling are dispatched through
parallel per-section function-pointer tables; menu labels and picklist values
come from a flat 121-entry string catalog (`g_menu_value_strings_table @
0x0307aff4`).

**Codeplug.** Channels/contacts/zones live in the **Ailunce/Dahua vendor
on-flash format** on the W25Q512 (HW SPI0; see the
[buses chapter](10-buses-peripherals) for the flash transport). The OpenRTX port reads and writes
the factory records *in place* — no native store, no import step — translating
each 176-byte vendor channel record to `channel_t` on the fly and doing
load-modify-save on write so vendor-only bytes survive a round-trip.

## How to implement it

### LCD bring-up (OpenRTX `display_init`, HW i8080 path — HW-verified)

1. `bus_init()` → program the i8080 write-strobe timing: `I80_WCFG
   (0x12000010) = 0x00020202` (2 leading / 2 active / 2 trailing cycles;
   ~143 ns at 42 MHz, well over the ST7735S 66 ns min).
2. Reset pulse over the **GPIO latch** (RST = **PTC2**, GPIO-only, never muxed
   to the i8080): `RST high, 10 ms; RST low, 10 ms; RST high, 120 ms`.
3. `send_cmd(0x11)` SLPOUT, 120 ms.
4. Frame rate: `0xB1/0xB2` = `05 3C 3C`; `0xB3` = `05 3C 3C 05 3C 3C`; `0xB4` =
   `03`.
5. Power: `0xC0`=`28 08 04`, `0xC1`=`C0`, `0xC2`=`0D 00`, `0xC3`=`8D 2A`,
   `0xC4`=`8D EE`, `0xC5`=`1A`.
6. Gamma: `0xE0` 16 bytes (`04 22 07 0A 2E 30 25 2A 28 26 2E 3A 00 01 03 13`),
   `0xE1` 16 bytes (`04 16 06 0D 2D 26 23 27 27 25 2D 3B 00 01 04 13`).
7. `0x36` MADCTL = `A0` (landscape, RGB order); `0x3A` COLMOD = `05` (RGB565).
8. Set full window (`CASET 0..0x9F`, `RASET 0..0x7F`), `RAMWR (0x2C)`, stream
   zeros to blank GRAM, then `0x29` DISPON.
9. `backlight_init()` then `display_setBacklightLevel(50)` — the threaded build
   links `main.cpp`, so without an explicit `backlight_init()` the PWM stays
   uninitialised and every `display_setBacklightLevel()` (Settings brightness
   *and* UI standby level 0) is a silent no-op.

Register writes: `I80_INDEX (0x12000000)` = command cycle (RS=0), `I80_DATA
(0x12000004)` = data cycle (RS=1). Pixels ship big-endian (`v>>8` then `v&0xFF`).
The i8080 pad mux is DIPLEX2 bits 3..18 = func 0, set by `platform_init` and
swapped transiently around keypad scans (`keyboard_HD2.c`).

### GPIO-latch fallback bit layout (`GPIOC_DR`, corrected map)

| bit | mask | role |
|----:|------|------|
| 2 | `0x004` | RST (active-low) |
| 3 | `0x008` | CS (active-low; held low for the whole transaction) |
| 4 | `0x010` | DCX (0 = command, 1 = data) |
| 5 | `0x020` | WR strobe — panel latches on the **rising** edge |
| 6 | `0x040` | RD (held high for writes) |
| 7..14 | `0xFF80` | D0..D7 (`byte << 7`) |

⚠️ The earlier map had WR and CS swapped (WR=bit3, CS=bit5) — it strobed CS and
held WR high, the panel never latched, permanent white screen. Do not revert to
it.

### Backlight PWM chain (vendor `pwm_channel_start @ 0x03059d20`)

`base = 0x140C0000 + ch*0x20` (ch 0 = backlight, ch 1 = audio). Sequence: clear
RUN/LOAD/mode bits, set mode bit `0x20` + enable bits `0x100|0x200`; `+0x04`
PRESCALER = 5; `+0x08` PERIOD = `CLK_CONST/freq` (`0x1068` @ 10 kHz); `+0x0C`
DUTY = `PERIOD * dutyN / 10000`; set LOAD (`0x04`) then RUN (`0x01`). Brightness
callers pass `(0, 10000, lutval)` where `lutval` comes from the 9/10-entry
`u18Brightness` LUT at `g_tune_data_struct + 0x1ac + 2*idx`, `idx =
g_state[0x4c]`. Live duty range `0x200`..`0xC84` (~5%..19% of `0x1068`), with a
`max(duty, 0xf)` minimum-on clamp. Apply driver: `backlight_tick @ 0x03058470`
on the 100 ms tick — counter==0 (just woken by `backlight_kick @ 0x0305851c`,
any key) re-applies the LUT duty; counter==`state[0x22]*10` zeroes duty (sleep;
PWM keeps running, only duty goes to 0). Menu commit `setting_set_brightness @
0x0304b390` only writes state + persists via `settings_mark_dirty @ 0x03056ca0`
(`nvram_write(g_state, 0x60)`) — **no HW poke on commit**; the tick applies it.

### Menu dispatch (vendor `menu_main_dispatcher @ 0x0304f560`)

`g_screen_state @ 0x000432c8`: `state[0]` mode, `state[1]` section (0..21),
`state[2]` screen index. Mode `2` = main menu; it fast-paths `state[1] ∈
{0,3,4,8}` and routes everything else to shared tables:

- `state[1]==0` "Main Set" → render `main_64 @ 0x0307cc9c` (31 valid entries),
  keyhandler `0x0307b4b0`.
- `state[1] ∈ {1,2,5,6,7,9..20}` → render `catchall_30 @ 0x0307cd24`,
  keyhandler `0x0307b530` (shared; each thunk disambiguates by reading
  `state[1]` in its own body).
- `state[1]==3` → `settings_4 @ 0x0307d0c0`; `==4` → `dmr_3 @ 0x0307c22c`;
  `==8` → `submenu_32 @ 0x0307cd1c` (the reused tail idx 32..63 of `main_64`).

Index dispatch is `fn = u32(render_table + state[2]*4) & ~1; fn()`. Section
titles + per-section screen counts are three parallel arrays keyed off
`g_menu_value_strings_table @ 0x0307aff4`: `+0x216` screen count (22×u8),
`+0x220` page count, `+0x22c` title ptrs (`g_menu_topbar_titles_table @
0x0307b220`). `format_page_indicator @ 0x0304639c` draws "title N/M". Each
main-table renderer is a value-readback thunk: it calls one of three
screen-template helpers (`0x030467d4`/`0x03046804`/`0x03046f08`), reads one
`g_state` byte, and writes it to `g_keypad_state[+0xE]` (the displayed
"selected value", capped by `g_screen_timer_limit_table @ 0x0307ca78`). Key
codes: `0x0D` ENTER, `0x11` UP, `0x13` DOWN, `0x1B` EXIT, `0x30..0x39` digits.

### Channel record & codeplug (OpenRTX `cps_io_HD2.c`, HW-verified round-trip)

The 176-byte vendor channel record (`hd2_vendor_channel_t`, `hd2_cps_records.h`):

| off | field | encoding |
|----:|-------|----------|
| `0x00` | `marker[4]` | `0xFFFFFFFF` = populated slot |
| `0x04` | `name[10]` | ASCII, NUL/0xFF padded |
| `0x14` | `rx_freq[4]` | 4-byte LE packed BCD, value ×10 Hz |
| `0x18` | `tx_freq[4]` | same |
| `0x1C` | `contact_id` | LE 24-bit DMR TX contact ID |
| `0x21` | `opt21` | bit0 ScanAdd, bit1 Talkaround, bits3:2 Power, **bit6 DMR_MODE** (set=DMR), bit7 Relay |
| `0x28` | `opt28` | bit7 2nd-TX, bits6:5 enc family, bits3:0 key index |
| `0x29` | `opt29` | bit0 Promiscuous, bits5:4 TX-authority, **bit6 BW_WIDE** (set=25 kHz) |
| `0x2A` | `cc_ts_dmr` | bits7:4 color code, bit0 TS2, bits3:1 DMR mode (Simplex/Repeater/Double) |
| `0x24`/`0x26` | `rx_tone`/`tx_tone` | 2-byte LE CTCSS/DCS, `0xFFFF`=none |
| `0x30..0xAF` | `rx_list[32]` | inline `uint32_t` DMR IDs, `0xFFFFFFFF`-terminated |

Tone encoding: CTCSS = frequency in 0.1 Hz as 4 BCD nibbles (`70 06` → `0x0670`
→ 67.0 Hz). DCS = high byte `0x80` normal / `0xC0` inverted, octal code packed
`hundreds=hi&0x0F, tens=lo>>4, ones=lo&0x0F`. `decode_tone`/`encode_tone` are
exact inverses.

OpenRTX channel index `pos` maps to **vendor slot `pos + 2`** (slots 0/1 are
VFO A/B defaults, not exposed). Read: `hd2_vendor_channel_read(pos+2)` →
present-check → `vendor_to_channel`. Write: load slot, overlay owned fields
(`channel_to_vendor`), `hd2_vendor_channel_write(pos+2)` — a 4 kB-sector
read-modify-write because a 176-byte record straddles sector boundaries.
`cps_create()` returns `ENOTSUP`; contacts and zones are read-only.

On-flash bases (OpenRTX backend): priority contacts `0x006E1000` (72 B, 14/block),
**channel slots `0x006F3000`** (176 B, contiguous from `base+0x80`, so
`base + 0x80 + index*0xB0`), zones `0x00880000` (145 B), OpenRTX settings
`0x00FFF000`, vendor settings mirror `0x00FEE000`. Dual channel-presence bitmap
at `HD2_BITMAP_BASE = 0x00792000` (bm1 `+0`, bm2 `+0x177`); **bit clear =
populated**, indexed by real-channel index (VFO slots not counted). `bm1` must
equal `bm2` or the vendor firmware treats it as tamper and self-destructs —
any writer updates both copies.

## Gotchas & cautions

- **Backlight init is mandatory in the threaded build.** No `backlight_init()`
  ⇒ `bl_initialised=0` ⇒ `display_setBacklightLevel()` silently no-ops for both
  Settings brightness and standby. (`ST7735S_HD2.c` calls it in `display_init`.)
- ⚠️ **Do not use the old GPIO-latch bit map** (WR=bit3, CS=bit5) — it never
  latches, permanent white screen. Corrected map: CS=bit3, WR=bit5.
- **RST (PTC2) is GPIO-only** — it is never muxed to the i8080 controller, so
  the reset pulse always goes through the latch even on the HW-i8080 path.
- ⚠️ `screen_state_set @ 0x03058450` in the vendor RE is **mis-named** — it is a
  **beep-tone request** (`beep_request`), not a screen-state setter. Earlier
  notes claiming "channel mode = `screen_state_set(0)`" are wrong. Note the
  name collision: `menu_functions.md` also applies the label `screen_state_set`
  to a *different* address (`0x0304b450`, sets `state[7]`) — treat both labels
  as suspect.
- ⚠️ `task_menudisp_entry @ 0x030403a4` is **not** the display task — it is an
  RF/squelch tuning task (`task_rf_squelch_apply`). The real UI pump is
  `task_display_entry @ 0x030444e4`.
- **catchall_30 renderers are shared across 17 sections** — the dispatch table
  does not encode which visible label each slot shows; the renderer body checks
  `state[1]` at runtime. Don't expect a static section→label map from the table
  alone.
- **The channel base differs between sources.** The OpenRTX vendor-backed
  backend places channel slots at `0x006F3000` (176 B). The vendor-firmware RE
  (`docs/channel_config.md`) reads channels at `0x006E1000` with stride
  **0x48** and calls `0x6F3000` a runtime cache. These disagree on both base
  and record size — reconcile before trusting either for a raw flash poke (see
  open questions).
- **W25Q is SPI-accessed, not memory-mapped** — dbgshell `0xDD` memory reads at
  flash offsets fault. Read the codeplug over the CPS protocol
  (`hd1_dump.py`), not by memory read.
- ⚠️ CPS address arithmetic is region-dependent: `b1=0x0F` regions are flat
  `physical = radio_addr + 0x790000`; `b1=0x31` regions are `addr<<10`
  (`block×0x400`). Don't apply one rule to the other.
- **Brightness commit does not touch hardware** — `setting_set_brightness` only
  writes state + persists; the 100 ms `backlight_tick` applies it. A commit
  path that pokes PWM directly diverges from the vendor timing.

## Where the code lives

- `vendor/wt-hd2-vp-adpcm/platform/drivers/display/ST7735S_HD2.c` — LCD driver
  (shipping build; HW-i8080 only). The GPIO-latch bit-bang fallback
  (`HD2_LCD_BITBANG`) is retained only in `vendor/OpenRTX/`'s copy.
- `vendor/wt-hd2-vp-adpcm/platform/drivers/backlight/backlight_HD2.c` — PWM
  backlight (owns `display_setBacklightLevel`, moved here from the display driver).
- `vendor/OpenRTX/platform/drivers/NVM/cps_io_HD2.c` — vendor-backed `cps_io.h`
  backend (channel translate + read/write). ⚠️ The codeplug backend below lives
  only in `vendor/OpenRTX/`; the live `wt-hd2-vp-adpcm` build currently links
  `cps_io_stub.c`, so the round-trip is not yet in the shipping firmware.
- `vendor/OpenRTX/platform/drivers/NVM/nvmem_vendor_records_HD2.c` — channel
  read+write, contact read.
- `vendor/OpenRTX/platform/targets/HD2/hd2_cps_records.h` — 176-byte channel /
  72-byte contact structs + BCD/tone helpers.
- `vendor/OpenRTX/platform/targets/HD2/hd2_cps_settings.h`,
  `hd2_cps_settings_export.c` — vendor settings block + `settings_t` adapter.
- `src/firmware/include/lcd.h` — latch bit definitions for the bit-bang path.

## Status & deeper reading

**Status: ✅ HW-verified** for the LCD driver (i8080 pixels drawn live
2026-06-13) and the backlight PWM chain (live 2026-05-13/14) — both in the
shipping `wt-hd2-vp-adpcm` build. The codeplug channel round-trip is 🟡
**verified in `vendor/OpenRTX/` only** (0 failures on `cp_ai5qz_germany.bin`,
40 channels) and not yet linked into the shipping build. The
menu tree / renderer maps are 🟡 **RE-derived** from the vendor binary
(grounded in `ui_dump_menu_tree.py`) — trustworthy for navigation but not fully
label-decoded for the shared `catchall_30` sections.

Source docs distilled here:
- `docs/lcd_driver.md`, `docs/brightness_chain.md`
- `docs/ui_state_renderer.md`, `docs/menu_tree.md`, `docs/menu_functions.md`
- `docs/channel_config.md`, `docs/codeplug_vendor_backed.md`
- `docs/menu_template_payloads.md`, `docs/widget_event_system.md` (referenced
  follow-ups on catchall labels + the widget event dispatcher)

Related chapters: LCD i8080 bus / W25Q SPI0 / keypad matrix
([buses & peripherals](10-buses-peripherals)), the audio PWM channel and
codec-DAC leg ([audio path](03-audio-path)), DMR/FM channel RF apply
(`rf_apply_channel_to_pll @ 0x03059090`).
