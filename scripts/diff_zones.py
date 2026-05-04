"""Diff post-CPS dump against pre-CPS baseline to locate zone storage.

Usage:
    mise exec -- python3 diff_zones.py <pre_bin> <post_bin>

Expected CPS state in post:
    TestZone1 -> channel 4 only        (channel index 3)
    TestZone2 -> channels 3, 5, 7      (channel indices 2, 4, 6)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from codeplug import Codeplug, REGIONS


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    pre = Path(sys.argv[1]).read_bytes()
    post = Path(sys.argv[2]).read_bytes()
    assert len(pre) == len(post), f"size mismatch: {len(pre)} vs {len(post)}"

    # Find region for table_21dx
    t21 = next(r for r in REGIONS if r[0] == "table_21dx")
    name, rbase, fbase, fsize, stride, blockwise = t21
    print(f"table_21dx: file 0x{fbase:x}..0x{fbase+fsize:x} ({fsize} bytes)")
    print(f"            radio block 0x{rbase:x}..0x{rbase + fsize//0x400:x}")
    print()

    # Diff entire file
    diffs = [(i, pre[i], post[i]) for i in range(len(pre)) if pre[i] != post[i]]
    print(f"Total bytes changed: {len(diffs)}")

    # Group diffs by region
    by_region = {}
    for name_, rbase_, fbase_, fsize_, _, _ in REGIONS:
        in_region = [(i, p, q) for i, p, q in diffs if fbase_ <= i < fbase_ + fsize_]
        if in_region:
            by_region[name_] = in_region

    print("\nDiffs per region:")
    for region, items in by_region.items():
        print(f"  {region:<14}: {len(items)} bytes")

    # Show grouped runs (consecutive byte diffs)
    print("\nGrouped runs (region, file_off, length):")
    runs = []
    if diffs:
        run_start = diffs[0][0]
        prev = diffs[0][0]
        for i, _, _ in diffs[1:]:
            if i != prev + 1:
                runs.append((run_start, prev - run_start + 1))
                run_start = i
            prev = i
        runs.append((run_start, prev - run_start + 1))

    for start, length in runs:
        # Find which region
        region = "?"
        for name_, _, fbase_, fsize_, _, _ in REGIONS:
            if fbase_ <= start < fbase_ + fsize_:
                region = name_
                break
        print(f"  {region:<14} file_off=0x{start:06x} len={length}  "
              f"pre={pre[start:start+min(length, 24)].hex()}  "
              f"post={post[start:start+min(length, 24)].hex()}")

    # Check zones: parse both
    print("\nParsed zones:")
    cp_pre = Codeplug.from_bin(pre)
    cp_post = Codeplug.from_bin(post)
    print(f"  PRE:  {len(cp_pre.zones)} zones")
    for z in cp_pre.zones:
        print(f"    {z.name!r}: {len(z.channels)} ch {z.channels[:8]} @0x{z._file_offset:x}")
    print(f"  POST: {len(cp_post.zones)} zones")
    for z in cp_post.zones:
        print(f"    {z.name!r}: {len(z.channels)} ch {z.channels[:8]} @0x{z._file_offset:x}")


if __name__ == "__main__":
    main()
