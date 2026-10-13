-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Timing-aware rev-A tile: identical ports/topology/behaviour to
-- hardware/simulation/tile.vhdl (zero-delay reference), re-wired from the
-- actual rev-A chip list (docs/architecture/protocol.md) with the timed,
-- self-checking 74-series models of logic74_timed.vhdl:
--
--   U103/U104  2 x SN74LVC165A   (SR chain; DS mux in front of U103)
--   U109       SN74LV161A        (counter; RCO = Tc; ~MR = ~rst)
--   U102A/B    SN74LVC2G08       (W = T_W AND B_first; flag AND = B_data AND Tc)
--   U106A/B    SN74LVC2G32       (latch OR; flag feedback OR: D = (AND) OR Q)
--   U105       SN74LVC1G04       (~rst = NOT latch, drives ~PL/~MR/~CLR)
--   U108       SN74LVC2G74       (B_W sticky flag FF, ~CLR = ~rst)
--   U107       SN74LVC2G125      (T_clk forward + T_data buffer, active-low OE)
--   U101       SN74LVC2G126      (L_clk forward + L_data buffer, active-high OE)
--
-- Inter-tile routes are NOT delayed here; the testbench inserts the synthetic
-- per-hop route delay on the nets so every hop is visible there.
--
-- Delays are corner-selected per path at elaboration and multiplied by SCALE
-- (synthetic stress; SCALE=1.0 = pure datasheet values):
--   CORNER_CLK   : W AND gate, T/L clock forward buffers, T/L data buffers
--   CORNER_LATCH : latch OR, ~rst inverter
--   CORNER_DATA  : '165s, counter, flag AND/OR, B_W FF
-- split so cross-corner tracking (e.g. fast latch vs slow clock) can be run.
--
-- dbg_* outputs are observation-only (testbench instrumentation); they do not
-- feed back into the tile.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.chain_timing_pkg.all;

entity tile_timed is
  generic (
    CORNER_CLK   : natural := 1;   -- 0 = datasheet min, 1 = datasheet max
    CORNER_LATCH : natural := 1;
    CORNER_DATA  : natural := 1;
    SCALE_CLK_PCT   : natural := 100;  -- 100 = 1.0x (pure datasheet values)
    SCALE_LATCH_PCT : natural := 100;
    SCALE_DATA_PCT  : natural := 100;
    LOC          : string  := "tile"
  );
  port (
    buttons      : in std_logic_vector(11 downto 0) := (others => 'L');

    T_W : in std_logic := 'Z';
    T_endcol : in std_logic := 'Z';
    T_first : out std_logic;
    T_latch : out std_logic;
    T_clk : out std_logic;
    T_data : in std_logic := 'Z';

    B_W : out std_logic;
    B_endcol : out std_logic := '0';
    B_first : in std_logic := 'Z';
    B_latch : in std_logic := 'Z';
    B_clk : in std_logic := 'Z';
    B_data : out std_logic;

    L_endrow : in std_logic := 'Z';
    L_latch : out std_logic;
    L_clk : out std_logic;
    L_data : in std_logic := 'Z';

    R_endrow : out std_logic := '0';
    R_latch : in std_logic := 'Z';
    R_clk : in std_logic := 'Z';
    R_data : out std_logic;

    dbg_clk   : out std_logic;   -- local clock net after the input pulls
    dbg_latch : out std_logic;   -- local latch OR output
    dbg_ds    : out std_logic    -- resolved DS mux node of U103
  );
end entity;

architecture timed of tile_timed is

  constant SCALE_CLK   : real := real(SCALE_CLK_PCT) / 100.0;
  constant SCALE_LATCH : real := real(SCALE_LATCH_PCT) / 100.0;
  constant SCALE_DATA  : real := real(SCALE_DATA_PCT) / 100.0;

  -- corner-selected, scaled leaf delays
  constant D_165_CQ   : time := pick_ns(LVC165A_TPD_CQ_MIN_NS,   LVC165A_TPD_CQ_MAX_NS,   CORNER_DATA) * SCALE_DATA;
  constant D_165_LOAD : time := pick_ns(LVC165A_TPD_LOAD_MIN_NS, LVC165A_TPD_LOAD_MAX_NS, CORNER_DATA) * SCALE_DATA;
  constant D_161_CQ   : time := pick_ns(LV161A_TPD_CQ_MIN_NS,    LV161A_TPD_CQ_MAX_NS,    CORNER_DATA) * SCALE_DATA;
  constant D_161_RCO  : time := pick_ns(LV161A_TPD_RCO_MIN_NS,   LV161A_TPD_RCO_MAX_NS,   CORNER_DATA) * SCALE_DATA;
  constant D_161_CLR  : time := LV161A_TPHL_CLR_NS * 1 ns * SCALE_DATA;
  constant D_AND_W    : time := pick_ns(LVC2G08_TPD_MIN_NS, LVC2G08_TPD_MAX_NS, CORNER_CLK) * SCALE_CLK;
  constant D_AND_FLAG : time := pick_ns(LVC2G08_TPD_MIN_NS, LVC2G08_TPD_MAX_NS, CORNER_DATA) * SCALE_DATA;
  constant D_OR_LATCH : time := pick_ns(LVC2G32_TPD_MIN_NS, LVC2G32_TPD_MAX_NS, CORNER_LATCH) * SCALE_LATCH;
  constant D_OR_FLAG  : time := pick_ns(LVC2G32_TPD_MIN_NS, LVC2G32_TPD_MAX_NS, CORNER_DATA) * SCALE_DATA;
  constant D_INV      : time := pick_ns(LVC1G04_TPD_MIN_NS, LVC1G04_TPD_MAX_NS, CORNER_LATCH) * SCALE_LATCH;
  constant D_74_CQ    : time := pick_ns(LVC2G74_TPD_CQ_MIN_NS, LVC2G74_TPD_CQ_MAX_NS, CORNER_DATA) * SCALE_DATA;
  constant D_125_PD   : time := pick_ns(LVC2G125_TPD_MIN_NS, LVC2G125_TPD_MAX_NS, CORNER_CLK) * SCALE_CLK;
  constant D_125_EN   : time := pick_ns(0.0, LVC2G125_TEN_MAX_NS,  CORNER_CLK) * SCALE_CLK;  -- no datasheet min: 0 ns lower bound (unsigned term)
  constant D_125_DIS  : time := pick_ns(0.0, LVC2G125_TDIS_MAX_NS, CORNER_CLK) * SCALE_CLK;  -- ditto
  constant D_126_PD   : time := pick_ns(LVC2G126_TPD_MIN_NS, LVC2G126_TPD_MAX_NS, CORNER_CLK) * SCALE_CLK;
  constant D_126_EN   : time := pick_ns(0.0, LVC2G126_TEN_MAX_NS,  CORNER_CLK) * SCALE_CLK;
  constant D_126_DIS  : time := pick_ns(0.0, LVC2G126_TDIS_MAX_NS, CORNER_CLK) * SCALE_CLK;
  -- T/L data buffers: same chips but the data path corner
  constant D_125D_PD  : time := pick_ns(LVC2G125_TPD_MIN_NS, LVC2G125_TPD_MAX_NS, CORNER_DATA) * SCALE_DATA;
  constant D_125D_EN  : time := pick_ns(0.0, LVC2G125_TEN_MAX_NS,  CORNER_DATA) * SCALE_DATA;
  constant D_125D_DIS : time := pick_ns(0.0, LVC2G125_TDIS_MAX_NS, CORNER_DATA) * SCALE_DATA;
  constant D_126D_PD  : time := pick_ns(LVC2G126_TPD_MIN_NS, LVC2G126_TPD_MAX_NS, CORNER_DATA) * SCALE_DATA;
  constant D_126D_EN  : time := pick_ns(0.0, LVC2G126_TEN_MAX_NS,  CORNER_DATA) * SCALE_DATA;
  constant D_126D_DIS : time := pick_ns(0.0, LVC2G126_TDIS_MAX_NS, CORNER_DATA) * SCALE_DATA;

  -- pulled inputs (same convention as the zero-delay model)
  -- Initial values match the elaboration-time resolved level so that the
  -- first evaluation of the leaf processes is already settled (no bogus
  -- power-on transactions onto the nets).
  signal T_W_p      : std_logic := 'H';
  signal T_endcol_p : std_logic := 'H';
  signal T_data_p   : std_logic := 'L';
  signal B_first_p  : std_logic := 'H';
  signal B_latch_p  : std_logic := 'L';
  signal B_clk_p    : std_logic := 'H';
  signal L_endrow_p : std_logic := 'H';
  signal L_data_p   : std_logic := 'L';
  signal R_latch_p  : std_logic := 'L';
  signal R_clk_p    : std_logic := 'H';

  signal clock      : std_logic := 'H';
  signal latch      : std_logic := '0';
  signal nlatch     : std_logic := '1';
  signal w_state    : std_logic := '1';
  signal tc                   : std_logic;   -- U109 RCO
  signal flag_and, flag_d     : std_logic;
  signal bw_q                 : std_logic;
  signal ds_mux               : std_logic;   -- resolved U107B/U101B outputs
  signal data                 : std_logic;   -- U104 Q7 (= B_data/R_data net)
  signal sr_bridge            : std_logic;   -- U103 Q7 -> U104 DS
  signal sr2_inputs           : std_logic_vector(7 downto 0);

begin

  -- input pull-ups/downs exactly as on the rev-A schematic pulls
  T_W_p      <= 'H';  T_W_p      <= T_W;
  T_endcol_p <= 'H';  T_endcol_p <= T_endcol;
  T_data_p   <= 'L';  T_data_p   <= T_data;
  B_first_p  <= 'H';  B_first_p  <= B_first;
  B_latch_p  <= 'L';  B_latch_p  <= B_latch;
  B_clk_p    <= 'H';  B_clk_p    <= B_clk;
  L_endrow_p <= 'H';  L_endrow_p <= L_endrow;
  L_data_p   <= 'L';  L_data_p   <= L_data;
  R_latch_p  <= 'L';  R_latch_p  <= R_latch;
  R_clk_p    <= 'H';  R_clk_p    <= R_clk;

  -- B_clk and R_clk are one net on the tile (protocol.md pin table)
  clock <= R_clk_p;
  clock <= B_clk_p;

  -- U102A: W = T_W AND B_first
  u_and_w : entity work.lvc2g08_t
    generic map (LOC => LOC & ".U102A", T_PD => D_AND_W, Y_INIT => '1')
    port map (A => T_W_p, B => B_first_p, Y => w_state);

  -- U106A: latch = R_latch OR B_latch; the OR output is forwarded directly
  u_or_latch : entity work.lvc2g32_t
    generic map (LOC => LOC & ".U106A", T_PD => D_OR_LATCH)
    port map (A => R_latch_p, B => B_latch_p, Y => latch);

  T_latch <= latch;
  L_latch <= latch;

  -- U105: ~rst
  u_inv : entity work.lvc1g04_t
    generic map (LOC => LOC & ".U105", T_PD => D_INV)
    port map (A => latch, Y => nlatch);

  -- U107A: T_clk forward, enabled while W = 0 (active-low OE)
  u_tclk : entity work.lvc2g125_t
    generic map (LOC => LOC & ".U107A", T_PD => D_125_PD, T_EN => D_125_EN, T_DIS => D_125_DIS)
    port map (A => clock, nOE => w_state, Y => T_clk);

  -- U101A: L_clk forward, enabled while W = 1
  u_lclk : entity work.lvc2g126_t
    generic map (LOC => LOC & ".U101A", T_PD => D_126_PD, T_EN => D_126_EN, T_DIS => D_126_DIS)
    port map (A => clock, OE => w_state, Y => L_clk);

  -- U107B / U101B: serial input mux of U103 (resolved wired node)
  u_tdat : entity work.lvc2g125_t
    generic map (LOC => LOC & ".U107B", T_PD => D_125D_PD, T_EN => D_125D_EN, T_DIS => D_125D_DIS)
    port map (A => T_data_p, nOE => w_state, Y => ds_mux);
  u_ldat : entity work.lvc2g126_t
    generic map (LOC => LOC & ".U101B", T_PD => D_126D_PD, T_EN => D_126D_EN, T_DIS => D_126D_DIS)
    port map (A => L_data_p, OE => w_state, Y => ds_mux);

  -- U104 (feeds the tile data output) and U103 (markers/end flags)
  u_sr1 : entity work.lvc165a_t
    generic map (LOC => LOC & ".U104", T_CQ => D_165_CQ, T_LOAD => D_165_LOAD)
    port map (nPL => nlatch, nCE => '0', CP => clock, DS => sr_bridge,
              D => buttons(11 downto 4), Q7 => data, nQ7 => open);
  sr2_inputs <= buttons(3 downto 0) & "11" & to_x01(L_endrow_p) & to_x01(T_endcol_p);
  u_sr2 : entity work.lvc165a_t
    generic map (LOC => LOC & ".U103", T_CQ => D_165_CQ, T_LOAD => D_165_LOAD)
    port map (nPL => nlatch, nCE => '0', CP => clock, DS => ds_mux,
              D => sr2_inputs, Q7 => sr_bridge, nQ7 => open);

  R_data <= data;
  B_data <= data;

  -- U109: counter, Tc = RCO
  u_cnt : entity work.lv161a_t
    generic map (LOC => LOC & ".U109", T_CQ => D_161_CQ, T_RCO => D_161_RCO, T_CLR => D_161_CLR)
    port map (CP => clock, nMR => nlatch, Q => open, RCO => tc);

  -- U102B: flag AND (B_data AND Tc); U106B: sticky feedback OR; U108: FF
  u_and_flag : entity work.lvc2g08_t
    generic map (LOC => LOC & ".U102B", T_PD => D_AND_FLAG)
    port map (A => data, B => tc, Y => flag_and);
  u_or_flag : entity work.lvc2g32_t
    generic map (LOC => LOC & ".U106B", T_PD => D_OR_FLAG)
    port map (A => flag_and, B => bw_q, Y => flag_d);
  u_ff_bw : entity work.lvc2g74_t
    generic map (LOC => LOC & ".U108", T_CQ => D_74_CQ)
    port map (CP => clock, D => flag_d, nCLR => nlatch, Q => bw_q);

  B_W <= bw_q;

  -- presence straps are hardwired levels (J102.4/.5 = GND)
  T_first  <= '0';
  B_endcol <= '0';
  R_endrow <= '0';

  -- observation only
  dbg_clk   <= clock;
  dbg_latch <= latch;
  dbg_ds    <= ds_mux;

end architecture;
