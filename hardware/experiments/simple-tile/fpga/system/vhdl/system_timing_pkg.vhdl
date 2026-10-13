-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Timing constants for the FPGA-tile chain system model (fpga/system).
--
-- Values are transcribed from
--   hardware/experiments/simple-tile/fpga/system/cfg/corners.json
-- which is the single source of truth; results/check_system_sync.py FAILS on
-- drift. The JSON records per-value provenance:
--   * interior values anchor to the FITTED nextpnr max-analysis numbers in
--     results/interior_delays.json (GW1NZ-LV1QN48, SNAP_MODE="fall");
--   * exterior values (pads, TBUF en/dis, hop route) are SYNTHETIC because no
--     open device IO timing model exists here (DS861 gate). They are
--     exploration knobs, not hardware sign-off.
--
-- Corner selector: CORNER 0 = syn_min, 1 = fit (fitted anchor corner),
--                  2 = syn_max.

library ieee;
use ieee.std_logic_1164.all;

package system_timing_pkg is

  -- ------------------------- fitted interior anchors (GW1NZ fall, nextpnr
  -- post-route max-analysis; see results/interior_delays.json anchors):
  --   clk-to-q element       0.46 ns
  --   critical path total    3.93 ns (logic 1.36 + routing 2.57)
  --   cross-domain negedge latch -> posedge clk   4.86 ns (+0.04 setup)
  --   interior shift-clock Fmax                   254.84 MHz
  -- and gw1nz track: posedge sysclk -> posedge clk 5.59 ns (recorded for the
  -- track characterisation unit).

  -- per-value triplets [syn_min, fit, syn_max] (ns), corners.json "delays_ns":
  constant T_PADIN_NS   : real := 0.5;  constant T_PADIN_F_NS  : real := 1.5;
  constant T_PADIN_X_NS : real := 3.0;
  constant T_DO_INT_NS  : real := 0.7;  constant T_DO_INT_F_NS : real := 1.5;
  constant T_DO_INT_X_NS : real := 3.93;
  constant T_BW_INT_NS  : real := 0.7;  constant T_BW_INT_F_NS : real := 1.5;
  constant T_BW_INT_X_NS : real := 3.93;
  constant T_LATCHO_INT_NS   : real := 0.3;  constant T_LATCHO_INT_F_NS : real := 0.8;
  constant T_LATCHO_INT_X_NS : real := 2.0;
  constant T_PADOUT_NS   : real := 0.5;  constant T_PADOUT_F_NS : real := 1.5;
  constant T_PADOUT_X_NS : real := 3.0;
  constant T_TBUF_EN_NS  : real := 0.3;  constant T_TBUF_EN_F_NS : real := 1.0;
  constant T_TBUF_EN_X_NS : real := 2.5;
  constant T_TBUF_DIS_NS  : real := 0.3;  constant T_TBUF_DIS_F_NS : real := 1.0;
  constant T_TBUF_DIS_X_NS : real := 2.5;
  constant T_TBUF_PD_NS   : real := 0.3;  constant T_TBUF_PD_F_NS : real := 1.0;
  constant T_TBUF_PD_X_NS : real := 2.0;
  constant T_XDOM_REQ_NS  : real := 1.5;  constant T_XDOM_REQ_F_NS : real := 4.9;
  constant T_XDOM_REQ_X_NS : real := 4.9;
  constant T_SNAP_SU_NS   : real := 0.2;  constant T_SNAP_SU_F_NS : real := 0.5;
  constant T_SNAP_SU_X_NS : real := 0.8;
  constant T_SNAP_HD_NS   : real := 0.2;  constant T_SNAP_HD_F_NS : real := 0.5;
  constant T_SNAP_HD_X_NS : real := 0.8;
  constant T_CLKHI_REQ_NS : real := 3.0;  constant T_CLKHI_REQ_F_NS : real := 5.0;
  constant T_CLKHI_REQ_X_NS : real := 8.0;
  constant ROUTE_HOP_NS   : real := 0.2;  constant ROUTE_HOP_F_NS : real := 1.5;
  constant ROUTE_HOP_X_NS : real := 3.0;

  -- corner selector: CORNER 0/1/2 returns the triplet element
  function pick_ns(a : real; b : real; c : real; corner : natural) return time;

  -- default controller-settle requirement for returned data at the sample
  -- point (synthetic guard band, ns): scaled per corner like the others.
  constant T_SETTLE_REQ_NS  : real := 1.0;

end package;

package body system_timing_pkg is

  function pick_ns(a : real; b : real; c : real; corner : natural) return time is
  begin
    case corner is
      when 0      => return a * 1 ns;
      when 2      => return c * 1 ns;
      when others => return b * 1 ns;
    end case;
  end function;

end package body;
