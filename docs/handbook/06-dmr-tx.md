---
title: "06. DMR TX (4FSK on-air)"
---

# 06. DMR TX (4FSK on-air)

## What it is / how it works

On the HD2 the **HR_C7000 modem is an autonomous TDMA engine**. In DMR mode the CK803S CPU does *not* run a software slot timer and does *not* compute DMR FEC — BPTC (Block Product Turbo Code, the forward-error-correction the DMR air interface wraps around each payload), Golay, interleave, sync insertion and the 30 ms slot cadence all happen in modem silicon. The CPU's job is to (1) put the modem into DMR Layer-2 mode, (2) start the slot engine, (3) stage the un-FEC'd logical fields (Link Control word + a 27-byte voice burst) into the modem's shared burst RAM, and (4) refill that RAM each slot in response to the modem's 30 ms `TS_TX` interrupt. RF is generated as two-point 4FSK modulation on the modem MOD pins, fed to the AT1846S, then the PA — the same RF handoff as the working FM voice-TX path (see the [FM analog chapter](04-fm-analog)).

The DMR control surface is the modem's **Layer-2 register file at MMIO `0x11000400`** (the decompiler renders these as low `_DAT_0000040x` because of a `movih+bseti` low-address artifact — the real base is `0x11000400`; see the [RE pipeline chapter](14-re-pipeline) and memory `hd2-decomp-movih-bseti-lowaddr-mistrack`). `WORK_MODE (0x100) = 0x6a` selects DMR L2 Tier-II/TimeSlot. The 30 ms `TS_TX_INTER` interrupt arrives on **PIC vector 0x3e** (source 0x1e) and drives the per-slot burst pump.

**Status: ✅ HW-verified for a wide, strong, correctly-framed 4FSK DMR carrier on air** (SDR-verified against the vendor at 433.450 MHz, 2026-06-18). What is *not yet* done is decodable voice — that needs the software AMBE+2 encoder (Phase 1; see the [voice codecs chapter](07-voice-codecs)); until then the pump stages a non-constant bench pattern so the 4FSK develops.

## How to implement it

The canonical recipe lives in `vendor/OpenRTX/platform/drivers/baseband/dmr_HD2.cpp`, gated by the `HD2_DMR_TX_LIVE` cmake option (default OFF).

> ⚠️ **DMR TX is not in the shipping build.** `docker/build.sh` builds `vendor/wt-hd2-vp-adpcm/` (the FM-only VP-ADPCM worktree), which stubs DMR out (`hd2_stubs.c`; its `radio_HD2.cpp` has no DMR symbols). The DMR TX driver exists only in the parallel `vendor/OpenRTX/` worktree behind `HD2_DMR_TX_LIVE=ON`. Paths below point there deliberately.

Ordered sequence, all values clean-room-verified before flashing:

**1. Stage call context** — `hd2_dmr_tx_call_start()`: build the 9-byte LC word (`build_lc()`: FLCO/FID/service-opts + 3-byte big-endian dst + src DMR IDs), write it to modem RAM offset `0x00` (`MODEM_RAM_LC_HDR`), set color code into `LOCAL_CC`.

**2. Modem DMR datapath bring-up** — `hd2_dmr_tx_start()` Phase A:
- `SYS_SOFT_RSTN (0x000) = 0x1fc` (release modem)
- zero `LAYER2_CONTROL`, `LAYER2_SLOTON`, `LAYER2_TXRX_CTRL`
- `REG2C (0x02c) |= 0x700` (modem tx/rx/mc clock enable)
- `ADC_CONTROL (0x074) = 0x41c3`
- 14 DMR sync words → `0x12c..0x160` (`kDmrSync[14]`; note `0x128` is `PHASE_OUT`, RO — not sync[0])
- `VOICE_PATH (0x080) = 0x13` — **bit0 = tx_voice_source = TX-RAM** (the key bit; see gotchas), bit1 i2s_slave, bit4 ahb_wr_voice_en
- `PCM_MODE (0x084) = 3` (AUDIO_BUFFER_CLR, self-clears to 0)
- `RF_MODE (0x104) = 0x034c9060` (two-point modulation), `TX_IF_FREQ (0x10c) = 0xbb800`, `RF_CONTROL (0x110) = 0x00041f1a`
- `SIG_CENTER (0x108) = 0x6868e7e7`
- `RF_MOD_BIAS (0x114) = 0x01e70000 | (modAmp<<8) | modAmp` — this is a deviation **reduction** ([15:8] sig_reduce, [7:0] phase_reduce), NOT a gain; vendor static `modAmp = 0x19`
- `DEV_LIMITER (0x118) = 0xff00` (reset default = full deviation), `SLOT_GUARD (0x168) = 0x14`
- `WORK_MODE (0x100) = 0x6a` (`WORK_MODE_DMR_L2`), `LOCAL_CC |= 0x100` (cc_opt DMR), `AF_GATE (0x39c) = 0x0001007f`
- Do **not** set `FM_PTT (0x560)` — that is the analog-FM modulator gate; the vendor's keyed-DMR capture reads it 0.

**3. Arm the temp slot, then start the engine** (the non-obvious unlock, HR_C7000 SoC User Guide §10.5.2.3 — the vendor SoC manual under `vendor/docs/hr_c7000/`, indexed in `vendor/docs/index.md`; later "§" / "manual" citations in this chapter refer to the same guide):
- `LAYER2_CONTROL (0x400) = 0xc0`; `LAYER2_TXRX_CTRL (0x408) = 0x40`; `LAYER2_CONTROL |= 0x10` (bit4 txtmp_master_mode → 0xd0)
- `LAYER2_SLOT_CNT (0x40c) = 0x20000000` (temp-slot counter preload)
- **`LAYER2_SLOTON (0x404) |= 0x2`** (bit1 `dll_tx_slot_on_tmp`) — THE FIX
- spin (≤40 ms) until `LAYER2_SLOTON` bit30 (`o_dll_tx_slot_on_tmp`) goes high
- `LAYER2_CONTROL = 0xdb` (full active TX: txen+rxen+tx_master)
- re-preload `LAYER2_SLOT_CNT` from the live count in `LAYER2_STATUS (0x41c)`
- `LAYER2_TXRX_CTRL = 0x40`
- **`LAYER2_SLOTON = (SLOTON & ~1) | 0x851`** — opens the real TX slot from the temp slot (bits 6 dll_txtmp_open_tx + 11 dll_tx_slot_frm_tmp). This is what actually starts the 30 ms slot engine.

**4. Key the AT1846S** (validated bench recipe): APC DAC-B up (`DAC_PD_MODE_EN &= ~2`, `DAC_PD_CTRL &= ~2`, `DAC_DATA_B = 0x400` for Medium power); padrv reg `0x0a = (0x0c<<11)|0x0420`; reg `0x40 = 0x0031` (DMR **digital mod-path enable**, bit0 tx_path_en / bit5 digital_mod_path_sel); `0x58 = 0xbcfd`, `0x44 = 0x0ad1`, `0x33 = 0x45f5`, `0x3a = 0x00c9`; then `0x30 = 0x4006` → `0x30 = 0x4046` (**tx_on bit6**).

**5. Prime + pump** — commit the staged LC-header burst: `LAYER2_SEND_TYPE (0x418) = 0x68` then `LAYER2_TXRX_CTRL bit7 = 1` (txnextsloten). Register the vec-0x3e ISR (`hd2_dmr_irq_enable()` → `IRQregisterIrq(HD2_IRQ_DMR_TS_TX, dmr_ts_tx_isr)`). Each `TS_TX` the ISR acks `INT_STATUS (0x3b0) |= 1` and runs `hd2_dmr_tx_slot_pump()` inline (MMIO-only, IRQ-safe — no thread handoff). The pump walks voice frames A..F: `SEND_TYPE = (seq<<4)|8` (0x08..0x58), stages the 27-byte VoiceBurst at `MODEM_RAM 0x30` (`MODEM_RAM_VOICE`), then commits with `layer2_tx_next_slot()` (`TXRX_CTRL` bit7). Frame A restages the LC + color code; frame F sets `VOICE_EMB_CTRL bit1` for embedded-LC. On dekey, `hd2_dmr_tx_call_stop()` sets `stopReq`; the pump emits the terminator (`SEND_TYPE = 0x68`) at the next frame-A boundary, then goes idle.

**Teardown** — `hd2_dmr_tx_stop()`: AT1846S `0x30 = 0x4006` (dekey), `DAC_DATA_B = 0`, zero `SLOTON`/`TXRX_CTRL`/`LAYER2_CONTROL`/`SLOT_CNT`, `WORK_MODE = 0`.

**Engine-state diagnostics** (diag op `j`, `dmr_tx_pump_test`): read `LAYER2_STATUS (0x41c)` `tx_bit_cnt` (cycles 0..287 when clocking) and `LAYER2_SLOTON (0x404)` bit31 `o_dll_tx_slot_on` / bit30 tmp / bit29 rx. `0x418` frame-type live keyed = 0x38 (mid-superframe); `0x41c` idle 0 → keyed 0x6e37.

## Gotchas & cautions

- **The slot engine will not start without arming the temporary TX slot first.** `SLOTON |= 0x851` is the "open TX slot FROM a temporary reserved slot" path and requires the temp slot (`SLOTON |= 0x2`, bit1) already active. `tx_master_mode` (0x400 bit1 / 0xdb) alone is NOT enough — without the temp-slot arm, bit31 never engages, `tx_bit_cnt` stays 0, and `TS_TX` never fires.
- **A thin, unmodulated carrier = you are transmitting EMPTY bursts.** For a clear call the modem auto-reads voice from the vocoder exchange buffer `MODEM_RAM 0x960` — filled only by the (unported) AMBE encoder. Fix: `VOICE_PATH bit0 = 1` (TX-RAM source) + stage NON-CONSTANT bytes at `MODEM_RAM 0x30` each burst. A flat/constant burst modulates nothing.
- ⚠️ **Dead end — replaying a one-shot diag snapshot of the vendor's full keyed end-state does NOT start the engine (`bursts=0`); use the temp-slot arm sequence above, run inside the driver.**
- ⚠️ **`WORK_MODE = 0x6e` is a repeater unit.** The vendor-live 0x6e has bit2 `is_repeater` set (that unit was a repeater); bit2 does NOT affect modulation. Use **`0x6a`** for DMO/direct.
- ⚠️ **AT1846S `0x30`: use `0x4046` (tx_on bit6), NOT `0x4026`.** `0x4026` is rx_on (bit5) and was an RE error from tracing the vendor RX path. DMR and FM use the same AT1846S keying; only the modulation *source* differs.
- ⚠️ **`INT_STATUS (0x3b0)` is write-1-to-ACK only — it is NOT a pollable TS_TX status.** Polling it always reads 0. Use the real vec-0x3e ISR or read `0x41c`/`0x404`.
- **Do not write `0x11c` (RSSI_BIAS, RO)** or `0x120` (THRESHOLD_VALUE, RX sync) — their apparent keyed "deltas" are the chip's own RO/RX activity, not TX state.
- **`SIG_CENTER (0x108)` / `RF_MOD_BIAS (0x114)`**: mod-bias fields are deviation *reduction*, not gain; `DEV_LIMITER (0x118) = 0xff00` is the reset default (full deviation), not a gain stage. Do not "turn them up" to boost the carrier.
- **Power**: APC DAC-B `0x400` + AT1846S padrv `0x0c` (Medium) gives a strong carrier; the vendor "Low" (`DAC 0x106` / padrv `0x08`) is faint.
- **Verify every register change against the clean-room RE / manual BEFORE flashing** — that review caught the `0x11c`-is-RO, `WORK_MODE` bit2, and `PCM_MODE` write-3 errors before burning a flash cycle.

## Where the code lives

- `vendor/OpenRTX/platform/drivers/baseband/dmr_HD2.cpp` — the canonical recipe: `hd2_dmr_tx_start()` / `_stop()` / `_slot_pump()` / `_call_start()` / `_call_stop()`, `build_lc()`, `write_modem_ram()`, and the vec-0x3e ISR (`dmr_ts_tx_isr` / `hd2_dmr_irq_enable`). Register names (`SOCSYS_LAYER2_*`, `MODEM_RAM_*`, `WORK_MODE_DMR_L2`) resolve via `platform/targets/HD2/hd2_regs.h`.
- `vendor/OpenRTX/platform/drivers/baseband/radio_HD2.cpp` — OpMode glue: `hd2_dmr_enable_tx()`, `hd2_dmr_build_call()` (CC/TS from `state.channel.dmr`, dst/type from `cps_readContact()`), `hd2_at1846s_write/read`.
- `src/firmware/include/hrc7000.h` — an alternate (`HRC7000_*`) register map for the modem, including the `0x400..0x424` datapath/burst-control sub-block and `hrc7000_write_modem_ram @0x03058aac`. **`hd2_regs.h` is authoritative for driver code** — write new DMR/modem code against its `SOCSYS_*`/`MODEM_RAM_*` names, not the `HRC7000_*` names here. The two headers are not in conflict on addresses: both define base `0x11000000` and identical offsets (0x400/0x404/0x408…), so the offsets are verified to match and only the symbol names differ. `hrc7000.h` is kept as an RE-era cross-reference (it also documents live values on those regs); don't `#include` both in the same translation unit to avoid duplicate-macro clashes.
- `scripts/labels/dmr_tx.py` — Ghidra labels for the TX burst-control regs (`0x11000418` frametype, `0x41c`, `0x420`, `0x424`) and `modem_rx_spawn_dmr_tasks @0x0305b6b8`.

## Status & deeper reading

**Status: ✅ HW-verified** — wide 4FSK DMR carrier keys and frames correctly on air (2026-06-18). **🟡 In-progress**: decodable voice (needs the software AMBE+2 encoder, Phase 1 — runs but currently no-ops tone vs silence; see memory `hd2-dmr-voice-sw-ambe-codec`), the ~1–2 kHz DMR-mode TX frequency offset (per-radio cal), and a decode confirm with a real DMR decoder. Also still stubbed: own DMR ID (LC source) returns a build-time default until the Radio-ID codeplug table is wired.

Deeper reading:
- `docs/dmr_tx_plan.md` — full plan, phase breakdown, clean-room corrections
- `docs/dmr_c6000_to_c7000_map.md` — HR_C6000 driver → HR_C7000 MMIO mapping
- `docs/dmr_functions.md` — RE'd DMR functions, boot-time IAP modem programmer, sync-word source blob
- `docs/dmr_tx_state.md` — live DBGSHELL idle→keyed IRAM diff (TX state clusters)
- memory `hd2-dmr-tx-onair-bringup` — the temp-slot + TX-RAM unlocks, engine diagnostics, verified register set
- memory `hd2-dmr-tx-progress` — the earlier register-replication dead end and open blocker
- reference capture: `docs/reference/dmr_vendor_keyed_4fsk_433450.png`
