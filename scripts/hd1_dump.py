#!/usr/bin/env python3
"""
hd1_dump.py - Codeplug dumper for the Ailunce HD1 / HD2 DMR radio.

Protocol reverse-engineered from USB pcaps of the official Windows CPS
(see ../pylunce/dump/hd2_read.pcapng).

Frame (11 bytes, host -> radio):
    68 0f 00 01 [percent] [csum] [size_lo] [size_hi] [addr_lo] [addr_hi] 10

Where:
    csum = 0xff - (0x10 + addr_hi + ((addr_lo + size - 1) >> 7))   mod 0x100
    size is normally 0x80 (128) for codeplug reads; byte_hi is 0 except
    for the special "read serial" probe.

Response (10 + size + 1 bytes, radio -> host):
    [echo of first 10 bytes of cmd] [size bytes data] [0x10]
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import serial

SYNC = 0x68
TERMINATOR = 0x10


def csum(addr: int, size: int, b1: int = 0x0F) -> int:
    """Command checksum. Two formulas, chosen by protocol family:
      b1=0x0F (128-byte settings reads): derived from addr_hi + (addr_lo+size-1)>>7
      b1=0x31 (1024-byte block reads):    derived from (addr - 0x88) >> 8
    Both verified against the official CPS pcap.
    """
    if b1 == 0x31:
        return (0xFF - (0x15 + ((addr - 0x88) >> 8))) & 0xFF
    addr_lo = addr & 0xFF
    addr_hi = (addr >> 8) & 0xFF
    return (0xFF - (0x10 + addr_hi + ((addr_lo + size - 1) >> 7))) & 0xFF


def build_cmd(b1: int, addr: int, size: int, *, percent: int = 0, b7: int = None) -> bytes:
    if not 0 <= addr <= 0xFFFF:
        raise ValueError(f"addr out of range: 0x{addr:x}")
    if not 1 <= size <= 0xFFFF:
        raise ValueError(f"size out of range: {size}")
    # byte 7 is the high byte of size unless caller overrides (some probes do).
    size_hi = b7 if b7 is not None else (size >> 8) & 0xFF
    return bytes([
        SYNC,
        b1,
        0x00,
        0x01,
        percent & 0xFF,
        csum(addr, size, b1),
        size & 0xFF,
        size_hi & 0xFF,
        addr & 0xFF,
        (addr >> 8) & 0xFF,
        TERMINATOR,
    ])


def hexdump(data: bytes, n: int = 32) -> str:
    head = data[:n]
    return f"{' '.join(f'{b:02x}' for b in head)}{' ...' if len(data) > n else ''}"


# Codeplug regions read by the official HD2 CPS, in order.
# (start_addr, end_addr_inclusive, chunk_size, b1)
#
# Two protocol families are used:
#   b1=0x0F size=0x80  — small 128-byte "settings" reads (header, VFO, contacts,
#                         group lists, radio IDs)
#   b1=0x31 size=0x0400 — 1024-byte block reads for the main data (channels,
#                         zones, etc.). Addresses are block numbers.
#
# Regions derived from pylunce/dump/hd2_read.pcapng.
# (name, start, end_inclusive, chunk_size, b1)
CODEPLUG_REGIONS = [
    # Small settings reads
    ("header",     0x0000, 0x0180, 0x80, 0x0F),
    ("vfo_config", 0x2000, 0x2300, 0x80, 0x0F),
    ("settings",   0x2900, 0x5F00, 0x80, 0x0F),
    # Large block reads (1024 bytes each, address is a block index)
    ("addr_book",  0x0000, 0x0000, 0x0400, 0x31),
    ("channels",   0x1B84, 0x1DCF, 0x0400, 0x31),
    ("table_1dfx", 0x1DF8, 0x1E03, 0x0400, 0x31),
    ("table_21dx", 0x21D8, 0x22FF, 0x0400, 0x31),
    ("table_4000", 0x4000, 0x4000, 0x0400, 0x31),
    ("table_428x", 0x4280, 0x4282, 0x0400, 0x31),
]

REGION_NAMES = [r[0] for r in CODEPLUG_REGIONS]


# Addresses outside CODEPLUG_REGIONS that are known/suspected to be readable
# but live outside the mapped codeplug. Read once each (no walking) when
# --include-probes is set; each result lands in <out>.probe_<name>.bin so the
# main .bin stays a clean codeplug image.
# (name, b1, addr, size, b7)
PROBE_REGIONS = [
    ("header_0d", 0x0D, 0x0000, 0x10, 0x00),  # b1=0x0D header probe (different command class)
    ("e000",      0x0F, 0xE000, 0x80, 0x00),  # unit serial number + manufacture date
    ("e800",      0x0F, 0xE800, 0x80, 0x00),  # CPS reads 7 B here; try a full chunk
    ("config",    0x0F, 0x2950, 0x40, 0x00),  # inside settings region; captured for reference
]


class HD1:
    def __init__(self, port: str, *, timeout: float, trace_fp=None):
        self.trace_fp = trace_fp
        self.ser = serial.Serial(
            port=port,
            baudrate=120000,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            rtscts=False, dsrdtr=False,
            timeout=timeout, write_timeout=timeout,
            exclusive=True,
        )
        self.ser.rts = True
        self.ser.dtr = True
        time.sleep(0.2)  # let RTS/DTR settle
        self._drain_boot_log()

    def _drain_boot_log(self, quiet_for: float = 1.0, max_wait: float = 10.0):
        """Drain the radio's boot debug log until the port is quiet."""
        drained = bytearray()
        last = time.monotonic()
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            self.ser.timeout = 0.1
            chunk = self.ser.read(4096)
            if chunk:
                drained.extend(chunk)
                last = time.monotonic()
            elif time.monotonic() - last >= quiet_for:
                break
        if drained:
            self.trace(f"DRAIN  {len(drained)} bytes of boot log")
        self.ser.reset_input_buffer()

    def trace(self, msg: str):
        if self.trace_fp:
            self.trace_fp.write(msg + "\n")
            self.trace_fp.flush()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def get_version(self) -> bytes:
        self.ser.reset_input_buffer()
        self.ser.write(b"GetVer")
        self.ser.flush()
        time.sleep(0.3)  # let radio fully send response before reading
        self.ser.timeout = 0.5
        buf = bytes(self.ser.read(self.ser.in_waiting or 256))
        self.trace("TX GetVer")
        self.trace(f"RX GetVer  {len(buf)} bytes  {hexdump(buf)}")
        return buf

    def read_chunk(self, b1: int, addr: int, size: int, *, percent: int = 0,
                   b7: int | None = None, retries: int = 3) -> tuple[bytes, str]:
        cmd = build_cmd(b1, addr, size, percent=percent, b7=b7)
        expected = 10 + size + 1
        timeout = self.ser.timeout
        buf = bytearray()

        # Estimate transmission time at 119200 baud (~12 KB/s) + slack
        transmit_time = (expected * 10) / 119200.0 + 0.1

        for attempt in range(retries + 1):
            self.ser.reset_input_buffer()
            self.ser.write(cmd)
            self.ser.flush()
            self.trace(f"TX[{attempt}] b1=0x{b1:02x} addr=0x{addr:04x} size={size:>3} pct={percent:>3}  {hexdump(cmd)}")

            # Wait long enough for the radio to finish sending, then read
            # everything available at once. Reading byte-by-byte while bytes
            # are still arriving causes corruption on macOS at 119200 baud.
            time.sleep(transmit_time)

            buf = bytearray()
            deadline = time.monotonic() + timeout
            while True:
                pending = self.ser.in_waiting
                if pending:
                    buf.extend(self.ser.read(pending))
                if len(buf) >= expected:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)

            self.trace(f"RX[{attempt}] b1=0x{b1:02x} addr=0x{addr:04x}  got {len(buf)}/{expected}  {hexdump(bytes(buf))}")

            if len(buf) == expected:
                break  # full response, stop retrying

        self.ser.timeout = timeout

        if len(buf) == 0:
            return b"", "TIMEOUT"
        if len(buf) < expected:
            return bytes(buf), f"SHORT({len(buf)}/{expected})"
        if buf[-1] != TERMINATOR:
            return bytes(buf), f"BAD_TERM(0x{buf[-1]:02x})"
        # Echo: codeplug (0x0f) reads echo cmd[:10] exactly (byte 2 = 0x00).
        # Logo (0x31) reads echo with byte 2 rewritten to 0x02.
        # Accept either form.
        echo = bytes(buf[:10])
        if echo != cmd[:10] and echo != cmd[:2] + b"\x02" + cmd[3:10]:
            return bytes(buf), f"BAD_ECHO({echo.hex()})"
        return bytes(buf), "OK"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port",
                    help="Serial device. macOS: /dev/cu.usbserial-*")
    ap.add_argument("--out", help="Output prefix")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--skip-setup", action="store_true",
                    help="Skip the header/serial/config probe commands")
    ap.add_argument("--regions", default="all",
                    help=("Comma-separated region names to dump (default: all). "
                          f"Available: {','.join(REGION_NAMES)}"))
    ap.add_argument("--addr-range",
                    help=("Restrict each selected region to [START,END] (inclusive), "
                          "clipped to the region's own bounds. "
                          "Format: '0x1BCC' or '0x1BCC-0x1BCF' (hex or decimal)."))
    ap.add_argument("--list-regions", action="store_true",
                    help="List available regions and exit")
    ap.add_argument("--include-probes", action="store_true",
                    help=("Also read PROBE_REGIONS (addresses outside the mapped "
                          "codeplug, e.g. 0xE800) and write each to "
                          "<out>.probe_<name>.bin"))
    args = ap.parse_args()

    if args.list_regions:
        print(f"{'name':<12}  {'start':>6}  {'end':>6}  {'chunk':>5}  {'b1':>4}")
        for name, start, end, chunk, b1 in CODEPLUG_REGIONS:
            print(f"{name:<12}  0x{start:04x}  0x{end:04x}  0x{chunk:03x}  0x{b1:02x}")
        return

    if not args.port or not args.out:
        ap.error("--port and --out are required (use --list-regions to see region names)")

    if args.regions == "all":
        selected = CODEPLUG_REGIONS
    else:
        wanted = [r.strip() for r in args.regions.split(",") if r.strip()]
        unknown = [r for r in wanted if r not in REGION_NAMES]
        if unknown:
            ap.error(f"unknown region(s): {unknown}. known: {REGION_NAMES}")
        selected = [r for r in CODEPLUG_REGIONS if r[0] in wanted]
        print(f"Selected regions: {[r[0] for r in selected]}")

    if args.addr_range:
        parts = args.addr_range.split("-", 1)
        try:
            lo = int(parts[0], 0)
            hi = int(parts[1], 0) if len(parts) == 2 else lo
        except ValueError:
            ap.error(f"bad --addr-range: {args.addr_range!r}")
        clipped = []
        for name, start, end, chunk, b1 in selected:
            s = max(start, lo)
            e = min(end, hi)
            if s <= e:
                clipped.append((name, s, e, chunk, b1))
        if not clipped:
            ap.error(f"--addr-range 0x{lo:x}..0x{hi:x} excludes every selected region")
        selected = clipped
        print(f"Addr range: 0x{lo:x}..0x{hi:x} -> {[(n, hex(s), hex(e)) for n,s,e,_,_ in selected]}")

    out_path = Path(args.out)
    log_path = out_path.with_suffix(".log")
    bin_path = out_path.with_suffix(".bin")
    raw_path = out_path.with_suffix(".raw")

    trace_fp = open(log_path, "w") if args.trace else None
    if trace_fp:
        print(f"Trace log:    {log_path}")
    bin_fp = open(bin_path, "wb")
    raw_fp = open(raw_path, "wb")
    print(f"Codeplug bin: {bin_path}")
    print(f"Raw frames:   {raw_path}")

    hd1 = HD1(port=args.port, timeout=args.timeout, trace_fp=trace_fp)

    interrupted = {"flag": False}

    def handle_sigint(signum, frame):
        interrupted["flag"] = True
        print("\nInterrupted, flushing partial image...", file=sys.stderr)
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        ver = hd1.get_version()
        if not ver or b"HD" not in ver:
            print("ERROR: GetVer failed - radio not responding.", file=sys.stderr)
            sys.exit(2)
        printable = bytes(b if 32 <= b < 127 else 0x2e for b in ver).decode("ascii", errors="replace")
        print(f"Radio:        {printable.rstrip('.')}")

        # Setup commands (mirrors the official CPS).
        if not args.skip_setup:
            print("Setup probes...")
            for label, b1, addr, size, b7 in [
                ("header",  0x0D, 0x0000, 0x10, 0x00),
                ("serial",  0x0F, 0xE800, 0x07, 0x00),
                ("config",  0x0F, 0x2950, 0x40, 0x00),
            ]:
                resp, status = hd1.read_chunk(b1, addr, size, percent=0, b7=b7)
                raw_fp.write(b"SETUP" + label.encode().ljust(8) + len(resp).to_bytes(4,"little") + resp)
                raw_fp.flush()
                if status != "OK":
                    print(f"  {label}: {status}", file=sys.stderr)
                else:
                    data = resp[10:-1]
                    printable = bytes(b if 32 <= b < 127 else 0x2e for b in data).decode("ascii", errors="replace")
                    print(f"  {label}: {len(data)} bytes  {hexdump(data, 16)}  ({printable!r})")

        # Walk codeplug regions.
        ok = 0
        bad = 0
        last_addr = None
        for region_idx, (name, start, end, chunk, b1) in enumerate(selected):
            # For b1=0x0F the addr is a byte address and stride = chunk (128).
            # For b1=0x31 the addr is a 1024-byte BLOCK index, stride = 1.
            step = 1 if b1 == 0x31 else chunk
            print(f"Region {region_idx} {name}: 0x{start:04x}..0x{end:04x} "
                  f"chunk=0x{chunk:x} step={step} b1=0x{b1:02x}")
            addr = start
            n = 0
            while addr <= end:
                if interrupted["flag"]:
                    break
                # Crude percent: progress within this region.
                pct = min(100, round((addr - start) * 100 / max(1, end - start)))
                resp, status = hd1.read_chunk(b1, addr, chunk, percent=pct)
                raw_fp.write(b"DATA " + addr.to_bytes(4,"little") + len(resp).to_bytes(4,"little") + resp)
                raw_fp.flush()

                if status == "OK":
                    bin_fp.write(resp[10:-1])
                    bin_fp.flush()
                    ok += 1
                    last_addr = addr
                else:
                    bad += 1
                    print(f"  0x{addr:04x}: {status}", file=sys.stderr)
                    # Save zero-fill for the gap so file offsets stay aligned.
                    bin_fp.write(b"\x00" * chunk)

                if n % 8 == 0:
                    print(f"  0x{addr:04x} pct={pct:>3}  ok={ok} bad={bad}", file=sys.stderr)

                addr += step
                n += 1
            if interrupted["flag"]:
                break

        if args.include_probes and not interrupted["flag"]:
            print("Probe regions...")
            for name, b1, addr, size, b7 in PROBE_REGIONS:
                resp, status = hd1.read_chunk(b1, addr, size, percent=0, b7=b7)
                raw_fp.write(b"PROBE" + name.encode().ljust(12)
                             + len(resp).to_bytes(4, "little") + resp)
                raw_fp.flush()
                if status != "OK":
                    print(f"  {name} 0x{addr:04x} b1=0x{b1:02x}: {status}",
                          file=sys.stderr)
                    continue
                data = resp[10:-1]
                probe_path = out_path.parent / f"{out_path.stem}.probe_{name}.bin"
                probe_path.write_bytes(data)
                printable = bytes(b if 32 <= b < 127 else 0x2e for b in data
                                  ).decode("ascii", errors="replace")
                print(f"  {name} 0x{addr:04x} b1=0x{b1:02x}: {len(data)} bytes "
                      f"-> {probe_path.name}")
                print(f"    {hexdump(data, 32)}  ({printable!r})")

        print()
        print(f"  ok:        {ok}")
        print(f"  bad:       {bad}")
        if last_addr is not None:
            print(f"  last good: 0x{last_addr:04x}")
    finally:
        hd1.close()
        bin_fp.close()
        raw_fp.close()
        if trace_fp:
            trace_fp.close()


if __name__ == "__main__":
    main()
