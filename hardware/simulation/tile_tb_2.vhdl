library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tile_tb_2 is
end tile_tb_2;

architecture sim of tile_tb_2 is

  signal buttons11    : std_logic_vector(11 downto 0);
  signal buttons21    : std_logic_vector(11 downto 0);
  signal buttons12    : std_logic_vector(11 downto 0);
  signal buttons22    : std_logic_vector(11 downto 0);
  signal buttons32    : std_logic_vector(11 downto 0);

  signal latch, clk, data : std_logic;

  constant CLK_PERIOD : time := 10 ns;

  signal clk_en : std_logic := '0';

  -- sengali di collegamento fra 11 e 21
  signal W_11_21, endcol_11_21, first_11_21, latch_11_21, clock_11_21, data_11_21 : std_logic;
  -- sengali di collegamento fra 11 e 12
  signal endrow_11_12, latch_11_12, clock_11_12, data_11_12 : std_logic;
  -- sengali di collegamento fra 12 e 22
  signal W_12_22, endcol_12_22, first_12_22, latch_12_22, clock_12_22, data_12_22 : std_logic;
  -- sengali di collegamento fra 22 e 32
  signal W_22_32, endcol_22_32, first_22_32, latch_22_32, clock_22_32, data_22_32 : std_logic;
  -- sengali di collegamento fra 21 e 22
  signal endrow_21_22, latch_21_22, clock_21_22, data_21_22 : std_logic;



  signal sr_controllo : std_logic_vector(95 downto 0) := (others => '0');

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
            T_data => data_11_21,
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
            L_endrow => endrow_21_22,
            L_latch => latch_21_22,
            L_clk => clock_21_22,
            L_data => data_21_22,
            R_endrow => open,
            R_data => open
        );

    uut12: entity work.tile
        port map (
            buttons => buttons12,
            T_W => W_12_22,
            T_endcol => endcol_12_22,
            T_first => first_12_22,
            T_latch => latch_12_22,
            T_clk => clock_12_22,
            T_data => data_12_22,
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

    uut22: entity work.tile
        port map (
            buttons => buttons22,
            T_W => W_22_32,
            T_endcol => endcol_22_32,
            T_first => first_22_32,
            T_latch => latch_22_32,
            T_clk => clock_22_32,
            T_data => data_22_32,
            B_W => W_12_22,
            B_endcol => endcol_12_22,
            B_first => first_12_22,
            B_latch => latch_12_22,
            B_clk => clock_12_22,
            B_data => data_12_22,
            L_latch => open,
            L_clk => open,
            R_endrow => endrow_21_22,
            R_data => data_21_22,
            R_clk => clock_21_22,
            R_latch => latch_21_22
        );

    uut32: entity work.tile
        port map (
            buttons => buttons32,
            T_first => open,
            T_latch => open,
            T_clk => open,
            B_W => W_22_32,
            B_endcol => endcol_22_32,
            B_first => first_22_32,
            B_latch => latch_22_32,
            B_clk => clock_22_32,
            B_data => data_22_32,
            L_latch => open,
            L_clk => open,
            R_endrow => open,
            R_data => open
        );



    -- Generatore di Clock (sulla linea R_clk)
    clk_process : process  -- RIMOSSO (clk_en)
    begin
        while true loop
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
                sr_controllo <= sr_controllo(94 downto 0) & data;
            end if;
        end if;
    end process;



    -- Stimolo principale
    stim_proc: process
    begin

        buttons11 <= x"B44";
        buttons21 <= x"C23";
        buttons12 <= x"34D";
        buttons22 <= x"E11";
        buttons32 <= x"F55";

        latch <= '1';  -- stato di reset
        wait for 20 ns;
        latch <= '0'; -- shifting
        wait for 20 ns;

        clk_en <= '1';
        wait for CLK_PERIOD * 95;
        clk_en <= '0';

        wait for 40 ns;




        buttons11 <= x"DF3";
        buttons21 <= x"A31";
        buttons12 <= x"000";
        buttons22 <= x"FFF";
        buttons32 <= x"A34";

        latch <= '1';  -- stato di reset
        wait for 20 ns;
        latch <= '0'; -- shifting
        wait for 20 ns;

        clk_en <= '1';
        wait for CLK_PERIOD * 95;
        clk_en <= '0';

        wait for 40 ns;


        --wait for CLK_PERIOD * 2;
        wait;
    end process;

end sim;
