-- SPDX-License-Identifier: GPL-3.0-only
--
-- cfg_f100p5: scan20_top at 100.500 MHz -- the NEAREST achievable to 100 MHz
-- from 12 MHz (icepll: 100.000 MHz infeasible, achieved 100.500 MHz,
-- DIVF=66 DIVQ=3, VCO 804 MHz). Documented comparison config only:
--   shift clock   = 100.5 MHz / 5 ticks = 20.100 MHz (+0.5%, NOT exact)
--   high/low      = 3+2 ticks = 29.85 ns / 19.90 ns
--   latch guard   = 6 ticks = 59.7 ns (>= 50 ns deep-col max bound)
--   sample lead   = 1 tick = 9.95 ns (window 1..30 ns)
--   latch width   = 100 ticks ~ 1.0 us

library ieee;
use ieee.std_logic_1164.all;

entity scan20_cfg is
  port (
    CLK_IN      : in  std_logic;
    RESET_N     : in  std_logic;
    BOARD_CLK   : out std_logic;
    BOARD_DATA  : in  std_logic;
    BOARD_LATCH : out std_logic;
    LED_BLUE    : out std_logic;
    LED_GREEN   : out std_logic;
    LED_RED     : out std_logic;
    PACKAGE_MIDI: out std_logic
  );
end scan20_cfg;

architecture wrap of scan20_cfg is
begin
  u_top : entity work.scan20_top
    generic map (
      PLL_DIVF          => 66,
      PLL_DIVQ          => 3,
      SYS_HZ            => 100_500_000,
      TICKS_PER_BIT     => 5,
      TICKS_HIGH        => 3,
      SAMPLE_LEAD_TICKS => 1,
      LATCH_TICKS       => 100,
      GUARD_TICKS       => 6,
      FRAME_GAP_TICKS   => 5,
      IDLE_TICKS        => 50_250,
      TIMEOUT_TICKS     => 8192,
      RECOVERY_TICKS    => 200,   -- multiple of PRE_SCALE=8
      MAX_TILES         => 16,
      COORD_BITS        => 5,
      AUTO_RETRY        => true
    )
    port map (
      CLK_IN       => CLK_IN,
      RESET_N      => RESET_N,
      BOARD_CLK    => BOARD_CLK,
      BOARD_DATA   => BOARD_DATA,
      BOARD_LATCH  => BOARD_LATCH,
      LED_BLUE     => LED_BLUE,
      LED_GREEN    => LED_GREEN,
      LED_RED      => LED_RED,
      PACKAGE_MIDI => PACKAGE_MIDI
    );
end wrap;
