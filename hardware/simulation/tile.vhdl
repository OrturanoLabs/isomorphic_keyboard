library ieee;
use ieee.std_logic_1164.all;
use IEEE.NUMERIC_STD.ALL;

entity tile is
  port (
    buttons : in std_logic_vector(11 downto 0) := (others => 'L');

    T_W : in std_logic := 'H';
    T_endcol : in std_logic := 'H';
    T_first : out std_logic := '0';
    T_latch : out std_logic;
    T_clk : out std_logic := 'L';
    T_data : in std_logic := 'L';

    B_W : out std_logic;
    B_endcol : out std_logic := '0';
    B_first : in std_logic := 'H';
    B_latch : in std_logic;
    B_clk : in std_logic;
    B_data : out std_logic;

    L_endrow : in std_logic := 'H';
    L_latch : out std_logic := 'L';
    L_clk : out std_logic := 'L';
    L_data : in std_logic := 'L';

    R_endrow : out std_logic := '0';
    R_latch : in std_logic;
    R_clk : in std_logic;
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

begin

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

  sr2_inputs <= buttons(3 downto 0) & "11" & L_endrow & T_endcol;

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


  -- I/O latch clock e data
  --latch <= R_latch;
  --clock <= R_clk;
  R_data <= data;

  T_latch <= latch;
  T_clk <= clock when w_state = '0' else 'Z';

  --latch <= B_latch;
  --clock <= B_clk;
  B_data <= data;

  L_latch <= latch when w_state = '1' else 'Z';
  L_clk <= clock when w_state = '1' else 'Z';

  ds_input <= T_data when w_state = '0' else L_data;


  -- controllo di w_state
  w_state <= T_W and B_first;


  process(clock, latch)
  begin
    if latch = '1' then
      count_reg <= (others => '0');
    elsif rising_edge(clock) then
      count_reg <= count_reg + 1;
    end if;
  end process;

  count <= std_logic_vector(count_reg);
  ffinput <= count(3) and count(2) and count(1) and data; -- non mettiamo count(0) perchè col ff-sr sincrono perdiamo un ciclo

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


  -- il pezzo sotto serve solo a non far incazzare GHDL
  latch <= R_latch when to_x01(B_first) = '1' else B_latch;
  clock <= R_clk when to_x01(B_first) = '1' else B_clk;


end rtl;
