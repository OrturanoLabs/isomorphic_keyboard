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
  -- When output enable is high, pull the line to '0' (D_OUT_0 is tied to '0' in the top level)
  -- Otherwise release the line ('Z') to model an open-drain output
  PACKAGE_PIN <= D_OUT_0 when OUTPUT_ENABLE = '1' else 'Z';

  -- Feed the physical pin value back into the logic
  D_IN_0 <= PACKAGE_PIN;
end sim;
