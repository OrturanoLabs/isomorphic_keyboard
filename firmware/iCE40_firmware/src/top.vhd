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

        PACKAGE_MIDI: out std_logic
    );
end top;

architecture behavioral of top is

    component olo_intf_debounce
        generic (
            CLKFREQUENCY_G      : real      := 12.0e6;
            DEBOUNCETIME_G      : real      := 2.0e-2; -- 2.0e-2
            WIDTH_G             : positive  := 12;
            IDLELEVEL_G         : std_logic := '0';
            MODE_G              : string    := "LOW_LATENCY"
        );
        port (
            -- control signals
            CLK                 : in    std_logic;
            RST                 : in    std_logic;
            -- Input clock domain
            DATAASYNC           : in    std_logic_vector(Width_g - 1 downto 0);
            DATAOUT             : out   std_logic_vector(Width_g - 1 downto 0)
        );
    end component;

    component olo_intf_uart
        generic (
            CLKFREQ_G       : real                  := 1.2e7;
            BAUDRATE_G      : real                  := 31.25e3;
            DATABITS_G      : positive range 7 to 9 := 8;
            STOPBITS_G      : string                := "1";
            PARITY_G        : string                := "none"
        );
        port (
            -- Control Signals
            CLK             : in    std_logic;
            RST             : in    std_logic;
            -- Tx Data
            TX_VALID        : in    std_logic                                 := '0';
            TX_READY        : out   std_logic;
            TX_DATA         : in    std_logic_vector(DataBits_g - 1 downto 0) := (others => '0');
            -- Rx Data
            RX_VALID        : out   std_logic;
            RX_DATA         : out   std_logic_vector(DataBits_g - 1 downto 0);
            RX_PARITYERROR  : out   std_logic;
            -- UART Interface
            UART_TX         : out   std_logic;
            UART_RX         : in    std_logic                                 := '1'
        );
    end component;

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

    type state_serializer_t is (
        polling,
        s0,
        s1,
        s2,
        err
    );

    type state_midi_sender_t is (
        idle,
        a1,
        a2,
        b1,
        b2,
        c1,
        c2,
        err
    );

    signal state_main : state_main_t := idle;
    signal state_pull : state_pull_t := idle;
    signal next_state_pull : state_pull_t := idle;
    signal state_serializer : state_serializer_t := polling;
    signal state_midi : state_midi_sender_t := idle;

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
    signal keyboard_state : keyboard_t := KEYBOARD_ZERO;    -- contiene lo stato in tempo reale
    signal keyboard_debounced : keyboard_t := KEYBOARD_ZERO;    -- contiene lo stato dopo il debounce
    signal keyboard_debounced_old : keyboard_t := KEYBOARD_ZERO;    -- stato dopo il debounce con un ciclo di ritardo
    signal keyboard_pending : keyboard_t := KEYBOARD_ZERO;  -- contiene 1 quando va aggiornato lo stato del tasto

    -- variabili per contenere i dati serializzati
    signal x : unsigned(7 downto 0) := (others => '0');
    signal y : unsigned(7 downto 0) := (others => '0');
    signal change_dir : std_logic := '0';

    -- segnali per la fsm del MIDI
    signal midi_start : std_logic := '0';
    signal midi_busy : std_logic := '0';
    signal midi_uart_ready : std_logic := '0';
    signal midi_uart_start : std_logic := '0';
    signal midi_uart_data : std_logic_vector(7 downto 0) := (others => '0');

    -- mappa dei tasti
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

    -- funzioni per isomorfismi delle metrici di tasti
    function flatten(m : pbs_t) return std_logic_vector is
        variable v : std_logic_vector(11 downto 0);
    begin
        for i in 0 to 2 loop
            for j in 0 to 3 loop
                v(i*4 + j) := m(i+1,j+1);
            end loop;
        end loop;
        return v;
    end;
    function unflatten(v : std_logic_vector(11 downto 0)) return pbs_t is
        variable m : pbs_t;
    begin
        for i in 0 to 2 loop
            for j in 0 to 3 loop
                m(i+1,j+1) := v(i*4 + j);
            end loop;
        end loop;
        return m;
    end;

    -- overload delle funzioni logiche
    function "xor" (a, b : pbs_t) return pbs_t is
        variable result : pbs_t;
    begin
        for i in 1 to 3 loop
            for j in 1 to 4 loop
                result(i, j) := a(i, j) xor b(i, j);
            end loop;
        end loop;
        return result;
    end function;
    function "or" (a, b : pbs_t) return pbs_t is
        variable result : pbs_t;
    begin
        for i in 1 to 3 loop
            for j in 1 to 4 loop
                result(i, j) := a(i, j) or b(i, j);
            end loop;
        end loop;
        return result;
    end function;

    -- segnali per la gestione del MIDI
    constant pitch_x : integer := -2;
    constant pitch_y : integer := 7;
    signal pitch : unsigned (7 downto 0);
    constant ref_pitch : unsigned (6 downto 0) := "1100000"; -- 96 = C7

    constant note_on : std_logic_vector (7 downto 0) := x"90";
    constant note_off : std_logic_vector (7 downto 0) := x"80";
    constant velocity : std_logic_vector (7 downto 0) := x"64";

begin
    reset <= not RESET_N;

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
                    when done => state_main <= done;
                    when err => state_main <= err;
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
            when err => next_state_pull <= err;
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
-- DEBOUNCING e CHANGE DETECTION ---------------------------------------------------------------------------------------------------------------

-- ogni volta che c'è la transizione done=>idle di state_pull, i dati in keyboard_state sono pronti
-- e in generale è sicuro usarli a ogni clock se next_state_pull /= load (possiamo usare i fronti di discesa?)
-- priviamo ad inserire queste uscite nei debouncer

    -- generiamo un debouncer da 12 canali per ogni tile allocata
    gen_debouncer : for i in 1 to 10 generate -- dimensionalità delle tile in keyboard_t
        signal pbs_flat : std_logic_vector(11 downto 0);
    begin
        debouncer : olo_intf_debounce
            port map(
                CLK => not CLK_IN,
                RST => not RESET_N,
                DATAASYNC => flatten(keyboard_state(i).pbs),
                DATAOUT => pbs_flat
            );

        keyboard_debounced(i).pbs <= unflatten(pbs_flat);
        keyboard_debounced(i).coord <= keyboard_state(i).coord;
    end generate;

    -- i dati in keyboard_debounced sono stabili su ogni fronte di salita
    state_serializer_fsm : process(CLK_IN)
        variable pos_b : integer range 0 to 15 := 1;
        variable pos_i : integer range 0 to 7  := 1;
        variable pos_j : integer range 0 to 7  := 1;
    begin
        if rising_edge(CLK_IN) then
            if RESET_N = '0' then
                keyboard_debounced_old <= KEYBOARD_ZERO;
                keyboard_pending <= KEYBOARD_ZERO;
                state_serializer <= polling;
                midi_start <= '0';
            else
                midi_start <= '0';
                keyboard_debounced_old <= keyboard_debounced;

                for i in 1 to 10 loop
                    keyboard_pending(i).coord <= keyboard_debounced(i).coord;   -- le coordinate non dovrebbero cambiare fra i vari scan
                    keyboard_pending(i).pbs <= keyboard_pending(i).pbs or ( keyboard_debounced(i).pbs xor keyboard_debounced_old(i).pbs );
                end loop;

                case state_serializer is
                    when polling =>
                        -- logica per trovare tutte le occorrenze dentro a pending
                        if keyboard_pending(pos_b).pbs(pos_i, pos_j) = '1' then
                            keyboard_pending(pos_b).pbs(pos_i, pos_j) <= '0';

                            -- calcolo della coordinata assoluta del tasto premuto
                            y <= resize( (keyboard_pending(pos_b).coord.r -1)*3 + to_unsigned(pos_i, 3), 8);
                            x <= resize( (keyboard_pending(pos_b).coord.c -1)*4 + to_unsigned(pos_j, 3) + keyboard_pending(pos_b).coord.r, 8);
                            change_dir <= keyboard_debounced(pos_b).pbs(pos_i, pos_j);
                            state_serializer <= s0; -- inviamo i dati in MIDI
                        end if;

                        -- incremento degli indici
                        if pos_j < 4 then
                            pos_j := pos_j + 1;
                        else
                            pos_j := 1;
                            if pos_i < 3 then
                                pos_i := pos_i + 1;
                            else
                                pos_i := 1;
                                if pos_b < 10 then
                                    pos_b := pos_b + 1;
                                else
                                    pos_b := 1;
                                end if;
                            end if;
                        end if;

                    when s0 =>
                        if midi_busy = '0' then
                            state_serializer <= s1;
                        end if;

                    when s1 =>
                        midi_start <= '1';
                        if midi_busy = '1' then
                            state_serializer <= s2;
                        end if;

                    when s2 =>
                        if midi_busy = '0' then
                            state_serializer <= polling;
                        end if;

                    when err => state_serializer <= err;
                    when others => state_serializer <= err;

                end case;

            end if;
        end if;
    end process;



------------------------------------------------------------------------------------------------------------------------------------------------
-- COORD to PITCH ------------------------------------------------------------------------------------------------------------------------------

-- dobbiamo prendere le coordinate dentro a x e y e calcolare il pitch corrispondente.
-- regole:  spostamento a sinistra di un tasto = -2 semitoni    pitch_x
--          spostamento in alto di una riga = +7 semitoni       pitch_y
-- possiamo quindi calcolare la differenza in semitoni dalla nota alle coordinate (1, 1)

    pitch <= '0' & to_unsigned( to_integer(ref_pitch) + pitch_x * to_integer(x) + pitch_y * to_integer(y) , 7);




------------------------------------------------------------------------------------------------------------------------------------------------
-- MIDI SENDER ---------------------------------------------------------------------------------------------------------------------------------

    midi_uart : olo_intf_uart
        port map(
            CLK             => CLK_IN,
            RST             => not RESET_N,
            TX_VALID        => midi_uart_start,
            TX_READY        => midi_uart_ready,
            TX_DATA         => midi_uart_data,
            RX_VALID        => open,
            RX_DATA         => open,
            RX_PARITYERROR  => open,
            UART_TX         => PACKAGE_MIDI,
            UART_RX         => '1'
        );

    midi_sender_fsm : process(CLK_IN)
    begin
        if rising_edge(CLK_IN) then
            if RESET_N = '0' then
                state_midi <= idle;
                midi_uart_start <= '0';
                midi_busy <= '0';
            else
                midi_uart_start <= '0';
                midi_busy <= '1';

                case state_midi is
                    when idle =>
                        midi_busy <= '0';   -- unico stato in cui busy è basso
                        if midi_start = '1' and midi_uart_ready = '1' then
                            state_midi <= a1;
                            -- controlliamo la direzione del cambiamento e prepariamo data
                            if change_dir = '1' then
                                midi_uart_data <= note_on;
                            else
                                midi_uart_data <= note_off;
                            end if;
                        end if;

                    when a1 =>
                        midi_uart_start <= '1';
                        if midi_uart_ready = '0' then
                            state_midi <= a2;
                        end if;

                    when a2 =>
                        if midi_uart_ready = '1' then
                            state_midi <= b1;
                            midi_uart_data <= std_logic_vector(pitch);
                        end if;

                    when b1 =>
                        midi_uart_start <= '1';
                        if midi_uart_ready = '0' then
                            state_midi <= b2;
                        end if;

                    when b2 =>
                        if midi_uart_ready = '1' then
                            state_midi <= c1;
                            if change_dir = '1' then
                                midi_uart_data <= velocity;
                            else
                                midi_uart_data <= x"00"; -- se la nota si deve spegnere mettiamo velocity 0
                            end if;
                        end if;

                    when c1 =>
                        midi_uart_start <= '1';
                        if midi_uart_ready = '0' then
                            state_midi <= c2;
                        end if;

                    when c2 =>
                        if midi_uart_ready = '1' then
                            state_midi <= idle;
                        end if;

                    when err => state_midi <= err;
                    when others => state_midi <= err;

                end case;
            end if;
        end if;
    end process;





    LED_BLUE <= '0' WHEN state_main = err ELSE '1';
    LED_RED <= '0' WHEN state_pull = err ELSE '1';
    LED_GREEN <= '0' WHEN state_serializer = err ELSE '1';


end behavioral;











