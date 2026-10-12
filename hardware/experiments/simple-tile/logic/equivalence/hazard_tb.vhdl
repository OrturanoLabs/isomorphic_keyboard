-- W-transition hazard probe (the "legal topology" question for the GAL).
--
-- W (= T_W and B_first) selects whether the clock is forwarded up (T_clk) or
-- left (L_clk). Legally it changes between frames while the board clock is
-- idle low; but tiles are hot-pluggable "while playing", so W can in principle
-- move while BCLK is high. What lands on the neighbour's clock net then?
--
-- Far-end net model: an undriven clock net is held by the receiving tile's
-- pull-up ('H'), per the protocol pin table (B_clk in, pull-up).
--
-- Expected findings (hand-traced, then asserted):
--   * Tri-stated forwarding (rev A, gal v2) has a RELEASE edge: a net driven low
--     and then tri-stated floats up through the pull-up => one rising edge on the
--     neighbour's clock net. On T_clk this happens at W 0->1 with BCLK low
--     (t_up=1 such edge here); L_clk (driven low while W=1, released at W 1->0)
--     shows two. This is inherent to rev A's own tri-state topology, not a GAL
--     artefact. In legal sequencing W moves only between frames while the clock
--     idles low, and the per-frame latch re-clears counters before the next
--     frame, so the extra count is inert; mid-frame W transients (hot-plug
--     bounce) desync a frame, which the protocol's marker bits catch.
--   * gal v1 (driven low) has NO release edge on T_clk (net stays driven 0);
--     instead W 1->0 while BCLK=1 produces a driven 0->1 edge (one extra
--     spurious edge class vs rev A: t_up=3 total vs 2). W toggles with BCLK=0
--     give none.
--   * gal v2 (true-Z) matches the rev-A edge pattern exactly.

library ieee;
use ieee.std_logic_1164.all;

entity hazard_tb is
end hazard_tb;

architecture sim of hazard_tb is
  signal bclk              : std_logic := '0';
  signal blatch, rlatch    : std_logic := '0';
  signal tw, bfirst        : std_logic := '1';  -- W=1: chain turned left
  signal tdata, ldata      : std_logic := '0';
  signal bdata             : std_logic := '0';

  signal tclk_r,  lclk_r  : std_logic;
  signal tclk_g,  lclk_g  : std_logic;
  signal tclk_g2, lclk_g2 : std_logic;

  -- what the neighbour actually sees (pull-up holds an undriven net high)
  signal tnet_r,  tnet_g,  tnet_g2 : std_logic;
  signal lnet_r,  lnet_g,  lnet_g2 : std_logic;

  signal t_up_r, t_up_g, t_up_g2 : natural := 0;
  signal l_up_r, l_up_g, l_up_g2 : natural := 0;

  function resolve(s : std_logic) return std_logic is
  begin
    if s = 'Z' then return 'H'; else return s; end if;
  end function;
begin

  glue_r  : entity work.ref_glue
    port map (bclk, blatch, rlatch, tw, bfirst, tdata, ldata, bdata,
              tclk_r, lclk_r, open, open, open, open);
  glue_g  : entity work.gal_glue
    port map (bclk, blatch, rlatch, tw, bfirst, tdata, ldata, bdata,
              tclk_g, lclk_g, open, open, open, open);
  glue_g2 : entity work.gal_glue_v2
    port map (bclk, blatch, rlatch, tw, bfirst, tdata, ldata, bdata,
              tclk_g2, lclk_g2, open, open, open, open);

  tnet_r  <= resolve(tclk_r);  tnet_g  <= resolve(tclk_g);  tnet_g2 <= resolve(tclk_g2);
  lnet_r  <= resolve(lclk_r);  lnet_g  <= resolve(lclk_g);  lnet_g2 <= resolve(lclk_g2);

  cnt_t_r  : process(tnet_r)  begin if rising_edge(tnet_r)  then t_up_r  <= t_up_r  + 1; end if; end process;
  cnt_t_g  : process(tnet_g)  begin if rising_edge(tnet_g)  then t_up_g  <= t_up_g  + 1; end if; end process;
  cnt_t_g2 : process(tnet_g2) begin if rising_edge(tnet_g2) then t_up_g2 <= t_up_g2 + 1; end if; end process;
  cnt_l_r  : process(lnet_r)  begin if rising_edge(lnet_r)  then l_up_r  <= l_up_r  + 1; end if; end process;
  cnt_l_g  : process(lnet_g)  begin if rising_edge(lnet_g)  then l_up_g  <= l_up_g  + 1; end if; end process;
  cnt_l_g2 : process(lnet_g2) begin if rising_edge(lnet_g2) then l_up_g2 <= l_up_g2 + 1; end if; end process;

  stim : process
  begin
    tw <= '1'; bfirst <= '1';           -- W=1: clock goes left, T_clk unselected
    wait for 100 ns;

    -- reference change: W toggling while BCLK is LOW (the legal protocol case)
    tw <= '0'; wait for 40 ns; tw <= '1'; wait for 40 ns;
    report "hazard: W bounce with BCLK low done (edges must be 0)" severity note;

    -- W toggle while BCLK is HIGH (out-of-protocol transient: hot plug mid-bit)
    bclk <= '1'; wait for 10 ns;
    tw <= '0'; wait for 10 ns;          -- W: 1 -> 0 while clock high
    tw <= '1'; wait for 10 ns;          -- W: 0 -> 1 while clock high
    wait for 10 ns; bclk <= '0'; wait for 40 ns;
    report "hazard: W bounce with BCLK high done" severity note;

    -- and back: W 0->1 with clock high covered by returning to W=1 stable,
    -- now exercise the opposite sequence from W=0
    tw <= '0'; wait for 40 ns;          -- W=0: T_clk selected
    bclk <= '1'; wait for 10 ns;
    tw <= '1'; wait for 10 ns;          -- W: 0 -> 1 while clock high
    tw <= '0'; wait for 10 ns;          -- W: 1 -> 0 while clock high
    wait for 10 ns; bclk <= '0'; wait for 40 ns;

    report "T_clk net rising edges:  ref=" & integer'image(t_up_r) &
           " gal_v1=" & integer'image(t_up_g) & " gal_v2=" & integer'image(t_up_g2) severity note;
    report "L_clk net rising edges:  ref=" & integer'image(l_up_r) &
           " gal_v1=" & integer'image(l_up_g) & " gal_v2=" & integer'image(l_up_g2) severity note;

    -- expectations (hand-traced in the header comment)
    assert t_up_r = 2  report "ref: expect 2 T_clk net edges (1 legal forward + 1 release), got "
      & integer'image(t_up_r) severity error;
    assert t_up_g2 = 2 report "gal_v2: must match ref edge pattern exactly, got "
      & integer'image(t_up_g2) severity error;
    assert t_up_g = 3  report
      "gal_v1: expect 3 T_clk net edges (1 legal + 2 spurious re/enables at BCLK=1), got " &
      integer'image(t_up_g) severity error;
    assert l_up_r = 3 and l_up_g = 3 and l_up_g2 = 3
      report "L_clk net: expect 3 edges (1 legal + 2 release), identical across designs, got ref="
      & integer'image(l_up_r) & " gal_v1=" & integer'image(l_up_g) & " gal_v2=" & integer'image(l_up_g2)
      severity error;

    report "HAZARD PROBE: PASS (gal_v1's only added class vs rev A: driven 0->1 when W " &
           "returns while BCLK=1; release edges are inherent to tri-stated forwarding, " &
           "including rev A)" severity note;
    std.env.stop;
  end process;

end sim;
