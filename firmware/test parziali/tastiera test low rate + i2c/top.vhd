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
    SIGNAL i2c_addr      : STD_LOGIC_VECTOR(6 DOWNTO 0) := "0111100"; -- Es. Indirizzo 0x3C (display OLED)
    SIGNAL i2c_rw        : STD_LOGIC := '0';                          -- '0' = Scrittura
    SIGNAL i2c_data_wr   : STD_LOGIC_VECTOR(7 DOWNTO 0) := x"A5";     -- Dato da inviare: 0xA5
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
            -- Campi opzionali superflui omessi per brevità
            LATCH_INPUT_VALUE : in std_logic := '0';
            CLOCK_ENABLE      : in std_logic := '0';
            INPUT_CLK         : in std_logic := '0';
            OUTPUT_CLK        : in std_logic := '0';
            D_OUT_1           : in std_logic := '0';
            D_IN_1            : out std_logic
        );
    end component;

    signal clk_counter : unsigned(25 downto 0) := (others => '0');  -- contatore per il clock principale
    signal clk_low : std_logic;
    signal reset : std_logic;

    signal tile_stream : std_logic_vector(15 downto 0);    -- 2 byte per lo stato di una tile
    signal pb_counter : unsigned(4 downto 0);       -- contatore per i bit della tile
    signal byteHL : unsigned(1 downto 0); -- conta i byte inviati

    type state_pull_t is (
        idle,   -- attende che la prima FSM sia in scanning
        r1,     -- alza il reset
        r2,     -- abbassa il reset e prepara a prendere il primo bit
        c1,     -- clock alto
        get_bit,    -- carica bit e incrementa il contatore
        s1,     -- abilita il sender e attende per il segnale ack_send
        s2,     -- aspettiamo che ack_send torni a zero, indicando che il sender è di nuovo in idle
        done,
        err
    );
    signal state : state_pull_t := idle;
    signal next_state : state_pull_t := idle;

begin

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


    reset <= not reset_n;
    led_blue <= reset_n;
    --led_red <= not clk_low;
    --led_green <= not data;


    led_red <= '0' when state = idle else '1';
    led_green <= '0' when state = r1 else '1';

    ----------------------------------------------------------------
    -- 1. GENERATORE DI CLOCK ENABLE (STROBE)
    -- Questo processo gira alla massima velocità del clock globale.
    -- Alza il segnale clk_en a '1' per UN SOLO ciclo di clk_in ogni 4.
    ----------------------------------------------------------------
    -- gen_enable : process(clk_in)
    -- begin
    --     if rising_edge(clk_in) then
    --         if reset = '1' then
    --             clk_counter <= (others => '0');
    --             clk_low  <= '0';
    --         else
    --             if clk_counter = 1 then  -- Conta: 0, 1, 2, 3 (quattro cicli)
    --                 clk_counter <= (others => '0');
    --                 clk_low  <= '1'; -- Impulso alto per un solo ciclo di clk_in
    --             else
    --                 clk_counter <= clk_counter + 1;
    --                 clk_low  <= '0'; -- Torna subito a zero al ciclo successivo
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
        -- di default così non dobbiamo scrivere sempre l'ELSE
        next_state <= state;

        case state is
            when idle => next_state <= r1;
            when r1 => next_state <= r2;
            when r2 => next_state <= get_bit;
            when get_bit => next_state <= c1;
            when c1 =>  -- controlliamo se abbiamo raccolto tutti i 16 bit
                if pb_counter = 16 then
                    if i2c_busy = '0' then
                        next_state <= s1; -- allora possiamo inviare
                    else
                        next_state <= c1; -- dobbiamo attendere ancora
                    end if;
                else
                    next_state <= get_bit;
                end if;
            when s1 => -- stiamo qui fino a che busy non è 1
                if i2c_busy = '1' then
                    next_state <= s2;
                end if;
            when s2 => -- attendiamo che abbia completato la tramissione
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
                -- valori di default
                clk_out <= '0';
                latch <= '0';

                -- quando entriamo nello stato, le cose scritte qua vengono subito eseguite
                case next_state is     -- controlliamo lo stato successivo per non perdere un ciclo
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
                        i2c_ena <= '1';  -- facciamo partire la tramissione
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











