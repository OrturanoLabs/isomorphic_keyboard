// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// atf1502_cells.v -- ATF1502ASV device primitives used by the techmapping
// (synth/tile_cpld_atf1502.ys -> techmap -map synth/atf1502_techmap.v).
//
// These are BLACKBOX models shaped after the ATF1502ASV macrocell flip-flop
// and output-enable sections, per DS20006485A ("Flip-Flop", "I/O Control"):
//   * D-type register; clock from a global clock pin or a product term
//   * asynchronous reset  AR  <- product term (or GCLEAR, or their OR)
//   * asynchronous preset AP  <- product term
//   * register enable CE      <- product term (when the clock is GCK)
//   * per-macrocell tri-state output enable (product term / global OE mux)
//
// The cell library is NOT a timing model and NOT a fuse map. A real fit (PT
// allocation, switch-matrix routing, fuse generation) requires the Microchip
// ProChip/WinCUPL fitter -- see ../fit/run_fitter.sh.

(* blackbox *)
module ATF1502_FF_D_AR (input C, D, AR, output Q); endmodule

(* blackbox *)
module ATF1502_FF_D_AP (input C, D, AP, output Q); endmodule

(* blackbox *)
module ATF1502_FF_D_SR_CE (input C, D, AP, AR, CE, output Q); endmodule

(* blackbox *)
module ATF1502_FF_D_AR_CE (input C, D, AR, CE, output Q); endmodule

(* blackbox *)
module ATF1502_FF_D_AP_CE (input C, D, AP, CE, output Q); endmodule

(* blackbox *)
module ATF1502_OBUF_TRI (input I, OE, output O); endmodule

(* blackbox *)
module ATF1502_GCLKBUF (input I, output O); endmodule
