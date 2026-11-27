// fp16_add: one lane of the S4 add. IEEE 754 binary16 a + b, round to nearest
// even, subnormals in and out, overflow to +-Inf, an exact zero sum +0 unless
// both operands are -0, every NaN result 0x7E00, no flags.
// Spec: src/fp16_add/doc/README.md.
//
// [FADD-1], [FADD-3], [FADD-11], [TOP-HIER-3]: purely combinational, no clock,
// reset, state or parameters; the only paths are a -> s and b -> s.
//
// Structure [bankside]: a single-path guard/round/sticky adder. The operands
// are ordered by magnitude (x the larger), y is aligned to x with its
// shifted-out bits ORed into a sticky bit, the 15-bit sum or difference is
// normalised by one place right (carry) or up to the subnormal limit left,
// then rounded to nearest even; the rounding carry runs into the exponent
// field by itself. NaN, Inf and zero + zero are chosen by a final multiplexer.
// The datapath is symmetric in a and b except for the ordering compare, which
// picks a on equal magnitudes; that case is either an exact zero (opposite
// signs) or 2x (same signs), the same whichever is x, so [FADD-10] holds.

module fp16_add (
  input  logic [15:0] a,
  input  logic [15:0] b,
  output logic [15:0] s
);

  // ------------------------------------------------------------ unpack, [FADD-4]
  logic [4:0] ea, eb;
  logic [9:0] fa, fb;
  logic       a_zero, b_zero, a_inf, b_inf, a_nan, b_nan;

  assign ea = a[14:10];
  assign eb = b[14:10];
  assign fa = a[9:0];
  assign fb = b[9:0];

  assign a_zero = (ea == 5'd0)  && (fa == 10'd0);
  assign b_zero = (eb == 5'd0)  && (fb == 10'd0);
  assign a_inf  = (ea == 5'd31) && (fa == 10'd0);
  assign b_inf  = (eb == 5'd31) && (fb == 10'd0);
  // [FADD-4], [FADD-8]: signalling and quiet NaNs, any payload, are alike.
  assign a_nan  = (ea == 5'd31) && (fa != 10'd0);
  assign b_nan  = (eb == 5'd31) && (fb != 10'd0);

  // Significand with the hidden bit; a subnormal's exponent counts as 1, so
  // value = M * 2^(F - 25) for both classes.
  logic [10:0] ma, mb;
  logic [4:0]  fea, feb;

  assign ma  = {ea != 5'd0, fa};
  assign mb  = {eb != 5'd0, fb};
  assign fea = (ea == 5'd0) ? 5'd1 : ea;
  assign feb = (eb == 5'd0) ? 5'd1 : eb;

  // ------------------------------------------------------------ order
  // Bits 14..0 compared as unsigned integers compare magnitudes. Both
  // exponent differences are formed in parallel with the compare, so the
  // compare only selects one (it is the first thing on the a/b -> s path).
  logic       swap;
  logic       sign_x, sub;
  logic [10:0] mx, my;
  logic [4:0]  fx;
  logic [4:0]  d_ab, d_ba, d;

  assign swap   = (b[14:0] > a[14:0]);
  assign d_ab   = fea - feb;
  assign d_ba   = feb - fea;
  assign d      = swap ? d_ba : d_ab;            // Fx - Fy, in [0, 29]
  assign mx     = swap ? mb : ma;
  assign my     = swap ? ma : mb;
  assign fx     = swap ? feb : fea;
  assign sign_x = swap ? b[15] : a[15];          // [FADD-6]: the larger operand's sign
  assign sub    = a[15] ^ b[15];

  // ------------------------------------------------------------ align
  // X = Mx * 8 and Y = (My * 8) >> d: the three low bits are guard, round and
  // sticky. Every bit shifted below Y's bit 0 is ORed into bit 0. For d >= 14
  // only the sticky bit is left, so the shift is capped at 14.
  logic [3:0]  dsh;
  logic [27:0] yext;
  logic [13:0] xa, ya;
  logic        y_lost;

  assign dsh    = (d > 5'd14) ? 4'd14 : d[3:0];
  assign yext   = {my, 17'd0} >> dsh;
  assign y_lost = |yext[13:0];
  assign xa     = {mx, 3'd0};
  assign ya     = {yext[27:15], yext[14] | y_lost};

  // ------------------------------------------------------------ add
  // x has the larger magnitude, so X >= Y and the difference is never
  // negative. sum == 0 is an exact zero sum ([FADD-6]).
  logic [14:0] sum;

  assign sum = sub ? ({1'b0, xa} - {1'b0, ya}) : ({1'b0, xa} + {1'b0, ya});

  // ------------------------------------------------------------ normalise
  // A carry (sum[14]) shifts right by one, keeping the lost bit as sticky,
  // and raises the exponent. Otherwise shift left until bit 13 is the hidden
  // bit or the exponent reaches 1 (the subnormal range stops the shift). A
  // left shift never drops a 1 (it is at most the leading-zero count), and
  // more than one place happens only for d <= 1, where Y lost nothing.
  logic [3:0]  lz;
  logic [4:0]  lsh;
  logic [13:0] norm;
  logic [4:0]  fn;                               // the result's F, in [1, 31]

  always_comb begin
    lz = 4'd14;                                  // sum[13:0] == 0: don't care
    for (int i = 0; i <= 13; i++) begin
      if (sum[i]) lz = 4'(13 - i);
    end
  end

  always_comb begin
    if (sum[14]) begin
      lsh  = 5'd0;
      norm = {sum[14:2], sum[1] | sum[0]};
      fn   = fx + 5'd1;
    end else begin
      lsh  = ({1'b0, lz} < fx - 5'd1) ? {1'b0, lz} : fx - 5'd1;
      norm = sum[13:0] << lsh;
      fn   = fx - lsh;
    end
  end

  // ------------------------------------------------------------ round, [FADD-7]
  logic [10:0] n;
  logic        guard, sticky, inc;
  logic [15:0] mag;
  logic        ovf;

  assign n      = norm[13:3];
  assign guard  = norm[2];
  assign sticky = norm[1] | norm[0];
  // Round to nearest; on a tie (guard set, nothing below it) to even.
  assign inc    = guard & (sticky | n[0]);

  // (F - 1) * 1024 + n: with the hidden bit set this is F * 1024 + m; for a
  // subnormal (F = 1, n < 1024) the exponent field is 0. A rounding carry
  // (n = 2047 + 1, or 1023 + 1 at F = 1) lands in the exponent field. 16 bits:
  // the largest value is 30 * 1024 + 2047 + 1 = 0x8000.
  assign mag = {1'b0, fn - 5'd1, 10'd0} + {5'd0, n} + 16'(inc);
  // |v| rounded to 65536 or more: Inf, no saturation ([FADD-7]).
  assign ovf = (mag >= 16'h7C00);

  // ------------------------------------------------------------ result, [FADD-5]
  always_comb begin
    if (a_nan || b_nan || (a_inf && b_inf && sub)) begin
      s = 16'h7E00;                              // [FADD-8], [TOP-FP-6]
    end else if (a_inf) begin
      s = a;
    end else if (b_inf) begin
      s = b;
    end else if (a_zero && b_zero) begin
      s = {a[15] & b[15], 15'd0};                // [FADD-6]: -0 only for (-0) + (-0)
    end else if (sum == 15'd0) begin
      s = 16'h0000;                              // [FADD-6]: x + (-x) = +0
    end else if (ovf) begin
      s = {sign_x, 15'h7C00};
    end else begin
      // A zero operand needs no case of its own: y = 0 gives sum = X, which
      // normalises and packs back to x bit for bit, subnormals included.
      s = {sign_x, mag[14:0]};
    end
  end

endmodule
