-- ATF1502ASV full-tile candidate: the two '165 shift registers AND the whole
-- rev-A glue in one device. Zero-delay behavioural RTL, written so the /PL load
-- is ASYNCHRONOUS and TRANSPARENT, like the real 74LVC165A: while the latch is
-- high the parallel word appears at the chain output before the first clock
-- (the rev-A scan protocol samples BOARD_DATA before raising BOARD_CLK,
-- docs/architecture/protocol.md step 2). A "load on the first clock edge"
-- design would break that.
--
-- Documented ATF1502 mapping (not a fit claim; the practical fitter is
-- proprietary, Microchip ProChip/WinCUPL):
--   shreg(i)   -> 16 macrocell FFs, parallel-load transparency via the per-FF
--               async preset/clear product terms:
--                 SP_i = /npl * pd(i),  AR_i = /npl * /pd(i)   (2 PTs per bit)
--               (the level-sensitive load is exactly 74x165 /PL behaviour)
--   cnt(0..3)-> 4 macrocell FFs, async reset product term AR = latch
--   bw       -> 1 macrocell FF, same AR
--   latch/npl/ds/tclk/lclk -> combinatorial outputs (4 PTs); if the macrocell
--               OE is a single product term, tclk's OE reuses the HX helper
--               pattern proven in ../pld/tile_glue_truez.pld (+1 cell)
-- Register-level total ~= 21 FFs + comb outputs; a real fit requires the
-- proprietary fitter (see logic/README.md) -- no fit claim is made here.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tile_cpld is
  port (
    buttons : in  std_logic_vector(11 downto 0);
    endrow  : in  std_logic;  -- L_endrow
    endcol  : in  std_logic;  -- T_endcol
    bclk    : in  std_logic;
    blatch  : in  std_logic;
    rlatch  : in  std_logic;
    tw      : in  std_logic;
    bfirst  : in  std_logic;
    tdata   : in  std_logic;
    ldata   : in  std_logic;
    tclk    : out std_logic;
    lclk    : out std_logic;
    latcho  : out std_logic;
    npl     : out std_logic;
    ds      : out std_logic;  -- selected serial input (observability)
    bw      : out std_logic;
    dout    : out std_logic   -- chain output to B_data / R_data
  );
end tile_cpld;

architecture rtl of tile_cpld is
  signal latch : std_logic;
  signal w     : std_logic;
  signal dsin  : std_logic;
  signal pd    : std_logic_vector(15 downto 0);  -- parallel word, pd(15) out first
  signal shreg   : std_logic_vector(15 downto 0);
  signal cnt   : unsigned(3 downto 0) := (others => '0');
begin

  latch  <= blatch or rlatch;
  latcho <= latch;
  npl    <= not latch;             -- internal inversion, no extra pin
  w      <= tw and bfirst;

  -- glue muxes (true tri-state outputs, as rev A)
  tclk <= bclk when w = '0' else 'Z';
  lclk <= bclk when w = '1' else 'Z';
  ds   <= ldata when w = '1' else tdata;
  dsin <= ldata when w = '1' else tdata;

  -- parallel word: 12 keys, two marker '1's, L_endrow, T_endcol (MSB first out)
  pd(15 downto 4) <= buttons;
  pd(3)           <= '1';
  pd(2)           <= '1';
  pd(1)           <= endrow;
  pd(0)           <= endcol;

  -- 16-bit chain with asynchronous transparent /PL load, guarding the shift by
  -- an edge: 'process(bclk, latch, pd)' + 'elsif rising_edge' mirrors the
  -- reference 74hc165 model (hardware/simulation/74hc165.vhdl) exactly.
  p_sr : process(bclk, latch, pd)
  begin
    if latch = '1' then
      shreg <= pd;                                  -- level-transparent parallel load
    elsif rising_edge(bclk) then
      shreg <= shreg(14 downto 0) & dsin;
    end if;
  end process;
  dout <= shreg(15);

  p_cnt : process(bclk, latch)
  begin
    if latch = '1' then
      cnt <= (others => '0');
    elsif rising_edge(bclk) then
      cnt <= cnt + 1;
    end if;
  end process;

  p_flag : process(bclk, latch)
  begin
    if latch = '1' then
      bw <= '0';
    elsif rising_edge(bclk) then
      if (bw = '0') and (shreg(15) = '1') and (cnt = 15) then
        bw <= '1';
      end if;
    end if;
  end process;

end rtl;
