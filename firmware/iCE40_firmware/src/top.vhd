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
        done,
        err     -- stato di errore / fallback
    );

    type state_pull_t is (
        idle,   -- attende che la prima FSM sia in scanning
        newcol, -- nuova colonna: azzera anotherCol
        r1,     -- alza il reset
        r2,     -- abbassa il reset e prepara a prendere il primo bit
        c1,     -- clock alto
        get_bit,    -- carica bit e incrementa il contatore
        s1,     -- abilita il sender e attende per il segnale ack_send
        s2,     -- aspettiamo che ack_send torni a zero, indicando che il sender è di nuovo in idle
        done,
        load,   -- carica i dati della tile nel primo registro
        err
    );

    type state_sender_t is (
        idle,   -- attende che la seconda FSM abbia raccolto una tile
        start_tx,
        wait_busy,
        wait_finish,
        start_tx_2,
        wait_busy_2,
        wait_finish_2,
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

    -- ci serve un segnale che sia 1 se appare esserci una nuova colonna e che si resetta la tile dopo che la colonna sia finita
    signal anotherCol : std_logic := '0';
    type coord_t is record
        r : unsigned(2 downto 0);
        c : unsigned(2 downto 0);
    end record;
    constant COORD_ZERO : coord_t := (r => (others => '0'), c => (others => '0') );
    signal coord : coord_t := ( r => (others => '0'), c => (others => '0') );

    type pbs_t is array (1 to 3, 1 to 4) of std_logic; -- tipo per la matrice di tasti in una tile
    type tile_t is record
        pbs : pbs_t; -- matrice dei pulsanti della tile
        coord : coord_t; -- coordinata della tile all'interno della griglia
    end record;
    constant TILE_ZERO : tile_t := (pbs => (others => (others => '0')), coord => COORD_ZERO );
    type keyboard_t is array (1 to 10) of tile_t;
    constant KEYBOARD_ZERO : keyboard_t := (others => TILE_ZERO);
    signal keyboard_state : keyboard_t := KEYBOARD_ZERO;


    function map_pbs(stream : std_logic_vector(15 downto 0)) return pbs_t is
        variable p : pbs_t;
    begin
        p(1,1) := stream(5);
        p(1,2) := stream(4);
        p(1,3) := stream(11);
        p(1,4) := stream(10);
        p(2,1) := stream(7);
        p(2,2) := stream(6);
        p(2,3) := stream(13);
        p(2,4) := stream(12);
        p(3,1) := stream(9);
        p(3,2) := stream(8);
        p(3,3) := stream(15);
        p(3,4) := stream(14);
        return p;
    end function;

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
                    when scanning => state_main <= done;
                    when done => state_main <= done;
                    when others => state_main <= err;
                end case;
            end if;
        end if;
    end process;



------------------------------------------------------------------------------------------------------------------------------------------------
-- DISPATCHER ----------------------------------------------------------------------------------------------------------------------------------

-- la funzione principale è estrarre i dati dalle tile e popolare keyboard_state


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
            when newcol => next_state_pull <= r2;
            when r2 => next_state_pull <= get_bit;
            when get_bit => next_state_pull <= c1;
            when c1 =>  -- controlliamo se abbiamo raccolto tutti i 16 bit
                if pb_counter = 16 then
                    -- controlliamo che i bit di controllo siano giusti
                    if tile_stream(2) = '1' and tile_stream(3) = '1' then
                        next_state_pull <= load; -- allora possiamo caricare nel primo registro
                    else
                        next_state_pull <= err; -- altrimenti c'è un errore
                    end if;
                else
                    next_state_pull <= get_bit;
                end if;
            when load =>
                if tile_stream(0) = '1' then -- vuol dire che siamo in cima alla colonna
                    if anotherCol = '1' then
                        next_state_pull <= newcol; -- se c'è un'altra colonna
                    else
                        next_state_pull <= done;  -- se abbiamo finito la griglia
                    end if;
                else
                    next_state_pull <= r2;  -- se non abbiamo finito la colonna
                end if;
            when done => next_state_pull <= idle;
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
                anotherCol <= '0';
                keyboard_state <= KEYBOARD_ZERO;
                coord <= COORD_ZERO;

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
                        coord.c <= to_unsigned(1, 3); -- resettiamo tutto perché iniziamo la griglia
                        coord.r <= (others => '0');

                    when newcol =>
                        anotherCol <= '0';
                        coord.c <= coord.c + 1;  -- incrementa il contatore di colonna
                        coord.r <= (others => '0'); -- resetta il contatore di riga

                    when r2 =>
                        pb_counter <= (others => '0');
                        tile_counter <= tile_counter + 1;
                        coord.r <= coord.r + 1;

                    when get_bit =>
                        pb_counter <= pb_counter + 1;
                        tile_stream <= tile_stream(14 downto 0) & BOARD_DATA;

                    when c1 =>
                        BOARD_CLK <= '1';

                    when load =>
                        anotherCol <= anotherCol or (not tile_stream(1));
                        -- codice per caricare il tile_stream all'interno del registro giusto
                        keyboard_state(to_integer(tile_counter)).coord <= coord;
                        keyboard_state(to_integer(tile_counter)).pbs <= map_pbs(tile_stream);

                    when others =>
                        null;

                end case;
            end if;
        end if;
    end process;



------------------------------------------------------------------------------------------------------------------------------------------------
-- DEBOUNCING ----------------------------------------------------------------------------------------------------------------------------------

-- ogni volta che c'è la transizione done=>idle di state_pull, i dati in keyboard_state sono pronti
-- e in generale è sicuro usarli a ogni clock se next_state_pull /= load (possiamo usare i fronti di discesa?)
-- priviamo ad inserire queste uscite nei debouncer



------------------------------------------------------------------------------------------------------------------------------------------------
-- SENDER --------------------------------------------------------------------------------------------------------------------------------------

    -- sender_fsm_clocking : process(CLK_IN)
    -- begin
    --     if rising_edge(CLK_IN) then
    --         if RESET_N = '0' then
    --             state_sender <= idle;
    --         else
    --             state_sender <= next_state_sender;
    --         end if;
    --     end if;
    -- end process;
    --
    -- sender_fsm_next : process(state_sender, sender_fsm_enable, i2c_busy)
    -- begin
    --     next_state_sender <= state_sender;
    --
    --     case state_sender is
    --         when idle =>
    --             if sender_fsm_enable = '1' then -- attende che venga dato il segnale per inviare i file
    --                 if i2c_busy = '0' then  -- attende che il modulo i2c sia pronto
    --                     next_state_sender <= start_tx;
    --                 end if;
    --             end if;
    --         when start_tx => next_state_sender <= wait_busy;
    --         when wait_busy =>
    --             if i2c_busy = '1' then  -- aspettiamo che il modulo prenda il dato
    --                 next_state_sender <= wait_finish;
    --             end if;
    --         when wait_finish =>
    --             if i2c_busy = '0' then
    --                 if i2c_ack_err = '1' then
    --                     next_state_sender <= err;
    --                 else
    --                     next_state_sender <= start_tx_2;
    --                 end if;
    --             end if;
    --         when start_tx_2 => next_state_sender <= wait_busy_2;
    --         when wait_busy_2 =>
    --             if i2c_busy = '1' then  -- aspettiamo che il modulo prenda il dato
    --                 next_state_sender <= wait_finish_2;
    --             end if;
    --         when wait_finish_2 =>
    --             if i2c_busy = '0' then
    --                 next_state_sender <= f1;
    --             end if;
    --         when f1 =>  -- aspettiamo che si spenga en_send
    --             if sender_fsm_enable = '0' then
    --                 next_state_sender <= idle;
    --             end if;
    --         when others => next_state_sender <= err;
    --     end case;
    -- end process;
    --
    -- sender_fsm_output : process(clk_in, reset)
    -- begin
    --     if reset = '1' then
    --         i2c_ena <= '0';
    --         sender_fsm_busy <= '1';
    --     elsif rising_edge(clk_in) then
    --         -- defaults:
    --         i2c_ena <= '0';
    --         sender_fsm_busy <= '1';
    --
    --         case next_state_sender is
    --             when idle =>
    --                 sender_fsm_busy <= '0'; -- solo quando siamo in idle, la fsm segnala di essere pronta
    --
    --             when start_tx =>
    --                 i2c_data_wr <= tile_stream(15 downto 8);
    --                 i2c_rw <= '0';
    --
    --             when wait_busy =>
    --                 i2c_ena <= '1';        -- diciamo all'IP di partire
    --
    --             when wait_finish =>
    --                 null;
    --
    --             when start_tx_2 =>
    --                 i2c_data_wr <= tile_stream(7 downto 0);
    --                 i2c_rw <= '0';
    --
    --             when wait_busy_2 =>
    --                 i2c_ena <= '1';        -- diciamo all'IP di partire
    --
    --             when wait_finish_2 =>
    --                 null;
    --
    --             when f1 =>
    --                 null;
    --
    --             when others => null;
    --
    --         end case;
    --     end if;
    -- end process;


    LED_BLUE <= '0' WHEN state_main = err ELSE '1';
    LED_RED <= '0' WHEN state_pull = err ELSE '1';
    LED_GREEN <= '0' WHEN state_sender = err ELSE '1';


end behavioral;











