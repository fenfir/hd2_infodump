---
title: "03. Audio path & routing"
---

# 03. Audio path & routing

## What it is / how it works

The HD2 speaker amp has **two independent inputs**, selected by one GPIO. An
**analog route** carries the AT1846S FM demodulator's AFOUT (2-way FM RX) and
the RDA5802E broadcast tuner straight to the amp — the HR_C7000 codec/modem is
*not* in that path. A **codec-DAC leg** carries everything the CPU generates
(voice prompts and key beeps — see the [voice-codecs chapter](07-voice-codecs)
for the players that ride this leg — DMR voice RX, arbitrary PCM streaming):
the HR_C7000 codec DACs an 80-sample frame and drives a class-D PWM lineout into
the same amp. Which source the amp listens to is decided by **PTB17**.

The one fact that governs everything here: **GPIOB PTB17 is the analog PATH
SELECT.** `HIGH` = AT1846S analog demod (FM RX); `LOW` = codec-DAC lineout (MCU
beep / voice prompt / PCM playback). Each source must be paired with its side of
this bit. The months-long "our AT1846S AFOUT is quiet" mystery and the later
"codec DAC plays digitally but is silent" mystery were the *same* bit pointed the
wrong way.

> ⚠️ **Legacy label.** Older notes and the `SPKR_GAIN_PIN` macro name call PTB17
> a "speaker-amp gain/enable." It is not a gain — HIGH only *looked* like "gain"
> because the alternative source (the codec DAC) was silent during FM RX. Treat
> it as a 2:1 source select. The macro keeps the old name; the code comment in
> `registers.h` documents the true meaning.

The codec leg is fed not by DMA but by the modem's **100 Hz PCM frame IRQ**.
Once the PCM bridge is armed the modem requests one 80×s16 frame every 10 ms
(8 kHz mono); the ISR acks a handshake bit and copies the next frame into a
shared-SRAM (SAHB) mailbox window that the codec block DACs. The same mechanism
runs in reverse for capture (mic ADC or FM-demod audio → CPU-readable PCM),
which is what enables software modems like APRS/SSTV RX (the
[APRS chapter](09-aprs) is the worked example of this capture path).

## How to implement it

**Board-level routing GPIOs (GPIOB, pin macros from `registers.h`):**

| Line | Macro | Meaning | Value for FM RX | Value for codec/PCM playback |
|---|---|---|---|---|
| PTB4 | `SPKR_AMP_PIN` | speaker amp mute (active-LOW) | LOW = un-muted | LOW = un-muted |
| PTB10 | `AUDIO_ROUTE_PIN` | analog RX route gate | LOW = routed | LOW (also routed) |
| PTB17 (bit17, mask 0x20000) | `SPKR_GAIN_PIN` | **analog PATH SELECT** | **HIGH = AT1846S source** | **LOW = codec-DAC source** |

**Analog FM RX → speaker** (`SOURCE_RTX → SINK_SPK` in `audio_HD2.c`): the heavy
AT1846S AF-DSP config + chip-side un-mute (reg 0x30 bit7) runs once in
`radio_enableRx` (see the [FM analog chapter](04-fm-analog)); the
per-squelch-crossing gate is then pure GPIO. The analog
`spkr_amp_unmute()` drives PTB4 LOW (amp on) **and** PTB17 HIGH (select the
AT1846S), and `rx_route_on()` drives PTB10 LOW. Squelch close (`audio_disconnect`)
re-mutes PTB4 and closes the route (PTB10 HIGH), leaving the AT1846S AF config in
place so the next open is one GPIO toggle.

**CPU PCM / voice-prompt / beep playback → speaker** — the verified arming
recipe (`hd2_pcm_stream.cpp::hd2_pcm_tone`, HW-proven 2026-06-10; productized in
`outputStream_HD2.cpp`):

1. **Warm the codec + open the speaker node:** `hd2_audio_out_warm()` (latched,
   HW-verified constants live in `radio_HD2.cpp`); clear the DIPLEX0 audio-mute
   bit (`SOCSYS_IO_DIPLEX0 &= ~DIPLEX0_AUDIO_MUTE`, **bit 18**) which gates the
   codec-DAC/PWM leg to the amp; drive PTB4 + PTB10 LOW. **PTB17 must be LOW** to
   select the DAC source.
   *(`AUDIO_MUTE` is an upper write-only/read-as-zero bit, so this is exactly the
   RMW the gotcha below and [ch.10](10-buses-peripherals) warn against — a
   read-back can't confirm it. It is safe **only on DIPLEX0**: every other
   write-only upper bit there — the I2C1 mux 7/8 and UART2 mux 11/12 — also wants
   to be 0, so the RMW's zero-fill leaves them in their intended muxed state. Do
   not clone this pattern onto DIPLEX1/2, whose upper-bit target state is nonzero;
   those use whole-register constants instead. `hd2_audio_out_warm()` / step 7
   own the actual writes.)*
2. **Release the PCM blocks from reset:** `SOCSYS_SYS_SOFT_RSTN (0x11000000)
   |= 0x18` (bits 3+4; cleared = PCM blocks held in reset).
3. **Set PCM mode:** `SOCSYS_PCM_MODE (0x11000084) = 3`. (Write-only / mode-gated
   — reads back 0; do not diagnose by read-back.)
4. **Arm the voice path:** `SOCSYS_VOICE_PATH (0x11000080) |= VOICE_PATH_PCM_EN
   (bit0) | VOICE_PATH_PLAY (0x20)` for playback. (Capture side uses
   `VOICE_PATH_CAP = 0x10` instead of 0x20.)
5. **Register the frame IRQ:** `HD2_IRQ_PCM_PLAY` = vec 0x3b / PIC src 0x1b for
   playback; vec 0x3c / PIC src 0x1c for capture.
6. **Prime, then run.** *One-time kick* = write frame 0 into the playback window
   **then** ack — `SAHB_PCM_PLAY (0x180000a0)` = 80×s16, then
   `SOCSYS_INT_STATUS (0x110003b0) |= INT_STATUS_PCM_PLAY_ACK (0x20)`.
   *Steady-state ISR* = ack **first**, then write the next 80 samples (the vendor
   `pcm_isr_rd_body` order). Capture acks with `INT_STATUS_PCM_CAP_ACK (0x10)`.
7. **Stop** = restore the saved `VOICE_PATH` (disarming the play bits stops the
   frame IRQs), re-mute PTB4, re-set the DIPLEX0 audio-mute bit.

**FM-demod audio → CPU PCM capture** (`hd2_pcm_capture` / `hd2_aprs_rx`):
arm as above with `VOICE_PATH_CAP (0x10)`; read 80×s16 per 10 ms frame from
`SAHB_PCM_CAP (0x18000000)`, ack `INT_STATUS_PCM_CAP_ACK (0x10)` each frame. The
buffer carries the C7000 modem FM-demod audio (proven by signature: no carrier
→ pp ~3500 hiss, carrier → pp ~2200; mic speech = no change). **For data
(AFSK/SSTV) flatten the audio:** `AT1846S reg 0x58 |= 0xE0` (bit5 voice-LPF
bypass, bit6 voice-HPF bypass, bit7 de-emphasis bypass) or the 2200 Hz AFSK
space tone is rolled off to nothing.

## Gotchas & cautions

- **PTB17 is a PATH SELECT, not a gain.** Codec DAC silent while it clocks
  digitally = PTB17 stuck HIGH (amp listening to the AT1846S). Drive it LOW for
  all codec/PCM playback. Conversely FM-RX audio needs it HIGH.
- **The key beep MUST be a PCM tone, not a bare PWM tone.** The HR_C7000 PWM
  channel only sounds while a PCM stream is *already clocking* the codec DAC (the
  audio block, `SYS_SOFT_RSTN` bit3, is held in reset until a playback stream
  arms `|= 0x18`). A standalone PWM beep is silent. `platform_beepStart/Stop`
  are no-ops on HD2; emit the beep as a square-wave PCM tone through the output
  stream.
- **Prime write-then-ack at start, ack-then-write in steady state.** Acking
  first at start-up (the per-IRQ vendor order) syncs the modem PCM engine to an
  empty window → only frame 0 plays ("chirp"), never recovers (HW-observed
  2026-07-20). The one-time kick reverses the order; the ISR keeps the vendor
  order.
- **`PCM_MODE (0x11000084)` is write-only / mode-gated** — reads back 0 after a
  valid write. Never diagnose the bridge by reading it back.
- **A tone won't STOP by re-muting the amp alone** — you must disarm the bridge
  (restore `VOICE_PATH`/`PCM_MODE`), or the codec keeps looping the last SAHB
  frame.
- **RX-audio route must be closed on disconnect.** `audio_connect` opening PTB10
  LOW without a matching `audio_disconnect` close latches the route open and
  leaves AT1846S demod noise a permanent path to the amp (the "FM-RX squeal").
  Fixed with `rx_route_off()` on disconnect.
- **DIPLEX0 upper bits are NOT writable** — they are write-only / read-as-zero
  (per `registers.h` and the [buses chapter](10-buses-peripherals)), so a read-back cannot confirm the
  audio-mute bit; don't chase the audio-mute problem there. (The specific
  `0x38000007` read-back value is ⚠️ unverified — it is not found in any source
  and conflicts with the read-as-zero behavior; the only `0x38000000` constant in
  the RE notes belongs to `DIPLEX1`, not `DIPLEX0`.)
- ⚠️ **Dead end — the codec is NOT the 2-way FM audio path** (falsified by live kill-tests; FM RX is analog-direct). Don't poke the codec mixer for FM RX.
- ⚠️ **Dead end — the codec internal AGC/mixer (`0x160009EF`/`0x160009F0`,
  `mixdacl_sel`/`mixadcl_sel`) is left at reset** for both FM and DMR. Don't
  configure it.
- ⚠️ **Dead end — `work_mode 0x11000100` bit7 (0x80) is the FM modulator/TX bit, not RX**; don't set it for FM RX (analog FM needs no modem).
- ⚠️ **Dead end — the DMR-voice-RX modem PCM engine is a separate subsystem, not a register poke**; driving the vendor FM-RX register state onto the radio won't clock it (`pcm_mode` won't latch). Analog FM RX is unaffected.

## Where the code lives

- `vendor/wt-hd2-vp-adpcm/platform/drivers/audio/audio_HD2.c` — board-level
  routing HAL (the OpenRTX source/sink matrix); owns the PTB4/PTB10/PTB17 GPIO
  twiddles (`spkr_amp_mute`, `spkr_amp_unmute` = analog/PTB17 HIGH,
  `spkr_amp_unmute_codec` = DAC/PTB17 LOW, `rx_route_on/off`) and the
  `SOURCE_RTX→SINK_SPK` / `SOURCE_MCU→SINK_SPK` connect/disconnect cases.
- `vendor/wt-hd2-vp-adpcm/platform/drivers/audio/outputStream_HD2.cpp` — the
  productized CPU→codec-DAC PCM output-stream driver (`hd2_pcm_audio_driver`):
  arms the bridge, registers the 100 Hz ISR, the prime-write-then-ack kick,
  double-buffer sync.
- `vendor/wt-hd2-vp-adpcm/platform/drivers/baseband/radio_HD2.cpp` —
  `hd2_audio_out_warm()` (single source of truth for the HW-verified codec +
  socsys audio-gate bring-up constants, called not re-hardcoded by the drivers
  above) and `hd2_audio_out_lineout()`.
- IMA-ADPCM voice-prompt decode lives in `vendor/wt-hd2-vp-adpcm/platform/targets/HD2/platform.c`
  + `lib/codec/` (branch `hd2-vp-adpcm`).
- Register/pin macros: `vendor/wt-hd2-vp-adpcm/platform/mcu/HR_C7000/registers.h`
  (`SPKR_AMP_PIN`, `AUDIO_ROUTE_PIN`, `SPKR_GAIN_PIN`, the `SOCSYS` struct
  fields `VOICE_PATH`/`PCM_MODE`/`INT_STATUS`/`IO_DIPLEX0`, `SAHB_PCM_PLAY`,
  `SAHB_PCM_CAP`, `SOFT_RSTN_PCM_BITS`, `VOICE_PATH_*`, `INT_STATUS_PCM_*_ACK`,
  `DIPLEX0_AUDIO_MUTE`, `HD2_IRQ_PCM_PLAY/CAP`, `PCM_FRAME_SAMPLES`); board
  discrete-signal labels in `targets/HD2/pinmap.h`.
- ⚠️ The diag/experiment ops `hd2_pcm_tone` (raw arming A/B), `hd2_pcm_capture`,
  `hd2_aprs_rx` (capture + reg 0x58 flatten) live in
  `vendor/OpenRTX/platform/targets/HD2/hd2_pcm_stream.cpp` and were **not**
  carried onto the live `hd2-vp-adpcm` tree — reference-only.

## Status & deeper reading

**Status: ✅ HW-verified** for analog FM RX routing (PTB10/PTB17), CPU→codec-DAC
PCM playback (voice prompts / beeps / streaming), and FM-demod PCM capture
(APRS RX). The split MCU-playback un-mute is done on the live `hd2-vp-adpcm`
tree: `audio_HD2.c` calls `spkr_amp_unmute_codec()` (PTB17 LOW) for `MCU→SPK` and
`spkr_amp_unmute()` (PTB17 HIGH) for `RTX→SPK` — the earlier "shared un-mute
drove PTB17 HIGH for both" concern no longer applies. ⚠️ DMR-voice-RX codec-leg
audio (modem PCM engine) is static-RE-complete but not brought up on hardware.

Distilled from:
- `docs/audio_paths.md` — per-path flowcharts (all 8 paths) + setup recipes.
- `docs/audio_renames.md` — vendor function renames, AT1846S reg / GPIO map.
- `docs/pcm_stream_playback.md` — the SAHB PCM mailbox recipe (RE'd from v2.1.3).
- `tmp/audio_path_findings.md`, `tmp/vendor_audio_cleaning_findings.md` — the
  live kill-tests that settled analog-direct FM and the modem-engine wall.
- memory: `hd2-min-bringup-codec-dac-silent` (PTB17 path-select root cause).
- memory: `hd2-adpcm-voiceprompts-audio-path` (PTB17/PTB10/PTB4 state machine,
  PCM-tone-not-PWM beep, RX-route latch bug).
- memory: `hd2-rx-audio-capture` (capture arming + reg 0x58 data flatten).
