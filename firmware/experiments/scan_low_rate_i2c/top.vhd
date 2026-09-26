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

        package_sda : inout std_logic;
        package_scl : inout std_logic;

        led_blue    : out std_logic;
        led_red     : out std_logic;
        led_green   : out std_logic
    );
end top;

architecture behavioral of top is

    COMPONENT i2c_master
        GENERIC(
        input_clk : INTEGER := 12_000_000;
        bus_clk   : INTEGER := 100_000
        );
        PORT(
        clk       : IN     STD_LOGIC;
        reset_n   : IN     STD_LOGIC;
        ena       : IN     STD_LOGIC;
        addr      : IN     STD_LOGIC_VECTOR(6 DOWNTO 0);
        rw        : IN     STD_LOGIC;
        data_wr   : IN     STD_LOGIC_VECTOR(7 DOWNTO 0);
        busy      : OUT    STD_LOGIC;
        data_rd   : OUT    STD_LOGIC_VECTOR(7 DOWNTO 0);
        ack_error : BUFFER STD_LOGIC;
        sda_in    : IN     STD_LOGIC;
        sda_en    : OUT    STD_LOGIC;
        scl_in    : IN     STD_LOGIC;
        scl_en    : OUT    STD_LOGIC
        );
    END COMPONENT;

    SIGNAL i2c_ena       : STD_LOGIC := '0';
    SIGNAL i2c_addr      : STD_LOGIC_VECTOR(6 DOWNTO 0) := "0111100"; -- e.g. address 0x3C (OLED display)
    SIGNAL i2c_rw        : STD_LOGIC := '0';                          -- '0' = write
    SIGNAL i2c_data_wr   : STD_LOGIC_VECTOR(7 DOWNTO 0) := x"A5";     -- Data to send: 0xA5
    SIGNAL i2c_busy      : STD_LOGIC;
    SIGNAL i2c_ack_error : STD_LOGIC;

    SIGNAL i2c_scl_in    : STD_LOGIC;
    SIGNAL i2c_scl_en    : STD_LOGIC;
    SIGNAL i2c_sda_in    : STD_LOGIC;
    SIGNAL i2c_sda_en    : STD_LOGIC;

    component SB_IO is
        generic ( PIN_TYPE : std_logic_vector(5 downto 0) := "000000" );
        port (
            PACKAGE_PIN   : inout std_logic;
            OUTPUT_ENABLE : in    std_logic := '0';
            D_OUT_0       : in    std_logic := '0';
            D_IN_0        : out   std_logic;
            -- Optional fields omitted for brevity
            LATCH_INPUT_VALUE : in std_logic := '0';
            CLOCK_ENABLE      : in std_logic := '0';
            INPUT_CLK         : in std_logic := '0';
            OUTPUT_CLK        : in std_logic := '0';
            D_OUT_1           : in std_logic := '0';
            D_IN_1            : out std_logic
        );
    end component;

    signal clk_counter : unsigned(25 downto 0) := (others => '0');  -- main clock divider counter
    signal clk_low : std_logic;
    signal reset : std_logic;

    signal tile_stream : std_logic_vector(15 downto 0);    -- 2 bytes: raw frame of one tile
    signal pb_counter : unsigned(4 downto 0);       -- bit counter within a tile frame
    signal byteHL : unsigned(1 downto 0); -- counts the bytes sent

    type state_pull_t is (
        idle,   -- wait for the main FSM to be in scanning
        r1,     -- raise the latch (parallel load of the tiles)
        r2,     -- release the latch and prepare to read the first bit
        c1,     -- board clock high
        get_bit,    -- sample one bit and increment the bit counter
        s1,     -- enable the sender and wait for ack_send
        s2,     -- wait for ack_send to return low, i.e. the sender is idle again
        done,
        err
    );
    signal state : state_pull_t := idle;
    signal next_state : state_pull_t := idle;

begin

    -- Physical I/O buffer for SDA instantiated in the top level
    sda_hardware_io : SB_IO
        generic map ( PIN_TYPE => "101001" ) -- Tristate out + simple in
        port map (
            PACKAGE_PIN   => package_sda,       -- Connected DIRECTLY to the physical pin
            OUTPUT_ENABLE => i2c_sda_en,    -- Driven by the internal I2C logic
            D_OUT_0       => '0',       -- Drive '0' when OE is high
            D_IN_0        => i2c_sda_in,    -- Feed the pin value back to the logic
            D_IN_1        => open
        );

    -- Physical I/O buffer for SCL instantiated in the top level
    scl_hardware_io : SB_IO
        generic map ( PIN_TYPE => "101001" )
        port map (
            PACKAGE_PIN   => package_scl,       -- Connected DIRECTLY to the physical pin
            OUTPUT_ENABLE => i2c_scl_en,    -- Driven by the internal I2C logic
            D_OUT_0       => '0',       -- Drive '0' when OE is high
            D_IN_0        => i2c_scl_in,    -- Feed the pin value back to the logic (needed for clock stretching)
            D_IN_1        => open
        );

    -- I2C master IP port map
    i2c_inst : i2c_master
        PORT MAP(
        clk       => clk_in,
        reset_n   => reset_n,
        ena       => i2c_ena,
        addr      => i2c_addr,
        rw        => i2c_rw,
        data_wr   => i2c_data_wr,
        busy      => i2c_busy,
        data_rd   => OPEN,          -- No reads in this example
        ack_error => i2c_ack_error,
        sda_in    => i2c_sda_in,       -- Connected directly to the output pin
        sda_en    => i2c_sda_en,
        scl_in    => i2c_scl_in,        -- Connected directly to the output pin
        scl_en    => i2c_scl_en
        );


    reset <= not reset_n;
    led_blue <= reset_n;
    --led_red <= not clk_low;
    --led_green <= not data;


    led_red <= '0' when state = idle else '1';
    led_green <= '0' when state = r1 else '1';

    ----------------------------------------------------------------
    -- 1. CLOCK ENABLE (STROBE) GENERATOR
    -- This process runs at the full global clock rate.
    -- Raise clk_en to '1' for ONE clk_in cycle out of every 4.
    ----------------------------------------------------------------
    -- gen_enable : process(clk_in)
    -- begin
    --     if rising_edge(clk_in) then
    --         if reset = '1' then
    --             clk_counter <= (others => '0');
    --             clk_low  <= '0';
    --         else
    --             if clk_counter = 1 then  -- Count: 0, 1, 2, 3 (four cycles)
    --                 clk_counter <= (others => '0');
    --                 clk_low  <= '1'; -- High pulse for a single clk_in cycle
    --             else
    --                 clk_counter <= clk_counter + 1;
    --                 clk_low  <= '0'; -- Back to zero on the next cycle
    --             end if;
    --         end if;
    --     end if;
    -- end process;

    clk_low <= '1';


    fsm_clocking : process(clk_in, reset)
    begin
        if rising_edge(clk_in) then
            if reset = '1' then
                state <= idle;
            elsif clk_low = '1' then
                state <= next_state;
            end if;
        end if;
    end process;

    fsm_next : process(clk_low, state, pb_counter, tile_stream, i2c_busy, byteHL)
    begin
        -- default assignment, so no ELSE branch is needed everywhere
        next_state <= state;

        case state is
            when idle => next_state <= r1;
            when r1 => next_state <= r2;
            when r2 => next_state <= get_bit;
            when get_bit => next_state <= c1;
            when c1 =>  -- have all 16 bits of the frame been collected?
                if pb_counter = 16 then
                    if i2c_busy = '0' then
                        next_state <= s1; -- then we can send
                    else
                        next_state <= c1; -- keep waiting
                    end if;
                else
                    next_state <= get_bit;
                end if;
            when s1 => -- stay here until busy is 1
                if i2c_busy = '1' then
                    next_state <= s2;
                end if;
            when s2 => -- wait for the transmission to complete
                if i2c_busy = '0' then
                    if byteHL >= 2 then
                        next_state <= done;
                    else
                        next_state <= s1;
                    end if;
                end if;
            when done => next_state <= done;
            when others => next_state <= err;
        end case;
    end process;

    fsm_output : process(clk_in, reset)
    begin
        if rising_edge(clk_in) then
            if reset = '1' then
                clk_out <= '0';
                latch <= '0';
                tile_stream <= (others => '0');
                pb_counter <= (others => '0');
                byteHL <= (others => '0');
            elsif clk_low = '1' then
                -- default values
                clk_out <= '0';
                latch <= '0';

                -- outputs are decoded from the NEXT state so they take effect on entering it
                case next_state is     -- look at the next state to avoid losing one cycle
                    when idle =>
                        null;

                    when r1 =>
                        latch <= '1';

                    when r2 =>
                        pb_counter <= (others => '0');

                    when get_bit =>
                        pb_counter <= pb_counter + 1;
                        tile_stream <= tile_stream(14 downto 0) & data;

                    when c1 =>
                        clk_out <= '1';
                        i2c_data_wr <= tile_stream(15 downto 8);

                    when s1 =>
                        i2c_ena <= '1';  -- start the transmission
                        if state /= s1 then
                            byteHL <= byteHL + 1;
                        end if;

                    when s2 =>
                        i2c_ena <= '0';
                        i2c_data_wr <= tile_stream(7 downto 0);

                    when others =>
                        null;

                end case;
            end if;
        end if;
    end process;






end behavioral;











