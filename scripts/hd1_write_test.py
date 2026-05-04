#!/usr/bin/env python3
"""
hd1_write_test.py - Test b1=0x0F small-setting write protocol.

Connects fresh, reads 4 small-setting chunks to confirm reads work,
then attempts one b1=0x0F write at addr 0x0000 with 0xFF data and
prints the ACK (or timeout).

Usage:
    python3 hd1_write_test.py --port /dev/ttyUSB0
"""

import argparse
import sys
import time
import serial

SYNC = 0x68
TERMINATOR = 0x10
BAUD = 120000


def hexdump(data: bytes, n: int = 32) -> str:
    head = data[:n]
    return ' '.join(f'{b:02x}' for b in head) + (' ...' if len(data) > n else '')


def drain_boot(ser, quiet=1.0, max_wait=10.0):
    drained = bytearray()
    last = time.monotonic()
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        ser.timeout = 0.1
        chunk = ser.read(4096)
        if chunk:
            drained.extend(chunk)
            last = time.monotonic()
        elif time.monotonic() - last >= quiet:
            break
    ser.reset_input_buffer()
    if drained:
        print(f"  drained {len(drained)} boot bytes")


def get_ver(ser) -> str:
    ser.reset_input_buffer()
    ser.write(b'GetVer')
    ser.flush()
    time.sleep(0.3)
    buf = bytes(ser.read(ser.in_waiting or 256))
    return buf.decode('ascii', errors='replace').strip('\x00').strip()


def checksum_0f(addr: int, size: int) -> int:
    addr_lo = addr & 0xFF
    addr_hi = (addr >> 8) & 0xFF
    return (0xFF - (0x10 + addr_hi + ((addr_lo + size - 1) >> 7))) & 0xFF


def read_chunk(ser, addr: int, size: int = 0x80, pct: int = 0) -> bytes:
    """Send a b1=0x0F read command and return the payload."""
    csum = checksum_0f(addr, size)
    cmd = bytes([SYNC, 0x0F, 0x00, 0x01, pct, csum, size & 0xFF, (size >> 8) & 0xFF,
                 addr & 0xFF, (addr >> 8) & 0xFF, TERMINATOR])
    expected = 10 + size + 1

    ser.reset_input_buffer()
    ser.write(cmd)
    ser.flush()

    tx_time = (len(cmd) * 10) / BAUD
    rx_time = (expected * 10) / BAUD
    time.sleep(tx_time + rx_time + 0.15)

    buf = bytearray()
    deadline = time.monotonic() + 2.0
    while len(buf) < expected and time.monotonic() < deadline:
        pending = ser.in_waiting
        if pending:
            buf.extend(ser.read(pending))
        else:
            time.sleep(0.02)

    print(f"  read  addr=0x{addr:04x} got {len(buf)}/{expected}  hdr={bytes(buf[:10]).hex()}")
    return bytes(buf[10:10+size]) if len(buf) >= expected else b''


def write_small(ser, addr: int, data: bytes, pct: int = 0) -> bytes:
    """Send a b1=0x0F write command and return the ACK."""
    assert len(data) == 128, f"data must be 128 bytes, got {len(data)}"
    # 10 header + 128 data + 1 terminator = 139 bytes
    cmd = bytes([SYNC, 0x0F, 0x01, 0x01, pct, 0x00, 0x80, 0x00,
                 addr & 0xFF, (addr >> 8) & 0xFF]) + data + bytes([TERMINATOR])
    assert len(cmd) == 139, f"cmd length wrong: {len(cmd)}"

    ser.reset_input_buffer()
    ser.write(cmd)
    ser.flush()

    tx_time = (len(cmd) * 10) / BAUD
    time.sleep(tx_time + 0.30)   # 300ms flash write margin

    buf = bytearray()
    deadline = time.monotonic() + 3.0
    while len(buf) < 11 and time.monotonic() < deadline:
        pending = ser.in_waiting
        if pending:
            buf.extend(ser.read(pending))
        else:
            time.sleep(0.02)

    return bytes(buf)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', default='/dev/ttyUSB0')
    ap.add_argument('--skip-reads', action='store_true',
                    help='Skip the probe reads and write immediately')
    args = ap.parse_args()

    ser = serial.Serial(
        port=args.port, baudrate=BAUD,
        bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
        rtscts=False, dsrdtr=False, exclusive=True,
    )
    ser.rts = True
    ser.dtr = True
    time.sleep(0.2)

    print("Draining boot log...")
    drain_boot(ser)

    ver = get_ver(ser)
    print(f"Radio: {ver}")
    if not ver or 'HD' not in ver:
        print("ERROR: GetVer failed", file=sys.stderr)
        sys.exit(1)

    if not args.skip_reads:
        print("\nReading 4 small-setting chunks (probe reads)...")
        for addr in [0x0000, 0x0080, 0x0100, 0x0180]:
            read_chunk(ser, addr, 0x80)

    # Now attempt a write at addr 0x0000 with 0xFF data (harmless — same as blank flash)
    print(f"\nAttempting b1=0x0F write at addr 0x0000 (128x 0xFF)...")
    data = bytes([0xFF] * 128)
    ack = write_small(ser, 0x0000, data, pct=0)

    if len(ack) >= 11:
        print(f"  ACK ({len(ack)} bytes): {hexdump(ack)}")
        # Expected: 68 0f 01 01 00 00 80 00 00 00 10
        if ack[0] == SYNC and ack[1] == 0x0F and ack[-1] == TERMINATOR:
            print("  WRITE OK - radio acknowledged!")
        else:
            print("  WARNING: unexpected ACK bytes")
    elif len(ack) > 0:
        print(f"  SHORT ACK ({len(ack)} bytes): {hexdump(ack)}")
    else:
        print("  TIMEOUT - no ACK received (0 bytes)")

    ser.close()


if __name__ == '__main__':
    main()
