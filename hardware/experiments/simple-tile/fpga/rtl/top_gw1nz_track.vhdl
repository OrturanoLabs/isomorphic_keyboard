-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Board-level top for GW1NZ-LV1QN48 (single-PCB tile candidate).
--
-- Pin-pruning vs the sim entity, matching the rev-A connector nets exactly:
--   B_clk and R_clk are the SAME net on the rev-A board (J103.2 = J104.2,
--   docs/architecture/protocol.md) -> one clk_pin feeding both core ports.
--   latcho = T_latch = L_latch (one net on J102.6/J101.5)
--   dout   = B_data  = R_data  (one net on J103.3/J104.3)
--   T_first / B_endcol / R_endrow are PCB GND straps (no FPGA pin).
-- => exact board pin budget = 26 user IO (documented in docs/pin_budget.md).
--
-- SNAP_MODE: "fall" (default) needs no oscillator at all; "track" uses the
-- GW1NZ on-chip OSCZ (the only oscillator BEL present on GW1NZ-1 per the
-- installed chipdb). Board pin pulls are pad PULL_MODE in synth/tile_gw1nz.cst.

library ieee;
use ieee.std_logic_1164.all;

entity top_gw1nz_track is
  generic ( SNAP_MODE : string := "track" );
  port (
    keys        : in  std_logic_vector(11 downto 0);
    clk_pin     : in  std_logic;   -- merged J103.2 / J104.2 (one board net)
    t_w_pin     : in  std_logic;
    t_endcol_pin: in  std_logic;
    t_data_pin  : in  std_logic;
    b_first_pin : in  std_logic;
    b_latch_pin : in  std_logic;
    r_latch_pin : in  std_logic;
    l_endrow_pin: in  std_logic;
    l_data_pin  : in  std_logic;
    t_clk_pin   : out std_logic;  -- true tri-state (TBUF)
    l_clk_pin   : out std_logic;  -- true tri-state (TBUF)
    latcho_pin  : out std_logic;
    dout_pin    : out std_logic;
    b_w_pin     : out std_logic
  );
end top_gw1nz_track;

architecture wrap of top_gw1nz_track is
  -- GW1NZ on-chip oscillator; unbound component maps to the gowin OSCZ cell
  component OSCZ
    generic (FREQ_DIV : integer := 128);
    port (OSCOUT : out std_logic);
  end component;
  signal sysclk : std_logic := '0';
begin
  gen_osc : if SNAP_MODE = "track" generate
    u_osc : OSCZ generic map (FREQ_DIV => 128) port map (OSCOUT => sysclk);
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
