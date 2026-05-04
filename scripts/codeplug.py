#!/usr/bin/env python3
"""
codeplug.py - Round-trip parser for the Ailunce HD1/HD2 codeplug binary format.

Parses a packed .bin (as produced by hd1_dump.py) into Python dataclasses,
and serializes back to an identical binary. All unknown bytes are preserved
via raw byte storage on each record.

Usage:
    python3 codeplug.py dump output/cp_testcontacts.bin
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Region layout — must match hd1_dump.py's CODEPLUG_REGIONS output order.
# (name, radio_addr_base, file_base, length_bytes, block_size, is_block)
# ---------------------------------------------------------------------------
# Current layout (settings 0x3680, table_21dx 0x4A000 covering all 256 zones)
REGIONS = [
    ("header",     0x0000, 0x000000, 0x00200, 0x80,  False),
    ("vfo_config", 0x2000, 0x000200, 0x00380, 0x80,  False),
    ("settings",   0x2900, 0x000580, 0x03680, 0x80,  False),
    ("addr_book",  0x0000, 0x003C00, 0x00400, 0x400, True),
    ("channels",   0x1B84, 0x004000, 0x93000, 0x400, True),
    ("table_1dfx", 0x1DF8, 0x097000, 0x03000, 0x400, True),
    ("table_21dx", 0x21D8, 0x09A000, 0x4A000, 0x400, True),  # 0x21D8..0x22FF
    ("table_4000", 0x4000, 0x0E4000, 0x00400, 0x400, True),
    ("table_428x", 0x4280, 0x0E4400, 0x00C00, 0x400, True),
]

EXPECTED_SIZE = sum(r[3] for r in REGIONS)  # 938,000

# Pre-zones-extended layout (table_21dx 0x14000)
REGIONS_MEDIUM = [
    ("header",     0x0000, 0x000000, 0x00200, 0x80,  False),
    ("vfo_config", 0x2000, 0x000200, 0x00380, 0x80,  False),
    ("settings",   0x2900, 0x000580, 0x03680, 0x80,  False),
    ("addr_book",  0x0000, 0x003C00, 0x00400, 0x400, True),
    ("channels",   0x1B84, 0x004000, 0x93000, 0x400, True),
    ("table_1dfx", 0x1DF8, 0x097000, 0x03000, 0x400, True),
    ("table_21dx", 0x21D8, 0x09A000, 0x14000, 0x400, True),
    ("table_4000", 0x4000, 0x0AE000, 0x00400, 0x400, True),
    ("table_428x", 0x4280, 0x0AE400, 0x00C00, 0x400, True),
]
MEDIUM_SIZE = sum(r[3] for r in REGIONS_MEDIUM)  # 716,800

# Legacy layout (settings 0x3280 instead of 0x3680)
REGIONS_LEGACY = [
    ("header",     0x0000, 0x000000, 0x00200, 0x80,  False),
    ("vfo_config", 0x2000, 0x000200, 0x00380, 0x80,  False),
    ("settings",   0x2900, 0x000580, 0x03280, 0x80,  False),
    ("addr_book",  0x0000, 0x003800, 0x00400, 0x400, True),
    ("channels",   0x1B84, 0x003C00, 0x93000, 0x400, True),
    ("table_1dfx", 0x1DF8, 0x096C00, 0x03000, 0x400, True),
    ("table_21dx", 0x21D8, 0x099C00, 0x14000, 0x400, True),
    ("table_4000", 0x4000, 0x0ADC00, 0x00400, 0x400, True),
    ("table_428x", 0x4280, 0x0AE000, 0x00C00, 0x400, True),
]
LEGACY_SIZE = sum(r[3] for r in REGIONS_LEGACY)  # 715,776

# Block address ranges within the channels region
CONTACT_BLOCKS = (0x1B84, 0x1BCB)  # inclusive
CHANNEL_BLOCKS = (0x1BCC, 0x1DCF)  # inclusive

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _region(name: str, regions=None):
    for r in (regions or REGIONS):
        if r[0] == name:
            return r
    raise KeyError(name)


def radio_to_file(name: str, radio_addr: int, regions=None) -> int:
    """Convert a radio address to a file offset within the named region."""
    _, base, fbase, length, bsz, is_block = _region(name, regions)
    if is_block:
        return fbase + (radio_addr - base) * bsz
    return fbase + (radio_addr - base)


def read_cstring(data: bytes, offset: int, length: int) -> str:
    """Read a null/0xFF-padded ASCII string."""
    raw = data[offset:offset + length]
    end = len(raw)
    while end > 0 and raw[end - 1] in (0x00, 0xFF):
        end -= 1
    return raw[:end].decode("ascii", errors="replace")


def write_cstring(s: str, length: int, fill: int = 0x00) -> bytes:
    """Encode a string into a fixed-length padded field."""
    return s.encode("ascii", errors="replace")[:length].ljust(length, bytes([fill]))


def decode_freq_bcd(b: bytes) -> float:
    """4-byte BCD LE frequency -> MHz float. Returns 0.0 if invalid."""
    if len(b) != 4 or all(x == 0xFF for x in b):
        return 0.0
    digits = ""
    for byte in reversed(b):
        hi, lo = (byte >> 4) & 0xF, byte & 0xF
        if hi > 9 or lo > 9:
            return 0.0
        digits += f"{hi}{lo}"
    return int(digits) * 10 / 1e6


def encode_freq_bcd(mhz: float) -> bytes:
    """MHz float -> 4-byte BCD LE frequency."""
    if mhz <= 0:
        return b"\xff\xff\xff\xff"
    val = round(mhz * 1e6 / 10)
    digits = f"{val:08d}"
    result = bytearray(4)
    for i in range(4):
        d = (3 - i) * 2
        result[i] = (int(digits[d]) << 4) | int(digits[d + 1])
    return bytes(result)


def decode_tone(b: bytes) -> str:
    """2-byte BCD CTCSS tone -> string (e.g. '131.7'). '' if none."""
    if len(b) != 2 or b == b"\xff\xff":
        return ""
    digits = ""
    for byte in b:
        hi, lo = (byte >> 4) & 0xF, byte & 0xF
        if hi > 9 or lo > 9:
            return f"raw:{b.hex()}"
        digits += f"{hi}{lo}"
    return f"{int(digits) / 10:.1f}"


def encode_tone(s: str) -> bytes:
    """String tone -> 2-byte BCD. '' -> 0xFFFF."""
    if not s:
        return b"\xff\xff"
    if s.startswith("raw:"):
        return bytes.fromhex(s[4:])
    val = round(float(s) * 10)
    digits = f"{val:04d}"
    return bytes([
        (int(digits[0]) << 4) | int(digits[1]),
        (int(digits[2]) << 4) | int(digits[3]),
    ])


# ---------------------------------------------------------------------------
# Contact (72-byte record)
# ---------------------------------------------------------------------------

CALL_TYPE_MAP = {0x04: "group", 0x05: "private", 0x06: "all"}
CALL_TYPE_RMAP = {v: k for k, v in CALL_TYPE_MAP.items()}

CONTACT_STRIDE = 72
CONTACTS_PER_BLOCK = 1024 // CONTACT_STRIDE  # 14


@dataclass
class Contact:
    dmr_id: int
    call_type: str       # "group" | "private" | "all"
    name: str
    city: str
    province: str
    country: str
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @classmethod
    def from_bytes(cls, data: bytes, file_offset: int = -1) -> Contact | None:
        """Parse a 72-byte contact record. Returns None if empty."""
        if len(data) < CONTACT_STRIDE:
            return None
        rec = data[:CONTACT_STRIDE]
        dmr_id = int.from_bytes(rec[0:4], "little")
        # Skip empty records
        if rec[:8] == b"\xff" * 8:
            return None
        if dmr_id == 0 and not any(rec[5:21]):
            return None
        return cls(
            dmr_id=dmr_id,
            call_type=CALL_TYPE_MAP.get(rec[4], f"0x{rec[4]:02x}"),
            name=read_cstring(rec, 0x05, 16),
            city=read_cstring(rec, 0x15, 16),
            province=read_cstring(rec, 0x25, 16),
            country=read_cstring(rec, 0x35, 16),
            _raw=bytes(rec),
            _file_offset=file_offset,
        )

    def to_bytes(self) -> bytes:
        buf = bytearray(self._raw) if len(self._raw) == CONTACT_STRIDE else bytearray(CONTACT_STRIDE)
        buf[0:4] = self.dmr_id.to_bytes(4, "little")
        buf[4] = CALL_TYPE_RMAP.get(self.call_type, int(self.call_type, 16) if self.call_type.startswith("0x") else 0x04)
        # Detect fill byte from raw (0x00 or 0xFF padding)
        fill = buf[0x14] if len(self._raw) == CONTACT_STRIDE and buf[0x14] in (0x00, 0xFF) else 0x00
        buf[0x05:0x15] = write_cstring(self.name, 16, fill)
        buf[0x15:0x25] = write_cstring(self.city, 16, fill)
        buf[0x25:0x35] = write_cstring(self.province, 16, fill)
        buf[0x35:0x45] = write_cstring(self.country, 16, fill)
        return bytes(buf)


# ---------------------------------------------------------------------------
# Channel (176-byte record)
# ---------------------------------------------------------------------------

CHANNEL_STRIDE = 176
CHANNELS_PER_BLOCK = 5  # at offset 0x80 within each 1024-byte block
CHANNEL_BLOCK_OFFSET = 0x80

POWER_MAP = {
    (0b00, 0): "low",
    (0b01, 0): "medium",
    (0b10, 0): "high",
    (0b01, 1): "extra_low",
}
POWER_RMAP = {v: k for k, v in POWER_MAP.items()}

ENCRYPT_FAMILY = {0: "off", 1: "normal", 2: "enhanced", 3: "aes"}
ENCRYPT_FAMILY_RMAP = {v: k for k, v in ENCRYPT_FAMILY.items()}

DMR_MODE_MAP = {(0, 0): "simplex", (0, 1): "repeater", (1, 0): "double"}
DMR_MODE_RMAP = {v: k for k, v in DMR_MODE_MAP.items()}

BUSY_LOCK_MAP = {0: "forbid", 1: "impolite", 2: "polite_cc", 3: "polite_all"}
BUSY_LOCK_RMAP = {v: k for k, v in BUSY_LOCK_MAP.items()}


@dataclass
class Channel:
    name: str
    mode: str             # "FM" | "DMR"
    rx_freq: float        # MHz
    tx_freq: float        # MHz
    contact_id: int
    power: str            # "low"|"medium"|"high"|"extra_low"
    bandwidth: str        # "narrow"|"wide"
    color_code: int       # 0..15
    timeslot: int         # 1 or 2
    dmr_mode: str         # "simplex"|"repeater"|"double"
    gps_enable: bool
    tx_gps: bool
    rx_gps_info: bool
    gps_timing: int
    encrypt_family: str   # "off"|"normal"|"enhanced"|"aes"
    encrypt_key: int      # 0..15
    promiscuous: bool
    tx_authority_2: bool
    tx_authority_cf: bool
    busy_lock: str
    rx_all_pc: bool
    scan_add: bool
    work_alone: bool
    talkaround: bool
    relay: bool
    radio_id_index: int
    rx_tone: str
    tx_tone: str
    rx_list: list[int]    # DMR IDs
    vox_enable: bool = False
    vox_level: int = 0    # 0 = off; 1..9 when enabled
    tot_seconds: int = 0  # Time-Out Timer in seconds; 0=off, multiples of 15
    _power_bits: int = field(default=0, repr=False)   # raw bits 3:2 of +0x21
    _power_ext: int = field(default=0, repr=False)    # raw bit 3 of +0x29
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @classmethod
    def from_bytes(cls, data: bytes, file_offset: int = -1) -> Channel | None:
        """Parse a 176-byte channel slot. Returns None if empty."""
        if len(data) < CHANNEL_STRIDE:
            return None
        rec = data[:CHANNEL_STRIDE]
        rx_raw = rec[0x14:0x18]
        if rx_raw == b"\xff\xff\xff\xff" or rx_raw == b"\x00\x00\x00\x00":
            return None

        flags = int.from_bytes(rec[0x10:0x14], "little")
        # Reject slots where flags are all-FF (not a real channel)
        if flags == 0xFFFFFFFF:
            return None

        # +0x20 mode/flag bytes
        b20 = rec[0x20]
        b21 = rec[0x21]
        b22 = rec[0x22]
        b28 = rec[0x28]
        b29 = rec[0x29]
        b2a = rec[0x2A]
        b2b = rec[0x2B]

        # FM/DMR mode is +0x21 bit 6 (0x40) — THE ONE TRUE MODE BIT.
        # Verified 2026-04-15 by CPS toggle DMR→FM: only +0x21 changed
        # (0x49→0x09); +0x29 and all other bytes stayed identical.
        is_fm = not bool(b21 & 0x40)

        # VOX: +0x20 bit 5 = enable; when on, low nibble = level - 1 (1..9 in CPS).
        vox_enable = bool(b20 & 0x20)
        vox_level = (b20 & 0x0F) + 1 if vox_enable else 0

        # Power: +0x21 bits 3:2 + +0x29 bit 3
        pwr_bits = (b21 >> 2) & 0x03
        pwr_ext = (b29 >> 3) & 0x01
        power = POWER_MAP.get((pwr_bits, pwr_ext), "low")

        # Encrypt: +0x28 bits 6:5 = family, +0x28 bits 3:0 = key index
        enc_fam = (b28 >> 5) & 0x03
        enc_key = b28 & 0x0F

        # DMR mode: +0x2A bit3, bit1
        dmr_bit3 = (b2a >> 3) & 1
        dmr_bit1 = (b2a >> 1) & 1
        dmr_mode = DMR_MODE_MAP.get((dmr_bit3, dmr_bit1), "simplex")

        # Busy lock: +0x2B bits 7:6
        busy = (b2b >> 6) & 0x03

        # Rx list: 4-byte LE DMR IDs at +0x30, terminated by 0xFFFFFFFF
        rx_list = []
        for i in range(0x30, 0xB0, 4):
            rid = int.from_bytes(rec[i:i + 4], "little")
            if rid == 0xFFFFFFFF:
                break
            rx_list.append(rid)

        return cls(
            name=read_cstring(rec, 4, 10),
            mode="FM" if is_fm else "DMR",
            rx_freq=decode_freq_bcd(rx_raw),
            tx_freq=decode_freq_bcd(rec[0x18:0x1C]),
            contact_id=int.from_bytes(rec[0x1C:0x20], "little"),
            power=power,
            bandwidth="wide" if (b29 & 0x40) else "narrow",
            color_code=(b2a >> 4) & 0x0F,
            timeslot=2 if (b2a & 0x01) else 1,
            dmr_mode=dmr_mode,
            gps_enable=bool(b20 & 0x80),
            tx_gps=bool(b20 & 0x10),
            rx_gps_info=bool(b2b & 0x20),
            gps_timing=b22,
            encrypt_family=ENCRYPT_FAMILY.get(enc_fam, "off"),
            encrypt_key=enc_key,
            promiscuous=bool(b29 & 0x01),
            tx_authority_2=bool(b28 & 0x80),
            tx_authority_cf=bool(b29 & 0x10),
            busy_lock=BUSY_LOCK_MAP.get(busy, "forbid"),
            rx_all_pc=bool(rec[0x11] & 0x40),
            scan_add=bool(b21 & 0x01),
            work_alone=bool(b20 & 0x40),
            talkaround=bool(b21 & 0x02),
            relay=bool(b21 & 0x80),
            radio_id_index=b2b & 0x01,
            rx_tone=decode_tone(rec[0x24:0x26]),
            tx_tone=decode_tone(rec[0x26:0x28]),
            rx_list=rx_list,
            vox_enable=vox_enable,
            vox_level=vox_level,
            tot_seconds=rec[0x23] * 15,
            _power_bits=pwr_bits,
            _power_ext=pwr_ext,
            _raw=bytes(rec),
            _file_offset=file_offset,
        )

    def to_bytes(self) -> bytes:
        buf = bytearray(self._raw) if len(self._raw) == CHANNEL_STRIDE else bytearray(CHANNEL_STRIDE)

        # Marker
        buf[0x00:0x04] = b"\xff\xff\xff\xff"
        # Name — preserve original fill byte (0x00 or 0xFF)
        name_fill = buf[0x0D] if buf[0x0D] in (0x00, 0xFF) else 0x00
        buf[0x04:0x0E] = write_cstring(self.name, 10, name_fill)

        # Flags at +0x10..+0x13: preserve raw, patch RxAll PC.
        # Mode (FM/DMR) is encoded at +0x29 bit 7, not here.
        flags = int.from_bytes(buf[0x10:0x14], "little")
        # RxAll PC: byte +0x11 bit 6
        if self.rx_all_pc:
            flags |= (0x40 << 8)
        else:
            flags &= ~(0x40 << 8)
        buf[0x10:0x14] = flags.to_bytes(4, "little")

        # Frequencies
        buf[0x14:0x18] = encode_freq_bcd(self.rx_freq)
        buf[0x18:0x1C] = encode_freq_bcd(self.tx_freq)

        # Contact
        buf[0x1C:0x20] = self.contact_id.to_bytes(4, "little")

        # +0x20: gps/work_alone/tx_gps + VOX (bit 5 = enable, low nibble = level-1).
        # Mask out our bits (gps, work_alone, tx_gps, vox enable, vox level low nibble).
        b20 = buf[0x20]
        b20 = (b20 & ~0xFF) | (0x80 if self.gps_enable else 0) \
                            | (0x40 if self.work_alone else 0) \
                            | (0x10 if self.tx_gps else 0)
        if self.vox_enable:
            b20 |= 0x20 | ((self.vox_level - 1) & 0x0F)
        else:
            # Preserve the DMR-mode "0x02" flag the radio writes when VOX is off.
            # Other low-nibble bits aren't observed in test data; we use the raw byte
            # for those if present.
            orig = self._raw[0x20] if len(self._raw) > 0x20 else 0x02
            b20 |= (orig & 0x0F)
        buf[0x20] = b20

        # +0x21: scan_add, talkaround, power bits, relay.
        # Bit 6 (0x40) is set in channel slots when mode=DMR but not in VFOs;
        # leaving it preserved from raw is the safe behaviour.
        b21 = buf[0x21]
        b21 = (b21 & ~0x8F) | (0x80 if self.relay else 0) \
                            | ((self._power_bits & 0x03) << 2) \
                            | (0x02 if self.talkaround else 0) \
                            | (0x01 if self.scan_add else 0)
        buf[0x21] = b21

        # +0x22: GPS timing
        buf[0x22] = self.gps_timing & 0xFF

        # +0x23: TOT in 15-second units.
        buf[0x23] = (self.tot_seconds // 15) & 0xFF

        # +0x24..+0x27: tones
        buf[0x24:0x26] = encode_tone(self.rx_tone)
        buf[0x26:0x28] = encode_tone(self.tx_tone)

        # +0x28: tx_authority_2, encrypt family, encrypt key
        enc_fam = ENCRYPT_FAMILY_RMAP.get(self.encrypt_family, 0)
        buf[0x28] = (0x80 if self.tx_authority_2 else 0) | ((enc_fam & 0x03) << 5) | (self.encrypt_key & 0x0F)

        # +0x29: promiscuous, power ext, tx_authority_cf, bandwidth.
        # Bit 7 (DMR mode marker) is set in channel slots but not in VFOs;
        # preserve it from raw rather than re-deriving from self.mode.
        b29 = buf[0x29]
        b29 = (b29 & ~0x59) | (0x40 if self.bandwidth == "wide" else 0) \
                            | (0x10 if self.tx_authority_cf else 0) \
                            | ((self._power_ext & 1) << 3) \
                            | (0x01 if self.promiscuous else 0)
        buf[0x29] = b29

        # +0x2A: color code, timeslot, DMR mode
        dmr_bit3, dmr_bit1 = DMR_MODE_RMAP.get(self.dmr_mode, (0, 0))
        buf[0x2A] = ((self.color_code & 0x0F) << 4) | (dmr_bit3 << 3) | (dmr_bit1 << 1) | (1 if self.timeslot == 2 else 0)
        # Preserve bits 2 and 4-7 that we don't map? No — +0x2A is fully mapped:
        # high nibble = CC, bit3 = dmr_mode high, bit2 = ?, bit1 = dmr_mode low, bit0 = TS
        # Actually bit 2 might be unknown. Let's preserve it.
        orig_2a = self._raw[0x2A] if len(self._raw) > 0x2A else 0
        buf[0x2A] = ((self.color_code & 0x0F) << 4) | (orig_2a & 0x04) | (dmr_bit3 << 3) | (dmr_bit1 << 1) | (1 if self.timeslot == 2 else 0)

        # +0x2B: radio_id_index, rx_gps_info, busy_lock
        busy_val = BUSY_LOCK_RMAP.get(self.busy_lock, 0)
        b2b = buf[0x2B]
        b2b = (b2b & ~0xE1) | ((busy_val & 0x03) << 6) | (0x20 if self.rx_gps_info else 0) | (self.radio_id_index & 0x01)
        buf[0x2B] = b2b

        # Rx list at +0x30..+0xAF
        for i, rid in enumerate(self.rx_list):
            off = 0x30 + i * 4
            if off + 4 > 0xB0:
                break
            buf[off:off + 4] = rid.to_bytes(4, "little")
        # Terminate
        term_off = 0x30 + len(self.rx_list) * 4
        if term_off + 4 <= 0xB0:
            buf[term_off:term_off + 4] = b"\xff\xff\xff\xff"
        # Fill rest with 0xFF
        fill_start = term_off + 4
        if fill_start < 0xB0:
            buf[fill_start:0xB0] = b"\xff" * (0xB0 - fill_start)

        return bytes(buf)

    @classmethod
    def from_vfo_bytes(cls, data: bytes, file_offset: int = -1) -> Channel | None:
        """Parse a 32-byte VFO record (channel layout +0x10..+0x2F)."""
        if len(data) < 32 or all(b == 0xFF for b in data[:32]):
            return None
        fake = bytearray(CHANNEL_STRIDE)
        fake[0x00:0x04] = b"\xff\xff\xff\xff"
        fake[0x0E:0x10] = b"\x00\x00"
        fake[0x10:0x30] = data[:32]
        fake[0x30:] = b"\xff" * (CHANNEL_STRIDE - 0x30)
        ch = cls.from_bytes(bytes(fake), file_offset)
        if ch is not None:
            ch._raw = bytes(data[:32])
        return ch

    def to_vfo_bytes(self) -> bytes:
        """Serialize to 32-byte VFO record."""
        # Build full 176-byte record, extract +0x10..+0x2F
        if len(self._raw) == 32:
            # Reconstruct fake full record from VFO raw
            fake_raw = bytearray(CHANNEL_STRIDE)
            fake_raw[0x00:0x04] = b"\xff\xff\xff\xff"
            fake_raw[0x10:0x30] = self._raw
            fake_raw[0x30:] = b"\xff" * (CHANNEL_STRIDE - 0x30)
            saved = self._raw
            self._raw = bytes(fake_raw)
            full = self.to_bytes()
            self._raw = saved
        else:
            full = self.to_bytes()
        return full[0x10:0x30]


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------

ZONE_STRIDE = 0x91   # 145 bytes per zone slot, packed (NOT one per 1024B block)
ZONE_MAX_CHANNELS = 64
ZONE_MAX_COUNT = 256


@dataclass
class Zone:
    name: str
    channels: list[int]   # 0-based channel indices (16-bit LE)
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @classmethod
    def from_bytes(cls, rec: bytes, file_offset: int = -1) -> Zone | None:
        """Parse a zone from a 145-byte (0x91) record.
        Layout:
          +0x00  1B    count (0xff = empty slot)
          +0x01  128B  channel list (count * 2-byte LE channel index, 0-based)
          +0x81  16B   name (ASCII, null-padded; 0xff = empty)
        """
        if len(rec) < ZONE_STRIDE:
            return None
        count = rec[0]
        if count == 0xFF:
            return None  # empty slot
        if count > ZONE_MAX_CHANNELS:
            return None  # invalid
        name = read_cstring(rec, 0x81, 16)
        if not name:
            return None
        channels = []
        for n in range(count):
            i = 1 + n * 2
            v = rec[i] | (rec[i + 1] << 8)
            channels.append(v)
        return cls(
            name=name,
            channels=channels,
            _raw=bytes(rec[:ZONE_STRIDE]),
            _file_offset=file_offset,
        )

    def to_bytes(self) -> bytes:
        """Serialize back to 145-byte record."""
        buf = bytearray(b"\xff" * ZONE_STRIDE)
        buf[0] = len(self.channels) & 0xFF
        for n, ch in enumerate(self.channels):
            i = 1 + n * 2
            buf[i] = ch & 0xFF
            buf[i + 1] = (ch >> 8) & 0xFF
        buf[0x81:0x91] = write_cstring(self.name, 16)
        return bytes(buf)


# ---------------------------------------------------------------------------
# RadioID (20-byte record in settings region at radio 0x4000+)
# ---------------------------------------------------------------------------

RADIO_ID_STRIDE = 20


@dataclass
class RadioID:
    dmr_id: int
    name: str
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @classmethod
    def from_bytes(cls, data: bytes, file_offset: int = -1) -> RadioID | None:
        if len(data) < RADIO_ID_STRIDE:
            return None
        rec = data[:RADIO_ID_STRIDE]
        dmr_id = int.from_bytes(rec[0:4], "little")
        if dmr_id == 0 or dmr_id == 0xFFFFFFFF:
            return None
        return cls(
            dmr_id=dmr_id,
            name=read_cstring(rec, 4, 16),
            _raw=bytes(rec),
            _file_offset=file_offset,
        )

    def to_bytes(self) -> bytes:
        buf = bytearray(self._raw) if len(self._raw) == RADIO_ID_STRIDE else bytearray(RADIO_ID_STRIDE)
        buf[0:4] = self.dmr_id.to_bytes(4, "little")
        buf[4:20] = write_cstring(self.name, 16)
        return bytes(buf)


# ---------------------------------------------------------------------------
# RxGroupAlias (142-byte record at table_21dx, block 0x21D8+)
# ---------------------------------------------------------------------------

RX_GROUP_STRIDE = 142


@dataclass
class RxGroupAlias:
    name: str
    members: list[int]  # contact refs (addr book: 0-based index, priority: 100000+index)
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @classmethod
    def from_bytes(cls, data: bytes, file_offset: int = -1) -> RxGroupAlias | None:
        if len(data) < RX_GROUP_STRIDE:
            return None
        rec = data[:RX_GROUP_STRIDE]
        name = read_cstring(rec, 0, 10)
        if not name:
            return None
        members = []
        for i in range(0x0A, 0x8E, 4):
            mid = int.from_bytes(rec[i:i + 4], "little")
            if mid == 0xFFFFFFFF:
                break
            members.append(mid)
        return cls(
            name=name,
            members=members,
            _raw=bytes(rec),
            _file_offset=file_offset,
        )

    def to_bytes(self) -> bytes:
        buf = bytearray(self._raw) if len(self._raw) == RX_GROUP_STRIDE else bytearray(RX_GROUP_STRIDE)
        buf[0:10] = write_cstring(self.name, 10)
        off = 0x0A
        for mid in self.members:
            buf[off:off + 4] = mid.to_bytes(4, "little")
            off += 4
        if off < 0x8E:
            buf[off:off + 4] = b"\xff\xff\xff\xff"
            off += 4
        while off < 0x8E:
            buf[off:off + 4] = b"\xff\xff\xff\xff"
            off += 4
        return bytes(buf)


# ---------------------------------------------------------------------------
# EncryptionKey (49-byte record at settings radio 0x5018+)
# ---------------------------------------------------------------------------

ENCRYPT_KEY_STRIDE = 49
ENCRYPT_KEY_RADIO_BASE = 0x5018
ENCRYPT_KEY_HDR_RADIO = 0x5000
ENCRYPT_KEY_HDR_LEN = 24
MAX_ENCRYPT_KEYS = 48  # 3 groups of 16 in the 49-byte table

# Key type by slot range (49-byte table only)
def _key_type_for_slot(slot: int) -> str:
    if slot < 16:
        return "aes256"
    elif slot < 32:
        return "aes128"
    else:
        return "arc4"

# Normal keys: radio 0x3D00, 2-byte BE BCD, 16 keys
NORMAL_KEY_RADIO_BASE = 0x3D00
NORMAL_KEY_STRIDE = 2
MAX_NORMAL_KEYS = 16

# Enhanced keys: radio 0x3E00, 16 bytes each, 16 keys
ENHANCED_KEY_RADIO_BASE = 0x3E00
ENHANCED_KEY_STRIDE = 16
MAX_ENHANCED_KEYS = 16

# Key Calls 1-6: radio 0x29D0, 7-byte stride, 6 slots
KEY_CALL_RADIO_BASE = 0x29D0
KEY_CALL_STRIDE = 7
NUM_KEY_CALLS = 6

# Quick (SMS) messages: table_1dfx block 0x1DF8, first slot at block+0xDC,
# 200-byte stride. Up to 16 slots (4 fit in block 0x1DF8; rest spill into 0x1DF9).
QUICK_MSG_STRIDE = 0xC8  # 200
QUICK_MSG_FIRST_OFFSET = 0xDC
MAX_QUICK_MESSAGES = 16


@dataclass
class NormalKey:
    index: int            # 0-based (UI shows 1-based)
    value: int            # 2-byte BE BCD value (0x0000..0xFFFF)
    present: bool
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @classmethod
    def from_bytes(cls, data: bytes, index: int = 0, file_offset: int = -1) -> NormalKey:
        rec = data[:NORMAL_KEY_STRIDE] if len(data) >= NORMAL_KEY_STRIDE else data
        present = rec != b"\xff" * NORMAL_KEY_STRIDE
        value = (rec[0] << 8) | rec[1] if len(rec) >= 2 else 0
        return cls(index=index, value=value, present=present,
                   _raw=bytes(rec), _file_offset=file_offset)

    def to_bytes(self) -> bytes:
        if len(self._raw) == NORMAL_KEY_STRIDE:
            return bytes(self._raw)
        return b"\xff" * NORMAL_KEY_STRIDE


@dataclass
class EnhancedKey:
    index: int            # 0-based (UI shows 1-based)
    present: bool
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @classmethod
    def from_bytes(cls, data: bytes, index: int = 0, file_offset: int = -1) -> EnhancedKey:
        rec = data[:ENHANCED_KEY_STRIDE] if len(data) >= ENHANCED_KEY_STRIDE else data
        present = rec != b"\xff" * ENHANCED_KEY_STRIDE
        return cls(index=index, present=present,
                   _raw=bytes(rec), _file_offset=file_offset)

    def to_bytes(self) -> bytes:
        if len(self._raw) == ENHANCED_KEY_STRIDE:
            return bytes(self._raw)
        return b"\xff" * ENHANCED_KEY_STRIDE


@dataclass
class EncryptionKey:
    index: int            # 0-based slot index within the full 48-slot table
    key_type: str         # "aes256" | "aes128" | "arc4"
    key_number: int       # 1-based key number within its type (1..16)
    present: bool         # True if key is programmed (not all-FF)
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @classmethod
    def from_bytes(cls, data: bytes, index: int = 0, file_offset: int = -1) -> EncryptionKey:
        rec = data[:ENCRYPT_KEY_STRIDE] if len(data) >= ENCRYPT_KEY_STRIDE else data
        present = rec != b"\xff" * ENCRYPT_KEY_STRIDE
        key_type = _key_type_for_slot(index)
        key_number = (index % 16) + 1
        return cls(
            index=index,
            key_type=key_type,
            key_number=key_number,
            present=present,
            _raw=bytes(rec),
            _file_offset=file_offset,
        )

    def to_bytes(self) -> bytes:
        if len(self._raw) == ENCRYPT_KEY_STRIDE:
            return bytes(self._raw)
        return b"\xff" * ENCRYPT_KEY_STRIDE


@dataclass
class KeyCall:
    """Programmable Key Call 1-6 binding (7 bytes each, settings 0x29D0+).

    contact_ref encoding (1-based, 0 = unset):
      - 0               : unset
      - 1..N            : address book index+1 (1 = AB[0])
      - 100001..100000+N: priority contact index+1 (100001 = priority[0])
    """
    index: int                # 1-based (1..6)
    mode: str                 # "analog" | "digital"
    contact_ref: int          # raw reference value
    call_type: str            # "unset" | "voice" | "message"
    quick_msg_index: int      # 1-based; 0 = none
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @property
    def present(self) -> bool:
        return self.contact_ref != 0 or self.quick_msg_index != 0

    @property
    def contact_desc(self) -> str:
        r = self.contact_ref
        if r == 0:
            return "unset"
        if r < 100000:
            return f"AB[{r - 1}]"
        return f"priority[{r - 100001}]"

    @classmethod
    def from_bytes(cls, data: bytes, index: int, file_offset: int = -1) -> KeyCall:
        rec = data[:KEY_CALL_STRIDE]
        if len(rec) < KEY_CALL_STRIDE:
            rec = rec + b"\x00" * (KEY_CALL_STRIDE - len(rec))
        mode = "digital" if rec[0] == 1 else "analog"
        contact_ref = int.from_bytes(rec[1:5], "little")
        ct_byte = rec[5]
        call_type = {0: "unset", 1: "voice", 2: "message"}.get(ct_byte, f"unk{ct_byte:#04x}")
        qm = rec[6]
        return cls(
            index=index,
            mode=mode,
            contact_ref=contact_ref,
            call_type=call_type,
            quick_msg_index=qm,
            _raw=bytes(rec),
            _file_offset=file_offset,
        )

    def to_bytes(self) -> bytes:
        # Preserve original bytes for lossless round-trip. Editing should be
        # done via explicit field manipulation + a dedicated rebuild step.
        if len(self._raw) == KEY_CALL_STRIDE:
            return bytes(self._raw)
        buf = bytearray(KEY_CALL_STRIDE)
        buf[0] = 1 if self.mode == "digital" else 0
        buf[1:5] = self.contact_ref.to_bytes(4, "little")
        ct_map = {"unset": 0, "voice": 1, "message": 2}
        buf[5] = ct_map.get(self.call_type, 0)
        buf[6] = self.quick_msg_index & 0xFF
        return bytes(buf)


@dataclass
class QuickMessage:
    """Quick SMS message slot (200 bytes, null-padded ASCII).

    Stored starting at table_1dfx block 0x1DF8 + 0xDC, 200-byte stride.
    Slots spill from block 0x1DF8 into 0x1DF9 past the 4th slot.
    """
    index: int              # 1-based
    text: str
    _raw: bytes = field(default=b"", repr=False)
    _file_offset: int = field(default=-1, repr=False)

    @property
    def present(self) -> bool:
        return bool(self.text)

    @classmethod
    def from_bytes(cls, data: bytes, index: int, file_offset: int = -1) -> QuickMessage | None:
        rec = data[:QUICK_MSG_STRIDE]
        if len(rec) < QUICK_MSG_STRIDE:
            return None
        # Skip slots that are clearly unused (all-FF or all-00) so we don't
        # round-trip garbage through the text field.
        if rec == b"\xff" * QUICK_MSG_STRIDE or rec == b"\x00" * QUICK_MSG_STRIDE:
            return None
        # Decode text up to first null. Require all bytes before the null to
        # be valid printable ASCII — otherwise it's not a real message slot.
        nul = rec.find(b"\x00")
        if nul < 0:
            nul = len(rec)
        text_bytes = rec[:nul]
        if not text_bytes:
            return None
        try:
            text = text_bytes.decode("ascii")
        except UnicodeDecodeError:
            return None
        return cls(index=index, text=text, _raw=bytes(rec), _file_offset=file_offset)

    def to_bytes(self) -> bytes:
        # Preserve original bytes verbatim for lossless round-trip.
        if len(self._raw) == QUICK_MSG_STRIDE:
            return bytes(self._raw)
        buf = bytearray(QUICK_MSG_STRIDE)
        enc = self.text.encode("ascii", errors="replace")[:QUICK_MSG_STRIDE]
        buf[:len(enc)] = enc
        return bytes(buf)


# ---------------------------------------------------------------------------
# Top-level Codeplug
# ---------------------------------------------------------------------------

@dataclass
class Codeplug:
    address_book: list[Contact]
    priority_contacts: list[Contact]
    channels: list[Channel]
    zones: list[Zone]
    radio_ids: list[RadioID]
    rx_groups: list[RxGroupAlias]
    encrypt_keys: list[EncryptionKey]
    normal_keys: list[NormalKey]
    enhanced_keys: list[EnhancedKey]
    key_calls: list[KeyCall]
    quick_messages: list[QuickMessage]
    vfo_a: Channel | None
    vfo_b: Channel | None
    raw_settings: bytes
    raw_header: bytes
    _data: bytearray = field(repr=False, default_factory=bytearray)

    @classmethod
    def from_bin(cls, data: bytes) -> Codeplug:
        if len(data) == EXPECTED_SIZE:
            regions = REGIONS
        elif len(data) == MEDIUM_SIZE:
            regions = REGIONS_MEDIUM
        elif len(data) == LEGACY_SIZE:
            regions = REGIONS_LEGACY
        else:
            raise ValueError(
                f"Expected {EXPECTED_SIZE}, {MEDIUM_SIZE}, or {LEGACY_SIZE} bytes, got {len(data)}"
            )
        buf = bytearray(data)

        # --- Raw regions ---
        hdr_r = _region("header", regions)
        raw_header = bytes(data[hdr_r[2]:hdr_r[2] + hdr_r[3]])

        set_r = _region("settings", regions)
        raw_settings = bytes(data[set_r[2]:set_r[2] + set_r[3]])

        # --- VFO-A (radio 0x0090) and VFO-B (radio 0x0140) in header region ---
        vfo_a = Channel.from_vfo_bytes(data[0x0090:0x00B0], file_offset=0x0090)
        vfo_b = Channel.from_vfo_bytes(data[0x0140:0x0160], file_offset=0x0140)

        # --- Address book (1 block at region addr_book) ---
        ab_r = _region("addr_book", regions)
        ab_base = ab_r[2]
        address_book = []
        for i in range(CONTACTS_PER_BLOCK):
            off = ab_base + i * CONTACT_STRIDE
            c = Contact.from_bytes(data[off:off + CONTACT_STRIDE], file_offset=off)
            if c is not None:
                address_book.append(c)

        # --- Priority contacts (channel blocks 0x1B84..0x1BCB) ---
        ch_r = _region("channels", regions)
        ch_fbase = ch_r[2]
        ch_rbase = ch_r[1]
        priority_contacts = []
        for blk in range(CONTACT_BLOCKS[0], CONTACT_BLOCKS[1] + 1):
            blk_off = ch_fbase + (blk - ch_rbase) * 0x400
            for i in range(CONTACTS_PER_BLOCK):
                off = blk_off + i * CONTACT_STRIDE
                c = Contact.from_bytes(data[off:off + CONTACT_STRIDE], file_offset=off)
                if c is not None:
                    priority_contacts.append(c)

        # --- Channels (continuous 176-byte stream starting at block 0x1BCC +0x80) ---
        # Records wrap across 1024-byte block boundaries.
        stream_start = ch_fbase + (CHANNEL_BLOCKS[0] - ch_rbase) * 0x400 + CHANNEL_BLOCK_OFFSET
        stream_end = ch_fbase + (CHANNEL_BLOCKS[1] - ch_rbase + 1) * 0x400
        channels = []
        pos = stream_start
        while pos + CHANNEL_STRIDE <= stream_end:
            ch = Channel.from_bytes(data[pos:pos + CHANNEL_STRIDE], file_offset=pos)
            if ch is not None:
                channels.append(ch)
            pos += CHANNEL_STRIDE

        # --- Zones (table_21dx, block 0x2200+) ---
        z_r = _region("table_21dx", regions)
        z_fbase = z_r[2]
        z_rbase = z_r[1]
        z_nblocks = z_r[3] // 0x400
        # Zones start at radio block 0x2200, packed densely with 145-byte stride
        # (NOT one zone per block). Walk up to ZONE_MAX_COUNT slots.
        zones = []
        zones_file_base = z_fbase + (0x2200 - z_rbase) * 0x400
        zones_file_end = z_fbase + z_nblocks * 0x400
        for i in range(ZONE_MAX_COUNT):
            off = zones_file_base + i * ZONE_STRIDE
            if off + ZONE_STRIDE > zones_file_end:
                break
            z = Zone.from_bytes(data[off:off + ZONE_STRIDE], file_offset=off)
            if z is not None:
                zones.append(z)

        # --- Radio IDs (settings region, radio 0x4000+) ---
        rid_file = radio_to_file("settings", 0x4000, regions)
        radio_ids = []
        for i in range(16):  # max 16 radio IDs
            off = rid_file + i * RADIO_ID_STRIDE
            if off + RADIO_ID_STRIDE > set_r[2] + set_r[3]:
                break
            rid = RadioID.from_bytes(data[off:off + RADIO_ID_STRIDE], file_offset=off)
            if rid is not None:
                radio_ids.append(rid)

        # --- Rx Group Aliases (table_21dx, block 0x21D8+) ---
        rx_groups = []
        # RxGroupAlias records are 142-byte stride, packed at the start of
        # the table_21dx region (block 0x21D8 onwards, before zones at 0x2200)
        for blk_addr in range(z_rbase, min(z_rbase + (0x2200 - z_rbase), z_rbase + z_nblocks)):
            blk_off = z_fbase + (blk_addr - z_rbase) * 0x400
            # Try parsing 142-byte records from this block
            for i in range(1024 // RX_GROUP_STRIDE):
                off = blk_off + i * RX_GROUP_STRIDE
                rg = RxGroupAlias.from_bytes(data[off:off + RX_GROUP_STRIDE], file_offset=off)
                if rg is not None:
                    rx_groups.append(rg)

        # --- Encryption keys (settings region, radio 0x5018+, 49-byte stride) ---
        ek_file = radio_to_file("settings", ENCRYPT_KEY_RADIO_BASE, regions)
        encrypt_keys = []
        for i in range(MAX_ENCRYPT_KEYS):
            off = ek_file + i * ENCRYPT_KEY_STRIDE
            if off + ENCRYPT_KEY_STRIDE > set_r[2] + set_r[3]:
                break
            ek = EncryptionKey.from_bytes(data[off:off + ENCRYPT_KEY_STRIDE], index=i, file_offset=off)
            encrypt_keys.append(ek)

        # --- Normal keys (radio 0x3D00, 2-byte BE BCD) ---
        nk_file = radio_to_file("settings", NORMAL_KEY_RADIO_BASE, regions)
        normal_keys = []
        for i in range(MAX_NORMAL_KEYS):
            off = nk_file + i * NORMAL_KEY_STRIDE
            if off + NORMAL_KEY_STRIDE > set_r[2] + set_r[3]:
                break
            nk = NormalKey.from_bytes(data[off:off + NORMAL_KEY_STRIDE], index=i, file_offset=off)
            normal_keys.append(nk)

        # --- Enhanced keys (radio 0x3E00, 16 bytes each) ---
        enk_file = radio_to_file("settings", ENHANCED_KEY_RADIO_BASE, regions)
        enhanced_keys = []
        for i in range(MAX_ENHANCED_KEYS):
            off = enk_file + i * ENHANCED_KEY_STRIDE
            if off + ENHANCED_KEY_STRIDE > set_r[2] + set_r[3]:
                break
            enk = EnhancedKey.from_bytes(data[off:off + ENHANCED_KEY_STRIDE], index=i, file_offset=off)
            enhanced_keys.append(enk)

        # --- Key Calls 1-6 (settings 0x29D0, 7B stride) ---
        kc_file = radio_to_file("settings", KEY_CALL_RADIO_BASE, regions)
        key_calls = []
        for i in range(NUM_KEY_CALLS):
            off = kc_file + i * KEY_CALL_STRIDE
            kc = KeyCall.from_bytes(data[off:off + KEY_CALL_STRIDE], index=i + 1, file_offset=off)
            key_calls.append(kc)

        # --- Quick SMS messages (table_1dfx block 0x1DF8 + 0xDC, 200B stride) ---
        t1dfx_r = _region("table_1dfx", regions)
        qm_base = t1dfx_r[2] + QUICK_MSG_FIRST_OFFSET
        quick_messages = []
        for i in range(MAX_QUICK_MESSAGES):
            off = qm_base + i * QUICK_MSG_STRIDE
            if off + QUICK_MSG_STRIDE > t1dfx_r[2] + t1dfx_r[3]:
                break
            qm = QuickMessage.from_bytes(data[off:off + QUICK_MSG_STRIDE], index=i + 1, file_offset=off)
            if qm is not None:
                quick_messages.append(qm)

        return cls(
            address_book=address_book,
            priority_contacts=priority_contacts,
            channels=channels,
            zones=zones,
            radio_ids=radio_ids,
            rx_groups=rx_groups,
            encrypt_keys=encrypt_keys,
            normal_keys=normal_keys,
            enhanced_keys=enhanced_keys,
            key_calls=key_calls,
            quick_messages=quick_messages,
            vfo_a=vfo_a,
            vfo_b=vfo_b,
            raw_settings=raw_settings,
            raw_header=raw_header,
            _data=buf,
        )

    def to_bin(self) -> bytes:
        """Serialize back to packed binary. Writes parsed records at their
        original file offsets; everything else is preserved from the original."""
        buf = bytearray(self._data)

        # VFOs
        if self.vfo_a is not None:
            buf[0x0090:0x00B0] = self.vfo_a.to_vfo_bytes()
        if self.vfo_b is not None:
            buf[0x0140:0x0160] = self.vfo_b.to_vfo_bytes()

        # Address book contacts
        for c in self.address_book:
            if c._file_offset >= 0:
                buf[c._file_offset:c._file_offset + CONTACT_STRIDE] = c.to_bytes()

        # Priority contacts
        for c in self.priority_contacts:
            if c._file_offset >= 0:
                buf[c._file_offset:c._file_offset + CONTACT_STRIDE] = c.to_bytes()

        # Channels
        for ch in self.channels:
            if ch._file_offset >= 0:
                buf[ch._file_offset:ch._file_offset + CHANNEL_STRIDE] = ch.to_bytes()

        # Zones (145-byte stride, packed)
        for z in self.zones:
            if z._file_offset >= 0:
                buf[z._file_offset:z._file_offset + ZONE_STRIDE] = z.to_bytes()

        # Radio IDs
        for r in self.radio_ids:
            if r._file_offset >= 0:
                buf[r._file_offset:r._file_offset + RADIO_ID_STRIDE] = r.to_bytes()

        # Rx Groups
        for rg in self.rx_groups:
            if rg._file_offset >= 0:
                buf[rg._file_offset:rg._file_offset + RX_GROUP_STRIDE] = rg.to_bytes()

        # Encryption keys (49-byte table)
        for ek in self.encrypt_keys:
            if ek._file_offset >= 0:
                buf[ek._file_offset:ek._file_offset + ENCRYPT_KEY_STRIDE] = ek.to_bytes()

        # Normal keys
        for nk in self.normal_keys:
            if nk._file_offset >= 0:
                buf[nk._file_offset:nk._file_offset + NORMAL_KEY_STRIDE] = nk.to_bytes()

        # Enhanced keys
        for enk in self.enhanced_keys:
            if enk._file_offset >= 0:
                buf[enk._file_offset:enk._file_offset + ENHANCED_KEY_STRIDE] = enk.to_bytes()

        # Key Calls
        for kc in self.key_calls:
            if kc._file_offset >= 0:
                buf[kc._file_offset:kc._file_offset + KEY_CALL_STRIDE] = kc.to_bytes()

        # Quick messages
        for qm in self.quick_messages:
            if qm._file_offset >= 0:
                buf[qm._file_offset:qm._file_offset + QUICK_MSG_STRIDE] = qm.to_bytes()

        return bytes(buf)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _freq_str(mhz: float) -> str:
    return f"{mhz:.5f}" if mhz > 0 else "-"


def dump_summary(cp: Codeplug):
    print(f"=== Codeplug Summary ===\n")

    if cp.radio_ids:
        print(f"Radio IDs ({len(cp.radio_ids)}):")
        for r in cp.radio_ids:
            print(f"  {r.dmr_id:>8d}  {r.name}")
        print()

    if cp.address_book:
        print(f"Address Book ({len(cp.address_book)}):")
        for c in cp.address_book:
            print(f"  {c.dmr_id:>8d}  {c.call_type:<7s}  {c.name}")
        print()

    if cp.priority_contacts:
        print(f"Priority Contacts ({len(cp.priority_contacts)}):")
        for c in cp.priority_contacts:
            extra = ""
            if c.city:
                extra += f"  city={c.city}"
            if c.province:
                extra += f"  prov={c.province}"
            if c.country:
                extra += f"  country={c.country}"
            print(f"  {c.dmr_id:>8d}  {c.call_type:<7s}  {c.name}{extra}")
        print()

    if cp.vfo_a:
        v = cp.vfo_a
        print(f"VFO-A: {v.mode}  rx={_freq_str(v.rx_freq)}  tx={_freq_str(v.tx_freq)}  pwr={v.power}")
    if cp.vfo_b:
        v = cp.vfo_b
        print(f"VFO-B: {v.mode}  rx={_freq_str(v.rx_freq)}  tx={_freq_str(v.tx_freq)}  pwr={v.power}")
    if cp.vfo_a or cp.vfo_b:
        print()

    if cp.channels:
        print(f"Channels ({len(cp.channels)}):")
        for i, ch in enumerate(cp.channels):
            tone = ""
            if ch.rx_tone:
                tone += f" rxT={ch.rx_tone}"
            if ch.tx_tone:
                tone += f" txT={ch.tx_tone}"
            dmr = ""
            if ch.mode == "DMR":
                dmr = f" CC={ch.color_code} TS{ch.timeslot} {ch.dmr_mode}"
                if ch.contact_id:
                    dmr += f" cid={ch.contact_id}"
            enc = ""
            if ch.encrypt_family != "off":
                enc = f" enc={ch.encrypt_family}:{ch.encrypt_key}"
            rxl = ""
            if ch.rx_list:
                rxl = f" rxl=[{','.join(str(x) for x in ch.rx_list[:5])}{'...' if len(ch.rx_list) > 5 else ''}]"
            print(f"  {i:>3d}  {ch.name or '(unnamed)':<12s}  {ch.mode:<3s}  "
                  f"rx={_freq_str(ch.rx_freq)}  tx={_freq_str(ch.tx_freq)}  "
                  f"pwr={ch.power}{dmr}{tone}{enc}{rxl}")
        print()

    if cp.zones:
        print(f"Zones ({len(cp.zones)}):")
        for z in cp.zones:
            ch_str = ",".join(str(c) for c in z.channels[:10])
            if len(z.channels) > 10:
                ch_str += "..."
            print(f"  {z.name}  channels=[{ch_str}]")
        print()

    if cp.rx_groups:
        print(f"Rx Group Aliases ({len(cp.rx_groups)}):")
        for rg in cp.rx_groups:
            print(f"  {rg.name}  members={rg.members}")
        print()

    # Normal keys
    normal_set = [nk for nk in cp.normal_keys if nk.present]
    if normal_set:
        print(f"Normal Keys ({len(normal_set)}/16):")
        for nk in cp.normal_keys:
            if nk.present:
                print(f"  key {nk.index + 1:>2d}: 0x{nk.value:04X}")
            else:
                print(f"  key {nk.index + 1:>2d}: ---")
        print()

    # Enhanced keys
    enhanced_set = [ek for ek in cp.enhanced_keys if ek.present]
    if enhanced_set:
        print(f"Enhanced Keys ({len(enhanced_set)}/16):")
        for ek in cp.enhanced_keys:
            status = "SET" if ek.present else "---"
            print(f"  key {ek.index + 1:>2d}: {status}")
        print()

    # Key Calls 1-6
    active_kc = [kc for kc in cp.key_calls if kc.present]
    if active_kc:
        print(f"Key Calls ({len(active_kc)}/{len(cp.key_calls)} set):")
        for kc in cp.key_calls:
            if kc.present:
                qm = f" qm={kc.quick_msg_index}" if kc.quick_msg_index else ""
                print(f"  KC{kc.index}: mode={kc.mode} contact={kc.contact_desc} "
                      f"type={kc.call_type}{qm}")
        print()

    # Quick messages
    active_qm = [qm for qm in cp.quick_messages if qm.present]
    if active_qm:
        print(f"Quick SMS Messages ({len(active_qm)}/{len(cp.quick_messages)} set):")
        for qm in active_qm:
            t = qm.text if len(qm.text) <= 60 else qm.text[:57] + "..."
            print(f"  [{qm.index:2d}] {t!r}")
        print()

    # AES/ARC4 keys (49-byte table)
    programmed = [ek for ek in cp.encrypt_keys if ek.present]
    if programmed:
        print(f"AES/ARC4 Keys ({len(programmed)}/{len(cp.encrypt_keys)} slots programmed):")
        for ktype in ("aes256", "aes128", "arc4"):
            keys = [ek for ek in cp.encrypt_keys if ek.key_type == ktype]
            active = [ek for ek in keys if ek.present]
            if active:
                print(f"  {ktype.upper()} ({len(active)}/16):")
                for ek in keys:
                    status = "SET" if ek.present else "---"
                    print(f"    key {ek.key_number:>2d}: {status}")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p_dump = sub.add_parser("dump", help="Print codeplug summary")
    p_dump.add_argument("bin", help="Input .bin file")
    p_rt = sub.add_parser("roundtrip", help="Verify round-trip parse/serialize")
    p_rt.add_argument("bin", help="Input .bin file")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return

    data = Path(args.bin).read_bytes()
    cp = Codeplug.from_bin(data)

    if args.cmd == "dump":
        dump_summary(cp)
    elif args.cmd == "roundtrip":
        out = cp.to_bin()
        if data == out:
            print("Round-trip OK: output matches input exactly.")
        else:
            diffs = [i for i in range(len(data)) if data[i] != out[i]]
            print(f"MISMATCH: {len(diffs)} byte(s) differ.")
            for i in diffs[:20]:
                print(f"  offset 0x{i:06x}: expected 0x{data[i]:02x}, got 0x{out[i]:02x}")
            if len(diffs) > 20:
                print(f"  ... and {len(diffs) - 20} more")
            sys.exit(1)


if __name__ == "__main__":
    main()
