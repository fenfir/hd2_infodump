---
title: "07. Voice codecs & prompts"
---

# 07. Voice codecs & prompts

The HD2 has three voice-audio code paths, and the one fact that governs all of
them: **there is no hardware vocoder** — every speech codec runs in software on
the CK803S core. This chapter covers the device-resident software AMBE+2 codec
(DMR), the fixed-point codec2 work (M17, encode-only), and the IMA-ADPCM
voice-prompt player that ships today.

## What it is / how it works

**DMR voice = a software AMBE+2 codec on the CK803S.** Established 2026-06-10 by
a multi-agent RE pass plus direct decompilation. The IRAM "DSP cores" people
assumed were an FEC layer are in fact the speech codec itself: they convert
80-sample (0x50) 8 kHz PCM blocks ↔ a 49-bit (0x31) MBE parameter vector, touch
zero MMIO, and are seeded with Q15 fractional coefficients (0x2aab≈⅓, 0x147b,
0x7fff). The 49-bit pack/expand functions are trivial bit↔byte serializers with
no Golay/Hamming/CRC — so there is no "HW does speech, SW does FEC" split; it is
all software, the same lineage as md380tools (C5000) and OpenGD77 (C6000). This
is DVSI AMBE — patent-encumbered, same caveat as md380tools. (The on-air burst
pump that stages these 27-byte voice frames into the modem is the
[DMR TX chapter](06-dmr-tx); the codec is the last unfinished piece of DMR voice.)

**M17 voice = codec2 3200, and only the ENCODE half is viable.** The vendored
`Codec2-mod` tree (M17-Project fork, 3200 bps mode only) has a fixed-point port
under `-DC2_FIXED`. On the actual CK803S at the stock ~42 MHz clock, **encode is
14.5 ms/frame** (under the 20 ms budget, ~28% headroom) — this is what M17 TX
(mic→air) needs, and it is a GO today. **Decode is the opposite story:** the
`C2_FIXED` work converted only the analysis/encode path; synthesis stayed float
at first (measured ~505 ms/frame). A months-long fixed-point decode effort drove
it down to ~40 ms/frame — ~2.0–2.35× over the 20 ms budget, and only a ~12.7× speedup
from the ~505 ms float baseline — but hit a hard floor: the
codec2 3200 bitstream carries LSPs (an LPC envelope), so decode is *forced* to
reconstruct `1/|A(ω)|²` at formant nulls — exactly where block-floating-point FFTs
have the fewest bits. AMBE sidesteps this by transmitting log-amplitudes directly;
codec2 cannot. **Real-time decode on this core is not reached and is off the table**
unless the CPU clock is raised toward ≥84 MHz (unverified feasibility).

**Voice prompts = IMA-ADPCM, not codec2.** Because codec2 decode is unusable in
real time, the shipping voice-prompt player decodes an integer IMA-ADPCM stream
(microseconds/frame, no underruns). This is the validated answer, not a stopgap.

## How to implement it

### A. DMR software AMBE+2 codec (encode path, on-device verified)

The codec is **not position-independent** — binutils 2.45 can't decode ~29% of
CK803S DSP-ext ops, so relocation is impractical. It is carved from the vendor
image and copied to its **native VMAs** at runtime, then called through function
pointers. Verified entry points (v2.1.3):

| Symbol | Native VMA | Role |
|---|---|---|
| `ambe_codec_init` | `0x0001ca4c` | seed Q15 coeffs + working area |
| `ambe_encode_entry` | `0x0001c8e0` | PCM(80) → 49-bit params |
| decode dispatcher | `0x0001dd04` → `0x0001c64c` | 49-bit → PCM(80) |
| `ambe_49bit_pack` | `0x00032504` | params → 9-byte payload |
| `ambe_49bit_expand` | `0x0003227c` | payload → params |

Ordered bring-up recipe (implemented in `hd2_ambe.c`):

1. **Copy THREE blobs to their VMAs**, not just the code:
   - `ambe_lo.bin` → `0x0001bfe0`
   - `ambe_hi.bin` → `0x0003227c`
   - `.sahb_sram` → `0x18000000` (32 KiB of read-only DSP coefficient tables at
     `0x18001168..0x180034cc`). **The SAHB tables are the non-obvious blocker** —
     without them the first analysis call reads garbage coefficient pointers and
     the WDT resets. `0x18000000` is a separate SRAM block with no image overlap.
2. Barrier: `__asm__ volatile("sync")` — code was written as data; serialise
   before executing (this CK803S has no SW-managed I-cache under miosix).
3. Zero the two fixed working regions (`0x50000..0x56000`) and call
   `ambe_codec_init(0x000539e4, 1, 1)`.
4. Encode one 20 ms frame as **two 80-sample half-blocks**. The state base MUST be
   the codec's native object `0x000539e4`; PCM input is staged at `0x5527c`
   (= `0x539e4 + 0x1898`). Encode ABI (verified against the in-firmware caller
   `@0x1c028`): `r0`=PCM ptr, `r1`=pitch, `r2`=index, `r3`=len(80, clamped 76..84),
   stack `[0x800, half(0/1), *(u16*)(state+0x173a), state]`. **PCM is not an out
   arg** — the 49-bit output lands inside the state struct at `+0xc4c`; extract it
   with `ambe_49bit_pack`.
5. Run the codec on a **≥16 KiB-stack pthread** — its deep large-frame call chain
   overflowed the 2 KiB diag stack and caused warm reboots.

RAM layout: the DMR-voice build raises the image ORIGIN `0x20000`→`0x33000`
(the `hd2.ld` variant — described in `hd2_m17.ld`'s header but not yet committed;
the committed default `unikernel.ld` and `hd2_m17.ld` both keep ORIGIN `0x20000`)
to free the code window `0x1bfe0..0x327e8`; the fixed globals `0x53000..0x55300` sit
above the `0x4f000` ceiling in unused top SRAM (below SRAM end `0x58000`).

> 🟡 **Encode config is NOT yet fully replicated.** `ambe_codec_init` alone is
> insufficient — encode runs and is stable but produces byte-identical state for a
> tone vs silence, i.e. it no-ops on a fixed path. The vendor's OS spawner
> `ambe_state_struct_init @0x1bbb8` writes config (`+0x172c..+0x1752`) and
> ready-flags (`+5928/+5930`) that the encoder task checks and `init` does not.
> Next step: RE the spawner's plain (non-DSP-ext) stores and replicate them before
> encode. Gated behind the `HD2_DMR_VOICE` cmake option (OFF by default); diag
> op `K` runs the staged self-test.

### B. codec2 fixed-point (M17)

Do not start a port — the port exists on branch `hd2-fixedpoint-experiments`
(dual-path: float by default, fixed under `-DC2_FIXED`; bitstream ~98–100%
frame-identical to float). To ship **M17 TX voice**: build with `-DC2_FIXED`, use
`codec2_encode` (14.5 ms/frame at stock clock — real-time now). The M17 TX chain
outside the codec is integer framing/FEC plus the hardware-pumped FM baseband
(see the [M17 TX chapter](08-m17-tx)); it fits comfortably inside the ~5.5 ms/frame slack.

### C. IMA-ADPCM voice prompts (shipping, on-device verified)

The player is `voicePrompts_adpcm.c` — a portable `openrtx/src/core/` feature,
not HD2-specific. A target links EITHER it OR the codec2-based
`core/voicePrompts.c`: both expose the same `vp_*` API and share the
queue/dictionary/symbol/beep logic; only the decode core differs (integer
IMA-ADPCM vs codec2). Key mechanics:

- Clip data is a `'VPA1'` container (magic `0x31415056` LE) embedded via
  `voicePromptData_adpcm.S` (`_vpadata_start`/`_vpadata_end`), built from stock
  `voiceprompts.vpc` by `scripts/vpc_to_adpcm.py`. Layout:
  `[magic][count][TOC: count+1 u32 offsets][clips]`.
- **Single-threaded**, like stock. `vp_play()` opens a `SOURCE_MCU → SINK_SPK`
  audio path and an 8 kHz double-buffered circular output stream (2×160-sample
  halves = 20 ms each). `vp_tick()` (UI main thread) decodes **one 160-sample half
  per call**, paced by `outputStream_sync` — ADPCM decode is microseconds, so the
  blocking sync just paces the UI loop to ~50 Hz. No separate thread (an earlier
  threaded version deadlocked mixing `pthread_detach`/`pthread_join`).
- A `LEADIN_SILENCE_MS = 60` lead-in masks the amp turn-on pop.
- Decode is `adpcm_ima_decode()` per 4-bit code (`codec/adpcm_ima.h`; state
  `{pred, index}` from `adpcm_ima_reset`). Missing clips (not in the embedded
  subset) play as zero-length silence.

Note the audio-path detail from the amp routing: MCU playback needs **PTB17 LOW**
(codec-DAC path select); HIGH routes the amp to the AT1846S analog RX instead (see
the [audio-path chapter](03-audio-path)). Beeps go through `platform_beepStart` (PWM), but a PWM
tone is only audible while a PCM stream is actively clocking the codec DAC.

## Gotchas & cautions

- ⚠️ **codec2 decode fixed-point is a dead end for real-time — do not retry**
  (~40 ms/frame floor, ~2.0–2.35× over the 20 ms budget, dominated by *integer*
  FFT/postfilter work not soft-float; no reusable overlap with the encode
  `C2_FIXED` path).
- ⚠️ **Do not switch voice prompts back to stock codec2 `.vpc`.** It needs the
  decoder (~505 ms/frame float). IMA-ADPCM is the correct, validated choice — its header
  rationale stands.
- ⚠️ **The vendor `g_beep_seq` GPIOB.28/29 doorbell trigger is a dead end** — our
  OpenRTX image has no hardware listener consuming the request, so it's silent;
  clip audio isn't in the CPU's 4 MB flash window.
- **AMBE codec: pass the native object base `0x539e4`, not an arbitrary state
  ptr.** The encoder reads/writes hardcoded absolute buffers; an arbitrary ptr is
  silently ignored for internal accesses and encode reads zeros.
- **AMBE codec: the SAHB coefficient tables at `0x18000000` are mandatory** — the
  first analysis call faults without them.
- **Run any codec on a large stack** (≥16 KiB); the AMBE call chain overflowed a
  2 KiB stack → warm reboot.
- **Tooling trap:** saved objdumps of the AMBE region (`tmp/ambe_range*.asm`) are
  unreliable — binutils 2.45 desyncs on CKV2 32-bit + DSP-ext ops and fabricates
  phantom `lrw` pool targets. Re-decode by extracting raw bytes → `.short` →
  round-trip through `csky-miosix-elf-as -mcpu=ck803`.
- **codec2 methodology:** qemu Cortex-M3 `-icount` ratios do NOT transfer to
  CK803S (ARM `__aeabi` vs C-SKY generic `fp-bit`; int64/shift-heavy loops
  especially mispredict). Every timing claim must be re-measured on the device.
  Fixed-point only wins when it stays in native `mulsh` (16×16) / `mult` (32×32-lo)
  — `(int64)a*b` compiles to a `__muldi3` libcall under `-mcpu=ck803` and is poison
  in inner loops.

## Where the code lives

The shipping VP player lives in the live port tree (`vendor/wt-hd2-vp-adpcm/`,
branch `hd2-vp-adpcm` — what `docker/build.sh` builds):

- `vendor/wt-hd2-vp-adpcm/openrtx/src/core/voicePrompts_adpcm.c` — IMA-ADPCM VP
  player (portable core feature; links in place of `core/voicePrompts.c`).
- `vendor/wt-hd2-vp-adpcm/openrtx/src/core/voicePromptData_adpcm.S` — embedded
  `'VPA1'` container.
- `vendor/wt-hd2-vp-adpcm/lib/codec/include/codec/adpcm_ima.h` — integer ADPCM
  decoder.
- `vendor/wt-hd2-vp-adpcm/voiceprompts.vpa` — the built container.
- `scripts/vpc_to_adpcm.py` — builds `voiceprompts.vpa` from stock `voiceprompts.vpc`.

The DMR-voice AMBE work is NOT in the shipping tree — it lives on a separate
experimental branch under `vendor/OpenRTX/`:

- `vendor/OpenRTX/platform/targets/HD2/hd2_ambe.c` / `hd2_ambe.h` — AMBE codec
  wrapper (blob copy, ABI, encode). Gated `HD2_DMR_VOICE`.
- `vendor/OpenRTX/platform/targets/HD2/ambe_blob_HD2.S` — `.incbin` of the carved
  blobs (from gitignored `build-ambe/`).
- `scripts/ambe_carve.py` — carves `ambe_lo/hi.bin` + `.sahb_sram` from the image.
- `scripts/labels/ambe_codec.py` — codec ABI + address provenance.
- `vendor/Codec2-mod/` (branch `hd2-fixedpoint-experiments`) — codec2 3200
  fixed-point port: `src/fft_fixed.c`, `inc/c2_fixed_shared.h`, `C2_FIXED` kernels
  in `analysis.c`/`nlp.c`/`lpc.c`/`synthesis.c`/`util.c`. Harness under
  `build-ambe/harness/`.

## Status & deeper reading

- **DMR software AMBE+2 codec** — 🟡 in-progress. Blobs load, encode runs and is
  stable on-device, but encode still no-ops pending the spawner-config replication.
  Decode-inject not yet demonstrated on our port.
- **codec2 3200 encode (M17 TX)** — ✅ HW-verified real-time (14.5 ms/frame).
- **codec2 3200 decode (M17 RX / codec2 VP)** — ⚠️ dead end for real-time
  (~40 ms floor = ~2.0–2.35× over the 20 ms budget, a ~12.7× speedup from the ~505 ms
  float baseline; won't reach 20 ms without a clock raise).
- **IMA-ADPCM voice prompts** — ✅ HW-verified (27/27 stream halves, no underrun).

Source docs distilled here:
- `docs/voice_prompt_map.md` — vendor prompt catalogue / msg_id map (reference).
- `docs/codec2_ck803s_feasibility_report.md` — full feasibility + budget math.
- `docs/codec2_fixedpoint_decode_plan.md` — the decode fixed-point campaign log.

Memory: `hd2-dmr-voice-sw-ambe-codec`, `hd2-codec2-encode-only-vp-adpcm`,
`hd2-adpcm-voiceprompts-audio-path`.
