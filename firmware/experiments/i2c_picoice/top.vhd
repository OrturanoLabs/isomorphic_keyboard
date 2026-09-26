LIBRARY ieee;
USE ieee.std_logic_1164.all;

ENTITY top IS
  PORT(
    clk_in      : IN    STD_LOGIC; -- System clock (e.g. 50 MHz)
    reset_n     : IN    STD_LOGIC; -- Reset button (active low)

    -- FPGA pins connected to the external I2C bus
    package_sda     : INOUT STD_LOGIC;
    package_scl     : INOUT STD_LOGIC;

    -- Status LEDs on the FPGA board
    led_blue    : OUT   STD_LOGIC; -- On when the transfer has finished
    led_red     : OUT   STD_LOGIC;  -- On when the slave answered NACK
    led_green   : out STD_LOGIC
  );
END top;

ARCHITECTURE behavioral OF top IS

  -- 1. i2c_master IP declaration
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

  -- iCE40 SB_IO primitive
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

  -- 2. Signals connecting the IP
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

  -- 3. FSM states
  TYPE state_type IS (IDLE, START_TX, WAIT_BUSY_HIGH, WAIT_BUSY_LOW, DONE);
  SIGNAL state : state_type := IDLE;

  signal lb : std_logic;
  signal lr : std_logic;

BEGIN

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

  -- Main process: FSM driving the IP
  PROCESS(clk_in, reset_n)
  BEGIN
    IF reset_n = '0' THEN
      state      <= IDLE;
      i2c_ena    <= '0';
      lr   <= '1';
      lb  <= '1';

    ELSIF rising_edge(clk_in) THEN
      CASE state IS

        -- STATE 0: wait for the start button
        WHEN IDLE =>
          lr  <= '1';
          lb <= '1';
          IF i2c_busy = '0' then
            state <= START_TX;
          end if;

        -- STATE 1: issue the command to the IP
        WHEN START_TX =>
          i2c_ena <= '1'; -- Raise the enable to start the IP
          state   <= WAIT_BUSY_HIGH;

        -- STATE 2: wait for the IP to accept the command and start
        WHEN WAIT_BUSY_HIGH =>
          IF i2c_busy = '1' THEN
            i2c_ena <= '0'; -- Drop the enable! (otherwise the IP keeps sending forever)
            state   <= WAIT_BUSY_LOW;
          END IF;

        -- STATE 3: wait for the IP to finish and send STOP
        WHEN WAIT_BUSY_LOW =>
          IF i2c_busy = '0' THEN
            state <= DONE;
          END IF;

        -- STATE 4: transaction done; latch the error flag and stay here
        WHEN DONE =>
          lr <= '0'; -- Signal completion
          IF i2c_ack_error = '1' THEN
            lb <= '0'; -- If the slave did not answer (NACK), light the error LED
          END IF;
          state <= DONE;
          -- Stays here until reset_n is pressed
          -- (to restart, go back to IDLE after a delay)

      END CASE;
    END IF;
  END PROCESS;

  led_green <= i2c_ena;
  led_red <= lr;
  led_blue <= i2c_busy;

END behavioral;
