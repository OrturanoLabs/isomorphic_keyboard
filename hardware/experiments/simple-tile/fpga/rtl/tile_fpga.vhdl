-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- tile_fpga: whole-tile candidate for FPGA fabric (Gowin GW1NZ / iCE40).
--
-- Ports mirror the hardware-tested rev-A tile behavioural model
-- (hardware/simulation/tile.vhdl, READ-ONLY reference) one-for-one, plus:
--   sysclk    : free-running snapshot clock, used ONLY in SNAP_MODE="track"
--   SNAP_MODE : "fall"  (default) shadow clocked by the latch falling edge:
--                        snapshot lands exactly on the rev-A capture instant
--                        (up to FF setup/hold at the fall); combinational
--                        first-bit during latch = exact '165 transparency.
--                        Requires pd stable through the fall edge -- the same
--                        kind of recovery window a real '165 /PL asks for.
--               "track" shadow continuously sampled on sysclk while latch=1:
--                        snapshot is the LAST sysclk sample before the fall,
--                        i.e. stale by up to one sysclk period. That is an
--                        APPROXIMATION of rev A: a key change inside the
--                        final (Tsys) window before the fall is captured by
--                        the '165 but NOT by "track" (characterised by the
--                        sim phase sweep; NOT a pass-equivalence). sysclk/latch
--                        CDC and recovery must be budgeted per
--                        docs/clock_domains.md.
--
-- FPGA fabric has no async parallel *data* load FF (the ATF1502 trick of 2
-- product terms per FF does not exist here), so neither mode uses one:
--
--   * "first bit before first clock": `data` is driven combinationally from
--     pd(15) while latch='1' (exact transparency) and from shadow(15) after
--     the fall until the first shift clock.
--   * "first shift special load": the FIRST rising shift-clock edge after the
--     latch loads shreg <= shadow(14 downto 0) & dsin (later edges shift
--     normally). The same word a '165 holds asynchronously is delayed into
--     the shreg at the first edge; bit 1 comes from the shadow/path mux.
--
-- True tri-state clock outputs (T_clk/L_clk <> 'Z') synthesize to TBUF/SB_IO
-- tristate cells (verified in results/ netlists). Weak pin pulls of rev A are
-- resolved at the pin by res_in(); board pulls are expressed as pad pull
-- config in the synth constraints (Gowin UP+DOWN; iCE40 UP only).

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tile_fpga is
  generic (
    SNAP_MODE : string := "fall"      -- "fall" exact snapshot | "track" sysclk
  );
  port (
    buttons : in std_logic_vector(11 downto 0) := (others => 'L');
    sysclk  : in std_logic := '0';   -- on-chip snapshot clock (extra domain)

    T_W : in std_logic := 'Z';
    T_endcol : in std_logic := 'Z';
    T_first : out std_logic := '0';
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
    R_data : out std_logic
  );
end tile_fpga;

architecture rtl of tile_fpga is

  -- resolve an open-connector input the way the rev-A pin pulls do:
  -- a truly undriven pin ('Z' here, pull resistor on the board) resolves to
  -- its documented idle level; any driven/pulled value maps through to_x01.
  function res_in(s : std_logic; pull : std_logic) return std_logic is
  begin
    if s = 'Z' then
      return pull;
    else
      return to_x01(s);
    end if;
  end function;

  signal tw_p, tec_p, tda_p : std_logic;
  signal bf_p, bla_p, bck_p : std_logic;
  signal ler_p, lda_p       : std_logic;
  signal rla_p, rck_p       : std_logic;

  signal clock, latch : std_logic;
  signal w_state      : std_logic;
  signal dsin         : std_logic;

  signal data  : std_logic;                      -- chain output of this tile
  signal cnt   : unsigned(3 downto 0) := (others => '0');  -- rev-A '161
  signal bw_i  : std_logic := '0';

  signal pd     : std_logic_vector(15 downto 0);  -- parallel word, MSB out first
  signal shadow : std_logic_vector(15 downto 0) := (others => '0');
  signal shreg  : std_logic_vector(15 downto 0) := (others => '0');
  signal loaded : std_logic := '0';               -- first shift edge consumed
  signal prebit : std_logic;  -- bit 1: live pd during latch, shadow after fall

begin

  -- pin-pull resolution (board pulls, 'H' up / 'L' down as in rev A)
  tw_p  <= res_in(T_W,      '1');
  tec_p <= res_in(T_endcol, '1');
  tda_p <= res_in(T_data,   '0');
  bf_p  <= res_in(B_first,  '1');
  bla_p <= res_in(B_latch,  '0');
  bck_p <= res_in(B_clk,    '1');
  ler_p <= res_in(L_endrow, '1');
  lda_p <= res_in(L_data,   '0');
  rla_p <= res_in(R_latch,  '0');
  rck_p <= res_in(R_clk,    '1');

  -- B_clk and R_clk are the same net on the rev-A board (J103.2 = J104.2);
  -- the reference model resolves two weak-pulled inputs, equivalent here to
  -- an AND of the two resolved values (at most one is ever driven low).
  clock <= bck_p and rck_p;

  latch <= rla_p or bla_p;          -- latch is an OR of the two connector legs

  w_state <= tw_p and bf_p;
  dsin    <= lda_p when w_state = '1' else tda_p;

  -- outputs wiring (identical to the reference)
  R_data <= data;
  B_data <= data;
  T_latch <= latch;
  L_latch <= latch;
  T_clk <= clock when w_state = '0' else 'Z';
  L_clk <= clock when w_state = '1' else 'Z';
  T_first  <= '0';             -- connector presence straps: PCB GND in rev A
  B_endcol <= '0';
  R_endrow <= '0';

  -- parallel word: 12 keys, markers '11', L_endrow, T_endcol (MSB out first)
  pd(15 downto 4) <= buttons;
  pd(3)           <= '1';
  pd(2)           <= '1';
  pd(1)           <= ler_p;
  pd(0)           <= tec_p;

  ----------------------------------------------------------------------------
  -- snapshot register. Two replaced implementations (generate):
  --  * "fall":  negedge latch FF -- capture instant = the latch falling edge,
  --             the same instant the '165 freezes. Setup/hold contract: pd
  --             stable through the fall (documented recovery window).
  --  * "track": sysclk sampling while latch='1' -- captures the last sample
  --             BEFORE the fall; a change inside the final Tsys window is NOT
  --             captured (sysclk/latch CDC; characterised in the sims).
  ----------------------------------------------------------------------------
  g_fall : if SNAP_MODE = "fall" generate
    p_shadow_f : process(latch)
    begin
      if falling_edge(latch) then
        shadow <= pd;
      end if;
    end process;
  end generate;

  g_track : if SNAP_MODE = "track" generate
    p_shadow_t : process(sysclk)
    begin
      if rising_edge(sysclk) then
        if latch = '1' then
          shadow <= pd;
        end if;
      end if;
    end process;
  end generate;

  ----------------------------------------------------------------------------
  -- shift-clock domain: async latch clear (fabric FF async reset), counted
  -- edges, sticky B_W, and the first-edge special load of the shift register
  -- from the frozen shadow.
  ----------------------------------------------------------------------------
  p_shift : process(clock, latch)
  begin
    if latch = '1' then
      shreg  <= (others => '0');
      cnt    <= (others => '0');
      bw_i   <= '0';
      loaded <= '0';
    elsif rising_edge(clock) then
      cnt <= cnt + 1;
      if loaded = '0' then
        shreg  <= shadow(14 downto 0) & dsin;   -- first shift special load
        loaded <= '1';
      else
        shreg  <= shreg(14 downto 0) & dsin;
      end if;
      if bw_i = '0' and cnt = "1111" and data = '1' then
        bw_i <= '1';
      end if;
    end if;
  end process;

  -- chain output: while the latch is high the parallel MSB appears
  -- combinationally (exact '165 /PL transparency); after the fall the frozen
  -- shadow carries bit 1 until the first shift edge has consumed it; then the
  -- shreg carries the stream, exactly like the '165 cascade of the reference.
  prebit <= pd(15) when latch = '1' else shadow(15);
  data   <= prebit when loaded = '0' else shreg(15);

  B_W <= bw_i;

end rtl;
