#!/usr/bin/env python3
"""
logo_render.py - Reconstruct the HD1/HD2 boot logo as a 160x128 BMP.

Three input modes:
  --raw  <path>    reads a .raw file from hd1_replay.py (OUT/IN frame tags)
  --bin  <path>    reads a 40960-byte RGB565 LE buffer directly
  --pcap <path>    reads a USB pcap (requires tshark on PATH), extracts the
                   40 blocks at radio block addresses 0x1DD0..0x1DF7

Outputs <prefix>.rgb565 and <prefix>.bmp.
"""

import argparse
import struct
import subprocess
from pathlib import Path

LOGO_W, LOGO_H = 160, 128
BLOCK_SIZE = 1024
START_BLOCK = 0x1DD0
END_BLOCK = 0x1DF7
NUM_BLOCKS = END_BLOCK - START_BLOCK + 1   # 40
TOTAL = NUM_BLOCKS * BLOCK_SIZE            # 40960

assert LOGO_W * LOGO_H * 2 == TOTAL


def read_frames(path: Path):
    """Yield (direction, payload) from .raw file."""
    data = path.read_bytes()
    i = 0
    while i < len(data):
        tag = data[i:i+4]
        if tag not in (b"OUT ", b"IN  "):
            raise ValueError(f"bad tag at {i}: {tag!r}")
        n = struct.unpack("<I", data[i+4:i+8])[0]
        payload = data[i+8:i+8+n]
        yield tag.strip().decode(), payload
        i += 8 + n


def reconstruct(raw_path: Path):
    """Return (40960-byte buffer, set of fully-correct block indices)."""
    buf = bytearray(b"\xff" * TOTAL)
    have = bytearray(TOTAL)  # 1 where we have a real byte
    pending_addr = None

    for d, p in read_frames(raw_path):
        if d == "OUT":
            # 11-byte block-read frame: 68 31 00 01 pct cd 00 04 lo hi 10
            if len(p) == 11 and p[0] == 0x68 and p[1] == 0x31:
                pending_addr = p[8] | (p[9] << 8)
            else:
                pending_addr = None
        elif d == "IN" and pending_addr is not None:
            # Response: [10-byte echo][data...][0x10]
            if len(p) < 10:
                continue
            payload = p[10:]
            # Strip trailing 0x10 if present (only on full 1035-byte responses)
            if len(p) == 1035 and payload.endswith(b"\x10"):
                payload = payload[:-1]
            block_idx = pending_addr - START_BLOCK
            if not (0 <= block_idx < NUM_BLOCKS):
                continue
            offset = block_idx * BLOCK_SIZE
            n = min(len(payload), BLOCK_SIZE)
            buf[offset:offset+n] = payload[:n]
            for k in range(n):
                have[offset+k] = 1

    # Stats
    block_completeness = []
    for b in range(NUM_BLOCKS):
        got = sum(have[b*BLOCK_SIZE:(b+1)*BLOCK_SIZE])
        block_completeness.append(got)
    return bytes(buf), block_completeness


def rgb565_to_rgb888(buf: bytes, width: int, height: int) -> bytes:
    """Convert RGB565 little-endian to RGB888."""
    out = bytearray(width * height * 3)
    for i in range(width * height):
        v = buf[2*i] | (buf[2*i+1] << 8)
        r5 = (v >> 11) & 0x1f
        g6 = (v >> 5) & 0x3f
        b5 = v & 0x1f
        out[3*i+0] = (r5 << 3) | (r5 >> 2)
        out[3*i+1] = (g6 << 2) | (g6 >> 4)
        out[3*i+2] = (b5 << 3) | (b5 >> 2)
    return bytes(out)


def write_bmp(path: Path, rgb: bytes, width: int, height: int):
    """Write a 24-bit BMP. BMP rows are bottom-up and padded to 4 bytes."""
    row_bytes = width * 3
    pad = (-row_bytes) % 4
    row_size = row_bytes + pad
    pixel_data = bytearray()
    # bottom-up
    for y in range(height - 1, -1, -1):
        row = rgb[y*row_bytes:(y+1)*row_bytes]
        # rgb -> bgr
        for x in range(width):
            r, g, b = row[3*x], row[3*x+1], row[3*x+2]
            pixel_data += bytes([b, g, r])
        pixel_data += b"\x00" * pad

    file_size = 14 + 40 + len(pixel_data)
    header = bytearray()
    header += b"BM"
    header += struct.pack("<I", file_size)
    header += b"\x00\x00\x00\x00"
    header += struct.pack("<I", 14 + 40)
    header += struct.pack("<I", 40)
    header += struct.pack("<i", width)
    header += struct.pack("<i", height)
    header += struct.pack("<H", 1)
    header += struct.pack("<H", 24)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", len(pixel_data))
    header += struct.pack("<i", 2835)
    header += struct.pack("<i", 2835)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", 0)
    path.write_bytes(bytes(header) + bytes(pixel_data))


def extract_from_pcap(pcap_path: Path) -> bytes:
    """Extract the 40 KiB logo from a USB pcap of the CPS read session.

    Requires tshark (and the ch340 dissector that pylunce provides) to be
    available. Returns a 40960-byte RGB565 LE buffer.
    """
    out = subprocess.check_output([
        "tshark", "-r", str(pcap_path),
        "-Y", "ch340.bulk.data_in",
        "-T", "fields", "-e", "ch340.bulk.data_in",
    ], text=True)
    stream = bytes.fromhex("".join(line.strip() for line in out.splitlines() if line.strip()))

    blocks: dict[int, bytes] = {}
    i = 0
    while i + 1035 <= len(stream):
        # Response header is 68 31 02 01 pct csum size_lo size_hi addr_lo addr_hi
        if stream[i] == 0x68 and stream[i+1] == 0x31 and stream[i+2] == 0x02:
            addr = stream[i+8] | (stream[i+9] << 8)
            payload = stream[i+10:i+10+BLOCK_SIZE]
            term = stream[i+10+BLOCK_SIZE]
            if len(payload) == BLOCK_SIZE and term == 0x10:
                blocks[addr] = payload
                i += 1035
                continue
        i += 1

    buf = bytearray(b"\xff" * TOTAL)
    for addr in range(START_BLOCK, END_BLOCK + 1):
        if addr in blocks:
            idx = addr - START_BLOCK
            buf[idx * BLOCK_SIZE:(idx + 1) * BLOCK_SIZE] = blocks[addr]
    return bytes(buf)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--raw", help=".raw file from hd1_replay.py")
    src.add_argument("--bin", help="40960-byte RGB565 LE buffer (pre-extracted)")
    src.add_argument("--pcap", help="USB pcap of a CPS logo read session")
    ap.add_argument("--out", required=True, help="output prefix")
    args = ap.parse_args()

    out_path = Path(args.out)
    completeness = None

    if args.raw:
        buf, completeness = reconstruct(Path(args.raw))
    elif args.bin:
        buf = Path(args.bin).read_bytes()
        if len(buf) != TOTAL:
            raise SystemExit(f"expected {TOTAL} bytes, got {len(buf)}")
    else:
        buf = extract_from_pcap(Path(args.pcap))

    bin_path = out_path.with_suffix(".rgb565")
    bin_path.write_bytes(buf)

    bmp_path = out_path.with_suffix(".bmp")
    rgb = rgb565_to_rgb888(buf, LOGO_W, LOGO_H)
    write_bmp(bmp_path, rgb, LOGO_W, LOGO_H)

    if completeness is not None:
        full = sum(1 for c in completeness if c == BLOCK_SIZE)
        partial = sum(1 for c in completeness if 0 < c < BLOCK_SIZE)
        missing = sum(1 for c in completeness if c == 0)
        total_bytes = sum(completeness)
        print(f"Blocks: {full} full, {partial} partial, {missing} missing")
        print(f"Coverage: {total_bytes}/{TOTAL} bytes ({100*total_bytes/TOTAL:.1f}%)")
    print(f"Wrote: {bin_path}")
    print(f"Wrote: {bmp_path}")


if __name__ == "__main__":
    main()
