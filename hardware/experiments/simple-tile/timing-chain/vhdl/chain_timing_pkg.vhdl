-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Datasheet timing constants for the timing-aware rev-A tile chain model.
--
-- Every value is transcribed from
--   hardware/experiments/simple-tile/logic/timing/timing.json
-- which records the datasheet source + table + conditions per device
-- (all at 3.3 V +/- 0.3 V, CL = 50 pF unless noted). That JSON is the single
-- source of truth; results/check_timing_sync.py FAILS if this package drifts.
--
-- Rules (same as timing.json):
--   * null in the JSON (not specified by the source) is represented by a
--     KNOWN_* = false flag; the corner selector then uses a documented bound
--     (0.0 ns for a missing min = theoretically earliest, conservative for
--     the slack questions where a min could sit) and the report marks the
--     affected margins as carrying an UNSIGNED term. Nothing is invented.
--   * No typical values are used anywhere.
--   * The per-hop interconnect (testbench ROUTE_NS, default 1.5 ns) is a
--     SYNTHETIC assumption, not physical signoff and not datasheet data.

library ieee;
use ieee.std_logic_1164.all;

package chain_timing_pkg is

  -- ---------------------------------------------------------------- SN74LVC165A
  -- TI SCLSA16 (May 2024), tables 5.6/5.7, 3.3 V +/- 0.3 V, CL = 50 pF, -40..125 C
  constant LVC165A_TPD_CQ_MIN_NS   : real    := 1.0;   -- CLK -> QH
  constant LVC165A_TPD_CQ_MAX_NS   : real    := 14.5;
  constant LVC165A_TPD_LOAD_MAX_NS : real    := 19.9;  -- SH/LD -> QH (async load to out)
  constant LVC165A_TPD_LOAD_MIN_NS : real    := 0.0;   -- no datasheet min -> bound
  constant LVC165A_TSU_SER_NS      : real    := 4.0;   -- SER setup before CLK^
  constant LVC165A_TH_SER_NS       : real    := 0.5;   -- SER hold after CLK^
  constant LVC165A_TSU_SHLD_NS     : real    := 3.5;   -- SH/LD high (recovery) before CLK^
  constant LVC165A_TW_SHLD_NS      : real    := 4.3;   -- SH/LD low pulse
  constant LVC165A_TW_CLK_NS       : real    := 4.3;   -- CLK pulse

  -- ---------------------------------------------------------------- SN74LV161A
  -- TI SCLS404F, 3.3 V +/- 0.3 V, CL = 50 pF
  constant LV161A_TPD_CQ_MIN_NS  : real := 1.0;    -- CLK -> Q
  constant LV161A_TPD_CQ_MAX_NS  : real := 16.0;
  constant LV161A_TPD_RCO_MIN_NS : real := 1.0;    -- CLK -> RCO (count mode)
  constant LV161A_TPD_RCO_MAX_NS : real := 16.0;
  constant LV161A_TPHL_CLR_NS    : real := 19.5;   -- ~MR -> Q (async clear), max
  -- LV161A has no published ~MR recovery in timing.json -> leaf check disabled
  constant LV161A_TW_NS          : real := 5.0;    -- CLK pulse

  -- ---------------------------------------------------------------- SN74LVC2G08 (AND)
  -- TI SCES198N, 3.3 V +/- 0.3 V, CL = 50 pF, -40..125 C
  constant LVC2G08_TPD_MIN_NS : real := 1.0;
  constant LVC2G08_TPD_MAX_NS : real := 5.3;

  -- ---------------------------------------------------------------- SN74LVC2G32 (OR)
  -- TI SCES201N, 3.3 V +/- 0.3 V, CL = 50 pF, -40..125 C
  constant LVC2G32_TPD_MIN_NS : real := 1.0;
  constant LVC2G32_TPD_MAX_NS : real := 4.8;

  -- ---------------------------------------------------------------- SN74LVC2G125
  -- TI SCES204Q, 3.3 V +/- 0.3 V, CL = 50 pF, -40..125 C
  constant LVC2G125_TPD_MIN_NS  : real := 1.4;    -- A -> Y
  constant LVC2G125_TPD_MAX_NS  : real := 5.3;
  constant LVC2G125_TEN_MAX_NS  : real := 5.7;    -- ~OE -> Y enable (min: not in JSON)
  constant LVC2G125_TDIS_MAX_NS : real := 5.6;    -- ~OE -> Y release (min: not in JSON)

  -- ---------------------------------------------------------------- SN74LVC2G126
  -- TI SCES205N, 3.3 V +/- 0.3 V, CL = 50 pF, -40..125 C
  constant LVC2G126_TPD_MIN_NS  : real := 1.4;
  constant LVC2G126_TPD_MAX_NS  : real := 5.0;
  constant LVC2G126_TEN_MAX_NS  : real := 5.1;
  constant LVC2G126_TDIS_MAX_NS : real := 5.4;

  -- ---------------------------------------------------------------- SN74LVC1G04 (INV)
  -- TI SCES214AF, 3.3 V +/- 0.3 V, CL 30..50 pF column
  constant LVC1G04_TPD_MIN_NS : real := 0.7;
  constant LVC1G04_TPD_MAX_NS : real := 4.2;

  -- ---------------------------------------------------------------- SN74LVC2G74 (D-FF)
  -- TI SCES203Q, 3.3 V +/- 0.3 V, CL = 50 pF, -40..125 C
  constant LVC2G74_TPD_CQ_MIN_NS : real := 2.2;    -- CLK -> Q
  constant LVC2G74_TPD_CQ_MAX_NS : real := 6.9;
  constant LVC2G74_TSU_NS        : real := 1.9;    -- D setup before CLK^
  constant LVC2G74_TH_NS         : real := 0.5;    -- D hold after CLK^
  constant LVC2G74_TSU_CLR_NS    : real := 1.8;    -- ~CLR inactive (recovery) before CLK^
  constant LVC2G74_TW_CLK_NS     : real := 3.5;    -- CLK pulse
  -- CLR->Q propagation is not a timing.json cell; the leaf uses TPD_CQ as a
  -- labelled proxy (affects only when B_W clears during the 200 ns latch).

  -- corner selector: CORNER 0 = min (fast), 1 = max (slow)
  function pick_ns(minv : real; maxv : real; corner : natural) return time;

end package;

package body chain_timing_pkg is

  function pick_ns(minv : real; maxv : real; corner : natural) return time is
  begin
    if corner = 0 then
      return minv * 1 ns;
    else
      return maxv * 1 ns;
    end if;
  end function;

end package body;
