---
title: "05. FM broadcast receive (RDA5802E)"
---

# 05. FM broadcast receive (RDA5802E)

## What it is / how it works

The HD2's "FM radio" (broadcast) feature is a **dedicated RDA Microelectronics
RDA5802E** single-chip broadcast-FM tuner — **not** the AT1846S 2-way
transceiver and **not** the HR_C7000 modem/codec. Broadcast audio comes out of
the RDA5802E as **analog** and is gated to the speaker by GPIO. There is no DSP,
codec, or digital-modem stage in the broadcast path — the HR_C7000 modem need
not run at all (verified: the vendor's modem RX IRQ latch `0x11000398` reads 0
while it is audibly playing FM).

The chip shares the AT1846S's radio I2C bus (SCL=PTA7, SDA=PTA8) at **8-bit
write address `0x20`** (7-bit `0x10`) — the
RDA5802E *sequential access* address. In sequential mode registers are 16-bit,
MSB-first, and there is **no `[reg][val]` random access**: every write starts at
register `0x02` and auto-increments (`0x02 hi, 0x02 lo, 0x03 hi, 0x03 lo, …`,
wrapping `0x3A → 0x00`); every read starts at register `0x0A` and
auto-increments. Verified on hardware 2026-06-08: tuning 97.7 MHz plays real
program audio out the speaker.

The tuner is driven by the portable **`OpMode_FMBroadcast`** (opMode
`OPMODE_FM_BCAST`), selected by the UI FM screen via `rtx_configure`.
`OpMode_FMBroadcast` calls a weak **`tuner_*` HAL** (`interfaces/tuner.h`) whose
strong HD2 overrides (`tuner_powerUp/powerDown/tune/rssi/getStatus`) live in the
RDA5802E driver. The old standalone worker thread is gone — it fought `rtx.cpp`
for the shared audio path.

> ⚠️ **Branch note.** This feature lives in `vendor/OpenRTX/` on branch
> **`hd2-miosix-app`**; it is **not** in the shipping `vendor/wt-hd2-vp-adpcm/`
> tree that `docker/build.sh` builds. HW-verified on `hd2-miosix-app`; merge
> forward before it ships in the VP-ADPCM firmware. All paths below are
> `vendor/OpenRTX/…` for that reason.
>
> **I2C transport differs by branch.** On this branch the driver still
> **bit-bangs** the radio bus via the old `CSKY_V2` `i2c_csky.h` (`i2c0_init`/
> `i2c0_write`/`i2c0_read`, SCL=PTA7/SDA=PTA8). The shipping tree has since moved
> the AT1846S onto the HW DesignWare **I2C1** controller `@0x14070000`
> (`i2c1_hd2.c`) and **removed the `CSKY_V2` bit-bang tree** — see the
> [FM analog chapter](04-fm-analog) and the [buses chapter](10-buses-peripherals).
> So merging this forward means porting the RDA5802E off `i2c0_*` onto the same
> `i2c1_hd2.c` transport (both devices are on that one bus — RDA5802E `0x20`,
> AT1846S `0xE2`).

## How to implement it

Two GPIOB output bits control the subsystem (both active-LOW), LIVE-verified by
before/after MMIO diff while playing:

| Pin | Macro | FM active | standby | Role |
|---|---|---|---|---|
| **PTB20** | `FM_ENABLE_BIT` | LOW | HIGH | chip enable / reset |
| **PTB10** | `AUDIO_ROUTE_BIT` | LOW | HIGH | broadcast audio → speaker route |
| **PTB4** | `SPKR_AMP_BIT` | LOW=on | — | speaker-amp mute (shared, audio-gated) |
| **PTB17** | `SPKR_GAIN_BIT` | HIGH | — | analog **path select** — *not* a gain (see below) |

> ⚠️ **PTB17 is a path select, not a gain, and the macro suffix differs by
> branch.** Despite the `SPKR_GAIN_BIT` name, PTB17 is the amp's 2:1 analog
> **source select**: HIGH steers the amp to the AT1846S/analog leg (which the
> broadcast tuner shares) — it only *looked* like a "gain" because the other
> source, the codec DAC, was silent during FM RX. Read the
> [audio-path chapter](03-audio-path) for the full model. Also note the macro
> names: this `hd2-miosix-app` branch's `hd2_regs.h` uses the `_BIT` suffix
> (`FM_ENABLE_BIT`/`AUDIO_ROUTE_BIT`/`SPKR_AMP_BIT`/`SPKR_GAIN_BIT`), while the
> shipping `wt-hd2-vp-adpcm` `registers.h` calls the shared pins
> `AUDIO_ROUTE_PIN`/`SPKR_AMP_PIN`/`SPKR_GAIN_PIN` — grep both suffixes.

Key registers (16-bit, sequential):

- **`0x02`** config word: `DHIZ`(b15, 1=output normal / 0=high-Z ⇒ **silent**),
  `DMUTE`(b14, 1=unmute), `SOFT_RESET`(b1), `ENABLE`(b0). `0xc601` (init) and
  `0xc201` (tune) both set DHIZ+DMUTE+ENABLE; teardown uses `0xc200` (ENABLE=0).
- **`0x03`**: `CHAN[9:0]`(b15:6), `TUNE`(b4), `BAND[3:2]`, `SPACE[1:0]`.
  HD2 uses BAND=`10` (76–108 MHz), SPACE=`00` (100 kHz). `CHAN =
  (f_kHz − 76000) / 100`.
- **`0x05`**: `SEEKTH` / `LNA_PORT_SEL` / `VOLUME[3:0]` — init sets `0x88af`
  (LNAP input, VOLUME=max).
- read **`0x0A`**: `STC`(b14, tune complete), `ST`(b10, stereo), `READCHAN[9:0]`.
- read **`0x0B`**: `RSSI[6:0]`(b15:9), `FM_TRUE`(b8, station present), `RDY`(b7).

Ordered power-up recipe (see `fm_broadcast_powerup` / `tuner_powerUp` in
`RDA5802E_HD2.c`):

1. `i2c0_init()`; set PTB20+PTB10 as outputs, parked HIGH (standby).
2. Pulse PTB20 HIGH (reset) `delayUs(10)`, then LOW (active), `delayMs(1)`.
3. Sequential-write the **64-byte factory init block** starting at reg `0x02`
   (`fm_init_seq[]`, head `0xc6 0x01 0x00 0x0a 0x04 0x00 0x88 0xaf …`, read live
   from flash `0x0307ade4`). `delayMs(2)`. Leaves the chip ENABLEd, non-high-Z,
   unmuted, VOLUME=max, BAND=10.
4. Route audio (`fm_broadcast_route_speaker`): PTB10 LOW (route), PTB4 LOW
   (amp on), PTB17 HIGH (select the AT1846S/analog leg the tuner shares — not a
   gain; see ch.03).
5. Mute the AT1846S 2-way demod on the shared analog node
   (`hd2_at1846s_afmute(1)`).

Tune (`fm_broadcast_tune`): one sequential burst of regs `0x02`/`0x03` —
`fm_write_02_03(0xc201, (chan<<6)|0x10|(0x2<<2))`, bit-identical to the vendor's
`{0xc2,0x01,chan>>2,((chan&3)<<6)|0x18}`.

Status/RSSI: a 4-byte sequential read from reg `0x0A`. STC = `b[0] & 0x40`;
READCHAN = `((b[0]&0x03)<<8)|b[1]`; RSSI = `b[2] >> 1`. The HAL folds this into
`g_fm_rssi` (low byte = RSSI, bit8 = lock).

## Gotchas & cautions

- ⚠️ **Silent-until-nudge regression (SOLVED 2026-06-14).** After converging to
  `OpMode_FMBroadcast`, entering the FM screen was silent until a manual UP/DOWN
  nudge. Root cause was **not** a chip power-up settle issue (chased that twice,
  wrong). `ui.c::ui_updateFSM`'s "disable TX outside VFO/MEM" block sets
  `*sync_rtx = true` on the same event that opens the FM screen; `threads.c`
  then re-posts the **channel** config (`OPMODE_FM`), switching the opMode away
  from `FM_BCAST` and running `disable() → tuner_powerDown()`. It fires once
  (`txDisable` latches), so a single nudge re-posts `FM_BCAST` and revives it.
  **Fix:** after the txDisable block, `if(state.ui_screen == FM_RADIO)
  *sync_rtx = false;` — broadcast owns its rtx config while its screen is open.
  (Exit sets `ui_screen = MAIN_VFO` first, so the restore sync still runs.)
- ⚠️ **Don't model this chip as `[reg][val]` 8-bit writes with a `&0x7f` mask.**
  `scripts/labels/fm_broadcast.py` did — it is **wrong** for an RDA5802E in
  sequential mode (a 2-byte write only ever touches reg `0x02`). Its register
  numbers (0x40/0x42/0xc2…) are artifacts of that mis-model, not chip registers.
  The `.c` driver has the correct decode.
- ⚠️ **`DHIZ=0 ⇒ audio output high-Z ⇒ silent.** Keep reg `0x02` bit15 set.
- ⚠️ **Random/indexed access is a different address** (7-bit `0x11`); the HD2
  does not use it. Don't reach for it.
- The RDA5802E shares the analog speaker node with the AT1846S 2-way AFOUT (the
  same amp-input select and route bits described in the
  [audio-path chapter](03-audio-path)) —
  **mute the transceiver demod** (see the [FM analog chapter](04-fm-analog))
  while broadcast plays or its noise mixes in.
- PTB4 flutters (audio/squelch-gated) and is **not** a deterministic FM-control
  bit; the two deterministic bits are PTB20 and PTB10.
- Corrected pin myths: enable is **PTB20, not GPIOB.0** (that's the green LED);
  route is **PTB10, not PTB14** (`AUDIO_ROUTE_WIDE_BIT` did not move).
- Broadcast tuning is slow-moving; poll at ~4 Hz (`sleepFor(0, 250)`) to keep
  the shared GPIOA I2C bus quiet.
- Live GPIOB_DR (`0x14100000`) fingerprints: playing = `0x0042e004`,
  powered-down/standby = `0x0050e414` — reading the powered-down pattern while
  `g_fm_active=1` is the smoking gun that `disable()` ran.

## Where the code lives

- `vendor/OpenRTX/platform/drivers/baseband/RDA5802E_HD2.c` — driver +
  `tuner_*` HAL overrides (`fm_broadcast_powerup/tune/status/rssi/route_speaker/
  powerdown`).
- `vendor/OpenRTX/openrtx/src/rtx/OpMode_FMBroadcast.cpp` — portable opMode +
  weak `tuner_*` defaults.
- `vendor/OpenRTX/platform/targets/HD2/hd2_fm_broadcast.cpp` — UI↔driver bridge
  globals (`g_fm_active`, `g_fm_rssi`, `g_fm_mode`; `g_fm_test_freq` lives in
  `radio_HD2.cpp`).
- `vendor/OpenRTX/openrtx/src/ui/default/ui.c` — `_ui_fmBcastConfigure`, the FM
  screen, and the `ui_updateFSM` `sync_rtx` guard (the regression fix).
- Datasheet: `vendor/RDA5802E-RDA.pdf`. Init-block provenance:
  `tmp/fm_probe/init_block_0307ade4.txt`.

## Status & deeper reading

**Status: ✅ HW-verified** on branch `hd2-miosix-app` (tuner + speaker path
2026-06-08; silent-until-nudge regression SOLVED + HW-verified 2026-06-14).
🟡 **Not yet merged into the shipping `wt-hd2-vp-adpcm` tree.**

- `docs/fm_broadcast_rda5802e.md` — chip access model, register table, GPIO map.
- `tmp/vendor_fm_playing_state.md` — vendor HR_C7000 register state while
  playing (confirms modem-run theory is dead; broadcast is pure analog).
- memory: `hd2-fm-broadcast-opmode-silent-regression` — root cause + live
  GPIO/RSSI debug recipe (`g_fm_rssi` @ `0x20ea8`, `g_fm_test_freq` @ `0x209c0`,
  `g_fm_active` @ `0x20eac`).
