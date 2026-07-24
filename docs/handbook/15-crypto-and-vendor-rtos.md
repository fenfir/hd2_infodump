---
title: "15. Firmware crypto, keystream & the vendor RTOS"
---

# 15. Firmware crypto, keystream & the vendor RTOS

Four loosely-coupled subsystems that share one root fact: the HD2 factory
firmware is a **uC/OS-III (~V3.03) app** wrapped in an encrypted flash
container. This chapter covers (a) the keystream/decryption DB used to peel
that container, (b) the on-device DMR crypto (AES / RC4 / EP-LFSR), (c) the
activation kill-switch and its solved challenge, and (d) the vendor RTOS
reference — struct layouts, task inventory, and the PIC (Programmable Interrupt Controller)/IRQ
table.

## What it is / how it works

**Flash keystream DB.** Vendor images ship XOR/stream-encrypted. The `fwdb`
tool (see the `firmware-keystream` skill) recovers the keystream incrementally:
register *cribs* (known-plaintext fragments — strings, binary constants, or
masked patterns) at a confidence level, `scan` them into candidate *bindings*
(a crib at an offset implies keystream bytes), promote the good ones, let the
solver fill cells. Conflicts (two bindings disagreeing on a byte) are refused
by default and investigated, never force-overwritten. State lives in
`db/firmware.sqlite`, with snapshot/rollback around risky bulk operations.

**On-device DMR crypto.** The runtime cipher library is **AES-128 / AES-256
(FIPS-197, ECB) + RC4, all resident in IRAM** at `0x00015620..0x00017380`.
An identical byte-for-byte copy sits in the app text at `0x03083df4..0x030851ce`
but is **dead code** (⚠️ zero external refs — don't wire to it).
The menu offers `Normal / Enhanced / ARC4 / AES128 / AES256 / Off`; AES128/256
map to the IRAM `dmr_aes_*` primitives, ARC4 to `dmr_rc4_*`, and **`Enhanced`
(DMR Enhanced-Privacy LFSR) is stubbed out** in V2.1.3 — the `dmr_ep_lfsr_*`
functions are empty prologue+`rts` frames (live-verified via DBGSHELL — the
stock-firmware side channel of the [RE pipeline chapter](14-re-pipeline)). Master
key material comes from the codeplug channel record combined with a CSBK
session nonce.

**Activation.** The `Activa` command is a kill-switch: a 7-group integrity
check (`FUN_0304d564`) hashes chip-UID bytes against NVRAM slots; failure gives
"Radio is not activated" (yellow 3-blink LED) and gates RF features. This is
**SOLVED** — the slot map, per-group formulas, and a 2-step re-activation
recipe are known.

**Vendor RTOS.** 22 tasks on uC/OS-III (spawned by the prio-`0x19` bootstrap task on the
[boot path](02-boot-flash-pipeline) after `OSStart`), priorities `0x0a` (shutdown, highest)
to `0x24` (Display, lowest). Kernel struct layouts (OS_TCB 128 B, OS_SEM 40 B)
were recovered empirically from live IRAM and the actual bodies of
`os_task_create` / `OSSemPend` / `OSSemPost` — **not** from stock Micrium
headers, which diverge (see gotchas).

## How to implement it

**Peeling a new firmware region (fwdb).**
1. Add a crib: pick kind (`string|binary|pattern`) + confidence
   (`confirmed|high|medium|low|speculative`); commit to `cribs/seed.yaml` or use
   the live CRUD path.
2. `fwdb cribs scan` → candidate bindings. Inspect before promoting (a
   speculative crib hitting 200 places is junk).
3. `fwdb cribs promote <N>` once the surrounding bytes decrypt sanely and
   another crib corroborates the region.
4. Test a period hypothesis with `fwdb period <N>` vs `<N±1>` — a sharp
   agreement peak = real period.
5. Snapshot before bulk work: `fwdb snapshot create pre-<thing>` →
   `… rollback pre-<thing>` if it goes wrong.

**Driving the DMR cipher (IRAM library).** The live entry points:

| IRAM VMA | Function | Signature |
|---|---|---|
| `0x00016270` | `dmr_aes_KeyExpansion` | `(RoundKey, Key, key_size, Nr)` |
| `0x00016490` | `dmr_aes_Cipher` | `(state_t*, RoundKey, _, Nr)` — Nr=10 or 14 |
| `0x0001666c` | `dmr_aes_InvCipher` | callable; no bulk decrypt path found |
| `0x00016a58` | `dmr_aes_ECB_9block_chain` | 9-block ECB (not 8 like the dead copy) |
| `0x00016b44` / `0x00017040` | `dmr_rc4_ksa` / `dmr_rc4_prga` | ARC4 mode |

S-box tables are shared in BOOTROM: `g_aes_sbox @ 0x18000e08`, `g_aes_inv_sbox
@ 0x18000f08`, `g_aes_rcon @ 0x18001008` (10 × u32 **big-endian**). Mode select
is the per-channel context byte `*PTR_dmr_channel_ctx[0x12]`: `0x01`=RC4,
`0x02`=EP-LFSR(stub), `0x03`=extended-RC4, `0x04`=AES-128, `0x05`=AES-256,
`0x10`=AES-128 w/ Nr=12. TX ciphertext is written to modem RAM offset `0x30`
(27 B, via `hrc7000_write_modem_ram(0x30, buf, 0x1b)`), the 4-B IV/counter to
modem RAM `0x29`. Call chain: `dmr_session_key_setup @ 0x000305f4` →
KeyExpansion/KSA; `dmr_data_frame_encrypt @ 0x030603a4` → block XOR.

**Re-activating any radio (SOLVED recipe).**
1. Flash the patched diagnostic firmware `firmware/PATCHED.ymodem-framed.bin`
   (built by `scripts/patch_crypto_check.py`, a 6×2-byte `br` overlay that
   forces every integrity group to print `加密组别 N: algo=0xXX stored=0xYY`).
   Cold boot; wait **45 s** after YMODEM before sending `3` to boot; capture UART.
2. Send `Activa` with G1=0 to flush a G1 verify (reveals the UID-dependent G1
   algo), then re-send `Activa` with corrected G1 + group-3 fix-ups.

NVRAM slot map (written by `nvram_write @ FUN_0304ba24`, addr + `0x16000000`
LCSFC window; UID buffer at RAM `0x00048350`):

| NVRAM addr | size | group | Activa payload bytes |
|---|---|---|---|
| `0x07ae000` | 4 | g1 (UID-dep) | token[0..3] |
| `0x07ae007` | 4 | g3 (`0x54871eab`) | token[7] + fill[0..2] LE |
| `0x07ae020` | 4 | g11 (UID-dep) | fill[24..27] |
| `0x07ae024` | 4 | g12 (`0x00000246`) | fill[28..31] |
| `0x07ae048` | 4 | g21 (UID-dep) | fill[64..67] |
| `0x07ae04c` | 8 | g22 (UID-dep, formula) | fill[68..75] |
| `0x07ae0c0` | 4 | g50 (UID-dep) | fill[184..187] |

g22 is the only non-trivial transform — a per-byte add/subtract of the 8 UID
bytes at `0x00048350` (`expected_g22()` in `docs/activation.md`).

**Kernel struct layouts (verified offsets).** OS_TCB (128 B, applied to all
22 TCBs) — `StkPtr @ +0x00`, `ExtPtr @ +0x04`, `StkLimitPtr @ +0x08`,
`NamePtr @ +0x20`, `StkBasePtr @ +0x24`, `TaskEntryAddr @ +0x28`,
`TaskEntryArg @ +0x2c`, `Prio @ +0x37` (single byte in a 4-byte slot),
`StkSize @ +0x38`, `Opt @ +0x3c`, `TimeQuanta @ +0x54`, `TimeQuantaCtr @ +0x58`.
OS_SEM (40 B) — `Type @ +0x00` (`'SEMA' = 0x53454d41`), `NamePtr @ +0x04`,
`PendList_Head @ +0x08`, `PendList_Nbr @ +0x10` (u16), `DbgPrev/Next @ +0x18/+0x1c`,
`Ctr @ +0x20`, `TS @ +0x24`.

## Gotchas & cautions

- ⚠️ **The `0x0308xxxx` AES library is dead code in V2.1.3** — zero external
  refs, reachable only by its own internal callers. The live copy is in IRAM
  at `0x00015620`. Don't hook the app-text copy.
- ⚠️ **DMR Enhanced Privacy is stubbed** — `dmr_ep_lfsr_init/step/seed` are
  empty frames (live-confirmed against flash offset `0x7ac2c`). All six callers
  still call in, but the LFSR is a no-op. Don't chase an EP keystream; the radio
  only really does AES + RC4/Basic-Privacy.
- ⚠️ **Manual §5.1.1 says the EP keystream lands at modem RAM `0x495..0x4af` —
  this firmware never writes there.** Ciphertext goes to modem RAM `0x30`. The
  C7000+V3000 die uses a flatter RAM map than the published HR_C6000 spec.
- ⚠️ **The previous fingerprint scan's S-box at `0x0306f2d8` is the IAP copy**
  (VMA `0x0326f2d8` minus IAP base), not the app's. The app dereferences the
  BOOTROM copy at runtime. Three in-image sbox copies exist (app/IAP/BOOTROM);
  only BOOTROM is live.
- ⚠️ **Rcon is big-endian u32, not LE** (an earlier note said LE). Matters for
  KeyExpansion word math.
- ⚠️ **Stock Micrium V3.08 headers do NOT match the firmware.** It was built
  against ~V3.03–V3.05: the `Dbg*` triplet lives at the *end* of OS_SEM/
  OS_FLAG_GRP, and OS_TCB has an extra deprecated `TickSpokePtr @ +0x1C` (128 B
  vs V3.08's 156 B). Use the empirical `/uCOS` types, never the imported
  `/uCOS_vendor` ones, at instance addresses — applying vendor layouts corrupts
  field naming. (OS_PEND_LIST/PEND_OBJ/RDY_LIST/TICK_LIST are identical across
  revisions and safe to apply.)
- ⚠️ **fwdb conflicts: don't `--force`.** A conflict usually means a
  low-confidence binding was wrong — `unsolve` it and re-promote the right one.
- On activation: an **all-zero NVRAM slot can coincidentally match** the algo
  for some UIDs, so a cold radio typically prints only 5 of 7 mismatches — G1
  and G3 stay hidden until non-zero. Send `Activa` with G1=0 to force the print.
- g22 byte order is fixed — **don't swap** the transform outputs; g3's four
  bytes (`ab 1e 87 54`) split across `token[7]` + `fill[0..2]`, also order-fixed.
- TIMER1 (vec 0x21, 100 Hz) **only feeds OSTimeTick** via the deferred
  `OS_IntQPost` — it posts no app FLAG_GRP. The real periodic poster is
  `isr_vec23_systick @ 0x0305b01c` (⚠️ an earlier draft wrongly called
  `FUN_00011924` an app dispatcher — it's stock `OS_IntQPost`).

## Where the code lives

RE artifacts and tooling — the crypto runs from the vendor blob; there is no
re-implemented source yet:

- `skills/firmware-keystream/SKILL.md` — fwdb operating procedures.
- `cribs/seed.yaml`, `db/firmware.sqlite` — crib set + keystream DB.
- `scripts/disasm_aes_region.py`, `scripts/cleanup_aes_funcs.py`,
  `scripts/seed_keyexp.py`, `scripts/apply_aes_renames.py` (⚠️ not present in
  repo — the other three exist) — AES-region recovery pipeline (idempotent).
- `scripts/import_c_types.py` (+ `vendor/tiny-AES-c/`) — types the primitives
  with `state_t*`/`uint8_t* RoundKey`.
- `scripts/patch_crypto_check.py` → `firmware/PATCHED.ymodem-framed.bin` /
  `firmware/PATCHED.decrypted.bin` — activation diagnostic firmware.
- `scripts/fw_flash.py` — YMODEM flash path.
- `scripts/import_ucos3_types.py`, `scripts/apply_os_tcb_struct.py`,
  `scripts/apply_os_sem_struct.py` — kernel struct import/apply.
- `vendor/uC-OS3/Source/{os.h,os_type.h}` (V3.08.02) and
  `vendor/uC-OS-III/uCOS-III/Source/` (V3.03 core, for the function-body match).
- Decompiled corpus: `assets/source_v213/00010000_iram.c` (IRAM kernel + AES),
  `assets/source_v213/0300d000_v2_1_3_app.c` (app shims).

## Status & deeper reading

- **DMR crypto library map** — ✅ HW-verified (live DBGSHELL reads confirm the
  IRAM copy is live, the app copy dead, and EP-LFSR stubbed).
- **Activation challenge / re-activation recipe** — ✅ HW-verified (two UIDs:
  `0.0.1d.5e`/V2.0.8, `0.0.a.92`/V2.0.7).
- **Kernel struct layouts (OS_TCB/OS_SEM) + task inventory + PIC table** — ✅
  cross-checked against live IRAM dumps.
- **Master-key derivation details, `dmr_aes_InvCipher` decrypt path, mode
  `0x10` (Nr=12), `dmr_session_id_hash`** — 🟡 in-progress (open gaps in
  `docs/aes_subsystem.md`).
- **Vendor V3.08 type import applied to instances** — ⚠️ not applied
  (layout mismatch); empirical types remain authoritative.

Source docs: `docs/aes_subsystem.md`, `docs/activation.md`,
`docs/ucos3_import.md`, `docs/ucos3_core_match.md`, `docs/os_tcb_struct.md`,
`docs/os_sem_struct.md`, `docs/rtos_tasks.md`, `docs/irq_handlers.md`,
`docs/pic_handler_table.md`; skill `skills/firmware-keystream/SKILL.md`.
Related memory: `hd2-dmr-voice-sw-ambe-codec` (software AMBE codec, not a HW
vocoder — the crypto workers `encrypt`/`decrypt` are the IRAM tasks named here;
the codec itself is the [voice codecs chapter](07-voice-codecs)).
