-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Board-level top for iCE40LP8K-CM81, targeting the TinyFPGA BX module
-- (mandatory candidate). Same pruning as GW1NZ (26 user IO + sysclk_pin,
-- merged clock pin).
--
-- sysclk_pin is only used with SNAP_MODE="track": the LP8K has NO on-chip
-- HF oscillator (LFOSC ~10 kHz is far too slow for a us-scale latch pulse),
-- so "track" needs a board/module clock -- the BX carries a 16 MHz osc on
-- B2 (amaranth-boards tinyfpga_bx.py resource). With "fall" no oscillator
-- is needed and sysclk_pin can be tied low / left as a spare.
-- Config storage: LP8K is SRAM-only (no NVCM; TO VERIFY vs Lattice LP/HX
-- DS) -> external SPI flash in production (the BX module carries one).

library ieee;
use ieee.std_logic_1164.all;

entity top_ice40lp_track is
  generic ( SNAP_MODE : string := "track" );
  port (
    keys        : in  std_logic_vector(11 downto 0);
    sysclk_pin  : in  std_logic;   -- BX 16 MHz module osc (B2), track only
    clk_pin     : in  std_logic;
    t_w_pin     : in  std_logic;
    t_endcol_pin: in  std_logic;
    t_data_pin  : in  std_logic;
    b_first_pin : in  std_logic;
    b_latch_pin : in  std_logic;
    r_latch_pin : in  std_logic;
    l_endrow_pin: in  std_logic;
    l_data_pin  : in  std_logic;
    t_clk_pin   : out std_logic;
    l_clk_pin   : out std_logic;
    latcho_pin  : out std_logic;
    dout_pin    : out std_logic;
    b_w_pin     : out std_logic
  );
end top_ice40lp_track;

architecture wrap of top_ice40lp_track is
begin
  u_tile : entity work.tile_fpga
    generic map (SNAP_MODE => SNAP_MODE)
    port map (
      buttons  => keys, sysclk => sysclk_pin,
      T_W => t_w_pin, T_endcol => t_endcol_pin, T_first => open,
      T_latch => latcho_pin, T_clk => t_clk_pin, T_data => t_data_pin,
      B_W => b_w_pin, B_endcol => open, B_first => b_first_pin,
      B_latch => b_latch_pin, B_clk => clk_pin, B_data => dout_pin,
      L_endrow => l_endrow_pin, L_latch => open, L_clk => l_clk_pin,
      L_data => l_data_pin,
      R_endrow => open, R_latch => r_latch_pin, R_clk => clk_pin,
      R_data => open
    );
end wrap;
