// ANEMOS's FP16 multiply on all 2^32 operand pairs, against an independent
// reference.
//
// ANEMOS (github.com/gem5-X/cnm_framework at commit f2d4018) multiplies with
// half's operator* (src/fp_multiplier.cpp: mul_res = op1->read() * op2->read()),
// from its own copy of half 2.2.0 (src/half.hpp), built as ANEMOS builds it:
// no HALF_ARITHMETIC_TYPE, default rounding (HALF_ROUND_STYLE 1), no error
// handling. That copy includes systemc.h, so this needs SystemC (2.3.4 was used).
//
// The reference is GCC's _Float16: the two operands widened to double, whose
// 53-bit significand holds the 22-bit product exactly, and the product converted
// once to _Float16 (libgcc, round to nearest, ties to even). A NaN is compared as
// a class: neither reference fixes the bits of a NaN the way [TOP-FP-6] does.
//
// It first prints ANEMOS's result for each worked case of the doc, read as
// "a b" hex pairs from stdin, then runs the sweep. Run from the repo root
// (the sweep takes a few minutes):
//   A=<cnm_framework>
//   g++ -std=c++17 -O2 -I $A/src src/fp16_mul/doc/examples/anemos_fmul.cpp -lsystemc -o <scratch>/anemos_fmul
//   python3 src/fp16_mul/doc/examples/fmul_check.py --print-pairs \
//     | SYSTEMC_DISABLE_COPYRIGHT_MESSAGE=1 <scratch>/anemos_fmul > src/fp16_mul/doc/examples/anemos_fmul.out
//
// fmul_check.py --anemos reads the output (with --exhaustive it also compares
// the two digests with bankside's model on all 2^32 pairs). Each line is "key value",
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
static bool is_inf(uint16_t b) { return (b & 0x7FFF) == 0x7C00; }

static uint16_t ref_mul(uint16_t a, uint16_t b) {
    _Float16 x, y;
    std::memcpy(&x, &a, 2);
    std::memcpy(&y, &b, 2);
    _Float16 r = (_Float16)((double)x * (double)y);
    uint16_t o;
    std::memcpy(&o, &r, 2);
    return o;
}

int sc_main(int, char **) {
    // The worked cases: "a b" pairs in hex on stdin (fmul_check.py --print-pairs).
    unsigned int ca, cb;
    while (std::scanf("%x %x", &ca, &cb) == 2)
        std::printf("case 0x%04X 0x%04X 0x%04X\n", ca, cb,
                    to_bits(from_bits((uint16_t)ca) * from_bits((uint16_t)cb)));

    uint64_t pairs = 0, equal = 0, nan_both = 0, differ = 0;
    // Digests of all 2^32 results in order, each NaN replaced by 0x7E00 first, so
    // fmul_check.py --exhaustive can compare them with bankside's own model:
    //   sum over (a, b) of (r + 1) * ((a * 65536 + b) * K + 1), mod 2^64.
    const uint64_t K = 0x9E3779B97F4A7C15ull;
    uint64_t dig_anemos = 0, dig_ref = 0;
    std::map<uint16_t, uint64_t> nan_invalid, nan_operand;   // half's NaN bits, by cause
    std::map<uint16_t, uint64_t> ref_nan;                    // the reference's NaN bits
    const int max_list = 40;
    int listed = 0;
    for (uint32_t a = 0; a < 0x10000; a++) {
        half ha = from_bits((uint16_t)a);
        for (uint32_t b = 0; b < 0x10000; b++) {
            uint16_t r = to_bits(ha * from_bits((uint16_t)b));
            uint16_t q = ref_mul((uint16_t)a, (uint16_t)b);
            pairs++;
            uint64_t w = (((uint64_t)a << 16) | b) * K + 1;
            dig_anemos += (uint64_t)((is_nan(r) ? 0x7E00 : r) + 1) * w;
            dig_ref += (uint64_t)((is_nan(q) ? 0x7E00 : q) + 1) * w;
            if (is_nan(r) && is_nan(q)) {
                nan_both++;
                bool invalid = !is_nan(a) && !is_nan(b);
                (invalid ? nan_invalid : nan_operand)[r]++;
                ref_nan[q]++;
            } else if (r == q) {
                equal++;
            } else {
                differ++;
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
    std::printf("digest_anemos %llu\n", (unsigned long long)dig_anemos);
    std::printf("digest_ref %llu\n", (unsigned long long)dig_ref);
    uint64_t inv = 0, opn = 0;
    for (auto &kv : nan_invalid) inv += kv.second;
    for (auto &kv : nan_operand) opn += kv.second;
    std::printf("nan_invalid_pairs %llu\n", (unsigned long long)inv);
    for (auto &kv : nan_invalid)
        std::printf("nan_invalid_bits 0x%04X %llu\n", kv.first, (unsigned long long)kv.second);
    std::printf("nan_operand_pairs %llu\n", (unsigned long long)opn);
    std::printf("nan_operand_distinct_bits %zu\n", nan_operand.size());
    std::printf("ref_nan_distinct_bits %zu\n", ref_nan.size());
    return 0;
}
