-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Timing-aware chain testbench for the rev-A tile scan.
--
-- Instantiates a W x H full grid of tile_timed (the timed rev-A chip-level
-- model) wired exactly like the zero-delay regression testbench, but with
--   * a synthetic per-hop route delay (ROUTE_NS, transport, on every net tap
--     including flag/latch/presence nets),
--   * a controller model with configurable LATCH_GUARD_NS (latch deassert ->
--     first rising clock), 50 % duty 20 MHz clock, and SAMPLE_LEAD_NS (sample
--     BOARD_DATA this many ns BEFORE each rising edge),
--   * self-checks herself output bit-exact against tile_reg_pkg golden frames
--     (2 passes), plus timing-specific checks:
--       - first bit valid before the first shift clock
--       - B_W flag of every column bottom, checked at edge + 30 ns
--       - T_clk/L_clk drive/Z windows at edge + 30 ns
--       - spurious rising-edge counters on EVERY clock net (expected counts
--         derived from the traversal functions; excess fails immediately,
--         missing fails at the end)
--       - W-transition hazards: T_clk may only RELEASE while its source clock
--         is high; L_clk may only ENABLE while its source clock is high
--       - DS mux node must be a driven level at every sampled clock edge
--       - resolution-contention 'X' monitors on all clock/data nets
--   * instrumentation: TMARK lines (actual local edge times at probe tiles,
--     latch forward arrival times, controller data arrival min/max, release /
--     enable margins) and a final TCREGSUMMARY line.
--
-- Pass criterion: exit 0 AND "TCREGPASS <NAME>" in the log. Failures carry
-- greppable TIMING-FAIL:<TOKEN> markers. This TB cannot false-pass by
-- compilation error or by hitting the stop-time: without TCREGPASS the
-- harness fails the run.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

use work.tile_reg_pkg.all;

entity chain_tb is
  -- time generics are in units of 0.1 ns because GHDL cannot override real or
  -- time generics from the command line (integer only, with string/boolean).
  generic (
    NAME            : string  := "unnamed";
    W               : natural := 1;    -- columns (the "N" of the sweep)
    H               : natural := 4;    -- rows per column (4x4-key tiles)
    BMODE           : natural := 0;
    TAIL            : natural := 32;
    PASSES          : natural := 2;
    CORNER_CLK      : natural := 1;    -- 0 min / 1 max (datasheet corners)
    CORNER_LATCH    : natural := 1;
    CORNER_DATA     : natural := 1;
    SCALE_CLK_PCT   : natural := 100;  -- synthetic stress multipliers, percent
    SCALE_LATCH_PCT : natural := 100;
    SCALE_DATA_PCT  : natural := 100;
    ROUTE_100PS     : natural := 15;   -- synthetic per-hop route delay (1.5 ns)
    TCLK_100PS      : natural := 500;  -- 20 MHz
    CLK_HIGH_100PS  : natural := 250;  -- controller clock high phase
    CLK_LOW_100PS   : natural := 250;  -- controller clock low phase
    LEAD_100PS      : natural := 50;   -- sample this long BEFORE each rising edge
    GUARD_100PS     : natural := 250;  -- latch deassert -> first rising clock
    LWIDTH_100PS    : natural := 2000  -- controller latch pulse width
  );
end entity;

architecture sim of chain_tb is

  constant pmap  : t_map(0 to W*H-1) := parse_present((1 to W*H => '1'), W, H);
  constant nfr   : natural := reachable_frames(pmap, W, H);
  constant nbits : natural := nfr*FRAME_BITS + TAIL;
  constant exp   : std_logic_vector(0 to nbits-1) :=
                     expected_stream(pmap, W, H, BMODE, nbits);

  constant ROUTE : time := ROUTE_100PS * 100 ps;

  function hc(c : natural) return natural is
  begin
    return contig_height(pmap, W, H, c);
  end function;

  -- global 0-indexed edge count at which column c switches (its bottom tile
  -- releases T_clk / enables L_clk): edges of column c that travel upward
  -- = 16*(hc(c)-1); cumulative over columns 1..c
  function rel_thru(c : natural) return natural is
    variable n : natural := 0;
  begin
    for j in 1 to c loop
      n := n + FRAME_BITS * (hc(j) - 1);
    end loop;
    return n;
  end function;

  -- expected rising-edge counts (all PASSES passes summed) per clock net
  function exp_vclk(c : natural; r : natural) return natural is
  begin
    if r >= 2 then
      return PASSES * FRAME_BITS * (hc(c) - 1);
    end if;
    return 0;
  end function;

  function exp_hclk(c : natural; r : natural) return natural is
  begin
    if r /= 1 then
      return 0;
    end if;
    if c = 0 then
      return PASSES * nbits;
    end if;
    return PASSES * (nbits - rel_thru(c));
  end function;

  type t_net  is array (natural range <>, natural range <>) of std_logic;
  type t_nats is array (natural range <>, natural range <>) of natural;
  type t_times is array (natural range <>, natural range <>) of time;

  -- inter-tile nets (after the route delay), indices like tile_grid_tb
  signal vW, vEC, vFirst, vLatch, vClk, vData : t_net(1 to W, 1 to H+1) :=
    (others => (others => 'Z'));
  signal hER, hLatch, hClk, hData : t_net(0 to W, 1 to H) :=
    (others => (others => 'Z'));

  -- raw tile output taps (before the route delay)
  signal dTclk, dTlatch, dBdata, dBW, dBendcol, dTfirst : t_net(1 to W, 1 to H) :=
    (others => (others => 'Z'));
  signal dLclk, dLlatch, dRdata, dRendrow : t_net(1 to W, 1 to H) :=
    (others => (others => 'Z'));

  -- observation taps
  signal dDbgClk, dDbgLatch, dDbgDs : t_net(1 to W, 1 to H) :=
    (others => (others => 'Z'));

  -- controller pins (latch starts asserted: power-on load state)
  signal clk, data : std_logic := '0';
  signal latch     : std_logic := '1';

  -- pass synchronisation
  signal t0        : time := 0 ns;    -- latch deassert time of the current pass
  signal alldone   : boolean := false;
  signal ctrl_rise : time := 0 ns;    -- last launch rising edge at the controller

  -- instrumentation
  signal got_sig  : std_logic_vector(0 to nbits-1) := (others => '0');
  signal cnt_vclk : t_nats(1 to W, 1 to H+1) := (others => (others => 0));
  signal cnt_hclk : t_nats(0 to W, 1 to H)   := (others => (others => 0));
  signal src_rise : t_times(1 to W, 1 to H)  := (others => (others => 0 ns));
  signal arr_max_ns : real := 0.0;
  signal arr_min_ns : real := 1.0e9;

begin

  -- ---------------------------------------------------------------- grid
  tiles : for c in 1 to W generate
    rows : for r in 1 to H generate
      u_t : entity work.tile_timed
        generic map (
          CORNER_CLK => CORNER_CLK, CORNER_LATCH => CORNER_LATCH,
          CORNER_DATA => CORNER_DATA,
          SCALE_CLK_PCT => SCALE_CLK_PCT, SCALE_LATCH_PCT => SCALE_LATCH_PCT,
          SCALE_DATA_PCT => SCALE_DATA_PCT,
          LOC => "t" & integer'image(c) & "," & integer'image(r))
        port map (
          buttons  => buttons_for(BMODE, c, r),
          T_W      => vW(c, r+1),    T_endcol => vEC(c, r+1),
          T_first  => dTfirst(c, r), T_latch  => dTlatch(c, r),
          T_clk    => dTclk(c, r),   T_data   => vData(c, r+1),
          B_W      => dBW(c, r),     B_endcol => dBendcol(c, r),
          B_first  => vFirst(c, r),  B_latch  => vLatch(c, r),
          B_clk    => vClk(c, r),    B_data   => vData(c, r),
          L_endrow => hER(c, r),     L_latch  => dLlatch(c, r),
          L_clk    => dLclk(c, r),   L_data   => hData(c, r),
          R_endrow => dRendrow(c, r), R_latch => hLatch(c-1, r),
          R_clk    => hClk(c-1, r),  R_data   => dRdata(c, r),
          dbg_clk => dDbgClk(c, r), dbg_latch => dDbgLatch(c, r),
          dbg_ds  => dDbgDs(c, r));
    end generate;
  end generate;

  -- synthetic per-hop route delays on every net tap
  routes_v : for c in 1 to W generate
    rts : for r in 1 to H generate
      vClk(c, r+1)   <= transport dTclk(c, r)    after ROUTE;
      vLatch(c, r+1) <= transport dTlatch(c, r)  after ROUTE;
      vData(c, r)    <= transport dBdata(c, r)   after ROUTE;
      vW(c, r)       <= transport dBW(c, r)      after ROUTE;
      vEC(c, r)      <= transport dBendcol(c, r) after ROUTE;
      vFirst(c, r+1) <= transport dTfirst(c, r)  after ROUTE;
      hClk(c, r)     <= transport dLclk(c, r)    after ROUTE;
      hLatch(c, r)   <= transport dLlatch(c, r)  after ROUTE;
      hData(c-1, r)  <= transport dRdata(c, r)   after ROUTE;
      hER(c-1, r)    <= transport dRendrow(c, r) after ROUTE;
    end generate;
  end generate;

  -- controller taps (same synthetic route on the cable)
  hClk(0, 1)   <= transport clk   after ROUTE;
  hLatch(0, 1) <= transport latch after ROUTE;
  data         <= transport hData(0, 1) after ROUTE;

  -- ------------------------------------------------------------- driver
  driver : process
  begin
    wait for LWIDTH_100PS * 100 ps;    -- initial latch-high (power-on settle)
    for p in 1 to PASSES loop
      latch <= '0';
      t0 <= now;
      wait for GUARD_100PS * 100 ps;
      for e in 1 to nbits loop
        clk <= '1';
        ctrl_rise <= now;
        wait for CLK_HIGH_100PS * 100 ps;
        clk <= '0';
        wait for CLK_LOW_100PS * 100 ps;
      end loop;
      -- grace with clock idle + latch low so the deep-column flags can settle
      -- before the end-of-pass check at last-rise + 350 ns
      wait for 500 ns;
      latch <= '1';                    -- monitors gate on the latch LEVEL
      wait for LWIDTH_100PS * 100 ps;
    end loop;
    alldone <= true;
    wait;
  end process;

  -- ------------------------------------------------------------- sampler
  -- bit e sampled SAMPLE_LEAD_NS before rising edge e+1 (sample-before-clock)
  sampler : process
    variable tw  : time;
    variable du  : integer;
    variable bit : std_logic;
  begin
    for p in 1 to PASSES loop
      wait on t0;
      for e in 0 to nbits-1 loop
        du := integer(GUARD_100PS) + e * integer(TCLK_100PS) - integer(LEAD_100PS);
        tw := t0 + du * 100 ps;
        if tw > now then
          wait for tw - now;
        end if;
        bit := to_x01(data);
        assert data = '0' or data = '1' or data = 'L' or data = 'H'
          report "TIMING-FAIL:SAMPLE-WINDOW " & NAME & ": pass " & integer'image(p) &
                 " bit" & integer'image(e) & " level " & std_logic'image(data)
          severity failure;
        if p = 1 then
          got_sig(e) <= bit;
        end if;
        if e = 0 then
          assert bit = exp(0)
            report "TIMING-FAIL:FIRSTBIT " & NAME & ": pass " & integer'image(p) &
                   " first bit got " & std_logic'image(bit) & " expected " &
                   std_logic'image(exp(0))
            severity failure;
        else
          assert bit = exp(e)
            report "TIMING-FAIL:STREAM " & NAME & ": pass " & integer'image(p) &
                   " bit" & integer'image(e) & " (frame" & integer'image(e/FRAME_BITS) &
                   ") got " & std_logic'image(bit) & " expected " & std_logic'image(exp(e))
            severity failure;
        end if;
      end loop;
    end loop;
    wait;
  end process;

  -- ------------------------------------------------- B_W and mux windows
  -- Checked at edge + 44 ns. Only column 1 is window-checked bit-by-bit:
  -- deeper columns' local clocks lag the controller by per-hop forward
  -- delays (that is exactly what is being modelled), so a controller-frame
  -- window there would false-fire; they are covered instead by the stream
  -- itself, the per-net edge counts, the hazard monitors and the end-of-pass
  -- aggregate flag check below.
  checker : process
    variable tw    : time;
    variable du    : integer;
    variable bwexp : std_logic;
  begin
    for p in 1 to PASSES loop
      wait on t0;
      for e in 1 to nbits loop
        du := integer(GUARD_100PS) + (e - 1) * integer(TCLK_100PS) + 440;
        tw := t0 + du * 100 ps;
        if tw > now then
          wait for tw - now;
        end if;
        -- B_W of column-1 bottom
        if e >= bw_set_edge(pmap, W, H, 1) then
          bwexp := '1';
        else
          bwexp := '0';
        end if;
        assert to_x01(vW(1, 1)) = bwexp
          report "TIMING-FAIL:BW " & NAME & ": pass " & integer'image(p) &
                 " edge" & integer'image(e) & " col1 got " &
                 std_logic'image(vW(1, 1)) & " expected " & std_logic'image(bwexp)
          severity failure;
        -- T_clk of the controller tile: driven iff e < rel_thru(1)
        if hc(1) >= 2 then
          if e < rel_thru(1) then
            assert vClk(1, 2) = '0'
              report "TIMING-FAIL:MUXSEL " & NAME & ": pass " & integer'image(p) &
                     " edge" & integer'image(e) & " T_clk col1 should forward, is " &
                     std_logic'image(vClk(1, 2))
              severity failure;
          else
            assert vClk(1, 2) = 'Z'
              report "TIMING-FAIL:MUXSEL " & NAME & ": pass " & integer'image(p) &
                     " edge" & integer'image(e) & " T_clk col1 should be released, is " &
                     std_logic'image(vClk(1, 2))
              severity failure;
          end if;
        end if;
        if W >= 2 then
          if e >= rel_thru(1) then
            assert hClk(1, 1) = '0'
              report "TIMING-FAIL:MUXSEL " & NAME & ": pass " & integer'image(p) &
                     " edge" & integer'image(e) & " L_clk col1 should forward, is " &
                     std_logic'image(hClk(1, 1))
              severity failure;
          else
            assert hClk(1, 1) = 'Z'
              report "TIMING-FAIL:MUXSEL " & NAME & ": pass " & integer'image(p) &
                     " edge" & integer'image(e) & " L_clk col1 should not be driven, is " &
                     std_logic'image(hClk(1, 1))
              severity failure;
          end if;
        end if;
      end loop;
      -- end-of-pass aggregate: every traversed column's bottom flag must be
      -- set well after the last edge (skew-tolerant: deep local clocks lag)
      du := integer(GUARD_100PS) + integer(nbits - 1) * integer(TCLK_100PS) + 3500;
      tw := t0 + du * 100 ps;
      wait for tw - now;
      for c in 1 to W loop
        assert to_x01(vW(c, 1)) = '1'
          report "TIMING-FAIL:BW-END " & NAME & ": pass " & integer'image(p) &
                 " bottom flag of col" & integer'image(c) & " not set at pass end, is " &
                 std_logic'image(vW(c, 1))
          severity failure;
      end loop;
    end loop;
    wait;
  end process;

  -- --------------------------------------- clock-net edge counters + 'X'
  monv : for c in 1 to W generate
    monr : for r in 1 to H+1 generate
      mon : process
        variable prev : std_logic := 'Z';
        variable cnt  : natural := 0;
      begin
        wait on vClk(c, r);
        if vClk(c, r) = 'X' then
          -- a real driver fight (0 vs 1) persists; a delta-wide transient at
          -- power-on does not (it is overwritten in the same timestep and is
          -- never a clock edge for any receiver). Require persistence.
          wait on vClk(c, r) for 100 ps;
          assert vClk(c, r) /= 'X'
            report "TIMING-FAIL:CONTENTION " & NAME & " vClk(" &
                   integer'image(c) & "," & integer'image(r) & ") net=X persists at " &
                   time'image(now) & " prev=" & std_logic'image(prev) &
                   " tap=" & std_logic'image(dTclk(c, r-1)) &
                   " src_clk=" & std_logic'image(dDbgClk(c, r-1))
            severity failure;
          prev := vClk(c, r);
        elsif latch = '0' and to_x01(prev) = '0' and to_x01(vClk(c, r)) = '1' then
          cnt := cnt + 1;
          cnt_vclk(c, r) <= cnt;
          assert cnt <= exp_vclk(c, r)
            report "TIMING-FAIL:SPURIOUS-CLK " & NAME & " vClk(" & integer'image(c) &
                   "," & integer'image(r) & ") rising edge #" & integer'image(cnt) &
                   " exceeds expected " & integer'image(exp_vclk(c, r)) &
                   " at " & time'image(now)
            severity failure;
          prev := vClk(c, r);
        else
          prev := vClk(c, r);
        end if;
      end process;
    end generate;
  end generate;

  monh : for c in 0 to W generate
    monr : for r in 1 to H generate
      mon : process
        variable prev : std_logic := 'Z';
        variable cnt  : natural := 0;
      begin
        wait on hClk(c, r);
        if hClk(c, r) = 'X' then
          wait on hClk(c, r) for 100 ps;
          assert hClk(c, r) /= 'X'
            report "TIMING-FAIL:CONTENTION " & NAME & " hClk(" &
                   integer'image(c) & "," & integer'image(r) & ") net=X persists at " &
                   time'image(now) & " prev=" & std_logic'image(prev) &
                   " tap=" & std_logic'image(dLclk(c, r)) &
                   " src_clk=" & std_logic'image(dDbgClk(c, r))
            severity failure;
          prev := hClk(c, r);
        elsif latch = '0' and to_x01(prev) = '0' and to_x01(hClk(c, r)) = '1' then
          cnt := cnt + 1;
          cnt_hclk(c, r) <= cnt;
          assert cnt <= exp_hclk(c, r)
            report "TIMING-FAIL:SPURIOUS-CLK " & NAME & " hClk(" & integer'image(c) &
                   "," & integer'image(r) & ") rising edge #" & integer'image(cnt) &
                   " exceeds expected " & integer'image(exp_hclk(c, r)) &
                   " at " & time'image(now)
            severity failure;
          prev := hClk(c, r);
        else
          prev := hClk(c, r);
        end if;
      end process;
    end generate;
  end generate;

  -- --------------------------------- W-switch high-phase hazard monitors
  -- T_clk of tile (c, r-1) may go 'Z' only while its source clock is high.
  relmon : for c in 1 to W generate
    relr : for r in 2 to H+1 generate
      mon : process
        variable prev   : std_logic := 'Z';
        variable min_dt : real := 1.0e9;
        variable dt     : real;
      begin
        wait on vClk(c, r);
        if latch = '0' and vClk(c, r) = 'Z' and
           (prev = '0' or prev = '1') then
          if prev = '0' then
            assert false
              report "TIMING-FAIL:RELEASE-HIGH " & NAME & " col" & integer'image(c) &
                     " T_clk released while clock LOW at " & time'image(now) &
                     " (receiver pull-up will float a spurious rising edge)"
              severity failure;
          else
            assert dDbgClk(c, r-1) = '1' or dDbgClk(c, r-1) = 'H'
              report "TIMING-FAIL:RELEASE-HIGH " & NAME & " col" & integer'image(c) &
                     " T_clk release net landed after the source clock fell, at " &
                     time'image(now)
              severity failure;
            dt := real((now - src_rise(c, r-1)) / 1 ns);
            if dt < min_dt then
              min_dt := dt;
              report "TMARK RELEASE col" & integer'image(c) & " row" & integer'image(r) &
                     " release_at=" & time'image(now) & " since_src_rise_ns=" &
                     integer'image(integer(dt));
            end if;
          end if;
        end if;
        prev := vClk(c, r);
      end process;
    end generate;
  end generate;

  -- L_clk of tile (c, 1) may enable only while its source clock is high --
  -- an enable that lands in the low phase means W switched too late and the
  -- forwarded pulse train would be clipped.
  enmon : for c in 1 to W generate
    mon : process
      variable prev   : std_logic := 'Z';
      variable min_dt : real := 1.0e9;
      variable dt     : real;
    begin
      wait on hClk(c, 1);
      if latch = '0' and prev = 'Z' and
         (hClk(c, 1) = '0' or hClk(c, 1) = '1') then
        assert dDbgClk(c, 1) = '1' or dDbgClk(c, 1) = 'H'
          report "TIMING-FAIL:ENABLE-HIGH " & NAME & " col" & integer'image(c) &
                 " L_clk enable landed after the source clock fell, at " & time'image(now)
          severity failure;
        dt := real((now - src_rise(c, 1)) / 1 ns);
        if dt < min_dt then
          min_dt := dt;
          report "TMARK ENABLE col" & integer'image(c) & " enable_at=" & time'image(now) &
                 " since_src_rise_ns=" & integer'image(integer(dt));
        end if;
      end if;
      prev := hClk(c, 1);
    end process;
  end generate;

  srcv : for c in 1 to W generate
    srcr : for r in 1 to H generate
      srct : process
      begin
        wait on dDbgClk(c, r);
        if to_x01(dDbgClk(c, r)) = '1' then
          src_rise(c, r) <= now;
        end if;
      end process;
    end generate;
  end generate;

  -- ------------------------------------- DS valid at every sampled edge
  dsmon : for c in 1 to W generate
    dsr : for r in 1 to H generate
      mon : process
      begin
        wait on dDbgClk(c, r);
        if latch = '0' and to_x01(dDbgClk(c, r)) = '1' then
          assert dDbgDs(c, r) = '0' or dDbgDs(c, r) = '1'
            report "TIMING-FAIL:DS-VALID " & NAME & " tile(" & integer'image(c) &
                   "," & integer'image(r) & ") DS mux level " &
                   std_logic'image(dDbgDs(c, r)) & " at clock rising edge, " &
                   time'image(now)
            severity failure;
        end if;
      end process;
    end generate;
  end generate;

  -- ------------------------------------- local edge actual times (drift)
  -- At the corner tiles ((1,1),(1,H),(W,1),(W,H)) log each pass's first edge,
  -- the column-switch edge and (bottom tile) the column's last own edge, as
  -- lateness vs the controller launch of the same chain edge.
  edgemon : for c in 1 to W generate
    edger : for r in 1 to H generate
      probe : if ((c = 1 or c = W or c = 2 or c = 3 or c = W / 2 or c = W - 1) and
                  (r = 1 or r = H)) generate
        mon : process(dDbgClk(c, r), latch)
          variable k    : natural := 0;
          variable ge, late : integer;
          variable prev : std_logic := 'Z';
        begin
          if latch = '1' then
            k := 0;
            prev := dDbgClk(c, r);   -- keep tracking the idle level
          elsif dDbgClk(c, r)'event then
            -- count only true logical rises (a floatup/strength transition
            -- 'H'->'1' at an enable is not an edge, matching the receivers)
            if to_x01(prev) = '0' and to_x01(dDbgClk(c, r)) = '1' then
              k := k + 1;
              ge := integer(GUARD_100PS) + (rel_thru(c - 1) + k - 1) * integer(TCLK_100PS);
              late := integer((now - (t0 + ge * 100 ps)) / 100 ps);
              if k = 1 or k = FRAME_BITS * (hc(c) - 1) or
                 (r = 1 and k = FRAME_BITS * hc(c)) then
                report "TMARK EDGE t(" & integer'image(c) & "," & integer'image(r) &
                       ") chain_edge#" & integer'image(rel_thru(c - 1) + k) &
                       " local#" & integer'image(k) & " lateness_x01ns=" &
                       integer'image(late / 10) & "." & integer'image(late mod 10);
              end if;
            end if;
            prev := dDbgClk(c, r);
          end if;
        end process;
      end generate;
    end generate;
  end generate;

  -- -------------------------------------------------- controller arrival
  arrmon : process
    variable dt : real;
  begin
    wait on data;
    if latch = '0' and now > 0 ns then
      -- dat returned to the controller pin, timed from the controller's own
      -- LAUNCH rising edge (cable out happens before the tiles see it)
      dt := real((now - ctrl_rise) / 1 ns);
      if dt >= 0.0 and dt < arr_min_ns then
        arr_min_ns <= dt;
        report "TMARK ARRIVAL-MIN dt_ns=" & integer'image(integer(dt));
      end if;
      if dt > arr_max_ns then
        arr_max_ns <= dt;
        report "TMARK ARRIVAL-MAX dt_ns=" & integer'image(integer(dt));
      end if;
    end if;
  end process;

  -- --------------------------------------------- latch-forward arrivals
  latchmon : for c in 1 to W generate
    latchr : for r in 1 to H generate
      mon : if (r = 1 or r = H) and (c = 1 or c = W) generate
        proc : process
        begin
          wait on dDbgLatch(c, r);
          report "TMARK LATCH tile(" & integer'image(c) & "," & integer'image(r) &
                 ") latch=" & std_logic'image(dDbgLatch(c, r)) &
                 " at " & time'image(now);
        end process;
      end generate;
    end generate;
  end generate;

  -- ----------------------------------------------------- endpoint checks
  finisher : process
    variable frame : std_logic_vector(15 downto 0);
  begin
    wait until alldone;
    for c in 1 to W loop
      for r in 1 to H+1 loop
        assert cnt_vclk(c, r) = exp_vclk(c, r)
          report "TIMING-FAIL:SPURIOUS-CLK " & NAME & " vClk(" & integer'image(c) &
                 "," & integer'image(r) & ") total " & integer'image(cnt_vclk(c, r)) &
                 " expected " & integer'image(exp_vclk(c, r))
          severity failure;
      end loop;
    end loop;
    for c in 0 to W loop
      for r in 1 to H loop
        assert cnt_hclk(c, r) = exp_hclk(c, r)
          report "TIMING-FAIL:SPURIOUS-CLK " & NAME & " hClk(" & integer'image(c) &
                 "," & integer'image(r) & ") total " & integer'image(cnt_hclk(c, r)) &
                 " expected " & integer'image(exp_hclk(c, r))
          severity failure;
      end loop;
    end loop;

    -- per-frame decode: markers + flags on pass-1 bits
    for f in 0 to nfr-1 loop
      for i in 0 to FRAME_BITS-1 loop
        frame(FRAME_BITS-1 - i) := got_sig(f*FRAME_BITS + i);
      end loop;
      assert frame(3 downto 2) = "11"
        report "TIMING-FAIL:STREAM " & NAME & ": frame" & integer'image(f) &
               " markers " & to_hstring(frame(3 downto 2))
        severity failure;
      report NAME & " frame" & integer'image(f) & " word=" & to_hstring(frame) &
             " endrow=" & std_logic'image(frame(1)) & " endcol=" & std_logic'image(frame(0));
    end loop;

    report "TCREGSUMMARY " & NAME &
           " arrival_min_ns=" & integer'image(integer(arr_min_ns)) &
           " arrival_max_ns=" & integer'image(integer(arr_max_ns));
    report "TCREGPASS " & NAME & " frames=" & integer'image(nfr) &
           " bits=" & integer'image(nbits) & " passes=" & integer'image(PASSES);
    finish;
    wait;
  end process;

  -- sanity of the controller generics themselves
  assert LEAD_100PS > 0 and LEAD_100PS < TCLK_100PS
    report "CONFIG ERROR: sample lead out of range" severity failure;
  assert CLK_HIGH_100PS + CLK_LOW_100PS = TCLK_100PS
    report "CONFIG ERROR: CLK_HIGH + CLK_LOW must equal the 50 ns period"
    severity failure;

end architecture;
