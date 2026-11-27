// fp16_mul: one lane of the S3 multiply. IEEE 754 binary16 a x b, round to
// nearest even, subnormals in and out, every NaN result 0x7E00, no flags.
// Spec: src/fp16_mul/doc/README.md.
//
// [FMUL-1], [FMUL-3], [FMUL-11], [TOP-HIER-3]: purely combinational, no clock,
// reset, state or parameters; the only paths are a -> p and b -> p.
//
// Structure [bankside]: one 11 x 11 significand multiply, a leading-zero count
// on the 22-bit product, then a single alignment that puts the product's
// quantum bit at a fixed position (bit 11): a left shift for a normal result
// (or a subnormal one reached by normalising), a right shift when the
// exponents alone already put the result below the normal range. Guard and
// sticky round to nearest even, and the rounding carry runs into the exponent
// field by itself. Special operands are chosen by a final multiplexer.

module fp16_mul (
  input  logic [15:0] a,
  input  logic [15:0] b,
  output logic [15:0] p
);

  // ------------------------------------------------------------ unpack, [FMUL-4]
  logic       sign;
  logic [4:0] ea, eb;
  logic [9:0] fa, fb;
  logic       a_zero, b_zero, a_inf, b_inf, a_nan, b_nan;

  assign sign = a[15] ^ b[15];                          // [FMUL-6]
  assign ea   = a[14:10];
  assign eb   = b[14:10];
  assign fa   = a[9:0];
  assign fb   = b[9:0];

  assign a_zero = (ea == 5'd0)  && (fa == 10'd0);
  assign b_zero = (eb == 5'd0)  && (fb == 10'd0);
  assign a_inf  = (ea == 5'd31) && (fa == 10'd0);
  assign b_inf  = (eb == 5'd31) && (fb == 10'd0);
  // [FMUL-4], [FMUL-8]: signalling and quiet NaNs, any payload, are alike.
  assign a_nan  = (ea == 5'd31) && (fa != 10'd0);
  assign b_nan  = (eb == 5'd31) && (fb != 10'd0);

  // Significand with the hidden bit; a subnormal's exponent counts as 1.
  logic [10:0] ma, mb;
  logic [4:0]  ea_eff, eb_eff;

  assign ma     = {ea != 5'd0, fa};
  assign mb     = {eb != 5'd0, fb};
  assign ea_eff = (ea == 5'd0) ? 5'd1 : ea;
  assign eb_eff = (eb == 5'd0) ? 5'd1 : eb;

  // ---------------------------------------------------------------- multiply
  // Exact: value(a) x value(b) = prod * 2^(ea_eff + eb_eff - 50).
  logic [21:0] prod;

  assign prod = {11'd0, ma} * {11'd0, mb};

  // Leading-zero count of prod. prod is never 0 when both operands are
  // finite non-zero (the smallest is 1 x 1), so lz <= 21 there; for a zero
  // operand the value is don't-care, the special mux below overrides it.
  logic [4:0] lz;

  always_comb begin
    lz = 5'd21;
    for (int i = 0; i <= 21; i++) begin
      if (prod[i]) lz = 5'(21 - i);
    end
  end

  // ------------------------------------------------------- exponent, align
  // be0: the biased exponent field the result would have if prod's leading 1
  // were at bit 21, be0 = ea_eff + eb_eff - 14, in [-12, 46].
  // be:  the true biased exponent field, be0 - lz, in [-33, 46].
  // Signed 8 bits hold both.
  logic signed [7:0] be0, be;

  assign be0 = $signed({3'd0, ea_eff}) + $signed({3'd0, eb_eff}) - 8'sd14;
  assign be  = be0 - $signed({3'd0, lz});

  // Align so that bit 11 of q carries the result's quantum and bit 21 is the
  // hidden bit of a normal result:
  //   be0 >= 1, lz <= be0 - 1: normal; shift left by lz, q[21] = 1.
  //   be0 >= 1, lz >  be0 - 1: subnormal; shift left only by be0 - 1, so that
  //                            bit 21 weighs 2^-14 and bit 11 2^-24.
  //   be0 <= 0:                subnormal or zero; shift right by 1 - be0
  //                            (1 to 13), the lost bits go to sticky.
  // The left shift never drops a 1 (it is at most lz), so only the right
  // shift feeds sticky. q[21] is 1 exactly when the result is normal.
  logic        go_right;
  logic [4:0]  lsh;
  logic [3:0]  rsh;
  logic [34:0] rext;
  logic [21:0] q;
  logic        lost;

  assign go_right = (be0 <= 8'sd0);

  always_comb begin
    if (go_right) begin
      lsh = 5'd0;
    end else if ($signed({3'd0, lz}) <= be0 - 8'sd1) begin
      lsh = lz;
    end else begin
      lsh = be0[4:0] - 5'd1;     // be0 in [1, 21] here, since be0 - 1 < lz <= 21
    end
  end

  // be0 in [-12, 0] when go_right, so 1 - be0 is in [1, 13] and fits 4 bits.
  assign rsh  = go_right ? 4'(8'sd1 - be0) : 4'd0;
  assign rext = {prod, 13'd0} >> rsh;
  assign lost = |rext[12:0];
  assign q    = go_right ? rext[34:13] : (prod << lsh);

  // ------------------------------------------------------ round, [FMUL-7]
  logic        normal;
  logic        guard, sticky, inc;
  logic [4:0]  efield;
  logic [14:0] mag_trunc, mag_round;
  logic        ovf;

  assign normal = q[21];
  assign guard  = q[10];
  assign sticky = (|q[9:0]) | lost;
  // Round to nearest; on a tie (guard set, nothing below it) to even.
  assign inc    = guard & (sticky | q[11]);

  // A normal result's exponent field is be in [1, 30] unless it overflows;
  // a subnormal one's is 0, and its hidden bit q[21] is 0 too.
  assign efield    = normal ? be[4:0] : 5'd0;
  assign mag_trunc = {efield, q[20:11]};
  // A carry out of the significand lands in the exponent field: 0x03FF + 1 is
  // the smallest normal 0x0400, 0x7BFF + 1 is Inf 0x7C00 ([FMUL-7]).
  assign mag_round = mag_trunc + 15'(inc);

  // be >= 31 before rounding is |v| >= 2^16: Inf. be <= 30 that rounds up
  // past 65504 gives 0x7C00 through the carry above. No saturation.
  assign ovf = normal && (be >= 8'sd31);

  // ---------------------------------------------------- result, [FMUL-5]
  always_comb begin
    if (a_nan || b_nan || (a_zero && b_inf) || (a_inf && b_zero)) begin
      p = 16'h7E00;                                     // [FMUL-8], [TOP-FP-6]
    end else if (a_inf || b_inf) begin
      p = {sign, 15'h7C00};
    end else if (a_zero || b_zero) begin
      p = {sign, 15'h0000};
    end else if (ovf) begin
      p = {sign, 15'h7C00};
    end else begin
      p = {sign, mag_round};                            // [FMUL-6]: zero keeps sign
    end
  end

endmodule
