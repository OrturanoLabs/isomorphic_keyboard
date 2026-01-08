library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tile_tb is
end tile_tb;

architecture sim of tile_tb is

  signal buttons11    : std_logic_vector(11 downto 0) := x"A53"; -- 1010 0101 0011
  signal buttons21    : std_logic_vector(11 downto 0) := x"B31";
  signal buttons12    : std_logic_vector(11 downto 0) := x"5F9";

  signal latch, clk, data : std_logic;

  constant CLK_PERIOD : time := 10 ns;

  signal clk_en : std_logic := '0';

  -- sengali di collegamento fra 11 e 21
  signal W_11_21, endcol_11_21, first_11_21, latch_11_21, clock_11_21, data_11_21 : std_logic;
  -- sengali di collegamento fra 11 e 12
  signal endrow_11_12, latch_11_12, clock_11_12, data_11_12 : std_logic;


  signal sr_controllo : std_logic_vector(63 downto 0) := (others => '0');

begin

    -- Istanza del tuo modulo
    uut11: entity work.tile
        port map (
            buttons => buttons11,
            T_W => W_11_21,
            T_endcol => endcol_11_21,
            T_first => first_11_21,
            T_latch => latch_11_21,
            T_clk => clock_11_21,
            t_data => data_11_21,
            B_W => open,
            B_endcol => open,
            B_data => open,
            L_endrow => endrow_11_12,
            L_latch => latch_11_12,
            L_clk => clock_11_12,
            L_data => data_11_12,
            R_endrow => open,
            R_latch => latch,
            R_clk => clk,
            R_data => data
        );

    uut21: entity work.tile
        port map (
            buttons => buttons21,
            T_first => open,
            T_latch => open,
            T_clk => open,
            B_W => W_11_21,
            B_endcol => endcol_11_21,
            B_first => first_11_21,
            B_latch => latch_11_21,
            B_clk => clock_11_21,
            B_data => data_11_21,
            L_latch => open,
            L_clk => open,
            R_endrow => open,
            R_data => open
        );

    uut12: entity work.tile
        port map (
            buttons => buttons12,
            T_first => open,
            T_latch => open,
            T_clk => open,
            B_W => open,
            B_endcol => open,
            B_data => open,
            L_latch => open,
            L_clk => open,
            R_endrow => endrow_11_12,
            R_data => data_11_12,
            R_clk => clock_11_12,
            R_latch => latch_11_12
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



    capture_data: process(clk)
    begin
        if rising_edge(clk) then
            if latch = '0' then
                -- shift a sinistra: il nuovo bit entra dalla posizione 0
                sr_controllo <= sr_controllo(62 downto 0) & data;
            end if;
        end if;
    end process;



    -- Stimolo principale
    stim_proc: process
    begin

        latch <= '1';  -- stato di reset
        wait for 5 ns;
        latch <= '0'; -- shifting

        clk_en <= '1';
        wait for CLK_PERIOD * 100;
        clk_en <= '0';

        wait for 20 ns;





        --wait for CLK_PERIOD * 2;
        wait;
    end process;

end sim;
