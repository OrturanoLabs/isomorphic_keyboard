-- SPDX-License-Identifier: GPL-3.0-only
--
-- Isomorphic keyboard - iCE40UP5K (pico-ice) top level.
--
-- Scans a chain of tiles (two '165 shift registers per tile) through BOARD_LATCH /
-- BOARD_CLK / BOARD_DATA, rebuilds the position of every tile in the grid from the
-- marker bits of each 16-bit frame, debounces the 12 keys of every tile, and sends
-- note-on / note-off messages on a 31250 baud MIDI UART (PACKAGE_MIDI).
-- The frame format and the grid walk are documented in docs/architecture/protocol.md.

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

    -- CUSTOM TYPES

    -- coord_t(5 downto 3): r
    -- coord_t(2 downto 0): c
    subtype coord_t is std_logic_vector(5 downto 0);
    constant COORD_ZERO : coord_t := (others => '0');

    -- pbs_t(0): key r1,c1
    -- pbs_t(1): key r1,c2
    -- [...]
    -- pbs_t(4): key r2,c1
    -- [...]
    -- pbs_t(11): key r3,c4
    subtype pbs_t is std_logic_vector(11 downto 0);

    -- tile_t(17 downto 6): pbs_t
    -- tile_t(5 downto 0): coord_t
    subtype tile_t is std_logic_vector(17 downto 0);
    constant TILE_ZERO : tile_t := (others => '0');
    -- state of key (i,j):
    -- tile_t(6 + i*4 + j)

    type keyboard_t is array (0 to 9) of tile_t;
    constant KEYBOARD_ZERO : keyboard_t := (others => TILE_ZERO);


    component olo_intf_debounce
        generic (
            CLKFREQUENCY_G      : real      := 12.0e6;
            DEBOUNCETIME_G      : real      := 2.0e-3; -- 2.0e-2
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

    signal clk_counter : unsigned(11 downto 0) := (others => '0');  -- main clock divider counter
    signal en_clk_scan : std_logic := '0';  -- clock enable for the grid scan (CLK_IN / 17)
    signal reset : std_logic;
    signal midi_out : std_logic;

    signal sender_fsm_enable : std_logic := '0'; -- handshake: send the data of one tile
    signal sender_fsm_busy : std_logic := '0'; -- handshake: tile data sent

    type state_main_t is (
        idle,   -- initial state
        scanning,   -- scanning. While in this state the pull FSM is active too
        done,
        err     -- error / fallback state
    );

    type state_pull_t is (
        idle,   -- wait for the main FSM to be in scanning
        newcol, -- new column: clear anotherCol
        r1,     -- raise the latch (parallel load of the tiles)
        r2,     -- release the latch and prepare to read the first bit
        c1,     -- board clock high
        get_bit,    -- sample one bit and increment the bit counter
        s1,     -- enable the sender and wait for ack_send (unused)
        s2,     -- wait for ack_send to return low, i.e. the sender is idle again (unused)
        done,
        load,   -- store the tile data in keyboard_state
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

    signal tile_stream : std_logic_vector(15 downto 0);    -- 2 bytes: raw frame of one tile
    signal pb_counter : unsigned(4 downto 0);       -- bit counter within a tile frame
    signal tile_counter : unsigned(5 downto 0);     -- tile counter

    -- '1' when another column follows the current one; cleared when the next column starts
    signal anotherCol : std_logic := '0';
    signal coord : coord_t := COORD_ZERO;

    signal keyboard_state : keyboard_t := KEYBOARD_ZERO;    -- raw (real-time) state
    signal keyboard_debounced : keyboard_t := KEYBOARD_ZERO;    -- debounced state
    signal keyboard_debounced_old : keyboard_t := KEYBOARD_ZERO;    -- debounced state delayed by one clock
    signal keyboard_pending : keyboard_t := KEYBOARD_ZERO;  -- '1' where a key changed and a MIDI message is still due

    -- absolute coordinates of the key being serialised
    signal x : unsigned(7 downto 0) := (others => '0');
    signal y : unsigned(7 downto 0) := (others => '0');
    signal change_dir : std_logic := '0';

    -- MIDI FSM signals
    signal midi_start : std_logic := '0';
    signal midi_busy : std_logic := '0';
    signal midi_uart_ready : std_logic := '0';
    signal midi_uart_start : std_logic := '0';
    signal midi_uart_data : std_logic_vector(7 downto 0) := (others => '0');

    -- maps the 16-bit tile frame to the 12 keys
    function map_pbs(stream : std_logic_vector(15 downto 0)) return pbs_t is
        variable p : pbs_t;
    begin
        p(0) := stream(5);
        p(1) := stream(4);
        p(2) := stream(11);
        p(3) := stream(10);
        p(4) := stream(7);
        p(5) := stream(6);
        p(6) := stream(13);
        p(7) := stream(12);
        p(8) := stream(9);
        p(9) := stream(8);
        p(10) := stream(15);
        p(11) := stream(14);
        return p;
    end function;

    -- MIDI note computation
    signal pitch : unsigned (7 downto 0);
    constant ref_pitch : unsigned (6 downto 0) := "0111100"; -- 60 = C4 (middle C)

    constant note_on : std_logic_vector (7 downto 0) := x"90";
    constant note_off : std_logic_vector (7 downto 0) := x"80";
    constant velocity : std_logic_vector (7 downto 0) := x"64";

    type lut_t is array (0 to 15) of unsigned(2 downto 0);
    constant DIV4_LUT : lut_t := (
        0 => "000",  -- 0/4
        1 => "000",
        2 => "000",
        3 => "000",
        4 => "001",
        5 => "001",
        6 => "001",
        7 => "001",
        8 => "010",
        9 => "010",
        10 => "010",
        11 => "010",
        12 => "011",
        13 => "011",
        14 => "011",
        15 => "011"
    );

    constant MOD4_LUT : lut_t := (
        0 => "000",
        1 => "001",
        2 => "010",
        3 => "011",
        4 => "000",
        5 => "001",
        6 => "010",
        7 => "011",
        8 => "000",
        9 => "001",
        10 => "010",
        11 => "011",
        12 => "000",
        13 => "001",
        14 => "010",
        15 => "011"
    );

begin
    reset <= not RESET_N;

    -- generate the scan clock enable (one pulse every 17 CLK_IN cycles)
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

-- shifts the frames out of the tile chain and fills keyboard_state


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
        -- default assignment, so no ELSE branch is needed everywhere
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
            when c1 =>  -- have all 16 bits of the frame been collected?
                if pb_counter = 16 then
                    -- check the two fixed marker bits (always '1')
                    if tile_stream(2) = '1' and tile_stream(3) = '1' then
                        next_state_pull <= load; -- frame valid: store it
                    else
                        next_state_pull <= err; -- otherwise: framing error (red LED)
                    end if;
                else
                    next_state_pull <= get_bit;
                end if;
            when load =>
                if tile_stream(0) = '1' then -- this tile is the top of its column
                    if anotherCol = '1' then
                        next_state_pull <= newcol; -- another column follows
                    else
                        next_state_pull <= done;  -- whole grid read
                    end if;
                else
                    next_state_pull <= r2;  -- column not finished yet
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
                -- default values
                BOARD_CLK <= '0';
                BOARD_LATCH <= '0';
                sender_fsm_enable <= '0';

                -- outputs are decoded from the NEXT state so they take effect on entering it
                case next_state_pull is     -- look at the next state to avoid losing one cycle
                    when idle =>
                        null;

                    when r1 =>
                        BOARD_LATCH <= '1';
                        tile_counter <= (others => '0');
                        coord(2 downto 0) <= std_logic_vector(to_unsigned(1, 3)); -- start of the grid: reset the coordinates
                        coord(5 downto 3) <= (others => '0');

                    when newcol =>
                        anotherCol <= '0';
                        coord(2 downto 0) <= std_logic_vector( unsigned(coord(2 downto 0)) + 1 ); -- next column
                        coord(5 downto 3) <= (others => '0'); -- restart from the bottom row

                    when r2 =>
                        pb_counter <= (others => '0');
                        tile_counter <= tile_counter + 1;
                        coord(5 downto 3) <= std_logic_vector( unsigned(coord(5 downto 3)) + 1 );

                    when get_bit =>
                        pb_counter <= pb_counter + 1;
                        tile_stream <= tile_stream(14 downto 0) & BOARD_DATA;

                    when c1 =>
                        BOARD_CLK <= '1';

                    when load =>
                        anotherCol <= anotherCol or (not tile_stream(1));
                        -- store the frame in the slot of this tile
                        keyboard_state(to_integer(tile_counter))(5 downto 0) <= coord;
                        keyboard_state(to_integer(tile_counter))(17 downto 6) <= map_pbs(tile_stream);

                    when others =>
                        null;

                end case;
            end if;
        end if;
    end process;



------------------------------------------------------------------------------------------------------------------------------------------------
-- DEBOUNCING AND CHANGE DETECTION ---------------------------------------------------------------------------------------------------------------

-- keyboard_state is complete at every done=>idle transition of state_pull, and it is
-- safe to use on any clock where next_state_pull /= load.
-- It is fed to the debouncers, clocked on the falling edge of CLK_IN.

    -- one 12-channel debouncer per tile slot
    gen_debouncer : for i in 0 to 9 generate -- number of tile slots in keyboard_t
    begin
        debouncer : olo_intf_debounce
            port map(
                CLK => not CLK_IN,
                RST => not RESET_N,
                DATAASYNC => keyboard_state(i)(17 downto 6),
                DATAOUT => keyboard_debounced(i)(17 downto 6)
            );

        keyboard_debounced(i)(5 downto 0) <= keyboard_state(i)(5 downto 0);
    end generate;

    -- keyboard_debounced is stable on every rising edge
    state_serializer_fsm : process(CLK_IN)
        variable pos_tile : integer range 0 to 9 := 0;
        variable pos_bit : integer range 0 to 11  := 0;
        variable active_tile : tile_t;
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
                active_tile := keyboard_pending(pos_tile);

                for i in 0 to 9 loop
                    keyboard_pending(i)(5 downto 0) <= keyboard_debounced(i)(5 downto 0);   -- coordinates are not expected to change between scans
                    keyboard_pending(i)(17 downto 6) <=
                                    keyboard_pending(i)(17 downto 6) or
                                    ( keyboard_debounced(i)(17 downto 6) xor keyboard_debounced_old(i)(17 downto 6) );
                end loop;

                case state_serializer is
                    when polling =>
                        -- walk through all pending bits, one per clock
                        if active_tile(6 + pos_bit) = '1' then
                            keyboard_pending(pos_tile)(6 + pos_bit) <= '0';

                            -- absolute coordinates of the key that changed
                            y <= resize( ( unsigned(active_tile(5 downto 3)) -1)*3 + DIV4_LUT(pos_bit), 8);
                            x <= resize( ( unsigned(active_tile(2 downto 0)) -1)*4 + MOD4_LUT(pos_bit) + unsigned(active_tile(5 downto 3)) -1, 8);
                            change_dir <= keyboard_debounced(pos_tile)(6 + pos_bit);
                            state_serializer <= s0; -- send it over MIDI
                        end if;

                        -- advance the indices
                        if pos_bit < 11 then
                            pos_bit := pos_bit + 1;
                        else
                            pos_bit := 0;
                            if pos_tile < 9 then
                                pos_tile := pos_tile + 1;
                            else
                                pos_tile := 0;
                            end if;
                        end if;

                    when s0 =>
                        -- convert the (x, y) coordinates into a MIDI pitch.
                        -- rules:  one key to the left  = -2 semitones
                        --         one row up            = +7 semitones
                        -- i.e. the offset in semitones from the note at (0, 0)
                        pitch <= resize( ref_pitch - 2*x + 7*y , 8);

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
            UART_TX         => midi_out,
            UART_RX         => '1'
        );
    PACKAGE_MIDI <= not midi_out;

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
                        midi_busy <= '0';   -- the only state where busy is low
                        if midi_start = '1' and midi_uart_ready = '1' then
                            state_midi <= a1;
                            -- key pressed -> note on, released -> note off
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
                                midi_uart_data <= x"00"; -- velocity 0 for note off
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
