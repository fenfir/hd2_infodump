---
title: "16. Roadmap & open problems"
---

# 16. Roadmap & open problems

Status legend: ✅ HW-verified · 🟡 in-progress · ⚠️ dead-end/superseded

## What it is / how it works

The HD2 is a working analog-FM transceiver on OpenRTX/Miosix today (FM voice TX/RX,
squelch, S-meter, CTCSS/DCS/DTMF/VOX, broadcast-FM, APRS TX, GPS, codeplug NVM,
4-level TX power — all ✅ HW-verified). This chapter tracks the frontier: the
features that are *built but not finished*, the ones blocked on a hard technical
wall, and the packaging work needed to upstream the port. Each item below is one
mental model plus its single load-bearing blocker.

The recurring pattern across every open problem is the **CK803S soft-float / slow
bit-bang bus tax**. There is no FPU, so transcendental libcalls (`expf`/`logf`/`powf`,
worst on C-SKY's generic `fp-bit`) dominate DSP cost; and the AT1846S radio bus is
GPIOA bit-bang (~hundreds of µs/transfer), so polling it hard is what drives the
lockups. Almost every roadmap item is a fight against one of those two taxes.

A second recurring lesson: **the qemu Cortex-M3 `-icount` proxy is NOT a valid
CK803S cycle model** for int64/shift-heavy or soft-float-heavy inner loops — it has
mis-predicted in both directions repeatedly. Every performance claim must be
re-measured flashed on real silicon before it counts.

## How to implement it (per-item status + the blocker + the next move)

**codec2 decode → real-time (M17 RX voice, codec2 voiceprompts)** — 🟡 stalled near
the floor. (Background: [voice codecs](07-voice-codecs).) On-device decode has gone **505 ms → ~40 ms/frame (~12.7×)** via a long
fixed-point campaign (`fast_powf` for `aks_to_mag2`'s `(A2g/A2)^0.2` postfilter power,
`fast_sincosf` Q15 LUT, fixed BFP FFTs, an integer log-domain postfilter, integer
overlap-add, double-precision elimination). **Blocker: ~40 ms is 2.0–2.35× over the
20 ms budget and is the soft-float floor** — the residual is now *integer* FFT +
256-bin postfilter-LUT compute, not libcalls, so the remaining classic levers barely
move it. Next: only radix-4 or an oscillator-bank `synthesise` (drop the inverse FFT)
could go lower, both risky and uncertain to reach 20 ms. Correctness note: the
speed-first path sits at ~22 dB segmental SNR (down from transparent 60 dB); the
transparent endpoint is P1a+P2a only (−46% on-device, still 13.5× over). Decode is
usable for **buffered/near-real-time**, not real-time RX. See
`docs/codec2_fixedpoint_decode_plan.md`.

**Voiceprompts** — ✅ SETTLED as IMA-ADPCM; do not revisit. Because decode is not
real-time, HD2 voiceprompts stay on IMA-ADPCM (`voicePrompts_adpcm.c`, `voiceprompts.vpa`
built by `scripts/vpc_to_adpcm.py`) — this is what `docker/build.sh` ships. ⚠️ "switch
voiceprompts back to codec2 `.vpc`" is a dead end — VP needs the decoder.

**Miosix modern port** — ✅ core done / 🟡 packaging. The CK803S / C-SKY V2 core port
(no-PendSV tickless scheduler, `cskyv2_context.S`, `hr_c7000_os_timer.cpp`,
`interrupts.cpp`; the full port is the [kernel chapter](12-kernel-cskyv2)) is
HW-verified and running. The repo is now OpenRTX-free
(build-verified byte-identical). **Blocker for upstream:** the earlier
`hd2_phase1/` bring-up scaffolding has already been dropped (it is not present on
`hd2-miosix-port`), so the remaining concern is that the reviewer-sensitive core
touchpoints (`kernel/lock.h` no-PendSV yield, `kernel/thread.cpp`)
need to survive review. `tmp/miosix_modern_port_spec.md` is the layout spec.

**DMR AMBE voice** — 🟡 TX PHY done, voice codec in bring-up. Wide-4FSK DMR TX works
on air ([DMR TX](06-dmr-tx), [voice codecs](07-voice-codecs)); the software AMBE+2 codec (no external HR_V3000) is bringing up in
`dmr_HD2.{cpp,h}`. **Blocker: full voice not yet integrated/verified**; the codec is
fixed-point-native (per-harmonic mantissa/exponent, direct oscillator sum) so it does
*not* hit codec2's small-bin FFT wall.

**M17 voice TX** — 🟡 works but not upstream-shaped. Proven on air (4FSK baseband
pumped through the FM modulator, not the DMR modem; see [M17 TX](08-m17-tx)). **Blocker: it lives in diag op
`s` (a bring-up harness) and is still intermittent (per-bank refill glitch)** — for
upstream it must move into `radio_HD2`/`OpMode_M17`, and it depends on the DMR driver
at file level (adds ~88 lines to `dmr_HD2.cpp`), so the M17 PR stacks on the DMR PR.

**APRS RX FCS gap** — 🟡 near-complete, blocked on signal, not code. (Full RX/TX
recipe: [APRS](09-aprs).) The full 1200
AFSK pipeline (`protocols/APRS/`) locks HDLC flags and assembles near-full frames
(flags=56, max=61) but **never passes FCS**. Root cause chased to ground: the demod
recovers the entire info field perfectly but corrupts the early address region — a
momentary bit-sync slip coming out of the flag preamble. **Blocker: captured audio is
mark/space-imbalanced (correlator sees 83–91% mark vs expected ~49%); a strong scipy
reference demod ALSO fails on the same captures ⇒ the limit is SIGNAL QUALITY /
discriminator centering, not the PLL.** Next: fix the RF link / RX fine-tune to
balance the tones FIRST, then the demod. ⚠️ Don't retry PLL-gain sweeps or the
vec-0x3c ISR capture — both exhaustively failed (ISR faults the radio → WDT reboot).

**Threading redesign (event-driven radio SM)** — 🟡 designed, not implemented. The
polled ~33 Hz rtx model over the slow bit-bang bus causes worsening lockups as
features stack. **Blocker: not yet built** — Phase 1 (the highest-leverage, no-IRQ
step) is to decouple the AT1846S RSSI poll from the loop and drop it to ~5–10 Hz,
timer-pace PTT debounce, and drop the 200 Hz power poll to ~10 Hz (`rf_freeze` A/B
already proved freezing this poll stops the lockups). Later phases add a single-owner
radio state machine and GPIOB/UART2 edge IRQs. See `docs/threading_redesign.md`.

**Upstreaming** — 🟡 branches assessed, not all cut. (The full three-fork branch
structure and cut-point SHAs are in the [OpenRTX port chapter](13-openrtx-port-layout).)
Three independent PRs to three
upstreams: **(1)** miosix core → `fedetft/miosix-kernel` (`hd2-miosix-port`, ready
bar scaffolding drop); **(2)** OpenRTX HD2 target → `OpenRTX/OpenRTX`, layered
`hd2-platform` → `hd2-dmr` → `hd2-m17` (pointer-cut SHAs identified: platform
`bd18cc59`, dmr `154e6be2`, m17 `044f1afc`) — branch stack not yet created;
**(3)** codec2 `C2_FIXED` encode → `M17-Project/Codec2-mod` (`hd2-fixedpoint-experiments`,
✅ pushed to fenfir). **Blocker: the OpenRTX branch stack, the `Modulator.cpp`
`PLATFORM_HD2` standalone-patch extraction, and the diag→OpMode M17 refactor** are all
still open. See `docs/upstream_plan.md`.

## Gotchas & cautions

- ⚠️ **qemu `-icount` lies for CK803S.** It has mis-predicted decode cost in *both*
  directions (double-float under-predicted; int64/kiss-FP16 FFT over-predicted).
  Never call a perf change a win until it's flashed and measured on the radio.
- ⚠️ **codec2 decode cannot copy AMBE's trick.** The LSP-vs-log-amplitude wall — why
  codec2 3200 is *forced* to reconstruct `1/|A(ω)|²` where AMBE never does — is the
  [voice-codecs chapter](07-voice-codecs)'s core finding; see there for the mechanism.
  The roadmap corollary: "do the postfilter in the log domain" does NOT fix it (the
  error is bin precision at the FFT source, not the arithmetic on top).
- ⚠️ **Q30-twiddle / kiss-FP16 FFT for decode = tried and reverted.** The hand-rolled
  Q15 `fft_fixed` (radix-2, int32, `__muldi3`-free, output kept ~2^14) is both faster
  on real silicon and higher quality. FFT restructuring is a dead end here.
- ⚠️ **APRS: don't `rf_freeze` during the `w` op** — the capture rides the squelch
  audio gate; freezing leaves it muted. And keep squelch OPEN during capture (the
  gate flutter chops the beacon into false long-mark runs).
- ⚠️ **No inline `delayUs`/sub-ms sleeps in the rtx PTT path** — both wedged the
  tickless core. Use timer-paced cadence and ISR→post→worker (the PCM path is the
  proven reference handoff).
- **Threading: keep GPIOC keypad polled** — it shares the LCD bus; never edge-IRQ it.
- **Upstream ordering is fixed:** the M17 PR depends on the DMR PR landing first
  (file-level dependency in `dmr_HD2.cpp`); decided to stack as-is, no refactor.

## Where the code lives

- codec2 decode: `vendor/Codec2-mod/` (branch `hd2-fixedpoint-experiments`) —
  `src/codec2_mod.c` (`codec2_decode`), `src/lpc.c` (`aks_to_mag2`, `lsp_to_lpc`),
  `src/synthesis.c` (`synthesise`, `phase_synth_zero_order`, `postfilter`),
  `src/fft_fixed.c`, `src/util.c` (`fast_powf`/`fast_sincosf`); harness under
  `build-ambe/harness/`.
- voiceprompts (shipping tree): `vendor/wt-hd2-vp-adpcm/openrtx/src/core/voicePrompts_adpcm.c`
  (+ `voicePromptData_adpcm.S` → embeds root `voiceprompts.vpa`), `scripts/vpc_to_adpcm.py`.
- miosix port: `vendor/miosix-kernel` (branch `hd2-miosix-port`) —
  `miosix/arch/cpu/cskyv2/`, `miosix/arch/chip/hr_c7000/`, `miosix/arch/board/hrc7000_hd2/`.
- FM radio driver (shipping tree): `vendor/wt-hd2-vp-adpcm/platform/drivers/baseband/radio_HD2.cpp`
  (RSSI/CTCSS/DCS squelch, opmode bookkeeping — the RF-squelch decision lives in `OpMode_FM`).
- ⚠️ DMR/M17/APRS are NOT on the shipping `wt-hd2-vp-adpcm` branch — they live in the
  integrated `vendor/OpenRTX` tree: `platform/drivers/baseband/dmr_HD2.{cpp,h}` (DMR extends
  `radio_HD2.cpp` there); `platform/targets/HD2/hd2_diag.cpp`, `m17_blob_HD2.S`; M17 sink in
  `openrtx/src/protocols/M17/Modulator.cpp` (`PLATFORM_HD2` guard — present in `vendor/OpenRTX`,
  not yet in the shipping tree's `Modulator.cpp`).
- APRS RX (in `vendor/OpenRTX`): `openrtx/src/protocols/APRS/Afsk1200.cpp` (the demod PLL to
  replace), `Hdlc.cpp`, `Ax25.cpp`, `Decoder.cpp`; capture in `platform/targets/HD2/hd2_pcm_stream.cpp`
  (diag op `w`); host tools `scripts/aprs_afsk.py`, `scripts/aprs_host_decode.sh`.
- threading: the AT1846S bus driver `vendor/wt-hd2-vp-adpcm/platform/mcu/HR_C7000/drivers/i2c1_hd2.c`
  (now HW-I2C1, was the CSKY_V2 bit-bang), CK803S IRQ vectors in
  `vendor/miosix-kernel/miosix/arch/cpu/cskyv2/interrupts.cpp`, and the PCM ISR→worker
  reference in `vendor/OpenRTX/platform/targets/HD2/hd2_pcm_stream.cpp`. ⚠️ The old
  `hd2_rtx.c` polled loop was removed in `35bb42f4` (OpMode_FM convergence); the
  `threading_redesign.md` references to it are historical.

## Status & deeper reading

Overall chapter status: **🟡 in-progress** (a roadmap of open work; the settled
decisions inside — ADPCM voiceprompts, the OpMode_FM convergence — are ✅).

- `docs/codec2_fixedpoint_decode_plan.md` — the full decode fixed-point campaign,
  phase-by-phase on-device numbers.
- `docs/threading_redesign.md` — event-driven radio SM plan + phased migration.
- `docs/upstream_plan.md` — three-repo branch structure + cut-point SHAs.
- `tmp/miosix_modern_port_spec.md` — modern Miosix CK803S port layout spec.
- `tmp/STATUS.md` — canonical subsystem status matrix.
- memory `hd2-codec2-encode-only-vp-adpcm` — why VP stays ADPCM; decode feasibility.
- memory `hd2-aprs-rx-status` — the APRS RX signal-quality wall in detail.
- memory `hd2-openrtx-convergence-roadmap` — repo/fork map + OpMode_FM convergence
  (note: this convergence is DONE; `hd2_rtx.c` was removed in commit `35bb42f4`, so
  the threading-redesign doc's `hd2_rtx.c` references are historical).
