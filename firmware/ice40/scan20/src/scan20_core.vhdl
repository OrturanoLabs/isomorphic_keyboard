-- SPDX-License-Identifier: GPL-3.0-only
--
-- scan20_core: isolated 20 MHz 16-tile scan frontend / test engine for the
-- isomorphic keyboard tile chain. This is a TEST FIXTURE for bring-up of the
-- 20 MHz link timing: it scans the chain, walks the grid, and exposes every
-- frame plus observability strobes. It is NOT a MIDI-capable drop-in
-- replacement for firmware/ice40/src/top.vhd (the golden controller, which
-- stays untouched).
--
-- Kept from the golden controller (docs/architecture/protocol.md):
--   * 16-bit frame, keys msb-first; after 16 samples shreg(15) = first wire
--     bit, shreg(3)/shreg(2) = markers, shreg(1) = L_endrow, shreg(0) =
--     T_endcol (shreg <= shreg(14 downto 0) & data per sample, as golden);
--   * sample-before-shift: each bit is sampled BEFORE the shift clock edge
--     that advances the chain past it;
--   * grid walk: columns right-to-left (col 1 at the controller), tiles of a
--     column bottom-up (row 1 at the bottom);
--   * framing error when markers /= "11".
--
-- Deliberate deviations from the golden controller:
--   * sysclk-tick engine: TICKS_PER_BIT sysclk ticks per shifted bit, of
--     which TICKS_HIGH high (60 MHz: 3 ticks, 2 high + 1 low => 33.33/16.67
--     ns, 20.000 MHz shift; 120 MHz: 6 ticks, 4 high + 2 low, same phases);
--   * SAMPLE_LEAD_TICKS (default 1): BOARD_DATA is registered exactly this
--     many sysclk edges BEFORE the edge that launches the next clock pulse
--     -> one full sysclk period of input hold guard against the launch;
--   * coordinates widened to COORD_BITS >= 5 per axis (golden: 3) so a
--     16-tall column (up to 32) is representable;
--   * error RECOVERY instead of the golden sticky state: framing error,
--     frame-count cap overflow or watchdog abort parks the bus quiet for
--     >= RECOVERY_TICKS and starts a fresh episode (AUTO_RETRY) or waits in
--     HALT for a start rising edge / reset (not AUTO_RETRY);
--   * hard timeout watchdog (TIMEOUT_TICKS per episode, 8-tick quantised)
--     so a broken chain can never wedge the scanner.
--
-- Timing closure style (UP5K): every state-exit and every mid-state event
-- (fall edge, sample point) is driven by a REGISTERED one-tick-early "arm"
-- flag set from (state, ph = K-2), so no FF's data/enable cone is deeper
-- than state_bit AND arm_bit; the board pins themselves stay registered
-- (each BOARD_CLK/BOARD_LATCH edge is one FF) and every observable count
-- (latch width, guard, duty, gap, sample-lead) is tick-identical to the
-- direct-compare formulation. Long waits (IDLE/RECOVERY/TIMEOUT) use the
-- PRE_SCALE=8 prescaler; idle rounds up to a 2048-tick coarse wrap
-- (>= IDLE_TICKS), recovery lasts RECOVERY_TICKS+1..+9 ticks (always
-- >= RECOVERY_TICKS), the watchdog quantises on the 8-tick grid.
--
-- Tick schedule (registered outputs only; every BOARD_CLK/BOARD_LATCH edge
-- comes from these FFs and lands exactly on a sysclk edge):
--   episode   = ST_LATCH (LATCH_TICKS high) -> ST_GUARD (GUARD_TICKS)
--   bit pulse = TICKS_PER_BIT ticks: high during ticks 0..TICKS_HIGH-1,
--               low the rest; launch = register edge entering tick 0
--   sample    = evaluated at tick TICKS_PER_BIT-1-SAMPLE_LEAD_TICKS, so the
--               shreg shifts exactly SAMPLE_LEAD_TICKS sysclk edges before
--               the edge that launches the next pulse (bit 1 of a frame is
--               sampled equivalently in ST_GUARD / ST_GAP)
--   frame     = after the 16th pulse's FULL TICKS_PER_BIT ticks elapse;
--               ST_FRAME (1) + ST_GAP (FRAME_GAP_TICKS) sit between the
--               16th pulse and the next frame's first launch
-- Guarantees (structural; checked by sim/scan20_tb.vhdl):
--   * every high phase is exactly TICKS_HIGH sysclk ticks, every low phase
--     an exact tick count; no combinational path to either pin;
--   * the 16th shift pulse always completes before FRAME work / frame_valid;
--   * exactly one sample per planned launch, SAMPLE_LEAD_TICKS before it;
--   * exactly 16 launches per frame.
--
-- BOARD_DATA is sampled directly (no synchroniser): it only changes after
-- our own launches, so it is stable around every sample point by
-- construction (metastability note in the README). reset_n is synchronous,
-- matching the golden style.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity scan20_core is
  generic (
    SYS_HZ            : natural := 60_000_000; -- documentation only
    TICKS_PER_BIT     : natural := 3;   -- sysclk ticks per shifted bit
    TICKS_HIGH        : natural := 2;   -- high ticks of each pulse
    SAMPLE_LEAD_TICKS : natural := 1;   -- sample this many ticks before launch
    LATCH_TICKS       : natural := 60;  -- latch high width (1.0 us @ 60 MHz)
    GUARD_TICKS       : natural := 4;   -- latch deassert -> first launch
    FRAME_GAP_TICKS   : natural := 3;   -- low ticks between frames
    IDLE_TICKS        : natural := 30_000; -- gap between episodes (rounded up
                                        -- to a 2048-tick coarse wrap)
    TIMEOUT_TICKS     : natural := 8192;   -- hard watchdog per episode, %8=0
    RECOVERY_TICKS    : natural := 120;    -- quiet bus after an error, %8=0
    MAX_TILES         : natural := 16;     -- frames/episode safety cap
    COORD_BITS        : natural := 5;      -- >= 5 (16-tall columns!)
    AUTO_RETRY        : boolean := true    -- recover+rescan on error
  );
  port (
    sysclk   : in  std_logic;
    reset_n  : in  std_logic;
    start    : in  std_logic := '0';  -- rising edge re-kicks a HALTed engine

    board_clk   : out std_logic;
    board_latch : out std_logic;
    board_data  : in  std_logic;

    -- per-frame test-engine outputs (valid with the 1-tick frame_valid strobe)
    frame_valid : out std_logic;
    frame_data  : out std_logic_vector(15 downto 0);
    frame_col   : out std_logic_vector(COORD_BITS-1 downto 0);
    frame_row   : out std_logic_vector(COORD_BITS-1 downto 0);
    frame_index : out std_logic_vector(4 downto 0); -- 0-based within episode

    scan_done  : out std_logic;  -- 1-tick strobe: episode completed cleanly
    scan_count : out std_logic_vector(15 downto 0); -- clean episodes so far
    busy       : out std_logic;  -- registered decode of episode-active states
                                 -- (lags state entry/exit by 1 sysclk tick)

    err_framing : out std_logic; -- 1-tick strobe on bad markers / cap overflow
    err_timeout : out std_logic; -- 1-tick strobe on watchdog bite
    err_count   : out std_logic_vector(7 downto 0); -- saturating error total

    -- observability strobes for the testbench (all exactly 1 sysclk tick)
    dbg_sample : out std_logic; -- board_data was registered this tick
    dbg_launch : out std_logic; -- board_clk 0->1 launched this tick
    dbg_state  : out std_logic_vector(3 downto 0)
  );
end scan20_core;

architecture rtl of scan20_core is

  constant TICKS_LOW : natural := TICKS_PER_BIT - TICKS_HIGH;

  type state_t is (
    ST_IDLE,      -- x0: quiet, first episode starts immediately (auto-run)
    ST_LATCH,     -- x1: latch high, tiles parallel-load
    ST_GUARD,     -- x2: latch fell; settle; frame 1 bit 1 sampled here
    ST_BIT,       -- x3: one shift pulse in flight (tick-phased)
    ST_FRAME,     -- x4: 16th pulse complete; outcome registered (1 tick)
    ST_ACT,       -- xA: frame_valid + coordinate walk / done / abort
    ST_GAP,       -- x5: inter-frame low gap; next frame's bit 1 sampled here
    ST_DONE,      -- x6: scan_done strobe
    ST_IDLEGAP,   -- x7: between episodes (coarse prescaled, >= IDLE_TICKS)
    ST_RECOVERY,  -- x8: quiet bus after an error (prescaled, >= RECOVERY)
    ST_HALT       -- x9: not AUTO_RETRY: waits for start rising edge / reset
  );

  function max2(a : natural; b : natural) return natural is
  begin
    if a > b then return a; else return b; end if;
  end function;

  -- fine prescaler: long waits are counted in 8-tick / 2048-tick units
  constant PRE_SCALE  : natural := 8;
  constant TMO_PS     : natural := TIMEOUT_TICKS / PRE_SCALE;
  constant REC_PS     : natural := RECOVERY_TICKS / PRE_SCALE;
  constant COARSE     : natural := 256;                -- 8 * 256 = 2048 ticks
  constant IDLE_WRAPS : natural := (IDLE_TICKS + PRE_SCALE * COARSE - 1) /
                                   (PRE_SCALE * COARSE); -- ceil, >= 1

  -- ph only counts TICK-EXACT phases (latch/guard/bit/gap widths)
  constant PH_MAX : natural :=
    max2(LATCH_TICKS, max2(GUARD_TICKS, max2(TICKS_PER_BIT, FRAME_GAP_TICKS)));

  signal state   : state_t := ST_IDLE;
  signal ph      : natural range 0 to PH_MAX := 0; -- ticks spent in state
  signal bit_cnt : natural range 0 to 16 := 0;     -- launched pulses so far
  signal shreg   : std_logic_vector(15 downto 0) := (others => '0');

  signal col, row : unsigned(COORD_BITS-1 downto 0) := (others => '0');
  signal another  : std_logic := '0';
  signal fidx     : unsigned(4 downto 0) := (others => '0');

  -- 1-tick-early registered event arms (state-tagged, self-clearing)
  signal arm_latch : std_logic := '0'; -- exit ST_LATCH (fall board_latch)
  signal arm_g_smp : std_logic := '0'; -- sample in ST_GUARD
  signal arm_g_ext : std_logic := '0'; -- exit ST_GUARD (first launch)
  signal arm_fall  : std_logic := '0'; -- mid-pulse fall in ST_BIT
  signal arm_b_smp : std_logic := '0'; -- sample in ST_BIT
  signal arm_b_ext : std_logic := '0'; -- pulse end in ST_BIT (launch/exit)
  signal arm_p_smp : std_logic := '0'; -- sample in ST_GAP
  signal arm_p_ext : std_logic := '0'; -- exit ST_GAP (next frame launch)
  signal arm_idle  : std_logic := '0'; -- exit ST_IDLEGAP (prescaled)
  signal arm_rec   : std_logic := '0'; -- exit ST_RECOVERY (prescaled)
  signal arm_wd    : std_logic := '0'; -- watchdog bite (registered abort)

  -- frame-input snapshot: shreg bits registered at the 16th pulse's exit
  -- tick, so ST_FRAME decisions see FF outputs only (timing closure)
  signal fr_ok   : std_logic := '0'; -- markers == "11"
  signal fr_top  : std_logic := '0'; -- shreg(0): T_endcol (top of column)
  signal fr_lend : std_logic := '0'; -- shreg(1): L_endrow

  -- per-frame outcome: registered in ST_FRAME (FF-only fanin there), acted
  -- on in ST_ACT (second tick of the frame work; the 16th pulse is already
  -- complete, so the extra tick is invisible to the chain)
  signal out_frm  : std_logic := '0'; -- framing abort (bad markers)
  signal out_done : std_logic := '0'; -- whole grid read
  signal out_next : std_logic := '0'; -- advance to next frame
  signal out_cap  : std_logic := '0'; -- MAX_TILES cap overflow
  signal fr_another_in : std_logic := '0'; -- v_another for this frame

  signal ps_fine : natural range 0 to PRE_SCALE-1 := 0; -- free-running /8 tick
  signal wd_ps   : natural range 0 to TMO_PS := 0;   -- watchdog, 8-tick units
  signal rec_w   : natural range 0 to REC_PS := 0;   -- recovery, 8-tick units
  signal ps_c    : natural range 0 to COARSE-1 := 0; -- idle coarse, 8-tick
  signal idle_w  : natural range 0 to IDLE_WRAPS := 0; -- idle, 2048-tick units
  signal scans   : unsigned(15 downto 0) := (others => '0');
  signal errors  : unsigned(7 downto 0) := (others => '0');
  signal start_d : std_logic := '0';

begin

  -- configuration sanity (elaboration-time; simulation severity failure)
  assert TICKS_HIGH >= 2
    report "scan20: TICKS_HIGH must be >= 2 (armed fall edge)" severity failure;
  assert TICKS_LOW >= 1
    report "scan20: TICKS_PER_BIT-TICKS_HIGH must be >= 1" severity failure;
  assert SAMPLE_LEAD_TICKS >= 1
    report "scan20: SAMPLE_LEAD_TICKS must be >= 1" severity failure;
  assert SAMPLE_LEAD_TICKS <= TICKS_PER_BIT - 2
    report "scan20: lead must leave >= 1 launch tick before the sample" severity failure;
  assert SAMPLE_LEAD_TICKS <= GUARD_TICKS - 2
    report "scan20: lead must fit in GUARD_TICKS before the first launch" severity failure;
  assert SAMPLE_LEAD_TICKS <= FRAME_GAP_TICKS - 2
    report "scan20: lead must fit in FRAME_GAP_TICKS before the frame launch" severity failure;
  assert LATCH_TICKS >= 2
    report "scan20: LATCH_TICKS must be >= 2 (armed exit)" severity failure;
  assert IDLE_TICKS >= 1 and RECOVERY_TICKS >= 1
    report "scan20: IDLE/RECOVERY_TICKS must be >= 1" severity failure;
  assert TIMEOUT_TICKS mod PRE_SCALE = 0
    report "scan20: TIMEOUT_TICKS must be a multiple of 8 (prescaled)" severity failure;
  assert RECOVERY_TICKS mod PRE_SCALE = 0
    report "scan20: RECOVERY_TICKS must be a multiple of 8 (prescaled)" severity failure;
  assert TMO_PS >= 2 and REC_PS >= 1
    report "scan20: prescaled TIMEOUT/RECOVERY must be >= 2 / >= 1" severity failure;
  assert MAX_TILES >= 1 and MAX_TILES <= 31
    report "scan20: MAX_TILES out of range (frame_index is 5 bits)" severity failure;
  assert COORD_BITS >= 5
    report "scan20: COORD_BITS must be >= 5 (16-tall columns)" severity failure;

  ----------------------------------------------------------------------------
  -- arming network: all flags set one tick early from (state, ph); each is
  -- a dedicated small cone into its own FF. All flags decay automatically
  -- once their state is left.
  ----------------------------------------------------------------------------
  p_arms : process(sysclk)
    variable v_episode : boolean;
  begin
    if rising_edge(sysclk) then
      if reset_n = '0' then
        arm_latch <= '0';
        arm_g_smp <= '0';
        arm_g_ext <= '0';
        arm_fall  <= '0';
        arm_b_smp <= '0';
        arm_b_ext <= '0';
        arm_p_smp <= '0';
        arm_p_ext <= '0';
        arm_idle  <= '0';
        arm_rec   <= '0';
        arm_wd    <= '0';
      else
        v_episode := (state = ST_LATCH or state = ST_GUARD or
                      state = ST_BIT or state = ST_FRAME or state = ST_ACT or state = ST_GAP);

        if state = ST_LATCH    and ph = LATCH_TICKS - 2 then
          arm_latch <= '1'; else arm_latch <= '0'; end if;
        if state = ST_GUARD    and ph = GUARD_TICKS - 2 - SAMPLE_LEAD_TICKS then
          arm_g_smp <= '1'; else arm_g_smp <= '0'; end if;
        if state = ST_GUARD    and ph = GUARD_TICKS - 2 then
          arm_g_ext <= '1'; else arm_g_ext <= '0'; end if;
        if state = ST_BIT      and ph = TICKS_HIGH - 2 then
          arm_fall  <= '1'; else arm_fall  <= '0'; end if;
        if state = ST_BIT      and ph = TICKS_PER_BIT - 2 - SAMPLE_LEAD_TICKS
                               and bit_cnt < 16 then
          arm_b_smp <= '1'; else arm_b_smp <= '0'; end if;
        if state = ST_BIT      and ph = TICKS_PER_BIT - 2 then
          arm_b_ext <= '1'; else arm_b_ext <= '0'; end if;
        if state = ST_GAP      and ph = FRAME_GAP_TICKS - 2 - SAMPLE_LEAD_TICKS then
          arm_p_smp <= '1'; else arm_p_smp <= '0'; end if;
        if state = ST_GAP      and ph = FRAME_GAP_TICKS - 2 then
          arm_p_ext <= '1'; else arm_p_ext <= '0'; end if;

        -- watchdog arm: bite one tick after the wrap that reaches the cap
        if v_episode and ps_fine = PRE_SCALE - 1 and wd_ps = TMO_PS - 1 then
          arm_wd <= '1';
        else
          arm_wd <= '0';
        end if;

        -- prescaled idle/recovery exits: arm on the wrap AFTER the last
        -- counted one, so recovery lasts >= RECOVERY_TICKS+2 sysclk ticks
        -- (regardless of the 8-tick phase of strobe vs prescaler)
        if state = ST_IDLEGAP and ps_fine = PRE_SCALE - 1 and
           ps_c = COARSE - 1 and idle_w = IDLE_WRAPS - 1 then
          arm_idle <= '1'; else arm_idle <= '0'; end if;
        if state = ST_RECOVERY and ps_fine = PRE_SCALE - 1 and
           rec_w = REC_PS then
          arm_rec <= '1'; else arm_rec <= '0'; end if;
      end if;
    end if;
  end process p_arms;

  ----------------------------------------------------------------------------
  -- free-running prescaler + long-wait counters (never on a fast FF fanin)
  ----------------------------------------------------------------------------
  p_pre : process(sysclk)
    variable v_episode : boolean;
  begin
    if rising_edge(sysclk) then
      if reset_n = '0' then
        ps_fine <= 0;
        wd_ps   <= 0;
        rec_w   <= 0;
        ps_c    <= 0;
        idle_w  <= 0;
      else
        v_episode := (state = ST_LATCH or state = ST_GUARD or
                      state = ST_BIT or state = ST_FRAME or state = ST_ACT or state = ST_GAP);
        if ps_fine = PRE_SCALE - 1 then
          ps_fine <= 0;
          if v_episode and wd_ps < TMO_PS then
            wd_ps <= wd_ps + 1;
          end if;
          if state = ST_RECOVERY and rec_w < REC_PS then
            rec_w <= rec_w + 1;
          end if;
          if state = ST_IDLEGAP then
            if ps_c = COARSE - 1 then
              ps_c <= 0;
              if idle_w < IDLE_WRAPS then
                idle_w <= idle_w + 1;
              end if;
            else
              ps_c <= ps_c + 1;
            end if;
          end if;
        else
          ps_fine <= ps_fine + 1;
        end if;
        -- counters are re-based on entering their state (see main FSM)
        if state /= ST_RECOVERY then rec_w <= 0; end if;
        if state /= ST_IDLEGAP  then ps_c <= 0; idle_w <= 0; end if;
        if not v_episode        then wd_ps <= 0; end if;
      end if;
    end if;
  end process p_pre;

  ----------------------------------------------------------------------------
  -- frame-input snapshot: at the 16th pulse's exit tick the shifted word is
  -- complete (16th sample landed earlier in that pulse); register the three
  -- decision bits + marker check so ST_FRAME fans from FFs only.
  ----------------------------------------------------------------------------
  p_frame_bits : process(sysclk)
  begin
    if rising_edge(sysclk) then
      if reset_n = '0' then
        fr_ok   <= '0';
        fr_top  <= '0';
        fr_lend <= '0';
      elsif state = ST_BIT and arm_b_ext = '1' and bit_cnt = 16 then
        fr_ok   <= shreg(3) and shreg(2);
        fr_top  <= shreg(0);
        fr_lend <= shreg(1);
      end if;
    end if;
  end process p_frame_bits;

  ----------------------------------------------------------------------------
  -- main FSM: transition/event conditions are (state AND arm) 2-input terms
  ----------------------------------------------------------------------------
  main : process(sysclk)
    variable v_another : std_logic;
    variable v_done    : boolean;
    variable v_kick    : boolean;
  begin
    if rising_edge(sysclk) then
      if reset_n = '0' then
        state       <= ST_IDLE;
        ph          <= 0;
        bit_cnt     <= 0;
        shreg       <= (others => '0');
        col         <= (others => '0');
        row         <= (others => '0');
        another     <= '0';
        fidx        <= (others => '0');
        scans       <= (others => '0');
        errors      <= (others => '0');
        start_d     <= '0';

        board_clk   <= '0';
        board_latch <= '0';
        frame_valid <= '0';
        frame_data  <= (others => '0');
        frame_col   <= (others => '0');
        frame_row   <= (others => '0');
        frame_index <= (others => '0');
        scan_done   <= '0';
        scan_count  <= (others => '0');
        err_framing <= '0';
        err_timeout <= '0';
        err_count   <= (others => '0');
        dbg_sample  <= '0';
        dbg_launch  <= '0';
        dbg_state   <= x"0";
      else
        -- defaults: all strobes are exactly one tick
        frame_valid <= '0';
        scan_done   <= '0';
        err_framing <= '0';
        err_timeout <= '0';
        dbg_sample  <= '0';
        dbg_launch  <= '0';
        start_d     <= start;
        v_kick := (start = '1' and start_d = '0');

        if arm_wd = '1' then
          -- registered watchdog bite: abort from any episode state
          state       <= ST_RECOVERY;
          ph          <= 0;
          board_clk   <= '0';
          board_latch <= '0';
          err_timeout <= '1';
          if errors < 255 then
            errors    <= errors + 1;
            err_count <= std_logic_vector(errors + 1);
          else
            err_count <= std_logic_vector(errors);
          end if;
          dbg_state   <= x"8";
        else
          case state is
            when ST_IDLE =>
              dbg_state <= x"0";
              -- auto-run like the golden controller: the first episode
              -- starts right after reset
              state       <= ST_LATCH;
              ph          <= 0;
              bit_cnt     <= 0;
              col         <= to_unsigned(1, COORD_BITS);
              row         <= to_unsigned(1, COORD_BITS);
              fidx        <= (others => '0');
              another     <= '0';
              board_latch <= '1';
              dbg_state   <= x"1";

            when ST_LATCH =>
              dbg_state <= x"1";
              if arm_latch = '1' then
                board_latch <= '0';
                ph          <= 0;
                state       <= ST_GUARD;
                dbg_state   <= x"2";
              else
                ph <= ph + 1;
              end if;

            when ST_GUARD =>
              dbg_state <= x"2";
              -- bit 1 of frame 1 is on the wire since the latch; sample it
              -- SAMPLE_LEAD_TICKS sysclk edges before the first launch
              if arm_g_smp = '1' then
                shreg      <= shreg(14 downto 0) & board_data;
                dbg_sample <= '1';
              end if;
              if arm_g_ext = '1' then
                board_clk  <= '1';
                dbg_launch <= '1';
                bit_cnt    <= 1;
                ph         <= 0;
                state      <= ST_BIT;
                dbg_state  <= x"3";
              else
                ph <= ph + 1;
              end if;

            when ST_BIT =>
              dbg_state <= x"3";
              -- fall edge: high phase is ticks 0..TICKS_HIGH-1
              if arm_fall = '1' then
                board_clk <= '0';
              end if;
              -- next bit: sampled SAMPLE_LEAD_TICKS edges before the next
              -- launch (never on the 16th pulse: bit 17 belongs to the next
              -- frame and is sampled in ST_GAP)
              if arm_b_smp = '1' then
                shreg      <= shreg(14 downto 0) & board_data;
                dbg_sample <= '1';
              end if;
              if arm_b_ext = '1' then
                -- this pulse is COMPLETE: all TICKS_PER_BIT ticks elapsed
                if bit_cnt = 16 then
                  ph        <= 0;
                  state     <= ST_FRAME;
                  dbg_state <= x"4";
                else
                  board_clk  <= '1';   -- launch of pulse bit_cnt+1
                  dbg_launch <= '1';
                  bit_cnt    <= bit_cnt + 1;
                  ph         <= 0;
                end if;
              else
                ph <= ph + 1;
              end if;

            when ST_FRAME =>
              dbg_state <= x"4";
              -- the 16th pulse is fully complete here by construction.
              -- decision inputs are FFs only (p_frame_bits); register the
              -- outcome, act next tick in ST_ACT. Order of the old single-
              -- tick block is preserved (markers -> done -> cap -> next).
              v_another := another or (not fr_lend);
              fr_another_in <= v_another;
              out_frm  <= not fr_ok;
              out_done <= '0';
              out_next <= '0';
              out_cap  <= '0';
              if fr_ok = '1' then
                if fr_top = '1' and v_another = '0' then
                  out_done <= '1';            -- whole grid read
                elsif fidx = MAX_TILES - 1 then
                  out_cap  <= '1';            -- frame-count cap overflow
                else
                  out_next <= '1';            -- advance to next frame
                end if;
              end if;
              state    <= ST_ACT;
              dbg_state <= x"A";

            when ST_ACT =>
              dbg_state <= x"A";
              if out_frm = '1' then
                -- framing error: abort the episode, recover quietly
                state       <= ST_RECOVERY;
                ph          <= 0;
                board_clk   <= '0';
                err_framing <= '1';
                if errors < 255 then
                  errors    <= errors + 1;
                  err_count <= std_logic_vector(errors + 1);
                else
                  err_count <= std_logic_vector(errors);
                end if;
                dbg_state   <= x"8";
              elsif out_done = '1' then
                frame_valid <= '1';
                frame_data  <= shreg;
                frame_col   <= std_logic_vector(col);
                frame_row   <= std_logic_vector(row);
                frame_index <= std_logic_vector(fidx);
                state     <= ST_DONE;
                dbg_state <= x"6";
              elsif out_cap = '1' then
                -- frame-count cap: chain longer than MAX_TILES = broken;
                -- the capped frame itself is still reported (as before)
                frame_valid <= '1';
                frame_data  <= shreg;
                frame_col   <= std_logic_vector(col);
                frame_row   <= std_logic_vector(row);
                frame_index <= std_logic_vector(fidx);
                state       <= ST_RECOVERY;
                ph          <= 0;
                board_clk   <= '0';
                err_framing <= '1';
                if errors < 255 then
                  errors    <= errors + 1;
                  err_count <= std_logic_vector(errors + 1);
                else
                  err_count <= std_logic_vector(errors);
                end if;
                dbg_state   <= x"8";
              else
                -- out_next: report the frame, then walk the grid
                frame_valid <= '1';
                frame_data  <= shreg;
                frame_col   <= std_logic_vector(col);
                frame_row   <= std_logic_vector(row);
                frame_index <= std_logic_vector(fidx);
                if fr_top = '1' then            -- top of column just read
                  col     <= col + 1;
                  row     <= to_unsigned(1, COORD_BITS);
                  another <= '0';
                else
                  row     <= row + 1;
                  another <= fr_another_in;
                end if;
                fidx      <= fidx + 1;
                bit_cnt   <= 0;
                ph        <= 0;
                state     <= ST_GAP;
                dbg_state <= x"5";
              end if;

            when ST_GAP =>
              dbg_state <= x"5";
              -- bit 1 of the NEXT frame was put on the wire by the 16th
              -- launch; sample it SAMPLE_LEAD_TICKS before the next launch
              if arm_p_smp = '1' then
                shreg      <= shreg(14 downto 0) & board_data;
                dbg_sample <= '1';
              end if;
              if arm_p_ext = '1' then
                board_clk  <= '1';
                dbg_launch <= '1';
                bit_cnt    <= 1;
                ph         <= 0;
                state      <= ST_BIT;
                dbg_state  <= x"3";
              else
                ph <= ph + 1;
              end if;

            when ST_DONE =>
              dbg_state  <= x"6";
              scan_done  <= '1';
              scans      <= scans + 1;
              scan_count <= std_logic_vector(scans + 1);
              state      <= ST_IDLEGAP;

            when ST_IDLEGAP =>
              dbg_state <= x"7";
              if arm_idle = '1' then
                -- hop through ST_IDLE (1-tick auto-forward) so the only
                -- fanin of "enter ST_LATCH" is state = ST_IDLE (timing)
                state     <= ST_IDLE;
                dbg_state <= x"0";
              end if;

            when ST_RECOVERY =>
              dbg_state <= x"8";
              if arm_rec = '1' then
                if AUTO_RETRY then
                  state     <= ST_IDLE;   -- fresh episode (hop via ST_IDLE)
                  dbg_state <= x"0";
                else
                  state     <= ST_HALT;
                  dbg_state <= x"9";
                end if;
              end if;

            when ST_HALT =>
              dbg_state <= x"9";
              if v_kick then
                state     <= ST_IDLE;
                dbg_state <= x"0";
              end if;
          end case;
        end if;
      end if;
    end if;
  end process;

  ----------------------------------------------------------------------------
  -- busy: registered decode of the episode states (lags state entry by one
  -- sysclk tick; identical width otherwise). Keeping it a decode instead of
  -- set/clear assignments keeps every FF's cone tiny (UP5K timing).
  ----------------------------------------------------------------------------
  p_busy : process(sysclk)
  begin
    if rising_edge(sysclk) then
      if reset_n = '0' then
        busy <= '0';
      elsif state = ST_LATCH or state = ST_GUARD or state = ST_BIT or
            state = ST_FRAME or state = ST_ACT or state = ST_GAP then
        busy <= '1';
      else
        busy <= '0';
      end if;
    end if;
  end process p_busy;

end rtl;
