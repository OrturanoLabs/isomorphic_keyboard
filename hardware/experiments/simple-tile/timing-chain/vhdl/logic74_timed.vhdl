-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Timing-aware, self-checking models of the rev-A tile's 74-series parts.
-- Delay values come from chain_timing_pkg (transcribed from
-- logic/timing/timing.json); each instance receives them already
-- corner-selected and scaled. Checks that the datasheets DO specify raise
-- "TIMING-FAIL:<token>" assertion failures (locating the hop); parameters the
-- JSON lacks simply have no check (reported as UNSIGNED by the testbench).
--
-- Outputs use TRANSPORT delay so glitches are propagated to the receivers
-- instead of being silently filtered; a sub-ns/glitch is therefore a
-- *pessimistic* stimulus for the downstream LVC input (real gates band-limit
-- them). Violations found with this pessimism are safe to trust.
--
-- The models are simulation models: behaviour matches the zero-delay
-- hardware/simulation reference, with datasheet delays and checks added.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- ---------------------------------------------------------------------------
-- SN74LVC165A: 8-bit parallel-in shift register.
-- ~PL low = transparent async parallel load; rising CP with CE low shifts.
-- Checks: SER setup/hold, SH/LD recovery, SH/LD and CLK pulse widths.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lvc165a_t is
  generic (
    LOC       : string := "lvc165a";
    T_CQ      : time   := 14.5 ns;  -- CLK -> Q7
    T_LOAD    : time   := 19.9 ns;  -- ~PL -> Q7 (async load path)
    T_SU_SER  : time   := 4.0 ns;
    T_H_SER   : time   := 0.5 ns;
    T_SU_SHLD : time   := 3.5 ns;   -- ~PL high (recovery) before CLK^
    T_W_SHLD  : time   := 4.3 ns;   -- ~PL low pulse
    T_W_CLK   : time   := 4.3 ns);
  port (
    nPL : in  std_logic;
    nCE : in  std_logic;
    CP  : in  std_logic;
    DS  : in  std_logic;
    D   : in  std_logic_vector(7 downto 0);
    Q7  : out std_logic := '0';
    nQ7 : out std_logic := '1');
end entity;

architecture sim of lvc165a_t is
  signal qs    : std_logic_vector(7 downto 0) := (others => '0');
  signal armed : boolean := false;   -- checks arm at the first real load pulse
begin

  p_arm : process(nPL)
  begin
    if nPL = '0' then
      armed <= true;
    end if;
  end process;

  -- functional register (zero delay; the output stage adds the datasheet delay)
  p_reg : process(nPL, CP, D)
  begin
    if nPL = '0' then
      qs <= D;                          -- transparent asynchronous parallel load
    elsif rising_edge(CP) and nCE = '0' then
      qs <= qs(6 downto 0) & DS;
    end if;
  end process;

  -- delayed output; the load path and the clock path carry different delays
  Q7  <= transport qs(7)     after T_LOAD when nPL = '0' else qs(7) after T_CQ;
  nQ7 <= transport not qs(7) after T_LOAD when nPL = '0' else not qs(7) after T_CQ;

  -- SER setup/hold vs CP (only while shifting: ~PL high, CE low)
  p_dsmon : process(CP, DS, nPL, nCE, armed)
    variable t_ds     : time    := 0 ns;
    variable t_cp     : time    := 0 ns;
    variable seen_ds  : boolean := false;
    variable seen_cp  : boolean := false;
  begin
    if DS'event then
      seen_ds := true;
      t_ds := now;
      if armed and seen_cp and nPL = '1' and nCE = '0' and
         now - t_cp >= 0 ns and now - t_cp < T_H_SER then
        assert false
          report "TIMING-FAIL:HOLD " & LOC & " SER changed " &
                 time'image(now - t_cp) & " after CP^ (th " & time'image(T_H_SER) & ")"
          severity failure;
      end if;
    end if;
    if CP'event and rising_edge(CP) then
      seen_cp := true;
      t_cp := now;
      if armed and seen_ds and nPL = '1' and nCE = '0' and now - t_ds < T_SU_SER then
        assert false
          report "TIMING-FAIL:SETUP " & LOC & " SER changed " &
                 time'image(now - t_ds) & " before CP^ (tsu " & time'image(T_SU_SER) & ")"
          severity failure;
      end if;
    end if;
  end process;

  -- ~PL recovery (deassert -> next active clock) + low pulse width
  p_plmon : process(nPL, CP, armed)
    variable t_fall, t_rise         : time    := 0 ns;
    variable seen_fall, seen_rise   : boolean := false;
  begin
    if nPL'event then
      if nPL = '0' then
        seen_fall := true;
        t_fall := now;
      else
        seen_rise := true;
        t_rise := now;
        if seen_fall and now - t_fall < T_W_SHLD then
          assert false
            report "TIMING-FAIL:PULSE " & LOC & " ~PL low pulse " &
                   time'image(now - t_fall) & " < " & time'image(T_W_SHLD)
            severity failure;
        end if;
      end if;
    end if;
    if CP'event and rising_edge(CP) and nCE = '0' and nPL = '1' and
       armed and seen_rise and now - t_rise < T_SU_SHLD then
      assert false
        report "TIMING-FAIL:RECOVERY " & LOC & " ~PL high " &
               time'image(now - t_rise) & " before CP^ (tsu " & time'image(T_SU_SHLD) & ")"
        severity failure;
    end if;
  end process;

  -- CLK pulse widths (checked only while armed: ~PL high; power-on routing
  -- transients during the load window are irrelevant -- the latch has not yet
  -- released the part)
  p_clkmon : process(CP, nPL, armed)
    variable t_rise, t_fall       : time    := 0 ns;
    variable seen_rise, seen_fall : boolean := false;
  begin
    if nPL /= '1' or not armed then
      seen_rise := false;
      seen_fall := false;
    elsif rising_edge(CP) then
      if seen_fall and now - t_fall < T_W_CLK then
        assert false
          report "TIMING-FAIL:PULSE " & LOC & " CLK low pulse " &
                 time'image(now - t_fall) & " < " & time'image(T_W_CLK)
          severity failure;
      end if;
      seen_rise := true;
      t_rise := now;
    elsif CP'event and (CP = '0' or CP = 'L') then
      if seen_rise and now - t_rise < T_W_CLK then
        assert false
          report "TIMING-FAIL:PULSE " & LOC & " CLK high pulse " &
                 time'image(now - t_rise) & " < " & time'image(T_W_CLK)
          severity failure;
      end if;
      seen_fall := true;
      t_fall := now;
    end if;
  end process;

end architecture;

-- ---------------------------------------------------------------------------
-- SN74LV161A: 4-bit counter, async master reset; ENT/ENP/parallel-load tied
-- inactive (the rev-A tile uses count + terminal-count only).
-- Checks: CLK pulse width. ~MR recovery is NOT in timing.json -> unchecked.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lv161a_t is
  generic (
    LOC     : string := "lv161a";
    T_CQ    : time   := 16.0 ns;   -- CLK -> Q
    T_RCO   : time   := 16.0 ns;   -- CLK -> RCO, count mode
    T_CLR   : time   := 19.5 ns;   -- ~MR -> Q
    T_W_CLK : time   := 5.0 ns);
  port (
    CP   : in  std_logic;
    nMR  : in  std_logic;
    Q    : out std_logic_vector(3 downto 0) := (others => '0');
    RCO  : out std_logic := '0');
end entity;

architecture sim of lv161a_t is
  signal cnt   : unsigned(3 downto 0) := (others => '0');
  signal armed : boolean := false;
begin

  p_arm : process(nMR)
  begin
    if nMR = '0' then
      armed <= true;
    end if;
  end process;

  p_cnt : process(nMR, CP)
  begin
    if nMR = '0' then
      cnt <= (others => '0');
    elsif rising_edge(CP) then
      cnt <= cnt + 1;
    end if;
  end process;

  Q <= transport std_logic_vector(cnt) after T_CLR when nMR = '0' else
       std_logic_vector(cnt) after T_CQ;

  RCO <= transport '1' after T_RCO when cnt = 15 else '0' after T_RCO;

  p_clkmon : process(CP, nMR, armed)
    variable t_rise, t_fall       : time    := 0 ns;
    variable seen_rise, seen_fall : boolean := false;
  begin
    if nMR /= '1' or not armed then
      seen_rise := false;
      seen_fall := false;
    elsif rising_edge(CP) then
      if seen_fall and now - t_fall < T_W_CLK then
        assert false
          report "TIMING-FAIL:PULSE " & LOC & " CLK low pulse " &
                 time'image(now - t_fall) & " < " & time'image(T_W_CLK)
          severity failure;
      end if;
      seen_rise := true;
      t_rise := now;
    elsif CP'event and (CP = '0' or CP = 'L') then
      if seen_rise and now - t_rise < T_W_CLK then
        assert false
          report "TIMING-FAIL:PULSE " & LOC & " CLK high pulse " &
                 time'image(now - t_rise) & " < " & time'image(T_W_CLK)
          severity failure;
      end if;
      seen_fall := true;
      t_fall := now;
    end if;
  end process;

end architecture;

-- ---------------------------------------------------------------------------
-- SN74LVC2G08: one AND gate.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lvc2g08_t is
  generic (LOC : string := "lvc2g08"; T_PD : time := 5.3 ns;
           Y_INIT : std_logic := '0');
  port (A : in std_logic; B : in std_logic; Y : out std_logic := Y_INIT);
end entity;
architecture sim of lvc2g08_t is
begin
  Y <= transport to_x01(A) and to_x01(B) after T_PD;
end architecture;

-- ---------------------------------------------------------------------------
-- SN74LVC2G32: one OR gate.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lvc2g32_t is
  generic (LOC : string := "lvc2g32"; T_PD : time := 4.8 ns;
           Y_INIT : std_logic := '0');
  port (A : in std_logic; B : in std_logic; Y : out std_logic := Y_INIT);
end entity;
architecture sim of lvc2g32_t is
begin
  Y <= transport to_x01(A) or to_x01(B) after T_PD;
end architecture;

-- ---------------------------------------------------------------------------
-- SN74LVC1G04: inverter.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lvc1g04_t is
  generic (LOC : string := "lvc1g04"; T_PD : time := 4.2 ns;
           Y_INIT : std_logic := '1');
  port (A : in std_logic; Y : out std_logic := Y_INIT);
end entity;
architecture sim of lvc1g04_t is
begin
  Y <= transport not to_x01(A) after T_PD;
end architecture;

-- ---------------------------------------------------------------------------
-- SN74LVC2G125: tri-state buffer, active-low ~OE. ten/tdis models are
-- asymmetric: enable/disable carry their own delays; the min corner of
-- ten/tdis is NOT published (timing.json null) so callers may hand us a
-- documented 0.0 lower bound.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lvc2g125_t is
  generic (
    LOC   : string := "lvc2g125";
    T_PD  : time := 5.3 ns;
    T_EN  : time := 5.7 ns;
    T_DIS : time := 5.6 ns);
  port (A : in std_logic; nOE : in std_logic; Y : out std_logic := 'Z');
end entity;
architecture sim of lvc2g125_t is
begin
  p_buf : process(A, nOE)
    variable en : boolean := false;
  begin
    if to_x01(nOE) = '0' then
      if not en then
        Y <= transport to_x01(A) after T_EN;
      else
        Y <= transport to_x01(A) after T_PD;
      end if;
      en := true;
    else
      if en then
        Y <= transport 'Z' after T_DIS;
      end if;
      en := false;
    end if;
  end process;
end architecture;

-- ---------------------------------------------------------------------------
-- SN74LVC2G126: tri-state buffer, active-high OE.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lvc2g126_t is
  generic (
    LOC   : string := "lvc2g126";
    T_PD  : time := 5.0 ns;
    T_EN  : time := 5.1 ns;
    T_DIS : time := 5.4 ns);
  port (A : in std_logic; OE : in std_logic; Y : out std_logic := 'Z');
end entity;
architecture sim of lvc2g126_t is
begin
  p_buf : process(A, OE)
    variable en : boolean := false;
  begin
    if to_x01(OE) = '1' then
      if not en then
        Y <= transport to_x01(A) after T_EN;
      else
        Y <= transport to_x01(A) after T_PD;
      end if;
      en := true;
    else
      if en then
        Y <= transport 'Z' after T_DIS;
      end if;
      en := false;
    end if;
  end process;
end architecture;

-- ---------------------------------------------------------------------------
-- SN74LVC2G74: D flip-flop with async ~CLR (~PRE tied high; the rev-A tile
-- clears the sticky B_W flag from ~rst). CLK -> Q delay stands in for
-- ~CLR -> Q (labelled proxy: timing.json has no such cell).
-- Checks: D setup/hold, ~CLR recovery, CLK pulse width.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lvc2g74_t is
  generic (
    LOC     : string := "lvc2g74";
    T_CQ    : time := 6.9 ns;
    T_SU    : time := 1.9 ns;
    T_H     : time := 0.5 ns;
    T_SUCLR : time := 1.8 ns;   -- ~CLR inactive before CLK^ (recovery)
    T_W_CLK : time := 3.5 ns);
  port (
    CP   : in  std_logic;
    D    : in  std_logic;
    nCLR : in  std_logic;
    Q    : out std_logic := '0');
end entity;
architecture sim of lvc2g74_t is
  signal qi    : std_logic := '0';
  signal armed : boolean := false;
begin

  p_arm : process(nCLR)
  begin
    if nCLR = '0' then
      armed <= true;
    end if;
  end process;

  p_ff : process(nCLR, CP)
  begin
    if nCLR = '0' then
      qi <= '0';
    elsif rising_edge(CP) then
      qi <= D;
    end if;
  end process;

  Q <= transport '0' after T_CQ when nCLR = '0' else qi after T_CQ;

  p_dmon : process(CP, D, nCLR, armed)
    variable t_d, t_cp : time := 0 ns;
    variable seen_d, seen_cp : boolean := false;
  begin
    if D'event then
      seen_d := true;
      t_d := now;
      if armed and seen_cp and nCLR = '1' and now - t_cp >= 0 ns and now - t_cp < T_H then
        assert false
          report "TIMING-FAIL:HOLD " & LOC & " D changed " &
                 time'image(now - t_cp) & " after CP^ (th " & time'image(T_H) & ")"
          severity failure;
      end if;
    end if;
    if CP'event and rising_edge(CP) then
      seen_cp := true;
      t_cp := now;
      if armed and seen_d and nCLR = '1' and now - t_d < T_SU then
        assert false
          report "TIMING-FAIL:SETUP " & LOC & " D changed " &
                 time'image(now - t_d) & " before CP^ (tsu " & time'image(T_SU) & ")"
          severity failure;
      end if;
    end if;
  end process;

  p_clrmon : process(nCLR, CP, armed)
    variable t_rise : time := 0 ns;
    variable seen   : boolean := false;
  begin
    if nCLR'event and nCLR = '1' then
      seen := true; t_rise := now;
    end if;
    if CP'event and rising_edge(CP) and nCLR = '1' and armed and seen and now - t_rise < T_SUCLR then
      assert false
        report "TIMING-FAIL:RECOVERY " & LOC & " ~CLR high " &
               time'image(now - t_rise) & " before CP^ (tsu " & time'image(T_SUCLR) & ")"
        severity failure;
    end if;
  end process;

  p_clkmon : process(CP, nCLR, armed)
    variable t_rise, t_fall       : time    := 0 ns;
    variable seen_rise, seen_fall : boolean := false;
  begin
    if nCLR /= '1' or not armed then
      seen_rise := false;
      seen_fall := false;
    elsif rising_edge(CP) then
      if seen_fall and now - t_fall < T_W_CLK then
        assert false
          report "TIMING-FAIL:PULSE " & LOC & " CLK low pulse " &
                 time'image(now - t_fall) & " < " & time'image(T_W_CLK)
          severity failure;
      end if;
      seen_rise := true;
      t_rise := now;
    elsif CP'event and (CP = '0' or CP = 'L') then
      if seen_rise and now - t_rise < T_W_CLK then
        assert false
          report "TIMING-FAIL:PULSE " & LOC & " CLK high pulse " &
                 time'image(now - t_rise) & " < " & time'image(T_W_CLK)
          severity failure;
      end if;
      seen_fall := true;
      t_fall := now;
    end if;
  end process;

end architecture;
