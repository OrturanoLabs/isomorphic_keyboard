-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Self-checking behavioural regression testbench for the rev-A tile chain.
--
-- Instantiates a W x H grid of *real* tile models (hardware/simulation/tile.vhdl)
-- with tile-to-tile wiring only where a tile is present (open connectors fall
-- back to the modelled pin pull-ups/down, exactly like an unmated edge), drives
-- the documented latch + sample-before-shift-clock 20 MHz sequence from the
-- controller tile at (c=1, r=1), and checks the received stream bit-by-bit
-- against the independently generated docs-derived reference (tile_reg_pkg).
--
-- Per edge it also checks: B_W (column-end flag) timing of every traversed
-- column, and the T_clk/L_clk selection (W mux) of the controller tile.
-- Anything but an exact match is severity failure -> simulator exits nonzero.
--
-- RAGGED=1: expects tiles to be unreachable; classifies the loss as SILENT
-- (scan stops cleanly) or LOUD (firmware-visible framing error) and asserts it.
--
-- Zero-delay behavioural run at 20 MHz: establishes FUNCTIONALITY ONLY,
-- not achievable hardware timing.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

use work.tile_reg_pkg.all;

entity tile_grid_tb is
  generic (
    NAME    : string  := "unnamed";
    W       : natural := 1;
    H       : natural := 1;
    PRESENT : string  := "1";       -- row 1 first, within a row c = 1..W (right first)
    BMODE   : natural := 0;          -- 0 distinctive keys, 1 all pressed, 2 all released
    TAIL    : natural := 32;         -- extra bits read after the last expected frame
    RAGGED  : natural := 0           -- 1: expect unreachable tiles, classify detection
  );
end entity;

architecture sim of tile_grid_tb is

  constant TCLK : time := 50 ns;    -- 20 MHz shift clock (behavioural)

  constant pmap : t_map(0 to W*H-1) := parse_present(PRESENT, W, H);
  constant h1      : natural := contig_height(pmap, W, H, 1);
  constant ncol    : natural := traversed_columns(pmap, W, H);
  constant nfr     : natural := reachable_frames(pmap, W, H);
  constant npres   : natural := count_present(pmap, W, H);
  constant nbits   : natural := nfr*FRAME_BITS + TAIL;
  constant exp     : std_logic_vector(0 to nbits-1) :=
                       expected_stream(pmap, W, H, BMODE, nbits);

  signal clk, latch, data : std_logic := '0';

  type t_net is array (natural range <>, natural range <>) of std_logic;
  -- nets between (c,r).bottom and (c,r-1).top edge connectors.
  -- IMPORTANT: every net carries an implicit constant 'Z' driver (open
  -- connector). Without it an *unconnected but associated* net would sit at
  -- 'U' and poison the tile inputs (a tile input's own pull only sees 'Z').
  signal vW, vEC, vFirst, vLatch, vClk, vData : t_net(1 to W, 1 to H+1) :=
    (others => (others => 'Z'));
  -- nets between (c,r).left and (c+1,r).right edge connectors; index 0 = controller
  signal hER, hLatch, hClk, hData : t_net(0 to W, 1 to H) :=
    (others => (others => 'Z'));

begin

  -- controller attaches to the bottom edge of tile (1,1)
  hClk(0, 1)   <= clk;
  hLatch(0, 1) <= latch;
  data         <= hData(0, 1);

  tiles : for c in 1 to W generate
    rows : for r in 1 to H generate
      has : if present_at(pmap, W, H, c, r) generate
        u_t : entity work.tile
          port map (
            buttons  => buttons_for(BMODE, c, r),
            T_W      => vW(c, r+1),
            T_endcol => vEC(c, r+1),
            T_first  => vFirst(c, r+1),
            T_latch  => vLatch(c, r+1),
            T_clk    => vClk(c, r+1),
            T_data   => vData(c, r+1),
            B_W      => vW(c, r),
            B_endcol => vEC(c, r),
            B_first  => vFirst(c, r),
            B_latch  => vLatch(c, r),
            B_clk    => vClk(c, r),
            B_data   => vData(c, r),
            L_endrow => hER(c, r),
            L_latch  => hLatch(c, r),
            L_clk    => hClk(c, r),
            L_data   => hData(c, r),
            R_endrow => hER(c-1, r),
            R_latch  => hLatch(c-1, r),
            R_clk    => hClk(c-1, r),
            R_data   => hData(c-1, r)
          );
      end generate;
    end generate;
  end generate;

  checker : process
    variable got     : std_logic_vector(0 to nbits-1);
    variable frame   : std_logic_vector(15 downto 0);
    variable e       : natural;
    variable bwexp   : std_logic;
    variable lastrow : natural;
    variable silent  : boolean;
  begin
    report "=== tile_grid_tb " & NAME & " W=" & integer'image(W) &
           " H=" & integer'image(H) & " present=" & integer'image(npres) &
           " traversed_frames=" & integer'image(nfr) &
           " tail=" & integer'image(TAIL) & " ragged=" & integer'image(RAGGED);

    assert present_at(pmap, W, H, 1, 1)
      report NAME & ": controller tile (c=1,r=1) must be present" severity failure;
    assert RAGGED = 0 or TAIL >= FRAME_BITS
      report NAME & ": RAGGED=1 needs TAIL >= 16 for the overhang frame check"
      severity failure;

    for pass in 1 to 2 loop   -- rescan: proves latch resets counters and B_W flags

      latch <= '1';                       -- parallel load; clears count and B_W
      wait for 4*TCLK;
      latch <= '0';
      wait for TCLK/2 - 5 ns;

      -- the B_W sticky flag must be cleared by the latch before the scan starts
      for cc in 1 to ncol loop
        assert to_x01(vW(cc, 1)) = '0'
          report NAME & " pass " & integer'image(pass) &
                 ": B_W of bottom tile of column" & integer'image(cc) &
                 " not cleared by latch"
          severity failure;
      end loop;

      -- first bit must be valid BEFORE the first shift clock
      assert to_x01(data) = exp(0)
        report NAME & " pass " & integer'image(pass) &
               ": first bit not present before first shift clock"
        severity failure;

      e := 0;
      while e < nbits loop
        -- sample BEFORE the shift clock (firmware: get_bit, then c1).
        -- to_x01 maps the weak pull levels ('H'/'L') to logic values; the
        -- controller line itself must always be a resolved logic level.
        assert data = '0' or data = '1' or data = 'L' or data = 'H'
          report NAME & " pass " & integer'image(pass) &
                 ": stream bit" & integer'image(e) & " is not a driven/pulled " &
                 "logic level: " & std_logic'image(data)
          severity failure;
        got(e) := to_x01(data);
        assert got(e) = exp(e)
          report NAME & " pass " & integer'image(pass) &
                 ": stream bit" & integer'image(e) & " (frame" &
                 integer'image(e/FRAME_BITS) & " bit" &
                 integer'image(FRAME_BITS - 1 - (e mod FRAME_BITS)) & ") " &
                 " got " & std_logic'image(got(e)) & " expected " & std_logic'image(exp(e))
          severity failure;

        clk <= '1';                       -- rising edge: one shift everywhere
        wait for 10 ns;
        e := e + 1;

        -- B_W flag of every traversed column's bottom tile: must set exactly
        -- when the top frame of that column has passed (16*h of its own edges)
        for cc in 1 to ncol loop
          if e >= bw_set_edge(pmap, W, H, cc) then
            bwexp := '1';
          else
            bwexp := '0';
          end if;
          assert to_x01(vW(cc, 1)) = bwexp
            report NAME & " pass " & integer'image(pass) &
                   ": edge" & integer'image(e) & " B_W(col" & integer'image(cc) &
                   ") got " & std_logic'image(vW(cc, 1)) & " expected " & std_logic'image(bwexp)
            severity failure;
        end loop;
        wait for TCLK/2 - 10 ns;
        clk <= '0';
        wait for 5 ns;

        -- W mux / clock selection of the controller tile, checked at clk low.
        -- B_W of row 2 sets on the rising edge of the column's last
        -- upward-forwarded clock (edge 16*(h1-1)); the W mux flips during that
        -- edge's high phase, so at the post-edge low phase:
        --   T_clk is driven iff e < 16*(h1-1), gated to 'Z' from e = 16*(h1-1)
        --   L_clk is driven iff e >= 16*(h1-1) (gated 'Z' before)
        if e < FRAME_BITS*(h1 - 1) then
          assert vClk(1, 2) = '0'
            report NAME & ": edge" & integer'image(e) &
                   " T_clk of (1,1) should still forward the clock"
            severity failure;
        else
          assert vClk(1, 2) = 'Z'
            report NAME & ": edge" & integer'image(e) &
                   " T_clk of (1,1) should be released"
            severity failure;
        end if;
        if W >= 2 and present_at(pmap, W, H, 2, 1) then
          if e >= FRAME_BITS*(h1 - 1) then
            assert hClk(1, 1) = '0'
              report NAME & ": edge" & integer'image(e) &
                     " L_clk of (1,1) should forward the clock to the next column"
              severity failure;
          else
            assert hClk(1, 1) = 'Z'
              report NAME & ": edge" & integer'image(e) &
                     " L_clk of (1,1) should not be driven yet"
              severity failure;
          end if;
        end if;
        wait for TCLK/2 - 5 ns;
      end loop;
    end loop;

    -- per-frame decode: markers, flags, identity
    for f in 0 to nfr-1 loop
      for i in 0 to FRAME_BITS-1 loop
        frame(FRAME_BITS-1 - i) := got(f*FRAME_BITS + i);
      end loop;
      assert frame(3 downto 2) = "11"
        report NAME & ": frame" & integer'image(f) & " marker bits are " &
               to_hstring(frame(3 downto 2)) & " (framing error)"
        severity failure;
      report NAME & " frame" & integer'image(f) & " word=" & to_hstring(frame) &
             " endrow=" & std_logic'image(frame(1)) & " endcol=" & std_logic'image(frame(0));
    end loop;

    if RAGGED = 0 then
      assert nfr = npres
        report NAME & ": legal layout expected but " & integer'image(npres - nfr) &
               " of " & integer'image(npres) & " tiles are unreachable"
        severity failure;
    else
      assert nfr < npres
        report NAME & ": ragged layout expected unreachable tiles, got none"
        severity failure;
      -- classify: if the last delivered frame says "no tile to the left", the
      -- firmware ends the scan cleanly -> SILENT loss; otherwise it reads one
      -- more (all-zero tail) frame and its marker check fails -> LOUD detect
      lastrow := contig_height(pmap, W, H, ncol);
      silent := not present_at(pmap, W, H, ncol + 1, lastrow);
      if silent then
        report NAME & " RAGGED-DETECT: " & integer'image(npres - nfr) &
               " tile(s) out of " & integer'image(npres) &
               " silently lost (scan ends cleanly, no framing error)";
      else
        for i in 0 to FRAME_BITS-1 loop
          frame(FRAME_BITS-1 - i) := got(nfr*FRAME_BITS + i);
        end loop;
        assert frame(3 downto 2) /= "11"
          report NAME & ": expected a framing error in the overhang frame"
          severity failure;
        report NAME & " RAGGED-DETECT: " & integer'image(npres - nfr) &
               " tile(s) out of " & integer'image(npres) &
               " lost, scan flags a framing error (markers=" &
               to_hstring(frame(3 downto 2)) & ") in the following frame";
      end if;
    end if;

    report "REGPASS " & NAME & " frames=" & integer'image(nfr) &
           " bits=" & integer'image(nbits) & " (2 passes, flags+mux checked)";
    finish;
    wait;
  end process;

end architecture;
