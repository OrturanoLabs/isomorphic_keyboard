LIBRARY ieee;
USE ieee.std_logic_1164.all;

ENTITY top_tb IS
-- Un testbench non ha porte esterne!
END top_tb;

ARCHITECTURE sim OF top_tb IS

    -- 1. Dichiarazione del componente da testare (UUT)
    COMPONENT top
        PORT(
            CLK_IN      : in std_logic;
            RESET_N     : in std_logic;

            BOARD_CLK   : out std_logic;
            BOARD_DATA  : in std_logic;
            BOARD_LATCH : out std_logic;

            LED_BLUE    : out std_logic;
            LED_GREEN   : out std_logic;
            LED_RED     : out std_logic;

            PACKAGE_MIDI: out std_logic
        );
    END COMPONENT;

    -- 2. Segnali interni del testbench per pilotare la UUT
    SIGNAL clk_tb    : STD_LOGIC := '0';
    SIGNAL reset_n_tb: STD_LOGIC := '0';
    SIGNAL led_b_tb  : STD_LOGIC;
    SIGNAL led_r_tb  : STD_LOGIC;
    signal led_g_tb : STD_LOGIC;
    signal data_tb : std_logic;
    signal clk_out_tb : std_logic;
    signal latch_tb : std_logic;

    signal state : std_logic_vector(47 downto 0) := (others => '0');

    -- Costanti di temporizzazione (12 MHz basato sul tuo codice i2c_master)
    CONSTANT clk_period : TIME := 1 sec / 12_000_000; -- Circa 83.33 ns

BEGIN

    -- 3. Istanziamo la Unit Under Test (UUT)
    uut: top
        PORT MAP (
            clk_in    => clk_tb,
            reset_n   => reset_n_tb,
            led_blue  => led_b_tb,
            led_red   => led_r_tb,
            led_green => led_g_tb,
            board_data => data_tb,
            board_latch => latch_tb,
            board_clk => clk_out_tb
        );

    -- 5. Generatore del Clock (Oscilla all'infinito)
    clk_process : PROCESS
    BEGIN
        clk_tb <= '0';
        WAIT FOR clk_period / 2;
        clk_tb <= '1';
        WAIT FOR clk_period / 2;
    END PROCESS;

    -- 6. Stimoli di test (Reset e simulazione risposta dello Slave)
    stimulus_process : PROCESS
    BEGIN
        -- Applichiamo il reset iniziale
        reset_n_tb <= '0';
        WAIT FOR 5 * clk_period;
        reset_n_tb <= '1'; -- Rilasciamo il reset, la FSM del top passa in START_TX

        WAIT;
    END PROCESS;


    -- per ogni clock out dobbiamo comunicare un preciso bit
    data_tb <= state(47);

    sdv : PROCESS(clk_out_tb, latch_tb)
        variable count : integer := 0;
    begin
        if latch_tb = '1' then
            if count = 0 then
                state <= "001000000000110000000000000011110000000000001111";
            --elsif count = 1 then
                --state <= "000000000000110000000000000011110000001000001111";
            elsif count = 20 then
                state <= "000000000000110000000000000011110000001000001111";
            else
                state <= "000000000000110000000000000011110000000000001111";
            end if;
            count := count + 1;
        elsif rising_edge(clk_out_tb) then
            state(47 downto 0) <= state(46 downto 0) & '0';
        end if;
    end process;

END sim;
