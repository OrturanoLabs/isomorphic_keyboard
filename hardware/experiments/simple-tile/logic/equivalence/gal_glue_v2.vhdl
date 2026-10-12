-- Behavioural transliteration of tile_glue_truez.pld (the corrected variant in
-- ../pld/). Same equations as gal_glue EXCEPT:
--   * macrocell NPL is dropped (an external 74LVC1G04 fed by the LATCH pin gives
--     the '165 ~PL instead -> +1 tiny IC, -1 macrocell)
--   * the freed macrocell HX = /TW + /BFIRST feeds TCLK's single OE product term
--     via feedback: TCLK.T = BCLK, TCLK.E = HX  -> TRUE tri-state on T_clk,
--     recovering the rev-A electrical behaviour observed in ref_glue.

library ieee;
use ieee.std_logic_1164.all;

entity gal_glue_v2 is
  port (
    bclk   : in  std_logic;
    blatch : in  std_logic;
    rlatch : in  std_logic;
    tw     : in  std_logic;
    bfirst : in  std_logic;
    tdata  : in  std_logic;
    ldata  : in  std_logic;
    bdata  : in  std_logic;
    tclk   : out std_logic;
    lclk   : out std_logic;
    latcho : out std_logic;
    npl    : out std_logic;   -- now from the external 1G04 on LATCH
    ds     : out std_logic;
    bw     : out std_logic
  );
end gal_glue_v2;

architecture pld of gal_glue_v2 is
  signal q0, q1, q2, q3 : std_logic := '0';
  signal bw_int         : std_logic := '0';
  signal latch          : std_logic;
  signal hx             : std_logic;  -- helper macrocell: HX = /TW + /BFIRST
begin

  p_regs : process(bclk, latch)
  begin
    if latch = '1' then
      q0 <= '0'; q1 <= '0'; q2 <= '0'; q3 <= '0';
      bw_int <= '0';
    elsif rising_edge(bclk) then
      q0 <= not q0;
      q1 <= (q1 and not q0) or (not q1 and q0);
      q2 <= (q2 and not q1) or (q2 and not q0) or (not q2 and q1 and q0);
      q3 <= (q3 and not q2) or (q3 and not q1) or (q3 and not q0)
            or (not q3 and q2 and q1 and q0);
      bw_int <= bw_int or (bdata and q0 and q1 and q2 and q3);
    end if;
  end process;
  bw <= bw_int;

  latch  <= blatch or rlatch;
  latcho <= latch;
  npl    <= not latch;                  -- external 74LVC1G04, fed from the LATCH pin

  hx     <= (not tw) or (not bfirst);   -- HX macrocell (buried, .E = GND)
  tclk   <= bclk when hx = '1' else 'Z';          -- TCLK.T = BCLK, TCLK.E = HX
  lclk   <= bclk when (tw = '1' and bfirst = '1') else 'Z';

  ds <= (tw and bfirst and ldata) or ((not tw) and tdata) or ((not bfirst) and tdata);

end pld;
