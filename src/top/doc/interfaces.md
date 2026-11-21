# Interfaces (v1)

In v1 the unit has a deliberately simple boundary: the testbench plays both the
host (triggers, register-file writes) and the DRAM banks (a synchronous memory
model). v2 replaces this with the HBM2 command interface and memory-mapped
register files. **[bankside]** throughout, unless marked.

## Parameters

| Name | Default | Meaning |
|---|---|---|
| `ROW_W` | 14 | Row address width (HBM2 pseudo-channel) |
| `COL_W` | 5 | Column address width (32 columns of 256 bits) |

## Ports

| Port | Dir | Width | Description |
|---|---|---|---|
| `clk` | in | 1 | Unit clock (DRAM core clock) |
| `rst_n` | in | 1 | Synchronous reset, active low |
| **Trigger** | | | |
| `trig_valid` | in | 1 | One issue slot this cycle |
| `trig_row` | in | ROW_W | Row of the triggering command |
| `trig_col` | in | COL_W | Column of the triggering command |
| **Bank read** | | | |
| `bank_rd_en` | out | 1 | The instruction in S1 reads a bank |
| `bank_rd_sel` | out | 1 | 0 = EVEN_BANK, 1 = ODD_BANK |
| `bank_rd_row`, `bank_rd_col` | out | ROW_W, COL_W | Address (the trigger's) |
| `bank_rd_data` | in | 256 | Read data, valid in the next cycle |
| **Bank write** | | | |
| `bank_wr_en` | out | 1 | A bank store in S5 |
| `bank_wr_sel` | out | 1 | 0 = EVEN_BANK, 1 = ODD_BANK |
| `bank_wr_row`, `bank_wr_col` | out | ROW_W, COL_W | Address of the store's own trigger |
| `bank_wr_data` | out | 256 | Write data |
| **Configuration** | | | |
| `cfg_wr_en` | in | 1 | Write one register-file entry |
| `cfg_wr_sel` | in | 3 | 0 GRF_A, 1 GRF_B, 2 SRF_M, 3 SRF_A (the operand codes), 7 CRF |
| `cfg_wr_idx` | in | 5 | Entry index (0–31 for CRF, 0–7 otherwise) |
| `cfg_wr_data` | in | 256 | Data; CRF uses bits 31:0, SRF bits 15:0 |
| **Debug (testbench only)** | | | |
| `dbg_rd_sel`, `dbg_rd_idx` | in | 3, 5 | As `cfg_wr_sel` / `cfg_wr_idx` |
| `dbg_rd_data` | out | 256 | Combinational read of the selected entry |
| **Status** | | | |
| `busy` | out | 1 | An instruction is in flight, a multi-cycle NOP is running, or a loop is active |
| `err_illegal` | out | 1 | Sticky: an illegal instruction was executed ([ISA-2]); cleared by reset |

## Timing

- **[IF-1]** A cycle with `trig_valid = 1` is one issue slot. The instruction
  at the PC enters S1 in that cycle (or, during a multi-cycle NOP, one NOP slot
  is consumed).
- **[IF-2]** **Bank read.** In the S1 cycle the unit drives `bank_rd_en`,
  `bank_rd_sel` and the address. The bank samples them at the end of that
  cycle and must drive `bank_rd_data` during the next cycle (S2), like a
  synchronous SRAM with one cycle of read latency.
- **[IF-3]** **Bank write.** `bank_wr_*` are registered outputs, valid in the
  S5 cycle. The bank writes at the end of that cycle. Writes take effect
  before reads sampled on the same edge ([HAZ-6]).
- **[IF-4]** **Reset.** On `rst_n = 0`: PC ← 0, loop and NOP counters cleared,
  all pipeline stages invalid, `err_illegal` ← 0. Register files keep their
  contents ([ARCH-5]).
- **[IF-5]** **Configuration writes** take effect at the end of the cycle.
  A written entry can be read by `dbg_rd_*` in the next cycle.
- **[IF-6]** The host must write register files only while `busy = 0` and
  `trig_valid = 0`.

Waveforms for these (WaveDrom) will be added with the RTL.

## Debug port

The debug port exists so the testbench can check register contents directly.
It is not part of the architecture: the synthesis wrapper ties it off, so it
doesn't count in the PPA results.

## v2

To be specified with v2:

- the HBM2 command interface (ACT/PRE/RD/WR with timing), replacing the trigger
  and bank ports
- SB / AB / AB-PIM modes and their entry and exit sequences **[paper]**
- AAM: register indices taken from the command address **[paper]**
- the memory map of the CRF, GRF, SRF and configuration registers inside the
  reserved region, replacing the configuration port
