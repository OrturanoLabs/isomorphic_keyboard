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

    signal toggle : std_logic := '0';

begin
    reset <= not reset_n;
    led_blue <= reset_n;

    led_red <= '0';

    led : process(clk_in)
    begin
        if rising_edge(clk_in) then
            if reset = '1' then
                toggle <= '0';
                latch <= '1';
            else
                toggle <= not toggle;
                latch <= '0';
            end if;
        end if;
    end process;

    gen_enable : process(clk_in)
    begin
        if rising_edge(clk_in) then
            if reset = '1' then
                clk_counter <= (others => '0');
                clk_low  <= '0';
            else
                if clk_counter(2) = '1' then  -- Conta: 0, 1, 2, 3 (quattro cicli)
                    clk_counter <= (others => '0');
                    clk_low  <= '1'; -- Impulso alto per un solo ciclo di clk_in
                else
                    clk_counter <= clk_counter + 1;
                    clk_low  <= '0'; -- Torna subito a zero al ciclo successivo
                end if;
            end if;
        end if;
    end process;

    clk_out <= clk_in;

    led_green <= '0';


end behavioral;











