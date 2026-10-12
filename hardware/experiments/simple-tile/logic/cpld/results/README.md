# yosys proxy run (container localhost/oss-cad-suite:2026-09-26)
cmd: yosys -m ghdl -Q -T yosys_proxy.ys

Top cell inventory (generic synthesis, NOT a device fit):
  $aldff x1 (16-bit transparent async parallel load = the two 165 chains)
  $adff  x1 (4-bit counter, async reset = latch)
  $adffe x1 (sticky B_W flag)
  -> 21 FF bits; 2x $tribuf = the two forwarded clocks' OE (as rev A)
ATF1502 mapping note: per-bit SP/AR product terms for transparent load = 2 PT/bit x 16;
practical fit needs the proprietary Microchip fitter -> NO fit/perf claim made here.
