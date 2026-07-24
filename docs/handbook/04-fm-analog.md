---
title: "04. FM analog radio (AT1846S)"
---

# 04. FM analog radio (AT1846S)

**Status:** ✅ HW-verified two-way analog FM (RX + voice TX), CTCSS TX, squelch, RSSI/S-meter. 🟡 DCS, VOX-RX, DTMF-RX unverified on 26 MHz.

## What it is / how it works

The HD2's analog-FM transceiver is the **AT1846SD** RFIC (chip-ID reg `0x00` = `0x1846`), a near-clone of the RDA1846 used by OpenRTX's GDx/UV3x0 targets. The MCU (HR_C7000 / CK803S) talks to it over the on-chip **DesignWare I2C1 controller @ `0x14070000`** (SCL=PTA7, SDA=PTA8; see the [buses chapter](10-buses-peripherals) for the controller recipe), at 7-bit address `0x71` (= `0xE2` on the wire), 8-bit register index, 16-bit **big-endian** values. Two datapaths matter and they are physically separate:

- **RX audio is ANALOG-DIRECT** — the AT1846S demodulates and drives its AFOUT pin straight into the board audio route → speaker amp. The HR_C7000 codec/modem is **not** in the RX signal path. The months-long "quiet AFOUT" mystery was root-caused (2026-06-11) to **GPIOB PTB17**, a path-select/amp-enable that our port never drove — no AT1846S register was ever the cause (this is the analog PATH SELECT covered in the [audio-path chapter](03-audio-path)).
- **FM voice TX is a two-point-modulation datapath through the HR_C7000**: mic → codec ADC → **HR_C7000 FM modulator engine** → MOD1/MOD2 pins → AT1846S varactors → PA. The AT1846S only tunes and keys the carrier (its internal voice mux stays `voice_sel=000`, "Tx nothing"); the mic feed into the engine is pure hardware — no CPU sample pumping.

Everything RF — band select, PA gate, sub-audio encode — is done **inside the AT1846S over I2C**. There is **no discrete PA-enable GPIO and no band-select GPIO on the AT1846S side**; band routing is encoded in reg `0x30`'s field bits, and PA-enable is reg `0x30` bit 7. (The HR_C7000 side does use one GPIO, PTB19, to steer the VHF/UHF RF/PA path — see below.)

## How to implement it

Reference implementation: `radio_HD2.cpp` (radio.h HAL) + `AT1846S_HD2.cpp` (chip driver) + `OpMode_FM.cpp` (core squelch/PTT state machine).

**Init (`radio_init` → `AT1846S::init()`):** a verbatim port of vendor `at1846s_chip_init` @ `0x03058bd4` — a ~38-write inline sequence, no table read. The critical bit is the VCO-calibration dance that must run bit-exact with its delays:

```
0x30 = 0x0001 (soft reset)   delayMs(200)
0x30 = 0x0004 (chip enable)
0x04 = 0x0FD0 (26 MHz xtal)          <- HD2 xtal is 26 MHz, not 12.8/25.6
... PGA/AGC/filter/VCO-tune writes ...
0x30 = 0x40A4  delayMs(100)
0x30 = 0x40A6 (start cal)  delayMs(100)
0x30 = 0x4006 (stop cal)   delayMs(200)
```

**Frequency (`AT1846S::setFrequency`, vendor `at1846s_set_freq` @ `0x03058e24`):**
- reg `0x05` band-select cal word: `0x8763` / `0x8643` (455 MHz special) / `0x8543`, chosen by an 11.375 MHz VCO-subband classifier (`FREQ_BAND_MODULUS=11375000`, `THRESH=11374498`, `SPECIAL=455000000`).
- PLL divider `val = freq_hz * 16 / 1000` (use 64-bit intermediate to avoid overflow >268 MHz): reg `0x29` = `val>>16`, reg `0x2A` = `val & 0xFFFF`.
- Tail: double-writes reg `0x30` = `0x4006` then `0x4046`.

**RX entry (`radio_enableRx`):** `setFrequency(rxFreq)` → `setFuncMode(RX)` (reg `0x30` bits[6:5], `|0x20` = RX on) → enable RX CTCSS/DCS if requested → `hd2_at1846s_rx_audio_config()` (a ~12-write AF-DSP burst — reg `0x40=0x30` LISTEN, `0x41/0x44/0x33/0x54/0x63/0x58/0x4e`, then `setBandwidth(_25)` = **FM audio bank 0**, then `0x3a=0x80e1`, then reg `0x30` = `0x4806`→`0x4826`) → `unmuteRxOutput()` (reg `0x30` bit 7). Run the AF-DSP burst **once per RX entry**, never per squelch crossing (too heavy for the I2C bus). The one-time HR_C7000 modem/codec FM gate is set in `radio_init` via `hd2_modem_fm_boot_init()`, **not** per RX entry.

**FM voice TX key (`radio_enableTx` → `hd2_fm_tx_key`), the single canonical recipe:**
1. `setFrequency(txFreq)` — RAW, no fudge (the old +12.5 kHz shift was removed; residual error is a future per-band calibration).
2. Arm the C7000 engine: `SOCSYS_AF_GATE = AF_GATE_FM_VENDOR` (`0x0001007f`), `SOCSYS_WORK_MODE |= WORK_MODE_FM_MOD` (bit `0x80`; FM-RX runs `0x6e`), `SOCSYS_FM_PTT = 1`.
3. Band select: `GPIOB_DR` bit **19** set if `txFreq >= 300 MHz` else clear.
4. Power: `hd2_txpower_levels()` → **APC** (automatic power control) DAC channel B (`DAC_DATA_B`), which drives the PA power ramp + AT1846S reg `0x0a` padrv field (`(padrv<<11)|0x0420`). Set mic gate GPIOB bit **3** high.
5. TX deviation reg `0x59`: narrow `0x0C90` (no tone) / `0x0B11` (+CTCSS); wide `0x0C50` / `0x0C62` (+tone).
6. Key the carrier (exact words): `0x40=0x0030`, `0x30=0x4006` → `0x4046` (tx_on) → `0x40c6` (+ bit7 = PA on). Bit 7 is the datasheet TX-*mute* bit; setting it is correct **only** here on the MOD-pin voice path (the mic feed bypasses it). For AT1846S internal-tone modes, stop at `0x4046` — see the gotcha below.
7. Sub-audio: `enableTxCtcss/enableTxCdcss`; arm `setTxTailShift(TAIL_180)` if tail-elim.

**TX unkey (`hd2_fm_tx_unkey`):** `DAC_DATA_B=0` → reg `0x30`=`0x4046` (PA off) → `0x4006` (dekey) → reg `0x0a`=`0x4c20` (restore) → power down APC → mic gate off → `SOCSYS_FM_PTT=0`, clear `WORK_MODE_FM_MOD` → reg `0x40=0x0031`, reg `0x59=0x0b90` (restore RX mixer gain, which reg `0x59` shares).

**Feature-map registers** (from `at1846s-fm-feature-map`; tones passed as freq×10):
- **CTCSS**: TX `0x4A=freq×10`, `0x4E[10:9]=11`; RX `0x4D=freq×10`, `0x5B=threshold`, `0x3A[3]=1`; flag `0x1C` bit8.
- **DCS**: `0x4B`/`0x4C` = Golay(23,12) codeword (generator `g=0xC75`, `data12=0x800|(code9&0x1FF)`), `0x4A=13440`, `0x4E[10:9]=10`. RX detect `0x3A[1]` normal / `[2]` invert.
- **Squelch level 0..9**: reg `0x49` = `(th_h<<7)|th_l`; applied AFTER `setBandwidth` (`0x49` is not bank-managed).
- **1750 burst**: `0x35=freq×10`, `0x3A[14:12]=001`, `0x79[15:14]=11`.
- **Tail elim (reverse burst)**: `0x4E[15:14]=phase` (`0x8000`=180°), set `0x30[11]=1` ~180 ms before dekey.
- **VOX**: `0x64=(thHi<<7)|thLo`, `0x30[4]=vox_on`; result `0x1C[1]`.
- **DTMF TX**: `0x35`/`0x36`=row/col×10, `0x3A[14:12]=011`, `0x57[0]=1`, `0x7A[15]=en`, timing `0x7B`. **TX HW-verified.**

**RSSI / squelch:**
- **RSSI** (`radio_getRssi`, vendor `FUN_03040994`): reg `0x1B` layout is `[15:8]=rssi_db`, `[7:0]=noise_db`, both 1 dB units, **dBm = -137 + (reg>>8)**. Idle floor ≈ upper byte `0x2c`–`0x2d` ≈ -92 dBm.
- With **no carrier** the chip refreshes `rssi_db` only periodically (reads near-zero between updates) → the driver applies **peak-hold** (instant rise, ~2 dB/tick fall @ 33 Hz) so the S-meter doesn't flicker to 0. `SNR = rssi_db - noise_db` is the clean signal metric (idle ≈ -50, carrier ≈ +50..+80).
- **Squelch gate uses the AT1846S hardware comparator `sq_cmp` = reg `0x1C` bit 0** (built-in hi/lo hysteresis from `0x48/0x49`), surfaced through the OpenRTX weak hook `radio_checkRxRfSquelch()` — HD2 provides a strong override. This is steadier than thresholding raw RSSI. `sq_dten` selector is reg `0x3A[6]` (rssi1) / `[7]` (noise1); stock config is noise-based (wrong for AFSK; RSSI-only `0x3A=0xe040` opens cleanly on a beacon). `0x5A` = SQ detection-time counts (anti-jitter lever). **No hardware squelch-IRQ line is routed to the CPU — polling `sq_cmp` is the only option.**

**PTT input = GPIOB bit 11, active-low** (`platform_getPttStatus`). A held press is a solid multi-second low. Also doubles as the IAP DFU-entry button at power-on (held with SK1 — see the [boot & IAP chapter](02-boot-flash-pipeline)).

## Gotchas & cautions

- ⚠️ **PTB17 is the RX-audio path-select/amp gate, not any AT1846S register.** HIGH = AT1846S analog demod (FM RX audio); LOW = codec-DAC lineout (MCU beep/voice-prompt). Silent RX audio with a perfect chip config → check PTB17, not the AT1846S. **Do not re-chase AT1846S mute/gain/AGC registers for RX loudness** (`0x47`/`0x42`/`0x43`/`0x44` were all falsified live).
- ⚠️ **There is NO discrete PA-enable GPIO and NO band-select GPIO on the AT1846S.** On the MOD-pin voice path, PA-enable = reg `0x30` bit 7; band routing = reg `0x30` field bits. The `FUN_0002f914(0x31)` "GPIO" lead was wrong — those are pure inter-task SW event flags. Don't hunt for a TR-switch GPIO.
- ⚠️ **Reg `0x30` bit 7 is the datasheet TX-*mute* bit — it only doubles as "PA on" on the MOD-pin voice path.** The two-point-modulation voice TX above deliberately sets it (`0x40c6`) because the mic feed arrives via MOD1/MOD2, which bit 7 does not gate. **Do NOT set bit 7 for any AT1846S internal-tone mode** (1750 burst, DTMF, CTCSS tone gen, AFSK-tone keying) — there the audio *is* the internal-tone path and bit 7 mutes it. Key those modes at `0x4046`, never `0x40c6` (see the [APRS chapter](09-aprs), where `0x40c6` silences the tone).
- ⚠️ **The "weak TX power" hunt was a PHANTOM** — the bench RX radio was deaf; our TX was fine. Swept PTB2/8/14/16/18/22 + PTC0/1/2 = no effect. **Before chasing TX power, verify the receiver against a known-good signal.**
- **AT1846S transport is HW DesignWare I2C1 @ `0x14070000`** (`i2c1_hd2.c`), not bit-bang — live-verified 2026-07-23 (HW-I2C1 reads of regs `0x00`/`0x04`/`0x0a`/`0x33` matched the bit-bang reads byte-for-byte). `i2c0_init()` (despite the `i2c0_` prefix this is the *only* I2C driver — its public API carries a legacy name but operates the single I2C1 controller @ `0x14070000`; see the [buses chapter](10-buses-peripherals)) clears `IO_DIPLEX0` bits 7/8 to steer PTA7/PTA8 from GPIO to the I2C1 function; the HR_C7000 `IC_START` quirk means the whole FIFO is loaded before the transfer is triggered. The old bit-bang driver (SCL=PTA7/SDA=PTA8, `i2c_csky.c` under the now-removed `CSKY_V2` tree) is **historical** — the earlier "HW-I2C1 wedges in continuous operation, keep bit-bang" note is obsolete.
- ⚠️ **I2C bus-contention lockups** were a 3-way race (33 Hz RSSI poll + diag pokes + TX path) with a no-op lock. Fixed with a real `pthread_mutex` in `i2c0_lockDeviceBlocking`/`releaseDevice` (`i2c1_hd2.c`); every transfer funnels through that single chokepoint. **Never call I2C from the UI thread** — `rtx_rxSquelchOpen()` runs on UI, so squelch reads are cached once per rtx tick.
- FM audio **bank 0 = FM/25 kHz, bank 1 = DMR/12.5 kHz** (labels were inverted pre-2026-06-01; loading the DMR bank on FM gives no clean demod audio, only idle hiss). `setBandwidth(_25)` → bank 0.
- Reg `0x3A` must be written **after** `setBandwidth` — the bank table includes `0x3a=0x00c3` and silently clobbers the runtime value.
- ⚠️ Do **not** write `SIG_CENTER`/`RF_MOD_BIAS` on TX — the boot cal modulates cleanest; mid-scale guesses audibly degrade audio and readback shows the RX bank.
- Reg `0x59` is shared between TX deviation and RX mixer gain — always restore `0x0b90` on dekey.
- No `delayUs`/`Thread::sleep(1ms)` in the rtx PTT path — both wedge the tickless CK803S core; only the 30 ms bottom-of-loop `sleepFor` is safe.
- Park the GPS rail PTB15 low at boot — idle GPS NMEA on PTA11 was misread as PTT presses (chunked-TX / red-LED-blip bug).
- 🟡 DTMF-RX Goertzel coeffs (`0x67..0x76`) default to 12.8/25.6 MHz; HD2 is 26 MHz → RX decode unverified, may need a vendor 26 MHz table. VOX-detect-during-RX and DCS also unverified on hardware.

## Where the code lives

- `vendor/wt-hd2-vp-adpcm/platform/drivers/baseband/radio_HD2.cpp` — radio.h HAL: tune, RSSI (`radio_getRssi`), squelch hook (`radio_checkRxRfSquelch` strong override → `hd2_rx_carrier_detected`), FM voice TX key/unkey (`hd2_fm_tx_key`/`hd2_fm_tx_unkey`), AF-DSP config (`hd2_at1846s_rx_audio_config`), one-time modem/codec FM boot (`hd2_modem_fm_boot_init`), APC power levels (`hd2_txpower_levels`).
- `vendor/wt-hd2-vp-adpcm/platform/drivers/baseband/AT1846S_HD2.cpp` — chip driver: `init()` (verbatim vendor chip-init + VCO cal), `setFrequency()`, `setBandwidth()`, `setOpMode()`, `setFuncMode()`, I2C reg r/w, audio bank tables. Constructor `i2c_init()` → `i2c0_init()` at static-init time.
- `vendor/wt-hd2-vp-adpcm/openrtx/src/rtx/OpMode_FM.cpp` — core squelch/PTT/TOT/VOX state machine (the `radio_checkRxRfSquelch` hook it consumes lives in `radio_HD2.cpp`).
- `vendor/wt-hd2-vp-adpcm/platform/mcu/HR_C7000/drivers/i2c1_hd2.c` — HW DesignWare I2C1 @ `0x14070000` (SCL=PTA7/SDA=PTA8) + the `pthread_mutex` lockup fix. This is the live default transport; the FM stack (`radio_HD2.cpp`, `AT1846S_HD2.cpp`, `audio_HD2.c`) sits on the upstreamable `mcu/HR_C7000` structure.

## Status & deeper reading

**Status:** ✅ HW-verified — two-way FM RX (2026-06-11), FM voice TX (2026-06-11/12), CTCSS TX, hardware `sq_cmp` squelch, RSSI/S-meter, TX power levels, PTT=GPIOB.11. Re-derived onto the clean structure and re-verified 2026-07-23. 🟡 DCS TX, VOX-RX, DTMF-RX (26 MHz) unverified.

**Docs:** `docs/at1846s_driver.md`, `docs/pa_control.md`, `docs/audio_paths.md`.

**Memory:** `hd2-at1846s-fm-feature-map`, `hd2-fm-openrtx-port-clean`, `hd2-fm-rx-audio-modem-wall`, `hd2-fm-voice-tx-solved`, `hd2-fm-tx-ptt-and-lockups`, `hd2-rssi-smeter-rx-path`, `hd2-min-bringup-codec-dac-silent`.
