# Diff test plan

One CPS write → one fast dump → one diff. Each session is designed to extract
the maximum number of data points from a single CPS write operation.

## Setup

```bash
PORT=/dev/cu.usbserial-120

# Baseline before each session (settings block covering 0x2980..0x29FF):
mise exec -- python3 hd1_dump.py --port $PORT --regions settings --addr-range 0x2980 --out /tmp/before.bin

# Re-dump after CPS write:
mise exec -- python3 hd1_dump.py --port $PORT --regions settings --addr-range 0x2980 --out /tmp/after.bin

# Diff helper:
python3 -c "
a=open('/tmp/before.bin','rb').read(); b=open('/tmp/after.bin','rb').read()
[print(f'  radio 0x{0x2980+i:04x} (+0x{i:02x}): 0x{a[i]:02x} -> 0x{b[i]:02x}') for i,(x,y) in enumerate(zip(a,b)) if x!=y]
"
```

For channel-level tests, replace `--regions settings --addr-range 0x2980` with
`--regions channels --addr-range 0x1BCC` (or the block containing the channel).

---

## Write session 1 — Addresses: emergency key, priority scan, scan ranges

**What we learn**: confirms the addresses of emergency key short/long (`0x29AE`/`0x29AF`
vs `0x29AC`), priority scan channel, alarm type, and scan range encoding in one shot.

**CPS changes (all in one write)**:
| Setting | Change to | Expected address | Expected encoding |
|---------|-----------|------------------|-------------------|
| Emergency key Short | Scan | `0x29AE`? or `0x29AC`? | emergency enum value for Scan |
| Emergency key Long | Power | `0x29AF`? | emergency enum value for Power |
| Emergency Alarm type | Remote | near `0x29AC`..`0x29B0`? | unknown |
| Priority Scan Channel | CH 3 | `0x29AC`? | 0-based index = `0x02` |
| VHF Scan Start | 144.000 MHz | `0x29C0` | BCD LE × 100 kHz = `40 14`? |
| VHF Scan Stop  | 148.000 MHz | `0x29C2` | `80 14`? |
| UHF Scan Start | 430.000 MHz | `0x29C8` | `00 43`? |
| UHF Scan Stop  | 440.000 MHz | `0x29CA` | `00 44`? |

**Dump**: `--regions settings --addr-range 0x2980`

**Key questions resolved**:
- Do bytes at `0x29AE`/`0x29AF` change? → confirms MEMORY.md layout (emergency = AE/AF)
- Does `0x29AC` show `0x02` (CH3 index)? → confirms it's Priority Scan CH
- What bytes appear at `0x29C0..0x29CB`? → confirms scan range encoding
- Which byte near `0x29AC..0x29B0` changed for Remote alarm? → alarm type address

---

## Write session 2 — Key enum batch A (disputed 0x0D..0x11)

**What we learn**: resolves the biggest MEMORY.md vs settings.md conflict in the
0x0D..0x11 range (Kill, Zone+, Zone−, DMR Slot, 1000Hz).

**CPS changes**:
| Slot | Set to | settings.md predicts | MEMORY.md predicts |
|------|--------|---------------------|--------------------|
| Key1 Short | Kill (Remote Kill) | `0x0D` | `0x0E` |
| Key1 Long  | Zone Plus          | `0x0E` | `0x15` |
| Key2 Short | Zone Minus         | `0x0F` | `0x16` |
| Key2 Long  | DMR Slot           | `0x10` | `0x17` |

Plus (same write, different addresses):
| Setting | Change to | Address |
|---------|-----------|---------|
| Emergency key Short | Kill | `0x29AE` (confirmed in session 1) |
| Emergency key Long  | 1000Hz | `0x29AF` |

Emergency key changes let us cross-check: if Emergency "Kill" stores the same
byte as Key1 Short "Kill" → single shared enum. If different → two separate enums.

**Dump**: `--regions settings --addr-range 0x2980`

---

## Write session 3 — Key enum batch B (0x11..0x17 range)

| Slot | Set to | settings.md | MEMORY.md |
|------|--------|-------------|-----------|
| Key1 Short | 1000Hz  | `0x1C` | `0x11` |
| Key1 Long  | 1450Hz  | `0x1D` | `0x12` |
| Key2 Short | 1750Hz  | `0x1E` | `0x13` |
| Key2 Long  | 2100Hz  | `0x1F` | `0x14` |

Plus emergency crosscheck:
| Setting | Change to |
|---------|-----------|
| Emergency key Short | 1000Hz |
| Emergency key Long  | 2100Hz |

This batch directly resolves the `0x11` vs `0x1C` for 1000Hz conflict.

**Dump**: `--regions settings --addr-range 0x2980`

---

## Write session 4 — Key enum batch C (0x14..0x1B range)

| Slot | Set to | settings.md | MEMORY.md |
|------|--------|-------------|-----------|
| Key1 Short | Reverse        | `0x14` | `0x21` |
| Key1 Long  | Bluetooth      | `0x15` | `0x1C` |
| Key2 Short | 0.5W Power     | `0x16` | `0x1D` |
| Key2 Long  | FM Call        | `0x17` | `0x1E` |

Plus:
| Slot | Set to | settings.md | MEMORY.md |
|------|--------|-------------|-----------|
| Emergency Short | Promiscuous  | — | `0x16` |
| Emergency Long  | Manual Dial  | — | `0x17` |

**Dump**: `--regions settings --addr-range 0x2980`

---

## Write session 5 — Key enum batch D (0x18..0x1B + upper range)

| Slot | Set to | settings.md | MEMORY.md |
|------|--------|-------------|-----------|
| Key1 Short | Voltage        | `0x18` | `0x1F` |
| Key1 Long  | NOAA           | `0x19` | `0x20` |
| Key2 Short | Analog Monitor | `0x1A` | not in K1/K2? |
| Key2 Long  | TX Digital Dev | `0x1B` | not in K1/K2? |

Plus:
| Slot | Set to |
|------|--------|
| Emergency Short | NOAA |
| Emergency Long  | Analog Monitor |

**Dump**: `--regions settings --addr-range 0x2980`

---

## Write session 6 — Key enum batch E (long-only extras + CH-Mode/Promiscuous)

| Slot | Set to | settings.md | MEMORY.md |
|------|--------|-------------|-----------|
| Key1 Short | Promiscuous | `0x11` | `0x18..0x1B` |
| Key1 Long  | Manual Dial | `0x12` | `0x18..0x1B` |
| Key2 Short | CH-Mode     | `0x13` | `0x18..0x1B` |
| Key2 Long  | TX-DSW (long only) | `0x20` | `0x20`? |

Plus (Key1 Long only — long-press extras):
Set Key1 Long to each long-only function in separate passes **within this same CPS
session** — you can cycle Key1 Long through all 6 and note CPS's stored byte
representation by doing 6 quick writes:

| Key1 Long value | settings.md value |
|-----------------|-------------------|
| TX-DSW  | `0x20` |
| M-MONI  | `0x21` |
| Tx1000  | `0x22` |
| Tx1450  | `0x23` |
| Tx1750  | `0x24` |
| Tx2100  | `0x25` |

These 6 require 6 writes but each is a single 1-byte change at `0x29A9` — fastest
possible diff (only one byte changes per write). Alternatively batch all 6 by
writing Key1L=TX-DSW, Key2L=M-MONI in write 6a, then Key1L=Tx1000, Key2L=Tx1450
in write 6b, etc. (3 writes instead of 6).

**Dump each**: `--regions settings --addr-range 0x2980`

---

## Write session 7 — Emergency enum completeness

By now emergency enum values for Scan, Power, Kill, 1000Hz, 2100Hz, Promiscuous,
Manual Dial, NOAA, Analog Monitor are known. Cover the rest:

| Emergency Short | Emergency Long |
|-----------------|----------------|
| CH-Mode | Bluetooth |

| Emergency Short | Emergency Long |
|-----------------|----------------|
| Voltage | Reverse |

| Emergency Short | Emergency Long |
|-----------------|----------------|
| Zone Plus | Zone Minus |

These 3 writes resolve the full emergency enum.

Also in one of these writes, add: **Emergency Alarm = Local** (undo the Remote
from session 1) to confirm the alarm type byte encoding goes `Remote → Local`.

---

## Write session 8 — Settings gaps (flags and unknowns)

**Goal**: confirm documented bits and locate undocumented ones.

**CPS changes (all in one write)**:
| Setting | Change | Address | Expected |
|---------|--------|---------|----------|
| Double PTT | ON | `0x2973` bit 3 | `0x08` set |
| Scan Mode | CO (carrier) | `0x2973` bits 1:0 | `0x01` |
| Save | 1:4 | `0x2973` bits 7:5 | `0x80` |
| Miss Call Set | ON | `0x299D` bit 0 | `0x01` set |
| Rx Info Bright Set | ON | `0x299F` bit 7 | `0x80` set |
| Night Mode | ON (= clear bit 3) | `0x2978` bit 3 | `0x08` cleared |
| Noise Tail | ON | `0x2977` bit 2 | `0x04` set |
| Lock Mode | key+ch+ptt | `0x299F` bits 6:5 | `0x60` |
| Tx Channel | (toggle) | **unknown** | any change |

**Dump**: `--regions settings --addr-range 0x2980`
Also dump `--addr-range 0x2900` to catch changes outside the 0x2980 block.

Tx Channel is expected to land somewhere in the unmapped gaps; a full settings
diff (`--regions settings`) may be needed if it doesn't appear in the two 128-byte blocks.

---

## Write session 9 — Shift Up direction (channel-level)

**Goal**: find the Shift Up direction bit in channel slots.

**CPS changes**:
1. Create or edit a repeater channel: set TX freq = RX + 600 kHz, Shift Up = **+** (positive offset).
2. Write to radio.
3. Dump: `--regions channels --addr-range <block containing channel>`.
4. In same CPS write (or immediately after): flip **Shift Up → −** (negative), re-write.
5. Diff the two channel dumps.

Also diff the settings region for `0x2985` vicinity — if Shift Up direction is
global it may be a bit near the Shift Freq bytes.

---

## Write session 10 — Table regions (DTMF, 2-tone/5-tone)

**Goal**: locate DTMF digit sequences and 2-tone/5-tone tables in `table_428x`.

**CPS changes**:
- Program DTMF Signal 1 = digit string `"1234"`, DTMF Signal 2 = `"5678"`.
- Program at least one 2-tone and one 5-tone code (if CPS supports it).
- Write to radio.

**Dump**:
```bash
mise exec -- python3 hd1_dump.py --port $PORT --regions table_428x --out /tmp/t428x_after.bin
mise exec -- python3 hd1_dump.py --port $PORT --regions table_1dfx --out /tmp/t1dfx_after.bin
```

Search the result for `0x31 0x32 0x33 0x34` (ASCII "1234"). Record stride and
base offset to determine the full DTMF table layout.

---

## Summary — total writes

| Session | Writes | Resolves |
|---------|--------|----------|
| 1 | 1 | Emergency address, priority scan address, scan range encoding, alarm type address |
| 2 | 1 | Kill/Zone+/Zone−/DMR Slot values + emergency crosscheck |
| 3 | 1 | 1000Hz/1450Hz/1750Hz/2100Hz values + crosscheck |
| 4 | 1 | Reverse/Bluetooth/0.5W/FM Call values |
| 5 | 1 | Voltage/NOAA/Analog Monitor/TX Digital Dev values |
| 6 | 3 | Promiscuous/Manual Dial/CH-Mode + all 6 long-only extras |
| 7 | 3 | Remaining emergency enum values |
| 8 | 1 | Settings flag bits verification + Tx Channel address |
| 9 | 2 | Shift Up direction bit |
| 10 | 1 | DTMF digit table location |
| **Total** | **15** | All open questions |
