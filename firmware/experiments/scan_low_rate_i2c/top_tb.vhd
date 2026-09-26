LIBRARY ieee;
USE ieee.std_logic_1164.all;

ENTITY top_tb IS
-- A testbench has no external ports.
END top_tb;

ARCHITECTURE sim OF top_tb IS

    -- 1. Unit under test (UUT) declaration
    COMPONENT top
        PORT(
            clk_in    : IN    STD_LOGIC;
            reset_n   : IN    STD_LOGIC;
            package_sda   : INOUT STD_LOGIC;
            package_scl   : INOUT STD_LOGIC;
            led_blue  : OUT   STD_LOGIC;
            led_red   : OUT   STD_LOGIC;
            led_green : out STD_LOGIC;

            clk_out     : out std_logic;
            latch       : out std_logic;
            data        : in std_logic
        );
    END COMPONENT;

    -- 2. Testbench signals driving the UUT
    SIGNAL clk_tb    : STD_LOGIC := '0';
    SIGNAL reset_n_tb: STD_LOGIC := '0';
    SIGNAL sda_tb    : STD_LOGIC;
    SIGNAL scl_tb    : STD_LOGIC;
    SIGNAL led_b_tb  : STD_LOGIC;
    SIGNAL led_r_tb  : STD_LOGIC;
    signal led_g_tb : STD_LOGIC;
    signal data_tb : std_logic;
    signal clk_out_tb : std_logic;
    signal latch_tb : std_logic;

    signal state : std_logic_vector(11 downto 0) := "110101100101";

    -- Timing constants (12 MHz, the pico-ice clock)
    CONSTANT clk_period : TIME := 1 sec / 12_000_000; -- about 83.33 ns

BEGIN

    -- 3. Instantiate the unit under test (UUT)
    uut: top
        PORT MAP (
            clk_in    => clk_tb,
            reset_n   => reset_n_tb,
            package_sda   => sda_tb,
            package_scl   => scl_tb,
            led_blue  => led_b_tb,
            led_red   => led_r_tb,
            led_green => led_g_tb,
            data => data_tb,
            latch => latch_tb,
            clk_out => clk_out_tb
        );

    -- 4. Model of the I2C bus pull-up resistors (essential!)
    -- I2C lines are open-drain: when nobody drives them they go to 'H' (weak high)
    sda_tb <= 'H';
    scl_tb <= 'H';

    -- 5. Clock generator (runs forever)
    clk_process : PROCESS
    BEGIN
        clk_tb <= '0';
        WAIT FOR clk_period / 2;
        clk_tb <= '1';
        WAIT FOR clk_period / 2;
    END PROCESS;

    -- 6. Stimuli (reset, then emulated slave responses)
    stimulus_process : PROCESS
    BEGIN
        -- Apply the initial reset
        reset_n_tb <= '0';
        WAIT FOR 5 * clk_period;
        reset_n_tb <= '1'; -- Release the reset; the top-level FSM moves to START_TX

        WAIT;
    END PROCESS;


    -- on every BOARD_CLK pulse present the next bit of the emulated frame
    data_tb <= state(11);

    sdv : PROCESS(clk_out_tb)
    begin
        if latch_tb = '1' then
            state <= "110101100101";
        elsif rising_edge(clk_out_tb) then
            state(11 downto 0) <= state(10 downto 0) & state(11);
        end if;
    end process;

END sim;
