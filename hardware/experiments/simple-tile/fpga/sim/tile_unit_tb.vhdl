-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Unit self-checks for tile_fpga against the UNMODIFIED rev-A reference
-- (hardware/simulation/tile.vhdl with its 74hc165 model), single tile,
-- identical stimulus, edge-exact comparisons.
--
-- Scenarios (each assert failure aborts the sim nonzero):
--   S1  basic 16-bit frame + first-bit-before-first-clock, both impls
--   S2  keys CHANGING DURING latch must be tracked (snapshot-while-load);
--       the frame that shifts out after the latch carries the LAST sample
--       (snapshot at latch falling edge) on both impls
--   S3  keys changing AFTER the latch falls / before the first clock must
--       be ignored by both impls (frozen snapshot)
--   S4  latch re-pulse mid-scan: counter+bw cleared, reload, both impls
--   S5  W mux: T_clk/L_clk selected/Z mapping identical on both impls
--   S6  B_W sticky flag: exact set edge, per-edge equality (counter flag)
--   S7  idle tail after the frame: chain input pulls read '0' on both
--
-- sysclk (10 ns) is the DUT's snapshot clock. The single-tile layout has no
-- neighbours: every connector input is left open and falls back to the
-- documented pin pulls ('H'/'L' per pin), exactly like the reference.
-- Zero-delay sim -> functionality only, no achievable-frequency claim.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity tile_unit_tb is
  generic ( NAME : string := "tile_unit";
            SNAP : string := "fall" );
end entity;

architecture sim of tile_unit_tb is
  constant TCLK : time := 50 ns;      -- 20 MHz shift clock (behavioural)
  constant TSYS : time := 10 ns;      -- 100 MHz snapshot clock

  signal buttons : std_logic_vector(11 downto 0) := x"000";
  signal sysclk  : std_logic := '0';
  signal bclk    : std_logic := '0';
  signal latch   : std_logic := '0';
  signal tw      : std_logic := 'Z';

  signal ref_data, ref_bw, ref_tclk, ref_lclk : std_logic;
  signal ref_tlatch, ref_tf, ref_ec, ref_er   : std_logic;
  signal dut_data, dut_bw, dut_tclk, dut_lclk : std_logic;
  signal dut_tlatch, dut_tf, dut_ec, dut_er   : std_logic;

  -- expected frame for a 1x1 tile: keys, "11", L_endrow='1' (pulled, no left
  -- neighbour), T_endcol='1' (pulled, top of column); first bit = buttons(11)
  function exp_frame(k : std_logic_vector(11 downto 0)) return std_logic_vector is
    variable f : std_logic_vector(0 to 15);
  begin
    for j in 0 to 11 loop f(j) := k(11 - j); end loop;
    f(12) := '1'; f(13) := '1'; f(14) := '1'; f(15) := '1';
    return f;
  end function;

begin

  sysclk <= not sysclk after TSYS/2;

  u_ref : entity work.tile
    port map (
      buttons => buttons,
      T_W => tw,  T_endcol => open, T_first => ref_tf, T_latch => ref_tlatch,
      T_clk => ref_tclk, T_data => open,
      B_W => ref_bw, B_endcol => ref_ec, B_first => open, B_latch => latch,
      B_clk => bclk, B_data => ref_data,
      L_endrow => open, L_latch => open, L_clk => ref_lclk, L_data => open,
      R_endrow => ref_er, R_latch => open, R_clk => open, R_data => open
    );

  u_dut : entity work.tile_fpga
    generic map (SNAP_MODE => SNAP)
    port map (
      buttons => buttons, sysclk => sysclk,
      T_W => tw,  T_endcol => open, T_first => dut_tf, T_latch => dut_tlatch,
      T_clk => dut_tclk, T_data => open,
      B_W => dut_bw, B_endcol => dut_ec, B_first => open, B_latch => latch,
      B_clk => bclk, B_data => dut_data,
      L_endrow => open, L_latch => open, L_clk => dut_lclk, L_data => open,
      R_endrow => open, R_latch => open, R_clk => open, R_data => open
    );

  checker : process
    variable f   : std_logic_vector(15 downto 0);
    variable got : std_logic_vector(0 to 15);
    variable stale_hits, ctrl_hits : natural := 0;

    procedure check_data(stage : string) is
    begin
      assert to_x01(ref_data) = to_x01(dut_data)
        report NAME & " " & stage & ": ref data " & std_logic'image(ref_data) &
               " /= dut " & std_logic'image(dut_data)
        severity failure;
    end procedure;

    procedure check_bw(stage : string) is
    begin
      assert to_x01(ref_bw) = to_x01(dut_bw)
        report NAME & " " & stage & ": ref B_W " & std_logic'image(ref_bw) &
               " /= dut " & std_logic'image(dut_bw)
        severity failure;
    end procedure;

    -- one 16-bit frame: sample before each rising edge, compare to expected
    -- and to each other, per-edge B_W equality, return captured DUT word
    procedure run_frame(k : std_logic_vector(11 downto 0);
                        extra_edges : natural; stage : string) is
      variable ef : std_logic_vector(0 to 15);
    begin
      ef := exp_frame(k);
      for e in 0 to 15 + extra_edges - 1 loop
        check_data(stage & " bit" & integer'image(e));
        if e < 16 then
          assert to_x01(dut_data) = ef(e)
            report NAME & " " & stage & ": bit" & integer'image(e) &
                   " dut " & std_logic'image(to_x01(dut_data)) &
                   " expected " & std_logic'image(ef(e))
            severity failure;
        else
          assert to_x01(dut_data) = '0'          -- tail = pulled chain input
            report NAME & " " & stage & ": tail bit" & integer'image(e) &
                   " not '0'" severity failure;
        end if;
        bclk <= '1'; wait for 10 ns;
        check_bw(stage & " edge" & integer'image(e + 1));
        bclk <= '0'; wait for TCLK - 10 ns;
      end loop;
    end procedure;

  begin
    report "=== " & NAME & " unit self-check (ref=work.tile, dut=tile_fpga)";

    -- B_clk idles low at the beginning of every scan
    wait for 10 ns;

    ----------------------------------------------------------------- S1
    buttons <= x"A5C";
    latch <= '1'; wait for 200 ns; latch <= '0'; wait for 20 ns;
    assert to_x01(dut_data) = '1'                 -- first bit BEFORE first clk
      report NAME & " S1: first bit (A5C bit11='1') not present before " &
             "first shift clock" severity failure;
    check_data("S1 first-bit");
    assert to_x01(ref_bw) = '0' and to_x01(dut_bw) = '0'
      report NAME & " S1: B_W not cleared by latch" severity failure;
    run_frame(x"A5C", 8, "S1");                 -- +8 tail edges (S7 partly)
    -- S6: 1x1 top-of-column => B_W must be set now, exactly after edge 16
    assert to_x01(dut_bw) = '1'
      report NAME & " S6: B_W not set after the 16-bit frame" severity failure;
    check_bw("S6 set");

    ----------------------------------------------------------------- S2
    -- change keys DURING the latch: both impls track; frame carries last keys
    buttons <= x"000";
    latch <= '1'; wait for 5*TSYS;               -- settle into shadow
    assert to_x01(ref_data) = '0' and to_x01(dut_data) = '0'
      report NAME & " S2: data not following keys=000 during latch"
      severity failure;
    buttons <= x"FFF"; wait for 5*TSYS;
    assert to_x01(ref_data) = '1'
      report NAME & " S2: ref not transparent during latch" severity failure;
    assert to_x01(dut_data) = '1'
      report NAME & " S2: dut shadow did not track keys=FFF during latch"
      severity failure;
    buttons <= x"923"; wait for 5*TSYS;          -- 923 bit11 = '1'
    check_data("S2 tracking 923");
    assert to_x01(dut_data) = '1'
      report NAME & " S2: dut not tracking keys=923 during latch"
      severity failure;
    latch <= '0'; wait for 20 ns;
    run_frame(x"923", 0, "S2");                  -- snapshot = last keys

    ----------------------------------------------------------------- S3
    -- change keys AFTER the latch falls: must be ignored by both impls;
    -- the 'FFF' change has bit 11 = '1', so a broken (transparent) shadow
    -- would flip the pending first bit from '0' to '1' here and be caught.
    buttons <= x"000";                           -- ensure a clean edge below
    latch <= '1'; wait for 200 ns;
    buttons <= x"3C3"; wait for 5*TSYS;          -- last snapshot = 3C3
    latch <= '0'; wait for 20 ns;
    buttons <= x"FFF";                           -- evil change before clk 1
    wait for 5*TSYS;
    assert to_x01(dut_data) = '0'                -- 3C3 bit11 = 0: frozen snap
      report NAME & " S3: dut moved to post-fall keys before first clock"
      severity failure;
    check_data("S3 first bit");
    run_frame(x"3C3", 0, "S3");

    ----------------------------------------------------------------- S4
    -- mid-scan latch re-pulse: clears counter + B_W, reloads
    buttons <= x"111";
    latch <= '1'; wait for 200 ns; latch <= '0'; wait for 20 ns;
    for e in 0 to 4 loop                         -- shift 5 partial edges
      bclk <= '1'; wait for 10 ns; bclk <= '0'; wait for TCLK - 10 ns;
    end loop;
    assert to_x01(dut_bw) = '0' and to_x01(ref_bw) = '0'
      report NAME & " S4: B_W wrongly set 5 edges into the new frame"
      severity failure;
    buttons <= x"222";
    latch <= '1'; wait for 200 ns;
    check_data("S4 during re-latch");
    assert to_x01(dut_data) = '0'                -- 222 bit11 = 0
      report NAME & " S4: dut not reloaded by mid-scan latch" severity failure;
    latch <= '0'; wait for 20 ns;
    assert to_x01(dut_bw) = '0' and to_x01(ref_bw) = '0'
      report NAME & " S4: B_W not cleared by re-latch" severity failure;
    run_frame(x"222", 0, "S4");                  -- fresh frame from bit 1

    ----------------------------------------------------------------- S5
    -- mux: T_W low => w=0 => T_clk driven, L_clk Z; T_W open => reverse
    tw <= '0'; wait for 5 ns;
    assert ref_tclk /= 'Z' and dut_tclk /= 'Z'
      report NAME & " S5: T_clk not driven with T_W=0" severity failure;
    assert ref_lclk = 'Z' and dut_lclk = 'Z'
      report NAME & " S5: L_clk not Z with T_W=0" severity failure;
    bclk <= '1'; wait for 5 ns;
    assert ref_tclk = '1' and dut_tclk = '1'
      report NAME & " S5: T_clk not forwarding clock high" severity failure;
    assert ref_lclk = 'Z' and dut_lclk = 'Z'
      report NAME & " S5: L_clk not Z during clock high" severity failure;
    bclk <= '0'; wait for 5 ns;
    tw <= 'Z'; wait for 15 ns;
    assert ref_tclk = 'Z' and dut_tclk = 'Z'
      report NAME & " S5: T_clk not Z with T_W open" severity failure;
    assert ref_lclk /= 'Z' and dut_lclk /= 'Z'
      report NAME & " S5: L_clk not driven with T_W open" severity failure;
    assert dut_tclk = ref_tclk and dut_lclk = ref_lclk
      report NAME & " S5: mux state differs" severity failure;

    ------------------------------------------------------------------ S8
    -- CHARACTERISATION (not pass-equivalence): directed phase sweep of a key
    -- change inside the final sysclk window before the latch fall.
    --   * reference '165 (async /PL): captures K_B regardless of phase
    --   * SNAP="track": shadow keeps K_A (last aligned sysclk sample) for the
    --     whole window -> the first post-fall bit differs from rev A for EVERY
    --     in-window phase. This is the expected, documented mismatch window
    --     (docs/clock_domains.md); the sweep demonstrates rather than hides it.
    --   * SNAP="fall": snapshot at the falling edge -> captures K_B for every
    --     in-window phase (zero mismatches expected; FF setup/hold at the fall
    --     itself cannot be modelled in zero-delay sim).
    -- A control case changes the keys BEFORE the last aligned sample:
    -- both modes capture K_B.
    for ph in 1 to TSYS/(1 ns) - 1 loop            -- phases 1..9 ns
      buttons <= x"000";                            -- K_A: bit(11)=0
      latch <= '1'; wait for 200 ns;
      wait until rising_edge(sysclk);               -- aligned K_A sample
      wait for ph * 1 ns;                           -- into the window
      buttons <= x"800";                            -- K_B: bit(11)=1
      wait for (TSYS - ph * 1 ns - 1 ps);           -- land JUST before next
      latch <= '0';                                 -- aligned sysclk sample
      wait for TSYS;                                -- settle past that edge
      report NAME & " S8 sweep ph=" & integer'image(ph) & "ns: ref=" &
             std_logic'image(to_x01(ref_data)) & " dut=" &
             std_logic'image(to_x01(dut_data)) & " (snap=" & SNAP & ")";
      if to_x01(ref_data) /= to_x01(dut_data) then
        stale_hits := stale_hits + 1;
      end if;
    end loop;
    -- control: key change BEFORE the last aligned sample (no window)
    buttons <= x"000"; latch <= '1'; wait for 200 ns;
    buttons <= x"800";                              -- long before the fall
    wait for 5*TSYS;
    latch <= '0'; wait for TSYS;
    if to_x01(ref_data) /= to_x01(dut_data) then
      ctrl_hits := ctrl_hits + 1;
    end if;
    report NAME & " S8 CHARACTERISATION: stale hits=" &
           integer'image(stale_hits) & " of 9 in-window phases, control=" &
           integer'image(ctrl_hits) & " (snap=" & SNAP & ")";
    if SNAP = "track" then
      -- every in-window phase must show the approximation (else the TB
      -- timing is broken, not the design)
      assert stale_hits = 9 and ctrl_hits = 0
        report NAME & " S8: expected 9 stale + 0 control mismatches in " &
               "track mode, got " & integer'image(stale_hits) & "/" &
               integer'image(ctrl_hits)
        severity failure;
    else
      assert stale_hits = 0
        report NAME & " S8: fall mode should match rev A for every phase, " &
               "got " & integer'image(stale_hits) & " mismatches"
        severity failure;
    end if;

    report "REGPASS " & NAME & " (S1..S7: first-bit, change-in-latch, " &
           "frozen-after-fall, mid-scan reset, mux, counterflag, tail; " &
           "S8: phase-sweep characterisation, snap=" & SNAP & ")";
    finish;
    wait;
  end process;

end architecture;
