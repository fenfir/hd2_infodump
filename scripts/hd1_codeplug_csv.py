#!/usr/bin/env python3
"""
hd1_codeplug_csv.py - Dump an HD1/HD2 codeplug .bin to CSV files for browsing.

Produces three CSV files next to the input:
  <name>_hex.csv       - 16-byte hex dump with radio addresses
  <name>_strings.csv   - all printable ASCII runs (>= 3 chars)
  <name>_decoded.csv   - best-effort field decode for regions we understand

The .bin is a packed concatenation of the regions listed in hd1_dump.py's
CODEPLUG_REGIONS. This table must match that definition.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

# (radio_addr_start, file_offset, length_bytes).
# For b1=0x0F regions, the radio addresses are contiguous bytes.
# For b1=0x31 regions, each 1024-byte payload is stored packed with the next.
# To translate "which radio block is at this file offset" we expose a list
# of segments with a per-segment stride interpretation.
REGIONS = [
    # (name, radio_addr_base, file_base, length_bytes, block_size, chunk_is_block_index)
    ("header",         0x0000, 0x000000, 0x00200, 0x80, False),
    ("vfo_config",     0x2000, 0x000200, 0x00380, 0x80, False),
    ("settings",       0x2900, 0x000580, 0x03280, 0x80, False),
    ("channels",       0x1B84, 0x003800, 0x93000, 0x400, True),
    ("table_1dfx",     0x1DF8, 0x096800, 0x03000, 0x400, True),
    ("table_21dx",     0x21D8, 0x099800, 0x14000, 0x400, True),
    ("table_4000",     0x4000, 0x0AD800, 0x00400, 0x400, True),
    ("table_428x",     0x4280, 0x0ADC00, 0x00C00, 0x400, True),
]


def file_to_radio(off: int) -> int | None:
    """Return the radio byte-address corresponding to a file offset.

    For b1=0x0F regions this is a linear byte mapping. For b1=0x31 regions
    the radio 'address' is a 1024-byte block index, so we return the block
    index scaled to bytes (i.e. block_index << 10) for display only.
    """
    for _, radio_base, file_base, length, block_size, is_block in REGIONS:
        if file_base <= off < file_base + length:
            rel = off - file_base
            if is_block:
                block = radio_base + rel // block_size
                return (block << 10) | (rel % block_size)
            return radio_base + rel
    return None


def radio_to_file(addr: int) -> int | None:
    """Inverse of file_to_radio for b1=0x0F (byte-address) regions."""
    for _, radio_base, file_base, length, block_size, is_block in REGIONS:
        if is_block:
            continue
        if radio_base <= addr < radio_base + length:
            return file_base + (addr - radio_base)
    return None


def read_cstring(data: bytes, offset: int, length: int) -> str:
    raw = data[offset : offset + length]
    # Strip null and 0xff padding
    end = len(raw)
    while end > 0 and raw[end - 1] in (0x00, 0xFF):
        end -= 1
    return raw[:end].decode("ascii", errors="replace")


def decode_freq_bcd(b: bytes) -> str:
    """4-byte BCD frequency. Each byte is 2 BCD digits; LE byte order.
    Returns a MHz string (best-guess with decimal after 4 digits from right)."""
    if len(b) != 4 or any(x == 0xFF for x in b):
        return ""
    digits = ""
    for byte in reversed(b):
        hi, lo = (byte >> 4) & 0xF, byte & 0xF
        if hi > 9 or lo > 9:
            return f"raw:{b.hex()}"
        digits += f"{hi}{lo}"
    # Interpret as 10 Hz units: value * 10 Hz = Hz; divide by 1e6 -> MHz
    try:
        hz = int(digits) * 10
        return f"{hz / 1e6:.5f} MHz"
    except ValueError:
        return f"raw:{b.hex()}"


def write_hex_csv(data: bytes, out: Path):
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file_offset", "radio_addr"]
                   + [f"b{i:02d}" for i in range(16)]
                   + ["ascii"])
        for off in range(0, len(data), 16):
            row = data[off : off + 16]
            radio = file_to_radio(off)
            radio_s = f"0x{radio:04x}" if radio is not None else ""
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
            w.writerow([f"0x{off:04x}", radio_s]
                       + [f"{b:02x}" for b in row]
                       + [asc])


def write_strings_csv(data: bytes, out: Path):
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file_offset", "radio_addr", "length", "string"])
        for m in re.finditer(rb"[\x20-\x7e]{3,}", data):
            off = m.start()
            radio = file_to_radio(off)
            radio_s = f"0x{radio:04x}" if radio is not None else ""
            w.writerow([f"0x{off:04x}", radio_s, len(m.group()), m.group().decode("ascii")])


def _block_file_off(region_name: str, block_addr: int) -> int | None:
    """File offset of the start of a 1024-byte block, by region name and block index."""
    for name, radio_base, file_base, length, block_size, is_block in REGIONS:
        if name != region_name or not is_block:
            continue
        if not (radio_base <= block_addr < radio_base + length // block_size):
            return None
        return file_base + (block_addr - radio_base) * block_size
    return None


CONTACT_TYPES = {
    0x04: "group",
    0x05: "private",
    0x06: "all",
}


def decode_contacts(data: bytes, rows: list):
    """Contacts table: lives in the first block of the channels region
    (radio block 0x1B84, file 0x3800). Records are 72 bytes each, 14/block.

    Layout:
      +0x00  4B  DMR ID (little-endian uint32; 0xFFFFFFFF = "all call")
      +0x04  1B  type   (0x04 group, 0x05 private, 0x06 all)
      +0x05  16B name   (ASCII, null-padded)
      +0x15  ... padding/trailing
    """
    base = _block_file_off("channels", 0x1B84)
    if base is None:
        return
    stride = 72
    per_block = 1024 // stride
    for i in range(per_block):
        off = base + i * stride
        rec = data[off : off + stride]
        if rec[:8] == b"\xFF" * 8:
            continue
        cid = int.from_bytes(rec[0:4], "little")
        ctype = rec[4]
        name = read_cstring(rec, 5, 16)
        if cid == 0 and not name:
            continue
        rows.append([
            f"contact[{i}]",
            f"block 0x1B84 +0x{i*stride:03x}",
            f"dmr_id={cid}",
            f"type=0x{ctype:02x} ({CONTACT_TYPES.get(ctype, '?')})",
            f"name={name!r}",
            "",
            rec.hex(),
        ])


def decode_header(data: bytes, rows: list):
    """DMR IDs at radio 0x0000-0x000F (two 4-byte LE uint32)."""
    if len(data) < 16:
        return
    id1 = int.from_bytes(data[0:4], "little")
    id2 = int.from_bytes(data[4:8], "little")
    rows.append(["header", "0x0000", f"id1={id1}", f"id2={id2}", "", "", data[:8].hex()])


def decode_vfo(data: bytes, rows: list):
    """VFO-A at radio 0x0090, VFO-B at 0x0140.

    The layout is the same as the trailing portion of a channel slot starting
    at channel-offset 0x10 (i.e. no marker/name prefix):
      +0x00  4B flags (FM=0x00002000, DMR=0x00000000)
      +0x04  4B rx freq BCD LE
      +0x08  4B tx freq BCD LE
      +0x0C  4B contact DMR ID LE
      +0x10..+0x1F  mode/tone bytes
    """
    for name, radio_addr in (("VFO-A", 0x0090), ("VFO-B", 0x0140)):
        off = radio_to_file(radio_addr)
        if off is None:
            continue
        rec = data[off : off + 32]
        if all(b == 0xFF for b in rec):
            continue
        flags = int.from_bytes(rec[0:4], "little")
        rx = decode_freq_bcd(rec[4:8])
        tx = decode_freq_bcd(rec[8:12])
        contact = int.from_bytes(rec[12:16], "little")
        mode = "FM" if (flags & 0x00002000) else "DMR"
        tone_info = ""
        if mode == "FM":
            rx_ts = _decode_ctcss(rec[0x14:0x16])
            tx_ts = _decode_ctcss(rec[0x16:0x18])
            if rx_ts or tx_ts:
                tone_info = f"rx_ctcss={rx_ts} tx_ctcss={tx_ts}"
        rows.append([
            name,
            f"0x{radio_addr:04x}",
            f"{mode} rx={rx} tx={tx}",
            f"contact={contact}",
            tone_info or f"flags=0x{flags:08x}",
            "",
            rec.hex(),
        ])


def _decode_ctcss(b: bytes) -> str:
    """2-byte BCD CTCSS frequency: e.g. 13 17 -> 131.7 Hz. 0xFFFF = none."""
    if len(b) != 2 or b == b"\xff\xff":
        return ""
    digits = ""
    for byte in b:
        hi, lo = (byte >> 4) & 0xF, byte & 0xF
        if hi > 9 or lo > 9:
            return f"raw:{b.hex()}"
        digits += f"{hi}{lo}"
    try:
        return f"{int(digits) / 10:.1f} Hz"
    except ValueError:
        return f"raw:{b.hex()}"


def decode_channels(data: bytes, rows: list):
    """Channels live in 1024-byte blocks at radio 0x1BCC..0x1DCF.
    Each block holds up to 5 slots starting at block offset 0x80;
    each slot is 176 bytes.

    Slot layout:
      +0x00  4B  marker         (always 0xFFFFFFFF in observed data)
      +0x04  10B name           (ASCII, null/0xff-padded)
      +0x0E  2B  pad
      +0x10  4B  flags          (FM=0x00002000, DMR=0x00000000)
      +0x14  4B  rx freq        (BCD LE; value * 10 Hz; 0xFFFFFFFF = unset)
      +0x18  4B  tx freq        (BCD LE; value * 10 Hz)
      +0x1C  4B  contact dmr_id (LE uint32)
      +0x20  16B mode/tone bytes
              For FM: +0x24..0x25 = rx CTCSS (2B BCD), +0x28..0x29 = tx CTCSS
              For DMR: 0xFF in tone slots; slot/CC/group encoded in flags
    """
    ch_index = 0
    for block in range(0x1BCC, 0x1DD0):
        boff = _block_file_off("channels", block)
        if boff is None:
            continue
        for slot in range(5):
            off = boff + 0x80 + slot * 176
            rec = data[off : off + 176]
            rx_raw = rec[0x14:0x18]
            if rx_raw == b"\xff\xff\xff\xff" or rx_raw == b"\x00\x00\x00\x00":
                continue
            name = read_cstring(rec, 4, 10)
            flags = int.from_bytes(rec[0x10:0x14], "little")
            rx = decode_freq_bcd(rx_raw)
            tx = decode_freq_bcd(rec[0x18:0x1C])
            contact = int.from_bytes(rec[0x1C:0x20], "little")
            mode_byte = rec[0x20]
            mode = "FM" if (flags & 0x00002000) else "DMR"
            tone_info = ""
            if mode == "FM":
                rx_ts = _decode_ctcss(rec[0x24:0x26])
                tx_ts = _decode_ctcss(rec[0x26:0x28])
                if rx_ts or tx_ts:
                    tone_info = f"rx_ctcss={rx_ts} tx_ctcss={tx_ts}"
            rows.append([
                f"channel[{ch_index}]",
                f"block 0x{block:04x} slot {slot}",
                f"name={name!r}",
                f"{mode} rx={rx} tx={tx}",
                f"contact={contact}",
                tone_info or f"flags=0x{flags:08x} mode=0x{mode_byte:02x}",
                rec[:0x30].hex(),
            ])
            ch_index += 1


def decode_zones(data: bytes, rows: list):
    """Zones live in the table_21dx region (radio block 0x2200+).
    Layout (tentative, observed for a single 'Zone1' entry):
      block offset 0x80:
        +0x00  1B  pad/marker (0xff)
        +0x01  16B name (ASCII, null-padded)
        +0x11  channel-id list (16-bit LE indices, 0xFFFF = end)
    """
    zone_index = 0
    # Walk a small range of plausible zone blocks
    for block in range(0x2200, 0x2210):
        boff = _block_file_off("table_21dx", block)
        if boff is None:
            continue
        # Try a single slot at offset 0x80 (we have only one example)
        off = boff + 0x80
        slot = data[off : off + 256]
        if not slot or slot[1] in (0x00, 0xFF):
            continue
        name = read_cstring(slot, 1, 16)
        if not name:
            continue
        channels = []
        for i in range(0x11, 0x80, 2):
            v = slot[i] | (slot[i + 1] << 8)
            if v == 0xFFFF:
                break
            channels.append(v)
        rows.append([
            f"zone[{zone_index}]",
            f"block 0x{block:04x}",
            f"name={name!r}",
            f"channels={channels}",
            "",
            "",
            slot[:0x30].hex(),
        ])
        zone_index += 1


def write_decoded_csv(data: bytes, out: Path):
    rows: list = []
    decode_header(data, rows)
    decode_vfo(data, rows)
    decode_contacts(data, rows)
    decode_channels(data, rows)
    decode_zones(data, rows)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "radio_addr", "f1", "f2", "f3", "f4", "raw_hex"])
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bin", help="Input codeplug .bin file")
    ap.add_argument("--out", default=None, help="Output prefix (default: same as input)")
    args = ap.parse_args()

    data = Path(args.bin).read_bytes()
    prefix = Path(args.out) if args.out else Path(args.bin).with_suffix("")

    hex_csv = prefix.with_name(prefix.name + "_hex.csv")
    strings_csv = prefix.with_name(prefix.name + "_strings.csv")
    decoded_csv = prefix.with_name(prefix.name + "_decoded.csv")

    write_hex_csv(data, hex_csv)
    write_strings_csv(data, strings_csv)
    write_decoded_csv(data, decoded_csv)

    print(f"  {hex_csv}      ({len(data)//16} rows)")
    print(f"  {strings_csv}")
    print(f"  {decoded_csv}")


if __name__ == "__main__":
    main()
