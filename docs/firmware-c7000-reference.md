# HR_C7000 Reference Tables

Source: `HR_C7000_v2.7_en.pdf` (734-page user guide).

## 1. Memory map — MMIO base addresses (§4.5.3, Table 26)

| Start       | End         | Function                      | Size   |
| ----------- | ----------- | ----------------------------- | ------ |
| 0x00000000  | 0x0000FFFF  | Boot ROM                      | 2 KB   |
| 0x00010000  | 0x00057FFF  | IRAM                          | 288 KB |
| 0x03000000  | 0x03FFFFFF  | LCSFC (flash XIP)             | 16 MB  |
| 0x11000000  | 0x1100FFFF  | **Modem / System Control**    | 64 KB  |
| 0x12000000  | 0x1200FFFF  | i8080 (LCD parallel bus)      | 64 KB  |
| 0x13000000  | 0x1303FFFF  | **USB device controller**     | 256 KB |
| 0x14000000  | 0x1400FFFF  | TIMER (×6)                    | 64 KB  |
| 0x14010000  | 0x1401FFFF  | WDG (Watchdog)                | 64 KB  |
| 0x14020000  | 0x1402FFFF  | **GPIOA**                     | 64 KB  |
| **0x14030000** | 0x1403FFFF | **UART0** (boot ROM port)  | 64 KB  |
| 0x14040000  | 0x1404FFFF  | UART1                         | 64 KB  |
| 0x14050000  | 0x1405FFFF  | UART2                         | 64 KB  |
| 0x14060000  | 0x1406FFFF  | I2C0                          | 64 KB  |
| 0x14070000  | 0x1407FFFF  | I2C1                          | 64 KB  |
| 0x14080000  | 0x1408FFFF  | I2C2 (internal RTC)           | 64 KB  |
| 0x14090000  | 0x1409FFFF  | UART3                         | 64 KB  |
| 0x140A0000  | 0x140AFFFF  | **SPI Master 0**              | 64 KB  |
| 0x140B0000  | 0x140BFFFF  | **SPI Master 1**              | 64 KB  |
| 0x140C0000  | 0x140CFFFF  | PWM                           | 64 KB  |
| 0x140D0000  | 0x140DFFFF  | ADC                           | 64 KB  |
| 0x140E0000  | 0x140EFFFF  | SPI2                          | 64 KB  |
| 0x140F0000  | 0x140FFFFF  | DAC                           | 64 KB  |
| 0x14100000  | 0x1410FFFF  | GPIOB                         | 64 KB  |
| 0x14110000  | 0x1411FFFF  | GPIOC                         | 64 KB  |
| 0x14120000  | 0x1412FFFF  | SPI Slave 0                   | 64 KB  |
| 0x14130000  | 0x1413FFFF  | SPI Slave 1                   | 64 KB  |
| 0x14140000  | 0x1414FFFF  | SPI Slave 2                   | 64 KB  |
| 0x14150000  | 0x1415FFFF  | SPI Master 3 (EFUSE only)     | 64 KB  |
| 0x15000000  | 0x1500FFFF  | SDIO                          | 64 KB  |
| 0x16000000  | 0x1600FFFF  | **Modem Buffer**              | 64 KB  |
| 0x17000000  | 0x1700FFFF  | **PIC (interrupt controller)**| 64 KB  |
| 0x18000000  | 0x18007FFF  | SRAM on SAHB                  | 32 KB  |

## 2. PIC interrupt source assignment (§4.7.3, Table 30)

CSKY V2 reserves vector slots 0-31 for CPU exceptions (reset, NMI, traps).
PIC interrupts start at vector 32:

| IRQ # | Source              | Vector # | File offset (vec table @ 0x06e000) |
| ----- | ------------------- | -------- | ---------------------------------- |
|  0    | reserved            | 32       | 0x06e080                            |
|  1    | TIMER_1             | 33       | 0x06e084                            |
|  2    | TIMER_2             | 34       | 0x06e088                            |
|  3    | TIMER_3             | 35       | 0x06e08c                            |
|  4    | TIMER_4             | 36       | 0x06e090                            |
|  5    | TIMER_5             | 37       | 0x06e094                            |
|  6    | TIMER_6             | 38       | 0x06e098                            |
|  7    | I2C1                | 39       | 0x06e09c                            |
|  8    | I2C0                | 40       | 0x06e0a0                            |
|  9    | I2C2                | 41       | 0x06e0a4                            |
| 10    | UART1               | 42       | 0x06e0a8                            |
| 11    | UART2               | 43       | 0x06e0ac                            |
| 12    | UART0               | 44       | 0x06e0b0                            |
| 13    | UART3               | 45       | 0x06e0b4                            |
| 14    | GPIOB               | 46       | 0x06e0b8                            |
| 15    | GPIOA               | 47       | 0x06e0bc                            |
| 16    | SPI0                | 48       | 0x06e0c0                            |
| 17    | GPIOC               | 49       | 0x06e0c4                            |
| 18    | PWM                 | 50       | 0x06e0c8                            |
| 19    | RTC                 | 51       | 0x06e0cc                            |
| 20    | SDIO                | 52       | 0x06e0d0                            |
| 21    | USB                 | 53       | 0x06e0d4                            |
| 22    | SPI1                | 54       | 0x06e0d8                            |
| 23    | SPI2                | 55       | 0x06e0dc                            |
| 24    | LCSFC               | 56       | 0x06e0e0                            |
| 25    | DAC                 | 57       | 0x06e0e4                            |
| 26    | ADC                 | 58       | 0x06e0e8                            |
| 27    | PCM_rd_data_interp  | 59       | 0x06e0ec                            |
| 28    | PCM_wr_data_interp  | 60       | 0x06e0f0                            |
| 29    | **System_inter**    | 61       | 0x06e0f4                            |
| 30    | Time_slot_inter_tx  | 62       | 0x06e0f8                            |
| 31    | Time_slot_inter_rx  | 63       | 0x06e0fc                            |
| 32    | **Rf_tx_inter**     | 64       | 0x06e100                            |
| 33    | **Rf_rx_inter**     | 65       | 0x06e104                            |
| 34    | SlaveSPI0           | 66       | 0x06e108                            |
| 35    | SlaveSPI1           | 67       | 0x06e10c                            |
| 36    | SlaveSPI2           | 68       | 0x06e110                            |
| 37    | Codec_interp        | 69       | 0x06e114                            |

PIC controller registers (base 0x17000000):
| Off  | Name        | Notes |
| ---- | ----------- | ----- |
| 0x00 | PIC_MODE    | bit-per-IRQ trigger mode (1=edge, 0=level) for IRQ 0..31 |
| 0x04 | PIC_PO      | trigger polarity for IRQ 0..31 |
| 0x08 | PIC_MASK    | mask enable for IRQ 0..31 |
| 0x0c | PIC_VECTOR  | **vector base address** (the 0x06e000 in our case) |
| 0x10 | PIC_COW1    | end-of-interrupt |
| 0x14-0x30 | PIC_PRIOR0..31 | priorities (4 IRQs per reg) |
| 0x34 | PIC_COW2    | control |
| 0x38 | PIC_SYNC    | async process control |
| 0x3c | PIC_FFLAG_L | fast-int low (unused on C7000) |
| 0x40 | PIC_RECORD_SEL | which IRQ to count |
| 0x44 | PIC_INT_ST  | IRQ 0..31 status |
| 0x48 | PIC_INT_ST_1 | IRQ 32..63 status |
| 0x4c | PIC_INT_CNT | int count |
| 0x60 | PIC_MODE_1  | trigger mode IRQ 32..63 |
| 0x64 | PIC_PO_1    | polarity IRQ 32..63 |
| 0x68 | PIC_MASK_1  | mask IRQ 32..63 |
| 0x6c-0x88 | PIC_PRIOR32..63 | |
| 0x8c | PIC_FFLAG_H | fast-int high |

## 3. Baseband sub-interrupt vectors (§4.6.3 Tables 28-29)

Main baseband interrupts (mapped onto the PIC):
| # | Name             | Source  | Description |
| - | ---------------- | ------- | ----------- |
| 1 | RF_TX_INTERP     | IRQ 32  | RF send start interrupt |
| 2 | RF_RX_INTERP     | IRQ 33  | RF receive start interrupt |
| 3 | SYS_INTERP       | IRQ 29  | System sub-interrupt (see SYS_INTERP_LIST below) |
| 4 | TIME_SLOT_TX_INTERP | IRQ 30 | 30 ms TX time slot |
| 5 | TIME_SLOT_RX_INTERP | IRQ 31 | 30 ms RX time slot |
| 6 | PCM_WR_INTERP    | IRQ 28  | Codec audio data write |
| 7 | PCM_RD_INTERP    | IRQ 27  | Codec audio data read |

SYS_INTERP_LIST sub-interrupts (read at 0x11000398):
| Bit | Name                  | Description |
| --- | --------------------- | ----------- |
| 0   | dll_rdy_interp_tx     | Layer 2 send processing |
| 1   | dll_rdy_interp_rx     | Layer 2 receive processing |
| 2   | dll_latelc_rx_interp  | L2 voice access |
| 3   | dll_frame_rx_interp   | L2 frame info recv |
| 4   | dll_shortlc_rx_interp | L2 shortlc recv |
| 5   | dll_tx_slot_abnormal  | L2 TX timeslot abnormal |
| 6   | dll_rx_slot_abnormal  | L2 RX timeslot abnormal |
| 7   | gps_lost_interp       | Simulcast GPS pulse loss |
| 8   | gps_slot_abnormal     | Simulcast slot boundary abnormal |
| 9   | ccl_tx_interp         | Layer 3 send status |
| 10  | ccl_rx_interp         | Layer 3 recv status |
| 11  | phy_rx_interp         | PHY data RX (BER test) |
| 12  | phy_rdy_interp        | PHY early time slot |
| 13  | fm_sig_rx_interp      | FM detect |
| 14  | fm_rx_interp          | FM RX data |
| 15  | fm_tx_interp          | FM TX data |
| 16  | phy_recv_slot_abnormal | PHY RX slot boundary abnormal |
| 17  | rdy_next_short_lc     | Repeater shortlc info |

LAYER3_INTERP_LIST sub-interrupts (at 0x110003a4):
| Bit | Name                       | Description |
| --- | -------------------------- | ----------- |
| 0   | tx_denied                  | L3 send rejection |
| 1   | tx_oacsu_overtime          | L3 OACSU call timeout |
| 2   | tx_bs_overtime             | L3 BS activation timeout |
| 3   | tx_oacsu_req               | L3 OACSU call interrupt |
| 4   | tx_voice_start             | L3 voice TX start |
| 5   | tx_voice_finish            | L3 voice TX end |
| 6   | tx_v_emb_update            | L3 voice EMB update |
| 7   | tx_v_key_update            | L3 voice key update |
| 8   | tx_v_embf_update           | L3 voice F-frame EMB update |
| 9   | tx_data_start              | L3 SMS TX start |
| 10  | tx_data_retry_start        | L3 SMS partial retry |
| 11  | tx_data_allretry_start     | L3 SMS full retry |
| 12  | tx_data_finish             | L3 SMS TX end |
| 13  | tx_complete_data           | L3 SMS last frame, no confirm |
| 14  | tx_complete_data_confirmed | L3 SMS last frame, awaiting confirm |
| 25  | ccl_rx_data_abnormal       | L3 SMS RX abnormal |
| 26  | ccl_rx_data_error          | L3 SMS RX CRC32 error |
| 27  | ccl_rx_data_ok             | L3 SMS RX CRC32 OK |
| 28  | ccl_rx_voice_abnormal      | L3 voice RX abnormal |
| 29  | ccl_shortlc_rx_interp      | L3 shortlc RX |
| 30  | ccl_frame_rx_interp        | L3 frame info RX |
| 31  | ccl_latelc_rx_interp       | L3 voice access RX |

## 4. Working modes (§4.6.5.7 WORK_MODE @ 0x11000100)

| Value | Mode | Description |
| ----- | ---- | ----------- |
| 0x02  | DMR PHY continuous | |
| 0x16a / 0x16b | DMR/FM digital + analog simultaneous | |
| 0x22  | DMR PHY time-slot mode | |
| 0x6a  | DMR L2 direct (TDMA2 slot) or DCDM | |
| 0x6b  | DMR L2 direct (TDMA1 slot) or DCDM | |
| 0x6e  | DMR L2 relay slot 2 | |
| 0x6f  | DMR L2 relay slot 1 | |
| 0x73  | DMR L3 direct | |
| 0x76  | DMR L3 relay slot 2 | |
| 0x77  | DMR L3 relay slot 1 | |
| 0x80  | FM mode | |

## 5. IO_DIPLEX pin mux (§4.4.4 — base 0x11000000)

Three 32-bit registers select pin function for each multiplexed pin.

### 5.1 IO_DIPLEX0 @ 0x11000034

| Bits | Field        | 0 | 1 | 2 | 3 |
| ---- | ------------ | - | - | - | - |
| [31] | ptb7_sel     | AK_ADC_SDO | GPIO1_PTB7 | | |
| [19] | pwm2_sel     | PWM_2 | GPIO_PTA17 | | |
| [18] | pwm1_sel     | PWM_1 | GPIO_PTA16 | | |
| [17] | pwm0_sel     | PWM_0 | GPIO_PTA15 | | |
| [16:15] | uart3_txd_sel | UART3_TXD | Baseband rf_rx_inter | Reserved | GPIO_PTA14 |
| [14:13] | uart3_rxd_sel | UART3_RXD | Baseband rf_tx_inter | Reserved | GPIO_PTA13 |
| [12] | uart2_txd_sel | UART2_TXD | GPIO_PTA12 | | |
| [11] | uart2_rxd_sel | UART2_RXD | GPIO_PTA11 | | |
| [10] | uart1_txd_sel | UART1_TXD | GPIO_PTA10 | | |
| [9]  | uart1_rxd_sel | UART1_RXD | GPIO_PTA9  | | |
| [8]  | i2c1_sda_sel  | I2C_SDA_1 | GPIO_PTA8 | | |
| [7]  | i2c1_scl_sel  | I2C_SCL_1 | GPIO_PTA7 | | |
| [6]  | i2c0_sda_sel  | I2C_SDA_0 | GPIO_PTA6 | | |
| [5]  | i2c0_scl_sel  | I2C_SCL_0 | GPIO_PTA5 | | |
| [4]  | jtg_rstn_sel  | **JTG_RST_N** | GPIO_PTA4 | | |
| [3]  | jtg_tdo_sel   | **JTG_TDO** | GPIO_PTA3 | | |
| [2]  | jtg_tdi_sel   | **JTG_TDI** | GPIO_PTA2 | | |
| [1]  | jtg_tck_sel   | **JTG_TCK** | GPIO_PTA1 | | |
| [0]  | jtg_tms_sel   | **JTG_TMS** | GPIO_PTA0 | | |

**JTAG defaults to enabled (sel=0).** If the firmware writes IO_DIPLEX0 with bits[4:0] != 0,
JTAG pins get re-purposed as GPIO. Worth checking what the boot writes here.

### 5.2 IO_DIPLEX1 @ 0x11000038

| Bits | Field         | 0 | 1 | 2 | 3 |
| ---- | ------------- | - | - | - | - |
| [31] | ptb6_sel      | AK_ADC_SCLK | GPIO1_PTB6 | | |
| [30] | ptb5_sel      | AK_ADC_FS | GPIO1_PTB5 | | |
| [29] | ptb4_sel      | AK_DAC_SDI | GPIO1_PTB4 | | |
| [28] | ptb3_sel      | AK_DAC_SCLK | GPIO1_PTB3 | | |
| [27] | ptb2_sel      | AK_DAC_FS | GPIO1_PTB2 | | |
| [26:25] | time_slot_tx_sel | TIME_SLOT_T_INTER | Reserved | SDIO write_prt | GPIO_PTA31 |
| [24:23] | time_slot_rx_sel | TIME_SLOT_R_INTER | Reserved | SDIO card_detect_n | GPIO_PTA30 |
| [22:21] | bs_inter_out_sel | BS_INTER_OUT | Reserved | SDIO cdata[1] | GPIO_PTA29 |
| [20:19] | bs_inter_in_sel  | BS_INTER_IN | POR_RST_N | SDIO cdata[2] | GPIO_PTA28 |
| [18:17] | spi1_miso_sel    | Master SPI1_MISO | Slave SPI1_MISO | SDIO cdata[0] | GPIO_PTA27 |
| [16:15] | spi1_mosi_sel    | Master SPI1_MOSI | Slave SPI1_MOSI | SDIO ccmd | GPIO_PTA26 |
| [14:13] | spi1_sclk_sel    | Master SPI1_SCLK | Slave SPI1_SCLK | SDIO cclk_out | GPIO_PTA25 |
| [12:11] | spi1_csn1_sel    | Master SPI1_CSN_1 | Baseband sys_inter | Reserved | GPIO_PTA24 |
| [10:9]  | spi1_csn0_sel    | Master SPI1_CSN_0 | Slave SPI1_CSN_0 | SDIO cdata[3] | GPIO_PTA23 |
| [8:7]   | spi0_miso_sel    | Master SPI0_MISO | Slave SPI0_MISO | Reserved | GPIO_PTA22 |
| [6:5]   | spi0_mosi_sel    | Master SPI0_MOSI | Slave SPI0_MOSI | Reserved | GPIO_PTA21 |
| [4:3]   | spi0_sclk_sel    | Master SPI0_SCLK | Slave SPI0_SCLK | Reserved | GPIO_PTA20 |
| [2]     | spi0_csn1_sel    | SPI0_CSN_1 | GPIO_PTA19 | | |
| [1:0]   | spi0_csn0_sel    | Master SPI0_CSN_0 | Slave SPI0_CSN_0 | Reserved | GPIO_PTA18 |

### 5.3 IO_DIPLEX2 @ 0x1100003c

| Bits | Field         | 0 | 1 | 2 | 3 |
| ---- | ------------- | - | - | - | - |
| [29] | dac_vout_mcuc_sel | DAC_VOUT_MCUC | GPIO_PTC25 | | |
| [28] | dac_vout_mcub_sel | DAC_VOUT_MCUB | GPIO_PTC24 | | |
| [27] | dac_vout_mcua_sel | DAC_VOUT_MCUA | GPIO_PTC23 | | |
| [26] | adc7_in_sel   | ADC7_IN | GPIO_PTC22 | | |
| [25] | adc6_in_sel   | ADC6_IN | GPIO_PTC21 | | |
| [24] | adc5_in_sel   | ADC5_IN | GPIO_PTC20 | | |
| [23] | adc4_in_sel   | ADC4_IN | GPIO_PTC19 | | |
| [22] | adc3_in_sel   | ADC3_IN | GPIO_PTC18 | | |
| [21] | adc2_in_sel   | ADC2_IN | GPIO_PTC17 | | |
| [20] | adc1_in_sel   | ADC1_IN | GPIO_PTC16 | | |
| [19] | adc0_in_sel   | ADC0_IN | GPIO_PTC15 | | |
| [18] | lcd_db7_sel   | LCD_DB7 | GPIO_PTC14 | | |
| [17] | lcd_db6_sel   | LCD_DB6 | GPIO_PTC13 | | |
| [16] | lcd_db5_sel   | LCD_DB5 | GPIO_PTC12 | | |
| [15] | lcd_db4_sel   | LCD_DB4 | GPIO_PTC11 | | |
| [14] | lcd_db3_sel   | LCD_DB3 | GPIO_PTC10 | | |
| [13] | lcd_db2_sel   | LCD_DB2 | GPIO_PTC9 | | |
| [12:11] | lcd_db1_sel | LCD_DB1 | Master SPI2_MOSI | Slave SPI2_MOSI | GPIO_PTC8 |
| [10:9]  | lcd_db0_sel | LCD_DB0 | Master SPI2_MISO | Slave SPI2_MISO | GPIO_PTC7 |
| [8]  | lcd_rd_sel    | LCD_RD | GPIO_PTC6 | | |
| [7]  | lcd_wr_sel    | LCD_WR | GPIO_PTC5 | | |
| [6:5] | lcd_rs_sel   | LCD_RS | Master SPI2_SCLK | Slave SPI2_SCLK | GPIO_PTC4 |
| [4:3] | lcd_cs_sel   | LCD_CS | Master SPI2_CS | Slave SPI2_CS | GPIO_PTC3 |
| [1:0] | clk_out_sel  | PLLA CLK_OUT | PLLB CLK_OUT | RTC_CLK | GPIO_PTC0 |

## 6. System Control register block (§4.4.3, base 0x11000000)

| Off  | Name           | Notes |
| ---- | -------------- | ----- |
| 0x30 | LCSFC_BAUDR    | LCSFC SPI clock divider (default 4) |
| 0x34 | IO_DIPLEX0     | (table 5.1 above) |
| 0x38 | IO_DIPLEX1     | (table 5.2 above) |
| 0x3c | IO_DIPLEX2     | (table 5.3 above) |
| 0x40 | IOMGR_REN_REG0 | pull-up/down enable (set 0..31) |
| 0x44 | IOMGR_REN_REG1 | pull-up/down enable (set 32..63) |
| 0x48 | IOMGR_REN_REG2 | pull-up/down enable (set 64..95) |
| 0x4c | IOMGR_IE_IE0   | input enable (set 0..31) |
| 0x50 | IOMGR_IE_IE1   | input enable (set 32..63) |
| 0x54 | IOMGR_IE_IE2   | input enable (set 64..95) |
| 0x58 | RTC_REQ_HOLD   | RTC clamp |
| 0x5c | QUAD_ENABLE    | LCSFC SPI 4-wire control |
| 0x70 | DAC_CONTROL    | Baseband DAC ctrl |
| 0x74 | ADC_CONTROL    | Baseband ADC ctrl |
| 0x80 | AUDIO_CONTROL  | Baseband audio path |
| 0x84 | AUDIO_BUFFER_CLR | |
| 0x88 | LINEOUT_CTRL   | Codec lineout |
| 0x8c | CODEC_I2C_MUX  | Codec I2C |
| 0x100 | WORK_MODE     | (table §4 above) |
| 0x104 | RF_MODE       | RF interface mode |
| 0x398 | SYS_INTERP_LIST | (sub-interrupt status) |
| 0x39c | SYS_INTERP_MASK | |
| 0x3a0 | SYS_INTERP_CLEAR | |
| 0x3a4 | LAYER3_INTERP_LIST | (L3 sub-interrupt status) |
| 0x3a8 | LAYER3_INTERP_MASK | |
| 0x3ac | LAYER3_INTERP_CLEAR | |
| 0x3b0 | INTERP_CLEAR  | top-level interrupt clear |

## 7. JTAG (§4.5.5)

CK803S CPU JTAG features:
- Standard JTAG protocol
- Non-invasive CPU state acquisition
- 8 hardware breakpoints + soft breakpoints
- Multiple memory breakpoints
- CPU register read/write
- Memory read/write
- Single-step / multi-step execution
- Quick downloader
- Enter debug after reset OR in normal user mode

Connection: GDB ↔ Ethernet ↔ debug agent (PC) ↔ USB ↔ ICE/HAD ↔ JTAG ↔ CPU.
Standard tools: T-Head DebugServer + cklink, or generic OpenOCD with FT2232H.

## 8. Boot flow (§4.5.4)

```
POR → init hardware → send UART0 banner @ 115200 8N1
                    → host responds within timeout?
   yes → debug mode (loop on commands)
        → write cmd / read cmd / download cmd / jump cmd / exit cmd
   no → check Flash[0] == DH_FLAG?
        yes → read jump address from Flash[0x04]
              → jump and execute
        no → loop forever
```

Debug command set (from system startup flowchart, 5 commands):
1. **Write** command — write data to memory
2. **Read** command — read memory
3. **Download** command — load program
4. **Jump** command — jump to address
5. **Exit** command — leave debug mode

So the ISP protocol is custom but simple: 5 command types, each with an ack/data response over UART0.
