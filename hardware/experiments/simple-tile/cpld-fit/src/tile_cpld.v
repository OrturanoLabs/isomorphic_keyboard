// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// tile_cpld.v -- ATF1502ASV one-chip simple-tile candidate, Verilog port of the
// designated reference logic/cpld/tile_full.vhdl (READ-ONLY; checked in by the
// logic workstream). One CPLD per tile: the two 74LVC165A shift chains AND the
// whole rev-A glue (latch OR, W muxes, 4-bit frame counter, sticky B_W flag).
// No MCU, no Hall keys, no LED on the tile -- 12 contact keys in, one
// B_data/R_data chain out.
//
// PARALLEL LOAD FORMULATION (the reason this file exists):
// the 16 chain stages are written PER BIT with orthogonal async preset / async
// reset controls
//     AP[i] = latch &  pd[i]        (async PRESET  product term of macrocell i)
//     AR[i] = latch & ~pd[i]        (async RESET   product term of macrocell i)
// While `latch` is high, stage i FOLLOWS pd[i] combinationally -- the
// level-sensitive 74x165 /PL semantics: the first frame bit (buttons[11]) is
// valid on the chain output BEFORE the first shift clock
// (docs/architecture/protocol.md scan step 2; hardware/simulation/74hc165.vhdl
// models the same level transparency). On the ATF1502ASV this maps onto the
// macrocell flip-flop's AR input (a product term, or GCLEAR, or their OR) and
// AP input (a product term), which are ORTHOGONAL to the registered data path
// (DS20006485A "Flip-Flop" section; the PT3/PT5 product-term numbering for
// AR/AP is prjbureau fusemap-fuzzing documentation, a secondary source NOT
// re-verified this session -- no network). The shift data path needs no extra
// load mux: load action lives entirely in the AP/AR control terms.
//
// Race-free note: ar_v/ap_v are written by ONE comb process, reset before
// preset, so under IEEE-1364 scheduling a rising control never observes a
// stale complementary control (see ../docs/ap-ar-mapping.md).
//
// The `else if (!latch)` guard makes a clock edge DURING the latch window a
// no-op for the chain (load dominates), matching tile_full.vhdl's if/elsif
// priority and the real 74x165 (clock ignored while /PL is active).
//
// Zero-delay behavioural RTL for the self-checking TB and the Yosys/EDIF
// mapping flow. NOT a fitted or timing-closed design -- the ATF1502 fitter is
// proprietary (Microchip ProChip/WinCUPL); see ../fit/run_fitter.sh.

module tile_cpld (
  input  wire [11:0] buttons, // 12 keys, '1' = pressed
  input  wire        endrow,  // L_endrow ('0' = a tile stands to the left)
  input  wire        endcol,  // T_endcol ('1' = this tile is the top of its column)
  input  wire        bclk,    // B_clk/R_clk merged board-clock net (GCLK pin)
  input  wire        blatch,  // B_latch (controller)
  input  wire        rlatch,  // R_latch (right neighbour)
  input  wire        tw,      // T_W: B_W output of the tile above
  input  wire        bfirst,  // B_first: '1' = bottom tile of a column
  input  wire        tdata,   // T_data: chain serial in, from the tile above
  input  wire        ldata,   // L_data: chain serial in, from the left column
  output wire        tclk,    // T_clk: clock forwarded up    while W=0, else 'Z'
  output wire        lclk,    // L_clk: clock forwarded left  while W=1, else 'Z'
  output wire        latcho,  // merged latch, forwarded to T_latch/L_latch
  output wire        npl,     // observability only (internal node in the fit)
  output wire        ds,      // observability only (internal node in the fit)
  output reg         bw,      // B_W: sticky "column top has passed" flag
  output wire        dout     // chain output -> B_data/R_data net
);

  // ---- merged latch (rev-A U106A + U105) --------------------------------------
  wire latch = blatch | rlatch;
  assign latcho = latch;
  assign npl    = ~latch;

  // ---- W mux (rev-A U102B) ----------------------------------------------------
  wire w = tw & bfirst;

  // true-tri-state clock forwarding, exactly as rev A (U107 '125 / U101 '126):
  // the unselected output is RELEASED ('Z'), not driven low.
  assign tclk = w ? 1'bz : bclk;
  assign lclk = w ? bclk : 1'bz;

  // serial input mux (T_data through the '125 when W=0, L_data '126 when W=1)
  wire dsin = w ? ldata : tdata;
  assign ds = dsin;

  // ---- parallel word, chain output order (first bit out first) ---------------
  //     buttons[11], buttons[10], ..., buttons[0], '1', '1', endrow, endcol
  // ground truth: hardware/simulation/tile.vhdl sr1/sr2 wiring and the rev-A
  // regression stream (regression/results.md).
  wire [15:0] pd = {buttons, 1'b1, 1'b1, endrow, endcol};

  // ---- per-macrocell async control product terms ------------------------------
  // Single comb process, reset written before preset (event-ordering safety).
  reg [15:0] ar_v;
  reg [15:0] ap_v;
  always @* begin
    ar_v = {16{latch}} & ~pd;
    ap_v = {16{latch}} &  pd;
  end

  // ---- 16-bit PISO chain; per-bit AP/AR transparent parallel load -------------
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

  // ---- bit counter ('161-class: synchronous count, asynchronous clear) --------
  // tile_full.vhdl counts 4 bits; the sampled quantity is "count == 15" at the
  // flag FF, identical to tile.vhdl decoding the low 4 bits of its 6-bit count.
  reg [3:0] cnt;
  always @(posedge bclk or posedge latch) begin
    if (latch) cnt <= 4'd0;
    else       cnt <= cnt + 4'd1;
  end

  // ---- sticky column-end flag B_W ('74-class: async clear, sticky set) --------
  // Sets at the rising edge where the 16th bit of a frame with endcol='1' is
  // presented on the chain output (cnt==15 samples the pre-edge value).
  always @(posedge bclk or posedge latch) begin
    if (latch) bw <= 1'b0;
    else if (!bw && shreg[15] && (cnt == 4'd15)) bw <= 1'b1;
  end

endmodule
