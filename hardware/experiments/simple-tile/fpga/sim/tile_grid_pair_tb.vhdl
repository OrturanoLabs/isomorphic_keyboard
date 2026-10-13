-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Grid equivalence testbench: TWO identical W x H tile grids in one sim,
-- REF = unmodified rev-A behavioural tiles (hardware/simulation/tile.vhdl),
-- DUT = tile_fpga candidates, driven by the same controller waveforms.
--
-- Checks (both grids, both scans):
--   * bit-exact stream vs the docs-derived reference (tile_reg_pkg) and
--     REF-vs-DUT per-sample equality (first bit before first shift clock),
--   * B_W flag timing of every traversed column on BOTH grids per edge,
--   * T_clk/L_clk selection (W mux, true tristate Z) of BOTH grids'
--     controller tiles per edge,
--   * B_data of every tile: REF-vs-DUT net equality per edge,
--   * frame decode: markers '11', flag bits, identity,
--   * two latch-reset scans (reset coverage).
-- RAGGED layouts: ragged reachability is already characterised in
-- ../../regression/; here they are only checked REF-vs-DUT identical.
--
-- Zero-delay 20 MHz behavioural sim establishes FUNCTIONALITY ONLY.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

use work.tile_reg_pkg.all;

entity tile_grid_pair_tb is
  generic (
    NAME    : string  := "unnamed";
    W       : natural := 1;
    H       : natural := 1;
    PRESENT : string  := "1";
    BMODE   : natural := 0;
    TAIL    : natural := 32;
    RAGGED  : natural := 0;
    SNAP    : string  := "fall"      -- snapshot mode of the DUT core
  );
end entity;

architecture sim of tile_grid_pair_tb is

  constant TCLK : time := 50 ns;    -- 20 MHz shift clock (behavioural)
  constant TSYS : time := 10 ns;    -- snapshot clock for the DUT grid

  constant pmap : t_map(0 to W*H-1) := parse_present(PRESENT, W, H);
  constant h1      : natural := contig_height(pmap, W, H, 1);
  constant ncol    : natural := traversed_columns(pmap, W, H);
  constant nfr     : natural := reachable_frames(pmap, W, H);
  constant npres   : natural := count_present(pmap, W, H);
  constant nbits   : natural := nfr*FRAME_BITS + TAIL;
  constant exp     : std_logic_vector(0 to nbits-1) :=
                       expected_stream(pmap, W, H, BMODE, nbits);

  signal sysclk : std_logic := '0';
  signal clk_ref, latch_ref, data_ref : std_logic := '0';
  signal clk_dut, latch_dut, data_dut : std_logic := '0';

  type t_net is array (natural range <>, natural range <>) of std_logic;

  -- REF grid nets (implicit 'Z' open-connector default driver everywhere)
  signal vW, vEC, vFirst, vLatch, vClk, vData : t_net(1 to W, 1 to H+1) :=
    (others => (others => 'Z'));
  signal hER, hLatch, hClk, hData : t_net(0 to W, 1 to H) :=
    (others => (others => 'Z'));

  -- DUT grid nets (identical topology, separate drivers)
  signal vWd, vECd, vFirstd, vLatchd, vClkd, vDatad : t_net(1 to W, 1 to H+1) :=
    (others => (others => 'Z'));
  signal hERd, hLatchd, hClkd, hDatad : t_net(0 to W, 1 to H) :=
    (others => (others => 'Z'));

begin

  sysclk <= not sysclk after TSYS/2;

  hClk(0, 1)   <= clk_ref;
  hLatch(0, 1) <= latch_ref;
  data_ref     <= hData(0, 1);

  hClkd(0, 1)   <= clk_dut;
  hLatchd(0, 1) <= latch_dut;
  data_dut      <= hDatad(0, 1);

  ref_tiles : for c in 1 to W generate
    ref_rows : for r in 1 to H generate
      ref_has : if present_at(pmap, W, H, c, r) generate
        u_t : entity work.tile
          port map (
            buttons  => buttons_for(BMODE, c, r),
            T_W      => vW(c, r+1),   T_endcol => vEC(c, r+1),
            T_first  => vFirst(c, r+1), T_latch => vLatch(c, r+1),
            T_clk    => vClk(c, r+1),  T_data  => vData(c, r+1),
            B_W      => vW(c, r),     B_endcol => vEC(c, r),
            B_first  => vFirst(c, r),  B_latch => vLatch(c, r),
            B_clk    => vClk(c, r),    B_data  => vData(c, r),
            L_endrow => hER(c, r),     L_latch => hLatch(c, r),
            L_clk    => hClk(c, r),    L_data  => hData(c, r),
            R_endrow => hER(c-1, r),   R_latch => hLatch(c-1, r),
            R_clk    => hClk(c-1, r),  R_data  => hData(c-1, r)
          );
      end generate;
    end generate;
  end generate;

  dut_tiles : for c in 1 to W generate
    dut_rows : for r in 1 to H generate
      dut_has : if present_at(pmap, W, H, c, r) generate
        u_t : entity work.tile_fpga
          generic map (SNAP_MODE => SNAP)
          port map (
            buttons  => buttons_for(BMODE, c, r),
            sysclk   => sysclk,
            T_W      => vWd(c, r+1),  T_endcol => vECd(c, r+1),
            T_first  => vFirstd(c, r+1), T_latch => vLatchd(c, r+1),
            T_clk    => vClkd(c, r+1), T_data  => vDatad(c, r+1),
            B_W      => vWd(c, r),    B_endcol => vECd(c, r),
            B_first  => vFirstd(c, r), B_latch => vLatchd(c, r),
            B_clk    => vClkd(c, r),   B_data  => vDatad(c, r),
            L_endrow => hERd(c, r),    L_latch => hLatchd(c, r),
            L_clk    => hClkd(c, r),   L_data  => hDatad(c, r),
            R_endrow => hERd(c-1, r),  R_latch => hLatchd(c-1, r),
            R_clk    => hClkd(c-1, r), R_data  => hDatad(c-1, r)
          );
      end generate;
    end generate;
  end generate;

  checker : process
    variable got_dut : std_logic_vector(0 to nbits-1);
    variable frame   : std_logic_vector(15 downto 0);
    variable e       : natural;
    variable bwexp   : std_logic;
  begin
    report "=== tile_grid_pair_tb " & NAME & " W=" & integer'image(W) &
           " H=" & integer'image(H) & " present=" & integer'image(npres) &
           " traversed_frames=" & integer'image(nfr) &
           " tail=" & integer'image(TAIL) & " ragged=" & integer'image(RAGGED) &
           " snap=" & SNAP;

    assert present_at(pmap, W, H, 1, 1)
      report NAME & ": controller tile (c=1,r=1) must be present"
      severity failure;
    if RAGGED = 0 then
      assert nfr = npres
        report NAME & ": legal layout expected but " &
               integer'image(npres - nfr) & " of " & integer'image(npres) &
               " tiles are unreachable"
        severity failure;
    end if;

    for pass in 1 to 2 loop               -- two scans: reset coverage

      latch_ref <= '1'; latch_dut <= '1';
      wait for 4*TCLK;                    -- >> sysclk period: shadow loaded
      latch_ref <= '0'; latch_dut <= '0';
      wait for TCLK/2 - 5 ns;

      -- B_W sticky flags must be cleared by the latch before the scan
      for cc in 1 to ncol loop
        assert to_x01(vW(cc, 1)) = '0'
          report NAME & " pass" & integer'image(pass) &
                 ": REF B_W col" & integer'image(cc) & " not cleared"
          severity failure;
        assert to_x01(vWd(cc, 1)) = '0'
          report NAME & " pass" & integer'image(pass) &
                 ": DUT B_W col" & integer'image(cc) & " not cleared"
          severity failure;
      end loop;

      -- first bit BEFORE first shift clock, both impls, both vs reference
      assert to_x01(data_ref) = exp(0) and to_x01(data_dut) = exp(0)
        report NAME & " pass" & integer'image(pass) &
               ": first bit not present before first shift clock" &
               " (ref=" & std_logic'image(to_x01(data_ref)) &
               " dut=" & std_logic'image(to_x01(data_dut)) &
               " exp=" & std_logic'image(exp(0)) & ")"
        severity failure;

      e := 0;
      while e < nbits loop
        -- sample before the shift clock (firmware get_bit, then c1)
        assert data_dut = '0' or data_dut = '1' or
               data_dut = 'L' or data_dut = 'H'
          report NAME & " pass" & integer'image(pass) &
                 ": DUT stream bit" & integer'image(e) &
                 " is not a driven/pulled logic level"
          severity failure;
        got_dut(e) := to_x01(data_dut);
        assert got_dut(e) = exp(e)
          report NAME & " pass" & integer'image(pass) &
                 ": DUT stream bit" & integer'image(e) & " got " &
                 std_logic'image(got_dut(e)) & " expected " &
                 std_logic'image(exp(e))
          severity failure;
        assert to_x01(data_ref) = to_x01(data_dut)
          report NAME & " pass" & integer'image(pass) &
                 ": REF/DUT stream mismatch at bit" & integer'image(e)
          severity failure;

        clk_ref <= '1'; clk_dut <= '1';      -- one shift everywhere
        wait for 10 ns;
        e := e + 1;

        -- per-edge B_W flag timing, both grids
        for cc in 1 to ncol loop
          if e >= bw_set_edge(pmap, W, H, cc) then bwexp := '1';
          else bwexp := '0'; end if;
          assert to_x01(vW(cc, 1)) = bwexp
            report NAME & " pass" & integer'image(pass) &
                   ": edge" & integer'image(e) & " REF B_W(col" &
                   integer'image(cc) & ") got " & std_logic'image(vW(cc, 1)) &
                   " expected " & std_logic'image(bwexp) severity failure;
          assert to_x01(vWd(cc, 1)) = bwexp
            report NAME & " pass" & integer'image(pass) &
                   ": edge" & integer'image(e) & " DUT B_W(col" &
                   integer'image(cc) & ") got " & std_logic'image(vWd(cc, 1)) &
                   " expected " & std_logic'image(bwexp) severity failure;
        end loop;

        -- per-edge B_data REF-vs-DUT equality of every TRAVERSED tile (the
        -- tiles the chain actually visits; they have received the latch and
        -- shift clocks). Unreachable ragged tiles are excluded: the ref 165
        -- model leaves them 'U' forever while the DUT power-up-inits to '0'
        -- -- no scan-observable difference. Compare resolved levels
        -- (to_x01): the reference '165 shifts weak pull levels through while
        -- the DUT resolves pulls at the pin.
        for cc in 1 to ncol loop
          for rr in 1 to contig_height(pmap, W, H, cc) loop
            if present_at(pmap, W, H, cc, rr) then
              assert to_x01(vData(cc, rr)) = to_x01(vDatad(cc, rr))
                report NAME & " pass" & integer'image(pass) &
                       ": edge" & integer'image(e) & " tile(" &
                       integer'image(cc) & "," & integer'image(rr) &
                       ") B_data ref=" & std_logic'image(vData(cc, rr)) &
                       " dut=" & std_logic'image(vDatad(cc, rr))
                severity failure;
            end if;
          end loop;
        end loop;

        wait for TCLK/2 - 10 ns;
        clk_ref <= '0'; clk_dut <= '0';
        wait for 5 ns;

        -- W mux / tri-state clock selection of both controller tiles
        if e < FRAME_BITS*(h1 - 1) then
          assert vClk(1, 2) = '0' and vClkd(1, 2) = '0'
            report NAME & ": edge" & integer'image(e) &
                   " T_clk of (1,1) should still forward the clock"
            severity failure;
        else
          assert vClk(1, 2) = 'Z' and vClkd(1, 2) = 'Z'
            report NAME & ": edge" & integer'image(e) &
                   " T_clk of (1,1) should be released (Z)"
            severity failure;
        end if;
        if W >= 2 and present_at(pmap, W, H, 2, 1) then
          if e >= FRAME_BITS*(h1 - 1) then
            assert hClk(1, 1) = '0' and hClkd(1, 1) = '0'
              report NAME & ": edge" & integer'image(e) &
                     " L_clk of (1,1) should forward the clock"
              severity failure;
          else
            assert hClk(1, 1) = 'Z' and hClkd(1, 1) = 'Z'
              report NAME & ": edge" & integer'image(e) &
                     " L_clk of (1,1) should not be driven yet"
              severity failure;
          end if;
        end if;
        wait for TCLK/2 - 5 ns;
      end loop;
    end loop;

    -- per-frame decode of the DUT stream: markers, flags, identity
    for f in 0 to nfr-1 loop
      for i in 0 to FRAME_BITS-1 loop
        frame(FRAME_BITS-1 - i) := got_dut(f*FRAME_BITS + i);
      end loop;
      assert frame(3 downto 2) = "11"
        report NAME & ": DUT frame" & integer'image(f) & " markers=" &
               to_hstring(frame(3 downto 2)) & " (framing error)"
        severity failure;
      report NAME & " DUT frame" & integer'image(f) &
             " word=" & to_hstring(frame) &
             " endrow=" & std_logic'image(frame(1)) &
             " endcol=" & std_logic'image(frame(0));
    end loop;

    report "REGPASS " & NAME & " frames=" & integer'image(nfr) &
           " bits=" & integer'image(nbits) &
           " (2 passes, stream+flags+mux+B_data grid equality)";
    finish;
    wait;
  end process;

end architecture;
