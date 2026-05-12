# CPS Channel CSV Format

The HD2 CPS imports/exports channels as CSV with 75 columns. The header
row must match exactly. Empty trailing rows are required.

## Column Reference (75 columns)

| # | Column | Values | Notes |
|---|--------|--------|-------|
| 0 | No. | `VFO-A`, `VFO-B`, `1`..`3000` | VFOs are separate entries |
| 1 | Channel Type | `Digital CH`, `Analog CH` | |
| 2 | Channel Alias | string (max 10 chars) | Empty for VFOs |
| 3 | Rx Frequency | `438.72500` | 5 decimal places |
| 4 | Tx Frequency | `431.12500` | 5 decimal places |
| 5 | Tx Power | `High`, `Medium`, `Low` | |
| 6 | TOT | `180S`, `OFF` | Timeout timer |
| 7 | VOX | `No`, `Yes` | |
| 8 | VOX Level | `1`..`9` | |
| 9 | Scan Add/Step | `Yes`, `No`, `2.5K`, `5K`, `6.25K`, `10K`, `12.5K`, `20K`, `25K`, `30K`, `50K`, `Forbid` | VFOs use step value; `Forbid` disables step |
| 10 | Channel Work Alone | `No`, `Yes` | |
| 11 | Default to Talkaround | `No`, `Yes` | |
| 12 | Band Width | `25K`, `12.5K` | |
| 13 | Dec QT/DQT | `None`, CTCSS freq, DCS code | |
| 14 | Enc QT/DQT | `None`, CTCSS freq, DCS code | |
| 15 | Tx Authority | `Allow TX`, `Prohibit TX`, `Channel Free` | Analog side |
| 16 | Relay | `No`, `Yes` | |
| 17 | Work Mode | `Simplex`, `Repeat`, `Repeater` | Firmware display uses `Simplex`/`Repeater`; `Repeat` is a CSV alias |
| 18 | Slot | `Slot1`, `Slot2` | DMR only; firmware displays as `Slot 1`/`Slot 2` (space) |
| 19 | ID Setting | radio ID name (e.g. `radio-1`) or empty | |
| 20 | Color Code | `0`..`15` | DMR only |
| 21 | Encryption | `No`, `Yes` | |
| 22 | Encryption Type | `Normal Mode`, `Enhanced`, `Special` | Firmware menu enum: `Normal`, `Enhanced`, `ARC4`, `AES128`, `AES256` — CPS `Special` covers the AES/ARC4 ciphers |
| 23 | Encryption Key | `1`..`16` | Key index (radio menu calls this `Encrypt NO`) |
| 24 | Promiscuous | `No`, `Yes` | |
| 25 | Tx Authority | `No`, `Always`, `Forbid` | Digital side (2nd column); firmware menu enum: `Impolite`, `Polite to CC`, `Polite to All`, `Forbid` — channel-access policies |
| 26 | Kill Code | `Always`, `Forbid`, contact name | |
| 27 | WakeUp Code | `None`, contact name | |
| 28 | Contacts | `None`, `Priority Contacts: NAME`, `Address Book Contacts: ID` | |
| 29 | Rx Group Lists | `Custom`, `None`, list name | |
| 30-33 | (unnamed) | Group list refs | Part of Rx Group Lists |
| 34-63 | Group Lists 1-30 | Contact references | 30 group list member columns |
| 64 | GPS | `No`, `Yes` | |
| 65 | Send GPS Info | `No`, `Yes` | |
| 66 | Receive GPS Info | `No`, `Yes` | |
| 67 | GPS Timing Report | `OFF`, `30`..`1000` | Seconds |
| 68 | GPS Timing Report TX Contacts | `None`, contact name | |
| 69 | PTT ID | empty, `BOT`, `EOT`, `Both` | Analog only |
| 70 | Opt.Signal | empty, `DTMF` | Analog only |
| 71 | DTMF Code Group | empty, `1`..`128` | DTMF code index |
| 72 | Fixed key decryption | `Yes`, `No` | |
| 73 | RX all private call | `No`, `Yes` | |
| 74 | (trailing comma) | empty | |

## Critical Format Requirements

- **Line endings MUST be Windows `\r\n` (CRLF).** Unix `\n` will cause import failure.
- VFO-A and VFO-B entries MUST be the first two data rows.
- The file MUST end with several empty rows (75 commas per row).
- All frequencies use 5 decimal places (e.g. `438.72500`).

## Notes

- Column 17 "Work Mode": use `Repeat` (not `Repeater`) for repeater channels.
- Column 19 "ID Setting": must reference an existing radio ID name (e.g. `AI5QZ`).
  Empty value causes import failure.
- Column 25 "Tx Authority" is the DIGITAL side — different from column 15 (analog).
- Column 29 "Rx Group Lists": use `&H00000000` for no group, with `Custom` in column 30.
  Empty value may cause import failure.
- Contacts reference format: `Priority Contacts: NAME` or `Address Book Contacts: NUMBER`.
- Import replaces existing channels (not additive).

## Firmware menu strings (cross-reference)

Verified against decoded HD2 firmware v2.0.8 rodata strings (and corroborated
across v2.0.7 and v2.1.3). Useful for diff-by-display when a CPS dropdown
value is ambiguous.

- **Step (col 9)** — full menu enum: `2.5K`, `5K`, `6.25K`, `10K`, `12.5K`,
  `20K`, `25K`, `30K`, `50K`, `Forbid`. Adjacent to step in firmware: a
  separate `1750` Hz repeater wakeup tone option (not exported via this
  column).
- **Slot (col 18)** — firmware displays `Slot 1` / `Slot 2` with a space.
  CSV uses `Slot1` / `Slot2` (no space). Also has `Double Slot` option
  visible on the radio.
- **Encryption Type (col 22)** — firmware menu lists five values:
  `Normal`, `Enhanced`, `ARC4`, `AES128`, `AES256`. The CPS `Special`
  dropdown covers ARC4/AES128/AES256 collectively; the specific cipher is
  selected via `Encryption Key` index (col 23).
- **Tx Authority — digital (col 25)** — firmware menu enum: `Impolite`,
  `Polite to CC`, `Polite to All`, `Forbid`. CSV `No` / `Always` likely
  alias `Impolite` / one of the polite variants.
- **Tx Authority — analog (col 15)** — `Allow TX`, `Prohibit TX`,
  `Channel Free` are CPS-side labels; the on-radio menu uses `Wave` for
  the channel-free condition.
- **Work Mode (col 17)** — firmware shows `Simplex` and `Repeater` only.
  `Repeat` (no `-er`) is a CSV-side alias.
- **Power (col 5)** — radio also has explicit numeric labels (`0.5W`, `5W`)
  alongside the High/Medium/Low enum.
- **Encrypt key index (col 23)** — radio menu label is `Encrypt NO`.
- **PTT-ID / DTMF tone presets (col 71)** — firmware exposes `Tx1000`,
  `Tx1450`, `Tx1750`, `Tx2100` (Hz) and `TX-DSW` / `M-MONI` special
  codes; `KeyCall 1`..`KeyCall 6` are programmable per-key tone codes.
- **Sub-audio decoder modes (cols 12, 13, 14)** — firmware uses three
  matching labels: `C-CDC` (combined), `R-CDC` (Rx side), `T-CDC` (Tx
  side). Maps directly to channel `+0x24..+0x27` regions. The "sub-audio"
  match policy enum is `Off / 载波 (Wave/Carrier) / 亚音匹配
  (Sub-audio match) / 亚音不匹配 (Sub-audio not match)`.
- **Step (col 9) — display order vs stored byte:** the 0x297F enum stores
  `20K` at value `0x08` (out of sequence — 2.5/5/6.25/10/12.5/25/30/50
  fill `0x00..0x07`), but the **firmware menu** displays steps in
  numerical order: 2.5K, 5K, 6.25K, 10K, 12.5K, 20K, 25K, 30K, 50K. Reading
  back, `0x08` therefore renders as the 6th item even though it's the 9th
  byte value. The 1750 Hz repeater wakeup-tone option is *not* in this
  enum — it lives in the key-call function table (`Tx1750`).

## Adjacent menu items (not in CSV but useful for radio context)

These appear on the radio but are not part of the channel CSV. Kept here so
the CSV semantics make sense when reverse-engineering settings region.

- **Special-call commands**: `Stun`, `Kill`, `Radio Check`, `Radio WakeUp`,
  `WakeUp`, `Relay`, `Alarm`, `NOAA`.
- **GPS sub-menu** (channel cols 64-68 surface these): `Local GPS`,
  `Receive GPS`, `Outgoing` (timed-report), `Missed`, `Answered`,
  `1:1 / 1:2 / 1:3 / 1:4 / Off / Scan` (timing slots).
- **Channel display mode**: `Channel Mode` vs `Freq Mode`.

## Encoding-mode confidence notes

Things confirmed by **firmware string** evidence (high confidence):

- The radio internally distinguishes 5 encryption ciphers (Normal /
  Enhanced / ARC4 / AES128 / AES256) — the CPS Special dropdown alone
  is insufficient to pick the cipher; the `Encryption Key` index
  (col 23) selects within `0x5018+` and the cipher is determined by
  slot range (0..15 = AES256, 16..31 = AES128, 32..47 = ARC4 — see
  `settings.md` AES/ARC4 section).
- Step value `0x08` = 20 kHz is real — confirmed by both the
  on-radio menu listing 20K and the doc table at `0x297F`.
- `Forbid` is a real Tx-Authority and Step option, not a CSV-only
  alias.

Things still **unverified** (need a CPS round-trip diff):

- Exact CSV-string mapping for the digital-Tx-Authority enum:
  does CSV `No` mean firmware `Impolite`? Does CSV `Always` mean
  `Polite to All`?
- Whether the `Special` Encryption-Type CSV value supports
  ARC4/AES128/AES256 individually or whether the radio infers
  cipher purely from the slot index.

## Creating CPS-compatible CSVs programmatically

The CPS is strict about format — here is a minimal Python template that
produces an importable channel CSV. The generated file replaces all
existing channels on import (it is not additive).

### Enum value reference

Every column that takes a fixed set of values. CSV strings are shown
first; the firmware-internal byte value is in parentheses where
documented. See `channels.md` and `settings.md` for the wire-format
encoding details.

#### Col 0 — No.

`VFO-A`, `VFO-B`, `1`..`3000`. VFOs must be the first two data rows.

#### Col 1 — Channel Type

| CSV value | Description |
|-----------|-------------|
| `Digital CH` | DMR channel |
| `Analog CH` | FM/analog channel |

#### Col 5 — Tx Power

| CSV value | Firmware byte | Notes |
|-----------|--------------|-------|
| `High` | `0x08` / `0x00` | Default |
| `Medium` | `0x04` / `0x00` | |
| `Low` | `0x00` / `0x00` | |
| (Extra Low) | `0x04` / `0x08` | 0.5 W; not in CSV dropdown, set via radio menu |

Power is encoded across two bits: `+0x21` bits 3:2 and `+0x29` bit 3.
Firmware labels: `Low` / `Middle` / `High` / `Extra low`.

#### Col 6 — TOT (Time-Out Timer)

| CSV value | Stored byte | Seconds |
|-----------|-------------|---------|
| `OFF` | `0x00` | disabled |
| `180S` | `0x0C` | 180 s |
| `60S` | `0x04` | 60 s |
| `75S` | `0x05` | 75 s |
| `90S` | `0x06` | 90 s |
| `120S` | `0x08` | 120 s |

Units are 15 s. Any multiple of 15 up to at least 120 s works.
Format: `NNNS` where NNN is seconds.

#### Col 8 — VOX Level

`1`..`9`. Only meaningful when col 7 (VOX) is `Yes`.

#### Col 9 — Scan Add/Step

Channel mode (col 1 must be `Analog CH` for scan toggle):

| CSV value | Description |
|-----------|-------------|
| `Yes` | Channel included in scan |
| `No` | Channel excluded from scan |

VFO mode (cols 0-1 are `VFO-A`/`VFO-B` — step value only):

| CSV value | Stored byte | Frequency step |
|-----------|-------------|----------------|
| `2.5K` | `0x00` | 2.5 kHz |
| `5K` | `0x01` | 5 kHz |
| `6.25K` | `0x02` | 6.25 kHz |
| `10K` | `0x03` | 10 kHz |
| `12.5K` | `0x04` | 12.5 kHz |
| `20K` | `0x08` | 20 kHz (out of sequence) |
| `25K` | `0x05` | 25 kHz |
| `30K` | `0x06` | 30 kHz |
| `50K` | `0x07` | 50 kHz |
| `Forbid` | — | Disables frequency step |

Firmware menu displays steps in numerical order; 20 K is stored at
byte value `0x08` (out of sequence).

#### Col 10 — Channel Work Alone

| CSV value | Description |
|-----------|-------------|
| `No` | Default |
| `Yes` | Channel works independently |

#### Col 11 — Default to Talkaround

| CSV value | Description |
|-----------|-------------|
| `No` | Default |
| `Yes` | Talkaround on by default |

#### Col 12 — Band Width

| CSV value | Stored bit | Description |
|-----------|-----------|-------------|
| `12.5K` | `0x00` | Narrow (default) |
| `25K` | `0x40` | Wide |

#### Col 13 / 14 — Dec QT/DQT / Enc QT/DQT

CTCSS tones (31 values, firmware-confirmed):

`62.5`, `67.0`, `69.3`, `71.9`, `74.4`, `77.0`, `79.7`, `82.5`,
`85.4`, `88.5`, `91.5`, `94.8`, `103.3`, `117.5`, `127.5`,
`137.2`, `145.6`, `152.2`, `161.4`, `166.6`, `173.8`, `177.3`,
`199.5`, `203.5`, `206.5`, `210.7`, `218.1`, `225.7`, `229.1`,
`233.6`, `236.5`

DCS codes (103 values): `D023`, `D025`, `D026`, `D031`, `D032`,
`D036`, `D043`, `D047`, `D051`, `D053`, `D054`, `D065`, `D071`,
`D072`, `D073`, `D074`, `D114`, `D115`, `D116`, `D122`, `D125`,
`D131`, `D132`, `D134`, `D152`, `D155`, `D156`, `D162`, `D165`,
`D172`, `D174`, `D205`, `D212`, `D223`, `D225`, `D226`, `D243`,
`D244`, `D245`, `D246`, `D251`, `D252`, `D255`, `D261`, `D263`,
`D265`, `D266`, `D271`, `D274`, `D306`, `D311`, `D315`, `D325`,
`D331`, `D332`, `D343`, `D346`, `D351`, `D356`, `D364`, `D365`,
`D371`, `D411`, `D412`, `D413`, `D423`, `D431`, `D432`, `D445`,
`D446`, `D452`, `D454`, `D455`, `D462`, `D464`, `D465`, `D466`,
`D503`, `D506`, `D516`, `D523`, `D526`, `D532`, `D546`, `D565`,
`D606`, `D612`, `D624`, `D627`, `D631`, `D632`, `D645`, `D654`,
`D662`, `D664`, `D703`, `D712`, `D723`, `D731`, `D732`, `D734`,
`D743`

DCS variants: `D023N` (normal), `D023I` (inverted). The `N`/`I`
suffix selects normal vs inverted decode.

Use `None` for no tone.

#### Col 15 — Tx Authority (analog)

| CSV value | Description |
|-----------|-------------|
| `Allow TX` | Always transmit |
| `Prohibit TX` | Never transmit |
| `Channel Free` | Transmit only when channel is clear |

#### Col 16 — Relay

| CSV value | Description |
|-----------|-------------|
| `No` | Default |
| `Yes` | Talkaround/relay enabled |

#### Col 17 — Work Mode (DMR only)

| CSV value | Firmware label | DMR mode bits |
|-----------|---------------|---------------|
| `Simplex` | `Simplex` | `0x00` |
| `Repeat` | `Repeater` | `0x02` |
| (—) | `Double Slot` | `0x08` (not in CSV; radio-menu only) |

**Use `Repeat`, not `Repeater`.** The firmware displays `Repeater` but
the CPS CSV uses `Repeat` (no `-er`).

#### Col 18 — Slot (DMR only)

| CSV value | Firmware label |
|-----------|---------------|
| `Slot1` | `Slot 1` |
| `Slot2` | `Slot 2` |

Note: CSV has no space; firmware display has a space.

#### Col 20 — Color Code (DMR only)

`0`..`15`.

#### Col 21 — Encryption

| CSV value | Description |
|-----------|-------------|
| `No` | Encryption off |
| `Yes` | Encryption on |

#### Col 22 — Encryption Type

| CSV value | Cipher(s) covered | Key table location |
|-----------|-------------------|-------------------|
| `Normal Mode` | Normal (2-byte BE BCD) | `settings` `0x3D00` |
| `Enhanced` | Enhanced (16-byte) | `settings` `0x3E00` |
| `Special` | ARC4 / AES128 / AES256 (49-byte) | `settings` `0x5018+` |

When `Special` is selected, the specific cipher is determined by the
key index (col 23):

| Key index (col 23) | Cipher |
|---------------------|--------|
| 1–16 | AES256 |
| 17–32 | AES128 |
| 33–48 | ARC4 |

Firmware menu labels (6 total): `Off`, `Normal`, `Enhanced`, `ARC4`,
`AES128`, `AES256`. The CPS maps the last three into `Special` +
key index.

#### Col 23 — Encryption Key

`1`..`16`. Meaning depends on Encryption Type (col 22) — see above.

#### Col 24 — Promiscuous

| CSV value | Description |
|-----------|-------------|
| `No` | Default; only receive matching color code |
| `Yes` | Receive all calls regardless of color code |

Same feature as firmware "RxAll CC".

#### Col 25 — Tx Authority (digital)

| CSV value | Firmware label | Description |
|-----------|---------------|-------------|
| `No` | `Impolite` (?) | Transmit without waiting |
| `Always` | `Polite to All` (?) | Wait for channel + all color codes |
| `Forbid` | `Forbid` | Never transmit digitally |

The exact CSV-to-firmware mapping is unverified. The firmware enum is:
`Forbid` / `Impolite` / `Polite to CC` / `Polite to All`.

#### Col 26 — Kill Code

| CSV value | Description |
|-----------|-------------|
| `Always` | Always respond to kill commands (default) |
| `Forbid` | Ignore kill commands |
| *contact name* | Respond only to the named priority contact |

#### Col 27 — WakeUp Code

| CSV value | Description |
|-----------|-------------|
| `None` | Ignore wake-up commands (default) |
| *contact name* | Respond to the named priority contact |

#### Col 28 — Contacts

| Format | Description |
|--------|-------------|
| `None` | No contact assigned |
| `Priority Contacts: NAME` | Reference a priority contact by name |
| `Address Book Contacts: NUMBER` | Reference an address book contact by DMR ID |

#### Col 29 — Rx Group Lists

| CSV value | Description |
|-----------|-------------|
| `None` | No group list |
| `&H00000000` | No group list (alternative) |
| *list name* | Named group list |
| `Custom` | Custom group list (used with cols 30-33) |

#### Cols 30-33 — Group list refs (with col 29 = `Custom`)

Four columns that form part of the Rx Group Lists selection when col
29 is `Custom`. Values are contact references.

#### Cols 34-63 — Group Lists 1-30

Contact references for the selected group list. One contact per column.

#### Col 67 — GPS Timing Report

`OFF` or `30`..`1000` (seconds, in steps of 10).

#### Col 69 — PTT ID (analog only)

| CSV value | Description |
|-----------|-------------|
| *(empty)* | No PTT ID |
| `BOT` | Beginning of transmission |
| `EOT` | End of transmission |
| `Both` | BOT + EOT |

CPS-only labels — the firmware does not use these strings; it maps
PTT-ID through the DTMF Encode Table at `0x4471` instead.

#### Col 70 — Opt.Signal (analog only)

| CSV value | Description |
|-----------|-------------|
| *(empty)* | No optional signaling |
| `DTMF` | DTMF signaling enabled |

#### Col 71 — DTMF Code Group

`1`..`128` (1-based index into DTMF Encode Table at settings `0x4471`).
Empty = no DTMF code.

### Python template

```python
#!/usr/bin/env python3
"""Generate a CPS-importable channel CSV from a list of dicts."""

import csv
import io
import sys

HEADER = [
    "No.", "Channel Type", "Channel Alias",
    "Rx Frequency", "Tx Frequency", "Tx Power", "TOT",
    "VOX", "VOX Level", "Scan Add/Step", "Channel Work Alone",
    "Default to Talkaround", "Band Width", "Dec QT/DQT", "Enc QT/DQT",
    "Tx Authority", "Relay", "Work Mode", "Slot", "ID Setting",
    "Color Code", "Encryption", "Encryption Type", "Encryption Key",
    "Promiscuous", "Tx Authority",
    "Kill Code", "WakeUp Code", "Contacts", "Rx Group Lists",
    "Group List 1", "Group List 2", "Group List 3", "Group List 4",
    "Group List 5", "Group List 6", "Group List 7", "Group List 8",
    "Group List 9", "Group List 10", "Group List 11", "Group List 12",
    "Group List 13", "Group List 14", "Group List 15", "Group List 16",
    "Group List 17", "Group List 18", "Group List 19", "Group List 20",
    "Group List 21", "Group List 22", "Group List 23", "Group List 24",
    "Group List 25", "Group List 26", "Group List 27", "Group List 28",
    "Group List 29", "Group List 30",
    "GPS", "Send GPS Info", "Receive GPS Info",
    "GPS Timing Report", "GPS Timing Report TX Contacts",
    "PTT ID", "Opt.Signal", "DTMF Code Group",
    "Fixed key decryption", "RX all private call",
    "",  # trailing comma column
]

EMPTY_ROW = [""] * len(HEADER)


def freq(f: float) -> str:
    """Format MHz frequency with 5 decimal places."""
    return f"{f:.5f}"


def row(ch: dict) -> list[str]:
    """Build a 75-element CSV row from a channel dict.

    Required keys: no, mode, rx, tx
    Sensible defaults for everything else.
    """
    mode_label = "Digital CH" if ch.get("mode") == "DMR" else "Analog CH"
    slot = ch.get("slot", "Slot1")
    enc = ch.get("encryption", "No")
    enc_type = ch.get("encryption_type", "")
    if enc == "Yes" and not enc_type:
        enc_type = "Normal Mode"
    if enc == "Yes" and ch.get("encryption_type") == "aes":
        enc_type = "Special"
    contact = ch.get("contact", "None")
    if contact and ch.get("contact_type") == "ab":
        contact = f"Address Book Contacts: {contact}"
    elif contact and ch.get("contact_type") == "pc":
        contact = f"Priority Contacts: {contact}"

    group_list = ch.get("rx_group", "None")
    kill = ch.get("kill_code", "Always")
    wakeup = ch.get("wakeup_code", "None")

    group_cols = []
    if group_list != "None":
        group_cols = [group_list] + [""] * 29
    else:
        group_cols = [""] * 30

    r = [
        str(ch["no"]),
        mode_label,
        ch.get("alias", ""),
        freq(ch["rx"]),
        freq(ch["tx"]),
        ch.get("power", "High"),
        ch.get("tot", "OFF"),
        "No",                          # VOX
        "",                            # VOX Level
        "Yes" if ch.get("scan") else "No",
        "No",                          # Channel Work Alone
        "No",                          # Default to Talkaround
        ch.get("bandwidth", "12.5K"),
        "None",                        # Dec QT/DQT
        "None",                        # Enc QT/DQT
        "Allow TX",                    # Tx Authority (analog)
        "No",                          # Relay
        ch.get("work_mode", "Simplex"),
        slot,
        ch.get("id_setting", ""),
        str(ch.get("color_code", 0)),
        enc,
        enc_type,
        str(ch.get("encryption_key", 1)),
        "No",                          # Promiscuous
        "No",                          # Tx Authority (digital)
        kill,
        wakeup,
        contact,
        group_list,
        *group_cols,
        "No",                          # GPS
        "No",                          # Send GPS Info
        "No",                          # Receive GPS Info
        "OFF",                         # GPS Timing Report
        "",                            # GPS Timing Report TX Contacts
        "",                            # PTT ID
        "",                            # Opt.Signal
        "",                            # DTMF Code Group
        "No",                          # Fixed key decryption
        "No",                          # RX all private call
        "",                            # trailing comma
    ]
    return r


def make_csv(channels: list[dict]) -> str:
    """Build a complete CPS-importable CSV string.

    channels: list of dicts with at least 'no', 'mode', 'rx', 'tx' keys.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADER)
    # VFO rows (must be first two data rows)
    w.writerow(row({"no": "VFO-A", "mode": "DMR", "rx": 438.72500,
                    "tx": 431.12500, "scan": True}))
    w.writerow(row({"no": "VFO-B", "mode": "DMR", "rx": 438.72500,
                    "tx": 431.12500, "scan": True}))
    for ch in channels:
        w.writerow(row(ch))
    # Trailing empty rows (CPS requires these)
    for _ in range(8):
        w.writerow(EMPTY_ROW)
    return buf.getvalue()


if __name__ == "__main__":
    channels = [
        {"no": 1, "mode": "DMR", "rx": 438.72500, "tx": 431.12500,
         "alias": "TG262", "color_code": 1, "contact": "1",
         "contact_type": "ab", "slot": "Slot2",
         "work_mode": "Repeater"},
        {"no": 2, "mode": "Analog", "rx": 145.50000, "tx": 145.50000,
         "alias": "Analog1", "bandwidth": "25K"},
    ]
    csv_data = make_csv(channels)
    out_path = sys.argv[1] if len(sys.argv) > 1 else "channels.csv"
    with open(out_path, "w", newline="") as f:
        f.write(csv_data)
    print(f"Wrote {out_path}")
```

### Key pitfalls when generating CSVs

1. **CRLF line endings** — the CPS rejects LF-only files. Use
   `newline=""` with `csv.writer` and set `lineterminator="\r\n"`, or
   write with explicit `\r\n`.

2. **75 columns exactly** — the header must have 75 comma-separated
   fields (the last one is an empty trailing field). Row data must
   match column count.

3. **VFO-A and VFO-B first** — the first two data rows must be the VFO
   entries. Omitting them or placing channels first causes import
   failure.

4. **Trailing empty rows** — at least several empty rows (75 commas
   each) must follow the last channel row.

5. **Frequencies: 5 decimal places** — `438.72500` not `438.725`.

6. **Column 19 "ID Setting"** — must reference an existing radio ID
   *name* (not a number). Empty value may cause import failure.
   Export from CPS first to get valid names.

7. **Column 17 "Work Mode"** — use `Repeat` (not `Repeater`) for
   repeater channels.

8. **Column 29 "Rx Group Lists"** — use `&H00000000` for no group
   list, with `Custom` in column 30. Empty value may cause import
   failure.

9. **Import is destructive** — importing a CSV replaces all existing
   channels. Back up your codeplug first.

10. **Contacts must exist** — channel rows that reference contacts
    (column 28) or group lists (columns 30-63) require those contacts
    and lists to already exist in the CPS. Import contacts first, then
    channels.

11. **Contact reference format** — column 28 uses the prefix
    `Priority Contacts: ` or `Address Book Contacts: ` followed by the
    contact's name (priority) or DMR ID number (address book).
