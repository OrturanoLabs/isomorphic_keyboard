-- Tile wrappers: one glue implementation + two 74HCT165-style shift registers.
-- Chain wiring mirrors hardware/simulation/tile.vhdl (the existing behavioural
-- model of rev A; NOT modified, compiled alongside):
--   sr1 (LSB chip): D = buttons(11..4), DS = sr2.Q7, Q7 = chain out
--   sr2 (MSB chip): D = buttons(3..0) & "11" & L_endrow & T_endcol, DS = glue DS
-- The glue's BDATA input is this tile's own chain output, as on the rev-A board
-- (U108 D-input ANDed with Tc comes from B_data).

library ieee;
use ieee.std_logic_1164.all;

entity tile_ref is
  port (
    buttons : in  std_logic_vector(11 downto 0);
    endrow  : in  std_logic;
    endcol  : in  std_logic;
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
    ds      : out std_logic;
    bw      : out std_logic;
    dout    : out std_logic
  );
end tile_ref;

architecture struct of tile_ref is
  signal npl_s, ds_s, dout_s, bridge : std_logic;
begin
  glue : entity work.ref_glue
    port map (
      bclk => bclk, blatch => blatch, rlatch => rlatch, tw => tw,
      bfirst => bfirst, tdata => tdata, ldata => ldata, bdata => dout_s,
      tclk => tclk, lclk => lclk, latcho => latcho, npl => npl_s,
      ds => ds_s, bw => bw);

  sr1 : entity work.T74HCT165
    port map (nPL => npl_s, nCE => '0', CP => bclk, DS => bridge,
              D => buttons(11 downto 4), Q7 => dout_s, nQ7 => open);

  sr2 : entity work.T74HCT165
    port map (nPL => npl_s, nCE => '0', CP => bclk, DS => ds_s,
              D => buttons(3 downto 0) & "11" & endrow & endcol,
              Q7 => bridge, nQ7 => open);

  npl  <= npl_s;
  ds   <= ds_s;
  dout <= dout_s;
end struct;

-------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;

entity tile_gal is   -- tile_glue.pld as committed (driven-low T_clk)
  port (
    buttons : in  std_logic_vector(11 downto 0);
    endrow  : in  std_logic;
    endcol  : in  std_logic;
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
    ds      : out std_logic;
    bw      : out std_logic;
    dout    : out std_logic
  );
end tile_gal;

architecture struct of tile_gal is
  signal npl_s, ds_s, dout_s, bridge : std_logic;
begin
  glue : entity work.gal_glue
    port map (
      bclk => bclk, blatch => blatch, rlatch => rlatch, tw => tw,
      bfirst => bfirst, tdata => tdata, ldata => ldata, bdata => dout_s,
      tclk => tclk, lclk => lclk, latcho => latcho, npl => npl_s,
      ds => ds_s, bw => bw);

  sr1 : entity work.T74HCT165
    port map (nPL => npl_s, nCE => '0', CP => bclk, DS => bridge,
              D => buttons(11 downto 4), Q7 => dout_s, nQ7 => open);

  sr2 : entity work.T74HCT165
    port map (nPL => npl_s, nCE => '0', CP => bclk, DS => ds_s,
              D => buttons(3 downto 0) & "11" & endrow & endcol,
              Q7 => bridge, nQ7 => open);

  npl  <= npl_s;
  ds   <= ds_s;
  dout <= dout_s;
end struct;

-------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;

entity tile_galv2 is   -- tile_glue_truez.pld (true-Z T_clk, external NPL inverter)
  port (
    buttons : in  std_logic_vector(11 downto 0);
    endrow  : in  std_logic;
    endcol  : in  std_logic;
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
    ds      : out std_logic;
    bw      : out std_logic;
    dout    : out std_logic
  );
end tile_galv2;

architecture struct of tile_galv2 is
  signal npl_s, ds_s, dout_s, bridge : std_logic;
begin
  glue : entity work.gal_glue_v2
    port map (
      bclk => bclk, blatch => blatch, rlatch => rlatch, tw => tw,
      bfirst => bfirst, tdata => tdata, ldata => ldata, bdata => dout_s,
      tclk => tclk, lclk => lclk, latcho => latcho, npl => npl_s,
      ds => ds_s, bw => bw);

  sr1 : entity work.T74HCT165
    port map (nPL => npl_s, nCE => '0', CP => bclk, DS => bridge,
              D => buttons(11 downto 4), Q7 => dout_s, nQ7 => open);

  sr2 : entity work.T74HCT165
    port map (nPL => npl_s, nCE => '0', CP => bclk, DS => ds_s,
              D => buttons(3 downto 0) & "11" & endrow & endcol,
              Q7 => bridge, nQ7 => open);

  npl  <= npl_s;
  ds   <= ds_s;
  dout <= dout_s;
end struct;
