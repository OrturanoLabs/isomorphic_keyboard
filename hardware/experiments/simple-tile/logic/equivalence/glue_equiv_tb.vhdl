-- Self-checking glue-equivalence experiment.
--
--   DUT_R  tile_ref    rev-A seven-chip glue (true-Z T_clk)      [reference]
--   DUT_G  tile_gal    tile_glue.pld as committed (driven-low T_clk)
--   DUT_G2 tile_galv2  tile_glue_truez.pld (true-Z T_clk, ext. 1G04 on ~PL)
--   DUT_C  tile_cpld   ATF1502ASV full-tile candidate
--
-- Every implementation gets identical inputs; outputs are compared at every
-- sample point against each other AND against an expected-behaviour model
-- (frame bit order, first-bit-before-first-clock, counter 16-bit boundary,
-- sticky B_W, DS mux selection). Checking against expected values (not only
-- cross-checking) catches any common transliteration slip.
--
-- The known driven-low vs Z delta on T_clk for DUT_G is NOT glossed: any
-- inequality is a hard mismatch unless it is exactly the documented pattern
-- (ref='Z' while gal='0' under W=1); those are counted and reported.
--
-- Zero-delay functional equivalence only: no timing conclusions (see ../timing/).

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;

entity glue_equiv_tb is
  generic (SEED1 : positive := 2026; SEED2 : positive := 1012);
end glue_equiv_tb;

architecture sim of glue_equiv_tb is
  signal buttons : std_logic_vector(11 downto 0) := (others => '0');
  signal endrow, endcol                       : std_logic := '0';
  signal bclk                                 : std_logic := '0';
  signal blatch, rlatch                       : std_logic := '0';
  signal tw, bfirst                           : std_logic := '0';
  signal tdata, ldata                         : std_logic := '0';

  signal tclk_r, lclk_r, latch_r, npl_r, ds_r, bw_r, dout_r   : std_logic;
  signal tclk_g, lclk_g, latch_g, npl_g, ds_g, bw_g, dout_g   : std_logic;
  signal tclk_g2, lclk_g2, latch_g2, npl_g2, ds_g2, bw_g2, dout_g2 : std_logic;
  signal tclk_c, lclk_c, latch_c, npl_c, ds_c, bw_c, dout_c   : std_logic;

  constant HP : time := 25 ns;   -- 20 MHz half period (functional model: any value works)
begin

  dut_r : entity work.tile_ref
    port map (buttons, endrow, endcol, bclk, blatch, rlatch, tw, bfirst,
              tdata, ldata, tclk_r, lclk_r, latch_r, npl_r, ds_r, bw_r, dout_r);
  dut_g : entity work.tile_gal
    port map (buttons, endrow, endcol, bclk, blatch, rlatch, tw, bfirst,
              tdata, ldata, tclk_g, lclk_g, latch_g, npl_g, ds_g, bw_g, dout_g);
  dut_g2 : entity work.tile_galv2
    port map (buttons, endrow, endcol, bclk, blatch, rlatch, tw, bfirst,
              tdata, ldata, tclk_g2, lclk_g2, latch_g2, npl_g2, ds_g2, bw_g2, dout_g2);
  dut_c : entity work.tile_cpld
    port map (buttons, endrow, endcol, bclk, blatch, rlatch, tw, bfirst,
              tdata, ldata, tclk_c, lclk_c, latch_c, npl_c, ds_c, bw_c, dout_c);

  stim : process
    variable s1, s2 : positive := SEED1;
    variable r      : real;
    variable mismatches, samples, delta_z0, frames : natural := 0;
    variable bw_exp : std_logic := '0';

    impure function rnd_sl return std_logic is
    begin
      uniform(s1, s2, r);
      if r < 0.5 then return '0'; else return '1'; end if;
    end function;

    impure function rnd_vec(n : natural) return std_logic_vector is
      variable v : std_logic_vector(n-1 downto 0);
    begin
      for i in v'range loop v(i) := rnd_sl; end loop;
      return v;
    end function;

    -- exact equality of a ref output against the other three implementations
    procedure ck3(what_r, what_g, what_g2, what_c : std_logic; name : string) is
    begin
      samples := samples + 3;
      if what_g /= what_r then
        mismatches := mismatches + 1;
        report "MISMATCH gal/   " & name & " ref=" & to_string(what_r) & " gal=" & to_string(what_g) severity error;
      end if;
      if what_g2 /= what_r then
        mismatches := mismatches + 1;
        report "MISMATCH galv2/ " & name & " ref=" & to_string(what_r) & " galv2=" & to_string(what_g2) severity error;
      end if;
      if what_c /= what_r then
        mismatches := mismatches + 1;
        report "MISMATCH cpld/  " & name & " ref=" & to_string(what_r) & " cpld=" & to_string(what_c) severity error;
      end if;
    end procedure;

    procedure ck_exp(sig, e : std_logic; name : string) is
    begin
      if sig /= e then
        mismatches := mismatches + 1;
        report "MISMATCH vs expected " & name & " exp=" & to_string(e) & " got=" & to_string(sig) severity error;
      end if;
    end procedure;

    -- full comparison at one sample point; k = edge index (-1 = pre-clock)
    procedure compare_all(k : integer) is
      constant tag : string := "k=" & integer'image(k);
    begin
      ck3(latch_r, latch_g, latch_g2, latch_c, "LATCH " & tag);
      ck3(npl_r,  npl_g,  npl_g2,  npl_c,  "NPL " & tag);
      ck3(ds_r,   ds_g,   ds_g2,   ds_c,   "DS " & tag);
      ck3(bw_r,   bw_g,   bw_g2,   bw_c,   "BW " & tag);
      ck3(dout_r, dout_g, dout_g2, dout_c, "DOUT " & tag);
      ck3(lclk_r, lclk_g, lclk_g2, lclk_c, "LCLK " & tag);
      ck_exp(bw_r, bw_exp, "BW " & tag);
      -- TCLK: ref vs galv2/cpld must be EXACT (true tri-state recovered);
      -- ref vs galv1: the documented Z-vs-driven-0 delta under W=1 is counted.
      samples := samples + 3;
      if tclk_g /= tclk_r then
        if (tclk_r = 'Z') and (tclk_g = '0') and (tw = '1' and bfirst = '1') then
          delta_z0 := delta_z0 + 1;  -- documented delta pattern only
        else
          mismatches := mismatches + 1;
          report "MISMATCH gal/ TCLK " & tag & " ref=" & to_string(tclk_r) &
                 " gal=" & to_string(tclk_g) & " tw=" & to_string(tw) &
                 " bfirst=" & to_string(bfirst) severity error;
        end if;
      end if;
      if tclk_g2 /= tclk_r then
        mismatches := mismatches + 1;
        report "MISMATCH galv2/ TCLK " & tag & " ref=" & to_string(tclk_r) & " galv2=" & to_string(tclk_g2) severity error;
      end if;
      if tclk_c /= tclk_r then
        mismatches := mismatches + 1;
        report "MISMATCH cpld/ TCLK " & tag & " ref=" & to_string(tclk_r) & " cpld=" & to_string(tclk_c) severity error;
      end if;
    end procedure;

    procedure do_latch(src : natural) is  -- 0=B, 4=R, 2=both
    begin
      if src = 0 or src = 2 or src = 3 then blatch <= '1'; end if;
      if src = 1 or src = 2 or src = 4 then rlatch <= '1'; end if;
      wait for 60 ns;
      blatch <= '0'; rlatch <= '0';
      wait for HP;                 -- protocol keeps clock idle around the latch
      bw_exp := '0';               -- reference expectation: every FF cleared
    end procedure;

    -- one frame: 16 bits; lsrc: 0=BLATCH,1=RLATCH,2=both; latched=false keeps
    -- prior state (out-of-protocol directed sticky test)
    procedure run_frame(bs : std_logic_vector(11 downto 0); er, ec : std_logic;
                        wsel : natural; td, ld : std_logic; lsrc : natural;
                        latched : boolean := true) is
      variable exp : std_logic_vector(0 to 16);
    begin
      frames := frames + 1;
      case wsel is
        when 0 => tw <= '0'; bfirst <= '0';
        when 1 => tw <= '0'; bfirst <= '1';
        when 2 => tw <= '1'; bfirst <= '0';
        when others => tw <= '1'; bfirst <= '1';
      end case;
      tdata <= td; ldata <= ld;
      buttons <= bs; endrow <= er; endcol <= ec;
      wait for 1 ns;

      exp(0 to 7)  := bs(11 downto 4);
      exp(8 to 11) := bs(3 downto 0);
      exp(12) := '1'; exp(13) := '1'; exp(14) := er; exp(15) := ec;
      -- the 17th observed bit is the DS-injected neighbour bit of THIS frame;
      -- W comes from the argument (signals assigned above settle a delta later)
      if wsel = 3 then exp(16) := ld; else exp(16) := td; end if;

      if latched then do_latch(lsrc); end if;

      -- first bit MUST be on the chain output before the first clock edge.
      -- (Expected content is defined only for frames that start with a latch.)
      if latched then
        wait for 1 ns;
        samples := samples + 4;
        ck_exp(dout_r, exp(0), "first-bit ref");
        ck_exp(dout_g, exp(0), "first-bit gal");
        ck_exp(dout_g2, exp(0), "first-bit galv2");
        ck_exp(dout_c, exp(0), "first-bit cpld");
      end if;
      compare_all(-1);

      for k in 1 to 16 loop
        bclk <= '1';
        -- sticky model: the flag sets AT the 16th edge of a latched frame whose
        -- bit 16 (this tile's T_endcol) is '1'
        if latched and k = 16 and exp(15) = '1' then bw_exp := '1'; end if;
        wait for 1 ns;                 -- sample just after the rising edge
        compare_all(k);
        if latched then
          samples := samples + 4;
          ck_exp(dout_r, exp(k), "frame bit ref k=" & integer'image(k));
          ck_exp(dout_g, exp(k), "frame bit gal k=" & integer'image(k));
          ck_exp(dout_g2, exp(k), "frame bit galv2 k=" & integer'image(k));
          ck_exp(dout_c, exp(k), "frame bit cpld k=" & integer'image(k));
        end if;
        wait for HP - 1 ns;
        bclk <= '0'; wait for HP;
        compare_all(k * 100);          -- low phase: no-W-dependent divergence
      end loop;
    end procedure;

  begin
    ------------------------------------------------------------------
    report "glue_equiv_tb: start" severity note;

    -- d1: W=1 (turn left), T_endcol=1 -> B_W sets on the 16th edge
    do_latch(2);
    run_frame(x"ABC", '0', '1', 3, '0', '1', 2);
    assert bw_r = '1' report "d1: B_W must be set after endcol=1 frame" severity error;

    -- d2: W=0 (straight up), T_endcol=0 -> B_W stays clear
    run_frame(x"555", '1', '0', 1, '1', '0', 0);
    assert bw_r = '0' report "d2: B_W must stay clear" severity error;

    -- d3: sticky across an UNLATCHED frame (out-of-protocol by design), then clear
    run_frame(x"F0F", '1', '1', 3, '1', '1', 2);
    run_frame(x"123", '0', '0', 3, '0', '0', 2, latched => false);
    assert bw_r = '1' report "d3: B_W sticky across unlatched frame" severity error;
    run_frame(x"123", '0', '0', 3, '0', '0', 2);
    assert bw_r = '0' report "d3: B_W cleared by latch" severity error;

    -- d4: mid-frame re-latch must restart the counter and the chain
    buttons <= x"777"; endrow <= '1'; endcol <= '1'; tw <= '1'; bfirst <= '1';
    wait for 1 ns;
    do_latch(2);
    for k in 1 to 8 loop bclk <= '1'; wait for HP; bclk <= '0'; wait for HP; end loop;
    assert bw_r = '0' report "d4: B_W before the boundary must be clear" severity error;
    do_latch(2);
    wait for 1 ns;
    ck_exp(dout_r, '0', "d4: chain reloaded after mid-frame latch");  -- x"777": bit11=0
    ck_exp(dout_g, '0', "d4: chain reloaded gal");
    ck_exp(dout_c, '0', "d4: chain reloaded cpld");
    for k in 1 to 15 loop bclk <= '1'; wait for HP; bclk <= '0'; wait for HP; end loop;
    assert bw_r = '0' report "d4: B_W must set only at the 16th edge after re-latch" severity error;
    bclk <= '1'; wait for 1 ns;
    assert bw_r = '1' report "d4: B_W set at the 16th edge after re-latch" severity error;
    assert bw_g = '1' and bw_g2 = '1' and bw_c = '1'
      report "d4: B_W boundary equal in all implementations" severity error;
    bclk <= '0'; wait for HP;
    bw_exp := '1';

    -- d5: all four (T_W, B_first) combinations, distinctive DS sources
    run_frame(x"AAA", '1', '1', 0, '1', '0', 1);
    run_frame(x"AAA", '1', '1', 1, '1', '0', 0);
    run_frame(x"AAA", '1', '1', 2, '0', '1', 1);
    run_frame(x"AAA", '1', '1', 3, '0', '1', 2);

    -- d6: latch via BLATCH only / RLATCH only
    run_frame(x"0F0", '0', '1', 1, '1', '1', 0);
    run_frame(x"0F0", '0', '1', 1, '1', '1', 1);

    ------------------------------------------------------------------
    -- randomized frames (protocol-legal: always latched; W static per frame)
    for f in 1 to 250 loop
      run_frame(rnd_vec(12), rnd_sl, rnd_sl,
                (frames mod 4),          -- round-robins all W combos + randoms below
                rnd_sl, rnd_sl, frames mod 5 mod 3);
      if f mod 3 = 0 then
        run_frame(rnd_vec(12), rnd_sl, rnd_sl,
                  (abs(f * 7) mod 4), rnd_sl, rnd_sl, (f mod 2));
      end if;
    end loop;

    ------------------------------------------------------------------
    report "glue_equiv_tb: frames=" & integer'image(frames) &
           " samples=" & integer'image(samples) &
           " documented TCLK Z-vs-0 deltas (gal v1 only, W=1) =" & integer'image(delta_z0) &
           " mismatches=" & integer'image(mismatches) severity note;

    assert delta_z0 >= 34
      report "documented Z-vs-0 delta was NOT exercised enough (increase coverage)"
      severity error;
    assert mismatches = 0
      report "GLUE EQUIVALENCE: FAIL (" & integer'image(mismatches) & " mismatches)"
      severity failure;
    report "GLUE EQUIVALENCE: PASS" severity note;
    std.env.stop;
  end process;

end sim;
