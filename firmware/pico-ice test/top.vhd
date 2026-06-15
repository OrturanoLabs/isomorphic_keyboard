library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity top is
    Port (
        CLK_IN      : in std_logic;
        RESET_N     : in std_logic;

        BOARD_CLK   : out std_logic;
        BOARD_DATA  : in std_logic;
        BOARD_LATCH : out std_logic;

        LED_BLUE    : out std_logic;
        LED_GREEN   : out std_logic;
        LED_RED     : out std_logic;

        PACKAGE_SDA : inout std_logic;
        PACKAGE_SCL : inout std_logic
    );
end top;

architecture behavioral of top is

    component SB_IO is
        generic (
            PIN_TYPE : std_logic_vector(5 downto 0) := "000000" );
        port (
            PACKAGE_PIN         : inout std_logic;
            OUTPUT_ENABLE       : in std_logic := '0';
            D_OUT_0             : in std_logic := '0';
            D_IN_0              : out std_logic;

            LATCH_INPUT_VALUE   : in std_logic := '0';
            CLOCK_ENABLE        : in std_logic := '0';
            INPUT_CLK           : in std_logic := '0';
            OUTPUT_CLK          : in std_logic := '0';
            D_OUT_1             : in std_logic := '0';
            D_IN_1              : out std_logic
        );
    end component;

    -- dichiarazione del componente per l'i2c
    component i2c_master
        generic(
            INPUT_CLK           : integer := 12_000_000;
            BUS_CLK             : integer := 100_000
        );
        port (
            CLK                 : in std_logic;
            RESET_N             : in std_logic;
            ENA                 : in std_logic;
            ADDR                : in std_logic_vector(6 downto 0);
            RW                  : in std_logic;
            DATA_WR             : in std_logic_vector(7 downto 0);
            BUSY                : out std_logic;
            DATA_RD             : out std_logic_vector(7 downto 0);
            ACK_ERROR           : buffer std_logic;
            SDA_IN              : in std_logic;
            SDA_EN              : out std_logic;
            SCL_IN              : in std_logic;
            SCL_EN              : out std_logic
        );
    end component;

    -- segnali interni per collegare la nostra logica all'IP I2C
    signal i2c_ena     : std_logic := '0';
    signal i2c_addr    : std_logic_vector(6 downto 0) := "1010101"; -- indirizzo del RP2040
    signal i2c_rw      : std_logic := '0'; -- 0 = scrittura
    signal i2c_data_wr : std_logic_vector(7 downto 0);
    signal i2c_busy    : std_logic;
    signal i2c_ack_err : std_logic;

    signal i2c_scl_in  : std_logic;
    signal i2c_scl_en  : std_logic;
    signal i2c_sda_in  : std_logic;
    signal i2c_sda_en  : std_logic;


    signal clk_counter : unsigned(11 downto 0) := (others => '0');  -- contatore per il clock principale
    signal en_clk_scan : std_logic := '0';  -- divisore per il clock di scansione della griglia
    signal reset : std_logic;

    signal sender_fsm_enable : std_logic := '0'; -- handshake per inviare i dati di una tile
    signal sender_fsm_busy : std_logic := '0'; -- handshake dati della tile inviati

    type state_main_t is (
        idle,   -- stato iniziale
        scanning,   -- operazione di scansione. Quanto è in questo stato è attiva anche la seconda FSM
        err     -- stato di errore / fallback
    );

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

    type state_sender_t is (
        idle,   -- attende che la seconda FSM abbia raccolto una tile
        start_tx,
        wait_busy,
        wait_finish,
        f1,     -- alza ack_send e aspetta che si abbassi en_send
        err     -- stato di errore / fallback
    );

    signal state_main : state_main_t := idle;
    signal state_pull : state_pull_t := idle;
    signal state_sender : state_sender_t := idle;
    signal next_state_pull : state_pull_t := idle;
    signal next_state_sender : state_sender_t := idle;

    signal tile_stream : std_logic_vector(15 downto 0);    -- 2 byte per lo stato di una tile
    signal pb_counter : unsigned(4 downto 0);       -- contatore per i bit della tile
    signal tile_counter : unsigned(5 downto 0);     -- contatore delle tile

begin
    reset <= not RESET_N;

    -- buffer hardware fisico per SDA
    sda_hardware_io : SB_IO
        generic map ( PIN_TYPE => "101001" ) -- tristate out + simple in
        port map (
            PACKAGE_PIN   => PACKAGE_SDA,
            OUTPUT_ENABLE => i2c_sda_en,
            D_OUT_0       => '0',
            D_IN_0        => i2c_sda_in,
            D_IN_1        => open
        );

    -- buffer hardware fisico per SCL
    scl_hardware_io : SB_IO
        generic map ( PIN_TYPE => "101001" )
        port map (
            PACKAGE_PIN   => PACKAGE_SCL,
            OUTPUT_ENABLE => i2c_scl_en,
            D_OUT_0       => '0',
            D_IN_0        => i2c_scl_in,
            D_IN_1        => open
        );

    i2c_inst : i2c_master
        port map(
            CLK           => CLK_IN,
            RESET_N       => RESET_N,
            ENA           => i2c_ena,
            ADDR          => i2c_addr,
            RW            => i2c_rw,
            DATA_WR       => i2c_data_wr,
            BUSY          => i2c_busy,
            DATA_RD       => open,
            ACK_ERROR     => i2c_ack_err,
            SDA_IN        => i2c_sda_in,
            SDA_EN        => i2c_sda_en,
            SCL_IN        => i2c_scl_in,
            SCL_EN        => i2c_scl_en
        );


    -- genera il clock enable per la prima FSM
    main_clocking : process(CLK_IN)
    begin
        if rising_edge(CLK_IN) then
            if RESET_N = '0' then
                clk_counter <= (others => '0');
                en_clk_scan <= '0';
            else
                if clk_counter = 16 then
                     clk_counter <= (others => '0');
                     en_clk_scan  <= '1';
                 else
                     clk_counter <= clk_counter + 1;
                     en_clk_scan  <= '0';
                 end if;
            end if;
        end if;
    end process;


    main_fsm : process(CLK_IN)
    begin
        if rising_edge(CLK_IN) then
            if RESET_N = '0' then
                state_main <= idle;
            elsif en_clk_scan = '1' then
                case state_main is
                    when idle => state_main <= scanning;
                    when scanning => state_main <= scanning;
                    when others => state_main <= err;
                end case;
            end if;
        end if;
    end process;


    pull_fsm_clocking : process(CLK_IN)
    begin
        if rising_edge(CLK_IN) then
            if RESET_N = '0' then
                state_pull <= idle;
            elsif en_clk_scan = '1' then
                state_pull <= next_state_pull;
            end if;
        end if;
    end process;

    pull_fsm_next : process(state_pull, state_main, pb_counter, tile_stream, sender_fsm_busy)
    begin
        -- di default così non dobbiamo scrivere sempre l'ELSE
        next_state_pull <= state_pull;

        case state_pull is
            when idle =>
                if state_main = scanning then
                    next_state_pull <= r1;
                end if;
            when r1 => next_state_pull <= r2;
            when r2 => next_state_pull <= get_bit;
            when get_bit => next_state_pull <= c1;
            when c1 =>  -- controlliamo se abbiamo raccolto tutti i 16 bit
                if pb_counter = 16 then
                    -- controlliamo che i bit di controllo siano giusti
                    --if tile_stream(13) = '1' and tile_stream(12) = '1' then
                        if sender_fsm_busy = '0' then -- controlliamo se il sender è pronto
                            next_state_pull <= s1; -- allora possiamo inviare
                        end if;
                    --else
                    --    next_state_pull <= err; -- altrimenti c'è un errore
                    --end if;
                else
                    next_state_pull <= get_bit;
                end if;
            when s1 =>
                if sender_fsm_busy = '1' then
                    next_state_pull <= s2;
                end if;
            when s2 =>
                if sender_fsm_busy = '0' then
                    next_state_pull <= done;
                    -- controlliamo se abbiamo finito la griglia
                    --if tile_stream(15) = '1' and tile_stream(14) = '1' then
                        -- se siamo all'ultima tile
                    --    next_state_pull <= idle;
                    --else
                    --    next_state_pull <= r2;
                    --end if;
                end if;
            when done => next_state_pull <= done;
            when others => next_state_pull <= err;
        end case;
    end process;

    pull_fsm_output : process(CLK_IN)
    begin
        if rising_edge(CLK_IN) then
            if RESET_N = '0' then
                BOARD_CLK <= '0';
                BOARD_LATCH <= '0';
                sender_fsm_enable <= '0';
                tile_stream <= (others => '0');
                pb_counter <= (others => '0');
                tile_counter <= (others => '0');
            elsif en_clk_scan = '1' then
                -- valori di default
                BOARD_CLK <= '0';
                BOARD_LATCH <= '0';
                sender_fsm_enable <= '0';

                -- quando entriamo nello stato, le cose scritte qua vengono subito eseguite
                case next_state_pull is     -- controlliamo lo stato successivo per non perdere un ciclo
                    when idle =>
                        null;

                    when r1 =>
                        BOARD_LATCH <= '1';
                        tile_counter <= (others => '0');

                    when r2 =>
                        pb_counter <= (others => '0');
                        tile_counter <= tile_counter + 1;

                    when get_bit =>
                        pb_counter <= pb_counter + 1;
                        tile_stream <= tile_stream(14 downto 0) & BOARD_DATA;

                    when c1 =>
                        BOARD_CLK <= '1';

                    when s1 =>
                        sender_fsm_enable <= '1';

                    when s2 =>
                        null;

                    when others =>
                        null;

                end case;
            end if;
        end if;
    end process;


    sender_fsm_clocking : process(CLK_IN)
    begin
        if rising_edge(CLK_IN) then
            if RESET_N = '0' then
                state_sender <= idle;
            else
                state_sender <= next_state_sender;
            end if;
        end if;
    end process;

    sender_fsm_next : process(state_sender, sender_fsm_enable, i2c_busy)
    begin
        next_state_sender <= state_sender;

        case state_sender is
            when idle =>
                if sender_fsm_enable = '1' then -- attende che venga dato il segnale per inviare i file
                    if i2c_busy = '0' then  -- attende che il modulo i2c sia pronto
                        next_state_sender <= start_tx;
                    end if;
                end if;
            when start_tx => next_state_sender <= wait_busy;
            when wait_busy =>
                if i2c_busy = '1' then  -- aspettiamo che il modulo prenda il dato
                    next_state_sender <= wait_finish;
                end if;
            when wait_finish =>
                if i2c_busy = '0' then
                    --if i2c_ack_err = '1' then
                    --    next_state_sender <= err;
                    --else
                        next_state_sender <= f1;
                    --end if;
                end if;
            when f1 =>  -- aspettiamo che si spenga en_send
                if sender_fsm_enable = '0' then
                    next_state_sender <= idle;
                end if;
            when others => next_state_sender <= err;
        end case;
    end process;

    sender_fsm_output : process(clk_in, reset)
    begin
        if reset = '1' then
            i2c_ena <= '0';
            sender_fsm_busy <= '1';
        elsif rising_edge(clk_in) then
            -- defaults:
            i2c_ena <= '0';
            sender_fsm_busy <= '1';

            case next_state_sender is
                when idle =>
                    sender_fsm_busy <= '0'; -- solo quando siamo in idle, la fsm segnala di essere pronta

                when start_tx =>
                    i2c_addr <= "1010101"; -- indirizzo slave RP2040
                    i2c_data_wr <= tile_stream(15 downto 8);
                    i2c_rw <= '0';

                when wait_busy =>
                    i2c_ena <= '1';        -- diciamo all'IP di partire

                when wait_finish =>
                    null;

                when f1 =>
                    null;

                when others => null;

            end case;
        end if;
    end process;




end behavioral;











