"""Apply small UI tweaks and write the diff.

Changes (radio settings):
  - Voice prompts: OFF  (clear bit 5 @ 0x2971)
  - Night Mode:    ON   (clear bit 3 @ 0x2978)
  - CH-Mode:       Name (bit 5 set + bit 0 clear @ 0x2978; enum {bit5,bit0}: 00=Freq, 01=CH, 10=Name)
  - Key Beep:      OFF  (clear bit 7 @ 0x2977)
"""
from pathlib import Path

SRC = Path(__file__).parent / "output" / "cp_ai5qz_germany_fixed.bin"
DST = Path(__file__).parent / "output" / "cp_ai5qz_germany_v2.bin"

# Settings region maps radio 0x2900 -> file 0x0580
F_2971 = 0x0580 + (0x2971 - 0x2900)  # 0x05F1
F_2977 = 0x0580 + (0x2977 - 0x2900)  # 0x05F7
F_2978 = 0x0580 + (0x2978 - 0x2900)  # 0x05F8


def chmode(b):
    return {0b00: "Freq", 0b01: "CH", 0b10: "Name"}.get(((b >> 5) & 1) << 1 | (b & 1), "?")


def main():
    data = bytearray(SRC.read_bytes())

    old_2971 = data[F_2971]
    old_2977 = data[F_2977]
    old_2978 = data[F_2978]

    # Voice OFF: clear bit 5 (0x20)
    data[F_2971] = old_2971 & ~0x20

    # Key Beep OFF: clear bit 7 (0x80)
    data[F_2977] = old_2977 & ~0x80

    # Night Mode ON: clear bit 3 (0x08)
    # CH-Mode = Name: set bit 5 (0x20), clear bit 0 (0x01)
    new_2978 = (old_2978 & ~0x08 & ~0x01) | 0x20
    data[F_2978] = new_2978

    print(f"0x2971 (file 0x{F_2971:04x}): 0x{old_2971:02x} -> 0x{data[F_2971]:02x}  "
          f"(voice bit 5: {(old_2971>>5)&1} -> {(data[F_2971]>>5)&1})")
    print(f"0x2977 (file 0x{F_2977:04x}): 0x{old_2977:02x} -> 0x{data[F_2977]:02x}  "
          f"(keybeep bit 7: {(old_2977>>7)&1} -> {(data[F_2977]>>7)&1})")
    print(f"0x2978 (file 0x{F_2978:04x}): 0x{old_2978:02x} -> 0x{data[F_2978]:02x}  "
          f"(night bit 3: {(old_2978>>3)&1} -> {(data[F_2978]>>3)&1}; "
          f"chmode: {chmode(old_2978)} -> {chmode(data[F_2978])})")

    DST.write_bytes(bytes(data))
    print(f"\nWrote {DST.name}")


if __name__ == "__main__":
    main()
