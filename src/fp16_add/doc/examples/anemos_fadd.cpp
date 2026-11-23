// ANEMOS's FP16 add on all 2^32 operand pairs, against an independent
// reference, and the double rounding of a float32 sum.
//
// ANEMOS (github.com/gem5-X/cnm_framework at commit f2d4018) adds with half's
// operator+ (src/fp_adder.cpp: add_res = op1->read() + op2->read()), from its
// own copy of half 2.2.0 (src/half.hpp), built as ANEMOS builds it: no
// HALF_ARITHMETIC_TYPE, default rounding (HALF_ROUND_STYLE 1), no error
// handling. That copy includes systemc.h, so this needs SystemC (2.3.4 was used).
//
// Two references, both GCC's _Float16 conversions (libgcc, round to nearest,
// ties to even), with no _Float16 arithmetic, so no excess-precision rule applies:
//   ref:   the two operands widened to double, whose 53-bit significand holds
//          every sum of two binary16 values exactly (at most 40 bits, 2^16 down
//          to 2^-24), and the sum converted once to _Float16: one rounding.
//   ref32: the two operands widened to float and added in float (SSE, round to
//          nearest even), then converted to _Float16: two roundings, as NumPy's
//          float16 add does. The program counts the pairs whose float sum is
//          inexact, and the pairs where ref32 differs from ref.
// A NaN is compared as a class: no reference fixes the bits of a NaN the way
// [TOP-FP-6] does.
//
// It first prints ANEMOS's result for each worked case of the doc, read as
// "a b" hex pairs from stdin, then runs the sweep. Run from the repo root
// (the sweep takes a few minutes):
//   A=<cnm_framework>
//   g++ -std=c++17 -O2 -I $A/src src/fp16_add/doc/examples/anemos_fadd.cpp -lsystemc -o <scratch>/anemos_fadd
//   python3 src/fp16_add/doc/examples/fadd_check.py --print-pairs \
//     | SYSTEMC_DISABLE_COPYRIGHT_MESSAGE=1 <scratch>/anemos_fadd > src/fp16_add/doc/examples/anemos_fadd.out
//
// fadd_check.py --anemos reads the output (with --exhaustive it also compares
// the digests with bankside's model on all 2^32 pairs). Each line is "key value",
// "key bits count", "case a b result" or "differ a b ...".
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <map>
#include "half.hpp"

using half_float::half;

static half from_bits(uint16_t b) { half h; std::memcpy(&h, &b, 2); return h; }
static uint16_t to_bits(half h) { uint16_t b; std::memcpy(&b, &h, 2); return b; }
static bool is_nan(uint16_t b) { return (b & 0x7FFF) > 0x7C00; }

static _Float16 f16(uint16_t b) { _Float16 x; std::memcpy(&x, &b, 2); return x; }
static uint16_t bits16(_Float16 x) { uint16_t o; std::memcpy(&o, &x, 2); return o; }

static uint16_t ref_add(uint16_t a, uint16_t b) {           // one rounding
    return bits16((_Float16)((double)f16(a) + (double)f16(b)));
}

int sc_main(int, char **) {
    // The worked cases: "a b" pairs in hex on stdin (fadd_check.py --print-pairs).
    unsigned int ca, cb;
    while (std::scanf("%x %x", &ca, &cb) == 2)
        std::printf("case 0x%04X 0x%04X 0x%04X\n", ca, cb,
                    to_bits(from_bits((uint16_t)ca) + from_bits((uint16_t)cb)));

    uint64_t pairs = 0, equal = 0, nan_both = 0, differ = 0, differ_zero_sign = 0;
    uint64_t f32_inexact = 0, dr_differ = 0, dr_nan_mismatch = 0;
    uint64_t neg_zero_results = 0;
    // Digests of all 2^32 results in order, each NaN replaced by 0x7E00 first, so
    // fadd_check.py --exhaustive can compare them with bankside's own model:
    //   sum over (a, b) of (r + 1) * ((a * 65536 + b) * K + 1), mod 2^64.
    const uint64_t K = 0x9E3779B97F4A7C15ull;
    uint64_t dig_anemos = 0, dig_ref = 0, dig_ref32 = 0;
    std::map<uint16_t, uint64_t> nan_invalid, nan_operand;   // half's NaN bits, by cause
    const int max_list = 40;
    int listed = 0, dr_listed = 0;
    for (uint32_t a = 0; a < 0x10000; a++) {
        half ha = from_bits((uint16_t)a);
        double da = (double)f16((uint16_t)a);
        float fa = (float)f16((uint16_t)a);
        for (uint32_t b = 0; b < 0x10000; b++) {
            uint16_t r = to_bits(ha + from_bits((uint16_t)b));
            double db = (double)f16((uint16_t)b);
            float fb = (float)f16((uint16_t)b);
            double exact = da + db;
            float s32 = fa + fb;
            uint16_t q = bits16((_Float16)exact);
            uint16_t q32 = bits16((_Float16)s32);
            pairs++;
            uint64_t w = (((uint64_t)a << 16) | b) * K + 1;
            dig_anemos += (uint64_t)((is_nan(r) ? 0x7E00 : r) + 1) * w;
            dig_ref += (uint64_t)((is_nan(q) ? 0x7E00 : q) + 1) * w;
            dig_ref32 += (uint64_t)((is_nan(q32) ? 0x7E00 : q32) + 1) * w;
            if (q == 0x8000) neg_zero_results++;
            // double rounding: is the float sum exact, and does it change the result?
            if (exact == exact && (double)s32 != exact) f32_inexact++;
            if (is_nan(q) != is_nan(q32)) {
                dr_nan_mismatch++;
            } else if (!is_nan(q) && q != q32) {
                dr_differ++;
                if (dr_listed < max_list) {
                    std::printf("dr_differ 0x%04X 0x%04X one=0x%04X two=0x%04X\n", a, b, q, q32);
                    dr_listed++;
                }
            }
            // ANEMOS against the one-rounding reference
            if (is_nan(r) && is_nan(q)) {
                nan_both++;
                bool invalid = !is_nan(a) && !is_nan(b);
                (invalid ? nan_invalid : nan_operand)[r]++;
            } else if (r == q) {
                equal++;
            } else {
                differ++;
                if (((r | q) & 0x7FFF) == 0) differ_zero_sign++;
                if (listed < max_list) {
                    std::printf("differ 0x%04X 0x%04X anemos=0x%04X ref=0x%04X\n", a, b, r, q);
                    listed++;
                }
            }
        }
    }
    std::printf("pairs %llu\n", (unsigned long long)pairs);
    std::printf("equal %llu\n", (unsigned long long)equal);
    std::printf("nan_both %llu\n", (unsigned long long)nan_both);
    std::printf("differ %llu\n", (unsigned long long)differ);
    std::printf("differ_zero_sign %llu\n", (unsigned long long)differ_zero_sign);
    std::printf("ref_neg_zero_results %llu\n", (unsigned long long)neg_zero_results);
    std::printf("f32_inexact %llu\n", (unsigned long long)f32_inexact);
    std::printf("dr_differ %llu\n", (unsigned long long)dr_differ);
    std::printf("dr_nan_mismatch %llu\n", (unsigned long long)dr_nan_mismatch);
    std::printf("digest_anemos %llu\n", (unsigned long long)dig_anemos);
    std::printf("digest_ref %llu\n", (unsigned long long)dig_ref);
    std::printf("digest_ref32 %llu\n", (unsigned long long)dig_ref32);
    uint64_t inv = 0, opn = 0;
    for (auto &kv : nan_invalid) inv += kv.second;
    for (auto &kv : nan_operand) opn += kv.second;
    std::printf("nan_invalid_pairs %llu\n", (unsigned long long)inv);
    for (auto &kv : nan_invalid)
        std::printf("nan_invalid_bits 0x%04X %llu\n", kv.first, (unsigned long long)kv.second);
    std::printf("nan_operand_pairs %llu\n", (unsigned long long)opn);
    std::printf("nan_operand_distinct_bits %zu\n", nan_operand.size());
    return 0;
}
