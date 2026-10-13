-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- track_cdc_tb: SNAP_MODE="track" additional-clock-domain characterisation.
--
-- A tile_sys leaf (SNAP => "track") with a free-running synthetic sysclk
-- (TSYS_100PS; 10 ns default - 100 MHz EXPLORATION clock: the real OSCZ base
-- frequency is still unverified per the DS861 gate; see fpga/docs/
-- clock_domains.md "T2"). A key change is swept across offsets
-- OSET = fall - change of 0.5 ns .. 2*TSYS in 0.5 ns steps. The fall phase
-- relative to the sysclk grid varies naturally between steps (the loop
-- period is not an integer multiple of TSYS), which is intended: the
-- guaranteed side of the contract must hold for ANY phase.
--
-- Contract under test (docs/clock_domains.md, the fpga workstream's T1):
--   OSET >= TSYS        : the change MUST be captured (at least one full
--                         sysclk sample inside the window) - asserted, failure
--                         token TIMING-FAIL:TRACK-CONTRACT.
--   0 < OSET < TSYS     : dead zone; stale-or-captured is phase dependent.
--                         Characterised (TMARK TRACK lines + tally), NOT
--                         asserted - the documented approximation window,
--                         extending sim S8 with pad timing.
-- Negative scenario (SCEN=1): latch high window < TSYS (violates T1): no
--   sysclk sample lands while latch is high -> frame = stale initial content
--   != fresh keys -> the stream check must fail: TIMING-FAIL:STREAM.
--
-- Marker "SYSPASS <NAME>" at the end of the positive contract run.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
use work.system_timing_pkg.all;

entity track_cdc_tb is
  generic (
    NAME        : string  := "track_cdc";
    SCEN        : natural := 0;      -- 0 contract sweep / 1 negative: short latch
    TSYS_100PS  : natural := 100;    -- 10 ns synthetic sysclk
    CORNER      : natural := 1;
    SCALE_PCT   : natural := 100
  );
end entity;

architecture sim of track_cdc_tb is

  constant TSYS    : time := TSYS_100PS * 100 ps;
  constant K1      : std_logic_vector(11 downto 0) := x"A5A";
  constant K2      : std_logic_vector(11 downto 0) := x"3C3";
  constant NSTEPS  : natural := 4 * TSYS_100PS / 10;   -- 0.5 ns steps over 2*TSYS

  -- wire order: keys(11) first on the wire
  function wire_order(v : std_logic_vector(11 downto 0))
    return std_logic_vector is
    variable r : std_logic_vector(0 to 11);
  begin
    for j in 0 to 11 loop
      r(j) := v(11 - j);
    end loop;
    return r;
  end function;

  signal sysclk    : std_logic := '0';
  signal keys      : std_logic_vector(11 downto 0) := K1;
  signal latchsrc  : std_logic := 'Z';
  signal clk       : std_logic := '0';  -- driven-low idle (see latch_or_tb)
  signal dout      : std_logic;
  signal n_stale   : natural := 0;
  signal n_capt    : natural := 0;

begin

  sysclk <= not sysclk after TSYS / 2;

  dut : entity work.tile_sys
    generic map (CORNER => CORNER, SCALE_PCT => SCALE_PCT, SNAP => "track",
                 LOC => "u")
    port map (
      buttons => keys, sysclk => sysclk,
      T_W => 'Z', T_endcol => 'Z', T_first => open, T_latch => open,
      T_clk => open, T_data => 'Z',
      B_W => open, B_endcol => open, B_first => 'Z',
      B_latch => latchsrc, B_clk => clk, B_data => dout,
      L_endrow => 'Z', L_latch => open, L_clk => open, L_data => 'Z',
      R_endrow => open, R_latch => 'Z', R_clk => 'Z', R_data => open,
      dbg_clk => open, dbg_latch => open, dbg_ds => open, dbg_w => open);

  stim : process
    variable oset        : time;
    variable captured    : boolean;
    variable got         : std_logic_vector(0 to 11);
  begin

    if SCEN = 1 then
      ------------------------------------------------- negative: short latch
      keys <= K1;
      latchsrc <= '1';
      wait for TSYS / 5;               -- 2 ns: the local fall (pad-delayed)
                                       -- lands before the first sysclk rise:
                                       -- zero shadow samples (T1 violated)
      latchsrc <= '0';
      wait for 60 ns;
      for j in 0 to 11 loop
        if j = 0 then
          got(0) := to_x01(dout);      -- first bit before first clock
        else
          clk <= '1'; wait for 25 ns; clk <= '0'; wait for 20 ns;
          got(j) := to_x01(dout);
        end if;
      end loop;
      assert got = wire_order(K1)
        report "TIMING-FAIL:STREAM " & NAME &
               ": short-latch track frame key bits got " & to_hstring(got) &
               " (stale != fresh: this negative run must fail here)"
        severity failure;
      report "SYSPASS " & NAME & " scen=1";
      finish;
      wait;
    end if;

    ------------------------------------------------------- contract sweep
    -- PSH shifts every fall OFF the sysclk rise grid (oset is in 0.5 ns
    -- steps; fall lands at (oset + 0.33) mod TSYS, never == a rise instant),
    -- so no step is an ambiguous exactly-at-a-sample race. The contract
    -- threshold below uses the ACTUAL offset (oset + PSH).
    for step in 1 to NSTEPS loop
      oset := step * 500 ps;
      keys <= K1;
      latchsrc <= '1';
      wait for 8 * TSYS;               -- latch high: >= 1 full sysclk sample
      keys <= K2;
      wait for oset + 330 ps;          -- change sits OSET+PSH before the fall
      latchsrc <= '0';
      wait for 60 ns;                  -- xdom(4.86 max) + D_DO margins
      for j in 0 to 11 loop
        if j = 0 then
          got(0) := to_x01(dout);      -- first bit before first clock
        else
          clk <= '1'; wait for 25 ns; clk <= '0'; wait for 20 ns;
          got(j) := to_x01(dout);
        end if;
      end loop;
      captured := (got = wire_order(K2));
      assert got = wire_order(K2) or got = wire_order(K1)
        report "TIMING-FAIL:TRACK-CONTRACT " & NAME & ": frame keys " &
               to_hstring(got) & " neither fresh nor stale key vector"
        severity failure;
      report "TMARK TRACK " & NAME & " step=" & integer'image(step) &
             " oset_ns_x10=" & integer'image(step * 5) &
             " captured=" & boolean'image(captured);
      if oset + 330 ps >= TSYS then
        assert captured
          report "TIMING-FAIL:TRACK-CONTRACT " & NAME & ": key change " &
                 time'image(oset + 330 ps) & " before the latch fall (>= TSYS) not captured"
          severity failure;
      end if;
      if captured then
        n_capt <= n_capt + 1;
      else
        n_stale <= n_stale + 1;
      end if;
      wait for TSYS;                   -- scan spacing, keeps phases rotating
    end loop;

    report "TMARK TRACK-SUMMARY " & NAME &
           " stale_in_window=" & integer'image(n_stale) &
           " captured=" & integer'image(n_capt) &
           " steps=" & integer'image(NSTEPS);
    report "SYSPASS " & NAME & " contract sweep done";
    finish;
    wait;
  end process;

end architecture;
