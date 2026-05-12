# Channel slot format

## Channels @ radio blocks `0x1BCC..0x1DCF` (`b1=0x31` region)

Each 1024-byte block holds up to 5 channel slots. Slots start at block
offset `0x80`; slot stride is 176 bytes (`0xB0`). The trailing area of
each slot is **not** padding — it holds the inline Rx List (see below).

### Slot header (`+0x00..+0x2F`)

```
  [0x00]   4 B   marker    (0xFFFFFFFF observed for populated slots)
  [0x04]  10 B   name      (ASCII; null- or 0xff-padded for blank)
  [0x0E]   2 B   pad
  [0x10]   4 B   flags / mode-aux  (FM-mode mirror = 0x00002000 LE; DMR = 0x00000000)
  [0x14]   4 B   rx freq   BCD LE, value × 10 Hz
  [0x18]   4 B   tx freq   BCD LE
  [0x1C]   4 B   contact   uint32 LE DMR ID
  [0x20]   4 B   mode / power / scan / TOT / GPS / talkaround
  [0x24]   2 B   rx tone   CTCSS/DCS (0xFFFF = none; FM only)
  [0x26]   2 B   tx tone   CTCSS/DCS (0xFFFF = none; FM only)
  [0x28]   8 B   misc flags / TS / CC / squelch / etc.
```

#### Field-level firmware notes

- **Name (`+0x04`, 10 B):** the on-radio editor surfaces this through three
  keypad input modes (firmware labels at v208 rodata `0x06f5dc`+):
  `CH.Name(abc)`, `CH.Name(ABC)`, `CH.Name(123)` — lowercase, uppercase,
  numeric. The same triplet exists for `ID Name(...)` and a generic
  `Edit(...)`. The radio enforces the 10-byte limit by truncation.
- **Contact (`+0x1C`, 4 B LE DMR ID):** stored as 32-bit LE but the value is
  a 24-bit DMR ID. The radio firmware enforces the upper bound via the
  message *"Id Must be Less Than 16777215"* (= `0xFFFFFF`, the max 24-bit
  unsigned), surfaced at v208 rodata `0x06fe6b`. Values above this are
  rejected by the in-radio editor; whether the codeplug parser silently
  accepts higher values is not tested.

### Tone field encoding (CTCSS / DCS)

Two bytes: `[lo] [hi]`.

| Type         | Encoding                                             | Example |
|--------------|------------------------------------------------------|---------|
| CTCSS        | `hi < 0x80`; value = `BCD(hi, lo) × 0.1 Hz`          | `13 17` = 171.3 Hz |
| DCS Normal   | `hi = 0x80 \| leading_BCD_digit`; `lo = lower 2 BCD` | D023N = `23 80`; D125N = `25 81` |
| DCS Inverted | `hi = 0xC0 \| leading_BCD_digit`; `lo = lower 2 BCD` | D125I = `25 C1` |
| None         | `FF FF`                                              |         |

#### Firmware tone tables (in flash rodata)

The firmware carries two flash-resident lookup tables that enumerate all
valid CTCSS frequencies and DCS codes the radio supports. Both use the
same on-the-wire encoding as the channel tone fields, so they are
direct cribs for what the channel byte values mean.

| Table | v207 offset  | v208 offset  | v213 offset  | Stride | Format |
|-------|--------------|--------------|--------------|--------|--------|
| CTCSS | `0x06bf2c..0x06bf98` | `0x06da3c..0x06daa8` | `0x06dadc..0x06db48` | 2 B (4-B word holds two tones) | 16-bit BCD-LE × 0.1 Hz; e.g. `70 06` = 67.0 Hz |
| DCS   | `0x06bf98..0x06c068` | `0x06daa8..0x06db78` | `0x06db48..0x06dc18` | 2 B            | 16-bit BCD-LE octal code; e.g. `23 00` = D023 (the channel field's `0x80`/`0xC0` bit is **only** in the channel slot, not the lookup table) |

**CTCSS table contents** (v208, 31 entries): 62.5, 67.0, 69.3, 71.9, 74.4,
77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8, 103.3, 117.5, 127.5, 137.2,
145.6, 152.2, 161.4, 166.6, 173.8, 177.3, 199.5, 203.5, 206.5, 210.7,
218.1, 225.7, 229.1, 233.6, 236.5 Hz. (Note: this is a partial subset of
the EIA-standard 38 plus several non-standard entries — the full CTCSS
list is **not** present in v208 firmware. v207 and v213 contain similar
but slightly different sets.)

**DCS table contents** (v208, 103 entries): D023, D025, D026, D031,
D032, D036, D043, D047, D051, D053, D054, D065, D071, D072, D073, D074,
D114, D115, D116, D122, D125, D131, D132, D134, D152, D155, D156, D162,
D165, D172, D174, D205, D212, D223, D225, D226, D243, D244, D245, D246,
D251, D252, D255, D261, D263, D265, D266, D271, D274, D306, D311, D315,
D325, D331, D332, D343, D346, D351, D356, D364, D365, D371, D411, D412,
D413, D423, D431, D432, D445, D446, D452, D454, D455, D462, D464, D465,
D466, D503, D506, D516, D523, D526, D532, D546, D565, D606, D612, D624,
D627, D631, D632, D645, D654, D662, D664, D703, D712, D723, D731, D732,
D734, D743. (Each code is the encoder octal — the channel field's
`0x80`/`0xC0` flag distinguishes Normal vs Inverted reception per
channel.)

Use these tables to:
- Validate any tone byte read from a channel slot is in the supported
  set (rather than raw arbitrary BCD that the firmware would reject).
- Build CSV-export dropdowns with the exact values the radio menu offers.
- Diff against firmware updates: a new CTCSS frequency added in a future
  release will appear as a new entry near the end.

### Mode / option bits

Decoded by single-setting toggle + dump diff. Bit positions are within the
named byte.

#### `+0x10..+0x12` (4-byte flags word, low end)

| Field                 | Mask / position           | Notes |
|-----------------------|---------------------------|-------|
| **DTMF signal index** | `+0x10` bits 6:0 (low 7 bits) | 0-based; UI 1..128 = 0x00..0x7F. DTMF code 1 encodes as 0x00, code 128 as 0x7F. References DTMF Encode Table at `0x4471` in settings region. |
| **PTT ID**            | `+0x11` bits 1:0 (`0x03`) | `00`=None, `01`=BOT (beginning of transmission), `10`=EOT (end of transmission), `11`=Both. Analog channels only. The labels `None`/`BOT`/`EOT`/`Both` are **CPS-only** — verified absent from firmware rodata in raw, DIFF-flipped, and UTF-16 forms. The radio menu instead surfaces `DTMF Signal` (the index-7-bit field) and the BOT/EOT *codes* are stored separately in DTMF Code Fields at settings region `0x4440`/`0x4450` (see `settings.md` "DTMF Code Fields"). |
| **DTMF enable**       | `+0x11` bit 2 (`0x04`)    | Set when DTMF signal selected; also set on newly-created channels by default. |
| **AES family variant**| `+0x11` bits 4:3 (`0x18`) | See "Encrypt Type" below. |
| **Fixed key decryption** | `+0x11` bit 5 (`0x20`)  | Set = on. Checkbox in CPS; requires encryption to be enabled. |
| **RxAll PC** (Private Call) | `+0x11` bit 6 (`0x40`) | Separate from Promiscuous/RxAll CC at `+0x29` bit 0. |
| **GPS contact index** | `+0x12` (1 byte)          | 1-based; `0x00` = none, `0x01` = contact 1, etc. The `+0x12` byte's role beyond GPS-contact is unconfirmed. |
| **Mode-aux mirror**   | `+0x10` byte 0 high bits  | FM channels have `0x00 20 00 00` here; DMR channels have `0x00 00 00 00`. NOT the authoritative mode bit — see `+0x21 bit 6` below. |

#### `+0x20..+0x23` (mode / power / scan)

| Field                | Mask / position                     | Notes |
|----------------------|-------------------------------------|-------|
| **Redundant mode mirror** | `+0x20` byte 0 (`0x01`/`0x02`) | Set ONLY by older CPS-native channel-edit writes (`0x01`=FM, `0x02`=DMR). NOT set by CSV import, factory defaults, or current CPS mode-toggle writes. The radio ignores this byte for mode display. |
| **TxGPS**            | `+0x20` bit 4 (`0x10`)              | Transmit GPS location. |
| **VOX enable**       | `+0x20` bit 5 (`0x20`)              | When set, low nibble = `vox_level − 1` (UI 1..9: vox=1 → 0x20, vox=9 → 0x28). DMR/FM mode bit gets cleared when VOX enabled (mode is preserved in `+0x10`/`+0x21` anyway). |
| **Channel Work Alone** | `+0x20` bit 6 (`0x40`)            | Set = on. Checkbox in CPS channel detail. |
| **GPS enable**       | `+0x20` bit 7 (`0x80`)              | Generic "GPS" checkbox. |
| **Scan Add**         | `+0x21` bit 0 (`0x01`)              | Set = channel included in scan list. Cleared = excluded. |
| **Default to Talkaround** | `+0x21` bit 1 (`0x02`)         | Set = on. Checkbox in CPS. |
| **Power**            | `+0x21` bits 3:2 (`0x0C`) + `+0x29` bit 3 (`0x08`) | Low=00/0, Med=04/0, High=08/0, XtraLow (0.5W)=04/8. "Extra High" untested; plausible `08/8`. Bit 0 of `+0x21` stays set in all observed states. **Firmware menu labels** (v208 rodata `0x06fd4c`): exactly four values: `Low` / `Middle` / `High` / `Extra low` — there is no "Extra High" entry, so that 4-bit combination is most likely unused/reserved. The radio also surfaces an explicit `0.5W Power` toggle from the function-key segment (Key Define `0x1D`), which corresponds to the XtraLow combo. |
| **DMR mode flag**    | `+0x21` bit 6 (`0x40`) — **THE ONE TRUE MODE BIT** | Verified by toggling slot 0 DMR→FM in CPS: only this single bit changed (`+0x21` `0x49` → `0x09`). Set when DMR, clear when FM, regardless of write path (CPS native edit, CSV import, factory defaults, in-radio menu). The radio firmware uses this bit and ONLY this bit to decide mode. |
| **Relay**            | `+0x21` bit 7 (`0x80`)              | Set = relay/talkaround on. Also possibly auto-enabled with GPS enable; observed set when enabling GPS on Ch7 without any Relay toggle. |
| **GPS Timing Report**| `+0x22` (1 byte)                    | GPS position report interval. Encoding: `(seconds − 20) / 10`. `0x00` = OFF, `0x01` = 30 s, `0x62` = 1000 s. Range 30–1000 s in steps of 10. |
| **TOT** (Time-Out Timer) | `+0x23` (1 byte)                | Per-channel. Units: 15 seconds. `0`=off, `1`=15s, `2`=30s, …, `5`=75s, `6`=90s, `8`=120s. |

#### `+0x28..+0x2B` (encryption / RxAll / Promiscuous / CC / TS / DMR mode)

| Field                | Mask / position                     | Notes |
|----------------------|-------------------------------------|-------|
| **2nd Tx Authority** | `+0x28` bit 7 (`0x80`)              | CSV col 25, NOT Promiscuous. |
| **Encrypt family**   | `+0x28` bits 6:5                    | 00=Off, 01=Normal, 10=Enhanced, 11=AES. When family=AES, `+0x11` bits 4:3 select variant: `00`=ARC4, `01`=AES128, `10`=AES256. The firmware **menu** (rodata segment 0 at `0x06df4c..0x06df60` in v208) lists the 6 resulting types as `Off / Normal / Enhanced / ARC4 / AES128 / AES256` (menu indices 0..5). |
| **Encrypt key index**| `+0x28` low nibble (`0x0F`)         | 4-bit index 0..15 (UI shows 1..16, off-by-one). Radio menu label is `Encrypt NO` / 加密组别 (lit. "encryption group"). Key tables: Normal at `0x3D00`, Enhanced at `0x3E00`, AES/ARC4 at `0x5018` — see `settings.md`. |
| **Promiscuous / RxAll CC** | `+0x29` bit 0 (`0x01`)        | CPS labels this "Promiscuous" in CSV (col 24) and "RxAll CC" in the channel UI — same bit, same feature. Set = receive all calls regardless of color code. |
| **TX Authority (analog)** | `+0x29` bits 5:4 (`0x30`)       | 2-bit field: `00`=Allow TX, `01`=Channel Free, `11`=Prohibit TX. |
| **Bandwidth**        | `+0x29` bit 6 (`0x40`)              | Set = wide, cleared = narrow. Firmware menu surfaces this as the `W/N` setting with two values `Narrow` / `Wide` (rodata `0x06fdb8`). |
| **Color Code + DMR Slot + DMR Mode** | `+0x2A` packed nibbles | high nibble `(byte >> 4) & 0x0F` = Color Code (0..15); low nibble bit 0 (`0x01`) = TS (0=TS1, 1=TS2; firmware menu labels these `Slot 1` / `Slot 2`); low nibble bits 3+1 = DMR Mode: Simplex `bit3=0 bit1=0` (mask `0x00`), Repeater `bit3=0 bit1=1` (mask `0x02`), Double slot `bit3=1 bit1=0` (mask `0x08`). DMR-only — FM channels show `0x40` here. The firmware DMR-screen menu (segment 6) presents `DMR Mode` and `DMR Slot` as separate items — the 2 fields really are independently editable. The DMR Mode enum is exactly 3 values: `Simplex` / `Repeater` / `Double Slot` (rodata `0x06fdf4`). |
| **RxGPSInfo**        | `+0x2B` bit 5 (`0x20`)              | Receive GPS info from other stations. |
| **Busy Lock / TX Authority (digital)** | `+0x2B` bits 7:6              | 2-bit field. CPS labels this "Busy Lock" for analog channels and "TX Authority" for digital channels — same bit position. The firmware menu uses unified naming: `Forbid` / `Impolite` / `Polite to CC` / `Polite to All` (rodata segment 1 at `0x06df70..0x06df80`). Digital CSV labels map as: `00`=Prohibit TX = `Forbid`; `01`=Always = `Impolite`; `10`=Color Code = `Polite to CC`; `11`=Channel Free = `Polite to All`. Analog encoding (raw byte values): `00`=Forbid (`0x00`), `01`=impolite (`0x40`), `10`=polite to CC (`0x80`), `11`=polite to all (`0xC0`) — same enum, the analog labels in this doc already use firmware terminology. |

#### `+0x2C..+0x2F` (kill/wakeup codes)

| Field                | Mask / position                     | Notes |
|----------------------|-------------------------------------|-------|
| **Kill Code**        | `+0x2C` (1 byte)                    | 1-based priority contact index. `0x00` = Always/None (default). E.g. `0x02` = priority contact CALL2. |
| `+0x2D`             | 1 byte                              | Unknown / padding. |
| **WakeUp Code**      | `+0x2E` (1 byte)                    | 1-based priority contact index. `0x00` = None (default). E.g. `0x02` = priority contact CALL2. |
| `+0x2F`             | 1 byte                              | Unknown / padding. |

### Inline Rx List (`+0x30..+0xAF`)

A per-channel **inline** list of contacts the channel listens for:

- Array of 4-byte LE DMR IDs, terminated by `0xFFFFFFFF`.
- Capacity ~32 entries (128 B / 4 B per entry).
- The CPS treats Rx Lists as global named lists, but writes them
  **denormalized** into each channel that references the same list — so
  two channels assigned the same Rx List end up with identical inline
  contents. There is no global Rx-Lists table in any region we currently
  read.

## Channel-related firmware error messages

Useful for diagnosing radio behavior when a codeplug write triggers
runtime rejection. All strings live in v208 rodata; the prefix groups
indicate which channel field/feature triggered the message.

| Message                          | Offset (v208) | Trigger |
|----------------------------------|---------------|---------|
| `Digital Channel Can't Set`      | `0x06fdae`    | Bandwidth set on a DMR channel |
| `Analog Channel Can't Set` (slot)| `0x06fdd9`    | Slot set on an FM channel |
| `Channel Mode Can't Set`         | `0x06fe14`    | CH-Mode display change blocked |
| `Freq Mode Can't Set`            | `0x06fe2c`    | Freq display change blocked |
| `Save CH.Name?`                  | `0x06ffa3`    | Confirmation when saving channel |
| `NOAA Can't Set FM Radio`        | `0x06ffac`    | NOAA channels are FM-only / read-only |
| `PF Key Error`                   | `0x07018c`    | Function-key value invalid |
| `Radio Mode Can't Moni`          | `0x070192`    | Monitor disabled in current mode |
| `Moni Error`                     | `0x0701a9`    | Monitor toggle failed |
| `Digital Channel Can't Moni`     | `0x0701ca`    | Tried to enable Monitor on DMR channel |
| `Talkaround On / Repeater On`    | `0x0701d8`    | Talkaround status messages |
| `Repeater Error`                 | `0x07021c`    | Talkaround/repeater toggle failed |
| `Encryption ... Normal/Enhanced` | `0x070232`    | Encryption type display |
| `Digital Channel Can't FM Call`  | `0x0702c8`    | FM-Call attempted on DMR channel |
| `FM Call Error`                  | `0x0702dc`    | FM-Call setup failed |
| `No Group`                       | `0x0702f0`    | Channel has no Rx group assigned |
| `Time Slot DMR Mode Can't Revert Freq` | `0x070304` | Slot/Mode mismatch with frequency |
| `Reverse Error`                  | `0x07033c`    | Reverse-frequency toggle failed |
| `Tx Freq is out of Range`        | `0x070356`    | Tx freq outside band limits |
| `Digital Channel Can't TxTone`   | `0x070366`    | TxTone disabled on DMR |
| `TxTone Error`                   | `0x070388`    | TxTone toggle failed |
| `FM Channel Can't TxCSBK`        | `0x07039a`    | TxCSBK disabled on FM |
| `TxCSBK Error`                   | `0x0703b8`    | TxCSBK toggle failed |
| `Repeater Fail`                  | `0x06efac`    | DMR repeater association failed |
| `Tx Error` / `Channel Busy`     | `0x06efbc`    | Generic Tx failure |
| `No Contacts`                    | `0x06ef9b`    | Channel references missing contact |
| `Low Voltage`                    | `0x06ef88`    | Battery too low to TX |
| `frequency Error`                | `0x06ef74`    | Frequency invalid |

If a feature you expected to toggle silently fails on a CSV import or
codeplug write, expect to see one of these strings on the radio
display — the message ID gives you a direct pointer to which channel
byte/bit the radio rejected.

## VFO-A / VFO-B @ radio `0x0090`, `0x0140`

32-byte records; layout identical to the trailing portion of a channel
slot starting at channel-offset `0x10` (no marker/name prefix):

```
  [0x00]   4 B  flags     (FM = 0x00002000, DMR = 0x00000000)
  [0x04]   4 B  rx freq   BCD LE, value × 10 Hz
  [0x08]   4 B  tx freq   BCD LE, value × 10 Hz
  [0x0C]   4 B  contact   uint32 LE DMR ID
  [0x10]   4 B  mode / bandwidth / power bytes
  [0x14]   2 B  rx tone   (CTCSS/DCS encoding, see above)
  [0x16]   2 B  tx tone   (CTCSS/DCS encoding, see above)
  [0x18]   8 B  flags / squelch / scan (TBD)
```

VFO-B CH-Mode and other VFO-B-only settings appear to live in an
unmapped region, probably radio `0xE800` (CPS reads it during the
setup probe).

## Firmware-confirmed enum value reference

Quick lookup for every enum field in this doc, with the on-radio menu
labels (verified in v208 firmware rodata).

| Field (channel byte)              | Firmware menu values (in order) | Anchor offset |
|-----------------------------------|---------------------------------|---------------|
| Power (`+0x21` bits 3:2 + `+0x29` bit 3) | `Low` / `Middle` / `High` / `Extra low` | `0x06fd4c` |
| Bandwidth W/N (`+0x29` bit 6)     | `Narrow` / `Wide`                | `0x06fdb8` |
| DMR Mode (`+0x2A` low nibble bits 3,1) | `Simplex` / `Repeater` / `Double Slot` | `0x06fdf4` |
| DMR Slot / TS (`+0x2A` low nibble bit 0) | `Slot 1` / `Slot 2`         | `0x06fdce` |
| Encrypt family + variant (`+0x28` 6:5 + `+0x11` 4:3) | `Off` / `Normal` / `Enhanced` / `ARC4` / `AES128` / `AES256` | `0x06df4c` (segment 0) |
| Tx Authority — digital (`+0x2B` bits 7:6) | `Forbid` / `Impolite` / `Polite to CC` / `Polite to All` | `0x06df70` (segment 1) |
| Step (settings `0x297F` — global, but per-channel relevant) | `2.5K` / `5K` / `6.25K` / `10K` / `12.5K` / `20K` / `25K` / `30K` / `50K` / `Forbid` | `0x06ec24` |
| Scan Mode (settings `0x2973` bits 1:0) | `TO` / `CO` / `SE`         | `0x06fd2a` |
| Lock Mode (settings `0x299F` bits 6:5) | `Key` / `Key+CH` / `Key+CH+PTT` | `0x06fd33` |
| CH-Mode display (settings `0x2978` bits 5,0) | `Channel Mode` / `Freq Mode` (and a third "Name" variant referenced by enum but not visible as a labelled option in segment 5) | `0x06fe14`, `0x06fe2c` |
| Sub-audio decoder (`+0x24..+0x27` modes) | `C-CDC` (combined) / `R-CDC` (Rx) / `T-CDC` (Tx) | `0x06e944` |

**CPS-only labels** (verified absent from firmware in raw, DIFF-flipped, and
UTF-16 forms; mapping these to actual radio behavior requires checking
codeplug bit values, not menu inspection): `None` / `BOT` / `EOT` / `Both`
(PTT-ID); `Allow TX` / `Prohibit TX` / `Channel Free` / `Always` (analog
Tx-Authority CSV labels); `Medium` / `180S` / `Address Book` /
`Priority Contacts` / `Send GPS` / `PTT ID` / `DTMF Code` / `GPS Timing`
(CSV column labels). See `cps-csv-format.md` for the full list and the
firmware-vs-CSV correspondence.
