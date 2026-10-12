-- 1:1 behavioural transliteration of hardware/gal/tile_glue.pld (ATF22V10C fit,
-- galette-assembled into tile_glue.jed). Every equation below quotes the .pld.
-- This is a zero-delay functional model of the JEDEC fuse map, NOT a timing model.
--
-- Deliberate differences vs ref_glue (kept observable, not glossed):
--   * TCLK is DRIVEN LOW when the chain turns left (W=1) instead of tri-state,
--     because the 22V10 output-enable is a single product term and W=0 is an OR.
--   * The async reset AR is the LATCH *output* fed back (single product term).

library ieee;
use ieee.std_logic_1164.all;

entity gal_glue is
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
    npl    : out std_logic;
    ds     : out std_logic;
    bw     : out std_logic
  );
end gal_glue;

architecture pld of gal_glue is
  signal q0, q1, q2, q3 : std_logic := '0';  -- buried counter macrocells Q0..Q3
  signal bw_int         : std_logic := '0';
  signal latch          : std_logic;
begin

  -- ; --- bit counter ---
  -- Q0.R = /Q0 ; Q1.R = Q1*/Q0 + /Q1*Q0 ; Q2.R = Q2*/Q1 + Q2*/Q0 + /Q2*Q1*Q0 ;
  -- Q3.R = Q3*/Q2 + Q3*/Q1 + Q3*/Q0 + /Q3*Q2*Q1*Q0 ; Q*.E = GND (never driven out)
  -- BW.R = BW + BDATA*Q0*Q1*Q2*Q3
  -- AR = LATCH (feedback); SP = GND
  p_regs : process(bclk, latch)
  begin
    if latch = '1' then                       -- AR = LATCH (level)
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

  -- ; --- latch merge ---  LATCH = BLATCH + RLATCH ; NPL = /BLATCH * /RLATCH
  latch  <= blatch or rlatch;
  latcho <= latch;
  npl    <= (not blatch) and (not rlatch);

  -- ; --- clock to the top or left ---
  -- TCLK = BCLK*/TW + BCLK*/BFIRST   (driven low when unselected: NO tri-state)
  tclk <= bclk and ((not tw) or (not bfirst));
  -- LCLK.T = BCLK ; LCLK.E = TW*BFIRST  (single OE product term: real tri-state)
  lclk <= bclk when (tw = '1' and bfirst = '1') else 'Z';

  -- ; --- serial input --- DS = TW*BFIRST*LDATA + /TW*TDATA + /BFIRST*TDATA
  ds <= (tw and bfirst and ldata) or ((not tw) and tdata) or ((not bfirst) and tdata);

end pld;
