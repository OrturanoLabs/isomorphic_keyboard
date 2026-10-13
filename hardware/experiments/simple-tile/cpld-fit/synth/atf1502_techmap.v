// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// atf1502_techmap.v -- map the Yosys-inferred storage/tri-state cell types of
// tile_cpld onto ATF1502ASV device primitives (synth/atf1502_cells.v).
//
// Observed inference (Yosys 0.69+154, `proc; opt`):
//   16 x $dffsre  <- per-bit chain: D=shift-in, CLK=bclk, CE=!latch,
//                    SET=ap_v[i] (-> AP product term), CLR=ar_v[i] (-> AR
//                    product term). This IS the AP/AR transparent load.
//    1 x $adff    <- 4-bit frame counter, async clear = latch
//    1 x $adffe   <- sticky B_W flag, async clear = latch, CE = set condition
//    2 x $tribuf  <- tclk/lclk output enables (rev-A true tri-state forwarding)
//
// All polarities in this design are positive; wrappers below assume
// POLARITY parameters 1 (they are only instantiated from this design).
// Multi-bit cells are expanded bit-wise so every ATF1502_FF_* instance models
// exactly one macrocell. ARST_VALUE bits select the clear vs preset flavour.

module \$dffsre (CLK, EN, SET, CLR, D, Q);
  parameter WIDTH = 1;
  parameter CLK_POLARITY = 1;
  parameter EN_POLARITY = 1;
  parameter SET_POLARITY = 1;
  parameter CLR_POLARITY = 1;
  input CLK, EN, SET, CLR;
  input  [WIDTH-1:0] D;
  output [WIDTH-1:0] Q;
  genvar i;
  generate for (i = 0; i < WIDTH; i = i + 1) begin : g
    ATF1502_FF_D_SR_CE mc (.C(CLK), .CE(EN), .AP(SET), .AR(CLR), .D(D[i]), .Q(Q[i]));
  end endgenerate
endmodule

module \$adff (CLK, ARST, D, Q);
  parameter WIDTH = 1;
  parameter CLK_POLARITY = 1;
  parameter ARST_POLARITY = 1;
  parameter [WIDTH-1:0] ARST_VALUE = 0;
  input CLK, ARST;
  input  [WIDTH-1:0] D;
  output [WIDTH-1:0] Q;
  genvar i;
  generate for (i = 0; i < WIDTH; i = i + 1) begin : g
    if (ARST_VALUE[i]) begin : preset
      ATF1502_FF_D_AP mc (.C(CLK), .AP(ARST), .D(D[i]), .Q(Q[i]));
    end else begin : clear
      ATF1502_FF_D_AR mc (.C(CLK), .AR(ARST), .D(D[i]), .Q(Q[i]));
    end
  end endgenerate
endmodule

module \$adffe (CLK, ARST, EN, D, Q);
  parameter WIDTH = 1;
  parameter CLK_POLARITY = 1;
  parameter ARST_POLARITY = 1;
  parameter [WIDTH-1:0] ARST_VALUE = 0;
  parameter EN_POLARITY = 1;
  input CLK, ARST, EN;
  input  [WIDTH-1:0] D;
  output [WIDTH-1:0] Q;
  genvar i;
  generate for (i = 0; i < WIDTH; i = i + 1) begin : g
    if (ARST_VALUE[i]) begin : preset
      ATF1502_FF_D_AP_CE mc (.C(CLK), .CE(EN), .AP(ARST), .D(D[i]), .Q(Q[i]));
    end else begin : clear
      ATF1502_FF_D_AR_CE mc (.C(CLK), .CE(EN), .AR(ARST), .D(D[i]), .Q(Q[i]));
    end
  end endgenerate
endmodule

module \$tribuf (A, EN, Y);
  parameter WIDTH = 1;
  input  [WIDTH-1:0] A;
  input EN;
  output [WIDTH-1:0] Y;
  genvar i;
  generate for (i = 0; i < WIDTH; i = i + 1) begin : g
    ATF1502_OBUF_TRI iob (.I(A[i]), .OE(EN), .O(Y[i]));
  end endgenerate
endmodule
