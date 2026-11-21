// ANEMOS's FP16 behaviour on the ReLU and NaN cases of fp_relu_nan.py.
//
// Built against ANEMOS's own half.hpp (half 2.2.0, github.com/gem5-X/cnm_framework
// at commit f2d4018, src/half.hpp), with the same build settings ANEMOS uses:
// no HALF_ARITHMETIC_TYPE, default rounding. ANEMOS's copy of half.hpp includes
// systemc.h, so this needs SystemC (2.3.4 was used). Run from the repo root:
//
//   g++ -std=c++17 -I <cnm_framework>/src src/top/doc/examples/anemos_fp.cpp -lsystemc -o <scratch>/anemos_fp
//   SYSTEMC_DISABLE_COPYRIGHT_MESSAGE=1 <scratch>/anemos_fp > src/top/doc/examples/anemos_fp.out
//
// The ReLU line copies the expression in ANEMOS src/grf.cpp (non-synthesis path):
//   (relu_en && in < 0) ? half_float::half_cast<half>(0.0) : in
// MUL and ADD are half's operator* and operator+, as in src/fp_multiplier.cpp and
// src/fp_adder.cpp (mul_res = op1 * op2; add_res = op1 + op2).
#include <cstdio>
#include <cstdint>
#include <cstring>
#include "half.hpp"

using half_float::half;

static half from_bits(uint16_t b) { half h; std::memcpy(&h, &b, 2); return h; }
static uint16_t to_bits(half h) { uint16_t b; std::memcpy(&b, &h, 2); return b; }

static half relu(half in) {
    return (in < 0) ? half_float::half_cast<half>(0.0) : in;
}

int sc_main(int, char **) {   // ANEMOS's half.hpp includes systemc.h
    const uint16_t relu_in[] = {0x3C00, 0xBC00, 0x0000, 0x8000, 0x8001, 0x7C00,
                                0xFC00, 0x7E00, 0x7C01, 0xFE00, 0xFC01};
    for (uint16_t x : relu_in)
        std::printf("RELU 0x%04X -> 0x%04X\n", x, to_bits(relu(from_bits(x))));

    struct { char op; uint16_t a, b; } bin[] = {
        {'+', 0x7C00, 0xFC00}, {'*', 0x0000, 0x7C00}, {'+', 0xFE00, 0x3C00},
        {'*', 0x7C01, 0x3C00}, {'+', 0x7E01, 0xFE02}, {'+', 0xFE02, 0x7E01},
        {'+', 0x3C00, 0xFE02}};
    for (auto &c : bin) {
        half a = from_bits(c.a), b = from_bits(c.b);
        half r = (c.op == '+') ? a + b : a * b;
        std::printf("%s 0x%04X 0x%04X -> 0x%04X\n", c.op == '+' ? "ADD" : "MUL",
                    c.a, c.b, to_bits(r));
    }
    return 0;
}
