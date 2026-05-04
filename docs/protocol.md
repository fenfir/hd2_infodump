# Wire protocol

All reverse-engineered from USB pcaps of the official Windows CPS
(`../dump/hd2_*.pcapng`) and verified against a live radio at firmware
`HD-GPS-HD2PA-C7000-V2.1.3-GPS.bin`.

## Serial

- Chip: CH340 (VID `0x1A86`, PID `0x7523`).
- Baud: **119200** 8N1 (non-standard — pyserial on macOS applies via
  `IOSSIOSPEED`; `termios` alone returns EINVAL).
- No flow control; RTS and DTR driven high locally after open.
- `/dev/cu.usbserial-*` on macOS; `/dev/tty.usbserial-*` blocks on DCD.
- **Power cable noise**: plugging in the radio's charging/power cable while
  the USB-serial cable is connected causes massive data corruption (~60–80%
  bad reads). Always unplug the power cable during dumps.

## Boot behaviour

On power-on the radio streams a plaintext debug log over serial (volume,
ADC readings, UID, etc.). **This must be drained to silence before any
command**, or the log bytes contaminate the first response. Drain pattern:
read with 0.1 s timeout until ≥1 s of silence, up to 10 s total.

## Probes

| Probe | Host sends | Radio replies | Purpose |
|-------|-----------|---------------|---------|
| `GetVer` (6 bytes ASCII) | ~35 bytes firmware ID, null-padded (e.g. `HD-GPS-HD2PA-C7000-V2.1.3-GPS.bin\x00\x00`) | Version / model check |
| `SLC7000` (7 bytes ASCII) | `BJDR380` (7 bytes ASCII) | Model check (CPS uses before clock set) |

Firmware ID breakdown: `HD-GPS` = product, `HD2PA` = variant, `C7000` =
internal DMR/AMBE chip, `V2.1.3` = firmware version.

The CPS sends `GetVer` before reads and `SLC7000` before writes, but
**neither probe is required to enter a distinct mode**. The radio accepts
read and write frames without any preceding probe. `hd1_codeplug_write.py`
uses `GetVer` (not `SLC7000`) as a pre-flight model check and writes
succeed — confirming there is no write-mode gate.

## Clock set (write sessions only)

Immediately after `SLC7000` / `BJDR380`, the CPS sends a 16-byte command
to synchronise the radio's real-time clock to the PC's current time.
The clock-set command also works after `GetVer` or with no preceding
probe — it does not require `SLC7000`. The CPS only sends it during
write sessions, but it is functionally independent.

### Frame (host → radio, 16 bytes)

```
offset  bytes  meaning
  0     0x68   sync
  1     0x0F   command family (settings)
  2     0x05   subcommand: SET CLOCK
  3..4  uint16 LE  year  (e.g. 0xEA 0x07 = 2026)
  5     uint8      month (1–12)
  6     0x00       padding
  7     uint8      day   (1–31)
  8     0x00       padding
  9     uint8      hour  (0–23, 24-hour)
 10     0x00       padding
 11     uint8      minute (0–59)
 12     0x00       padding
 13     uint8      second (0–59)
 14     0x00       padding
 15     0x10   terminator
```

**Encoding is binary (not BCD).** Year is a standard uint16 LE; time
fields are plain integers.

### Ack (radio → host, 16 bytes)

The radio echoes the entire 16-byte frame back verbatim on success.

On error the radio may send an ASCII error string followed by the echo with
bit 7 OR'd onto certain bytes (e.g. `month is Error\n\r` + modified echo).
This has been observed when the radio is in a bad state from a previous
failed command; the year/month values themselves appear to be accepted
broadly (year 2027 confirmed working).

### Examples

```
# CPS pcap (2026-04-15 18:22:40):
68 0f 05 ea 07 04 00 0f 00 12 00 16 00 28 00 10

# Confirmed on hardware (2027-04-16 23:41:26):
68 0f 05 eb 07 04 00 10 00 17 00 29 00 1a 00 10
```

### Write session sequence

1. Drain boot noise
2. Probe: `SLC7000` → `BJDR380`
3. **Set clock** (this command)
4. Read radio config (`b1=0x0D`)
5. Read model ID from addr `0xE800`
6. Read settings baseline from addr `0x2950`
7. Write codeplug data
8. (optional) `END` to reboot

**Note:** the CPS does not embed any date/time into the codeplug data
itself — the clock-set command is the only place a timestamp appears in
the write session.
## Read protocol

### Common frame (host → radio, 11 bytes)

```
offset  byte              meaning
  0     0x68              sync
  1     b1                read command family (0x0F or 0x31, see below)
  2     0x00              direction: 0 = request
  3     0x01              const
  4     pct               informational progress byte (0..100); radio doesn't validate
  5     csum              see formulas below
  6     size_lo           size low byte
  7     size_hi           size high byte
  8     addr_lo           addr low byte
  9     addr_hi           addr high byte
 10     0x10              terminator
```

### Common response (radio → host, 10 + size + 1 bytes)

```
  [0..9]            echo of cmd[0..9], with byte 2 rewritten to 0x02
  [10 .. 10+size-1] payload
  [10 + size]       0x10 terminator
```

The echo uses the **requested** size and address, so pipelining requires
matching responses to outstanding commands by address.

### Two read families

| Family        | `b1` | size     | Addressing                        | Used for                                              |
|---------------|------|----------|-----------------------------------|-------------------------------------------------------|
| small setting | 0x0F | 0x80     | `addr` = byte address; stride 128 | Header, VFO config, settings, contacts, group lists, radio IDs |
| large block   | 0x31 | 0x0400   | `addr` = 1024-byte block index; stride 1 | Address book, channels, zones, scan lists, logo |

**Critical:** for `b1=0x31` frames, `size_hi` MUST be `0x04`. If it is 0
(or the `size` field is misencoded), the radio replies with only the
11-byte echo and no data payload — looks like success but yields nothing.

### Checksums

Two independently-derived formulas, chosen by `b1`; both verified
byte-for-byte against 110 (`b1=0x0F`) and 684 (`b1=0x31`) frames in the
pcaps.

```python
def csum(addr: int, size: int, b1: int) -> int:
    if b1 == 0x31:  # large block
        return (0xFF - (0x15 + ((addr - 0x88) >> 8))) & 0xFF
    # small setting (b1=0x0F)
    addr_lo = addr & 0xFF
    addr_hi = (addr >> 8) & 0xFF
    return (0xFF - (0x10 + addr_hi + ((addr_lo + size - 1) >> 7))) & 0xFF
```

The radio appears to check both csum and terminator; an invalid frame
is silently ignored (no error response).

### Reliable read timing

At 119200 baud on macOS, reading byte-by-byte while bytes are still
arriving causes **bit-flip corruption**, not just truncation. Use this
pattern:

1. `ser.reset_input_buffer()`
2. `ser.write(cmd); ser.flush()`
3. `time.sleep((expected_len * 10) / 119200 + 0.1)` — wait for the full
   transmission to arrive.
4. `ser.read(ser.in_waiting)` — drain in one big read.
5. If short, retry up to 3×.

This matches the CPS behaviour observed in the pcaps.

## Write protocol

Two write variants, mirroring the two read families.

### `b1=0x31` — block-addressed, 4096-byte writes

Used for channels, zones, address book, the various `table_*` regions,
and the logo.

#### Frame (host → radio, 4107 bytes)

```
[0]      0x68
[1]      0x31
[2]      0x01           direction: 1 = write request
[3]      0x01
[4]      pct            progress 10..100 (cosmetic; radio doesn't validate)
[5]      0x31           const (was csum on reads — not a csum here)
[6]      0x00           size_lo (size = 0x1000 = 4096, encoded little-endian)
[7]      0x10           size_hi
[8..9]   addr_lo, addr_hi   1024-byte block address
[10..4105] 4096 bytes of data
[4106]   0x10           terminator
```

The 4096-byte payload covers **four** consecutive 1024-byte read-blocks,
so the effective block step per frame is +4. For regions smaller than
four read-blocks (`addr_book`, `table_4000`, `table_428x`), pad the
trailing read-blocks with `0xFF` to fill the 4096-byte write.

Settle ~0.3 s between TX end and ack — flash-write time on the radio side.

#### Ack (radio → host, 11 bytes)

```
68 31 02 01 [pct] 31 00 10 [addr_lo] [addr_hi] 10
```

### `b1=0x0F` — byte-addressed, 128-byte writes

Used for header, vfo_config, settings.

#### Frame (host → radio, 139 bytes)

```
[0]      0x68
[1]      0x0F
[2]      0x01           direction: 1 = write request
[3]      0x01
[4]      pct            cosmetic
[5]      0x00           const (NOT a checksum on writes)
[6]      0x80           size_lo (size = 0x80 = 128)
[7]      0x00           size_hi
[8..9]   addr_lo, addr_hi   byte address (matches the b1=0x0F READ addresses)
[10..137] 128 bytes of data
[138]    0x10           terminator
```

Settle ~0.05 s; flash writes are fast for these small chunks.

#### Ack (radio → host, 11 bytes)

```
68 0f 01 01 [pct] 00 80 00 [addr_lo] [addr_hi] 10
```

### Selective writes

The radio accepts partial writes of any single region without requiring a
whole-codeplug rewrite. CPS itself only writes the regions that changed
relative to the loaded baseline; `hd1_codeplug_write.py` does the same
(diff against a baseline `.bin` and only emit the differing 128-byte /
4096-byte windows).

### Logo specifics

- Image is 160 × 128 pixels.
- Stored as **RGB565 little-endian**, 40,960 bytes total.
- Uploaded with the b1=0x31 write protocol in 10 frames of 4 blocks each:
  addresses `0x1dd0, 0x1dd4, … 0x1df4` (step +4), pct values 10, 20, …, 100.

## Session teardown

Host sends ASCII `END` (`45 4e 44`). This **reboots the radio** — it is
not a graceful close; if you want to issue more commands, don't send it.
