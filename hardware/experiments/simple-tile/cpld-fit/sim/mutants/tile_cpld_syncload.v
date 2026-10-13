// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// MUTANT CONTROL -- NOT A CANDIDATE.
// Synchronous parallel load (load-on-first-clock). This is the classic
// architecture mistake for this protocol: the rev-A scan samples the first
// bit BEFORE any shift clock, after a latch window during which the clock
// stays low, so a sync-load chain still holds stale/unknown data at that
// sample. src/tile_cpld_tb.v MUST reject this design. Used by
// sim/run_sims.sh as a control: if the TB ever passes this file, the TB is
// broken and the whole run fails. (Same module name; linked in place of the
// real candidate.)

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
  wire [15:0] pd = {buttons, 1'b1, 1'b1, endrow, endcol};

  reg [15:0] shreg;
  genvar gi;
  generate
    for (gi = 0; gi < 16; gi = gi + 1) begin : g_sr
      // MUTATION: load only on a clock edge
      always @(posedge bclk) begin
        if (latch) shreg[gi] <= pd[gi];
        else       shreg[gi] <= (gi == 0) ? dsin : shreg[gi-1];
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
