#!/usr/bin/env python3
"""Send SLC7000 handshake + clock-set command to the HD2.

Usage:
    .venv/bin/python3 hd1_set_clock.py --port /dev/cu.usbserial-2140
    .venv/bin/python3 hd1_set_clock.py --port /dev/cu.usbserial-2140 --future 1y
"""
from __future__ import annotations

import argparse
import struct
import time
from datetime import datetime, timedelta

import serial


def drain_boot_log(ser, quiet_for=1.0, max_wait=10.0):
    drained = bytearray()
    last = time.monotonic()
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        ser.timeout = 0.1
        chunk = ser.read(4096)
        if chunk:
            drained.extend(chunk)
            last = time.monotonic()
        elif time.monotonic() - last >= quiet_for:
            break
    if drained:
        print(f"Drained {len(drained)} bytes of boot log")
    ser.reset_input_buffer()


def txrx(ser, data: bytes, expect_len: int, settle: float = 0.3) -> bytes:
    ser.reset_input_buffer()
    ser.write(data)
    ser.flush()
    tx_time = (len(data) * 10) / 119200.0
    rx_time = (expect_len * 10) / 119200.0
    time.sleep(tx_time + rx_time + settle)
    buf = ser.read(ser.in_waiting or expect_len)
    return bytes(buf)


def build_clock_frame(dt: datetime) -> bytes:
    """Build the 16-byte clock-set frame per protocol.md."""
    return struct.pack("<BBBHBBBBBBBBBBB",
        0x68,               # sync
        0x0F,               # command family
        0x05,               # subcommand: SET CLOCK
        dt.year,            # uint16 LE year (2 bytes)
        dt.month,           # month
        0x00,               # pad
        dt.day,             # day
        0x00,               # pad
        dt.hour,            # hour
        0x00,               # pad
        dt.minute,          # minute
        0x00,               # pad
        dt.second,          # second
        0x00,               # pad
        0x10,               # terminator
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--future", default="1y",
                    help="How far in the future (e.g. '1y', '6m', '1d'). Default: 1y")
    ap.add_argument("--no-slc", action="store_true",
                    help="Skip SLC7000 handshake, send clock set directly")
    args = ap.parse_args()

    # Parse --future
    val = args.future
    if val.endswith("y"):
        delta = timedelta(days=int(val[:-1]) * 365)
    elif val.endswith("m"):
        delta = timedelta(days=int(val[:-1]) * 30)
    elif val.endswith("d"):
        delta = timedelta(days=int(val[:-1]))
    else:
        delta = timedelta(days=365)

    target = datetime.now() + delta

    ser = serial.Serial(
        port=args.port,
        baudrate=119200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        rtscts=False, dsrdtr=False,
        timeout=3.0, write_timeout=3.0,
        exclusive=True,
    )
    ser.rts = True
    ser.dtr = True
    time.sleep(0.2)

    try:
        drain_boot_log(ser)

        # Step 1: SLC7000 handshake
        print("Sending SLC7000...")
        resp = txrx(ser, b"SLC7000", expect_len=7, settle=0.3)
        print(f"  Response ({len(resp)}B): {resp!r}")
        if b"BJDR" not in resp:
            print("WARNING: expected BJDR380, got something else")

        # Step 2: Clock set
        frame = build_clock_frame(target)
        print(f"\nSetting clock to: {target.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Frame: {frame.hex()}")
        resp = txrx(ser, frame, expect_len=16, settle=0.3)
        print(f"  Response ({len(resp)}B): {resp.hex()}")

        if resp == frame:
            print("\n  Radio echoed frame back verbatim - SUCCESS")
        elif len(resp) == 16:
            print("\n  Got 16 bytes back (expected echo)")
            for i in range(16):
                if i < len(resp) and resp[i] != frame[i]:
                    print(f"    byte {i}: sent 0x{frame[i]:02x}, got 0x{resp[i]:02x}")
        else:
            print(f"\n  Unexpected response length ({len(resp)} != 16)")

        print("\nDone. (Not sending END - radio stays running)")

    finally:
        ser.close()


if __name__ == "__main__":
    main()
