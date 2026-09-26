library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tile_tb is
end tile_tb;

architecture sim of tile_tb is

  signal buttons11    : std_logic_vector(11 downto 0);
  signal buttons21    : std_logic_vector(11 downto 0);
  signal buttons12    : std_logic_vector(11 downto 0);
  signal buttons13    : std_logic_vector(11 downto 0);
  signal buttons23    : std_logic_vector(11 downto 0);
  signal buttons33    : std_logic_vector(11 downto 0);

  signal latch, clk, data : std_logic;

  constant CLK_PERIOD : time := 10 ns;

  signal clk_en : std_logic := '0';

  -- signals between tile 11 and tile 21
  signal W_11_21, endcol_11_21, first_11_21, latch_11_21, clock_11_21, data_11_21 : std_logic;
  -- signals between tile 11 and tile 12
  signal endrow_11_12, latch_11_12, clock_11_12, data_11_12 : std_logic;
  -- signals between tile 12 and tile 13
  signal endrow_12_13, latch_12_13, clock_12_13, data_12_13 : std_logic;
  -- signals between tile 13 and tile 23
  signal W_13_23, endcol_13_23, first_13_23, latch_13_23, clock_13_23, data_13_23 : std_logic;
  -- signals between tile 23 and tile 33
  signal W_23_33, endcol_23_33, first_23_33, latch_23_33, clock_23_33, data_23_33 : std_logic;


  signal sr_controllo : std_logic_vector(95 downto 0) := (others => '0');

begin

    -- Tile instances
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
            L_endrow => endrow_12_13,
            L_latch => latch_12_13,
            L_clk => clock_12_13,
            L_data => data_12_13,
            R_endrow => endrow_11_12,
            R_data => data_11_12,
            R_clk => clock_11_12,
            R_latch => latch_11_12
        );

    uut13: entity work.tile
        port map (
            buttons => buttons13,
            T_W => W_13_23,
            T_endcol => endcol_13_23,
            T_first => first_13_23,
            T_latch => latch_13_23,
            T_clk => clock_13_23,
            T_data => data_13_23,
            B_W => open,
            B_endcol => open,
            B_data => open,
            L_latch => open,
            L_clk => open,
            R_endrow => endrow_12_13,
            R_data => data_12_13,
            R_clk => clock_12_13,
            R_latch => latch_12_13
        );

    uut23: entity work.tile
        port map (
            buttons => buttons23,
            T_W => W_23_33,
            T_endcol => endcol_23_33,
            T_first => first_23_33,
            T_latch => latch_23_33,
            T_clk => clock_23_33,
            T_data => data_23_33,
            B_W => W_13_23,
            B_endcol => endcol_13_23,
            B_first => first_13_23,
            B_data => data_13_23,
            B_latch => latch_13_23,
            B_clk => clock_13_23,
            L_latch => open,
            L_clk => open,
            R_endrow => open,
            R_data => open
        );

    uut33: entity work.tile
        port map (
            buttons => buttons33,
            T_first => open,
            T_latch => open,
            T_clk => open,
            B_W => W_23_33,
            B_endcol => endcol_23_33,
            B_first => first_23_33,
            B_latch => latch_23_33,
            B_clk => clock_23_33,
            B_data => data_23_33,
            L_latch => open,
            L_clk => open,
            R_endrow => open,
            R_data => open
        );

    -- Clock generator (on the R_clk line)
    clk_process : process  -- gated by clk_en
    begin
        while true loop
            if clk_en = '1' then
                clk <= '0';
                wait for CLK_PERIOD/2;
                clk <= '1';
                wait for CLK_PERIOD/2;
            else
                clk <= '0';
                -- Important: when the clock is disabled we must
                -- wait for clk_en to change, otherwise the loop spins
                -- forever at the same simulation time (hang).
                wait until clk_en = '1';
            end if;
        end loop;
        wait; -- stop everything
    end process;



    capture_data: process(clk)
    begin
        if rising_edge(clk) then
            if latch = '0' then
                -- shift left: the new bit enters at position 0
                sr_controllo <= sr_controllo(94 downto 0) & data;
            end if;
        end if;
    end process;



    -- Main stimulus
    stim_proc: process
    begin

        buttons11 <= x"B44";
        buttons21 <= x"C23";
        buttons12 <= x"34D";
        buttons13 <= x"E11";
        buttons23 <= x"F55";
        buttons33 <= x"AA1";

        latch <= '1';  -- parallel load (latch)
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
        buttons13 <= x"FFF";
        buttons23 <= x"A34";
        buttons33 <= x"843";

        latch <= '1';  -- parallel load (latch)
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
