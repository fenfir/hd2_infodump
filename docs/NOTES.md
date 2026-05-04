# HD1 / HD2 reverse-engineering notes

Detailed reference docs:

- [Wire protocol](docs/protocol.md) — serial settings, frame layouts,
  checksums, read/write families, timing.
- [Address space + bitmap + kill state](docs/address-space.md) — region
  map, packed `.bin` ordering, dual channel-presence bitmap, anti-tamper
  self-destruct.
- [Channel slot format](docs/channels.md) — bit-level channel layout,
  inline Rx List, VFOs.
- [Records: contacts, zones, group aliases, Radio IDs](docs/records.md)
- [Radio settings](docs/settings.md)

## Open questions

- VFO-B CH-Mode and other VFO-B-only settings live in an unmapped region
  (probably radio `0xE800`).
- Group Alias `+0x0A` 4-byte field — partial decode (looks like a
  contact reference; "default contact"?).
- `table_4000` (1 KB) beyond Radio IDs — unknown.
- `table_428x` (3 KB) — unknown.
- `table_1dfx` residual — Quick Messages occupy first ~3.2 KB (`0x1DF8+0xDC`,
  200 B × 16 slots); purpose of remaining ~8.8 KB unknown.
- Channel `+0x12` byte's role beyond GPS-contact index — unconfirmed.
- Many settings bytes unmapped — see "Still unmapped" table in `docs/settings.md`.
- DTMF digit-sequence tables (per-channel index is mapped; actual digit
  sequences are not). 2-tone / 5-tone tables also unmapped.
- Emergency Alarm type at `0x299D` bit 1 (clear=Remote, set=Local ✓);
  Emergency key functions at `0x29AE`/`0x29AF` (same enum as Key Define).
