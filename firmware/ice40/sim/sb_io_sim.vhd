library ieee;
use ieee.std_logic_1164.all;

entity SB_IO is
  generic (
    PIN_TYPE : std_logic_vector(5 downto 0) := "000000";
    PULLUP   : std_logic := '0'
  );
  port (
    PACKAGE_PIN       : inout std_logic;
    LATCH_INPUT_VALUE : in    std_logic := '0';
    CLOCK_ENABLE      : in    std_logic := '1';
    INPUT_CLK         : in    std_logic := '0';
    OUTPUT_CLK        : in    std_logic := '0';
    OUTPUT_ENABLE     : in    std_logic := '0';
    D_OUT_0           : in    std_logic := '0';
    D_OUT_1           : in    std_logic := '0';
    D_IN_0            : out   std_logic;
    D_IN_1            : out   std_logic
  );
end SB_IO;

architecture sim of SB_IO is
begin
  -- Se l'output enable è alto, tira a '0' (visto che D_OUT_0 è fisso a '0' nel top)
  -- Altrimenti lascia la linea libera ('Z') per simulare l'open-drain
  PACKAGE_PIN <= D_OUT_0 when OUTPUT_ENABLE = '1' else 'Z';

  -- Riporta il valore del pin fisico verso l'interno della logica
  D_IN_0 <= PACKAGE_PIN;
end sim;
