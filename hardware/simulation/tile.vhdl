library ieee;
use ieee.std_logic_1164.all;
use IEEE.NUMERIC_STD.ALL;

entity tile is
  port (
    buttons : in std_logic_vector(11 downto 0) := (others => 'L');

    T_W : in std_logic := 'Z';
    T_endcol : in std_logic := 'Z';
    T_first : out std_logic := '0';
    T_latch : out std_logic;
    T_clk : out std_logic;
    T_data : in std_logic := 'Z';

    B_W : out std_logic;
    B_endcol : out std_logic := '0';
    B_first : in std_logic := 'Z';
    B_latch : in std_logic := 'Z';
    B_clk : in std_logic := 'Z';
    B_data : out std_logic;

    L_endrow : in std_logic := 'Z';
    L_latch : out std_logic;
    L_clk : out std_logic;
    L_data : in std_logic := 'Z';

    R_endrow : out std_logic := '0';
    R_latch : in std_logic := 'Z';
    R_clk : in std_logic := 'Z';
    R_data : out std_logic
  );
end tile;

architecture rtl of tile is

signal latch, clock, data : std_logic; -- sengnali principali
signal nlatch : std_logic;

signal ds_bridge : std_logic; -- sengale per connettere l'uscita seriale di SR2 a SR1
signal ds_input : std_logic; -- ds in input dai moduli adiacenti

signal w_state : std_logic; -- stato dei buffer 3state

signal count_reg : unsigned(5 downto 0) := (others => '0'); -- contatore
signal count : std_logic_vector(5 downto 0);

signal sr2_inputs : std_logic_vector(7 downto 0); -- Segnale di supporto
signal ffinput : std_logic;

signal T_W_p, T_endcol_p, T_data_p, B_first_p, B_latch_p, B_clk_p, L_endrow_p, L_data_p, R_latch_p, R_clk_p : std_logic;

begin

  -- input pullups / pulldowns
  T_W_p       <= 'H';
  T_endcol_p  <= 'H';
  T_data_p    <= 'L';
  B_first_p   <= 'H';
  B_latch_p   <= 'L';
  B_clk_p     <= 'H';
  L_endrow_p  <= 'H';
  L_data_p    <= 'L';
  R_latch_p   <= 'L';
  R_clk_p     <= 'H';

  T_W_p       <=   T_W;
  T_endcol_p  <=   T_endcol;
  T_data_p    <=   T_data;
  B_first_p   <=   B_first;
  B_latch_p   <=   B_latch;
  B_clk_p     <=   B_clk;
  L_endrow_p  <=   L_endrow;
  L_data_p    <=   L_data;
  R_latch_p   <=   R_latch;
  R_clk_p     <=   R_clk;


  -- inputs wiring
  clock <= R_clk_p;
  clock <= B_clk_p;

  w_state <= T_W_p and B_first_p;

  latch <= R_latch_p or B_latch_p;  -- il latch è come un reset quindi lo mettiamo in or
  ds_input <= T_data_p when to_x01(w_state) = '0' else L_data_p;


  -- outputs wiring
  R_data <= data;
  B_data <= data;

  T_latch <= latch;
  L_latch <= latch;

  T_clk <= clock when to_x01(w_state) = '0' else 'Z';
  L_clk <= clock when to_x01(w_state) = '1' else 'Z';



  nlatch <= not latch;



  -- sr LSB
  sr1 : entity work.T74HCT165
    port map(
      nPL => nlatch,
      nCE => '0',
      CP => clock,
      DS => ds_bridge,
      D => buttons(11 downto 4),
      Q7 => data,
      nQ7 => open
    );

  sr2_inputs <= buttons(3 downto 0) & "11" & to_x01(L_endrow_p) & to_x01(T_endcol_p);

  -- sr MSB
  sr2 : entity work.T74HCT165
    port map(
      nPL => nlatch,
      nCE => '0',
      CP => clock,
      DS => ds_input,
      D => sr2_inputs,
      Q7 => ds_bridge,
      nQ7 => open
    );



  process(clock, latch)
  begin
    if latch = '1' then
      count_reg <= (others => '0');
    elsif rising_edge(clock) then
      count_reg <= count_reg + 1;
    end if;
  end process;

  count <= std_logic_vector(count_reg);
  ffinput <= count(3) and count(2) and count(1) and count(0) and data;

  process(clock, latch)
  begin
    if latch = '1' then
      B_W <= '0';
    elsif rising_edge(clock) then
      if ffinput = '1' then
        B_W <= '1';
      end if;
    end if;
  end process;


end rtl;
