# Ailunce HD2 Firmware Update Protocol

## Hardware

- **SoC**: HR_C7000 (Dahua DH4570), C-SKY CK803S core, 192 MHz
- **Flash**: Winbond W25Q512 (64 MB SPI NOR), JEDEC ID `ef 40 20`
- **Interface**: CH340 USB-to-serial adapter (VID `1a86`, PID `7523`)
- **Debug UART baud**: 120,000 (application firmware; `119200` also
  works — the CH340 maps the CPS `"115200,N,8,1"` string to the same
  rate. See [protocol](protocol) "Serial".)
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

### Firmware obfuscation — XOR algorithm

The raw payloads (after stripping YMODEM framing) are XOR-encrypted with a
stateless per-word predicate: `AilunceFW::ApplyXOR` from `radio_tool`,
ported in `scripts/fw_crypto.py` and `src/fwdb/algorithm.py`:

```
def apply_word(w):
    if w == 0 or w == 0xFFFFFFFF:  return w ^ 0xFFFFFFFF
    if w & (1 << 28):              return w ^ 0x01111111   # KEY_S
    return                              w ^ 0x07777777     # KEY_N
```

Symmetric: the same function encrypts and decrypts. No keystream
period, no position table, no phase. Round-trip vendor `.bin` ->
plaintext -> vendor `.bin` verified byte-identical against every
available firmware image.

#### Decode script

`scripts/fw_crypto.py` implements the algorithm plus 1K-YMODEM
framing in one CLI:

```
scripts/fw_crypto.py decrypt INPUT [-o OUT]      # ymodem-unframe + ApplyXOR
scripts/fw_crypto.py encrypt INPUT [-o OUT] [--frame]
scripts/fw_crypto.py frame   INPUT [-o OUT]
scripts/fw_crypto.py unframe INPUT [-o OUT]
scripts/fw_crypto.py info    INPUT
```

Auto-detects framed vs raw payload by `size % 1029 == 0` + first byte
`0x02 (STX)`.

**Load base**: `0x03000000` (flash XIP start; the LCSFC hardware maps external
flash starting at this address). The firmware image itself starts at offset
`0xd000` within the LCSFC window (VA `0x0300d000`), but Ghidra imports use
file offset `0x00000000` as the import base — see [Ghidra Import Kit](firmware-ghidra-README).

## Integrity-check fall-through patch

The application firmware contains an integrity-check function
`FUN_0304d564` (a.k.a. the boot-time "encryption group" check) that
runs 7 sequential checks against the activation NVRAM block. By
default the first failing check prints `加密组别 NN: 算法：%x,读取：%x`
and either inlines a function epilogue or branches to the shared
epilogue at `0x0304d57a`, which pops the frame and returns early — so
on an unactivated radio only one `加密组别` line is ever seen.

`scripts/patch_crypto_check.py` patches the plaintext firmware so all
7 checks print every boot. This was essential for reverse-engineering
the per-group format strings and the g22 / g50 NVRAM slots.

### Strategy

At each of the 6 non-final failure sites, the first 2 bytes of the
post-printf cleanup (a `movi r0, 0` at every site, encoded
`00 30`) are replaced with a **CSKY V2 16-bit `br`** to the entry of
the next check. The stack frame stays intact (no `addi`/`pop` runs
along the failure path) and the natural end-of-function epilogue at
`0x0304d57a` cleans up once when site 7 completes. Site 7 is
unchanged.

### CSKY V2 16-bit `br` encoding

```
br <target> placed at PC:
    disp   = target - PC                   (must be even)
    hwdisp = disp / 2                      (signed, range [-512, 512))
    enc    = 0x0400 | (hwdisp & 0x3FF)     (little-endian 16-bit)
```

### Patch table

Six 2-byte writes, all from `00 30` to `0x04xx`:

| Failure site VA | Next-check VA | Note                |
|-----------------|---------------|---------------------|
| `0x0304d5ea`    | `0x0304d5f0`  | check 1 -> check 2  |
| `0x0304d648`    | `0x0304d65a`  | check 2 -> check 3  |
| `0x0304d6ae`    | `0x0304d6b2`  | check 3 -> check 4  |
| `0x0304d700`    | `0x0304d70a`  | check 4 -> check 5  |
| `0x0304d762`    | `0x0304d7ba`  | check 5 -> check 6  |
| `0x0304d82c`    | `0x0304d830`  | check 6 -> check 7  |

### Optional version-string bump

The same script can also rewrite the embedded firmware-ID string so
that `GetVer` reports a distinguishable version (default
`V3.0.1-GPS.bin`). Two single-byte writes at file offsets `0x06de74`
and `0x06de78` (the `2` and `7` digits of `V2.0.7-GPS.bin`).

### Outputs

The script emits three files in `firmware/`:

- `PATCHED.decrypted.bin` — plaintext after patch (614,400 B)
- `PATCHED.encrypted.payload.bin` — `ApplyXOR`-encrypted plaintext
- `PATCHED.ymodem-framed.bin` — 600 × 1029 B ready for
  `scripts/fw_flash.py`

Flashed to hardware and verified: all 7 `加密组别` debug lines print
every boot, the radio completes normal init, and no stack corruption
is observed.

See also: [firmware-summary](firmware-summary)
"Encryption / boot-time integrity checks" and [protocol](protocol)
"`Activa` — radio activation".

## HR_C7000 Architecture

Confirmed from HR_C7000 user manual (Dahua, 2017) and DR5800 service manual:

- **CPU**: C-SKY CK803S — Chinese RISC processor (T-Head/Alibaba), **NOT ARM**
  - 32-bit, 16/32-bit mixed-length instruction set, 192 MHz max, 3-stage pipeline
  - Ghidra C-SKY module: https://github.com/leommxj/ghidra_csky
  - C-SKY arch guide: https://github.com/c-sky/csky-doc
- **SRAM**: 288 KB at `0x00010000`
- **Flash**: External SPI NOR via LCSFC, XIP at `0x03000000` (up to 16 MB address space)
- **Boot ROM**: 2 KB at `0x00000000`

Full memory map, PIC interrupt table, IO pin mux, and boot flow: see [HR_C7000 Reference Tables](firmware-c7000-reference).

### Boot process / JTAG / Flash chips

See [HR_C7000 Reference Tables](firmware-c7000-reference) and [HR_C7000 Pinmap](firmware-c7000-pinmap).

## Debug UART (120000 baud)

This is a **separate interface** from the CPS codeplug protocol at 119200 baud
(documented in [protocol](protocol)). The programming cable exposes the
application firmware's debug UART at **120000 baud** 8N1 (not UART0; likely
UART1 or UART3).

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

## Source

- Protocol captured from: `fw_update.pcapng` (310 packets, ~32 seconds, USB bus 3)
- Protocol decompiled from: `AilunceHD2-FW-V2.1.3-GPS.exe` (.NET 8 WinForms app, `HD2FW.dll`)
- Bootloader menu captured live from radio at 57600 baud
- Debug UART captured live at 120000 baud
- Architecture confirmed from: HR_C7000 user manual (Dahua, 2017), DR5800 service manual,
  AtomXL reverse engineering project (https://github.com/M17-Project/AtomXL-reverse-engineering)
- Firmware extracted from updater .exe resources; raw binaries in `firmware/` directory
