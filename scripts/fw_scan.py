#!/usr/bin/env python3
"""
Raw CK803S firmware scanner — no Ghidra required.

Usage:
    python3 fw_scan.py [firmware.bin]

Scans the raw .bin for:
  - Vector table pointers
  - Infinite loops (br . = 0x07FE)
  - Function prologues (push r15 = 0xDC20)
  - ASCII strings
  - Repeating/padding regions
"""

import sys
import struct
from pathlib import Path
from collections import Counter

FW_PATH   = Path(__file__).parent.parent / "firmware" / "HD-GPS-HD2PA-C7000-V2.1.3-GPS.raw.bin"
BASE_ADDR = 0x03700000


def load(path):
    data = path.read_bytes()
    print(f"Loaded {path.name}: {len(data):,} bytes (0x{len(data):x})")
    return data


def u16le(data, off): return struct.unpack_from("<H", data, off)[0]
def u32le(data, off): return struct.unpack_from("<I", data, off)[0]


# ── scanners ─────────────────────────────────────────────────────────────────

def dump_vectors(data):
    """Print non-zero vector table entries starting at fw+0x80."""
    print("\n=== Vector Table (fw+0x80) ===")
    for i in range(64):
        off = 0x80 + i * 4
        if off + 4 > len(data):
            break
        val = u32le(data, off)
        if val:
            print(f"  vec[{i:2d}]  file+0x{off:04x}  ->  0x{val:08x}")


def find_infinite_loops(data):
    """Scan for 0xFE07 halfwords (CK803S 'br .' = little-endian 0x07FE)."""
    hits = [i for i in range(0, len(data) - 1, 2) if u16le(data, i) == 0x07FE]
    print(f"\n=== Infinite Loops (0x07FE br .) — {len(hits)} total ===")
    for h in hits[:30]:
        print(f"  file+0x{h:06x}  ->  RAM 0x{BASE_ADDR + h:08x}")
    if len(hits) > 30:
        print(f"  ... ({len(hits) - 30} more)")
    return hits


def find_prologues(data):
    """
    Scan for 16-bit 'push r15' = 0xDC20  (saves link register = function start).
    Also catch 0xDExx (push {r4-r15} variants).
    """
    hits_dc20 = []
    hits_de   = []
    for i in range(0, len(data) - 1, 2):
        hw = u16le(data, i)
        if hw == 0xDC20:
            hits_dc20.append(i)
        elif (hw >> 8) == 0xDE:
            hits_de.append(i)

    print(f"\n=== Function Prologues ===")
    print(f"  push r15 (0xDC20): {len(hits_dc20)}")
    for h in hits_dc20[:20]:
        print(f"    file+0x{h:06x}  RAM 0x{BASE_ADDR + h:08x}")
    print(f"  push r4-r15 (0xDExx): {len(hits_de)}")
    for h in hits_de[:20]:
        hw = u16le(data, h)
        print(f"    file+0x{h:06x}  RAM 0x{BASE_ADDR + h:08x}  (0x{hw:04x})")

    return hits_dc20, hits_de


def find_strings(data, min_len=6):
    """Scan for null-terminated printable ASCII strings."""
    strings = []
    i = 0
    while i < len(data):
        if 0x20 <= data[i] < 0x7f:
            j = i
            while j < len(data) and 0x20 <= data[j] < 0x7f:
                j += 1
            # require null terminator to filter out code false positives
            if j - i >= min_len and j < len(data) and data[j] == 0x00:
                strings.append((i, data[i:j].decode("ascii")))
            i = j + 1
        else:
            i += 1

    print(f"\n=== Null-terminated Strings (min {min_len}) — {len(strings)} total ===")
    for off, s in strings[:80]:
        print(f"  file+0x{off:06x}  RAM 0x{BASE_ADDR + off:08x}  {s!r}")
    if len(strings) > 80:
        print(f"  ... ({len(strings) - 80} more)")
    return strings


def find_padding(data, block=256):
    """Identify large regions of 0x00 or 0xFF (likely flash erase boundaries)."""
    print("\n=== Padding / Erased Regions ===")
    i = 0
    while i < len(data):
        b = data[i]
        if b in (0x00, 0xFF):
            j = i
            while j < len(data) and data[j] == b:
                j += 1
            if j - i >= block:
                print(f"  file+0x{i:06x} - 0x{j:06x}  ({j-i:,} bytes of 0x{b:02x})")
            i = j
        else:
            i += 1


def byte_entropy(data, block=4096):
    """Print rough entropy map (high = code/compressed, low = padding/data)."""
    import math
    print("\n=== Block Entropy (4KB blocks) ===")
    for start in range(0, len(data), block):
        chunk = data[start:start + block]
        if not chunk:
            break
        cnt   = Counter(chunk)
        total = len(chunk)
        ent   = -sum((c / total) * math.log2(c / total) for c in cnt.values() if c)
        bar   = "#" * int(ent)
        print(f"  file+0x{start:06x}  {ent:.2f} bits  {bar}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else FW_PATH
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)

    data = load(path)
    dump_vectors(data)
    find_infinite_loops(data)
    find_prologues(data)
    find_strings(data)
    find_padding(data)
    byte_entropy(data)


if __name__ == "__main__":
    main()
