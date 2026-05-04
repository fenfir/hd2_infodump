# HD2 firmware — Ghidra GUI quickstart

All work products live in this directory (`analysis-opus/`).

## 1. Prepare & import

**Decrypted firmware images** (pick one):

- `v207.perword.bin` — HD-HD2PA-C7000-V2.0.7 (non-GPS variant)
- `v208.perword.bin` — HD-GPS-HD2PA-C7000-V2.0.8-GPS
- `v213.perword.bin` — HD-GPS-HD2PA-C7000-V2.1.3-GPS

In Ghidra (12.0.4):

1. **File → Import File** → pick one of the above
2. **Language**: `CSKY_V2:LE:32:default` (`C-SKY` in the processor dropdown, variant `CSKY_V2`, endian LE, size 32)
3. **Block**: single block, **Base Address `0x00000000`** (confirmed from literal-pool base-detection)
4. Accept import. When it asks **Analyze?**, say **Yes** and take the default analyzer set.
   (The GUI analyzer is more thorough than headless; wait for it to finish.)

## 2. Apply the metadata as labels + comments

The script `ghidra_apply_metadata.py` overlays 200+ HD2-specific annotations from
`metadata.txt` onto the program:

1. **Window → Script Manager**
2. Click the red **+** to add this directory to the script paths, or copy
   `ghidra_apply_metadata.py` into `~/ghidra_scripts/`
3. Run it. It auto-detects v207/v208/v213 from the program name, applies:
   - A **label** at each annotated offset (browsable via Window → Symbol Tree)
   - An **EOL comment** with the free-text note + byte length
   - Defines qualifying regions as ASCII strings so they render in the listing

## 3. Navigate

- Press **G** → type a label name to jump (e.g. `menu_MainSet`, `dlg_save_channel`,
  `mod_libjpeg_errors`, `IARU_R1_RxA`, `m_BandSet_Vox`).
- **Window → Symbol Tree** shows all labels grouped.
- **Window → Defined Strings** gives you every ASCII string with xrefs to each.

## 4. Hunt for menu handlers

Most productive: the top-referenced menu string is `"Vox"` at `0x06e920` (23 xrefs
across the code region — each is a different function loading that address).

1. Go to `0x06e920` (label `m_BandSet_Vox`)
2. Right-click → **References → Show References to Address** — this lists every
   call site. Each is typically inside a menu-handler function.
3. Double-click any entry to jump to the loading `lrw` instruction; press **F** to
   make the containing bytes a function if one isn't already defined; then **Ctrl-E**
   decompile.

Other high-value targets (count = number of direct 4-byte xrefs in v208):

| label                          | xrefs | what it unlocks |
|--------------------------------|------:|-----------------|
| `m_BandSet_Vox` (0x06e920)     | 23    | Band A/B settings handlers |
| `m_BandSet_TxGPSInfo-1` (0x06e903) | 18 | GPS-info menu handlers |
| `m_BandSet_TxGPSInfo` (0x06e904)   | 15 | same area, different offset |
| `mod_dmr_sync_printf` (0x071370)   | —  | DMR sync-word init (grep refs) |
| `mod_tune_data_printf` (0x0707ac)  | —  | RF tune table init |
| `IARU_R1_RxA` (0x06f670)           | —  | amateur-band-limits code |

## 5. Tips

- **Ignore libjpeg**: we proved via exhaustive xref search that no code
  references `mod_libjpeg_errors` or any libjpeg string — it's dead rodata. Don't
  spend time looking for `jpeg_*` functions; they're not in this firmware.
- **μC/OS-III task names** (at `mod_ucosiii`) are referenced by `OS_TaskCreate`
  calls — back-tracing from those names finds the **top-level task setup** function.
- **Boot init sequence**: start at the DMR printf labels (`lbl_SEND_DATA_SYNC_H`
  etc at 0x071370). The function(s) that load these are the boot-time DMR
  initializer — valuable entry point.
- **v207 vs v213 diff**: `diff_v208-v213_dec_w1024.png` shows structurally where
  the two GPS firmware versions diverge. Top ~38% is byte-identical (shared
  bootloader + library code); middle is where v2.1.3 actually changed.

## 6. Files in this directory

- `v{207,208,213}.perword.bin` — decrypted firmware, ready for Ghidra import
- `v{207,208,213}.keybits.bin` — packed per-word N/S key bitmap (18.7 KB each)
- `metadata.txt` — human-editable annotations, input to the apply script
- `ghidra_apply_metadata.py` — the Ghidra Script
- `view.py` / `metadata.txt` — CLI hex viewer with annotations (complements Ghidra)
- `cross_fw_string_catalog.{json,txt}` — 326 cross-firmware string clusters
- `diff_*.png` — visual cross-firmware byte-diff images
