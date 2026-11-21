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
| `busy` | out | 1 | The unit is not idle ([TOP-IF-7]) |
| `err_illegal` | out | 1 | Sticky: an illegal instruction was executed ([TOP-ISA-2]); set at the end of its S1 cycle ([TOP-ISA-24]); cleared by reset |

## Timing

- **[TOP-IF-1]** A cycle with `trig_valid = 1` is one issue slot. The instruction
  at the PC enters S1 in that cycle (or, during a multi-cycle NOP, one NOP slot
  is consumed).
- **[TOP-IF-2]** **Bank read.** In the S1 cycle the unit drives `bank_rd_en`,
  `bank_rd_sel` and the address. The bank samples them at the end of that
  cycle and must drive `bank_rd_data` during the next cycle (S2), like a
  synchronous SRAM with one cycle of read latency.
- **[TOP-IF-3]** **Bank write.** `bank_wr_*` are registered outputs, valid in the
  S5 cycle. The bank writes at the end of that cycle. Writes take effect
  before reads sampled on the same edge ([TOP-HAZ-6]).
- **[TOP-IF-4]** **Reset.** On `rst_n = 0`: PC ← 0, the loop state
  (`loop_active`, `loop_cnt`, [TOP-ISA-3]) and the NOP counter cleared,
  all pipeline stages invalid, `err_illegal` ← 0. Register files keep their
  contents ([TOP-ARCH-5]).
- **[TOP-IF-5]** **Configuration writes** take effect at the end of the cycle.
  A written entry can be read by `dbg_rd_*` in the next cycle.
- **[TOP-IF-6]** The host must write register files only while `busy = 0` and
  `trig_valid = 0`. This is a programming rule for the host
  ([programmer's guide](programmers_guide.md#programming-rules)).
- **[TOP-IF-8]** **A configuration write that breaks [TOP-IF-6] is
  ignored.** In a cycle with `cfg_wr_en` = 1 and `busy` = 1 or
  `trig_valid` = 1, no register-file or CRF entry changes. The S5 write of
  that cycle, if any, goes ahead as usual. The `busy` used is the output's
  value in that same cycle ([TOP-IF-7]; its exact cycles are #24). The
  [TOP-IF-6] assertion still fires, and nothing is flagged on the ports.
  **[bankside]** Options weighed:
  - the S5 write wins only when both write the same file, and the
    configuration write goes ahead otherwise (closest to ANEMOS, below).
    But then a write that lands mid-run depends on what is in the pipeline
    that cycle and, for the CRF, on how the fetch reads ahead (#27).
  - the configuration write wins. That drops an instruction's result
    without a trace.
  - ignore it whenever the rule is broken (chosen). The outcome depends only
    on `busy` and `trig_valid`, both visible on the ports. It costs one gate
    on `cfg_wr_en`, and no register or CRF entry can change under a running
    program.

  ANEMOS applies a host register write while a kernel runs. If an
  instruction's write-back to the same file falls in the same cycle, the
  decoder ORs the two writes' enables, indices and source selects bit by
  bit (`instr_decoder.cpp`, `out_method`, at `f2d4018`; read, not run). That
  isn't a behaviour to copy.

  Worked case: after a kernel's last trigger in cycle *c*, its last
  instruction writes GRF_B[0] in S5 at cycle *c* + 4, so `busy` = 1 up to
  then at least. A host write of SRF_A[0] in cycle *c* + 2 is ignored:
  `dbg_rd_*` still shows the old SRF_A[0] in cycle *c* + 3. The same write
  in the first cycle with `busy` = 0 and `trig_valid` = 0 takes effect
  ([TOP-IF-5]).
- **[TOP-IF-7]** **Busy.** `busy` = 1 while any of these holds: an instruction
  is valid in any of S1 to S5, a multi-cycle NOP has slots left
  ([TOP-ISA-12]), or `loop_active` = 1 ([TOP-ISA-3]). Otherwise `busy` = 0.

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
