# HR_C7000 BGA Pinmap

Source: `firmware/hr_c7000_manual.md` §1.6 管脚说明.

Top-down view (pin 1 / A1 indicator at upper-left corner of package):

```
         1     2     3     4     5     6     7     8     9    10    11    12    13    14    15    16
       ╔═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╤═════╗
    A  ║[1]  │ ADC1│ ADC3│ ADC6│ ADC7│┌───┐│ DVSS│SPI1 │I2C1 │UART1│PTB27│DVSS │MIC2P│MIC1P│MIC  │DVSS ║
       ║ A1  │ IN  │ IN  │ IN  │ IN  ││TDI││  ─  │MOSI │ SCL │ TX  │     │  ─  │ INP2│ INP1│BIAS │ ─   ║
       ╠═════╪═════╪═════╪═════╪═════╪├───┤╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    B  ║ ADC0│ ADC2│ DVSS│ ADC5│┌───┐│┌───┐│ MISO│ CSN │I2C  │PTB29│PTB26│DB7  │MIC2N│MIC1N│VCAP │VREFP║
       ║ IN  │ IN  │  ─  │ IN  ││TCK│││TDO││ SPI1│SPI1 │ SDA1│     │     │ LCD │ INN2│ INN1│CODEC│CODEC║
       ╠═════╪═════╪═════╪═════╪├───┤╪├───┤╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    C  ║ DVSS│ ADC │ ADC │ ADC4│┌───┐│┌───┐│ DVSS│ SPI1│ UART│PTB28│PTB25│PTB24│ AVDD│AVSS │LINOT│LINOT║
       ║  ─  │AVSS │AVDD3│ IN  ││TMS│││RST││  ─  │ SCLK│ 1RX │     │     │     │CODEC│CODEC│1 LP │2 LP ║
       ╠═════╪═════╪═════╪═════╪└───┘╪└───┘╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    D  ║RTC  │RTC  │LDORTC│ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │AVSS │DVSS │LINOT║
       ║CLKIN│CLKOUT│AVDD3│     │     │     │     │     │     │     │     │     │     │CODEC│  ─  │VSS  ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    E  ║DVSS │DVSS │LDORTC│ ─   │RTC  │DVSS │DVSS │LDO  │LDO  │LDO  │DVSS │DVDD3│DVSS │DVSS │DB5  │DB4  ║
       ║     │     │AVSS3│     │AVSS │     │     │DVDD12│AVDD33│AVSS │     │ 3   │     │     │ LCD │ LCD ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    F  ║USB  │USB  │RTC  │ ─   │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │DVDD3│ ─   │DB3  │DB2  │DB1  ║
       ║ DP  │ DM  │DVDD12│     │     │     │     │     │     │     │     │ 3   │     │ LCD │ LCD │ LCD ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    G  ║DVSS │DVSS │USB  │ ─   │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │ ─   │DB0  │ RD  │ WR  ║
       ║     │     │AVDD3│     │     │     │     │     │     │     │     │     │     │ LCD │ LCD │ LCD ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    H  ║PR_V │ PR_G│DVSS │ ─   │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │LDO  │ ─   │ RS  │ CS  │NRESET║
       ║     │     │     │     │     │     │     │     │     │     │     │AVDD33│     │ LCD │ LCD │ LCD ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    J  ║DACVO│DACVO│DACAV│ ─   │DAC  │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │LDO  │ ─   │PWM2 │DVSS │UART2║
       ║ UTA │ UTB │DD33 │     │VREFP│     │     │     │     │     │     │AVSS │     │     │     │ RX  ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    K  ║ ─   │ ─   │DAC  │ ─   │DAC  │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │LDO  │ ─   │UART2│PTB13│PTB14║
       ║     │     │AVSS │     │VREFN│     │     │     │     │     │     │DVDD12│     │ TX  │     │     ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    L  ║ ─   │DVSS │ADC  │ ─   │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │DVSS │ ─   │PTB15│PTB16│UART3║
       ║     │     │AVDD3│     │     │     │     │     │     │     │     │     │     │     │     │ RX  ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    M  ║ADC  │ADC  │ADCV │ ─   │LDO  │PLLAV│PLLAV│DVSS │DVSS │DVSS │DVDD3│DVDD3│ ─   │UART3│PTB17│PWM1 ║
       ║VINPI│VINMQ│REF  │     │DVDD12│DD1 │SS0  │     │     │     │ 3   │ 3   │     │ TX  │     │     ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    N  ║ADC  │ADC  │ADC  │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │ ─   │NFC  │NFC  │NFC  ║
       ║VINCQ│VINPI│AVSS3│     │     │     │     │     │     │     │     │     │     │ CSN │SCLK │MOSI ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    P  ║ADCVI│ADC  │LDOAV│LDO  │PTB20│PTB23│PTB3 │PTB6 │I2C  │UART0│SPI1 │PTB8 │PTB11│PTB12│NFC  │NFC  ║
       ║NCMI │VINMI│DD33 │AVSS │     │     │     │     │SDA0 │ TX  │MISO │     │     │     │MISO │HOLD ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    R  ║ADC  │POR  │NRESET│PTB19│PTB21│CLK  │PTB2 │PTB5 │I2C  │SPI1 │SPI1 │BS_INT│PTB7 │PTB10│DVSS │NFC  ║
       ║AVDD3│ EN  │ ←★  │     │     │ OUT │     │     │ SCL │ CSN0│MOSI │ OUT │     │     │     │ WP  ║
       ╠═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════╣
    T  ║DVSS │ OSC │ TEST│PTB18│PTB22│PTB0 │PTB1 │PTB4 │UART0│SPI1 │SPI1 │TIME │TIME │PTB9 │PWM0 │DVSS ║
       ║     │CLKIN│MODE │     │     │     │     │     │ RX  │ CSN1│SCLK │SLOTR│SLOTT│     │     │     ║
       ╚═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╧═════╝
```

Row letters skip I, O, Q (BGA convention). 16 rows × 16 columns.

## JTAG cluster (top-left, 3×2 block)

```
       Col 5    Col 6
      ┌─────┬─────┐
   A  │     │ TDI │   ← A6
      ├─────┼─────┤
   B  │ TCK │ TDO │   ← B5, B6
      ├─────┼─────┤
   C  │ TMS │RST_N│   ← C5, C6
      └─────┴─────┘
```

| Ball | Signal     |
| ---- | ---------- |
| A6   | JTG_TDI    |
| B5   | JTG_TCK    |
| B6   | JTG_TDO    |
| C5   | JTG_TMS    |
| C6   | JTG_RST_N  |

Standard CK803S JTAG; works with T-Head DebugServer + generic FT2232H.

## ISP / UART boot loader (115200 8N1)

| Ball | Signal              |
| ---- | ------------------- |
| T9   | UART0 RXD (input)   |
| P10  | UART0 TXD (output)  |
| R3   | NRESET              |
| R2   | POR_EN              |
| T3   | TEST_MODE           |

Manual §2.1: at reset, the boot ROM listens on UART0 for an ISP load. If
no data within timeout, falls through to flash boot.

## External Winbond W25Q512JV SPI (NFC interface)

| Ball | Signal               |
| ---- | -------------------- |
| N14  | NFC_CSN              |
| N15  | NFC_SCLK (≤ 96 MHz)  |
| N16  | NFC_MOSI / IO0       |
| P15  | NFC_MISO / IO1       |
| P16  | NFC_HOLD / IO3       |
| R16  | NFC_WP / IO2         |

## Clocks / power

| Ball   | Signal                       |
| ------ | ---------------------------- |
| T2     | OSC_CLK_IN (24 MHz crystal)  |
| D1, D2 | RTC 32.768 kHz in/out        |
| F1, F2 | USB DP / DM                  |
| G3     | USB AVDD33                   |

DVDD33 (3.3 V digital supply): E12, F12, M11, M12.
LDO_AVDD33 (internal LDO inputs): E9, H12, P3.
DVSS (digital ground): scattered through inner balls of every row.

## Boot mode flow (manual §2.1)

1. Reset asserted via NRESET (or internal POR if POR_EN=1).
2. Boot ROM at `0x00000000-0x0000FFFF` (2 KB) starts.
3. Boot ROM samples UART0 RXD for an ISP program-load handshake.
4. If handshake seen within timeout: load program from UART → SRAM, jump.
5. If timeout: jump to flash boot (XIP at `0x03000000`, the LCSFC mapped
   region — backed by C7000 internal flash, not the external Winbond).

Memory map (from §1.2.3):
- `0x00000000-0x0000FFFF` BOOTROM (2 KB)
- `0x03000000-0x03FFFFFF` LCSFC flash XIP window
- `0x11000000-0x1100FFFF` Modem
- `0x14030000-0x1409FFFF` UART0..UART3 register banks
- `0x16000000-0x1600FFFF` Modem buffer
- `0x18000000-…`          SRAM (320 KB)
