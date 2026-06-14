library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity top is
    Port (
        clk_in      : in  std_logic;
        clk_out     : out std_logic;
        reset_n     : in std_logic;
        latch       : out std_logic;
        data        : in std_logic;

        led_blue    : out std_logic;
        led_red     : out std_logic;
        led_green   : out std_logic
    );
end top;

architecture behavioral of top is

    signal clk_counter : unsigned(25 downto 0) := (others => '0');  -- contatore per il clock principale
    signal clk_low : std_logic;
    signal reset : std_logic;

begin
    reset <= not reset_n;
    led_blue <= reset_n;
    clk_low <= clk_counter(22);
    led_red <= not clk_low;

    clocking : process(clk_in, reset)
    begin

        latch <= '0';

        if reset = '1' then
            latch <= '1';
            clk_counter <= (others => '0');
        elsif rising_edge(clk_in) then
            clk_counter <= clk_counter + 1;
        end if;

    end process;

    clk_out <= clk_low;

    led_green <= not data;


end behavioral;











