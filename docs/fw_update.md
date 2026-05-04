# Ailunce HD2 Firmware Update Protocol

## Hardware

- **SoC**: HR_C7000 (Dahua DH4570), C-SKY CK803S core, 192 MHz
- **Flash**: Winbond W25Q512 (64 MB SPI NOR), JEDEC ID `ef 40 20`
- **Interface**: CH340 USB-to-serial adapter (VID `1a86`, PID `7523`)
- **Debug UART baud**: 120,000 (application firmware)
- **Firmware update baud**: 57,600 (bootloader)
- **Line settings**: 8N1

## Bootloader Menu

Enter firmware update mode via key combo at power-on. The bootloader presents
a menu at **57600 baud** (send any key to see it, or it appears after sending `1`):

```
Version: HD-GPS-HD2PA-C7000-V2.1.3-GPS.bin
==========================================================

========================= Main Menu ==================================

  Through UART Download Image To the HR_C7000 CHIP Flash ----------- 1

  Through USB Download Image To the HR_C7000 CHIP Flash ------------ 2

  Execute The New Program ------------------------------------------ 3

======================================================================
```

- **Option 1**: YMODEM-CRC receive over UART (write firmware to flash)
- **Option 2**: USB download (write firmware to flash via USB)
- **Option 3**: Jump to the newly flashed firmware

This is a **write-only** bootloader — no read/dump capability. The banner text is
`"UART boot mode"` (previously misread as `"T boot mode"` when captured at 115200 baud).

After selecting option 1, the radio outputs:
```
========================== UART boot mode ============================

Waiting for the file to be sent ... (press 'a' to abort)
```
Then sends YMODEM-CRC `C` (0x43) every ~263ms, waiting for the host to begin transfer.

## YMODEM Transfer Protocol

The transfer uses a **modified YMODEM** protocol with CRC-16/CCITT (poly `0x1021`,
initial value `0x0000`).

### Embedded firmware in the updater

The updater exe (`AilunceHD2-FW-V2.1.3-GPS.exe`) is a .NET 8 WinForms app containing
the firmware binary as an embedded resource: `HD2FW.Res.HD-GPS-HD2PA-C7000-V2.1.3-GPS.bin`.
It can also load from a file path.

- Build path: `D:\Workspaces\HD2\HD2-FW-V2.0.7-GPS\`
- Uses `RJCP.SerialPortStream` v3.0.1 for serial I/O
- Does not work under Wine (`set_queue_size` unimplemented, `EV_RXFLAG` not handled)

### Packet structure

```
[STX] [PacketNum] [InvPacketNum] [Data...] [CRC-Hi] [CRC-Lo]
```

- **STX**: `0x01` (SOH) — used for initial and closing packets
- **PacketNum**: sequence number (0-255, wraps at 256)
- **InvPacketNum**: `255 - PacketNum`
- **Data**: payload bytes
- **CRC**: CRC-16/CCITT over the data portion only

### Phase 1: Initial packet (block 0)

SOH packet with `packetNumber=0, invertedPacketNumber=255, dataSize=128`.

Data payload (128 bytes, zero-padded):
```
[filename\0][filesize_string\0][zero padding to 128 bytes]
```

- **filename**: e.g. `HD-GPS-HD2PA-C7000-V2.1.3-GPS.bin`
- **filesize**: decimal string, computed as `(stream_length / 1029) * 1024`

After sending: read+discard one byte (ACK), verify next byte is `C` (0x43).

### Phase 2: Data packets

The firmware `.bin` files are pre-framed as YMODEM packets. Each 1029-byte chunk from
the file is written directly to serial — the file already contains the
`[STX=0x02][Seq][~Seq][1024 data][CRC16]` framing.

For each chunk:
1. Write 1029 bytes to serial
2. Read one byte; expect `0x07` (BEL) as ACK
3. If not `0x07`, abort

### Phase 3: EOT and closing packet

1. Send `0x04` (EOT), read and discard response
2. Send `0x04` (EOT) again, read and discard response
3. Send closing SOH packet: `[0x01][0x00][0xFF][128 zero bytes][CRC-Hi][CRC-Lo]`
4. Read one byte; expect `0x07` (ACK)
5. Close serial port, report success

### ACK byte

The radio uses `0x07` (BEL) instead of the standard YMODEM `0x06` (ACK).

## Firmware Binary Format

The `.bin` files are **pre-framed YMODEM packets**, not raw flash images:

```
[STX=0x02] [Seq] [~Seq] [1024 bytes payload] [CRC16-Hi] [CRC16-Lo]
```

- CRC-16/CCITT over the 1024-byte payload — verified correct on all blocks
- Sequence numbers start at 1, wrap at 256
- GPS firmware: 600 blocks (617,400 bytes framed, 614,400 bytes raw)
- Non-GPS firmware: 592 blocks (609,168 bytes framed, 606,208 bytes raw)
- Trailing 0xFF = erased flash padding

### Extracted firmware resources

| Resource name                          | Framed size | Raw size | Type    |
|----------------------------------------|-------------|----------|---------|
| `HD-HD2PA-C7000-V2.0.7.bin`           | 609,168     | ~599 KB  | Non-GPS |
| `HD-GPS-HD2PA-C7000-V2.0.8-GPS.bin`   | 617,400     | ~606 KB  | GPS     |
| `HD2-FW-V2.0.9-GPS.bin`               | 617,400     | ~606 KB  | GPS     |
| `HD-GPS-HD2PA-C7000-V2.1.3-GPS.bin`   | 617,400     | ~606 KB  | GPS     |

### Firmware obfuscation — XOR key found

The raw payloads (after stripping YMODEM framing) are **XOR-obfuscated** with a
**word-level (4-byte) XOR cipher** — NOT a simple repeating 4-byte key.

#### Key structure

Two sub-keys alternate based on cycle position:

```
key_N = [0x77, 0x77, 0x77, 0x07]  (normal — most positions)
key_S = [0x11, 0x11, 0x11, 0x01]  (special — ~116 specific positions per cycle)
```

The cipher has a **period of 1844 words (7376 bytes)**. For each 4-byte word at
file byte offset `i`:

```
cycle_pos = (i // 4 + phase) % 1844
key = key_S if cycle_pos in S_SLOTS else key_N
word[i..i+3] ^= key
```

> **Note**: An earlier analysis concluded period=922. This was wrong. At word 102466
> (cp=124 mod 922, an S position), key_N is used; at word 110764 (cp=124 mod 922,
> also an S position), key_S is used. A 9-cycle gap rules out period=922. With
> period=1844: word 102466 is cp=1046 (not in S_SLOTS → key_N) and word 110764
> is cp=124 (in S_SLOTS → key_S). Consistent.

S_SLOTS (~116 positions in the 1844-word cycle that use key_S), empirically derived
from known-plaintext analysis (POSIX errno strings, RTOS strings, UI labels):

```python
# first half [0, 921] — 90 positions
{21, 54, 55, 57, 66, 70, 102, 106, 124, 125, 213, 233, 236, 239, 241, 250,
 258, 272, 275, 290, 292, 295, 297, 300, 303, 306, 310, 312, 316, 323, 326,
 328, 329, 336, 339, 356, 370, 372, 375, 484, 487, 495, 498, 503, 509, 514,
 522, 540, 546, 551, 597, 600, 644, 654, 656, 657, 660, 662, 667, 682, 687,
 690, 693, 710, 716, 721, 725, 731, 734, 758, 804, 808, 811, 816, 820, 827,
 830, 847, 848, 851, 852, 857, 859, 864, 866, 872, 877, 880, 885, 902, 903,
 912, 917}

# second half [922, 1843] — 26 verified positions
# errno table region (922–1006): fully mapped
# UI string region (1343–1383): partially mapped
# positions 1007–1342 and 1384–1843: still under investigation, assumed key_N
{923, 929, 934, 940, 943, 948, 949, 952, 956, 960, 970, 972, 976, 978, 982,
 991, 995, 999, 1005, 1006,
 1343, 1353, 1362, 1364, 1374, 1383}
```

Authoritative set is in `firmware/decode_fw.py` (`S_SLOTS` frozenset).

#### Phase per firmware file

The cipher starts at a different cycle offset ("phase") per firmware file:

| Firmware file                              | Phase | Status                          |
|--------------------------------------------|-------|---------------------------------|
| `HD-HD2PA-C7000-V2.0.7.raw.bin`           | 0     | Confirmed                       |
| `HD-GPS-HD2PA-C7000-V2.0.8-GPS.raw.bin`   | 0     | Untested (assumed same as V2.0.7) |
| `HD2-FW-V2.0.9-GPS.raw.bin`               | 0     | Untested (assumed same as V2.0.7) |
| `HD-GPS-HD2PA-C7000-V2.1.3-GPS.raw.bin`   | 881   | Tentative — confirmed for period=922; needs re-verification with period=1844 |

Phase was determined by known-plaintext crib dragging using the firmware filename
string embedded near the end of each file. Confirmed strings in V2.0.7 include:
"Encryption" ×5, "No such file or directory", "Shift Up/Freq", "Encrypt Type/NO",
"DMR Slot", "Promiscuous", "FM radio", "Target Radio", "Private Call",
"Radio WakeUp", "Unavailable", "Priority", "Quick Text".

#### Decode script

Use `firmware/decode_fw.py` — auto-detects phase from filename:

```
python3 firmware/decode_fw.py <input.raw.bin> <output.dec.bin>
```

Decrypted files in `analysis/` directory:
- `HD-HD2PA-C7000-V2.0.7.dec.bin`
- `HD-GPS-HD2PA-C7000-V2.0.8-GPS.dec.bin`  (phase 0, untested)
- `HD-GPS-HD2PA-C7000-V2.1.3-GPS.dec.bin`
- `HD2-FW-V2.0.9-GPS.dec.bin`              (phase 0, untested)

**Load base**: `0x03000000` (flash XIP start). Confirmed by self-referential pointer
scan: 3711 LE 32-bit values in the decrypted V2.0.7 firmware fall within
`[0x03000000, 0x03000000 + filesize)`, far exceeding any other candidate base.
This matches the hardware memory map (LCSFC XIP at `0x03000000`).

Ghidra analysis: `CSKY_V2:LE:32:default`, base `0x03000000`, using pre-decrypted
files from `analysis/`. Prior Ghidra analysis was on encrypted data — all prior
results are invalid.

## HR_C7000 Architecture

Confirmed from HR_C7000 user manual (Dahua, 2017) and DR5800 service manual:

- **CPU**: C-SKY CK803S — Chinese RISC processor (T-Head/Alibaba), **NOT ARM**
  - 32-bit, 16/32-bit mixed-length instruction set, 192 MHz max, 3-stage pipeline
  - Ghidra C-SKY module: https://github.com/leommxj/ghidra_csky
  - C-SKY arch guide: https://github.com/c-sky/csky-doc
- **SRAM**: 288 KB at `0x00010000`
- **Flash**: External SPI NOR via LCSFC, XIP at `0x03000000` (up to 16 MB address space)
- **Boot ROM**: 2 KB at `0x00000000`

### Memory map

From HR_C7000 User Manual (Dahua, 2017), table 1 地址映射关系:

| Start        | End          | Function          | Size   | Notes                  |
|--------------|--------------|-------------------|--------|------------------------|
| `0x00000000` | `0x0000FFFF` | Boot ROM          | 2 KB   |                        |
| `0x00010000` | `0x00057FFF` | IRAM (SRAM)       | 288 KB |                        |
| `0x03000000` | `0x03FFFFFF` | Flash XIP (LCSFC) | 16 MB  | Firmware load base     |
| `0x11000000` | `0x1100FFFF` | Modem             | 64 KB  |                        |
| `0x12000000` | `0x1200FFFF` | i8080             | 64 KB  |                        |
| `0x13000000` | `0x1303FFFF` | USB               | 256 KB |                        |
| `0x14000000` | `0x1400FFFF` | TIMER             | 64 KB  |                        |
| `0x14010000` | `0x1401FFFF` | WDG (watchdog)    | 64 KB  |                        |
| `0x14020000` | `0x1402FFFF` | GPIOA             | 64 KB  |                        |
| `0x14030000` | `0x1403FFFF` | UART0             | 64 KB  | Debug/boot UART        |
| `0x14040000` | `0x1404FFFF` | UART1             | 64 KB  |                        |
| `0x14050000` | `0x1405FFFF` | UART2             | 64 KB  |                        |
| `0x14060000` | `0x1406FFFF` | I2C0              | 64 KB  |                        |
| `0x14070000` | `0x1407FFFF` | I2C1              | 64 KB  |                        |
| `0x14080000` | `0x1408FFFF` | I2C2              | 64 KB  | Internal RTC dedicated |
| `0x14090000` | `0x1409FFFF` | UART3             | 64 KB  |                        |
| `0x140A0000` | `0x140AFFFF` | SPI Master 0      | 64 KB  |                        |
| `0x140B0000` | `0x140BFFFF` | SPI Master 1      | 64 KB  |                        |
| `0x140C0000` | `0x140CFFFF` | PWM               | 64 KB  |                        |
| `0x140D0000` | `0x140DFFFF` | ADC               | 64 KB  |                        |
| `0x140E0000` | `0x140EFFFF` | SPI2              | 64 KB  |                        |
| `0x140F0000` | `0x140FFFFF` | DAC               | 64 KB  |                        |
| `0x14100000` | `0x1410FFFF` | GPIOB             | 64 KB  |                        |
| `0x14110000` | `0x1411FFFF` | GPIOC             | 64 KB  |                        |
| `0x14120000` | `0x1412FFFF` | SPI Slave 0       | 64 KB  |                        |
| `0x14130000` | `0x1413FFFF` | SPI Slave 1       | 64 KB  |                        |
| `0x14140000` | `0x1414FFFF` | SPI Slave 2       | 64 KB  |                        |
| `0x14150000` | `0x1415FFFF` | SPI Master 3      | 64 KB  | EFUSE dedicated        |
| `0x15000000` | `0x1500FFFF` | SDIO              | 64 KB  |                        |
| `0x16000000` | `0x1600FFFF` | Modem Buffer      | 64 KB  |                        |
| `0x17000000` | `0x1700FFFF` | PIC (interrupts)  | 64 KB  |                        |
| `0x18000000` | `0x18007FFF` | SRAM (SAHB)       | 32 KB  |                        |

### Boot process

1. CPU starts from Boot ROM at `0x00000000` at 24 MHz
2. Boot ROM sends data on UART0 (115200 baud), waits for host response
3. If host responds: enters debug mode (read/write/download/jump/exit commands)
4. If no response: checks flash offset 0x00 for `DH_FLAG` magic
5. If found: reads jump address from offset 0x04, jumps to firmware
6. UART0 (boot ROM) is **not accessible** on the programming cable

### JTAG

5-wire CK803S JTAG (TCK, TMS, TDI, TDO, RST_N), enabled by default.
Requires a CK-Link debugger (not ARM J-Link). Pins on C7000 BGA:
C5 (TMS), B5 (TCK), A6 (TDI), B6 (TDO), C6 (RST_N).

### Flash chips (from DR5800 service manual, HD2 may differ)

- **W25Q64** (8 MB) on SPI0 — codeplug, calibration, channel data
- **W25Q128** (16 MB) on NFC_SPI — firmware and voice prompts
- HD2 confirmed: **W25Q512** (64 MB) via JEDEC ID in boot dump

## Debug UART (120000 baud)

The programming cable exposes the application firmware's debug UART at
**120000 baud** 8N1 (not UART0; likely UART1 or UART3).

### Boot diagnostic dump

On power-on, the firmware outputs ~1.4 KB of diagnostic text preceded by
an 8-byte binary header (`02 24 00 03 00 10 00 03`):

```
*I2C2_IC_FS_SCL_HCNT: 2c.
*I2C2_IC_FS_SCL_LCNT: 34.
*I2C2_IC_CON: 65.
*I2C2_IC_TX_TL: 6.
*I2C2_IC_RX_TL: 6.
*I2C2_IC_INTR_MASK: 4
JEDEC_ID[0]: ef.
JEDEC_ID[1]: 40.
JEDEC_ID[2]: 20.
b1FlashIC512M: 1.
g_tune_data_struct.VolumeDMR: 34.
g_tune_data_struct.VolumeFMW: 5f.
g_tune_data_struct.VolumeFMN: 5f.
g_tune_data_struct.u18Brightness[0]: 1220.
g_tune_data_struct.u18Brightness[1]: 2136.
...
g_tune_data_struct.u18Brightness[9]: 9999.
g_tune_data_struct.u8QTSampleNormal: 255.
b1PriScan: 0.
u16PriScanChannel: 65535.
u8KeyPF3_S: 0.
u8KeyPF3_L: 0.
UID: 0.0.0.0.
UID: 0.0.1d.5e.
ADC_CONTROL: 41c3.
DAC_CONTROL: 8000001f.
RX_IF_FREQ: bb800.
*SEND_DATA_SYNC_H: d7557f.
*SEND_DATA_SYNC_L: 5ff7f5.
*SEND_RC_SYNC_H: 77d55f.
*SEND_RC_SYNC_L: 7dfd77.
*RECV_MS_SYNC_H: d5d7f7.
*RECV_MS_SYNC_L: 7fd757.
*RECV_BS_SYNC_H: dff57d.
*RECV_BS_SYNC_L: 75df5d.
*RECV_TDMA1_SYNC_H: 80f7fdd5.
*RECV_TDMA1_SYNC_L: ddfd55.
*RECV_TDMA2_SYNC_H: 80d7557f.
*RECV_TDMA2_SYNC_L: 5ff7f5.
*RECV_RC_SYNC_H: 77d55f.
*RECV_RC_SYNC_L: 7dfd77.
u16AF_BIAS_OUTVALUE: 74c.
```

### Shutdown message

On power-off, sends 3 bytes: `51 81 00`.

### Commands

Only one command is accepted while running:
- **`V\r\n`** (or `AT+VERSION\r\n` / `AT+DMOVERQ\r\n`) — returns firmware version string

No memory read/write or other debug commands are available.

## Accessing Decrypted Firmware

The firmware update `.bin` files are obfuscated for transport. The bootloader decrypts
them before writing to flash. To obtain the decrypted firmware for reverse engineering:

1. **SPI flash clip** — read the W25Q512 externally with a CH341A or similar programmer.
   Safest approach, no risk of bricking. The decrypted firmware lives at flash offset
   corresponding to `0x03000000` in the memory map.
2. **JTAG** — connect to CK803S JTAG pads on the PCB (requires CK-Link debugger).
   Can read flash, RAM, and registers. Pins default to JTAG unless firmware reconfigures.
3. **Boot ROM UART0** — if UART0 test pads can be found on the PCB (pins T9/P10 on BGA),
   the 2 KB boot ROM at 115200 baud has read/write/download/jump commands.
   Not accessible via the programming cable.

## Firmware Reverse Engineering (Ghidra)

### Layout

- **File**: `firmware/HD-GPS-HD2PA-C7000-V2.1.3-GPS.raw.bin` (YMODEM framing stripped)
- **Size**: 606,600 bytes (0x94188)
- **Logical base**: `0x03700000` (confirmed from vector table pointer values)
- **No encryption, no compression** — entropy 7.0-7.5 bits throughout; consistent with
  compiled CK803S code. No null-terminated ASCII strings found (strings likely stored
  as encoded Chinese text or via indices into a string table).

### Memory map

| Offset | Logical addr | Description |
|--------|-------------|-------------|
| `+0x0000` | `0x03700000` | Startup/init code (0x78 bytes) |
| `+0x0078` | `0x03700078` | `0xFFFFFFFF` sentinel |
| `+0x007c` | `0x0370007c` | Vector table (32-bit pointers, little-endian) |
| `+0x0180` | `0x03700180` | Main code begins |
| `+0x066000` | `0x03766000` | Low-entropy data region (0x18000 bytes) — lookup tables (RGB palette, signal tables, etc.) |
| `+0x07e000` | `0x0377e000` | Code resumes |
| `+0x094188` | — | End of file |

### Vector table (`+0x007c`)

- **Only one unique ISR**: `vec[0]` → `0x03770f4b` (file `+0x70f4b`)
- All other vectors → `0x03777377` (file `+0x77377`, default handler)
- 45 infinite loops (`br . = 0xFE07`) scattered throughout — default ISR stubs
- 262 function prologues (`push r15 / push r4-r15` patterns) identified

### Ghidra setup

- Language: `CSKY_V2:LE:32:default`
- Extension: `~/.config/ghidra/ghidra_12.0.4_NIX/Extensions/CSKY/`
- **Extension bug fixed**: `mvcv` in `16b_data.sinc` had overly strict `i16_r4_rx_n = 0b0000`
  constraint that prevented decoding the first startup instruction (`0x665b` = `mvcv r9`).
  Removed that constraint — extension now decodes the startup code.
- 4 remaining unknown 32-bit opcodes (sop values not in extension): minor gaps.
- Scripts: `pylunce/fw_scan.py` (pure Python, no Ghidra) and `pylunce/fw_analyze.py` (PyGhidra).

## Source

- Protocol captured from: `fw_update.pcapng` (310 packets, ~32 seconds, USB bus 3)
- Protocol decompiled from: `AilunceHD2-FW-V2.1.3-GPS.exe` (.NET 8 WinForms app, `HD2FW.dll`)
- Bootloader menu captured live from radio at 57600 baud
- Debug UART captured live at 120000 baud
- Architecture confirmed from: HR_C7000 user manual (Dahua, 2017), DR5800 service manual,
  AtomXL reverse engineering project (https://github.com/M17-Project/AtomXL-reverse-engineering)
- Firmware extracted from updater .exe resources; raw binaries in `firmware/` directory
