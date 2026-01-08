library IEEE;
use IEEE.std_logic_1164.all;

entity T74HCT165 is
port (
    nPL                 : IN  std_logic;
    nCE                : IN  std_logic;
    CP                  : IN  std_logic;
    DS                  : IN  std_logic;
    D                    : IN  std_logic_vector(7 downto 0);
    Q7                  : OUT std_logic;
    nQ7                : OUT std_logic
);
end T74HCT165;

architecture behave_T74HCT165 of T74HCT165 is
signal  Qs            : std_logic_vector(7 downto 0) ;

begin
HCT165 : process(nPL, CP, D)
begin
    if(nPL = '0') then
        Qs <= D;
    elsif rising_edge(CP) then
        if(nCE = '0') then
            Qs <= Qs(6 downto 0) & DS;    -- or  Qs <= shl(Qs, '1') & DS;
        end if;
    end if;
end process;
    Q7 <= Qs(7);
    nQ7 <= not(Qs(7));
end behave_T74HCT165;
