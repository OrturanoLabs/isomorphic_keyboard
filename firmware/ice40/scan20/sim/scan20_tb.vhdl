-- SPDX-License-Identifier: GPL-3.0-only
--
-- scan20_tb: self-checking testbench for the scan20 20 MHz scan frontend /
-- test engine (firmware/ice40/scan20/src/scan20_core.vhdl, the DUT).
--
-- The chain under the DUT is an unmodified-by-path system model: a W x H
-- grid of the existing fall-snapshot tile FPGAs
-- (hardware/experiments/simple-tile/fpga/rtl/tile_fpga.vhdl,
-- SNAP_MODE="fall", driven by the DUT through the very same nets the golden
-- controller drives). Expected streams/coords come from the docs-derived
-- reference package hardware/experiments/simple-tile/regression/
-- tile_reg_pkg.vhdl. Both references are READ-ONLY (used by path).
--
-- Checks per run ("grid"):
--  C1 stream: every sampled bit (dbg_sample) equals the expected wire bit
--     (sample-before-shift: sampled BEFORE the launch that advances the
--     chain; lead to the next launch must be exactly SAMPLE_LEAD_TICKS);
--  C2 frames: at frame_valid the frame data equals the docs-expected frame
--     and (col,row,frame_index) equal the traversal walk;
--  C3 completion: frame_valid only with exactly 16 launched pulses in that
--     frame and BOARD_CLK already low for the full 16th low phase (the 16th
--     pulse completes before any frame state changes);
--  C4 edges: BOARD_CLK rising edges == dbg_launch strobes == exactly
--     16 per frame (no extra/missing edges), high phases exactly TICKS_HIGH
--     sysclk ticks, low phases exactly the scheduled tick count;
--  C5 glitch/runt: any two BOARD_CLK toggles are at least one full sysclk
--     period apart (the engine's minimum phase) and every high phase is
--     TICKS_HIGH x TSYS in TIME;
--  C6 latch: latch high width == LATCH_TICKS ticks; latch-deassert->first
--     launch == GUARD_TICKS ticks (the deassert guard);
--  C7 repeat: CLEAN_SCANS complete episodes, identical data across them
--     (latch reload), err counts stay 0;
--  C8 marker error (INJ_FRAME >= 0): episode INJ_EP sees markers of frame
--     INJ_FRAME forced '0' at the controller pin -> err_framing, quiet
--     recovery >= RECOVERY_TICKS, aborted episode had exactly
--     16 x (INJ_FRAME+1) edges, a following episode is then clean;
--  C9 timeout (EXPECT_TIMEOUTS > 0): watchdog bites (err_timeout), bus
--     quiet, retry; never a scan_done in this mode.
--
-- Model floors enforced AT ELABORATION (make negative configs fail loud;
-- numbers from hardware/experiments/simple-tile/timing-chain/results/
-- sweeps.txt, 20 MHz, route 1.5 ns/hop):
--   high phase  >= MODEL_MIN_HIGH_PS  (28 ns, max corner)
--   guard       >= MODEL_MIN_GUARD_PS (15 ns, max corner)
--   sample lead within [LEAD_MIN_PS, LEAD_MAX_PS] (0.5 .. 28 ns)
--   latch width >= 10 ns (SN74LVC165A ~PL width 4.3 ns + recovery 3.5 ns)
-- These floors are why the guard/duty negative configs are meaningful even
-- without a timed tile model here; the timed chain checks live in
-- hardware/experiments/simple-tile/timing-chain/.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

use work.tile_reg_pkg.all;

entity scan20_tb is
  generic (
    NAME          : string  := "unnamed";
    W             : natural := 1;
    H             : natural := 1;
    PRESENT       : string  := "1";
    BMODE         : natural := 0;
    -- DUT tick configuration (mirror of scan20_core generics)
    TSYS_PS       : natural := 10_000;   -- sysclk period (10 ns = 100 MHz)
    TPB           : natural := 5;        -- TICKS_PER_BIT
    THI           : natural := 3;        -- TICKS_HIGH
    LEAD          : natural := 1;        -- SAMPLE_LEAD_TICKS
    LATCH_TICKS   : natural := 100;
    GUARD_TICKS   : natural := 4;
    FGAP_TICKS    : natural := 5;
    IDLE_TICKS    : natural := 400;
    TIMEOUT_TICKS : natural := 8192;
    REC_TICKS     : natural := 200;
    MAX_TILES     : natural := 16;
    CLEAN_SCANS   : natural := 2;        -- clean episodes required
    INJ_FRAME     : integer := -1;       -- frame whose markers are forced '0'
    INJ_EP        : natural := 1;        -- on this episode (1-based)
    EXPECT_TIMEOUTS : natural := 0;      -- >0: timeout-mode test
    -- model floors (timing-chain sweeps; ps)
    MODEL_MIN_HIGH_PS  : natural := 28_000;
    MODEL_MIN_GUARD_PS : natural := 15_000;
    LEAD_MIN_PS        : natural := 500;
    LEAD_MAX_PS        : natural := 28_000
  );
end entity;

architecture sim of scan20_tb is

  constant TSYST : time := TSYS_PS * 1 ps;

  constant pmap  : t_map(0 to W*H-1) := parse_present(PRESENT, W, H);
  constant ncol  : natural := traversed_columns(pmap, W, H);
  constant nfr   : natural := reachable_frames(pmap, W, H);

  -- expected wiring
  signal sysclk      : std_logic := '0';
  signal reset_n     : std_logic := '0';
  signal board_clk   : std_logic;
  signal board_latch : std_logic;
  signal data_raw    : std_logic;
  signal data_drv    : std_logic;
  signal inj_on      : std_logic := '0';

  signal frame_valid : std_logic;
  signal frame_data  : std_logic_vector(15 downto 0);
  signal frame_col   : std_logic_vector(4 downto 0);
  signal frame_row   : std_logic_vector(4 downto 0);
  signal frame_index : std_logic_vector(4 downto 0);
  signal scan_done   : std_logic;
  signal scan_count  : std_logic_vector(15 downto 0);
  signal busy        : std_logic;
  signal err_framing : std_logic;
  signal err_timeout : std_logic;
  signal err_count   : std_logic_vector(7 downto 0);
  signal dbg_sample  : std_logic;
  signal dbg_launch  : std_logic;
  signal dbg_state   : std_logic_vector(3 downto 0);

  type t_net is array (natural range <>, natural range <>) of std_logic;

  -- grid nets (implicit 'Z' open-connector defaults)
  signal vW, vEC, vFirst, vLatch, vClk, vData : t_net(1 to W, 1 to H+1) :=
    (others => (others => 'Z'));
  signal hER, hLatch, hClk, hData : t_net(0 to W, 1 to H) :=
    (others => (others => 'Z'));

  -- per-episode expected frame bookkeeping
  type t_fr is record
    c, r : natural;
    wire : std_logic_vector(0 to 15);
  end record;
  type t_frvec is array (natural range <>) of t_fr;

  function build_frames return t_frvec is
    variable f : t_frvec(0 to nfr-1);
    variable k : natural := 0;
  begin
    for c in 1 to ncol loop
      for r in 1 to contig_height(pmap, W, H, c) loop
        f(k).c := c;
        f(k).r := r;
        f(k).wire := frame_wire(pmap, W, H, c, r, buttons_for(BMODE, c, r));
        k := k + 1;
      end loop;
    end loop;
    return f;
  end function;

  constant FRAMES : t_frvec(0 to nfr-1) := build_frames;

begin

  -- model floors checked at elaboration
  assert THI * TSYS_PS >= MODEL_MIN_HIGH_PS
    report NAME & ": high phase " & integer'image(THI * TSYS_PS / 1000) &
           " ns < modeled min " & integer'image(MODEL_MIN_HIGH_PS / 1000) & " ns"
    severity failure;
  assert GUARD_TICKS * TSYS_PS >= MODEL_MIN_GUARD_PS
    report NAME & ": latch deassert guard " &
           integer'image(GUARD_TICKS * TSYS_PS / 1000) & " ns < modeled min " &
           integer'image(MODEL_MIN_GUARD_PS / 1000) & " ns"
    severity failure;
  assert LEAD * TSYS_PS <= LEAD_MAX_PS and LEAD * TSYS_PS >= LEAD_MIN_PS
    report NAME & ": sample lead outside modeled window"
    severity failure;
  assert LATCH_TICKS * TSYS_PS >= 10_000
    report NAME & ": latch width below '165 floor" severity failure;

  sysclk <= not sysclk after TSYST/2;

  p_reset : process
  begin
    reset_n <= '0';
    wait for 7 * TSYST;
    reset_n <= '1';
    wait;
  end process;

  -- DUT
  u_dut : entity work.scan20_core
    generic map (
      SYS_HZ            => natural(1.0e12 / real(TSYS_PS)), -- doc only
      TICKS_PER_BIT     => TPB,
      TICKS_HIGH        => THI,
      SAMPLE_LEAD_TICKS => LEAD,
      LATCH_TICKS       => LATCH_TICKS,
      GUARD_TICKS       => GUARD_TICKS,
      FRAME_GAP_TICKS   => FGAP_TICKS,
      IDLE_TICKS        => IDLE_TICKS,
      TIMEOUT_TICKS     => TIMEOUT_TICKS,
      RECOVERY_TICKS    => REC_TICKS,
      MAX_TILES         => MAX_TILES,
      COORD_BITS        => 5,
      AUTO_RETRY        => true
    )
    port map (
      sysclk      => sysclk,
      reset_n     => reset_n,
      start       => '0',
      board_clk   => board_clk,
      board_latch => board_latch,
      board_data  => data_drv,
      frame_valid => frame_valid,
      frame_data  => frame_data,
      frame_col   => frame_col,
      frame_row   => frame_row,
      frame_index => frame_index,
      scan_done   => scan_done,
      scan_count  => scan_count,
      busy        => busy,
      err_framing => err_framing,
      err_timeout => err_timeout,
      err_count   => err_count,
      dbg_sample  => dbg_sample,
      dbg_launch  => dbg_launch,
      dbg_state   => dbg_state
    );

  -- controller legs of the chain (same nets as the golden controller)
  hClk(0, 1)   <= board_clk;
  hLatch(0, 1) <= board_latch;
  data_raw     <= hData(0, 1);
  data_drv     <= '0' when inj_on = '1' else to_x01(data_raw);

  -- the tile grid: unmodified fall-snapshot tile FPGA cores
  tiles : for c in 1 to W generate
    rows : for r in 1 to H generate
      has : if present_at(pmap, W, H, c, r) generate
        u_t : entity work.tile_fpga
          generic map (SNAP_MODE => "fall")
          port map (
            buttons  => buttons_for(BMODE, c, r),
            sysclk   => '0',
            T_W      => vW(c, r+1),   T_endcol => vEC(c, r+1),
            T_first  => vFirst(c, r+1), T_latch => vLatch(c, r+1),
            T_clk    => vClk(c, r+1), T_data  => vData(c, r+1),
            B_W      => vW(c, r),     B_endcol => vEC(c, r),
            B_first  => vFirst(c, r), B_latch => vLatch(c, r),
            B_clk    => vClk(c, r),   B_data  => vData(c, r),
            L_endrow => hER(c, r),    L_latch => hLatch(c, r),
            L_clk    => hClk(c, r),   L_data  => hData(c, r),
            R_endrow => hER(c-1, r),  R_latch => hLatch(c-1, r),
            R_clk    => hClk(c-1, r), R_data  => hData(c-1, r)
          );
      end generate;
    end generate;
  end generate;

  ---------------------------------------------------------------------------
  -- monitors + scoreboard (clocked view of the registered DUT outputs)
  ---------------------------------------------------------------------------
  monitor : process
    variable tick        : natural := 0;
    variable ep          : natural := 0;   -- episodes started (latch rises)
    variable ep_launch   : natural := 0;   -- dbg_launch strobes this episode
    variable ep_rise     : natural := 0;   -- board_clk RISING EDGES this episode
    variable ep_sample   : natural := 0;   -- dbg_sample strobes this episode
    variable ep_frames   : natural := 0;   -- frame_valid strobes this episode
    variable fr_launch   : natural := 0;   -- launches in the current frame
    variable f_walk      : natural := 0;   -- expected frame index (0-based)
    variable clean       : natural := 0;
    variable errf_seen   : natural := 0;
    variable errt_seen   : natural := 0;
    variable bclk_d, blatch_d : std_logic := '0';
    variable hi_run, lo_run : natural := 0;
    variable latch_run, latch_lo_run : natural := 0;
    variable quiet_need  : natural := 0;
    variable sample_tick : natural := 0;
    variable pending_sample : boolean := false;
    variable exp_frame   : t_fr;
    variable exp_bit     : std_logic;
    variable bitj        : natural := 0;   -- bit index within frame
    variable cur_frame   : natural := 0;    -- frame index being clocked
    variable abort_checked : boolean := false;

    -- episode-1 store for the latch-reload equality check
    type t_store is array (0 to 31) of std_logic_vector(15 downto 0);
    variable ep1_data    : t_store := (others => (others => '0'));

    impure function done_all return boolean is
    begin
      if EXPECT_TIMEOUTS > 0 then
        return errt_seen >= EXPECT_TIMEOUTS;
      end if;
      return clean >= CLEAN_SCANS;
    end function;

  begin
    wait until rising_edge(sysclk);
    tick := tick + 1;

    -- quiet window after an error
    if quiet_need > 0 then
      assert board_clk = '0' and board_latch = '0'
        report NAME & ": bus not quiet during recovery (" &
               integer'image(quiet_need) & " ticks left)"
        severity failure;
      quiet_need := quiet_need - 1;
    end if;

    -- lead / pairing monitor (C1)
    if dbg_sample = '1' then
      assert not pending_sample
        report NAME & ": two samples without a launch between them"
        severity failure;
      pending_sample := true;
      sample_tick := tick;
      ep_sample := ep_sample + 1;

      -- stream check: expected wire bit (possibly corrupted by injection)
      if cur_frame < nfr then
        exp_bit := FRAMES(cur_frame).wire(bitj);
        if INJ_FRAME >= 0 and ep = INJ_EP and cur_frame = INJ_FRAME and
           (bitj = 12 or bitj = 13) then
          exp_bit := '0';
        end if;
        assert data_drv = exp_bit
          report NAME & ": stream bit " & integer'image(cur_frame) & "." &
                 integer'image(bitj) & " got " & std_logic'image(data_drv) &
                 " expected " & std_logic'image(exp_bit)
          severity failure;
      end if;
      -- advance expected bit pointer
      if bitj = 15 then
        bitj := 0;
      else
        bitj := bitj + 1;
      end if;
    end if;

    if dbg_launch = '1' then
      assert pending_sample
        report NAME & ": launch without a preceding sample"
        severity failure;
      assert tick - sample_tick = LEAD
        report NAME & ": sample->launch lead is " &
               integer'image(tick - sample_tick) & " ticks, expected " &
               integer'image(LEAD)
        severity failure;
      pending_sample := false;
      ep_launch := ep_launch + 1;
      fr_launch := fr_launch + 1;
      assert fr_launch <= 16
        report NAME & ": more than 16 launches in one frame"
        severity failure;
      if ep_launch = 1 then
        -- latch_lo_run has not yet counted this tick: exactly GUARD_TICKS
        -- low ticks between the latch fall and the first launch
        assert latch_lo_run = GUARD_TICKS
          report NAME & ": latch deassert -> first launch is " &
                 integer'image(latch_lo_run) & " ticks, expected " &
                 integer'image(GUARD_TICKS)
          severity failure;
      end if;
    end if;

    -- board_clk duty monitor (C4/C5 halves, tick-domain)
    if board_clk = '1' then
      hi_run := hi_run + 1;
    else
      lo_run := lo_run + 1;
    end if;
    if bclk_d = '0' and board_clk = '1' then           -- rise
      ep_rise := ep_rise + 1;
      lo_run := 0;
    end if;
    if bclk_d = '1' and board_clk = '0' then           -- fall
      -- an abort (error strobe up this tick) truncates this pulse on purpose:
      -- the exact-duty check is skipped for that fall only
      if err_timeout = '0' and err_framing = '0' then
        assert hi_run = THI
          report NAME & ": high phase " & integer'image(hi_run) &
                 " ticks, expected " & integer'image(THI) & " (exact duty)"
          severity failure;
      end if;
      hi_run := 0;
      lo_run := 0;
    end if;

    -- latch monitor (C6): runs after the launch check so latch_lo_run is
    -- the strict count of low ticks since the latch fall
    if blatch_d = '0' and board_latch = '1' then
      ep := ep + 1;
      ep_launch := 0; ep_rise := 0; ep_sample := 0; ep_frames := 0;
      fr_launch := 0; f_walk := 0; bitj := 0; cur_frame := 0;
      -- NOTE: abort_checked is deliberately episode-cumulative (sticky): the
      -- final aggregation checks it AFTER later episodes have run
      latch_run := 1;
      latch_lo_run := 0;
    elsif board_latch = '1' then
      latch_run := latch_run + 1;
    else
      if blatch_d = '1' and board_latch = '0' then
        assert latch_run = LATCH_TICKS
          report NAME & ": latch high for " & integer'image(latch_run) &
                 " ticks, expected " & integer'image(LATCH_TICKS)
          severity failure;
      end if;
      latch_lo_run := latch_lo_run + 1;
    end if;

    -- markers-error injector bookkeeping is in p_inj (async to checks above)

    -- frame completion checks (C2/C3)
    if frame_valid = '1' then
      assert ep >= 1 report NAME & ": frame_valid outside an episode"
        severity failure;
      if INJ_FRAME >= 0 and ep = INJ_EP then
        assert f_walk < INJ_FRAME
          report NAME & ": frame_valid during/after injected frame " &
                 integer'image(INJ_FRAME) & " of episode " &
                 integer'image(ep)
          severity failure;
      end if;
      assert f_walk < nfr
        report NAME & ": more frames than the grid holds"
        severity failure;
      exp_frame := FRAMES(f_walk);
      -- exactly 16 launches AND 16 samples in this frame
      assert fr_launch = 16
        report NAME & ": frame " & integer'image(f_walk) & " completed after " &
               integer'image(fr_launch) & " launches, expected 16"
        severity failure;
      -- 16th pulse completed: clock low for the whole trailing low phase
      assert board_clk = '0' and lo_run >= TPB - THI + 1
        report NAME & ": frame_valid before the 16th pulse completed " &
               "(low run " & integer'image(lo_run) & " ticks)"
        severity failure;
      -- data
      for j in 0 to 15 loop
        assert frame_data(15 - j) = exp_frame.wire(j)
          report NAME & ": frame " & integer'image(f_walk) & " wire bit " &
                 integer'image(j) & " got " &
                 std_logic'image(frame_data(15 - j)) & " expected " &
                 std_logic'image(exp_frame.wire(j))
          severity failure;
      end loop;
      -- coords + index
      assert to_integer(unsigned(frame_col)) = exp_frame.c and
             to_integer(unsigned(frame_row)) = exp_frame.r
        report NAME & ": frame " & integer'image(f_walk) & " at (" &
               integer'image(to_integer(unsigned(frame_col))) & "," &
               integer'image(to_integer(unsigned(frame_row))) & "), expected (" &
               integer'image(exp_frame.c) & "," & integer'image(exp_frame.r) & ")"
        severity failure;
      assert to_integer(unsigned(frame_index)) = f_walk
        report NAME & ": frame_index " &
               integer'image(to_integer(unsigned(frame_index))) &
               " /= walk " & integer'image(f_walk)
        severity failure;
      -- latch-reload equality across episodes
      if ep = 1 then
        ep1_data(f_walk) := frame_data;
      elsif ep = 2 and INJ_FRAME < 0 then
        assert frame_data = ep1_data(f_walk)
          report NAME & ": episode 2 frame " & integer'image(f_walk) &
                 " differs from episode 1 (latch reload)"
          severity failure;
      end if;
      ep_frames := ep_frames + 1;
      f_walk := f_walk + 1;
      cur_frame := cur_frame + 1;
      fr_launch := 0;
    end if;

    -- error strobes
    if err_framing = '1' then
      errf_seen := errf_seen + 1;
      pending_sample := false;  -- aborted episode breaks sample/launch pairing
      -- bus is provably quiet REC_TICKS ticks from the strobe tick on; the
      -- strobe tick itself is quiet (outputs forced low at the abort edge),
      -- and this monitor already sampled it, so guard the REC_TICKS-1 next
      quiet_need := REC_TICKS - 1;
      if INJ_FRAME >= 0 and ep = INJ_EP then
        -- the injected frame must have been FULLY clocked: exactly
        -- 16*(INJ_FRAME+1) edges and samples before the abort
        assert ep_launch = 16 * (INJ_FRAME + 1)
          report NAME & ": aborted episode had " & integer'image(ep_launch) &
                 " launches, expected " & integer'image(16 * (INJ_FRAME + 1))
          severity failure;
        assert ep_sample = 16 * (INJ_FRAME + 1)
          report NAME & ": aborted episode had " & integer'image(ep_sample) &
                 " samples, expected " & integer'image(16 * (INJ_FRAME + 1))
          severity failure;
        assert f_walk = INJ_FRAME
          report NAME & ": framing error at wrong frame"
          severity failure;
        abort_checked := true;
      else
        report NAME & ": UNEXPECTED framing error" severity failure;
      end if;
    end if;

    if err_timeout = '1' then
      errt_seen := errt_seen + 1;
      pending_sample := false;  -- as above: abort breaks the pairing
      quiet_need := REC_TICKS - 1;  -- as above: strobe tick is quiet already
      assert EXPECT_TIMEOUTS > 0
        report NAME & ": UNEXPECTED timeout" severity failure;
    end if;

    if scan_done = '1' then
      assert EXPECT_TIMEOUTS = 0
        report NAME & ": scan completed in timeout mode" severity failure;
      assert ep_frames = nfr
        report NAME & ": clean episode had " & integer'image(ep_frames) &
               " frames, expected " & integer'image(nfr)
        severity failure;
      assert ep_launch = 16 * nfr
        report NAME & ": clean episode had " & integer'image(ep_launch) &
               " launches, expected " & integer'image(16 * nfr)
        severity failure;
      assert ep_rise = 16 * nfr
        report NAME & ": clean episode had " & integer'image(ep_rise) &
               " board_clk rising edges, expected " & integer'image(16 * nfr) &
               " (extra/missing edges)"
        severity failure;
      assert ep_sample = 16 * nfr
        report NAME & ": clean episode had " & integer'image(ep_sample) &
               " samples, expected " & integer'image(16 * nfr)
        severity failure;
      assert errf_seen = 0 or INJ_FRAME >= 0
        report NAME & ": framing error without injection" severity failure;
      clean := clean + 1;
    end if;

    -- global: edge counter may never exceed launch strobe count + past eps
    assert ep_rise <= ep_launch
      report NAME & ": more board_clk rising edges than launches (glitch)"
      severity failure;
    assert ep_rise = ep_launch
      report NAME & ": board_clk rising edges /= launches (extra edges)"
      severity failure;

    bclk_d := board_clk;
    blatch_d := board_latch;

    if done_all then
      -- final aggregates
      if INJ_FRAME >= 0 then
        assert errf_seen >= 1
          report NAME & ": expected the injected framing error" severity failure;
        assert abort_checked
          report NAME & ": injected-abort accounting never checked" severity failure;
      else
        assert errf_seen = 0
          report NAME & ": unexpected framing errors" severity failure;
      end if;
      if EXPECT_TIMEOUTS = 0 then
        assert errt_seen = 0
          report NAME & ": unexpected timeouts" severity failure;
        assert err_count = std_logic_vector(to_unsigned(errf_seen + errt_seen, 8))
          report NAME & ": err_count accounting mismatch" severity failure;
      else
        assert clean = 0
          report NAME & ": timeout mode must not produce clean scans"
          severity failure;
      end if;
      report "SCAN20SUMMARY " & NAME & " episodes=" & integer'image(ep) &
             " clean=" & integer'image(clean) &
             " errf=" & integer'image(errf_seen) &
             " errt=" & integer'image(errt_seen);
      report "SCAN20PASS " & NAME;
      stop(0);
    end if;
  end process monitor;

  ---------------------------------------------------------------------------
  -- runt/glitch monitor (async, time-domain): any toggle spacing must be at
  -- least one full sysclk period and every high phase exactly THI x TSYS.
  -- Falls coincident with an error strobe are the abort path truncating a
  -- pulse on purpose (watchdog/framing abort): exempt, and re-armed after.
  ---------------------------------------------------------------------------
  glitch : process(board_clk)
    variable last_edge : time := 0 ns;
    variable rise_t    : time := 0 ns;
  begin
    if board_clk'event then
      if last_edge /= 0 ns then
        assert now - last_edge >= TSYST - 200 ps
          report NAME & ": runt BOARD_CLK edge: spacing " &
                 time'image(now - last_edge) & " < one sysclk period"
          severity failure;
      end if;
      if board_clk = '1' then
        rise_t := now;
      else
        if rise_t /= 0 ns and err_timeout = '0' and err_framing = '0' then
          assert now - rise_t = THI * TSYST
            report NAME & ": high phase is " & time'image(now - rise_t) &
                   ", expected exactly " & integer'image(THI) & " x " &
                   time'image(TSYST)
            severity failure;
        end if;
        rise_t := 0 ns;  -- abort-truncated falls (error strobe up) are exempt
      end if;
      last_edge := now;
    end if;
  end process glitch;

  ---------------------------------------------------------------------------
  -- marker-error injection (C8): force the controller-visible data low
  -- around the marker bits of frame INJ_FRAME during episode INJ_EP.
  -- Windows are opened/closed >= 4 ticks away from any other sample.
  ---------------------------------------------------------------------------
  p_inj : process(sysclk)
    variable ep        : natural := 0;
    variable sc_ep     : natural := 0;   -- dbg_sample count in the episode
    variable blatch_d  : std_logic := '0';
  begin
    if rising_edge(sysclk) then
      if blatch_d = '0' and board_latch = '1' then
        ep := ep + 1;
        sc_ep := 0;
      elsif dbg_sample = '1' then
        sc_ep := sc_ep + 1;
      end if;
      blatch_d := board_latch;
      if INJ_FRAME >= 0 and ep = INJ_EP and
         sc_ep >= INJ_FRAME * 16 + 12 and sc_ep < INJ_FRAME * 16 + 14 then
        inj_on <= '1';
      else
        inj_on <= '0';
      end if;
    end if;
  end process p_inj;

end sim;
