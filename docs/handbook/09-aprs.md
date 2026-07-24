---
title: "09. APRS (AFSK)"
---

# 09. APRS (AFSK)

Status: **TX ✅ HW-verified (decodes in Direwolf) · RX 🟡 in-progress (near-complete frames, FCS fails)**

1200-baud Bell-202 AFSK on the HD2, riding the analog-FM carrier. TX is solved and
decodes cleanly in Direwolf; RX assembles near-full frames but the demod never
passes FCS. This chapter is the settled TX recipe plus an honest map of where RX
is stuck.

## What it is / how it works

APRS on the HD2 is 1200-baud AFSK (mark 1200 Hz / space 2200 Hz, NRZI-coded)
carried inside a normal narrowband-FM transmission. The protocol layers —
AX.25 UI framing, HDLC (FCS / bit-stuff / `0x7E` flags), NRZI, and the AFSK
tone modem — are all software and live in a hardware-agnostic OpenRTX protocol
module. The radio hardware only has to (a) put the two audio tones onto the FM
carrier for TX and (b) hand back demodulated audio for RX.

The key TX insight — and the thing that cost an entire debugging session — is
**how** the tones reach the carrier. On the HR_C7000 there is *no* reachable
CPU-PCM path into the analog-FM modulator: vendor RE confirmed the modem's
TX-RAM / SAHB PCM buffers (`0x16000030`, `0x180000a0`) are DMR-vocoder /
repeater-relay only and starve or collapse the FM carrier when driven standalone.
Instead, TX uses the **AT1846S transceiver's own internal tone1 generator**
(the same chip covered in the [FM analog chapter](04-fm-analog)),
retuned per NRZI symbol between mark and space, with the HR_C7000 FM modulator
kept **OFF** (its MOD-pin drive would swamp the internal tone). This is the same
"AT1846S-internal tone" mechanism the vendor uses for DTMF/sub-tones — the CPU
just writes a couple of AT1846S registers per bit.

RX reuses the FM-RX audio-capture path (see the [audio-path chapter](03-audio-path)): demodulated
8 kHz audio is streamed into the software AFSK decoder. The pipeline locks HDLC
flag sync and assembles frames to near-full length, but a bit-sync slip in the
address region corrupts the early bytes, so FCS always fails. This is a demod /
signal-quality wall, not a plumbing problem.

## How to implement it

### TX (✅ verified — diag op 'B', `hd2_aprs_tx`)

Working code path: `hd2_aprs_tx` in
`vendor/OpenRTX/platform/targets/HD2/hd2_pcm_stream.cpp` (diag op `'B'`, toml
`aprs_tx`). AX.25/HDLC/NRZI/AFSK sample generation is
`protocols/APRS/Encoder.cpp` + `Ax25.cpp` (`buildUi` / `crc16X25`), host
round-trip byte-perfect.

The on-air recipe — **AT1846S internal tone1 generator, HR_C7000 modulator OFF**:

1. **Carrier — bare AT1846S keying, no HR_C7000 modulator.** Reg `0x30 = 0x4006`,
   then `0x30 = 0x4046` (and **only** `0x4046`). Ride the current RX tune; no
   `setFrequency` needed at close range.
2. **Enable the single-tone generator** (full writes, not read-modify-write):
   - `0x79 = 0xC000` (dtmf_direct=1 single-tone + dtmf_tx=1)
   - `0x7A = 0x4000` (single_tone enable — the oscillator gate)
   - `0x3A[14:12] = 001` (voice_sel = Tx tone1)
3. **Power / deviation** to lift out of noise: APC DAC + reg `0x0A` padrv from
   `hd2_txpower_levels()` (honours the UI TX-power level — Extra Low is plenty at
   the bench), `0x59 = 0x0C50` (deviation), `0x41[6:0]` tone gain maxed.
4. **Modulate per NRZI symbol:** retune tone1 via reg `0x35` between mark
   `12000` (1200.0 Hz) and space `22000` (2200.0 Hz), holding each for
   **833.33 µs/bit** timed off `getTime()`.

That is the whole datapath — the CK803S only writes AT1846S registers; the
HR_C7000 modem is entirely bypassed. Do **not** call `radio_enableTx` /
`WORK_MODE |= 0x80` / `FM_PTT` / `AF_GATE` for this path (see gotchas).

### RX (🟡 in-progress — diag op 'w', `hd2_aprs_rx`)

Working-but-imperfect path: `hd2_aprs_rx` in the same
`hd2_pcm_stream.cpp` (diag op `'w'`), decoding through `protocols/APRS/`
(`Afsk1200.cpp` PHY correlator + bit PLL → `Hdlc.cpp` → `Ax25.cpp`, wired by
`Decoder.cpp`).

1. Wait for a carrier (trigger on SNR = `rssi_db − noise_db` > 10; the
   AT1846S sq_cmp comparator, reg `0x1C[0]`, gates the audio — squelch must be
   open or it flutters closed mid-beacon).
2. **Bypass the AT1846S voice filters:** `0x58 |= 0xE0` (bits 5/6/7) to restore
   the 2200 Hz space tone that the voice LPF/de-emphasis rolls off. Re-assert it
   inside the capture loop — the rtx thread can rewrite `0x58` mid-capture.
3. Stream the **8 kHz** FM-demod audio (confirmed 8000 Hz, contiguous) into the
   `Afsk1200` decoder. A ring dump `g_aprsDbg` (freezes ~2 frames after a
   near-complete frame closes) is readable via the `'R'` op for host analysis.

Diagnostics: `HdlcDecoder::flagsSeen()` / `maxFrameLen()` /
`curFrameLen()` are the bring-up counters. On a good capture this reaches
`flags=56–61`, frames to ~56–59 bytes — headers byte-perfect, info field
perfect, but a burst of substitutions/deletions in the src-SSID/digipeater
region (~byte 11–27, ~0.1 s into the frame) fails FCS.

## Gotchas & cautions

- **⚠️ Do NOT enable the HR_C7000 FM modulator for AFSK TX.** `radio_enableTx` /
  `WORK_MODE |= 0x80` / `FM_PTT (0x11000560)` / `AF_GATE` bring up the MOD-pin
  voice path, which **swamps the AT1846S internal tone** — carrier comes up but
  the tone is silent. The AT1846S has its own tone path; the C7000 modulator must
  be off to hear it.
- **⚠️ Never key reg `0x30 = 0x40c6`.** bit7 ("mute") silences the AT1846S
  internal-tone path. (The MOD-pin *voice* path bypasses bit7, so voice TX
  legitimately uses `0x40c6` — but it kills a tone.) Use `0x4046`.
- **⚠️ padrv reg `0x0A = 0x7C20`, never `0x7820`.** The `0x7820` (missing-pga-bit)
  value kills the carrier.
- **⚠️ Dead end — CPU-PCM into the FM modulator does not exist.** Every attempt to
  inject samples via modem TX-RAM (`0x16000030`, `voice_path 0x11000080` bit0=1)
  or codec DAC playback (`0x180000a0`, `pcm_mode=3`) either breaks the carrier
  (reconfigures the modem mux into DMR-vocoder topology) or leaves it unmodulated.
  Vendor RE: those buffers have zero xrefs for FM TX; the only TX-RAM user is the
  analog repeater relay, and *there* the samples come from the hardware RX
  recording engine, not the CPU. Don't retry the SAHB/TX-RAM PCM path.
- **⚠️ Dead end — vec-0x3c / HD2_IRQ_PCM_CAP ISR capture for RX.** Driving RX
  capture from the PCM-capture ISR **reliably faults the radio** → WDT
  warm-reboot; it races the modem's own use of that vector during FM-RX.
  Ack-first ordering did not stabilize it. Parked at
  `tmp/aprs_rx_isr_capture_wip.patch` — do NOT re-flash. Use the stable
  blind-sleep capture.
- **⚠️ Dead end — PLL-gain / majority-vote demod tuning on marginal audio.** A
  full DPLL gain sweep (1.0…0.05), majority voting, longer correlators (N=10–20),
  twist correction, and pre-emphasis were all tried on real captures and none
  beat the firmware's hard-reset PLL; majority vote made it *worse*. The blocker
  is early bit-*deletions* at the preamble→data boundary, which gain tweaks can't
  recover, and marginal/variable signal (space-tone deficit: correlator reads
  83–91% MARK vs expected ~49%). Fix the RF link / discriminator centering first,
  not the PLL.
- **Frequency offset:** the old hardcoded ~+12.5 kHz FM-TX "fudge" is **gone** from
  `hd2_fm_tx_key` (`radio_HD2.cpp`) — it now calls `at1846s.setFrequency(txFreq)`
  raw, and residual synth error is deferred to a proper per-band/per-radio
  calibration that is **not yet implemented** (`nvm_readCalibData` has no HD2
  backend yet). There is **no `HD2_FM_TX_FREQ_OFFSET_HZ` macro** in the tree
  (verified). The APRS TX path itself
  rides the current RX tune with no `setFrequency` at all. Residual discriminator
  centering still matters for RX — set VFO step to 1 kHz for fine tuning.
- **PA thermal:** ~1 h of back-to-back full-power test TX went choppy (thermal;
  recovered after rest). Keep test TX at Extra Low / Low, low duty.
- **Bridge op collision:** `'B'` was hardcoded as *backlight* in three places in
  `scripts/rtx_tui.py` (SPECIAL_OPS frozenset + `elif op=="B"` sender + `b <level>`
  parser). All removed so `'B'` routes through the toml `aprs_tx` dispatch; needs
  a TUI restart to load. (See the bridge op-collision note.)
- **Squelch gate chops RX capture:** the rtx audio gate (RF-squelch-gated
  `rtx_setAudio`) also gates the `'w'` capture; when a beacon sits near the
  threshold it flutters closed → muted gaps read as sustained MARK → deterministic
  garbage. Fixed by gating on the sq_cmp comparator (`0x1C[0]`) instead of raw
  RSSI, but keep the squelch open for a clean capture.
- **Don't `rf_freeze` during `'w'`** — the captured demod audio rides the squelch
  audio gate that rtx_task opens on carrier; freezing leaves it muted (pp~240).

## Where the code lives

> ⚠️ APRS is **not** in the shipping `hd2-vp-adpcm` worktree. The protocol module and
> the `hd2_pcm_stream.cpp` diag ops below live only in `vendor/OpenRTX/` (the FM/APRS
> branch). The FM driver pieces they lean on (`radio_HD2.cpp`, `OpMode_FM.cpp`) have
> since landed in the live tree at `vendor/wt-hd2-vp-adpcm/`.

- **Protocol module (hardware-agnostic, OSI-layered):**
  `vendor/OpenRTX/openrtx/src/protocols/APRS/` — `Afsk1200.cpp` (PHY correlator +
  bit PLL), `Hdlc.cpp` (NRZI/flag/de-stuff/FCS), `Ax25.cpp` (`buildUi` /
  `crc16X25` parse), `Encoder.cpp`, `Decoder.cpp`. Integer-only, O(1) memory,
  host-validatable. Headers under `vendor/OpenRTX/openrtx/include/protocols/APRS/`.
- **On-target diag ops:** `vendor/OpenRTX/platform/targets/HD2/hd2_pcm_stream.cpp`
  — `hd2_aprs_tx` (op `'B'`) and `hd2_aprs_rx` (op `'w'`, ring dump `g_aprsDbg`).
- **TX power mapping:** `hd2_txpower_levels(apc, padrv)` in
  `vendor/wt-hd2-vp-adpcm/platform/drivers/baseband/radio_HD2.cpp` (APC DAC
  0x060/0x100/0x200/0x400 + AT1846S reg `0x0A` padrv 0x08/0x0F per E/L/M/H level).
- **Squelch audio gate:** now in `vendor/wt-hd2-vp-adpcm/openrtx/src/rtx/OpMode_FM.cpp`
  (`OpMode_FM::update`) — `hd2_rtx.c`/`rtx_setAudio` is gone from the tree (verified).
  The RF-squelch decision prefers the AT1846S hardware comparator (sq_cmp) via the
  `radio_checkRxRfSquelch` weak hook, else a ±1 dBm hysteresis on `rtx_getRssi()`
  around a threshold derived from `sqlLevel`; RX audio is gated through `audioPath`.
- **Host tooling (`scripts/`):** `aprs_afsk.py` (host reference modem + `--decode`
  of captured s16le — note: too weak to reference real captures, no DC block),
  `aioc_record.py` (records the AIOC RX audio device, the key TX diagnostic),
  `aprs_beacon_now.py` (on-demand Direwolf KISS beacon, port 8001),
  `aprs_pull.py` / `aioc_record.py`, and the uncommitted `aprs_host_decode.sh` /
  `aprs_demod_eval.py` / `aprs_demod_lab.py` (byte-exact host port of the firmware
  demod for offline demod work). Bench-TX tool: `scripts/tmp_fm_tx_2tone.py`.
- **⚠️ Do-not-flash WIP:** `tmp/aprs_rx_isr_capture_wip.patch` (the dead-end ISR
  capture).

## Status & deeper reading

- **TX: ✅ HW-verified** — clean Direwolf decode 2026-06-14, radios a few feet
  apart, Extra Low power.
- **RX: 🟡 in-progress** — pipeline built and locking; frames to ~56–61 bytes but
  FCS never passes. Blocker is demod bit-sync at the preamble→data boundary
  plus marginal/variable signal quality (space-tone deficit). Next real attempt:
  a fundamentally stronger demod (interpolating clock recovery that doesn't drop
  bits at the boundary) validated against saved captures BEFORE building firmware
  — NOT more PLL-gain tuning.

Sources this chapter distills:
- memory: `hd2-aprs-tx-status` — TX solved, full recipe + three session-costing gotchas.
- memory: `hd2-aprs-rx-status` — RX pipeline, the bit-sync-slip diagnosis, dead ends.
- `tmp/aprs_tx_vendor_re_findings.md` — vendor RE proving no CPU-PCM FM-modulator
  path; AT1846S tone-gen / PWM-mic-node / TX-RAM-repeater mechanisms.
- Related: `hd2-rx-audio-capture` (the FM-demod → 8 kHz PCM path `'w'` reuses),
  `hd2-rssi-smeter-rx-path` (squelch/sq_cmp/SNR overhaul), `hd2-bridge-op-collision`.
