// SPDX-License-Identifier: CERN-OHL-S-2.0
//
// tile_cpld_tb.v -- self-checking Verilog testbench for the ATF1502ASV
// one-chip tile candidate (tile_cpld.v). Compares, on every sample and every
// clock edge:
//
//   DUT -- src/tile_cpld.v           (AP/AR per-bit transparent load)
//   REF -- rev-A structure modelled in this file: two 74HC165-class
//          level-transparent PISO registers + rev-A glue (latch OR/invert,
//          W muxes, 6-bit counter, unguarded sticky B_W flag), wired exactly
//          like hardware/simulation/tile.vhdl (sr1/sr2, ffinput chain);
//   EXP -- an independent docs-derived shift/flag model
//          (docs/architecture/protocol.md frame layout + traversal).
//
// Properties pinned down (mirroring the rev-A regression discipline,
// regression/tile_grid_tb.vhdl, 20 MHz behavioural cadence -- sample BEFORE
// the shift clock):
//   * first frame bit valid on the chain output BEFORE the first shift clock;
//   * load is TRANSPARENT: keys changed during the latch window are tracked
//     by the chain output (level-sensitive /PL semantics of the real 165);
//   * per-frame wire order buttons[11..0],1,1,endrow,endcol, markers 11;
//   * sticky B_W flag: cleared by latch (via blatch AND via rlatch), sets
//     exactly at edge 16*h of the column traversal, stays set otherwise;
//   * W mux: tclk driven / lclk released-'Z' while W=0, reversed while W=1;
//     ds switches tdata->ldata at the documented edge;
//   * reset: second scan pass must produce fresh frames (counters/flags clear);
//   * clock-gating: checked tclk/lclk against 'Z' with case-equality.
//
// Exit: nonzero (via $fatal) on any mismatch; prints "CPLD_FIT_TB PASS" last.

`timescale 1ns/1ns

// ---------------------------------------------------------------------------
// 74HC165-class 8-bit PISO register, testbench-only model.
// Level-transparent /PL section + rising-edge shift, mirroring
// hardware/simulation/74hc165.vhdl (process(nPL, CP, D)). The shadow bit cp_d
// is written in the same evaluation, keeping the single process race-free.
// ---------------------------------------------------------------------------
module ref_hc165 (
  input  wire       nPL,
  input  wire       CP,
  input  wire       DS,
  input  wire [7:0] D,
  output wire       Q7
);
  reg [7:0] qs;
  reg       cp_d;
  initial cp_d = 1'b0;
  always @(nPL or CP or D) begin
    if (!nPL) qs = D;
    else if (CP && !cp_d) qs = {qs[6:0], DS};
    cp_d = CP;
  end
  assign Q7 = qs[7];
endmodule

// ---------------------------------------------------------------------------
// rev-A reference tile: two '165s + glue, structure per
// hardware/simulation/tile.vhdl (sr1 = buttons[11:4] toward the output,
// sr2 = buttons[3:0],"11",L_endrow,T_endcol feeding sr1's DS) and
// docs/architecture/protocol.md.
// ---------------------------------------------------------------------------
module reva_ref (
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
  output wire        bw,
  output wire        dout
);
  wire latch = blatch | rlatch;
  assign latcho = latch;
  assign npl = ~latch;
  wire w = tw & bfirst;
  assign tclk = w ? 1'bz : bclk;
  assign lclk = w ? bclk : 1'bz;
  wire dsin = w ? ldata : tdata;
  assign ds = dsin;

  wire bridge;
  wire [7:0] sr2_inputs = {buttons[3:0], 1'b1, 1'b1, endrow, endcol};
  ref_hc165 srA (.nPL(npl), .CP(bclk), .DS(bridge), .D(buttons[11:4]), .Q7(dout));
  ref_hc165 srB (.nPL(npl), .CP(bclk), .DS(dsin),   .D(sr2_inputs),    .Q7(bridge));

  reg [5:0] cnt;          // 6-bit counter, as tile.vhdl (low 4 bits decoded)
  reg       bwf;
  wire ffinput = &cnt[3:0] & dout;
  always @(posedge bclk or posedge latch) begin
    if (latch) cnt <= 6'd0;
    else       cnt <= cnt + 6'd1;
  end
  always @(posedge bclk or posedge latch) begin
    if (latch) bwf <= 1'b0;
    else if (ffinput) bwf <= 1'b1;   // unguarded sticky set, as tile.vhdl
  end
  assign bw = bwf;
endmodule

// ---------------------------------------------------------------------------
// Testbench
// ---------------------------------------------------------------------------
module tile_cpld_tb;

  localparam TCLK = 50;   // 20 MHz behavioural shift clock (50 ns)

  // stimulus registers
  reg  [11:0] buttons = 12'h000;
  reg         endrow  = 1'b1;
  reg         endcol  = 1'b0;
  reg         bclk    = 1'b0;
  reg         blatch  = 1'b0;
  reg         rlatch  = 1'b0;
  reg         tw      = 1'b0;
  reg         bfirst  = 1'b1;
  reg         tdata   = 1'b0;
  reg         ldata   = 1'b0;

  // DUT
  wire dut_tclk, dut_lclk, dut_latcho, dut_npl, dut_ds, dut_bw, dut_dout;
  tile_cpld dut (
    .buttons(buttons), .endrow(endrow), .endcol(endcol),
    .bclk(bclk), .blatch(blatch), .rlatch(rlatch),
    .tw(tw), .bfirst(bfirst), .tdata(tdata), .ldata(ldata),
    .tclk(dut_tclk), .lclk(dut_lclk), .latcho(dut_latcho),
    .npl(dut_npl), .ds(dut_ds), .bw(dut_bw), .dout(dut_dout)
  );

  // REF (rev-A structure)
  wire ref_tclk, ref_lclk, ref_latcho, ref_npl, ref_ds, ref_bw, ref_dout;
  reva_ref ref0 (
    .buttons(buttons), .endrow(endrow), .endcol(endcol),
    .bclk(bclk), .blatch(blatch), .rlatch(rlatch),
    .tw(tw), .bfirst(bfirst), .tdata(tdata), .ldata(ldata),
    .tclk(ref_tclk), .lclk(ref_lclk), .latcho(ref_latcho),
    .npl(ref_npl), .ds(ref_ds), .bw(ref_bw), .dout(ref_dout)
  );

  integer errors = 0;
  integer checks = 0;

  task chk;
    input        cond;
    input [8*200-1:0] msg;
    begin
      checks = checks + 1;
      if (!cond) begin
        errors = errors + 1;
        $display("FAIL [%0t]: %0s", $time, msg);
      end
    end
  endtask

  // ---------------------------------------------------------
  // EXP: independent docs-derived shift/flag model
  // ---------------------------------------------------------
  reg [15:0] exp_m;
  reg  [3:0] exp_cnt;
  reg        exp_bw;

  task exp_latch;
    begin
      exp_m   = {buttons, 1'b1, 1'b1, endrow, endcol};
      exp_cnt = 4'd0;
      exp_bw  = 1'b0;
    end
  endtask

  // one shift edge with serial input din: flag decision uses PRE-edge values
  // (the sampled bit and the count at the moment of the edge), exactly like
  // the hardware sampling data/cnt at the rising clock.
  task exp_edge;
    input din;
    begin
      if (!exp_bw && (exp_cnt == 4'd15) && exp_m[15]) exp_bw = 1'b1;
      exp_m   = {exp_m[14:0], din};
      exp_cnt = exp_cnt + 4'd1;
    end
  endtask

  // frames in time order: [0..11]=keys msb-first, [12],[13]=markers, [14]=er,
  // [15]=ec. Packed as vectors FR[0] .. FR[15].
  reg [15:0] frame_own;   // filled per scan
  reg [15:0] frame_t;     // frame injected via tdata (tile above)
  reg [15:0] frame_l;     // frame injected via ldata (next column)

  // frame_t/frame_l as timed injection: edge k of a 16-edge window injects
  // frame[k-1] (the neighbour emits its key[11] first; it exits the bottom
  // tile in the same order -- FIFO through one 16-deep chain).
  function frame_bit;
    input [15:0] fr;
    input integer idx;
    frame_bit = fr[15 - idx];   // idx 0 = first bit in time
  endfunction

  function [15:0] mkframe;
    input [11:0] keys;
    input        er, ec;
    begin
      mkframe = {keys, 1'b1, 1'b1, er, ec};
    end
  endfunction

  // stripes: expected output at sample s (after s edges) before edge s+1.
  // sample s reads the model top: exp_m[15].

  // ---------------- clocked scan engine ----------------------
  // One pass = 2 phases: latch window, then clocked edges.
  integer k;
  reg     din_k;
  reg     w_stim;

  task drive_edge_inputs;
    input integer edge_no;   // 1-based
    begin
      // serial input for THIS edge, per current W path
      if (!w_stim) tdata = (edge_no <= 16) ? frame_bit(frame_t, edge_no-1) : 1'b0;
      if ( w_stim) ldata = ((edge_no >= 17) && (edge_no <= 32))
                             ? frame_bit(frame_l, edge_no-17) : 1'b0;
    end
  endtask

  task one_edge;
    input integer edge_no;
    begin
      w_stim = tw & bfirst;
      drive_edge_inputs(edge_no);
      #2;
      // ---- pre-edge (sample phase, clock low): stream + levels ----
      chk(dut_dout === exp_m[15], "DUT dout != expected stream bit");
      chk(ref_dout === exp_m[15], "REF dout != expected stream bit");
      chk(dut_dout === ref_dout,  "DUT dout != REF dout");
      chk(dut_bw   === exp_bw,    "DUT B_W != expected flag (pre-edge)");
      chk(ref_bw   === exp_bw,    "REF B_W != expected flag (pre-edge)");
      chk(dut_ds === (w_stim ? ldata : tdata), "DUT ds mux wrong");
      chk(ref_ds === dut_ds,      "REF ds != DUT ds");
      chk(dut_npl === 1'b1,       "DUT npl not high outside latch");
      chk(dut_latcho === 1'b0,    "DUT latcho not low outside latch");
      if (!w_stim) begin
        chk(dut_tclk === 1'b0, "DUT tclk should forward bclk(0) at W=0");
        chk(dut_lclk === 1'bz, "DUT lclk should be released 'Z' at W=0");
        chk(ref_tclk === 1'b0, "REF tclk should forward bclk(0) at W=0");
        chk(ref_lclk === 1'bz, "REF lclk should be released 'Z' at W=0");
      end else begin
        chk(dut_tclk === 1'bz, "DUT tclk should be released 'Z' at W=1");
        chk(dut_lclk === 1'b0, "DUT lclk should forward bclk(0) at W=1");
        chk(ref_tclk === 1'bz, "REF tclk should be released 'Z' at W=1");
        chk(ref_lclk === 1'b0, "REF lclk should forward bclk(0) at W=1");
      end
      // ---- rising edge ----
      bclk = 1;
      #10;
      exp_edge(w_stim ? ldata : tdata);
      chk(dut_bw === exp_bw, "DUT B_W != expected flag (post-edge)");
      chk(ref_bw === exp_bw, "REF B_W != expected flag (post-edge)");
      #15;
      bclk = 0;
      #5;
      // ---- post-edge clock-low phase: mux lines follow W again ----
      if (!w_stim) begin
        chk(dut_tclk === 1'b0 && dut_lclk === 1'bz, "DUT clock mux wrong after edge (W=0)");
      end else begin
        chk(dut_tclk === 1'bz && dut_lclk === 1'b0, "DUT clock mux wrong after edge (W=1)");
      end
      #13;
    end
  endtask

  // ------------------------------------------------------------
  initial begin : watchdog
    #1000000;
    $fatal(1, "TIMEOUT -- testbench did not finish");
  end

  initial begin
    // --------------------------------------------------
    // SCAN A: bottom tile of a column of height 2.
    //  own frame (endcol=0), then the tile-above frame via T_data (W=0),
    //  W flips after edge 16 (tw from the tile above), then the next
    //  column's frame via L_data, then an all-zero idle tail.
    // --------------------------------------------------
    buttons = 12'hA53; endrow = 1'b1; endcol = 1'b0;
    bfirst  = 1'b1;    tw     = 1'b0;
    frame_own = mkframe(buttons, endrow, endcol);
    frame_t   = mkframe(12'h5A6, 1'b0, 1'b1);   // tile above: top of column
    frame_l   = mkframe(12'hC39, 1'b1, 1'b0);   // next column's first frame

    // -- latch window (via blatch) --
    blatch = 1;
    #(4*TCLK);
    chk(dut_latcho === 1'b1, "DUT latcho must follow blatch");
    chk(dut_npl === 1'b0,    "DUT npl must be low during latch");
    chk(dut_bw === 1'b0,     "DUT B_W must be cleared by latch");
    chk(ref_bw === 1'b0,     "REF B_W must be cleared by latch");
    // transparency: first bit valid DURING the latch window, before any clock
    exp_latch();
    #1;
    chk(dut_dout === buttons[11], "DUT first bit not valid before first clock (latch window)");
    chk(ref_dout === buttons[11], "REF first bit not valid before first clock (latch window)");
    // -- transparency: change keys mid-latch; the chain output must track --
    buttons = 12'h96D; frame_own = mkframe(buttons, endrow, endcol); exp_latch(); #10;
    chk(dut_dout === 1'b1, "DUT transparent load: buttons[11]=1 must follow during latch");
    chk(ref_dout === 1'b1, "REF transparent load: buttons[11]=1 must follow during latch");
    buttons = 12'h16D; frame_own = mkframe(buttons, endrow, endcol); exp_latch(); #10;
    chk(dut_dout === 1'b0, "DUT transparent load: buttons[11]=0 must follow during latch");
    chk(ref_dout === 1'b0, "REF transparent load: buttons[11]=0 must follow during latch");
    buttons = 12'h96D; frame_own = mkframe(buttons, endrow, endcol); exp_latch(); #10;
    chk(dut_dout === 1'b1, "DUT transparent load: re-settle to 1 during latch");
    // -- drop latch; first bit must still be valid BEFORE the first clock --
    blatch = 0;
    #(TCLK/2 - 5);
    chk(dut_dout === frame_bit(frame_own,0), "DUT first bit not present before first shift clock");
    chk(ref_dout === frame_bit(frame_own,0), "REF first bit not present before first shift clock");
    // -- 48 clocked edges: own frame + T frame + L frame --
    for (k = 1; k <= 48; k = k + 1) begin
      one_edge(k);
      if (k == 16) begin
        tw = 1'b1;   // the tile above's B_W sets at ITS own edge 16(h=2)
        #1;
        chk(dut_ds === ldata, "DUT ds must switch to L_data once W=1");
        chk(dut_tclk === 1'bz && dut_lclk === 1'b0, "DUT clock forwarding must flip to the left");
      end
      if (k == 32) begin
        chk(exp_bw === 1'b1, "EXP: column-end flag must be set after edge 32 (16*h)");
        chk(dut_bw === 1'b1, "DUT: column-end flag must be set after edge 32 (16*h)");
      end
    end
    // -- idle tail: ldata now 0, sticky flag must hold --
    ldata = 1'b0;
    for (k = 49; k <= 52; k = k + 1) begin
      one_edge(k);
      chk(dut_bw === 1'b1, "DUT B_W must stay set until the next latch");
    end

    // --------------------------------------------------
    // SCAN B: reset via rlatch. Single-tile column (endcol=1): B_W of this
    // tile must set at exactly edge 16; tw stays 0 (W=0 the whole scan).
    // --------------------------------------------------
    buttons = 12'h0F0; endrow = 1'b0; endcol = 1'b1;
    tw = 1'b0;
    frame_own = mkframe(buttons, endrow, endcol);
    frame_t   = {16{1'b0}};
    frame_l   = {16{1'b0}};
    rlatch = 1;
    #(4*TCLK);
    chk(dut_latcho === 1'b1, "DUT latcho must follow rlatch");
    chk(dut_bw === 1'b0,     "DUT B_W must be cleared by rlatch");
    chk(ref_bw === 1'b0,     "REF B_W must be cleared by rlatch");
    exp_latch();
    #1;
    chk(dut_dout === buttons[11], "DUT first bit not valid before first clock (scan B)");
    rlatch = 0;
    #(TCLK/2 - 5);
    chk(dut_dout === frame_bit(frame_own,0), "DUT scan B first bit wrong");
    for (k = 1; k <= 20; k = k + 1) begin
      one_edge(k);
      if (k == 16) begin
        chk(dut_bw === 1'b1, "DUT: endcol=1 frame must set B_W at edge 16");
      end
      if (k == 15) begin
        chk(dut_bw === 1'b0, "DUT: B_W must NOT be set at edge 15");
      end
    end

    // --------------------------------------------------
    if (errors) $fatal(1, "CPLD_FIT_TB FAIL: %0d error(s) in %0d checks", errors, checks);
    $display("CPLD_FIT_TB PASS: %0d checks, 0 errors (2 scans, frames+flags+mux+transparency)", checks);
    $finish;
  end

endmodule
