"""Rebuild the channel-presence bitmap to match actual slot data, then write
the affected vfo_config blocks to the radio.

The bitmap is in vfo_config:
  bm1 = file 0x0200..0x0376 (375B)
  bm2 = file 0x0377..0x04ED (375B, identical to bm1)

Bit clear = populated; bit set = empty.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hd1_codeplug_write import HD1Writer

SRC = Path(__file__).parent / "output" / "cp_ai5qz_germany.bin"
OUT = Path(__file__).parent / "output" / "cp_ai5qz_germany_fixed.bin"

# vfo_config covers radio addr 0x2000..0x2300 in 128B chunks (7 blocks total)
VFO_BLOCKS = [0x2000, 0x2080, 0x2100, 0x2180, 0x2200, 0x2280, 0x2300]
VFO_FILE_BASE = 0x0200  # in EXPECTED/MEDIUM layouts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = bytearray(SRC.read_bytes())
    # Walk channel slots, determine which are populated
    slot_base = 0x4000 + (0x1BCC - 0x1B84) * 0x400 + 0x80  # = 0x16080
    populated = []
    for i in range(3000):
        off = slot_base + i * 176
        if off + 176 > len(data):
            break
        rec = data[off:off+176]
        name = rec[4:14].rstrip(b"\x00\xff")
        rx = rec[0x14:0x18]
        # "Populated" = has a name AND has a non-FF/00 frequency
        if name and rx not in (b"\xff\xff\xff\xff", b"\x00\x00\x00\x00"):
            populated.append(i)
    print(f"Populated slots: {len(populated)}")
    print(f"  first: {populated[:8]}")
    print(f"  last:  {populated[-8:]}")

    # Build new 375-byte bitmap: 1 bit per slot, bit clear = populated
    bm = bytearray(b"\xff" * 375)
    for slot in populated:
        bm[slot // 8] &= ~(1 << (slot % 8)) & 0xFF

    # Patch both bitmap copies
    bm1_off = VFO_FILE_BASE
    bm2_off = VFO_FILE_BASE + 375
    print(f"\nNew bitmap first 8: {bytes(bm[:8]).hex()}")
    print(f"Old bm1 first 8:    {bytes(data[bm1_off:bm1_off+8]).hex()}")
    data[bm1_off:bm1_off+375] = bm
    data[bm2_off:bm2_off+375] = bm

    OUT.write_bytes(bytes(data))
    print(f"\nWrote fixed bin: {OUT.name}")

    # Identify which vfo_config blocks changed
    src_data = SRC.read_bytes()
    changed = []
    for addr in VFO_BLOCKS:
        offset = (addr - 0x2000) + VFO_FILE_BASE
        old = src_data[offset:offset + 128]
        new = bytes(data[offset:offset + 128])
        if old != new:
            changed.append((addr, new))
    print(f"\nvfo_config blocks to write: {[hex(a) for a, _ in changed]}")

    if args.dry_run:
        print("[dry-run] not writing")
        return

    print(f"\n>>> Writing to {args.port} <<<")
    w = HD1Writer(args.port, timeout=2.0, trace_fp=sys.stderr)

    # CPS write-mode handshake: SLC7000 -> radio replies with model ID (BJDR380).
    # Without this, the radio kills the session after a few writes.
    w.ser.reset_input_buffer()
    w.ser.write(b"SLC7000")
    w.ser.flush()
    time.sleep(0.2)
    r1 = w.ser.read(w.ser.in_waiting or 64)
    print(f"SLC7000 #1 reply ({len(r1)}B): {r1.hex()}")

    w.ser.reset_input_buffer()
    w.ser.write(b"SLC7000")
    w.ser.flush()
    time.sleep(0.2)
    r2 = w.ser.read(w.ser.in_waiting or 64)
    print(f"SLC7000 #2 reply ({len(r2)}B): {r2!r}")
    if b"BJDR" not in r2 and b"HD" not in r2:
        print("WARNING: radio didn't reply with model ID; aborting")
        w.close()
        return

    for i, (addr, chunk) in enumerate(changed):
        pct = int(((i + 1) / len(changed)) * 100)
        ack, status = w.write_chunk_0f(pct, addr, chunk)
        print(f"  [{i+1}/{len(changed)}] addr 0x{addr:04x}: {status}")
        if status != "OK":
            print(f"    ack: {ack.hex(' ')}")
            print("ABORT (not sending END)")
            w.close()
            return
        time.sleep(0.1)

    # Send END to terminate session (radio reboots and commits)
    print("\nSending END to commit + reboot radio...")
    w.ser.reset_input_buffer()
    w.ser.write(b"END")
    w.ser.flush()
    time.sleep(0.5)
    w.close()
    print(f"Done. Should see {len(populated)} channels after reboot.")


if __name__ == "__main__":
    main()
