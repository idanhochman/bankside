# The clock every module is synthesized against (the synth skill).
#
# [TOP-ARCH-3]: one clock, 300 MHz, so 3333 ps. BANKSIDE_CLOCK_PS overrides it
# only for exploring (synth --clock-ps); syn/ppa.yaml is always at 3333 ps.
#
# - A module with a `clk` port gets a real clock on it. Its other inputs arrive,
#   and its outputs must be ready, 20% of the period from the edge: the
#   neighbouring modules' registers and wires.
# - A module without one (a combinational unit, such as fp16_mul) is timed
#   against a virtual clock with no input or output allowance, so its slack is
#   the period minus its own longest input-to-output delay. Its parent's
#   overheads are checked when the parent is synthesized ([FMUL-11],
#   [FADD-11]).
set period 3333
if {[info exists ::env(BANKSIDE_CLOCK_PS)]} { set period $::env(BANKSIDE_CLOCK_PS) }

if {[llength [get_ports -quiet clk]]} {
  puts "bankside-sdc: clocked, period $period ps"
  create_clock -name core_clock -period $period [get_ports clk]
  set io [expr {$period * 0.2}]
  set_input_delay  $io -clock core_clock [all_inputs -no_clocks]
  set_output_delay $io -clock core_clock [all_outputs]
} else {
  puts "bankside-sdc: combinational, period $period ps"
  create_clock -name core_clock -period $period
  set_input_delay  0 -clock core_clock [all_inputs]
  set_output_delay 0 -clock core_clock [all_outputs]
}
