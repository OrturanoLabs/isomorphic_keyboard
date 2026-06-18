LIBRARY ieee;
USE ieee.std_logic_1164.all;

ENTITY top_tb IS
-- Un testbench non ha porte esterne!
END top_tb;

ARCHITECTURE sim OF top_tb IS

    -- 1. Dichiarazione del componente da testare (UUT)
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

    -- 2. Segnali interni del testbench per pilotare la UUT
    SIGNAL clk_tb    : STD_LOGIC := '0';
    SIGNAL reset_n_tb: STD_LOGIC := '0';
    SIGNAL sda_tb    : STD_LOGIC;
    SIGNAL scl_tb    : STD_LOGIC;
    SIGNAL led_b_tb  : STD_LOGIC;
    SIGNAL led_r_tb  : STD_LOGIC;
    signal led_g_tb : STD_LOGIC;

    -- Costanti di temporizzazione (12 MHz basato sul tuo codice i2c_master)
    CONSTANT clk_period : TIME := 1 sec / 12_000_000; -- Circa 83.33 ns

BEGIN

    -- 3. Istanziamo la Unit Under Test (UUT)
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

    -- 4. Modello delle resistenze di Pull-Up sul bus I2C (Fondamentale!)
    -- In I2C i segnali sono open-drain. Se nessuno li guida, vanno a 'H' (High Weak)
    sda_tb <= 'H';
    scl_tb <= 'H';

    -- 5. Generatore del Clock (Oscilla all'infinito)
    clk_process : PROCESS
    BEGIN
        clk_tb <= '0';
        WAIT FOR clk_period / 2;
        clk_tb <= '1';
        WAIT FOR clk_period / 2;
    END PROCESS;

    -- 6. Stimoli di test (Reset e simulazione risposta dello Slave)
    stimulus_process : PROCESS
    BEGIN
        -- Applichiamo il reset iniziale
        reset_n_tb <= '0';
        WAIT FOR 5 * clk_period;
        reset_n_tb <= '1'; -- Rilasciamo il reset, la FSM del top passa in START_TX

        -- Il master inizierà a far oscillare SCL e trasmettere dati su SDA.
        -- Per evitare che dia l'errore ACK (led_red si accende), dobbiamo simulare
        -- uno slave che risponde con un ACK (cioè porta SDA a '0' al 9° impulso di clock).

        -- Attendiamo che la transazione parta e arrivi al nono bit dell'indirizzo
        -- WAIT UNTIL falling_edge(scl_tb); -- Start condition...
        --
        -- -- Contiamo 8 bit (Indirizzo + R/W)... al 9° bit facciamo finta di essere lo slave
        -- FOR i IN 0 TO 8 LOOP
        --     WAIT UNTIL falling_edge(scl_tb);
        -- END LOOP;
        --
        -- -- Lo Slave risponde tirando giù SDA per l'ACK dell'indirizzo
        -- sda_tb <= '0';
        -- WAIT UNTIL falling_edge(scl_tb); -- Fine del bit di ACK
        -- sda_tb <= 'Z'; -- Rilasciamo la linea
        --
        -- -- Contiamo altri 8 bit (il dato vero e proprio, es: 0xA5)
        -- FOR i IN 0 TO 8 LOOP
        --     WAIT UNTIL falling_edge(scl_tb);
        -- END LOOP;
        --
        -- -- Lo Slave risponde tirando giù SDA per l'ACK del dato
        -- sda_tb <= '0';
        -- WAIT UNTIL falling_edge(scl_tb);
        -- sda_tb <= 'Z';
        --
        -- -- Lasciamo finire la STOP condition del master
        -- WAIT FOR 200 us;
        --
        -- -- Ferma la simulazione in modo pulito
        -- ASSERT FALSE REPORT "Simulazione completata con successo!" SEVERITY FAILURE;
        WAIT;
    END PROCESS;

END sim;
