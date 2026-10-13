-- SPDX-License-Identifier: GPL-3.0-only
--
-- scan20_top: standalone iCE40UP5K (pico-ice pins) wrapper of the scan20
-- test engine. 12 MHz board oscillator -> SB_PLL40_PAD -> sysclk (config
-- f100: 100.5 MHz / f120: 120.0 MHz / f60: 60.0 MHz, all verified vs
-- icepll; run_synth.sh picks per config), core held in reset until PLL
-- LOCK. This is a BRING-UP TEST FIXTURE: it reuses the golden pinout
-- (firmware/ice40/constraints/up5k.pcf mapping, copied into
-- synth/scan20_up5k.pcf) and drives only the scan pins + LEDs.
-- PACKAGE_MIDI is driven to the golden UART idle level ('0' after the
-- golden's inversion) so the MIDI leg stays quiet; no MIDI here.
--
-- LEDs (pico-ice active-low, mirroring golden polarity):
--   LED_RED    '0' = an error has been seen since reset (sticky leg)
--   LED_GREEN  '0' = scan episode busy
--   LED_BLUE   '0' = at least one clean episode completed (scan_done seen)
--
-- Interior static timing ONLY: Fmax/Fmin numbers from nextpnr/icetime are
-- reported for the fabric; the external chain (cables, '165s, connectors)
-- is NOT closed by this build -- see README/RESULTS.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity scan20_top is
  generic (
    -- PLL: 12 MHz -> SYS. (DIVR, DIVF, DIVQ) verified by icepll:
    --   100.000 MHz infeasible; nearest 100.5: DIVF=66 DIVQ=3 (VCO 804 MHz)
    --   120.0 MHz exact:                    DIVF=79 DIVQ=3 (VCO 960 MHz)
    --    60.0 MHz exact:                    DIVF=79 DIVQ=4 (VCO 960 MHz)
    PLL_DIVF        : natural := 79;
    PLL_DIVQ        : natural := 4;
    SYS_HZ          : natural := 60_000_000; -- documentation only
    TICKS_PER_BIT   : natural := 3;
    TICKS_HIGH      : natural := 2;
    SAMPLE_LEAD_TICKS : natural := 1;
    LATCH_TICKS     : natural := 60;      -- 1.0 us @ 60 MHz
    GUARD_TICKS     : natural := 4;       -- 66.7 ns (>= model 15 ns)
    FRAME_GAP_TICKS : natural := 3;       -- 1 bit period
    IDLE_TICKS      : natural := 30_000;  -- 0.5 ms @ 60 MHz
    TIMEOUT_TICKS   : natural := 8192;
    RECOVERY_TICKS  : natural := 120;     -- 2.0 us
    MAX_TILES       : natural := 16;
    COORD_BITS      : natural := 5;
    AUTO_RETRY      : boolean := true
  );
  port (
    CLK_IN      : in  std_logic;  -- 12 MHz oscillator (pico-ice pin 35)
    RESET_N     : in  std_logic;

    BOARD_CLK   : out std_logic;
    BOARD_DATA  : in  std_logic;
    BOARD_LATCH : out std_logic;

    LED_BLUE    : out std_logic;
    LED_GREEN   : out std_logic;
    LED_RED     : out std_logic;

    PACKAGE_MIDI: out std_logic
  );
end scan20_top;

architecture wrap of scan20_top is

  component SB_PLL40_PAD
    generic (
      FEEDBACK_PATH                  : string := "SIMPLE";
      DELAY_ADJUSTMENT_MODE_FEEDBACK : string := "FIXED";
      DELAY_ADJUSTMENT_MODE_RELATIVE : string := "FIXED";
      SHIFTREG_DIV_MODE              : bit_vector(1 downto 0) := "00";
      FDA_FEEDBACK                   : bit_vector(3 downto 0) := "0000";
      FDA_RELATIVE                   : bit_vector(3 downto 0) := "0000";
      PLLOUT_SELECT                  : string := "GENCLK";
      DIVR                           : bit_vector(3 downto 0) := "0000";
      DIVF                           : bit_vector(6 downto 0) := "1001111";
      DIVQ                           : bit_vector(2 downto 0) := "100";
      FILTER_RANGE                   : bit_vector(2 downto 0) := "001";
      ENABLE_ICEGATE                 : bit := '0'
    );
    port (
      PACKAGEPIN   : in  std_logic;
      PLLOUTCORE   : out std_logic;
      PLLOUTGLOBAL : out std_logic;
      EXTFEEDBACK  : in  std_logic;
      DYNAMICDELAY : in  std_logic_vector(7 downto 0);
      LOCK         : out std_logic;
      BYPASS       : in  std_logic;
      RESETB       : in  std_logic;
      LATCHINPUTVALUE : in std_logic
    );
  end component;

  signal sysclk  : std_logic := '0';
  signal pll_lock : std_logic := '0';
  signal pll_rst_n : std_logic := '0';

  signal reset_pipe : std_logic_vector(3 downto 0) := (others => '0');
  signal crst_n      : std_logic := '0';

  signal s_clk, s_latch, s_busy : std_logic;
  signal s_valid, s_done : std_logic;
  signal s_errf, s_errt : std_logic;
  signal seen_err, seen_done : std_logic := '0';

  function to_bv(n : natural; w : natural) return bit_vector is
    variable u : unsigned(w-1 downto 0) := to_unsigned(n, w);
    variable b : bit_vector(w-1 downto 0);
  begin
    for i in 0 to w-1 loop
      if u(i) = '1' then b(i) := '1'; else b(i) := '0'; end if;
    end loop;
    return b;
  end function;

begin

  u_pll : SB_PLL40_PAD
    generic map (
      FEEDBACK_PATH => "SIMPLE",
      PLLOUT_SELECT => "GENCLK",
      DIVR          => "0000",
      DIVF          => to_bv(PLL_DIVF, 7),
      DIVQ          => to_bv(PLL_DIVQ, 3),
      FILTER_RANGE  => "001"
    )
    port map (
      PACKAGEPIN      => CLK_IN,
      PLLOUTCORE      => open,
      PLLOUTGLOBAL    => sysclk,
      EXTFEEDBACK     => '0',
      DYNAMICDELAY    => (others => '0'),
      LOCK            => pll_lock,
      BYPASS          => '0',
      RESETB          => pll_rst_n,
      LATCHINPUTVALUE => '0'
    );

  -- PLL reset: hold until the board reset is released (RESETB active low);
  -- core reset: hold until LOCK, then release synchronously (16-tick pipe)
  pll_rst_n <= RESET_N;

  p_resync : process(sysclk)
  begin
    if rising_edge(sysclk) then
      if RESET_N = '0' or pll_lock = '0' then
        reset_pipe <= (others => '0');
      else
        reset_pipe <= reset_pipe(2 downto 0) & '1';
      end if;
      crst_n <= reset_pipe(3);
    end if;
  end process;

  u_core : entity work.scan20_core
    generic map (
      SYS_HZ            => SYS_HZ,
      TICKS_PER_BIT     => TICKS_PER_BIT,
      TICKS_HIGH        => TICKS_HIGH,
      SAMPLE_LEAD_TICKS => SAMPLE_LEAD_TICKS,
      LATCH_TICKS       => LATCH_TICKS,
      GUARD_TICKS       => GUARD_TICKS,
      FRAME_GAP_TICKS   => FRAME_GAP_TICKS,
      IDLE_TICKS        => IDLE_TICKS,
      TIMEOUT_TICKS     => TIMEOUT_TICKS,
      RECOVERY_TICKS    => RECOVERY_TICKS,
      MAX_TILES         => MAX_TILES,
      COORD_BITS        => COORD_BITS,
      AUTO_RETRY        => AUTO_RETRY
    )
    port map (
      sysclk      => sysclk,
      reset_n     => crst_n,
      start       => '0',
      board_clk   => s_clk,
      board_latch => s_latch,
      board_data  => BOARD_DATA,
      frame_valid => s_valid,
      frame_data  => open,
      frame_col   => open,
      frame_row   => open,
      frame_index => open,
      scan_done   => s_done,
      scan_count  => open,
      busy        => s_busy,
      err_framing => s_errf,
      err_timeout => s_errt,
      err_count   => open,
      dbg_sample  => open,
      dbg_launch  => open,
      dbg_state   => open
    );

  BOARD_CLK   <= s_clk;
  BOARD_LATCH <= s_latch;

  -- sticky status legs (active-low LEDs)
  p_led : process(sysclk)
  begin
    if rising_edge(sysclk) then
      if crst_n = '0' then
        seen_err  <= '0';
        seen_done <= '0';
      else
        if s_errf = '1' or s_errt = '1' then
          seen_err <= '1';
        end if;
        if s_done = '1' then
          seen_done <= '1';
        end if;
      end if;
    end if;
  end process;

  LED_RED   <= not seen_err;
  LED_GREEN <= not s_busy;
  LED_BLUE  <= not seen_done;

  -- keep the MIDI leg at the golden idle level (golden drives
  -- PACKAGE_MIDI <= not midi_out with uart idle = '1')
  PACKAGE_MIDI <= '0';

end wrap;
