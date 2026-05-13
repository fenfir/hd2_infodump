# Radio settings

Radio-wide settings. Lives in the `settings` region (radio addr range
`0x2900..0x5F00`, b1=0x0F 128-byte reads). Bytes were isolated by
toggling one CPS setting at a time and diffing successive dumps.

Names match the HD2 User's Manual menu items; manual menu numbers are
shown in parentheses where helpful.

## Settings byte table (`0x2900+`)

| Radio addr | Bytes | Meaning |
|------------|-------|---------|
| `0x2970`   | 1     | Squelch (Main #1). Direct value 0..9. |
| `0x2971`   | 1     | Packed flags: bit 5 (`0x20`) = Voice (Main #7, voice announcements, set=on); bit 2 (`0x04`) = Auto key lock after 15 s (Main #17 "Key Lock", set=on) ✓; bit 1 (`0x02`) = Roger (Main #24, transmit end tone, set=on); bit 0 (`0x01`) = Keylock at power on (set=on) ✓ Session A. |
| `0x2972`   | 1     | Backlight (Main #14). Seconds; `0x00`=continuous, `0x01`=1 s … `0x78`=120 s. |
| `0x2973`   | 1     | Packed flags: bits 7:5 = Save (Main #2, power saving ratio; OFF=`000`, 1:1=`001`, 1:2=`010`, 1:3=`011`, 1:4=`100`); bit 3 (`0x08`) = Double PTT (Main #4, set=on) ✓; bits 1:0 = Scan Mode (Main #21; `00`=TO, `01`=CO, `10`=SE) ✓. Bit 4 (`0x10`) = Radio DW (FM broadcast dual watch, set=on) ✓; bit 2 (`0x04`) = FM Radio Work Mode (set=VFO, clear=CH) ✓. |
| `0x2974`   | 1     | A/B Time (Main #3). Direct value 1..10 seconds. |
| `0x2975`   | 1     | Packed flags: bit 7 (`0x80`) = Accept Radio Wake Up Command (CPS, set=on) ✓; bit 6 (`0x40`) = Accept Radio Kill Command (CPS, set=on) ✓; bit 5 (`0x20`) = FM TX Beep (Main #30, set=on); bit 4 (`0x10`) = DMR TX Beep (Main #29, set=on); bit 1 (`0x02`) = No TX Info When Operating Menu (CPS, set=on) ✓; bit 0 (`0x01`) = Zone Name (Main #8, set=on). |
| `0x2976`   | 1     | Packed: bits 5:4 = Wakeup Speed (power save wake speed; `10`=slow, `00`=fast, `01`=medium) ✓; bits 3:0 = VOX Delay (Main #9), value × 0.5 s; `0x01`=0.5 s, `0x0A`=5.0 s. |
| `0x2977`   | 1     | Packed flags: bit 7 (`0x80`) = Key Beep (Main #16, set=on); bit 5 (`0x20`) = Press PTT Cancel VOX (CPS, set=on) ✓; bit 4 (`0x10`) = Insert Headset Activates VOX (CPS, set=on) ✓; bit 3 (`0x08`) = Power On Password enable (CPS, set=enabled, clear=disabled) ✓; bit 2 (`0x04`) = Noise Tail (Main #32, repeater tail elimination, set=on); bit 1 (`0x02`) = Dual Watch BDR (CPS, **inverted**: set=off) ✓; bit 0 (`0x01`) = Noise Tail Elimination Mode (set=Reverse Code, clear=other) ✓. |
| `0x2978`   | 1     | Packed flags: bit 5 (`0x20`) = CH-Mode Name flag; bit 3 (`0x08`) = *unknown* (0 in all samples; previously thought to be Night Mode — incorrect); bit 2 (`0x04`) = Night Mode (Main #31, **set**=on, clear=off) ✓; bit 0 (`0x01`) = CH-Mode CH flag. CH-Mode (Main #19) is encoded as the 2-bit enum `{bit5, bit0}`: `00`=Freq, `01`=CH, `10`=Name. Note: Bluetooth (Main #5) address not yet confirmed. |
| `0x2979`   | 1     | Packed flags: bit 3 (`0x08`) = Time Format (set=24h, clear=12h) ✓; bit 2 (`0x04`) = Voice Language (set=English, clear=Chinese) ✓; bit 0 (`0x01`) = Radio Functions enable (set=on, clear=off) ✓. |
| `0x297A`   | 1     | Priv Group Call Response (CPS name; cf. Hang Up Main #11 — identical range). Range 0..10; `0x00`=OFF, `0x01`=1 … `0x0A`=10. ✓ Session A |
| `0x297D`   | 1     | FM Radio Work CH. 0-based channel index; `0x00`=CH1, `0x01`=CH2, etc. ✓ |
| `0x297F`   | 1     | Step (Ch #5). VFO frequency step enum (see below). |
| `0x2985`   | 3     | Shift Freq (Ch #18). BCD LE, kHz; e.g. `00 06 00` = 600 kHz, `50 05 00` = 550 kHz. Global. UI range 0.00..99.00 MHz. |
| `0x2988`   | 1     | Repeater Connect (CPS). Direct value 1..10. ✓ |
| `0x2989`   | 6     | Power On Password value. 6 ASCII digit bytes (`0x30`..`0x39`). E.g. `303030303030` = "000000". ✓ |
| `0x2990`   | 1     | Alarm TX Time (CPS Emergency). Encoding: value ÷ 2; `0x05`=10 s, `0x0F`=30 s. ✓ |
| `0x2991`   | 1     | Alarm Idle Time (CPS Emergency). Encoding: value − 5; `0x00`=5 s, `0x0F`=20 s. ✓ |
| `0x2998`   | 1     | Lone Worker Response Time (CPS). Encoding: value − 1; `0x04`=5, `0x09`=10. ✓ |
| `0x2999`   | 1     | Lone Worker Pre-Alarms (CPS). Encoding: value − 1; `0x04`=5, `0x09`=10. ✓ |
| `0x299A`   | 1     | Rx Info Display Time (CPS). Encoding: value − 1; `0x04`=5 s, `0x09`=10 s. ✓ |
| `0x299B`   | 1     | Mic Gain (Main #10). Signed int8; `0x00`=+0, `0xF6`=−10, `0x0A`=+10. |
| `0x299C`   | 1     | Brightness (Main #15). 0-indexed; `0x00`=level 1, `0x09`=level 10. |
| `0x299D`   | 1     | Packed flags: bit 3 (`0x08`) = unknown (set in all samples); bit 2 (`0x04`) = S/D Mode (Main #20, single/dual band standby, set=on); bit 1 (`0x02`) = Emergency Alarm type (clear=Remote, set=Local) ✓; bit 0 (`0x01`) = Miss Call Set (Main #27, set=on) ✓. |
| `0x299E`   | 1     | Menu Exit (Main #26). Seconds; `0x00`=OFF, `0x0A`=10 s, `0x3C`=60 s. |
| `0x299F`   | 1     | Packed flags: bit 7 (`0x80`) = Rx Info Bright Set (Main #28, LED bright on receive, set=on); bits 6:5 = Lock Mode (Main #18; `00`=Key, `01`=Key+CH, `10`=Key+CH+PTT) ✓; bit 4 (`0x10`) = VFO Lock (set=lock) ✓; bit 0 (`0x01`) = Active Band at Power On (set=A frequency, clear=B frequency) ✓. Note: Power On Password enable previously thought to be bit 4 — incorrect; it may share `0x299F` or live elsewhere. |
| `0x29A0`   | 1     | **Unknown counter/version byte.** Values vary across working dumps (0x00, 0x22, 0x25). Non-zero values are valid — factory has 0x25. However, writing an inconsistent value (e.g. 0x17) was observed in a "no data" state. Safe to write as 0x00. See also `0x2997`. |
| `0x29A3`   | 1     | Radio ID (Ch #26). Global active index; `0x00`=first, `0x01`=second, etc. |
| `0x29A4`   | 1     | Default Zone Band A (CPS). 0-based zone index; `0x00`=no zone/Zone 1, `0x01`=Zone 2, etc. ✓ |
| `0x29A6`   | 1     | Default Zone Band B (CPS). 0-based zone index; `0x00`=no zone/Zone 1, `0x01`=Zone 2, etc. ✓ |
| `0x29A8`   | 4     | Key Define (Main #13). Key1 Short/Long, Key2 Short/Long (4 bytes, 1 each). See enum below. |
| `0x29AC`   | 1     | Priority Scan Channel (0-based index; UI shows 1-based). `0x00` = CH1. Confirmed by diff: CH3 → `0x02`. |
| `0x29AD`   | 1     | Unknown. `0x00` in all samples. |
| `0x29AE`   | 1     | Emergency key Short press function. Uses Emergency enum (see below). Default `0x21` = Emergency. |
| `0x29AF`   | 1     | Emergency key Long press function. Uses Emergency enum. Default `0x21` = Emergency. |
| `0x29C0`   | 4     | VHF scan range: start (2 B BCD LE × 100 kHz) + stop (2 B). `0xFFFF` = not set. Confirmed: 144.0=`40 14`, 148.0=`80 14`. |
| `0x29C4`   | 4     | Unknown — `0xFF` in all samples even when VHF scan range is set. |
| `0x29C8`   | 4     | UHF scan range: start (2 B BCD LE × 100 kHz) + stop (2 B). Confirmed: 430.0=`00 43`, 440.0=`00 44`. |
| `0x29CC`   | 4     | Unknown — `0xFF` in all samples even when UHF scan range is set. |
| `0x29D0`   | 42    | Key Calls 1–6. 7-byte stride × 6 slots. See `codeplug.py` `KeyCall`. |
| `0x3000`   | 136   | FM Radio (32 preset channels). See below. |
| `0x3D00`   | 32    | Normal Encryption Keys. 2-byte BE BCD × 16 slots. |
| `0x3E00`   | 256   | Enhanced Encryption Keys. 16 bytes × 16 slots. |
| `0x4000`   | ~640  | Radio ID table. 20-byte stride (4 B DMR ID LE + 16 B name). Up to 32 entries. |
| `0x4400`   | 7     | DTMF Config Header (interval char, group code, Self ID length, timing params). See below. |
| `0x4407`   | ~89   | DTMF Code Fields (Self ID, Kill, Stun, Wake Up, BOT, EOT codes). 16-byte records. See below. |
| `0x4460`   | 17    | DTMF Encode Table header (purpose TBD). |
| `0x4471`   | 2048  | DTMF Encode Table. 16-byte stride × 128 slots. See below. |
| `0x5018`   | ~2352 | AES/ARC4 Keys. 49-byte stride × 48 slots (3 groups of 16: AES256, AES128, ARC4). Header at `0x5000` (24 B). |

## Step enum at `0x297F`

| Value   | Step     |
|---------|----------|
| `0x00`  | 2.5 kHz  |
| `0x01`  | 5 kHz    |
| `0x02`  | 6.25 kHz |
| `0x03`  | 10 kHz   |
| `0x04`  | 12.5 kHz |
| `0x05`  | 25 kHz   |
| `0x06`  | 30 kHz   |
| `0x07`  | 50 kHz   |
| `0x08`  | 20 kHz   |

20 kHz sits at `0x08` (out of sequence) — likely added to firmware later
than the other 7 and appended rather than inserted.

## Key Define function enum (`0x29A8..0x29AB`)

All values `0x00`–`0x23` are confirmed from a combination of CPS diff
sessions and the firmware menu pointer table (segments 3+4 at
`@0x06dfb0..0x06e0c4` in v208 rodata — see "Menu segment architecture"
section below). The previously-unknown values `0x0D` and `0x0F` are now
identified as **Stun** and **TX-DSW** respectively.

| Value  | Function                    | Source |
|--------|-----------------------------|--------|
| `0x00` | OFF / not set               | |
| `0x01` | Power (radio on/off)        | ✓ baseline Key2L |
| `0x02` | Scan                        | ✓ session1 |
| `0x03` | Radio (FM)                  | ✓ baseline Key1S |
| `0x04` | Wake Up                     | ✓ session1 |
| `0x05` | Relay (Talkaround)          | ✓ session5 Key1S |
| `0x06` | Key Call 1                  | ✓ session5 Key2S |
| `0x07` | Key Call 2                  | ✓ session5 Key2L |
| `0x08` | Key Call 3                  | ✓ session6 Key1S |
| `0x09` | Key Call 4                  | ✓ session6 Key1L |
| `0x0A` | Key Call 5                  | ✓ session6 Key2S |
| `0x0B` | Key Call 6                  | ✓ session6 Key2L |
| `0x0C` | VOX                         | ✓ session5 Key1L |
| `0x0D` | **Stun** (long-press)       | ✓ menu pointer table seg 4 +0 |
| `0x0E` | Transceive Inhibit / Kill   | ✓ session9; menu seg 4 +1 |
| `0x0F` | **TX-DSW** (long-press)     | ✓ menu pointer table seg 4 +2 |
| `0x10` | Analog Monitor / **M-MONI** | ✓ session7 Key2L; menu seg 4 +3 |
| `0x11` | 1000Hz / **Tx1000**         | ✓ session2 EmergL; menu seg 4 +4 |
| `0x12` | 1450Hz / **Tx1450**         | ✓ session3 Key1L; menu seg 4 +5 |
| `0x13` | 1750Hz / **Tx1750**         | ✓ session3 Key2L; menu seg 4 +6 |
| `0x14` | 2100Hz / **Tx2100**         | ✓ session3 EmergL; menu seg 4 +7 |
| `0x15` | Zone Plus                   | ✓ session2 Key1L |
| `0x16` | Zone Minus                  | ✓ session2 Key2S |
| `0x17` | DMR Slot                    | ✓ session2 Key2L |
| `0x18` | Promiscuous                 | ✓ session3 Key1S |
| `0x19` | Manual Dial                 | ✓ session3 Key2S |
| `0x1A` | CH-Mode                     | ✓ session4 Key1S |
| `0x1B` | Reverse                     | ✓ session4 Key1L |
| `0x1C` | Bluetooth                   | ✓ baseline Key1L |
| `0x1D` | 0.5W Power                  | ✓ baseline Key2S |
| `0x1E` | FM Call                     | ✓ session4 Key2S |
| `0x1F` | Voltage                     | ✓ session4 Key2L |
| `0x20` | NOAA                        | ✓ session3 EmergS |
| `0x21` | Emergency / Alarm           | ✓ default 0x29AE/0x29AF; firmware label is `Alarm` |
| `0x22` | Key Beep                    | ✓ session7 Key1L |
| `0x23` | Encryption                  | ✓ session8 Key2L |
| `0xFF` | OFF (factory default)       | |

Long-press-only extras (only valid for Key1 Long / Key2 Long):
`TX-DSW`, `M-MONI`, `Tx1000`, `Tx1450`, `Tx1750`, `Tx2100` — values unknown; **needs diff verification**.

**Now resolved** — see the values table above. All six are real Key Define
enum values pulled from the menu pointer table (v208 `@0x06dfdc` segment 4
in the menu pointer table at rodata `0x06df30..0x06e150`):

| Long-press label | Enum value | Position in seg 4 |
|------------------|-----------|-------------------|
| `Stun`           | `0x0D`    | +0 |
| `TX-DSW`         | `0x0F`    | +2 |
| `M-MONI`         | `0x10`    | +3 (= `Analog Monitor` semantically) |
| `Tx1000`         | `0x11`    | +4 (= `1000Hz` semantically) |
| `Tx1450`         | `0x12`    | +5 |
| `Tx1750`         | `0x13`    | +6 |
| `Tx2100`         | `0x14`    | +7 |

Confirmed sample: Key1S=`0x03` (Radio), Key1L=`0x1C` (Bluetooth),
Key2S=`0x1D` (0.5W Power), Key2L=`0x01` (Power) — from live radio baseline.

Four consecutive bytes at `0x29A8..0x29AB`: Key1 Short, Key1 Long, Key2
Short, Key2 Long. All four use the same function enum.

## Menu segment architecture (firmware-internal)

Reverse-engineered from v208 firmware rodata `0x06df30..0x06e150`. The
firmware stores menu labels in a single contiguous **pointer table**
broken into segments separated by handler function pointers.

### Layout

```
struct menu_segment {
    char* labels[N];      // N consecutive 32-bit pointers into menu pool (rodata 0x6c000-0x72000)
    void (*handler)();    // 32-bit function pointer in SRAM (range 0x05500000-0x05900000)
};
struct menu_segment table[];   // segments concatenated; no count field
```

The dispatcher distinguishes labels from handlers by **address range**:
labels point into the menu pool (VA `0x0307c000..0x0307f000` for v208,
i.e. `LOAD_BASE + 0x6c000..0x72000`), while handlers point into SRAM
code (VA `0x055xxxxx..0x056xxxxx`).

### v208 segment table

Starts at rodata `0x06df30`. Items in earlier (lower-value) segments
may be referenced by multiple settings via the same enum.

| Seg | Items | Handler (SRAM) | Purpose |
|-----|------:|----------------|---------|
| 0   | 7    | `0x0561daee`   | Encryption Type list (Off/Scan/Normal/Enhanced/ARC4/AES128/AES256) |
| 1   | 13   | `0x0561da2a`   | Tx Authority + leading step values |
| 2   | 2    | `0x0561df7e`   | Step list tail (50K, Forbid) |
| 3   | 10   | `0x0561df46`   | **Key Define** values `0x02..0x0B` (Scan, Radio, Wake Up, Relay, KeyCall 1-6) |
| 4   | 59   | `0x0561df76`   | **Key Define** values `0x0D..0x48` (Stun, Kill, TX-DSW, M-MONI, Tx1000-2100, ZonePlus/Minus, DMR Slot, …); index 23+ are Main-Set menu strings shared via the same handler |
| 5   | 15   | `0x0561dfc2`   | Channel A/B Set screen (Power, Vox, Vox Level, W/N, TOT, DTMF Signal, C-CDC, R-CDC, T-CDC, Ch.Name, Busy Lock, Shift Up, Shift Freq, Color Code, Encrypt Type) |
| 6   | 9    | `0x0561d3a2`   | DMR sub-screen (DMR Mode, DMR Slot, Promiscuous, RxAllPC, RxAllCC, GPS Contacts, Radio ID, Contacts, Rx List) |
| 7   | 21   | `0x05670c82`   | Top main menu (Band A/B Set, Message, Call Log, Contacts, Radio ID, FM radio, Encryption, Version, InBox, Write, Sent Items, Quick Text, Local GPS, Receive GPS, Missed, Answered, Outgoing, …) |

### Key Define index math

The Key Define value `K` at `0x29A8..0x29AB` indexes into a virtual
"flat" view of segments 3+4:

```
index = K
if   K in 0x02..0x0B:  segment 3 + (K - 0x02)
elif K in 0x0D..0x48:  segment 4 + (K - 0x0D)
else:                  special-cased (0x00=OFF, 0x01=Power, 0xFF=OFF)
```

Note: `0x0C` (VOX) is **not** in either segment — its label likely lives
in another segment or is rendered specially.

### Why we couldn't decompile the dispatcher

The handlers (`0x0561d…`, `0x0567…`) live at SRAM addresses, populated by
a flash→SRAM copy at boot. The flash source for these copies wasn't
located by direct address lookup (no LRW literal-pool entry in the flash
code section matches the SRAM addresses). To inspect the dispatcher
itself you'd need either:

1. Live SRAM dump from a running radio (via debugger or boot-time
   serial probe), or
2. Trace the boot-time copy routine in flash code that initializes the
   `0x05500000+` region — find its `memcpy(SRAM_dst, flash_src, size)`
   call and read source bytes from flash.

The label table itself in flash rodata is fully understood and is what
this section documents.

## Emergency key enum (`0x29AE`, `0x29AF`)

Two bytes: Short press (`0x29AE`) and Long press (`0x29AF`). Both default to
`0x21` (Emergency). **Same enum as Key1/Key2** — confirmed by diff sessions
showing identical byte values across both address sets for every tested function
(Scan=`0x02`, Wake Up=`0x04`, NOAA=`0x20`, 1000Hz=`0x11`, etc.).

## Key Calls 1–6 (`0x29D0`, 7 bytes × 6 slots)

Programmable key-call bindings. Each slot can reference a contact (address book
or priority contact) and optionally associate it with a quick SMS message.

### Layout (7 bytes)

```
offset  bytes  meaning
  0     1      mode (0=analog, 1=digital)
  1..4  4      contact reference (LE uint32; see encoding below)
  5     1      call type (0=unset, 1=voice, 2=message)
  6     1      quick message index (1-based; 0=none)
```

### Contact reference encoding

| Value range        | Meaning                |
|-------------------|------------------------|
| `0`               | unset                  |
| `1..N`            | address book index `N−1` (1 = AB[0]) |
| `100001..100000+N` | priority contact index `N−100001` (100001 = priority[0]) |

The `.present` property is true if either `contact_ref != 0` or `quick_msg_index != 0`.

## Normal Encryption Keys (`0x3D00`, 2 bytes × 16 slots)

16 encryption key slots for "Normal" encryption mode (Encrypt Type = Normal).
Each slot is a 2-byte big-endian BCD value (`0x0000`..`0xFFFF`). All-FF = unused.

## Enhanced Encryption Keys (`0x3E00`, 16 bytes × 16 slots)

16 encryption key slots for "Enhanced" encryption mode (Encrypt Type = Enhanced).
Each slot is 16 bytes (exact key encoding not documented; `codeplug.py` preserves
raw bytes for lossless round-trip). All-FF = unused.

## DTMF Config Header (`0x4400..0x4406`)

Configuration fields for DTMF decode/signaling. Digit encoding uses the same
scheme as the DTMF Encode Table (see below).

| Address | Setting | Encoding |
|---------|---------|----------|
| `0x4400` | DTMF Interval Character | DTMF digit code (A=0x0A, B=0x0B, C=0x0C, D=0x0D, *=0x0E, #=0x0F) |
| `0x4401` | Group Code | DTMF digit code, OFF=0xFF |
| `0x4402` | Self ID length | Number of digits in Self ID |
| `0x4403` | First Digit Time(ms) | value / 10 |
| `0x4404` | Auto Reset Time(s) | value × 10 (0x00=0.0, 0xFA=25.0) |
| `0x4405` | DTMF Transmitting Time(ms) | value / 10 (0x00=0, 0xFA=2500) |
| `0x4406` | Time-Lapse After En.(ms) | value / 10 (0x01=10, 0xFA=2500) |

## DTMF Code Fields (`0x4407..0x445F`)

DTMF digit-sequence fields for Self ID, remote control codes, and PTT ID
codes. Same digit encoding as the DTMF Encode Table. Each 16-byte code
field: bytes 0–13 = DTMF digits, byte 14 (+0x0E) = digit count.

| Address | Setting |
|---------|---------|
| `0x4407..0x440F` | Self ID digits (up to ~6 digits, at approximately `0x440A` based on observed data) |
| `0x4410..0x441F` | Remotely Kill code (16 bytes) |
| `0x4420..0x442F` | Remotely Stun code (16 bytes) |
| `0x4430..0x443F` | Remotely Wake Up code (16 bytes) |
| `0x4440..0x444F` | PTT ID Starting (BOT) code (16 bytes) |
| `0x4450..0x445F` | PTT ID Ending (EOT) code (16 bytes) |

## DTMF Encode Table (`0x4471`, 16 bytes × 128 slots)

128 DTMF code slots. Each slot holds a sequence of up to 14 DTMF digits.
Valid digits per CPS: 0-9, A, B, C, D, *, #.

Header at `0x4460..0x4470` (17 bytes, purpose TBD).

### Slot layout (16 bytes)

Entry N (1-based) starts at `0x4471 + (N-1) * 16`.

| Offset | Bytes | Meaning |
|--------|-------|---------|
| `+0x00..+0x0D` | 14 | DTMF digits (raw values, left-packed). Unused trailing bytes are `0x00`/`0xFF` (TBD). |
| `+0x0E` | 1 | Digit count (number of valid digits in the slot). |
| `+0x0F` | 1 | Unknown / padding. |

### Digit encoding

| Value | Digit |
|-------|-------|
| `0x00` | 0 |
| `0x01` | 1 |
| `0x02` | 2 |
| `0x03` | 3 |
| `0x04` | 4 |
| `0x05` | 5 |
| `0x06` | 6 |
| `0x07` | 7 |
| `0x08` | 8 |
| `0x09` | 9 |
| `0x0A` | A ✓ |
| `0x0B` | B ✓ |
| `0x0C` | C ✓ |
| `0x0D` | D ✓ |
| `0x0E` | * ✓ |
| `0x0F` | # ✓ |

### Evidence

- Entry #1 set to "1": digit at `0x4471`=`0x01`, length at `0x447F`=`0x01`.
- Entry #128 set to "128": digits at `0x4C61`=`0x01`, `0x4C62`=`0x02`, `0x4C63`=`0x08`, length at `0x4C6F`=`0x03`.
- Stride verified: `0x4C61 - 0x4471` = `0x7F0` = 2032 = 127 * 16.

## AES/ARC4 Keys (`0x5018`, 49 bytes × 48 slots)

48 encryption key slots organized into three groups of 16 by key type.
Header at `0x5000` (24 bytes, contents not documented).

### Slot layout (49 bytes)

The actual key data encoding is not documented in `codeplug.py` — the
preserves raw bytes verbatim for lossless round-trip.

### Key type by slot index

| Slot range | Key type |
|-----------|----------|
| `0..15`    | AES256   |
| `16..31`   | AES128   |
| `32..47`   | ARC4     |

The `.key_number` field is 1-based within the type (1..16), so slot 16 is
AES256 #16 and slot 17 is AES128 #1.

### Firmware naming evidence

The radio menu itself names the five distinct cipher types:

| Firmware label | Slot range | Where in CPS Encryption Type dropdown |
|----------------|-----------|---------------------------------------|
| `Normal`       | `0x3D00` (separate region, 2 B × 16) | "Normal Mode" |
| `Enhanced`     | `0x3E00` (separate region, 16 B × 16) | "Enhanced" |
| `ARC4`         | `0x5018+` slots 32..47 | "Special" (slot picks cipher) |
| `AES128`       | `0x5018+` slots 16..31 | "Special" (slot picks cipher) |
| `AES256`       | `0x5018+` slots 0..15  | "Special" (slot picks cipher) |

Channel byte `+0x28` bits 6:5 stores the *type* (`Encrypt Type`, 0..3
interpreted as Normal/Enhanced/Special-by-slot). Channel byte `+0x28`
low nibble stores `Encrypt NO` (the 1..16 key number within the type;
the radio menu labels this `加密组别` = "encryption group"). Combined,
the channel resolves to a (region, slot) tuple that picks one specific
key from the table.

## Quick Messages (SMS, `table_1dfx` block `0x1DF8` + `0xDC`, 200 bytes × 16 slots)

Pre-written SMS text messages. First slot starts at block offset `0xDC`
(220 bytes) within block `0x1DF8`. Slots stride is 200 bytes (`0xC8`), so
the first 4 slots fit in block `0x1DF8` and the remaining 12 spill into
`0x1DF9`.

Each slot is null-terminated ASCII text up to 199 characters. Empty slots
are all-`0xFF` or all-`0x00`. The parser validates that all bytes before the
null are printable ASCII.

## FM Radio (`0x3000`, 136 bytes)

32 FM broadcast preset channels + VFO frequency.

### Layout

| Offset | Bytes | Meaning |
|--------|-------|---------|
| `0x3000..0x3003` | 4 | Slot bitmap (LE uint32). Bit `i` cleared = slot `i+1` used. |
| `0x3004..0x3083` | 128 | 32 slots × 4 B each. Each slot is BCD LE frequency × 10 Hz (same encoding as channel rx/tx). Slot N at `0x3004 + (N-1)*4`. |
| `0x3084..0x3087` | 4 | FM Radio VFO frequency (BCD LE × 10 Hz). |

### Frequency encoding

Same as channel rx/tx frequencies: 4-byte BCD little-endian, value × 10 Hz.
For example, `00 00 00 01` = 100.0 MHz (BCD `00000001` → 10,000,000 × 10 Hz → 100.0 MHz),
`10 98 00 00` = 107.8 MHz.

## Frequency Scan ranges (`0x29C0`, `0x29C8`, 4 bytes each)

VHF and UHF frequency scan start/stop bounds as configured in CPS.
All bytes are `0xFF` when the scan range has not been set in CPS (radio
uses its full band limits).

### Encoding (confirmed by diff)

Each range is 4 bytes: start (2 B) + stop (2 B). BCD little-endian, value × 100 kHz.
For example:
- `40 14` (LE) = BCD `1440` → 144.0 MHz ✓
- `80 14` (LE) = BCD `1480` → 148.0 MHz ✓
- `00 43` (LE) = BCD `4300` → 430.0 MHz ✓
- `00 44` (LE) = BCD `4400` → 440.0 MHz ✓

### Addresses

| Address | Bytes | Meaning |
|---------|-------|---------|
| `0x29C0..0x29C1` | 2 | VHF scan start (BCD LE × 100 kHz) |
| `0x29C2..0x29C3` | 2 | VHF scan stop (BCD LE × 100 kHz) |
| `0x29C4..0x29C7` | 4 | Unknown — `0xFF` in all current samples. Earlier observation showed 136.0/174.0 MHz here, suggesting fixed VHF band limits or a second VHF range, but unverified. |
| `0x29C8..0x29C9` | 2 | UHF scan start (BCD LE × 100 kHz) |
| `0x29CA..0x29CB` | 2 | UHF scan stop (BCD LE × 100 kHz) |
| `0x29CC..0x29CF` | 4 | Unknown — `0xFF` in all current samples. |

## Notes on per-channel settings

**VOX**, **Vox Level** (Ch #7, #8), and **TOT** (Ch #10) produce zero
byte changes in the settings region — they live inside the channel slot
(per-channel TOT at `+0x23`, per-channel VOX at `+0x20` bit 5 + low
nibble). See [`channels.md`](channels.md).

## Outside the mapped 8 regions

- **Serial number** at radio `0xE000` (b1=0x0F): ASCII null-padded,
  e.g. `HD211101108`. Manufacture date at `0xE02C`: `2024/4/15`.
- **Radio ID string** at `0xE800`: `IHD8580` (7 bytes, read by CPS
  during setup probe; confirmed by both firmware analysis and CPS source
  decompilation).
- **Boot-ROM image filename** at firmware rodata `0x06de60` (v208):
  `HD-GPS-HD2PA-C7000-V2.0.7-GPS.bin` — note the version says
  **V2.0.7** even in the v2.0.8 firmware, so this string is a
  build-script artifact / loader reference image, not a per-firmware
  version label. v213 firmware has `…-V2.1.3-GPS.bin` at the same
  offset. Don't rely on this string to identify the firmware revision.

## Manual vs mapped settings comparison

Cross-reference of HD2 User's Manual (EN) against all documented
addresses in `settings.md`, `channels.md`, and `records.md`. The
`Firmware string` column (where filled) is the exact ASCII label
present in v208 firmware rodata — useful when matching CPS labels
to actual radio menu entries.

### Main Set

| # | Menu item | Firmware string | Chinese | Where |
|---|-----------|-----------------|---------|-------|
| 1 | Squelch | `Squelch` | 静噪 / 静噪等级 | `0x2970` |
| 2 | Save | `Save` | 省电模式 | `0x2973` bits 7:5 |
| 3 | A/B Time | `A/B Time` | — | `0x2974` |
| 4 | Double PTT | `Double PTT` | — | `0x2973` bit 3 |
| 5 | Bluetooth | `BlueTooth` | — | **unknown** (bit 2 = Night Mode; Bluetooth address not yet confirmed) |
| 6 | BTRebind | `BTRebind` | — | runtime action (not stored) |
| 7 | Voice | `Voice` | 声控等级 | `0x2971` bit 5 |
| 8 | Zone Name | `Zone Name` | — | `0x2975` bit 0 |
| 9 | VOX Delay | `Vox Delay` | — | `0x2976` bits 3:0 |
| 10 | Mic Gain | `Mic Gain` | — | `0x299B` |
| 11 | Hang Up | `Hang Up` | 通话挂起 | `0x297A` |
| 12 | Tx Channel | `Tx Channel` | 发射信道 | unknown |
| 13 | Key Define | `Key Define` | 侧键定义 | `0x29A8..0x29AB` |
| 14 | Backlight | `Backlight` | 背光灯 | `0x2972` |
| 15 | Brightness | `Brightness` | — | `0x299C` |
| 16 | Key Beep | `Key Beep` | — | `0x2977` bit 7 |
| 17 | Key Lock (auto lock after 15s) | `Key Lock` | — | `0x2971` bit 2 ✓ |
| 18 | Lock Mode | `Lock Mode` | — | `0x299F` bits 6:5 |
| 19 | CH-Mode | `CH-Mode` | — | `0x2978` bits 5,0 |
| 20 | S/D Mode | `S/D Mode` | — | `0x299D` bit 2 |
| 21 | Scan Mode | `Scan Mode` | 扫描模式 | `0x2973` bits 1:0 |
| 22 | Save CH | `Save CH` | 存储信道 | runtime action (not stored) |
| 23 | Delete CH | `Delete CH` | 删除信道 | runtime action (not stored) |
| 24 | Roger | `Roger beep` | 发射结束音 | `0x2971` bit 1 |
| 25 | Time | (set via clock cmd) | — | clock set command (see `protocol.md`) |
| 26 | Menu Exit | `MenuExitTime` | — | `0x299E` |
| 27 | Miss Call Set | `MissCallMenu` | — | `0x299D` bit 0 |
| 28 | Rx Info Bright Set | `Call InLight` | — | `0x299F` bit 7 |
| 29 | DMR TX Beep | `DMRTxBeep` | — | `0x2975` bit 4 |
| 30 | FM TX Beep | `FMTxBeep` | — | `0x2975` bit 5 |
| 31 | Night Mode | `NightMode` | — | `0x2978` bit 2 ✓ |
| 32 | Noise Tail | `Noise Tail` | 尾音消除 | `0x2977` bit 2 (on/off), bit 0 (mode: Reverse Code) |

(Note: several Main-Set firmware strings drop the spaces seen in CSV/CPS
labels — e.g. `MenuExitTime`, `MissCallMenu`, `DMRTxBeep`, `FMTxBeep`,
`NightMode`. The radio renders these compactly in its 12-char menu
slots.)

### Channel settings (Band A/B Set)

| # | Menu item | Firmware string | Chinese | Where |
|---|-----------|-----------------|---------|-------|
| 1 | Zone | `Zone` | 区域选择 | runtime selection |
| 2 | GPS | `GPS` | — | channel `+0x20` bit 7 |
| 3 | RxGPSInfo | `RxGPSInfo` | — | channel `+0x2B` bit 5 |
| 4 | TxGPSInfo | `TxGPSInfo` | — | channel `+0x20` bit 4 |
| 5 | Step | `Step` | 步进频率 | `0x297F` (global) |
| 6 | Power | `Power` | 功率 | channel `+0x21` bits 3:2 + `+0x29` bit 3 |
| 7 | VOX | `Vox` | — | channel `+0x20` bit 5 |
| 8 | Vox Level | `Vox Level` | — | channel `+0x20` low nibble |
| 9 | W/N (Bandwidth) | `W/N` | — | channel `+0x29` bit 6 |
| 10 | TOT | `TOT` | — | channel `+0x23` |
| 11 | DTMF Signal | `DTMF Signal` | — | channel `+0x10` bits 6:0 (7-bit index, 0..127), `+0x11` bit 2 (enable) |
| 12 | C-CDC (Combined CTCSS/DCS) | `C-CDC` | — | channel `+0x24..+0x27` (sets both Rx+Tx) |
| 13 | R-CDC (Rx CTCSS/DCS) | `R-CDC` | — | channel `+0x24..+0x25` |
| 14 | T-CDC (Tx CTCSS/DCS) | `T-CDC` | — | channel `+0x26..+0x27` |
| 15 | Ch.Name | `Ch.Name` | — | channel `+0x04` (10 B ASCII) |
| 16 | Busy Lock | `Busy Lock` | — | channel `+0x2B` bits 7:6 |
| 17 | Shift Up | `Shift Up` | — | **unmapped** (direction toggle for repeater offset) |
| 18 | Shift Freq | `Shift Freq` | 频差频率 | `0x2985` (global) |
| 19 | Color Code | `Color Code` | 色码 | channel `+0x2A` high nibble |
| 20 | Encrypt Type | `Encrypt Type` | 加密类型 | channel `+0x28` bits 6:5 |
| 21 | Encrypt NO. | `Encrypt NO` | 加密组别 | channel `+0x28` low nibble |
| 22 | DMR Mode | `DMR Mode` | — | channel `+0x2A` low nibble bits 3,1 |
| 23 | DMR Slot | `DMR Slot` | — | channel `+0x2A` low nibble bit 0 |
| 24 | Promiscuous | `Promiscuous` | — | channel `+0x29` bit 0 (same bit as RxAll CC — same feature, dual UI label) |
| 25 | RxAll CC | `RxAllCC` | — | channel `+0x29` bit 0 (same bit as Promiscuous above) |
| 26 | Radio ID | `Radio ID` | — | `0x29A3` (global active index) |
| 27 | Contacts | `Contacts` | 通信录 | channel `+0x1C` (4 B DMR ID LE) |
| 28 | GPS contacts | `GPS Contacts` | — | channel `+0x12` (1 B, 1-based index) |
| 29 | Rx List | `Rx List` | — | channel `+0x30..+0xAF` (inline, denormalized) |

### Other features

| Feature | Where |
|---------|-------|
| Priority Contacts | block `0x1B84` (72-byte records, see `records.md`) |
| Address Book | block `0x0000` b1=0x31 (72-byte records, see `records.md`) |
| Radio ID table | `0x4000+` (20-byte records, see `records.md`) |
| Zones | blocks `0x2200+` (145-byte records, see `records.md`) |
| RX Group Aliases | block `0x21D8` (142-byte records, see `records.md`) |
| Channel bitmap | `vfo_config 0x0200..0x04ED` (see `address-space.md`) |
| VFO-A / VFO-B | radio `0x0090`, `0x0140` (see `channels.md`) |
| Logo | blocks `0x1DD0..0x1DF4` (RGB565, see `protocol.md`) |
| Clock set | write-session command (see `protocol.md`) |
| FM Radio (32 presets) | `0x3000` (136 B: bitmap + 32 × 4 B freq + VFO) |
| Normal Encryption Keys | `0x3D00` (2 B × 16 slots) |
| Enhanced Encryption Keys | `0x3E00` (16 B × 16 slots) |
| AES/ARC4 Keys | `0x5018` (49 B × 48 slots) |
| DTMF Config Header | `0x4400` (7 B: interval char, group code, Self ID len, timing) |
| DTMF Code Fields | `0x4407` (Self ID, Kill, Stun, Wake Up, BOT, EOT; 16 B records) |
| DTMF Encode Table | `0x4471` (16 B × 128 slots, header at `0x4460`) |
| Key Calls 1–6 | `0x29D0` (7 B × 6 slots) |
| Quick Messages (SMS) | `table_1dfx` block `0x1DF8` + `0xDC` (200 B × 16 slots) |

### CPS-only settings (not in radio menu)

| Feature | Where |
|---------|-------|
| Accept Radio Kill Command | `0x2975` bit 6 |
| Accept Radio Wake Up Command | `0x2975` bit 7 |
| No TX Info When Operating Menu | `0x2975` bit 1 |
| Press PTT Cancel VOX | `0x2977` bit 5 |
| Insert Headset Activates VOX | `0x2977` bit 4 |
| Dual Watch BDR | `0x2977` bit 1 (inverted: set=off) |
| Noise Tail Elimination Mode | `0x2977` bit 0 (set=Reverse Code) |
| Voice Language | `0x2979` bit 2 (set=English, clear=Chinese) |
| Time Format | `0x2979` bit 3 (set=24h, clear=12h) |
| Wakeup Speed (power save) | `0x2976` bits 5:4 (`10`=slow, `00`=fast, `01`=medium) |
| Repeater Connect | `0x2988` (direct value 1..10) |
| Power On Password enable | `0x2977` bit 3 (set=enabled, clear=disabled) |
| Power On Password value | `0x2989..0x298E` (6 ASCII bytes) |
| Alarm TX Time | `0x2990` (value ÷ 2) |
| Alarm Idle Time | `0x2991` (value − 5) |
| Lone Worker Response Time | `0x2998` (value − 1) |
| Lone Worker Pre-Alarms | `0x2999` (value − 1) |
| Rx Info Display Time | `0x299A` (value − 1) |
| Default Zone Band A | `0x29A4` (0-based zone index) |
| Default Zone Band B | `0x29A6` (0-based zone index) |
| VFO Lock | `0x299F` bit 4 (set=lock) |
| Active Band at Power On | `0x299F` bit 0 (set=A, clear=B) |
| Radio Functions (FM radio enable) | `0x2979` bit 0 (set=on, clear=off) |
| FM Radio Work Mode | `0x2973` bit 2 (set=VFO, clear=CH) |
| FM Radio Work CH | `0x297D` (0-based channel index) |

### IARU Region / Band limits

The CPS allows selecting an IARU region which sets RX/TX band limits for
Band A (VHF) and Band B (UHF). The band limits appear in the **header probe
response** (16-byte reply to the initial `GetVer`-style handshake) as 8
BCD LE × 100 kHz values (2 bytes each):

```
offset  meaning
 0..1   RX A lo
 2..3   RX A hi
 4..5   TX A lo
 6..7   TX A hi
 8..9   RX B lo
10..11  RX B hi
12..13  TX B lo
14..15  TX B hi
```

Observed values:

| Field | Region 1 | Region 2 | Region 3 |
|-------|----------|----------|----------|
| RX A | 136–174 | 136–225 | 136–174 |
| TX A | 144–146 | 144–148 | 144–148 |
| RX B | 400–480 | 400–480 | 400–480 |
| TX B | 430–440 | 420–450 | 430–440 |

**The IARU region band limits ARE written to the radio** — they are sent as
the 16-byte payload of the `b1=0x0E` WriteCommit frame, which is a separate
mechanism from the regular codeplug `b1=0x0F`/`b1=0x31` address writes.
The WriteCommit frame format is:

```
68 0E 01 01 pct csum 10 00 00 00 [16 bytes band limits] 10
```

Switching between Region 2 and Region 3 produces zero EEPROM diffs across all
8 mapped regions because the band limits bypass the normal codeplug address
space entirely. They do not appear at any `b1=0x0F` or `b1=0x31` address.

### Still unmapped

| Feature | Manual ref | Notes |
|---------|-----------|-------|
| **Shift Up** (direction) | Ch #17 | Shift freq is at `0x2985` but up/down direction is unmapped. Likely near `0x2985` or per-channel. |
| **Tx Channel** | Main #12 | Unclear what this setting controls. |
| **Bluetooth** | Main #5 | `0x2978` bit 3 was ruled out; bit 2 = Night Mode. Address still unknown. |
| **Channel Dis B / VFO-B CH-Mode** | CPS | Band A is `0x2978` bits 5,0. Band B not in any of the 8 mapped EEPROM regions — confirmed by full-dump diff (zero changes). Likely firmware-internal or in an unmapped address range. |
| **2-tone / 5-tone tables** | — | Referenced in CPS but never located. |
| **NOAA config** | Detailed ops p.11 | 11 preset frequencies (162.400–162.550 + 161.650/750/775, 162.000 MHz). Exhaustive BCD search of full EEPROM dump and all unmapped address ranges (`0x0F` scan `0x0000..0xFFFF`) found zero hits. Frequencies are **firmware-hardcoded** in ROM, not stored in codeplug. |
| **table_1dfx** residual | — | Quick Messages use ~3.2 KB; rest of 12 KB is unknown. |
| **table_4000** residual | — | Radio IDs use first ~640 B; rest of 1 KB unknown. |
| **table_428x** (3 KB) | — | Entirely unknown purpose. |
| **Settings gaps** | — | Unmapped bytes: `0x297B..0x297C`, `0x297E`, `0x2980..0x2984`, `0x2986..0x2987`, `0x2992..0x2997`, `0x29A5`, `0x29A7`, `0x29AD..0x29BF`, `0x29CC..0x29CF`, `0x29D7..0x29FF`, `0x2FA0..0x2FFF`, `0x3088..0x3CFF`, `0x3D20..0x3DFF`, `0x3F00..0x3FFF`, `0x4140..0x43FF`, `0x4C71..0x5017`, `0x5990+`. |

---

## Firmware cross-references (2026-05-13)

Cross-referenced against the V2.1.3 firmware decompile (`assets/source_v213/`
in the hd2-clean working tree). Settings.md / NOTES.md open questions
that the firmware analysis can answer or constrain:

### Resolved: codeplug `0xE800` returns a hardcoded model-ID stub

The CPS reads `0xE800` during write-session setup; pylunce notes it
isn't in any of the 8 dumped regions. **Firmware confirmation:** the
wire-protocol READ handler (`wire_cmd00_read_handler` at V2.1.3 VMA
`0x03042814`, line ~70540 of the app decompile) special-cases this one
address by writing 7 hardcoded bytes (`I H D 8 5 8 0`) directly into
the response buffer instead of reading from the small-settings bank at
`0x790000 + offset`. So `0xE800` isn't a real codeplug address — it's
a probe slot the firmware answers with a fixed model identifier. There
is no settings data behind it; no codeplug content is "missing" from
the dump.

### Constrained: `+0x12` per-channel byte is GPS contact index only

pylunce/channels.md marks "`+0x12` byte's role beyond GPS-contact
unconfirmed." Firmware confirms `+0x12` is **only** the GPS contact
index (1-based; 0 = none). No other firmware path reads this byte.

### Resolved: per-channel settings setter ↔ flash settings address map

The on-radio menu's per-setting handlers are now named in the v213
project (`setting_set_*` family, mostly in `0x0304b1a0..0x0304b550`).
Each setter writes one byte/bit of the in-RAM `g_state` mirror; the
flash backing store is at `0x790000+` (b1=0x0F, 128-byte stride).
Firmware-side bit-mappings agree with settings.md for the following
items (high-confidence cross-check; firmware setter at left, flash
address from settings.md at right):

| Firmware setter                          | Flash settings addr | Field         |
|------------------------------------------|---------------------|---------------|
| `setting_set_squelch`                    | `0x2970`            | Squelch (0..9)|
| `setting_set_voice_at_0x25_b5`           | `0x2971` bit 5      | Voice prompt  |
| `setting_set_roger_beep`                 | `0x2971` bit 1      | Roger beep    |
| `setting_set_keylock`                    | `0x2971` bit 2      | Auto key lock |
| `setting_set_backlight`                  | `0x2972`            | Backlight     |
| `setting_set_scanmode`                   | `0x2973` bit 0      | Scan Mode     |
| `setting_set_save_mode`                  | `0x2973` bits 7:5   | Power Save    |
| `setting_set_double_ptt`                 | `0x2973` bit 3      | Double PTT    |
| `setting_set_ab_time`                    | `0x2974`            | A/B Time      |
| `setting_set_fm_tx_beep`                 | `0x2975` bit 4      | DMR TX Beep   |
| `setting_set_keybeep`                    | `0x2977` bit 7      | Key Beep      |
| `setting_set_micgain`                    | `0x299B`            | Mic Gain      |
| `setting_set_brightness`                 | `0x299C`            | Brightness    |
| `setting_set_sd_mode`                    | `0x299D` bit 2      | S/D Mode      |
| `setting_set_menu_exit_timeout`          | `0x299E`            | Menu Exit     |
| `setting_set_lockmode`                   | `0x299F` bits 6:5   | Lock Mode     |
| `setting_set_step_remapped`              | `0x297F`            | VFO Step      |
| `keydefine_dispatch_assign`              | `0x29A8..0x29AB`+   | PF key actions|

### Constrained: Kill/Wakeup codes live in the channel record, not in `0x29AC`

pylunce/NOTES.md flagged "Emergency Alarm encoding at `0x29AC` —
address confirmed, encoding unknown." The firmware decompile has
`dmr_tx_csbk_kill_wakeup` (`0x0305219c`) reading **`+0xAC` (kill
code)** and **`+0xAE` (wakeup code)** from the per-channel record.
Both are 1-byte 1-based **contact indices** (0 = none); the channels.md
description (already correct) matches the firmware. The `0x29AC`
settings byte is a separate global emergency-alarm config — its
firmware setter has not been pinned down yet.

### SRAM-resident menu handlers — clarification

settings.md's appendix claims menu segment handlers live in SRAM
`0x055xxxxx..0x056xxxxx`. The specific handler addresses listed
(`0x0561daee`, `0x05670c82`, …) do NOT appear as 4-byte literal
pointers in either the v208 or v213 firmware `.bin`. Two
possibilities, both consistent:
- The handler-pointer values listed in the table were captured from a
  live debug session of an older firmware revision and don't
  represent stable v2.1.3 entry points.
- The handlers are constructed by indirect dispatch in code we already
  have at `0x0304bxxx` (the `setting_set_*` family), and the
  "segment handler" pointer field is consumed by a dispatcher that
  treats out-of-app-range values as opaque cookies.

The 32-entry key-define action enum that settings.md lists (`0x00..0x23`)
matches the v2.1.3 firmware's behaviour empirically (the on-radio
"Key Define" menu offers the same actions), but the runtime enum→action
dispatcher cannot be statically resolved without dumping that SRAM
region.

### Wire-protocol firmware case table (informational)

The wire-protocol command parser in firmware (`wire_protocol_parse` at
V2.1.3 VMA `0x0304323c`) implements 5 sync-framed (`0x68`-prefix)
command paths plus 5 unsynced ASCII probes. Beyond what pylunce
already documents, the firmware-recovered cases are:

- `cmd=0x07 sub=0x01`: READ RTC datetime (10-byte response from the
  internal RTC mirror buffer at IRAM `0x00040504`).
- `cmd=0x07 sub=0x02`: exit programming mode (calls `screen_destroy`).
- `cmd=0x03 b1=0x09`: RF alignment / test-tone (writes modem MMIO
  `0x11000100 = 0x73`).
- Single-byte `V` probe: alias of `GetVer`.
- `SLC7001` probe: sibling of `SLC7000`, replies `BJDR380`.

See `hd2_infodump/docs/protocol.md` (or `pylunce/docs/protocol.md`)
§"Firmware-recovered commands" for the full bit-level details.

### Activa probe is more than an identity check

pylunce notes the `Activa` ASCII probe and that it returns the UID.
Reality is more involved: the **6-byte probe** form returns the
8-byte UID (same as `GetUID`). The **270-byte form** (keyword + token
+ fill payload) is the radio's activation transaction — it writes
NVRAM slots (`g1/g3/g11/g12/g21/g22/g50`) and unlocks RX. See
`activa_tests/test_38_uid_buf_g22.py` / `test_39_uid_0a92.py` for the
full payload structure.

