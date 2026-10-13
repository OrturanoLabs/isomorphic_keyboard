-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Board-level top for iCE40UP5K (-SG48). Same pruning as GW1NZ (26 user IO,
-- merged clock pin; docs/pin_budget.md).
--
-- NOTE (config storage is NOT embedded flash on this part): UP5K is SRAM
-- config; retained choices are OTP NVCM (one-time; open-flow programming of
-- NVCM is unverified here) or an external SPI flash (+1 BOM). See
-- docs/alternatives.md + docs/power_bom.md.
-- iCE40 pads implement pull-UP only: the four rev-A DOWN pulls (T_data,
-- L_data, B_latch, R_latch) need +4 board resistors on this variant.

library ieee;
use ieee.std_logic_1164.all;

entity top_ice40up is
  generic ( SNAP_MODE : string := "fall" );
  port (
    keys        : in  std_logic_vector(11 downto 0);
    clk_pin     : in  std_logic;
    t_w_pin     : in  std_logic;
    t_endcol_pin: in  std_logic;
    t_data_pin  : in  std_logic;
    b_first_pin : in  std_logic;
    b_latch_pin : in  std_logic;
    r_latch_pin : in  std_logic;
    l_endrow_pin: in  std_logic;
    l_data_pin  : in  std_logic;
    t_clk_pin   : out std_logic;  -- true tri-state (SB_IO tristate)
    l_clk_pin   : out std_logic;
    latcho_pin  : out std_logic;
    dout_pin    : out std_logic;
    b_w_pin     : out std_logic
  );
end top_ice40up;

architecture wrap of top_ice40up is
  component SB_HFOSC
    generic (CLKHF_DIV : string := "0b11");    -- 48 MHz / 8 = 6 MHz
    port (CLKHFPU : in std_logic; CLKHFEN : in std_logic; CLKHF : out std_logic);
  end component;
  signal sysclk : std_logic := '0';
begin
  gen_osc : if SNAP_MODE = "track" generate
    u_osc : SB_HFOSC generic map (CLKHF_DIV => "0b11")
                     port map (CLKHFPU => '1', CLKHFEN => '1', CLKHF => sysclk);
  end generate;

  u_tile : entity work.tile_fpga
    generic map (SNAP_MODE => SNAP_MODE)
    port map (
      buttons  => keys, sysclk => sysclk,
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
