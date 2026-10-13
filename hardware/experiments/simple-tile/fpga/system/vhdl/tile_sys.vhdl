-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- tile_sys: timing-aware FPGA tile for the 20 MHz chain system model.
--
-- The leaf is the UNMODIFIED golden RTL core ../rtl/tile_fpga.vhdl
-- (SNAP_MODE generic; lead device GW1NZ-LV1QN48, default SNAP_MODE="fall").
-- This wrapper adds, around it:
--
--   * per-pin pad input delays (transport, T_PADIN) incl. the pin pull
--     resolution (UP/DOWN) exactly as configured in synth/tile_gw1nz.cst;
--     B_clk/R_clk are merged into ONE node before the delay because the
--     FPGA has a single clk pin (rev-A J103.2 = J104.2, docs/pin_budget.md);
--   * lumped per-output-pin delays: dout (T_DO_INT + T_PADOUT), latch
--     forward (T_LATCHO + T_PADOUT), B_W (T_BW_INT + T_PADOUT);
--   * TBUF timing on the true-Z clock outputs T_clk/L_clk: enable / disable /
--     propagate (T_TBUF_EN/DIS/PD), mirroring the discrete '125/'126 pattern;
--   * latch OR of BOTH connector legs evaluated on their own delayed pads
--     (the DUT ORs them internally; dbg_latch duplicates it for observation);
--   * per-tile timing assertions:
--       SNAP-XDOM   : first shift rising edge after the local latch fall must
--                     come >= T_XDOM_REQ later (latch-clocked shadow domain ->
--                     shift-clocked shreg "first-shift special load" recovery;
--                     fit anchor = fitted 4.86 ns + setup, corners.json);
--       SNAP-WINDOW : pd legs (keys/straps) must be stable T_SNAP_SU before /
--                     T_SNAP_HD after the local latch falling edge (the '165
--                     /PL recovery analogue; SYNTHETIC placeholder window);
--       CLK-PULSE   : during an active pulse train (rises <= 60 ns apart) the
--                     high and low phases must be >= T_CLKHI_REQ.
--   * dbg_* observation-only outputs (resolved local clock/latch/DS mux/W),
--     same convention as the discrete tile_timed debug taps.
--
-- The cross-domain relationship is asserted as a BUDGET because the read-only
-- golden RTL does not export internal FF nodes; sims cannot model
-- metastability (documented in fpga/docs/clock_domains.md).
--
-- All delays are corner-selected (CORNER 0/1/2 = syn_min/fit/syn_max) from
-- system_timing_pkg and multiplied by SCALE/100 (synthetic stress knob).

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.system_timing_pkg.all;

entity tile_sys is
  generic (
    CORNER    : natural := 1;      -- 0 syn_min / 1 fit / 2 syn_max
    SCALE_PCT : natural := 100;    -- 100 = 1.0x (pure corner values)
    SNAP      : string  := "fall"; -- passed to the golden core
    LOC       : string  := "tile"
  );
  port (
    buttons : in std_logic_vector(11 downto 0) := (others => 'L');
    sysclk  : in std_logic := '0';   -- on-chip/module snapshot osc, track only
                                     -- (no pad: OSCZ/SB_HFOSC are interior)

    T_W : in std_logic := 'Z';
    T_endcol : in std_logic := 'Z';
    T_first : out std_logic := '0';
    T_latch : out std_logic := '0';
    T_clk : out std_logic := 'Z';
    T_data : in std_logic := 'Z';

    B_W : out std_logic := '0';
    B_endcol : out std_logic := '0';
    B_first : in std_logic := 'Z';
    B_latch : in std_logic := 'Z';
    B_clk : in std_logic := 'Z';
    B_data : out std_logic := '0';

    L_endrow : in std_logic := 'Z';
    L_latch : out std_logic := '0';
    L_clk : out std_logic := 'Z';
    L_data : in std_logic := 'Z';

    R_endrow : out std_logic := '0';
    R_latch : in std_logic := 'Z';
    R_clk : in std_logic := 'Z';
    R_data : out std_logic := '0';

    dbg_clk   : out std_logic;   -- resolved merged local shift clock
    dbg_latch : out std_logic;   -- local latch OR output (post-pad)
    dbg_ds    : out std_logic;   -- resolved serial-input mux node
    dbg_w     : out std_logic    -- local W state (post-pad straps)
  );
end entity;

architecture timed of tile_sys is

  constant SC : real := real(SCALE_PCT) / 100.0;

  constant D_PADIN  : time := pick_ns(T_PADIN_NS,  T_PADIN_F_NS,  T_PADIN_X_NS,  CORNER) * SC;
  constant D_PADOUT : time := pick_ns(T_PADOUT_NS, T_PADOUT_F_NS, T_PADOUT_X_NS, CORNER) * SC;
  constant D_DO     : time := pick_ns(T_DO_INT_NS, T_DO_INT_F_NS, T_DO_INT_X_NS, CORNER) * SC
                              + D_PADOUT;
  constant D_BW     : time := pick_ns(T_BW_INT_NS, T_BW_INT_F_NS, T_BW_INT_X_NS, CORNER) * SC
                              + D_PADOUT;
  constant D_LATCHO : time := pick_ns(T_LATCHO_INT_NS, T_LATCHO_INT_F_NS, T_LATCHO_INT_X_NS, CORNER) * SC
                              + D_PADOUT;
  constant D_TEN  : time := pick_ns(T_TBUF_EN_NS,  T_TBUF_EN_F_NS,  T_TBUF_EN_X_NS,  CORNER) * SC;
  constant D_TDIS : time := pick_ns(T_TBUF_DIS_NS, T_TBUF_DIS_F_NS, T_TBUF_DIS_X_NS, CORNER) * SC;
  constant D_TPD  : time := pick_ns(T_TBUF_PD_NS,  T_TBUF_PD_F_NS,  T_TBUF_PD_X_NS,  CORNER) * SC;

  -- timing REQUIREMENTS (assertion budgets; NOT scaled by the stress knob)
  constant T_XDOM_REQ   : time := pick_ns(T_XDOM_REQ_NS, T_XDOM_REQ_F_NS, T_XDOM_REQ_X_NS, CORNER);
  constant T_SNAP_SU    : time := pick_ns(T_SNAP_SU_NS,  T_SNAP_SU_F_NS,  T_SNAP_SU_X_NS,  CORNER);
  constant T_SNAP_HD    : time := pick_ns(T_SNAP_HD_NS,  T_SNAP_HD_F_NS,  T_SNAP_HD_X_NS,  CORNER);
  constant T_CLKHI_REQ  : time := pick_ns(T_CLKHI_REQ_NS, T_CLKHI_REQ_F_NS, T_CLKHI_REQ_X_NS, CORNER);

  -- pad nodes with pin pulls (UP/DOWN per synth/tile_gw1nz.cst)
  signal bclk_n, rclk_n : std_logic := 'H';   -- clk pull-UP (merged below)
  signal clk_node       : std_logic := 'H';   -- single physical clk pin node
  signal bla_n, rla_n   : std_logic := 'L';   -- latch legs pull-DOWN
  signal tda_n, lda_n   : std_logic := 'L';   -- data legs pull-DOWN
  signal tw_n, tec_n, bf_n, ler_n : std_logic := 'H';  -- straps pull-UP

  -- delayed pad signals = what the fabric actually sees
  signal clk_pad  : std_logic := 'H';
  signal bla_pad  : std_logic := 'L';
  signal rla_pad  : std_logic := 'L';
  signal tda_pad  : std_logic := 'L';
  signal lda_pad  : std_logic := 'L';
  signal tw_pad   : std_logic := 'H';
  signal tec_pad  : std_logic := 'H';
  signal bf_pad   : std_logic := 'H';
  signal ler_pad  : std_logic := 'H';
  signal btn_pad  : std_logic_vector(11 downto 0) := (others => 'L');

  -- DUT-side outputs
  signal dut_data, dut_latcho, dut_bw : std_logic;
  signal dut_tclk, dut_lclk           : std_logic;

  -- observation
  signal clk_loc, latch_loc, w_loc, ds_loc : std_logic;

begin

  -- ------------------------------------------------ pad legs with pin pulls
  bclk_n <= 'H';  bclk_n <= B_clk;
  rclk_n <= 'H';  rclk_n <= R_clk;
  clk_node <= bclk_n;  clk_node <= rclk_n;      -- one physical pin/node
  bla_n  <= 'L';  bla_n  <= B_latch;
  rla_n  <= 'L';  rla_n  <= R_latch;
  tda_n  <= 'L';  tda_n  <= T_data;
  lda_n  <= 'L';  lda_n  <= L_data;
  tw_n   <= 'H';  tw_n   <= T_W;
  tec_n  <= 'H';  tec_n  <= T_endcol;
  bf_n   <= 'H';  bf_n   <= B_first;
  ler_n  <= 'H';  ler_n  <= L_endrow;

  clk_pad <= transport clk_node after D_PADIN;
  bla_pad <= transport bla_n   after D_PADIN;
  rla_pad <= transport rla_n   after D_PADIN;
  tda_pad <= transport tda_n   after D_PADIN;
  lda_pad <= transport lda_n   after D_PADIN;
  tw_pad  <= transport tw_n    after D_PADIN;
  tec_pad <= transport tec_n   after D_PADIN;
  bf_pad  <= transport bf_n    after D_PADIN;
  ler_pad <= transport ler_n   after D_PADIN;
  btn_pad <= transport buttons after D_PADIN;

  clk_loc   <= to_x01(clk_pad);
  latch_loc <= to_x01(bla_pad) or to_x01(rla_pad);   -- duplicates the DUT OR
  w_loc     <= to_x01(tw_pad) and to_x01(bf_pad);
  ds_loc    <= to_x01(lda_pad) when to_x01(w_loc) = '1' else to_x01(tda_pad);

  dbg_clk   <= clk_loc;
  dbg_latch <= latch_loc;
  dbg_ds    <= ds_loc;
  dbg_w     <= w_loc;

  -- ------------------------------------------------------- golden FPGA core
  dut : entity work.tile_fpga
    generic map (SNAP_MODE => SNAP)
    port map (
      buttons  => btn_pad,
      sysclk   => sysclk,              -- used only in SNAP="track"
      T_W => tw_pad, T_endcol => tec_pad, T_first => open,
      T_latch => dut_latcho, T_clk => dut_tclk, T_data => tda_pad,
      B_W => dut_bw, B_endcol => open, B_first => bf_pad,
      B_latch => bla_pad, B_clk => clk_pad, B_data => dut_data,
      L_endrow => ler_pad, L_latch => open, L_clk => dut_lclk,
      L_data => lda_pad,
      R_endrow => open, R_latch => rla_pad, R_clk => clk_pad,
      R_data => open
    );

  -- --------------------------------------------------------- output pins
  B_data <= transport dut_data   after D_DO;
  R_data <= transport dut_data   after D_DO;
  T_latch <= transport dut_latcho after D_LATCHO;
  L_latch <= transport dut_latcho after D_LATCHO;
  B_W    <= transport dut_bw     after D_BW;

  -- presence straps: PCB GND in rev A, no FPGA pin (kept for TB wiring)
  T_first  <= '0';
  B_endcol <= '0';
  R_endrow <= '0';

  -- true-Z clock outputs with TBUF en/dis/propagate timing
  p_tclk : process(dut_tclk)
    variable driven : boolean := false;
  begin
    if dut_tclk = 'Z' then
      if driven then
        T_clk <= transport 'Z' after D_TDIS;
      end if;
      driven := false;
    else
      if not driven then
        T_clk <= transport dut_tclk after D_TEN;
      else
        T_clk <= transport dut_tclk after D_TPD;
      end if;
      driven := true;
    end if;
  end process;

  p_lclk : process(dut_lclk)
    variable driven : boolean := false;
  begin
    if dut_lclk = 'Z' then
      if driven then
        L_clk <= transport 'Z' after D_TDIS;
      end if;
      driven := false;
    else
      if not driven then
        L_clk <= transport dut_lclk after D_TEN;
      else
        L_clk <= transport dut_lclk after D_TPD;
      end if;
      driven := true;
    end if;
  end process;

  -- ============================ per-tile timing assertions (budget class)

  -- SNAP-XDOM: latch-clocked shadow domain -> clk-clocked shreg first load.
  p_xdom : process(clk_loc, latch_loc)
    variable t_fall : time := 0 ns;
    variable armed  : boolean := false;   -- a fall seen, first rise pending
    variable prev_l : std_logic := 'X';
    variable prev_c : std_logic := 'X';
  begin
    if latch_loc'event then
      if now > 0 ns and to_x01(prev_l) = '1' and to_x01(latch_loc) = '0' then
        t_fall := now;                   -- genuine 1->0 local fall arms it
        armed := true;
      elsif to_x01(latch_loc) = '1' then
        armed := false;
      end if;
      prev_l := latch_loc;
    end if;
    if clk_loc'event then
      if armed and to_x01(prev_c) = '0' and to_x01(clk_loc) = '1' then
        assert now - t_fall >= T_XDOM_REQ
          report "TIMING-FAIL:SNAP-XDOM " & LOC & ": first shift edge " &
                 time'image(now - t_fall) & " after latch fall < requirement " &
                 time'image(T_XDOM_REQ)
          severity failure;
        armed := false;
      end if;
      prev_c := clk_loc;
    end if;
  end process;

  -- SNAP-WINDOW: pd legs stable through the local latch fall ('165 /PL
  -- recovery analogue; SYNTHETIC window, corners.json "_t_snap_src").
  p_snap : process(btn_pad, tec_pad, ler_pad, latch_loc)
    variable t_last : time := -1000 ns;
    variable t_fall : time := 0 ns;
  begin
    if btn_pad'event or tec_pad'event or ler_pad'event then
      if now > 0 ns then
        t_last := now;
      end if;
      if to_x01(latch_loc) = '0' and now - t_fall < T_SNAP_HD and t_fall /= 0 ns then
        assert false
          report "TIMING-FAIL:SNAP-WINDOW " & LOC & ": pd leg changed " &
                 time'image(now - t_fall) & " after latch fall (< hold " &
                 time'image(T_SNAP_HD) & ")"
          severity failure;
      end if;
    end if;
    if latch_loc'event and to_x01(latch_loc) = '0' then
      assert now - t_last >= T_SNAP_SU
        report "TIMING-FAIL:SNAP-WINDOW " & LOC & ": pd leg last changed " &
               time'image(now - t_last) & " before latch fall (< setup " &
               time'image(T_SNAP_SU) & ")"
        severity failure;
      t_fall := now;
    end if;
  end process;

  -- CLK-PULSE: high/low phase guard during an active pulse train.
  p_pulse : process(clk_loc)
    variable t_rise : time := 0 ns;
    variable t_fall : time := 0 ns;
    variable have_r : boolean := false;
    variable have_f : boolean := false;
  begin
    if clk_loc'event and now > 10 ns then     -- pads settled (power-on
      if to_x01(clk_loc) = '1' then           -- transients are not pulses)
        if have_f and now - t_fall <= 70 ns and now - t_fall > 0 ns then
          assert now - t_fall >= T_CLKHI_REQ
            report "TIMING-FAIL:CLK-PULSE " & LOC & ": low phase " &
                   time'image(now - t_fall) & " < " & time'image(T_CLKHI_REQ)
            severity failure;
        end if;
        t_rise := now; have_r := true;
      else
        if have_r and now - t_rise <= 70 ns and now - t_rise > 0 ns then
          assert now - t_rise >= T_CLKHI_REQ
            report "TIMING-FAIL:CLK-PULSE " & LOC & ": high phase " &
                   time'image(now - t_rise) & " < " & time'image(T_CLKHI_REQ)
            severity failure;
        end if;
        t_fall := now; have_f := true;
      end if;
    end if;
  end process;

end architecture;
