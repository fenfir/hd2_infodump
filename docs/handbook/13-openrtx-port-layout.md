---
title: "13. The OpenRTX port layout & convergence"
---

# 13. The OpenRTX port layout & convergence

## What it is / how it works

The HD2 firmware is an OpenRTX **target** running on a vendored Miosix kernel. Three
independent git forks stack: a **miosix core port** (`fedetft/miosix-kernel` → CK803S /
C-SKY V2 arch + HR_C7000 chip + HD2 board — see the [kernel chapter](12-kernel-cskyv2)),
the **OpenRTX HD2 platform** on top of it,
and an independent **Codec2-mod** fixed-point delta. Layered bottom-up, an OpenRTX port
is: `openrtx/src/*` shared core (UI, RTOS shims, protocols, codec2 — not your job) →
`platform/drivers/<KIND>/<CHIP>_<RADIO>` chip drivers → `platform/targets/HD2/` board glue
→ `platform/mcu/HR_C7000/` (delays, RTC, I2C1 — the new-MCU-family layer; the canonical
`vendor/OpenRTX` tree still names this dir `CSKY_V2/`). The HD2 needed all four because
CK803S, HR_C7000, and the ST7735S panel were all new to OpenRTX.

The single most important structural fact is the **build split**: HD2 is *not* in
OpenRTX's meson build. The 8 legacy ARM targets use OpenRTX's meson, which compiles the
*older* miosix in `vendor/OpenRTX/lib/miosix-kernel` (meson, `arch/cortexMx`) as a library
(Model A). HD2 inverts this (Model B): the cmake project in
`vendor/wt-hd2-vp-adpcm/platform/targets/HD2/CMakeLists.txt` `add_subdirectory`s the
**modern** miosix (`vendor/miosix-kernel`, cmake 3.21, `arch/{cpu,chip,board}`) and pulls
OpenRTX source via `set(ORTX ../../..)`. That worktree (branch `hd2-vp-adpcm`) is the
**live build tree** `docker/build.sh` ships (the build→flash pipeline is the
[boot chapter](02-boot-flash-pipeline)) — a minimal FM + IMA-ADPCM-voiceprompt slice;
`vendor/OpenRTX` holds the fuller canonical layout (DMR, FM-broadcast, M17); both share the
same relative shape, so paths below name the live tree wherever the file exists there.
HD2 was brought up on modern-miosix because it was easier; the decision is to **keep HD2 on
cmake + modern-miosix** and move only device
*code* into the OpenRTX device layer — do not try to push HD2 into OpenRTX's meson, which
would drag it onto the older, harder-to-port miosix.

The second key fact is **convergence is done**: the HD2 no longer runs a bespoke RX/TX
task. The old `hd2_rtx.c` was removed (commit `35bb42f4`, 2026-06-14). HD2 now links the
portable `rtx.cpp` and dispatches real OpModes (`OpMode_FM`, `OpMode_DMR`,
`OpMode_FMBroadcast`) exactly like every other target, with HD2-specific behavior supplied
through weak HAL hooks the board driver strong-overrides. The live `hd2-vp-adpcm` slice
links only `rtx.cpp` + `OpMode_FM.cpp` (FM RX/TX); the DMR/FM-broadcast/M17 OpModes and
their drivers ride the canonical `vendor/OpenRTX` tree, not yet in the shipping build.

## How to implement it

**Boot / dispatch flow** (`vendor/wt-hd2-vp-adpcm/platform/targets/HD2/main.cpp`):
`openrtx_init()` (platform/state/gfx/kbd/ui/vp + codeplug + splash) → `openrtx_run(nullptr)`
which runs `create_threads()` (ui + rtx) then the main loop. ⚠️ The live minimal build does
*not* call `audio_init()` from `main.cpp` — audio routing is warmed by
`radio_HD2.cpp`'s `hd2_codec_audio_init()` on the FM-enable path. The **canonical**
`vendor/OpenRTX` main.cpp *does* insert an explicit `audio_init()` call between
`openrtx_init()` and `openrtx_run()` (`rtx_init` never inits audio; only the removed
`hd2_rtx.c` used to bundle it). Match whichever tree you build.

**OpMode dispatch** (`openrtx/src/rtx/rtx.cpp`): `rtx_task` holds `currMode`, starts at
`&noMode`, and on config change switches on `rtxStatus.opMode`:
`OPMODE_NONE→noMode`, `OPMODE_FM→fmMode`, `OPMODE_DMR→dmrMode`, `OPMODE_M17→m17Mode`,
`OPMODE_FM_BCAST→fmBcastMode`, calling `disable()`/`enable()`/`update()`. The enum lives in
`openrtx/include/rtx/rtx.h`: `OPMODE_NONE=0, OPMODE_FM=1, OPMODE_DMR=2, OPMODE_M17=3,
OPMODE_FM_BCAST=4`. `currMode = &noMode` until the first config replaces the old
`cfgApplied`/static-burst hack — no RX audio before the codeplug squelch lands, for free.

**The weak-HAL override pattern** (how HD2 behavior rides the portable OpModes without
regressing the 8 ARM targets — each hook is a weak no-op/RSSI-fallback default in the
portable layer, strong-overridden in the HD2 driver):
- **Squelch**: `radio_checkRxRfSquelch(bool *open)` (`interfaces/radio.h`), consulted in
  `OpMode_FM::update()`. HD2 override in `radio_HD2.cpp` returns the AT1846S `sq_cmp` bit —
  `at1846s_read_reg(0x1C) & 0x0001` — instead of a raw-RSSI threshold.
- **FM TX extras**: `radio_fmToneBurst()`, `radio_fmTailElim()`, `radio_fmVoxArm(level)`,
  `radio_fmVoxDetected()` (`interfaces/radio.h`) map to AT1846S tone1 / reverse-burst /
  VOX in `radio_HD2.cpp`. Burst+tail are blocking, safe because the WDT is fed in
  `threads.c` before `rtx_task`.
- **WDT**: portable failsafe `watchdog_kick()` (`interfaces/watchdog.h`, weak no-op),
  kicked once per rtx loop in `threads.c`; HD2 strong override in
  `platform/targets/HD2/watchdog_HD2.c` arms (~10 s) + feeds the HR_C7000 WDT
  (`HD2_WDG_EN` at `0x14010010` bit0=1 when armed).
- **Broadcast tuner**: `interfaces/tuner.h`
  (`tuner_init/powerUp/powerDown/tune(khz)/rssi/getStatus`), weak no-ops so tuner-less
  targets link. HD2 strong override in `RDA5802E_HD2.c` (`tuner_powerUp/tune/getStatus`)
  maps to the `fm_broadcast_*` driver + AT1846S AF-mute. `OpMode_FMBroadcast` tunes
  `rtxStatus.rxFrequency`; the UI FM screen sets `opMode = OPMODE_FM_BCAST` via
  `rtx_configure`.

**CMake wiring** (`vendor/wt-hd2-vp-adpcm/platform/targets/HD2/CMakeLists.txt`):
`MIOSIX_KPATH` points at `vendor/miosix-kernel/miosix` (a fixed default in the worktree,
overridable via `-DMIOSIX_KPATH=`); toolchain is `gcc-csky.cmake`; `MIOSIX_BOARD =
hrc7000_hd2`. The live radio set (`ORTX_RADIO`) links `rtx.cpp` + `OpMode_FM.cpp` + the HD2
baseband/audio drivers — **not** `hd2_rtx.c`, and no DMR/M17/broadcast objects. Voice
prompts use the IMA-ADPCM player (`ORTX_VP`: `voicePrompts_adpcm.c` + `voicePromptData_adpcm.S`),
not codec2. Defines are minimal: `PLATFORM_HD2 _MIOSIX FONT_UBUNTU_REGULAR timegm=mktime`.
The **canonical** `vendor/OpenRTX` CMakeLists adds the fuller feature gates —
`WITH_HD2_TRACE` (set before `add_subdirectory(miosix)` so it reaches kernel + app),
`HD2_M17` / `HD2_M17_VOICE` (Codec2-mod fixed-point, `-DMIOSIX_LINKER_SCRIPT=hd2_m17.ld` for
the low-RAM origin), `HD2_DMR_TX_LIVE`, `HD2_DMR_VOICE` (carved AMBE blob, off + not in
repo), `HD2_LCD_BITBANG` / `HD2_SPI_BITBANG` (HW-bus fallbacks, default = HW controllers).

**Upstream branch structure** (target, from `docs/upstream_plan.md`): three PRs to three
upstreams. miosix: `master` (v3.01 mirror) ← `hd2-miosix-port` (kernel-only, OpenRTX-free,
build-verified). OpenRTX: feature-layered `hd2-platform` (#1–50, `bd18cc59`) → `hd2-dmr`
(#51–71, `154e6be2`) → `hd2-m17` (#72–79, `044f1afc`); orthogonal architectural cut
`hd2-device` (all `platform/`) vs `hd2-app` (all `openrtx/`). Codec2-mod: `C2_FIXED` as an
independent PR to `M17-Project/Codec2-mod`.

## Gotchas & cautions

- ⚠️ **Two different miosix forks — do not confuse them.** `vendor/miosix-kernel` = modern
  (cmake, what HD2 uses). `vendor/OpenRTX/lib/miosix-kernel` = older (meson, what the 8 ARM
  targets use). They are independent dirs, no symlink.
- ⚠️ **Dead end: pointing OpenRTX meson at the external miosix.** Won't work — modern
  miosix is cmake-only and a different layout; it would force HD2 onto the older miosix.
  Keep HD2 on cmake.
- ⚠️ **Obsolete guidance: "HD2 runs hd2_rtx.c which doesn't dispatch OpModes."** Superseded
  2026-06-14. `hd2_rtx.c` is deleted; the portable OpMode dispatch is live. Do not
  reintroduce it.
- ⚠️ **`g_radio_enabled` boot-deferral is dead.** It was an I2C-wedge diagnostic;
  `rtx.cpp`'s `rtx_init` calls `radio_init` synchronously in the rtx thread (boot is past).
  Only a vestigial stub remains for diag op 'F'.
- ⚠️ **`audio_init()` call site differs by tree.** `rtx_init` never inits audio; only the
  removed `hd2_rtx.c` used to bundle it. The canonical `vendor/OpenRTX` main.cpp calls
  `audio_init()` explicitly. The live `hd2-vp-adpcm` main.cpp does *not* — routing is warmed
  by `radio_HD2.cpp`'s `hd2_codec_audio_init()` on the FM path. Don't add a duplicate call
  when building the live tree.
- **Broadcast FM silent-until-nudge regression** (canonical tree only — FM-broadcast is not
  in the live slice): the UI re-posts the channel (FM) config on entry, reverting
  `OPMODE_FM_BCAST` → `tuner_powerDown`. Guard with `ui_screen==FM_RADIO`. See the
  FM-broadcast regression memo.
- **`hd2_fm_broadcast.cpp` (canonical only)** still links there (in `add_executable`) but the
  worker thread is gutted — it only carries the `g_fm_*` UI-bridge globals, not a separate
  audio thread. The file is absent from the live worktree.
- **M17 is not upstream-shaped** (canonical tree). The M17 PHY lives in diag op `s`/`g` (a
  bring-up harness, not an OpMode); it depends on DMR at the file level (`hd2_m17_phy_*`
  lives inside `dmr_HD2.cpp`) and touches one portable file (`protocols/M17/Modulator.cpp`,
  `PLATFORM_HD2` branch). Isolate that as a standalone guarded patch.
- **The shipping build is a git worktree.** `docker/build.sh` builds
  `vendor/wt-hd2-vp-adpcm` (branch `hd2-vp-adpcm`), not the outer hd2-clean repo and not the
  canonical `vendor/OpenRTX` checkout. Feature branches live as sibling worktrees; flash
  serially (one TUI owns the serial port).

## Where the code lives

**Live build tree — `vendor/wt-hd2-vp-adpcm/` (branch `hd2-vp-adpcm`, what `docker/build.sh`
ships): FM + IMA-ADPCM voice prompts.**

- Build tree / dispatch wiring: `vendor/wt-hd2-vp-adpcm/platform/targets/HD2/CMakeLists.txt`,
  `.../HD2/main.cpp`, `.../HD2/hd2_glue.cpp`
- Portable rtx + FM OpMode: `vendor/wt-hd2-vp-adpcm/openrtx/src/rtx/rtx.cpp`,
  `.../rtx/OpMode_FM.cpp`; enum in `.../openrtx/include/rtx/rtx.h`; weak-HAL radio interface
  in `.../openrtx/include/interfaces/radio.h`
- HD2 board glue: `vendor/wt-hd2-vp-adpcm/platform/targets/HD2/` — `platform.c`,
  `hwconfig.{c,h}`, `pinmap.h`
- HD2 drivers (strong HAL overrides): `.../platform/drivers/baseband/radio_HD2.cpp`
  (`radio_checkRxRfSquelch` → AT1846S `sq_cmp`, reg 0x1C bit0),
  `.../baseband/AT1846S_HD2.cpp`, `.../audio/audio_HD2.c`, `.../audio/outputStream_HD2.cpp`,
  `.../display/ST7735S_HD2.c`, `.../keyboard/keyboard_HD2.c`, `.../backlight/backlight_HD2.c`,
  `.../GPIO/gpio_hrc7000.c`, `.../ADC/adcHrc7000.c`, `.../GPS/gps_HD2.c` + `nmea_rbuf.c`
- MCU layer: `vendor/wt-hd2-vp-adpcm/platform/mcu/HR_C7000/` — `registers.h`,
  `drivers/{delays.cpp, rtc_hd2.c, i2c1_hd2.c}`
- Voice prompts (IMA-ADPCM): `.../openrtx/src/core/voicePrompts_adpcm.c` +
  `voicePromptData_adpcm.S` (embeds repo-root `voiceprompts.vpa`)
- Kernel port: `vendor/miosix-kernel` (branch `hd2-miosix-port`)

**Canonical / reference layout — `vendor/OpenRTX/` (fuller feature set, not in the live
slice).** Same relative layout; these files exist only here:

- OpModes: `.../openrtx/src/rtx/OpMode_DMR.cpp`, `.../rtx/OpMode_FMBroadcast.cpp`
- HAL interfaces: `.../openrtx/include/interfaces/tuner.h`, `.../interfaces/watchdog.h`
- Board glue: `.../platform/targets/HD2/` — `hd2_stubs.c`, `hd2_diag.cpp`, `watchdog_HD2.c`,
  `hd2_fm_broadcast.cpp` (gutted bridge), `hd2_pcm_stream.cpp`, `hd2_gps.cpp`
- Drivers: `.../baseband/dmr_HD2.cpp`, `.../baseband/RDA5802E_HD2.c`, `.../NVM/*_HD2.c`
- MCU layer named `platform/mcu/CSKY_V2/` (drivers `gpio_csky.c`, `i2c_csky.c`, `adc_hd2.c`,
  `rtc_hd2.c`) — the live tree re-derived these as `gpio_hrc7000.c` / `i2c1_hd2.c` /
  `adcHrc7000.c` under `HR_C7000/` + shared driver dirs
- Low-RAM linker script for codec2/M17: `.../platform/targets/HD2/hd2_m17.ld`

## Status & deeper reading

**Status: ✅ HW-verified** — the OpMode convergence landed (commit `35bb42f4`) and passed
the 2026-06-15 review; `rtx.cpp` + `OpMode_FM` dispatch live on hardware. The shipping build
is the minimal `vendor/wt-hd2-vp-adpcm` worktree (FM + IMA-ADPCM voice prompts). 🟡
in-progress: folding the canonical `vendor/OpenRTX` feature set (DMR / FM-broadcast / M17
OpModes, tuner + watchdog HAL) onto the clean CMSIS `HR_C7000` structure the live worktree
uses; the three-upstream PR split (branches assessed/pointer-cut but the OpenRTX
`hd2-platform → hd2-dmr → hd2-m17` stack not yet created); full meson integration deferred.
⚠️ The M17 diag→OpMode refactor is deferred.

Sources distilled:
- `docs/upstream_plan.md` — three-fork inventory, branch structure, cut-point SHAs
- `skills/openrtx-port/SKILL.md` — the port-layer recipe (mcu/target/driver order, worktrees)
- memory `hd2-openrtx-convergence-roadmap` — two-repos/two-miosix map, fork-cleanup, OpMode_FM
  + OpMode_FMBroadcast convergence
- memory `hd2-fm-broadcast-opmode-silent-regression` — the entry-config gotcha downstream of
  convergence
- memory `hd2-rssi-smeter-rx-path` — the `sq_cmp` squelch source behind the `radio_checkRxRfSquelch` override
