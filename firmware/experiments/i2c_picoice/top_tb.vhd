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
            led_green : out STD_LOGIC
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
            led_green => led_g_tb
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

        -- The master starts toggling SCL and sending data on SDA.
        -- To avoid an ACK error (led_red on) we must emulate
        -- a slave answering ACK (SDA low on the 9th clock pulse).

        -- Wait for the transaction to start and reach the ninth address bit
        -- WAIT UNTIL falling_edge(scl_tb); -- start condition...
        --
        -- -- Count 8 bits (address + R/W)... on the 9th bit pretend to be the slave
        -- FOR i IN 0 TO 8 LOOP
        --     WAIT UNTIL falling_edge(scl_tb);
        -- END LOOP;
        --
        -- -- The slave pulls SDA low to ACK the address
        -- sda_tb <= '0';
        -- WAIT UNTIL falling_edge(scl_tb); -- end of the ACK bit
        -- sda_tb <= 'Z'; -- Release the line
        --
        -- -- Count 8 more bits (the payload, e.g. 0xA5)
        -- FOR i IN 0 TO 8 LOOP
        --     WAIT UNTIL falling_edge(scl_tb);
        -- END LOOP;
        --
        -- -- The slave pulls SDA low to ACK the data
        -- sda_tb <= '0';
        -- WAIT UNTIL falling_edge(scl_tb);
        -- sda_tb <= 'Z';
        --
        -- -- Let the master finish the STOP condition
        -- WAIT FOR 200 us;
        --
        -- -- Stop the simulation cleanly
        -- ASSERT FALSE REPORT "Simulation completed successfully!" SEVERITY FAILURE;
        WAIT;
    END PROCESS;

END sim;
