-- Reference: rev-A seven-chip glue, behavioural, zero-delay.
-- Derived from docs/architecture/protocol.md ("Inside a tile") and
-- hardware/simulation/tile.vhdl (existing behavioural model; not modified).
-- Chips modelled: U101 74LVC2G126, U102 74LVC2G08, U105 74LVC1G04,
--                 U106 74LVC2G32, U107 74LVC2G125, U108 74LVC2G74, U109 74HC161.
-- True tri-state on T_clk/L_clk, as in hardware.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ref_glue is
  port (
    bclk   : in  std_logic;  -- board clock (J103.2 / J104.2)
    blatch : in  std_logic;  -- latch from below
    rlatch : in  std_logic;  -- latch from the right
    tw     : in  std_logic;  -- T_W from the tile above
    bfirst : in  std_logic;  -- B_first (pull-up = first of column)
    tdata  : in  std_logic;  -- serial data from the tile above
    ldata  : in  std_logic;  -- serial data from the left tile
    bdata  : in  std_logic;  -- this tile's own chain output (feeds the flag AND)
    tclk   : out std_logic;  -- clock forwarded up   (Z when unselected)
    lclk   : out std_logic;  -- clock forwarded left (Z when unselected)
    latcho : out std_logic;  -- merged latch to the top/left neighbours
    npl    : out std_logic;  -- ~rst: '165 ~PL, '161 ~MR, '74 ~CLR
    ds     : out std_logic;  -- serial input selected for the local chain
    bw     : out std_logic   -- B_W sticky column-end flag to the tile below
  );
end ref_glue;

architecture behave of ref_glue is
  signal w     : std_logic;
  signal latch : std_logic;
  signal cnt   : unsigned(3 downto 0) := (others => '0');  -- U109 '161
  signal tc    : std_logic;                                 -- '161 terminal count (ENT=1)
begin

  w     <= tw and bfirst;              -- U102B
  latch <= blatch or rlatch;           -- U106A
  latcho <= latch;                     -- forwarded to L_latch / T_latch net
  npl   <= not latch;                  -- U105 (~rst)

  -- U107 '125 active-low OE: drives when W=0; Z otherwise
  tclk  <= bclk when w = '0' else 'Z';
  -- U101 '126 active-high OE: drives when W=1; Z otherwise
  lclk  <= bclk when w = '1' else 'Z';

  -- serial input: T_data through U107 when W=0, L_data through U101 when W=1
  ds    <= tdata when w = '0' else ldata;

  -- U109 '161: ~MR = ~rst (level), counts board-clock edges, ENT/ENP tied high
  p_cnt : process(bclk, latch)
  begin
    if latch = '1' then
      cnt <= (others => '0');
    elsif rising_edge(bclk) then
      cnt <= cnt + 1;
    end if;
  end process;

  tc    <= '1' when cnt = 15 else '0';

  -- U108 '74: D = Q OR (B_data AND Tc)  [U106B OR, U102A AND]; ~CLR = ~rst (level)
  p_flag : process(bclk, latch)
  begin
    if latch = '1' then
      bw <= '0';
    elsif rising_edge(bclk) then
      if (bw = '0') and (bdata = '1') and (tc = '1') then
        bw <= '1';
      end if;
    end if;
  end process;

end behave;
