library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tile_tb is
end tile_tb;

architecture sim of tile_tb is

  signal buttons    : std_logic_vector(11 downto 0) := x"A53"; -- 1010 0101 0011
  signal latch, clk, data : std_logic;

  constant CLK_PERIOD : time := 10 ns;

  signal clk_en : std_logic := '0';

begin

    -- Istanza del tuo modulo
    uut: entity work.tile
        port map (
            buttons => buttons,
            T_first => open,
            T_latch => open,
            T_clk => open,
            B_W => open,
            B_endcol => open,
            B_latch => 'L',
            B_clk => 'L',
            B_data => open,
            L_latch => open,
            L_clk => open,
            R_endrow => open,
            R_latch => latch,
            R_clk => clk,
            R_data => data
        );

    -- Generatore di Clock (sulla linea R_clk)
    clk_process : process  -- RIMOSSO (clk_en)
    begin
        while now < 500 ns loop
            if clk_en = '1' then
                clk <= '0';
                wait for CLK_PERIOD/2;
                clk <= '1';
                wait for CLK_PERIOD/2;
            else
                clk <= '0';
                -- Fondamentale: se il clock è disabilitato, dobbiamo
                -- aspettare che clk_en cambi, altrimenti il loop gira
                -- all'infinito nello stesso istante di tempo (hang).
                wait until clk_en = '1';
            end if;
        end loop;
        wait; -- Ferma tutto dopo 500 ns
    end process;



    -- Stimolo principale
    stim_proc: process
    begin

        latch <= '1';  -- stato di reset
        wait for 5 ns;
        latch <= '0'; -- shifting

        clk_en <= '1';
        wait for CLK_PERIOD * 20;
        clk_en <= '0';

        wait for 20 ns;





        --wait for CLK_PERIOD * 2;
        wait;
    end process;

end sim;
