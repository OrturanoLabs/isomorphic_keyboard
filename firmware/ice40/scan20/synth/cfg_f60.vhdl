-- SPDX-License-Identifier: GPL-3.0-only
--
-- cfg_f60: scan20_top pinned to the EXACT-20 MHz 60.000 MHz configuration.
-- 12 MHz -> SB_PLL40_PAD (DIVF=79 DIVQ=3+1 => VCO 960 MHz /16) = 60.000 MHz
-- (icepll: achieved 60.000 MHz exactly).
--   shift clock   = 60 MHz / 3 ticks = 20.000 MHz EXACT
--   high/low      = 2+1 ticks = 33.33 ns / 16.67 ns
--   latch guard   = 4 ticks = 66.7 ns (>= 50 ns deep-col max bound, machine.json)
--   sample lead   = 1 tick = 16.67 ns (window 1..30 ns)
--   latch width   = 60 ticks = 1.0 us

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
      PLL_DIVF          => 79,
      PLL_DIVQ          => 4,
      SYS_HZ            => 60_000_000,
      TICKS_PER_BIT     => 3,
      TICKS_HIGH        => 2,
      SAMPLE_LEAD_TICKS => 1,
      LATCH_TICKS       => 60,
      GUARD_TICKS       => 4,
      FRAME_GAP_TICKS   => 3,
      IDLE_TICKS        => 30_000,
      TIMEOUT_TICKS     => 8192,
      RECOVERY_TICKS    => 120,
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
