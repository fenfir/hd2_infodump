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
- **Encryption-group debug printf** (firmware-internal, useful for
  understanding key-table layout): `加密组别 NN: 算法：%x` — i.e.
  "Encryption group NN: algorithm: %x". Confirms that AES/ARC4 keys at
  `0x5018` are indexed by a (group, slot) tuple where the group comes
  from the channel's `Encryption Key` byte. Observed group values in
  firmware printf list: 21, 22, 50.

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
