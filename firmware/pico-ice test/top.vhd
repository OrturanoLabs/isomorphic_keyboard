library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity top is
    Port (
        clk_in      : in  std_logic;
        clk_out     : out std_logic;
        data        : in std_logic;
        latch       : out std_logic;
        reset_n     : in std_logic;

        led_blue    : out std_logic;
        led_green   : out std_logic;
        led_red     : out std_logic;

        i2c_sda     : inout std_logic;
        i2c_scl     : inout std_logic
    );
end top;

architecture behavioral of top is

    -- dichiarazione del componente per l'i2c
    component i2c_master is
        generic(
            input_clk : integer;
            bus_clk   : integer);
        port(
            clk       : in    std_logic;
            reset_n   : in    std_logic;
            ena       : in    std_logic;
            addr      : in    std_logic_vector(6 downto 0);
            rw        : in    std_logic;
            data_wr   : in    std_logic_vector(7 downto 0);
            busy      : out   std_logic;
            data_rd   : out   std_logic_vector(7 downto 0);
            ack_error : buffer std_logic;
            sda       : inout std_logic;
            scl       : inout std_logic);
    end component;

    -- segnali interni per collegare la nostra logica all'IP I2C
    signal i2c_ena     : std_logic := '0';
    signal i2c_addr    : std_logic_vector(6 downto 0) := "1010101"; -- indirizzo del RP2040
    signal i2c_rw      : std_logic := '0'; -- 0 = scrittura
    signal i2c_data_wr : std_logic_vector(7 downto 0);
    signal i2c_busy    : std_logic;
    signal i2c_ack_err : std_logic;


    signal clk_counter : unsigned(11 downto 0) := (others => '0');  -- contatore per il clock principale
    signal en_clk_scan : std_logic := '0';  -- divisore per il clock di scansione della griglia
    signal reset : std_logic;

    signal en_send : std_logic := '0'; -- handshake per inviare i dati di una tile
    signal ack_send : std_logic := '0'; -- handshake dati della tile inviati

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
    reset <= not reset_n;
    led_red <= '0';
    led_green <= '1';
    led_blue <= reset;

    -- istanziamento del modulo I2C
    i2c_inst : i2c_master
        generic map (
            input_clk => 12_000_000,
            bus_clk   => 100_000     -- 100 kHz velocità I2C standard
        )
        port map (
            clk       => clk_in,
            reset_n   => reset_n,
            ena       => i2c_ena,
            addr      => i2c_addr,
            rw        => i2c_rw,
            data_wr   => i2c_data_wr,
            busy      => i2c_busy,
            data_rd   => open,       -- non ci serve leggere per ora
            ack_error => i2c_ack_err,
            sda       => i2c_sda,    -- collegato al pin fisico
            scl       => i2c_scl     -- collegato al pin fisico
        );


    -- genera il clock enable per la prima FSM
    process(clk_in)
    begin
        if rising_edge(clk_in) then
            if reset = '1' then
                clk_counter <= (others => '0');
                en_clk_scan <= '0';
            else
                en_clk_scan <= '0';
                clk_counter <= clk_counter + 1;
                if clk_counter = x"FFF" then
                    en_clk_scan <= '1';
                end if;
            end if;
        end if;
    end process;


    main_fsm : process(clk_in, reset)
    begin
        if reset = '1' then
            state_main <= idle;
        elsif rising_edge(clk_in) then
            if en_clk_scan = '1' then
                case state_main is
                    when idle => state_main <= scanning;
                    when scanning => state_main <= scanning;
                    when others => state_main <= err;
                end case;
            end if;
        end if;
    end process;


    pull_fsm_clocking : process(clk_in, reset)
    begin
        if reset = '1' then
            state_pull <= idle;
        elsif rising_edge(clk_in) then
            if en_clk_scan = '1' then
                state_pull <= next_state_pull;
            end if;
        end if;
    end process;

    pull_fsm_next : process(state_pull, state_main, pb_counter, tile_stream, ack_send)
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
                    if tile_stream(13) = '1' and tile_stream(12) = '1' then
                        next_state_pull <= s1; -- allora possiamo inviare
                    else
                        next_state_pull <= err; -- altrimenti c'è un errore
                    end if;
                else
                    next_state_pull <= get_bit;
                end if;
            when s1 =>
                if ack_send = '1' then
                    next_state_pull <= s2;
                end if;
            when s2 =>
                if ack_send = '0' then
                    -- controlliamo se abbiamo finito la griglia
                    if tile_stream(15) = '1' and tile_stream(14) = '1' then
                        -- se siamo all'ultima tile
                        next_state_pull <= idle;
                    else
                        next_state_pull <= r2;
                    end if;
                end if;
            when others => next_state_pull <= err;
        end case;
    end process;

    pull_fsm_output : process(clk_in, reset)
    begin
        if reset = '1' then
            clk_out <= '0';
            latch <= '0';
            en_send <= '0';
            tile_stream <= (others => '0');
            pb_counter <= (others => '0');
            tile_counter <= (others => '0');
        elsif rising_edge(clk_in) then
            if en_clk_scan = '1' then
                -- valori di default
                clk_out <= '0';
                latch <= '0';
                en_send <= '0';

                -- quando entriamo nello stato, le cose scritte qua vengono subito eseguite
                case next_state_pull is     -- controlliamo lo stato successivo per non perdere un ciclo
                    when idle =>
                        null;

                    when r1 =>
                        latch <= '1';
                        tile_counter <= (others => '0');

                    when r2 =>
                        pb_counter <= (others => '0');
                        tile_counter <= tile_counter + 1;

                    when get_bit =>
                        pb_counter <= pb_counter + 1;
                        tile_stream <= tile_stream(14 downto 0) & data;

                    when c1 =>
                        clk_out <= '1';

                    when s1 =>
                        en_send <= '1';

                    when s2 =>
                        null;

                    when others =>
                        null;

                end case;
            end if;
        end if;
    end process;


    sender_fsm_clocking : process(clk_in, reset)
    begin
        if reset = '1' then
            state_sender <= idle;
        elsif rising_edge(clk_in) then
            state_sender <= next_state_sender;
        end if;
    end process;

    sender_fsm_next : process(state_sender, en_send, i2c_busy)
    begin
        next_state_sender <= state_sender;

        case state_sender is
            when idle =>
                if en_send = '1' then
                    next_state_sender <= start_tx;
                end if;
            when start_tx => next_state_sender <= wait_busy;
            when wait_busy =>
                if i2c_busy = '1' then  -- aspettiamo che il modulo prenda il dato
                    next_state_sender <= wait_finish;
                end if;
            when wait_finish =>
                if i2c_busy = '0' then
                    if i2c_ack_err = '1' then
                        next_state_sender <= err;
                    else
                        next_state_sender <= f1;
                    end if;
                end if;
            when f1 =>  -- aspettiamo che si spenga en_send
                if en_send = '0' then
                    next_state_sender <= idle;
                end if;
            when others => next_state_sender <= err;
        end case;
    end process;

    sender_fsm_output : process(clk_in, reset)
    begin
        if reset = '1' then
            i2c_ena <= '0';
            ack_send <= '0';
        elsif rising_edge(clk_in) then
            -- defaults:
            ack_send <= '0';

            case next_state_sender is
                when idle =>
                    i2c_ena <= '0';

                when start_tx =>
                    i2c_addr <= "1010101"; -- indirizzo slave RP2040
                    i2c_data_wr <= tile_stream(15 downto 8);
                    i2c_rw <= '0';
                    i2c_ena <= '1';        -- diciamo all'IP di partire

                when wait_busy =>
                    null;

                when wait_finish =>
                    i2c_ena <= '0';

                when f1 =>
                    ack_send <= '1';

                when others => null;

            end case;
        end if;
    end process;




end behavioral;











