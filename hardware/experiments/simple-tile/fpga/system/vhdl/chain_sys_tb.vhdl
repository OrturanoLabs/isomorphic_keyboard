-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Timing-aware FPGA-chain system testbench (fpga/system).
--
-- W x H full grid of tile_sys (timed FPGA tiles wrapping the UNMODIFIED
-- golden core ../rtl/tile_fpga.vhdl, SNAP_MODE="fall" by default), a
-- synthetic per-hop route delay on every inter-tile net, and a controller
-- model with configurable latch guard/width, 20 MHz clock with configurable
-- high/low phases, and sample-lead timing.
--
-- Self-checks (all TIMING-FAIL:<TOKEN> greppable):
--   * stream bit-exact vs tile_reg_pkg golden frames (2 passes), incl. the
--     FIRST BIT sampled BEFORE the first shift clock (FIRSTBIT/STREAM);
--   * B_W flag of every column-bottom window-checked at edge+44 ns (col 1,
--     BW) and end-of-pass aggregate (BW-END);
--   * true-Z clock selection: T_clk/L_clk drive/Z windows per edge (MUXSEL);
--   * per-tile rising-edge counters on the RESOLVED local clock (dbg_clk =
--     what the FFs actually see, incl. float-up edges on a released net):
--     exact expected counts, spurious excess fails immediately
--     (SPURIOUS-CLK);
--   * W-switch hazards: T_clk may only RELEASE while its source clock is
--     high (RELEASE-HIGH); L_clk may only ENABLE while its source clock is
--     high (ENABLE-HIGH); WPHASE TMARKs classify every column switch as
--     mid-high / low phase exposure;
--   * per-tile latch falling edges counted per pass: exactly one
--     (LATCH-GLITCH) -- covers the latch-OR merge of both connector legs;
--   * resolution contention 'X' persistence on clock nets (CONTENTION);
--   * DS mux node driven level at every local rising edge (DS-VALID);
--   * returned-data settle margin at the controller sample point
--     (DATA-SETTLE) + TMARK arrival min/max;
--   * leaf-level budgets inside tile_sys: SNAP-XDOM (latch-fall capture /
--     shadow->shreg domain recovery), SNAP-WINDOW, CLK-PULSE.
--
-- Pass criterion: exit 0 AND "SYSPASS <NAME>" in the log ("SYSSUMMARY" has
-- the arrival/extremes). Negative harness configs must fail on one of the
-- assertion tokens, not on infrastructure.
--
-- This remains EXPLORATION under synthetic corners: no pad/interconnect
-- sign-off (cfg/corners.json).

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

use work.tile_reg_pkg.all;

entity chain_sys_tb is
  -- time generics in units of 0.1 ns (GHDL: integer generics only over CLI)
  generic (
    NAME            : string  := "unnamed";
    W               : natural := 1;    -- columns
    H               : natural := 4;    -- rows per column
    BMODE           : natural := 0;
    TAIL            : natural := 32;
    PASSES          : natural := 2;
    CORNER          : natural := 1;    -- 0 syn_min / 1 fit / 2 syn_max
    SCALE_PCT       : natural := 100;  -- synthetic stress on tile delays
    ROUTE_100PS     : natural := 15;   -- synthetic per-hop route delay
    TCLK_100PS      : natural := 500;  -- 20 MHz
    CLK_HIGH_100PS  : natural := 250;
    CLK_LOW_100PS   : natural := 250;
    LEAD_100PS      : natural := 50;   -- sample this BEFORE each rising edge
    GUARD_100PS     : natural := 250;  -- latch deassert -> first rising clock
    LWIDTH_100PS    : natural := 2000; -- controller latch pulse width
    SETTLE_100PS    : natural := 20;   -- returned-data settle requirement
    MUXCHK_100PS    : natural := 440   -- B_W/mux window check offset after
                                       -- each edge (44 ns; stress negatives
                                       -- relax it so the hazard monitors are
                                       -- the binding constraint)
  );
end entity;

architecture sim of chain_sys_tb is

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

  function rel_thru(c : natural) return natural is
    variable n : natural := 0;
  begin
    for j in 1 to c loop
      n := n + FRAME_BITS * (hc(j) - 1);
    end loop;
    return n;
  end function;

  -- expected rising-edge count at tile (c,r)'s local clock over all passes.
  -- Exact cascade math (validated against the discrete timing-chain): the
  -- bottom tile (c,1) receives every chain clock from when its column's
  -- clock source is established (rel_thru(c-1)) to the end of the pass;
  -- an upper tile (c, r>=2) sees exactly FRAME_BITS*(hc(c)-1) forwarded
  -- edges per pass -- enough to drain its own frames and stage the top
  -- frame into (c,1), after which the column switch cuts the forwarding.
  function exp_clk_loc(c : natural; r : natural) return natural is
  begin
    if r = 1 then
      return PASSES * (nbits - rel_thru(c - 1));
    elsif r <= hc(c) then
      return PASSES * FRAME_BITS * (hc(c) - 1);
    end if;
    return 0;
  end function;

  type t_net  is array (natural range <>, natural range <>) of std_logic;
  type t_nats is array (natural range <>, natural range <>) of natural;
  type t_times is array (natural range <>, natural range <>) of time;

  -- inter-tile nets (after the synthetic route delay)
  signal vW, vEC, vFirst, vLatch, vClk, vData : t_net(1 to W, 1 to H+1) :=
    (others => (others => 'Z'));
  signal hER, hLatch, hClk, hData : t_net(0 to W, 1 to H) :=
    (others => (others => 'Z'));

  -- raw tile output taps (before the route delay)
  signal dTclk, dTlatch, dBdata, dBW, dBendcol, dTfirst : t_net(1 to W, 1 to H) :=
    (others => (others => 'Z'));
  signal dLclk, dLlatch, dRdata, dRendrow : t_net(1 to W, 1 to H) :=
    (others => (others => 'Z'));

  -- observation taps (resolved post-pad nodes)
  signal dDbgClk, dDbgLatch, dDbgDs, dDbgW : t_net(1 to W, 1 to H) :=
    (others => (others => 'Z'));

  -- controller pins (latch starts asserted: power-on load state)
  signal clk, data : std_logic := '0';
  signal latch     : std_logic := '1';

  signal t0        : time := 0 ns;
  signal alldone   : boolean := false;
  signal ctrl_rise : time := 0 ns;

  signal got_sig      : std_logic_vector(0 to nbits-1) := (others => '0');
  signal cnt_clk      : t_nats(1 to W, 1 to H) := (others => (others => 0));
  signal cnt_lfall    : t_nats(1 to W, 1 to H) := (others => (others => 0));
  signal src_rise     : t_times(1 to W, 1 to H) := (others => (others => 0 ns));
  signal arr_max_ns   : real := 0.0;
  signal arr_min_ns   : real := 1.0e9;
  signal data_change  : time := 0 ns;

begin

  -- ---------------------------------------------------------------- grid
  tiles : for c in 1 to W generate
    rows : for r in 1 to H generate
      u_t : entity work.tile_sys
        generic map (
          CORNER => CORNER, SCALE_PCT => SCALE_PCT, SNAP => "fall",
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
          dbg_ds  => dDbgDs(c, r), dbg_w => dDbgW(c, r));
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
      wait for 500 ns;                 -- deep-column settle grace
      latch <= '1';
      wait for LWIDTH_100PS * 100 ps;
    end loop;
    alldone <= true;
    wait;
  end process;

  -- ------------------------------------------------------------- sampler
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
        assert now - data_change >= SETTLE_100PS * 100 ps
          report "TIMING-FAIL:DATA-SETTLE " & NAME & ": pass " & integer'image(p) &
                 " bit" & integer'image(e) & " returned data last changed " &
                 time'image(now - data_change) & " before sample (< " &
                 time'image(SETTLE_100PS * 100 ps) & ")"
          severity failure;
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

  datmon : process(data)
  begin
    data_change <= now;
  end process;

  -- ------------------------------------------------- B_W and mux windows
  checker : process
    variable tw    : time;
    variable du    : integer;
    variable bwexp : std_logic;
  begin
    for p in 1 to PASSES loop
      wait on t0;
      for e in 1 to nbits loop
        du := integer(GUARD_100PS) + (e - 1) * integer(TCLK_100PS) + integer(MUXCHK_100PS);
        tw := t0 + du * 100 ps;
        if tw > now then
          wait for tw - now;
        end if;
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

  -- ------------------- per-tile local-clock edges + latch-fall counters
  monl : for c in 1 to W generate
    monr : for r in 1 to H generate
      mon : process
        variable cnt  : natural := 0;
        variable lf   : natural := 0;
      begin
        wait on dDbgClk(c, r), dDbgLatch(c, r);
        if now > 0 ns and dDbgLatch(c, r)'event and to_x01(dDbgLatch(c, r)) = '0' then
          lf := lf + 1;
          cnt_lfall(c, r) <= lf;
          assert lf <= PASSES
            report "TIMING-FAIL:LATCH-GLITCH " & NAME & " tile(" &
                   integer'image(c) & "," & integer'image(r) & ") latch fall #" &
                   integer'image(lf) & " exceeds " & integer'image(PASSES) &
                   " (latch-OR net glitched) at " & time'image(now)
            severity failure;
        end if;
        if dDbgClk(c, r)'event and latch = '0' and to_x01(dDbgClk(c, r)) = '1' then
          cnt := cnt + 1;
          cnt_clk(c, r) <= cnt;
          assert cnt <= exp_clk_loc(c, r)
            report "TIMING-FAIL:SPURIOUS-CLK " & NAME & " tile(" & integer'image(c) &
                   "," & integer'image(r) & ") rising edge #" & integer'image(cnt) &
                   " exceeds expected " & integer'image(exp_clk_loc(c, r)) &
                   " at " & time'image(now)
            severity failure;
        end if;
      end process;
    end generate;
  end generate;

  -- net contention: a persistent 'X' = real driver fight
  monv : for c in 1 to W generate
    monr : for r in 1 to H+1 generate
      mon : process
      begin
        wait on vClk(c, r);
        if vClk(c, r) = 'X' then
          wait on vClk(c, r) for 100 ps;
          assert vClk(c, r) /= 'X'
            report "TIMING-FAIL:CONTENTION " & NAME & " vClk(" &
                   integer'image(c) & "," & integer'image(r) & ") net=X persists at " &
                   time'image(now)
            severity failure;
        end if;
      end process;
    end generate;
  end generate;

  monh : for c in 0 to W generate
    monr : for r in 1 to H generate
      mon : process
      begin
        wait on hClk(c, r);
        if hClk(c, r) = 'X' then
          wait on hClk(c, r) for 100 ps;
          assert hClk(c, r) /= 'X'
            report "TIMING-FAIL:CONTENTION " & NAME & " hClk(" &
                   integer'image(c) & "," & integer'image(r) & ") net=X persists at " &
                   time'image(now)
            severity failure;
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
                     " T_clk release landed after the source clock fell, at " &
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

  -- L_clk of tile (c, 1) may enable only while its source clock is high.
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

  -- WPHASE: classify each bottom tile's W switch by its local clock phase
  wmon : for c in 1 to W generate
    mon : process
      variable dt : real;
    begin
      wait on dDbgW(c, 1);
      if latch = '0' and to_x01(dDbgW(c, 1)) = '1' then
        dt := real((now - src_rise(c, 1)) / 1 ns);
        report "TMARK WPHASE col" & integer'image(c) &
               " w_at=" & time'image(now) &
               " since_src_rise_ns=" & integer'image(integer(dt)) &
               " phase=" & std_logic'image(dDbgClk(c, 1));
        assert dDbgClk(c, 1) = '1' or dDbgClk(c, 1) = 'H'
          report "TIMING-FAIL:W-LOWPHASE " & NAME & " col" & integer'image(c) &
                 " bottom W switched while its local clock is LOW at " &
                 time'image(now) & " -- L_clk enable/T_clk release will land " &
                 "in the low phase"
          severity failure;
      end if;
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
            prev := dDbgClk(c, r);
          elsif dDbgClk(c, r)'event then
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
      for r in 1 to H loop
        assert cnt_clk(c, r) = exp_clk_loc(c, r)
          report "TIMING-FAIL:SPURIOUS-CLK " & NAME & " tile(" & integer'image(c) &
                 "," & integer'image(r) & ") local clock total " &
                 integer'image(cnt_clk(c, r)) & " expected " &
                 integer'image(exp_clk_loc(c, r))
          severity failure;
        assert cnt_lfall(c, r) = PASSES
          report "TIMING-FAIL:LATCH-GLITCH " & NAME & " tile(" & integer'image(c) &
                 "," & integer'image(r) & ") latch falls total " &
                 integer'image(cnt_lfall(c, r)) & " expected " & integer'image(PASSES)
          severity failure;
      end loop;
    end loop;

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

    report "SYSSUMMARY " & NAME &
           " arrival_min_ns=" & integer'image(integer(arr_min_ns)) &
           " arrival_max_ns=" & integer'image(integer(arr_max_ns));
    report "SYSPASS " & NAME & " frames=" & integer'image(nfr) &
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
  assert CORNER <= 2
    report "CONFIG ERROR: CORNER out of range" severity failure;

end architecture;
