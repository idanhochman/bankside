// ANEMOS's own control logic (instruction decoder, PC unit, CRF) run on the
// control cases of loop_trace.py, so that the ANEMOS columns of the
// programmer's guide come from a run, not only from reading the code.
//
// Built against github.com/gem5-X/cnm_framework at commit f2d4018: this file is
// a testbench only; it links ANEMOS's src/instr_decoder.cpp, src/pc_unit.cpp
// and src/crf.cpp unchanged and builds every instruction word with the field
// positions of ANEMOS's src/opcodes.h. Needs SystemC (2.3.4 was used). Run
// from the repo root:
//
//   A=<cnm_framework>
//   g++ -std=c++17 -I $A/src src/top/doc/examples/anemos_ctrl.cpp \
//       $A/src/instr_decoder.cpp $A/src/pc_unit.cpp $A/src/crf.cpp \
//       -lsystemc -o <scratch>/anemos_ctrl
//   SYSTEMC_DISABLE_COPYRIGHT_MESSAGE=1 <scratch>/anemos_ctrl > src/top/doc/examples/anemos_ctrl.out
//
// One clock cycle per line. "trig" is decode_en, the decoder's input for a
// PIM command (one triggering command); the interface unit is left out and
// decode_en is driven directly. Each line shows the PC and the opcode the
// decoder sees, the decoder's NOP counter and loop state (nop_cnt_reg,
// jmp_act_reg, jmp_cnt_reg) at the start of the cycle, and what the PC unit
// is told (count_en, jump_en, pc_rst).
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include "systemc.h"
#include "cnm_base.h"
#include "instr_decoder.h"
#include "pc_unit.h"
#include "crf.h"

static uint32_t ctrl(uint32_t op, uint32_t imm0, uint32_t imm1) {
    return (op << OPCODE_END) | (imm0 << IMM0_END) | (imm1 << IMM1_END);
}
static uint32_t mov(uint32_t dst, uint32_t src0, uint32_t dst_n, uint32_t src0_n) {
    return (OP_MOV << OPCODE_END) | (dst << DST_END) | (src0 << SRC0_END) |
           (dst_n << DST_N_END) | (src0_n << SRC0_N_END);
}

static const char *opname(uint32_t w) {
    switch (w >> OPCODE_END) {
        case OP_NOP: return "NOP";  case OP_JUMP: return "JUMP";
        case OP_EXIT: return "EXIT"; case OP_MOV: return "MOV";
        default: return "other";
    }
}

struct Case {
    std::string name;
    std::vector<uint32_t> prog;
    int cycles;
    int trig_every;   // a triggering command every n-th cycle
};

int sc_main(int, char **) {
    sc_clock clk("clk", 10, SC_NS, 0.5, 5, SC_NS, true);
    sc_signal<bool> rst, rf_access, decode_en;
    sc_signal<uint8_t> pc, jump_num, srf_wr_from, grfa_wr_from, grfb_wr_from;
    sc_signal<uint8_t> m1, m2, a1, a2;
    sc_signal<uint32_t> instr, crf_in;
    sc_signal<sc_uint<BANK_BITS> > bank_addr;
    sc_signal<sc_uint<ROW_BITS> > row_addr;
    sc_signal<sc_uint<COL_BITS> > col_addr;
    sc_signal<bool> pc_rst, count_en, jump_en, crf_wr_en_dec, crf_wr_en;
    sc_signal<uint> crf_wr_addr_dec, crf_wr_addr;
    sc_signal<uint> srf_rd_addr, srf_wr_addr, ga1, ga2, gaw, gb1, gb2, gbw;
    sc_signal<bool> srf_rd_a_nm, srf_wr_en, srf_wr_a_nm, gawe, gare, gbwe, gbre;
    sc_signal<bool> fme, fae, fos, eoe, ooe;

    instr_decoder id("id");
    id.clk(clk); id.rst(rst); id.rf_access(rf_access); id.decode_en(decode_en);
    id.pc_in(pc); id.instr(instr); id.bank_addr(bank_addr); id.row_addr(row_addr);
    id.col_addr(col_addr); id.pc_rst(pc_rst); id.count_en(count_en);
    id.jump_en(jump_en); id.jump_num(jump_num); id.crf_wr_en(crf_wr_en_dec);
    id.crf_wr_addr(crf_wr_addr_dec); id.srf_rd_addr(srf_rd_addr);
    id.srf_rd_a_nm(srf_rd_a_nm); id.srf_wr_en(srf_wr_en); id.srf_wr_addr(srf_wr_addr);
    id.srf_wr_a_nm(srf_wr_a_nm); id.srf_wr_from(srf_wr_from);
    id.grfa_rd_addr1(ga1); id.grfa_rd_addr2(ga2); id.grfa_wr_en(gawe);
    id.grfa_relu_en(gare); id.grfa_wr_addr(gaw); id.grfa_wr_from(grfa_wr_from);
    id.grfb_rd_addr1(gb1); id.grfb_rd_addr2(gb2); id.grfb_wr_en(gbwe);
    id.grfb_relu_en(gbre); id.grfb_wr_addr(gbw); id.grfb_wr_from(grfb_wr_from);
    id.fpu_mult_en(fme); id.fpu_add_en(fae); id.fpu_mult_in1_sel(m1);
    id.fpu_mult_in2_sel(m2); id.fpu_add_in1_sel(a1); id.fpu_add_in2_sel(a2);
    id.fpu_out_sel(fos); id.even_out_en(eoe); id.odd_out_en(ooe);

    pc_unit pcu("pcu");
    pcu.clk(clk); pcu.rst(rst); pcu.pc_rst(pc_rst); pcu.count_en(count_en);
    pcu.jump_en(jump_en); pcu.jump_num(jump_num); pcu.pc_out(pc);

    crf c("crf");
    c.clk(clk); c.rst(rst); c.PC(pc); c.instr(instr);
    c.wr_en(crf_wr_en); c.wr_addr(crf_wr_addr); c.wr_port(crf_in);

    const uint32_t MOV_A0 = mov(OPC_GRF_A, OPC_EVEN_BANK, 0, 0);   // MOV GRF_A[0], EVEN_BANK
    const uint32_t MOV_B0 = mov(OPC_GRF_B, OPC_ODD_BANK, 0, 0);    // MOV GRF_B[0], ODD_BANK
    const uint32_t MOV_A1 = mov(OPC_GRF_A, OPC_EVEN_BANK, 1, 0);   // MOV GRF_A[1], EVEN_BANK
    const uint32_t EXIT = ctrl(OP_EXIT, 0, 0);
    auto JUMP = [](uint32_t off, uint32_t n) { return ctrl(OP_JUMP, off, n); };
    auto NOP = [](uint32_t n) { return ctrl(OP_NOP, n, 0); };

    std::vector<Case> cases = {
        {"A: JUMP -1, 2 (slots per JUMP)", {MOV_A0, JUMP(1, 2), EXIT}, 8, 1},
        {"B: JUMP -0, 3 at PC 1 (IMM0 = 0, TOP-ISA-14)", {MOV_A0, JUMP(0, 3), EXIT}, 7, 1},
        {"C: JUMP -5, 1 at PC 2 (IMM0 > PC, TOP-ISA-14)", {MOV_A0, MOV_B0, JUMP(5, 1), EXIT}, 6, 1},
        {"D: nested loops (TOP-ISA-6)",
         {MOV_A0, MOV_B0, JUMP(1, 1), MOV_A1, JUMP(4, 1), EXIT}, 24, 1},
        {"E: JUMP after a JUMP (TOP-ISA-7)", {MOV_A0, JUMP(1, 1), JUMP(2, 0), EXIT}, 7, 1},
        {"F: NOP 3 with a trigger every 2nd cycle", {NOP(3), MOV_A0, EXIT}, 10, 2},
    };

    // The field positions of src/opcodes.h, and two words built the way
    // inputs/src/nmc_assembler.cpp's build_instr does (field << *_END).
    std::printf("Layout (src/opcodes.h): msb lsb\n");
    std::printf("  OPCODE %d %d\n  DST %d %d\n  SRC0 %d %d\n  SRC1 %d %d\n  SRC2 %d %d\n",
                OPCODE_STA, OPCODE_END, DST_STA, DST_END, SRC0_STA, SRC0_END,
                SRC1_STA, SRC1_END, SRC2_STA, SRC2_END);
    std::printf("  RELU %d %d\n  AAM %d %d\n", RELU_BIT, RELU_BIT, AAM_BIT, AAM_BIT);
    std::printf("  DST# %d %d\n  SRC0# %d %d\n  SRC1# %d %d\n", DST_N_STA, DST_N_END,
                SRC0_N_STA, SRC0_N_END, SRC1_N_STA, SRC1_N_END);
    std::printf("  IMM0 %d %d\n  IMM1 %d %d\n", IMM0_STA, IMM0_END, IMM1_STA, IMM1_END);
    uint32_t mul = (OP_MUL << OPCODE_END) | (OPC_GRF_B << DST_END) | (OPC_GRF_A << SRC0_END) |
                   (OPC_SRF_M << SRC1_END) | (3u << DST_N_END) | (1u << SRC0_N_END) |
                   (4u << SRC1_N_END);
    uint32_t movr = mov(OPC_GRF_A, OPC_EVEN_BANK, 3, 0) | (1u << RELU_BIT);
    uint32_t jmp = ctrl(OP_JUMP, 3, 7);
    std::printf("Word MUL GRF_B[3], GRF_A[1], SRF_M[4] 0x%08X\n", mul);
    std::printf("Word MOV(RELU) GRF_A[3], EVEN_BANK 0x%08X\n", movr);
    std::printf("Word JUMP -3, 7 0x%08X\n\n", jmp);

    sc_start(1, SC_NS);
    for (auto &cs : cases) {
        // Reset (active low), then load the CRF with no triggers.
        rst = false; decode_en = false; rf_access = false; crf_wr_en = false;
        sc_start(10, SC_NS);
        rst = true;
        for (unsigned i = 0; i < CRF_ENTRIES; i++) {
            crf_wr_en = true; crf_wr_addr = i;
            crf_in = i < cs.prog.size() ? cs.prog[i] : NOP(1);
            sc_start(10, SC_NS);
        }
        crf_wr_en = false;
        sc_start(10, SC_NS);
        std::printf("Case %s\n", cs.name.c_str());
        std::printf("  cycle trig  PC  word  nop_cnt act cnt  -> count_en jump_en pc_rst\n");
        for (int cyc = 1; cyc <= cs.cycles; cyc++) {
            decode_en = ((cyc - 1) % cs.trig_every) == 0;
            sc_start(1, SC_NS);              // settle, before the clock edge
            std::printf("  %5d %4d %3u  %-5s %7u %3d %3u  -> %d %d %d\n", cyc,
                        (int)decode_en.read(), (unsigned)pc.read(), opname(instr.read()),
                        (unsigned)id.nop_cnt_reg.read(), (int)id.jmp_act_reg.read(),
                        (unsigned)id.jmp_cnt_reg.read(), (int)count_en.read(),
                        (int)jump_en.read(), (int)pc_rst.read());
            sc_start(9, SC_NS);
        }
        std::printf("\n");
    }
    return 0;
}
