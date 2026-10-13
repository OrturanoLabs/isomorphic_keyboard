// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// MUTANT CONTROL -- NOT A CANDIDATE.
// Swaps the L_endrow / T_endcol frame bits in the parallel word. The expected
// stream (docs-derived) no longer matches and the TB MUST reject this design.
// Used by sim/run_sims.sh as a control: if the TB ever passes this file, the
// TB is broken and the whole run fails. (Same module name; linked in place of
// the real candidate.)

module tile_cpld (
  input  wire [11:0] buttons,
  input  wire        endrow,
  input  wire        endcol,
  input  wire        bclk,
  input  wire        blatch,
  input  wire        rlatch,
  input  wire        tw,
  input  wire        bfirst,
  input  wire        tdata,
  input  wire        ldata,
  output wire        tclk,
  output wire        lclk,
  output wire        latcho,
  output wire        npl,
  output wire        ds,
  output reg         bw,
  output wire        dout
);
  wire latch = blatch | rlatch;
  assign latcho = latch;
  assign npl    = ~latch;
  wire w = tw & bfirst;
  assign tclk = w ? 1'bz : bclk;
  assign lclk = w ? bclk : 1'bz;
  wire dsin = w ? ldata : tdata;
  assign ds = dsin;

  // MUTATION: flag bits swapped
  wire [15:0] pd = {buttons, 1'b1, 1'b1, endcol, endrow};

  reg [15:0] ar_v;
  reg [15:0] ap_v;
  always @* begin
    ar_v = {16{latch}} & ~pd;
    ap_v = {16{latch}} &  pd;
  end

  reg [15:0] shreg;
  genvar gi;
  generate
    for (gi = 0; gi < 16; gi = gi + 1) begin : g_sr
      always @(posedge bclk or posedge ar_v[gi] or posedge ap_v[gi]) begin
        if (ar_v[gi])      shreg[gi] <= 1'b0;
        else if (ap_v[gi]) shreg[gi] <= 1'b1;
        else if (!latch)   shreg[gi] <= (gi == 0) ? dsin : shreg[gi-1];
      end
    end
  endgenerate
  assign dout = shreg[15];

  reg [3:0] cnt;
  always @(posedge bclk or posedge latch) begin
    if (latch) cnt <= 4'd0;
    else       cnt <= cnt + 4'd1;
  end
  always @(posedge bclk or posedge latch) begin
    if (latch) bw <= 1'b0;
    else if (!bw && shreg[15] && (cnt == 4'd15)) bw <= 1'b1;
  end
endmodule
