# HD2 Menu Tree (full reference)

Complete radio menu hierarchy, cross-referenced against:

- **Manual** (`Ailuncehd2_manual.md`) — official menu order and definitions
- **Firmware** (`v208.perword.v32.bin`) — verified label strings and enum values
- **Codeplug docs** (`settings.md`, `channels.md`, `records.md`) — storage layout
- **CPS format** (`cps-csv-format.md`) — CSV column mapping

Notation in cross-reference columns:
- `S:0xNNNN` — settings region address (`b1=0x0F` block)
- `Ch+0xNN` — channel slot byte offset
- `seg N+M` — firmware menu pointer table segment (see `settings.md`
  "Menu segment architecture")
- `CSV NN` — CPS CSV column index (0-based)

---

## Top-level menu

Pressing **MENU** from the standby screen enters the top menu. Per the
manual, the top is structured as:

```
Top
├─ Band A Set       (channel-screen settings for Band A)
├─ Band B Set       (channel-screen settings for Band B)
├─ Main Set         (32 radio-wide settings — all surfaced via segment 4 of the firmware menu table from index 23 onwards)
└─ Other Functions  (sub-menu — segment 7 of the firmware menu table)
```

### Other Functions (segment 7)

Segment 7 (`@0x06e17c`, 21 entries, handler `0x05670c82`) is the
navigation list under "Other Functions". Order is the literal pointer
order in flash; the radio may filter or rearrange at display time.

| # | Item                | Where to find                                                      |
|---|---------------------|--------------------------------------------------------------------|
| #  | Item            | Where to find / notes                                              |
|----|-----------------|--------------------------------------------------------------------|
|  1 | **Band A Set**  | sub-menu — see [Band A/B Set](#band-ab-set-channel-settings)       |
|  2 | **Band B Set**  | sub-menu — see [Band A/B Set](#band-ab-set-channel-settings)       |
|  3 | **Message**     | sub-menu — see [Message (SMS)](#message-sms)                       |
|  4 | **Call Log**    | sub-menu — see [Call Log](#call-log)                               |
|  5 | **Contacts**    | priority-contact list — see [Contacts](#contacts)                  |
|  6 | **Radio ID**    | radio ID table — see [Radio ID](#radio-id)                         |
|  7 | **FM radio**    | FM broadcast — see [FM Radio](#fm-radio)                           |
|  8 | **GPS**         | GPS sub-menu (master GPS / RxGPSInfo / TxGPSInfo)                  |
|  9 | **Encryption**  | sub-menu — see [Encryption](#encryption)                           |
| 10 | **Version**     | firmware build / serial number screen                              |
| 11 | **InBox**       | received SMS list (Message → Inbox shortcut)                       |
| 12 | **Write**       | new SMS editor (Message → Write shortcut)                          |
| 13 | **Sent Items**  | sent SMS list                                                      |
| 14 | **Quick Text**  | preset SMS templates                                               |
| 15 | **Local GPS**   | shows current GPS coordinates                                      |
| 16 | **Receive GPS** | shows last received GPS info from peer                             |
| 17 | **Missed**      | missed-call log                                                    |
| 18 | **Answered**    | answered-call log                                                  |
| 19 | **Outgoing**    | outgoing-call log                                                  |
| 20 | **Contacts** (dup) | secondary entry — references the same priority-contact list    |
| 21 | **Manual Dial** | DTMF / manual contact dialer                                       |

(Items 11–21 are also reachable via the higher-level Message and Call
Log entries — they appear here as direct shortcuts in the firmware
table. The duplicate Contacts pointer suggests the radio renders the
list contextually different in two places.)

---

## Main Set

Manual section "Radio Menu Setting — Main Set" (32 items). Stored
across the settings region `0x2970..0x29A0`. Many items live in packed
flag bytes — see `settings.md` for bit-level details.

| # | Item             | Values / sub-options              | Storage    | Firmware label    |
|---|------------------|-----------------------------------|------------|-------------------|
| 1 | Squelch          | 0..9                              | S:0x2970   | `Squelch`         |
| 2 | Save             | OFF / 1:1 / 1:2 / 1:3 / 1:4       | S:0x2973 b7:5 | `Save`         |
| 3 | A/B Time         | 1..10 sec                         | S:0x2974   | `A/B Time`        |
| 4 | Double PTT       | OFF / ON                          | S:0x2973 b3 | `Double PTT`     |
| 5 | Bluetooth        | OFF / ON                          | (unmapped) | `BlueTooth`       |
| 6 | BTRebind         | (action — pairing trigger)        | runtime    | `BTRebind`        |
| 7 | Voice            | OFF / ON                          | S:0x2971 b5 | `Voice`          |
| 8 | Zone Name        | OFF / ON                          | S:0x2975 b0 | `Zone Name`       |
| 9 | VOX Delay        | 0.5..5.0 s (×0.5 s steps)         | S:0x2976 b3:0 | `Vox Delay`    |
|10 | Mic Gain         | -10..+10 (signed)                 | S:0x299B   | `Mic Gain`        |
|11 | Hang Up          | 0=OFF, 1..10 sec                  | S:0x297A   | `Hang Up`         |
|12 | Tx Channel       | (busy channel transmit setting)   | (unmapped) | `Tx Channel`      |
|13 | Key Define       | sub-menu — see [Key Define](#key-define-key1key2-functions) | S:0x29A8..0x29AB | `Key Define` |
|14 | Backlight        | Cont / 1s..120s                   | S:0x2972   | `Backlight`       |
|15 | Brightness       | 1..10                             | S:0x299C   | `Brightness`      |
|16 | Key Beep         | OFF / ON                          | S:0x2977 b7 | `Key Beep`       |
|17 | Key Lock         | Manual / Auto                     | S:0x2971 b2 | `Key Lock`       |
|18 | Lock Mode        | Key / Key+CH / Key+CH+PTT         | S:0x299F b6:5 | `Lock Mode`    |
|19 | CH-Mode          | Frequency / Name / CH (Channel)   | S:0x2978 b5,0 | `CH-Mode`      |
|20 | S/D Mode         | Single / Dual band                | S:0x299D b2 | `S/D Mode`       |
|21 | Scan Mode        | TO (Time) / CO (Carrier) / SE (Search) | S:0x2973 b1:0 | `Scan Mode` |
|22 | Save CH          | (action — store current as CH)    | runtime    | `Save CH`         |
|23 | Delete CH        | (action — delete CH)              | runtime    | `Delete CH`       |
|24 | Roger            | OFF / ON                          | S:0x2971 b1 | `Roger beep`     |
|25 | Time             | (clock-set sub-screen)            | (RTC chip) | (no flat label)   |
|26 | Menu Exit        | OFF / 10..60 s                    | S:0x299E   | `MenuExitTime`    |
|27 | Miss Call Set    | OFF / ON                          | S:0x299D b0 | `MissCallMenu`   |
|28 | Rx Info Bright Set | OFF / ON                        | S:0x299F b7 | `CallInLight`    |
|29 | DMR TX Beep      | OFF / ON                          | S:0x2975 b4 | `DMRTxBeep`       |
|30 | FM TX Beep       | OFF / ON                          | S:0x2975 b5 | `FMTxBeep`        |
|31 | Night Mode       | OFF / ON                          | S:0x2978 b2 | `NightMode`       |
|32 | Noise Tail       | OFF / ON (+ mode bit)             | S:0x2977 b2,b0 | `Noise Tail`  |

### Key Define (Key1/Key2 functions)

Sub-menu of Main Set #13. Four bytes at `S:0x29A8..0x29AB` — Key1
Short, Key1 Long, Key2 Short, Key2 Long. Same enum used at Emergency
key `S:0x29AE/0x29AF`. Long-press-only values (`Stun`, `TX-DSW`,
`M-MONI`, `Tx1000-2100`) are valid only for Key1L/Key2L slots.

| Value | Function           | Long-press only? |
|-------|--------------------|------------------|
| 0x00  | OFF                |                  |
| 0x01  | Power              |                  |
| 0x02  | Scan               |                  |
| 0x03  | Radio (FM)         |                  |
| 0x04  | Wake Up            |                  |
| 0x05  | Relay (Talkaround) |                  |
| 0x06  | Key Call 1         |                  |
| 0x07  | Key Call 2         |                  |
| 0x08  | Key Call 3         |                  |
| 0x09  | Key Call 4         |                  |
| 0x0A  | Key Call 5         |                  |
| 0x0B  | Key Call 6         |                  |
| 0x0C  | VOX                |                  |
| 0x0D  | Stun               | ✓ |
| 0x0E  | Kill (Transceive Inhibit) |        |
| 0x0F  | TX-DSW             | ✓ |
| 0x10  | Analog Monitor / M-MONI | ✓ (M-MONI label only on long press) |
| 0x11  | 1000Hz / Tx1000    | ✓ (Tx1000 label only on long press) |
| 0x12  | 1450Hz / Tx1450    | ✓                |
| 0x13  | 1750Hz / Tx1750    | ✓                |
| 0x14  | 2100Hz / Tx2100    | ✓                |
| 0x15  | Zone Plus          |                  |
| 0x16  | Zone Minus         |                  |
| 0x17  | DMR Slot           |                  |
| 0x18  | Promiscuous        |                  |
| 0x19  | Manual Dial        |                  |
| 0x1A  | CH-Mode            |                  |
| 0x1B  | Reverse            |                  |
| 0x1C  | Bluetooth          |                  |
| 0x1D  | 0.5W Power         |                  |
| 0x1E  | FM Call            |                  |
| 0x1F  | Voltage            |                  |
| 0x20  | NOAA               |                  |
| 0x21  | Emergency / Alarm  |                  |
| 0x22  | Key Beep           |                  |
| 0x23  | Encryption         |                  |
| 0xFF  | OFF (factory default) |               |

---

## Band A/B Set (Channel settings)

Manual section "Channel settings (Band A Set and Band B Set)" (29
items). Most settings are **per-channel** (stored in the channel slot);
a handful are **global** (settings region) with per-channel
selection of an index. Channel slot layout: `channels.md`.

Firmware menu surfaces these across two segments:
- **Segment 5** (`@0x06e0cc`, 15 items): Power, Vox, Vox Level, W/N, TOT, DTMF Signal, C-CDC, R-CDC, T-CDC, Ch.Name, Busy Lock, Shift Up, Shift Freq, Color Code, Encrypt Type
- **Segment 6** (`@0x06e10c`, 9 items): DMR Mode, DMR Slot, Promiscuous, RxAllPC, RxAllCC, GPS Contacts, Radio ID, Contacts, Rx List

| # | Item       | Values / sub-options              | Storage     | CSV col |
|---|------------|-----------------------------------|-------------|--------|
| 1 | Zone       | (zone selector — see Records)     | runtime     | —      |
| 2 | GPS        | OFF / ON                          | Ch+0x20 b7  | 64     |
| 3 | RxGPSInfo  | OFF / ON                          | Ch+0x2B b5  | 66     |
| 4 | TxGPSInfo  | OFF / ON                          | Ch+0x20 b4  | 65     |
| 5 | Step       | 2.5K / 5K / 6.25K / 10K / 12.5K / 20K / 25K / 30K / 50K / Forbid | S:0x297F (global) | 9 |
| 6 | Power      | Low / Middle / High / Extra low   | Ch+0x21 b3:2 + Ch+0x29 b3 | 5 |
| 7 | VOX        | OFF / ON                          | Ch+0x20 b5  | 7      |
| 8 | Vox Level  | 1..9                              | Ch+0x20 b3:0 | 8     |
| 9 | W/N        | Narrow / Wide                     | Ch+0x29 b6  | 12     |
|10 | TOT        | OFF / 15s / 30s / 45s / 60s / 75s / 90s / 120s | Ch+0x23 | 6 |
|11 | DTMF Signal | 1..128 (index into DTMF Encode Table) + enable bit | Ch+0x10 b6:0, Ch+0x11 b2 | 71 |
|12 | C-CDC      | sub-menu — see [CTCSS / DCS](#ctcss--dcs-tone-tables) | Ch+0x24..+0x27 | 13,14 |
|13 | R-CDC      | (Rx side of C-CDC; same options)  | Ch+0x24..+0x25 | 13   |
|14 | T-CDC      | (Tx side of C-CDC; same options)  | Ch+0x26..+0x27 | 14   |
|15 | Ch.Name    | text editor (10 chars; abc/ABC/123) | Ch+0x04 (10 B) | 2 |
|16 | Busy Lock  | sub-menu — see [Busy Lock / Tx Authority](#busy-lock--tx-authority) | Ch+0x29 b5:4 (analog), Ch+0x2B b7:6 (digital) | 15, 25 |
|17 | Shift Up   | Plus / Minus (offset direction)   | (unmapped)  | —      |
|18 | Shift Freq | 0.0..99.0 MHz                     | S:0x2985 (3 B BCD, global) | — |
|19 | Color Code | 0..15                             | Ch+0x2A high nibble | 20 |
|20 | Encrypt Type | OFF / Normal / Enhanced / ARC4 / AES128 / AES256 | Ch+0x28 b6:5 + Ch+0x11 b4:3 | 22 |
|21 | Encrypt NO | 1..16 (key index within type)     | Ch+0x28 low nibble | 23 |
|22 | DMR Mode   | Simplex / Repeater / Double Slot  | Ch+0x2A low nibble b3,b1 | — |
|23 | DMR Slot   | Slot 1 / Slot 2                   | Ch+0x2A low nibble b0 | 18 |
|24 | Promiscuous | OFF / ON (same bit as RxAll CC)  | Ch+0x29 b0  | 24     |
|25 | RxAll CC   | OFF / ON (same bit as Promiscuous) | Ch+0x29 b0 | —      |
|26 | Radio ID   | (selects from Radio ID table 0..31) | S:0x29A3 (global active idx) | 19 |
|27 | Contacts   | (DMR ID — references contact)     | Ch+0x1C (4 B LE) | 28 |
|28 | GPS contacts | (1-based index into Priority Contacts) | Ch+0x12 | 68 |
|29 | Rx List    | inline contact list               | Ch+0x30..0xAF (~32 entries) | 29 |

### Busy Lock / Tx Authority

Same byte position (`Ch+0x2B b7:6`); CPS labels differ by channel mode.

**Analog** (Ch+0x29 b5:4):

| Value | Firmware label | Manual / CSV equivalent          |
|-------|----------------|----------------------------------|
| 00    | `Forbid`       | Forbid (transmit blocked)        |
| 01    | `=Code`        | Prohibit when freq+sub-audio match |
| 10    | `Wave`         | Prohibit when channel busy       |
| 11    | (unused)       |                                  |

**Digital** (Ch+0x2B b7:6):

| Value | Firmware label   | Manual                         |
|-------|------------------|--------------------------------|
| 00    | `Forbid`         | Prohibit TX (blocked)          |
| 01    | `Impolite`       | Possible to transmit any time  |
| 10    | `Polite to CC`   | TX only if freq+CC match       |
| 11    | `Polite to All`  | TX only if freq+CC+contact match |

### CTCSS / DCS tone tables

The C-CDC / R-CDC / T-CDC editor cycles through three modes (short
press [*scan]):

- **CTCSS** — 31 frequencies (62.5..236.5 Hz; see firmware tone table at v208 rodata `0x06da3c`; full list in `channels.md`)
- **DCS Normal** — 103 codes D023..D754 (table at v208 `0x06daa8`)
- **DCS Inverted** — same 103 codes; channel byte flag 0xC0 vs 0x80 distinguishes

Each tone is encoded as 2-byte BCD-LE; see `channels.md` "Tone field
encoding" for the channel-byte format.

---

## Message (SMS)

Manual "Other Functions → Message". Each item is a sub-screen.

| # | Item        | Storage                                |
|---|-------------|----------------------------------------|
| 1 | Inbox       | runtime / DMR data layer (not codeplug) |
| 2 | Write       | (editor; max ~199 chars)               |
| 3 | Sent Items  | runtime                                |
| 4 | Quick Text  | `table_1dfx` block 0x1DF8+0xDC, 200 B × 16 slots |

Editor input modes (long-press [*scan] cycles):
- `Edit(abc)` — lowercase letters
- `Edit(ABC)` — uppercase letters
- `Edit(123)` — numbers / symbols

---

## Call Log

| Item     | Source                  |
|----------|-------------------------|
| Missed   | runtime DMR call history |
| Answered | runtime                 |
| Outgoing | runtime                 |

Each entry shows DMR ID, contact name, and timestamp.

Per-entry actions (firmware segments 4 + 5 of menu pointer table):
`Detail` / `Call Alert` / `WakeUp Radio` / `Radio Check` / `View GPS` /
`Kill Radio` / `Target Radio` / `Delete` / `Delete All` / `View Later`.

---

## Contacts

Manual "Contact: priority contact" — up to 5000 priority contacts.
Stored at radio block `0x1B84` onwards (`b1=0x31` region; see
`records.md`).

Sub-menu (firmware segment-7 entries surfaced from the contact-detail
screen):

| Item            | Action                                  |
|-----------------|-----------------------------------------|
| Edit ID         | enter DMR ID (max 16777215 = 0xFFFFFF)  |
| Contact Type    | Group / Private / All                    |
| ID Name         | text editor (16 chars; abc/ABC/123)      |
| Add Contacts    | new entry                                |
| Del Contacts    | remove entry                             |

Entry format (72 bytes per record, see `records.md`):
- DMR ID (4 B LE)
- Type byte: `0x04`=Group, `0x05`=Private, `0x06`=All
- Name (16 B), City (16 B), Province (16 B), Country (16 B)

---

## Radio ID

Up to 32 radio IDs at `S:0x4000+` (20-byte stride: 4 B DMR ID LE + 16 B
name). Per-channel ID selection is the global active index byte at
`S:0x29A3`.

| Action     | Description                              |
|------------|------------------------------------------|
| Edit ID    | enter own DMR ID (max 16777215)          |
| ID Name    | name this ID (16 chars; abc/ABC/123)     |

---

## FM Radio

Manual "FM radio" — 32 broadcast presets at `S:0x3000` (136 B: 4-byte
slot bitmap + 32 × 4-byte BCD-LE × 10 Hz frequency + VFO).

| Mode       | Action                                                  |
|------------|---------------------------------------------------------|
| FM VFO     | direct frequency entry                                  |
| FM CH      | preset 1..32 (long-press EXIT to switch VFO ⇄ CH mode) |
| Save preset| long-press [*scan] from VFO mode                        |
| Dual Watch | short-press [#] toggles intercom-priority dual-watch    |

Storage details: `settings.md` "FM Radio" section.

---

## Encryption

Top-level item #11. Sub-menu indices map to channel `Encrypt Type`:

| Sub-item   | Channel byte combo (Ch+0x28 b6:5 + Ch+0x11 b4:3) | Key region |
|------------|--------------------------------------------------|------------|
| Off        | 00 / xx                                           | (none) |
| Normal     | 01 / xx                                           | S:0x3D00 (16 × 2 B BCD) |
| Enhanced   | 10 / xx                                           | S:0x3E00 (16 × 16 B) |
| ARC4       | 11 / 00                                           | S:0x5018 slots 32..47 (49 B × 16) |
| AES128     | 11 / 01                                           | S:0x5018 slots 16..31 |
| AES256     | 11 / 10                                           | S:0x5018 slots 0..15 |

Key index (1..16) within the active type comes from channel `Ch+0x28`
low nibble (radio menu label `Encrypt NO` / 加密组别).

---

## GPS sub-menus

GPS works on DMR channels only.

| Sub-item            | Where set                                              |
|---------------------|--------------------------------------------------------|
| GPS (master enable) | Ch+0x20 b7 (per channel)                               |
| RxGPSInfo           | Ch+0x2B b5                                             |
| TxGPSInfo           | Ch+0x20 b4                                             |
| GPS Contacts        | Ch+0x12 (1-based index into priority contacts)         |
| GPS Timing Report   | Ch+0x22 (encoding: `(seconds-20)/10`; OFF / 30..1000s) |
| Local GPS (display) | top-menu item 9 — shows current coordinates            |
| Receive GPS (display) | top-menu item 10 — shows last received GPS          |
| GPS Timing Report TX Contacts | CSV col 68 (uses Ch+0x12)                    |

A separate timing-ratio sub-list `1:1 / 1:2 / 1:3 / 1:4 / Off / Scan`
appears in firmware near the GPS area (`0x06ead4`) — likely the
"Outgoing transmissions per GPS report" ratio (1 GPS in N TX, or
similar). Storage location not yet pinned.

---

## NOAA Weather (US only)

Top-level Key Define value 0x20 = NOAA. 11 hard-coded preset
frequencies in firmware ROM (not in codeplug):

| # | Freq (MHz) |
|---|------------|
| NOAA-1  | 162.550 |
| NOAA-2  | 162.400 |
| NOAA-3  | 162.475 |
| NOAA-4  | 162.425 |
| NOAA-5  | 162.450 |
| NOAA-6  | 162.500 |
| NOAA-7  | 162.525 |
| NOAA-8  | 161.650 |
| NOAA-9  | 161.750 |
| NOAA-10 | 161.775 |
| NOAA-11 | 162.000 |

Set a side key short or long press to NOAA function (Key Define value
`0x20`); the HD2 displays the NOAA channel on the sub-band.

---

## Number-key shortcuts (MENU + N)

From the standby screen:

| Combo    | Action     | Same as Main Set # |
|----------|------------|--------------------|
| MENU + 1 | Backlight  | 14                 |
| MENU + 2 | Save       | 2                  |
| MENU + 3 | Step       | (Band A/B Set #5)  |
| MENU + 4 | W/N        | (Band A/B Set #9)  |
| MENU + 5 | Power      | (Band A/B Set #6)  |
| MENU + 6 | Shift Up   | (Band A/B Set #17) |
| MENU + 7 | VOX        | (Band A/B Set #7)  |
| MENU + 8 | Squelch    | 1                  |
| MENU + 9 | Roger beep | 24                 |
| MENU + 0 | Key Beep   | 16                 |

Plus (special): `MENU + 6` while powering on enters the IARU region
selector (password `654321`).

---

## DTMF in-call key map

While transmitting (PTT held), each key sends one DTMF digit:

| Key       | DTMF |
|-----------|------|
| 0–9       | 0–9  |
| MENU      | A    |
| Up arrow  | B    |
| Down arrow | C   |
| EXIT      | D    |
| `*SCAN`   | E    |
| `#LOCK`   | F    |

Per-channel DTMF settings (Ch+0x10..0x11):
- DTMF index — selects one of 128 entries in DTMF Encode Table at S:0x4471
- Enable bit (Ch+0x11 b2)
- PTT-ID mode (Ch+0x11 b1:0): None / BOT / EOT / Both — CPS-only
  labels; uses BOT/EOT codes from S:0x4440/S:0x4450

---

## Top-mounted **alarm** key

Default = Emergency (Key Define `0x21`). Configurable via CPS Emergency
Alarm settings:

- `S:0x29AE` Emergency short press function (uses Key Define enum)
- `S:0x29AF` Emergency long press function
- `S:0x2990` Alarm TX Time (`value/2` seconds; e.g. `0x05`=10s, `0x0F`=30s)
- `S:0x2991` Alarm Idle Time (`value-5` seconds; e.g. `0x00`=5s, `0x0F`=20s)

Local vs Remote alarm mode at `S:0x299D b1`:
`set`=Local, `clear`=Remote.

---

## CH-Mode display (per Main #19)

Three display modes for the standby screen, encoded as a 2-bit enum at
`S:0x2978 {bit5, bit0}`:

| Encoding (b5,b0) | Display mode | Manual term         |
|------------------|--------------|---------------------|
| 00               | Frequency    | Frequency + CH#     |
| 01               | Channel      | CH (Channel mode)   |
| 10               | Name         | Channel name        |

The firmware uses `Channel Mode` and `Freq Mode` labels in the
sub-menu (`@0x06fe14`); the third "Name" mode is implicit (no separate
labelled item visible in segment 5).

---

## Cross-reference summary

The firmware menu pointer table assigns one **handler function** per
sub-menu (handler addresses in SRAM `0x055xxxxx..0x056xxxxx`). Mapping
of menu group → handler:

| Menu group                        | Firmware segment | Handler        |
|-----------------------------------|------------------|----------------|
| Encryption Type list              | 0                | `0x0561daee`   |
| Tx Authority + Step (1)           | 1                | `0x0561da2a`   |
| Step continuation (50K, Forbid)   | 2                | `0x0561df7e`   |
| Key Define values 0x02..0x0B      | 3                | `0x0561df46`   |
| Key Define values 0x0D..0x48 + Main Set | 4          | `0x0561df76`   |
| Channel A/B Set screen            | 5                | `0x0561dfc2`   |
| DMR sub-screen                    | 6                | `0x0561d3a2`   |
| Top main menu                     | 7                | `0x05670c82`   |

The handlers themselves live in SRAM (populated at boot via
flash→SRAM copy) — see `settings.md` "Menu segment architecture" for
why they aren't directly disassemblable from flash rodata alone.
