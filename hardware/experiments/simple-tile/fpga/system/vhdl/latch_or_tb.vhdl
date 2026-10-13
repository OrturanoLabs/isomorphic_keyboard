-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- latch_or_tb: unit checks of the FPGA tile's latch-OR capture (fall mode).
--
-- One tile_sys leaf, strapped like a standalone tile (all presence straps
-- open -> pull-ups: T_endcol='1', L_endrow='1'; B_first 'Z'->up -> '1' so W=1
-- selects the L_data leg for the serial input; L_data held 'Z'->down -> '0').
--
-- Scenarios (SCEN generic):
--   0  POS: latch driven from the B_latch leg only (source = below chain).
--   1  POS: latch driven from the R_latch leg only (source = right chain).
--   2  POS: both legs driven, SKEW_100PS apart on rise and fall: the OR must
--      deliver exactly ONE clean local falling edge (skew is absorbed for
--      rise-at-first / fall-at-last), capture still correct.
--   3  NEG: a glitch pattern makes the OR fall TWICE (A falls, B falls late,
--      A re-rises, A falls again): the local latch-glitch monitor must fire
--      (TIMING-FAIL:LATCH-GLITCH). A second capture is what real hardware
--      would do -- it must not be silent.
--   4  NEG: a key changes INSIDE the synthetic snapshot window at the local
--      latch fall: the leaf SNAP-WINDOW budget must fire
--      (TIMING-FAIL:SNAP-WINDOW).
--   5  POS: a key changes 30 ns BEFORE the fall (outside the window): the
--      new value must be captured (frame correct, no assertion).
--
-- Checks (positive scens): first bit present BEFORE the first shift clock,
-- 16-bit frame bit-exact vs the wire order, exactly one local latch fall,
-- local latch fall time reported (TMARK LATCHFALL). Marker "SYSPASS <NAME>".

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
use work.system_timing_pkg.all;

entity latch_or_tb is
  generic (
    NAME        : string  := "latch_or";
    SCEN        : natural := 0;
    SKEW_100PS  : natural := 70;   -- 7 ns source skew for scen 2/3
    CORNER      : natural := 1;
    SCALE_PCT   : natural := 100
  );
end entity;

architecture sim of latch_or_tb is

  constant D_PADIN_TB : time := pick_ns(T_PADIN_NS, T_PADIN_F_NS, T_PADIN_X_NS, CORNER);
  constant SU_TB      : time := pick_ns(T_SNAP_SU_NS, T_SNAP_SU_F_NS, T_SNAP_SU_X_NS, CORNER);

  constant K1 : std_logic_vector(11 downto 0) := x"A5A";
  constant K2 : std_logic_vector(11 downto 0) := x"3C3";

  signal keys     : std_logic_vector(11 downto 0) := K1;
  signal b_latch  : std_logic := 'Z';
  signal r_latch  : std_logic := 'Z';
  signal b_clk    : std_logic := '0';  -- driven-low idle (controller style);
                                       -- 'Z'->'1' would never rise through the
                                       -- pull-up resolution
  signal dout     : std_logic;
  signal dbg_latch, dbg_clk, dbg_ds, dbg_w : std_logic;

  signal exp_frame : std_logic_vector(0 to 15) := (others => '1');
  signal lfcount   : natural := 0;

begin

  dut : entity work.tile_sys
    generic map (CORNER => CORNER, SCALE_PCT => SCALE_PCT, SNAP => "fall",
                 LOC => "u")
    port map (
      buttons => keys,
      T_W => 'Z', T_endcol => 'Z', T_first => open, T_latch => open,
      T_clk => open, T_data => 'Z',
      B_W => open, B_endcol => open, B_first => 'Z',
      B_latch => b_latch, B_clk => b_clk, B_data => dout,
      L_endrow => 'Z', L_latch => open, L_clk => open, L_data => 'Z',
      R_endrow => open, R_latch => r_latch, R_clk => 'Z', R_data => open,
      dbg_clk => dbg_clk, dbg_latch => dbg_latch, dbg_ds => dbg_ds,
      dbg_w => dbg_w);

  -- expected 16-bit wire word for a known key vector (MSB first):
  -- keys(11..0), markers "11", L_endrow('1'), T_endcol('1')
  fgen : process(keys)
    variable v : std_logic_vector(0 to 15);
  begin
    for j in 0 to 11 loop
      v(j) := keys(11 - j);
    end loop;
    v(12) := '1'; v(13) := '1'; v(14) := '1'; v(15) := '1';
    exp_frame <= v;
  end process;

  -- local latch fall counter / glitch assertion
  mon : process(dbg_latch)
    variable n    : natural := 0;
    variable prev : std_logic := 'X';
  begin
    if now > 0 ns and dbg_latch'event and to_x01(prev) = '1' and
       to_x01(dbg_latch) = '0' then
      n := n + 1;
      lfcount <= n;
      report "TMARK LATCHFALL #" & integer'image(n) & " at " & time'image(now);
      assert n <= 1
        report "TIMING-FAIL:LATCH-GLITCH " & NAME & ": local latch falling edge #" &
               integer'image(n) & " -- latch-OR of the two connector legs glitched"
        severity failure;
    end if;
    prev := dbg_latch;
  end process;

  stim : process
    constant TFALL : time := 200 ns;       -- controller-side latch fall
    constant GAP   : time := 30 ns;        -- guard after (final) fall
    variable got : std_logic_vector(0 to 15);
  begin
    -- latch high phase per scenario (B leg only / R leg only / both skewed)
    if SCEN = 1 then
      r_latch <= '1';
    elsif SCEN = 0 or SCEN = 4 or SCEN = 5 then
      b_latch <= '1';
    else
      b_latch <= '1'; r_latch <= '1' after SKEW_100PS * 100 ps;
    end if;

    -- key stimulus timing. scen 4 (window stress) schedules the key change
    -- non-blocking so the fall below still happens: aim INSIDE the synthetic
    -- snapshot setup window at the LOCAL fall. The leaf measures
    -- (local fall) - (delayed key event) = TFALL - TC (equal pad delays
    -- cancel), so landing the change SU/2 before the controller-side fall
    -- puts it SU/2 before the fall the FF sees.
    if SCEN = 4 then
      keys <= K2 after TFALL - SU_TB / 2;
    elsif SCEN = 5 then
      wait for TFALL - 30 ns;
      keys <= K2;
    end if;

    wait for TFALL;                        -- synchronized fall(s)
    case SCEN is
      when 1 => r_latch <= '0';
      when 2 => b_latch <= '0'; r_latch <= '0' after SKEW_100PS * 100 ps;
      when 3 =>
        -- staged sequence (separate 'after' clauses on one signal would
        -- overwrite each other): A falls, B falls SKEW later (OR falls),
        -- A re-rises (OR rises), A falls again (the SECOND fall = glitch)
        b_latch <= '0';
        wait for SKEW_100PS * 100 ps;
        r_latch <= '0';
        wait for 30 ns;
        b_latch <= '1';
        wait for 70 ns;
        b_latch <= '0';
        wait for 200 ns;                 -- keep it low for the read phase
      when others => b_latch <= '0';
    end case;

    wait for GAP + 100 ns + SKEW_100PS * 100 ps;   -- past every fall + xdom

    -- first bit BEFORE any shift clock
    assert to_x01(dout) = exp_frame(0)
      report "TIMING-FAIL:FIRSTBIT " & NAME & ": first bit before clock got " &
             std_logic'image(to_x01(dout)) & " expected " & std_logic'image(exp_frame(0))
      severity failure;

    -- 16 shift clocks, sample just before each following edge
    for j in 0 to 15 loop
      wait for 45 ns;                      -- sample window before next rise
      got(j) := to_x01(dout);
      b_clk <= '1';
      wait for 25 ns;
      b_clk <= '0';
      wait for 5 ns;
    end loop;

    report NAME & " got stream=" & to_hstring(got) &
           " exp=" & to_hstring(exp_frame);
    for j in 0 to 15 loop
      assert got(j) = exp_frame(j)
        report "TIMING-FAIL:STREAM " & NAME & ": frame bit" & integer'image(j) &
               " got " & std_logic'image(got(j)) & " expected " &
               std_logic'image(exp_frame(j))
        severity failure;
    end loop;
    report NAME & " frame word=" & to_hstring(got) & " scen=" & integer'image(SCEN);

    assert SCEN /= 3 and SCEN /= 4
      report "CONTRACT: negative scenario reached the pass marker - hazard not caught"
      severity failure;
    report "SYSPASS " & NAME & " scen=" & integer'image(SCEN);
    finish;
    wait;
  end process;

end architecture;
