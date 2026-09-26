LIBRARY ieee;
USE ieee.std_logic_1164.all;

ENTITY top IS
  PORT(
    clk_in      : IN    STD_LOGIC; -- Clock di sistema (es. 50 MHz)
    reset_n     : IN    STD_LOGIC; -- Tasto di reset (attivo basso)

    -- Pin fisici della FPGA da collegare al bus I2C esterno
    package_sda     : INOUT STD_LOGIC;
    package_scl     : INOUT STD_LOGIC;

    -- LED di stato sulla FPGA
    led_blue    : OUT   STD_LOGIC; -- Si accende quando l'invio è terminato
    led_red     : OUT   STD_LOGIC;  -- Si accende se c'è stato un NACK dallo slave
    led_green   : out STD_LOGIC
  );
END top;

ARCHITECTURE behavioral OF top IS

  -- 1. Dichiarazione del tuo IP i2c_master
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

  -- Primitiva iCE40 SB_IO
  component SB_IO is
      generic ( PIN_TYPE : std_logic_vector(5 downto 0) := "000000" );
      port (
          PACKAGE_PIN   : inout std_logic;
          OUTPUT_ENABLE : in    std_logic := '0';
          D_OUT_0       : in    std_logic := '0';
          D_IN_0        : out   std_logic;
          -- Campi opzionali superflui omessi per brevità
          LATCH_INPUT_VALUE : in std_logic := '0';
          CLOCK_ENABLE      : in std_logic := '0';
          INPUT_CLK         : in std_logic := '0';
          OUTPUT_CLK        : in std_logic := '0';
          D_OUT_1           : in std_logic := '0';
          D_IN_1            : out std_logic
      );
  end component;

  -- 2. Segnali di interconnessione con l'IP
  SIGNAL i2c_ena       : STD_LOGIC := '0';
  SIGNAL i2c_addr      : STD_LOGIC_VECTOR(6 DOWNTO 0) := "0111100"; -- Es. Indirizzo 0x3C (display OLED)
  SIGNAL i2c_rw        : STD_LOGIC := '0';                          -- '0' = Scrittura
  SIGNAL i2c_data_wr   : STD_LOGIC_VECTOR(7 DOWNTO 0) := x"A5";     -- Dato da inviare: 0xA5
  SIGNAL i2c_busy      : STD_LOGIC;
  SIGNAL i2c_ack_error : STD_LOGIC;

  SIGNAL i2c_scl_in    : STD_LOGIC;
  SIGNAL i2c_scl_en    : STD_LOGIC;
  SIGNAL i2c_sda_in    : STD_LOGIC;
  SIGNAL i2c_sda_en    : STD_LOGIC;

  -- 3. Stati della Macchina a Stati (FSM)
  TYPE state_type IS (IDLE, START_TX, WAIT_BUSY_HIGH, WAIT_BUSY_LOW, DONE);
  SIGNAL state : state_type := IDLE;

  signal lb : std_logic;
  signal lr : std_logic;

BEGIN

  -- Buffer hardware fisico per SDA inserito nel TOP
  sda_hardware_io : SB_IO
      generic map ( PIN_TYPE => "101001" ) -- Tristate Out + Simple In
      port map (
          PACKAGE_PIN   => package_sda,       -- Connesso DIRETTAMENTE al pin fisico del chip
          OUTPUT_ENABLE => i2c_sda_en,    -- Guidato dalla logica interna dell'I2C
          D_OUT_0       => '0',       -- Forza a massa '0' quando OE è alto
          D_IN_0        => i2c_sda_in,    -- Riporta il valore letto alla logica interna
          D_IN_1        => open
      );

  -- Buffer hardware fisico per SCL inserito nel TOP
  scl_hardware_io : SB_IO
      generic map ( PIN_TYPE => "101001" )
      port map (
          PACKAGE_PIN   => package_scl,       -- Connesso DIRETTAMENTE al pin fisico del chip
          OUTPUT_ENABLE => i2c_scl_en,    -- Guidato dalla logica interna dell'I2C
          D_OUT_0       => '0',       -- Forza a massa '0' quando OE è alto
          D_IN_0        => i2c_scl_in,    -- Riporta il valore letto alla logica interna (indispensabile per clock stretching)
          D_IN_1        => open
      );

  -- Mappatura dell'IP I2C Master
  i2c_inst : i2c_master
    PORT MAP(
      clk       => clk_in,
      reset_n   => reset_n,
      ena       => i2c_ena,
      addr      => i2c_addr,
      rw        => i2c_rw,
      data_wr   => i2c_data_wr,
      busy      => i2c_busy,
      data_rd   => OPEN,          -- Non ci interessa leggere dati in questo esempio
      ack_error => i2c_ack_error,
      sda_in    => i2c_sda_in,       -- Collegato direttamente al pin di uscita
      sda_en    => i2c_sda_en,
      scl_in    => i2c_scl_in,        -- Collegato direttamente al pin di uscita
      scl_en    => i2c_scl_en
    );

  -- Processo principale: Macchina a Stati per controllare l'IP
  PROCESS(clk_in, reset_n)
  BEGIN
    IF reset_n = '0' THEN
      state      <= IDLE;
      i2c_ena    <= '0';
      lr   <= '1';
      lb  <= '1';

    ELSIF rising_edge(clk_in) THEN
      CASE state IS

        -- STATO 0: Attesa della pressione del tasto Start
        WHEN IDLE =>
          lr  <= '1';
          lb <= '1';
          IF i2c_busy = '0' then
            state <= START_TX;
          end if;

        -- STATO 1: Lancia il comando all'IP
        WHEN START_TX =>
          i2c_ena <= '1'; -- Alza l'enable per dire all'IP di partire
          state   <= WAIT_BUSY_HIGH;

        -- STATO 2: Attendi che l'IP registri il comando e inizi
        WHEN WAIT_BUSY_HIGH =>
          IF i2c_busy = '1' THEN
            i2c_ena <= '0'; -- Abbassa l'enable! (Altrimenti l'IP continua a mandare dati all'infinito)
            state   <= WAIT_BUSY_LOW;
          END IF;

        -- STATO 3: Attendi che l'IP finisca di inviare tutto e mandi lo STOP
        WHEN WAIT_BUSY_LOW =>
          IF i2c_busy = '0' THEN
            state <= DONE;
          END IF;

        -- STATO 4: Transazione completata. Legge l'errore e si blocca qui
        WHEN DONE =>
          lr <= '0'; -- Segnala la fine
          IF i2c_ack_error = '1' THEN
            lb <= '0'; -- Se lo slave non ha risposto (NACK), accende il LED di errore
          END IF;
          state <= DONE;
          -- Rimane in questo stato finché non si preme il tasto di reset_n
          -- (Se vuoi che riparta, potresti rimetterlo in IDLE dopo un delay)

      END CASE;
    END IF;
  END PROCESS;

  led_green <= i2c_ena;
  led_red <= lr;
  led_blue <= i2c_busy;

END behavioral;
