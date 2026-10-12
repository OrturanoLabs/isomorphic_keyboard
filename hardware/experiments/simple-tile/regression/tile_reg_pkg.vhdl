-- SPDX-License-Identifier: CERN-OHL-S-2.0
--
-- Reference model for the rev-A tile scan protocol, derived from
-- docs/architecture/protocol.md (NOT from tile.vhdl), used to check the
-- behavioural DUT (hardware/simulation/tile.vhdl + 74hc165.vhdl).
--
-- Documented wire order per tile frame (16 bits, first bit is present on the
-- data line BEFORE the first shift clock -- firmware `get_bit` then `c1`):
--   j =  0 .. 11 : buttons(11) .. buttons(0)        (key states, stream order)
--   j = 12, 13   : markers, always '1'              (framing, else firmware err)
--   j = 14       : L_endrow, '0' = a tile is present immediately to the left
--   j = 15       : T_endcol, '1' = this tile is the top of its column
-- (This equals the firmware table bit 15..0 reversed by construction.)
--
-- Grid model: columns c = 1..W (c = 1 = rightmost, controller attached to its
-- bottom tile), rows r = 1..H bottom-up. The scan chain is legal/meaningful only
-- while each column's tiles are contiguous from row 1 and each traversed
-- column's bottom tile exists; this package computes the reachable traversal
-- exactly, so ragged layouts are characterised instead of assumed legal.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package tile_reg_pkg is

  constant FRAME_BITS : natural := 16;

  -- flat presence map, index (r-1)*W + (c-1), c in 1..W, r in 1..H
  type t_map is array (natural range <>) of boolean;

  -- PRESENT string: length W*H, row 1 first ('1' = tile present),
  -- inside a row columns are listed right-to-left (c = 1 .. W).
  function parse_present(s : string; W : natural; H : natural) return t_map;

  function present_at(g : t_map; W : natural; H : natural; c : natural; r : natural)
    return boolean;

  -- contiguous stack height of column c starting at row 1 (0 if bottom missing)
  function contig_height(g : t_map; W : natural; H : natural; c : natural) return natural;

  -- number of columns that can be traversed (stops at first missing bottom tile)
  function traversed_columns(g : t_map; W : natural; H : natural) return natural;

  -- total frames the scan reads back (= reachable tiles)
  function reachable_frames(g : t_map; W : natural; H : natural) return natural;

  function count_present(g : t_map; W : natural; H : natural) return natural;

  -- 0 = scan ends cleanly at the left edge, 1 = scan stopped by a missing
  -- bottom tile of a column while a previous frame said "tile to the left" --
  -- only meaningful when traversed_columns < W or count differs.
  function stop_by_bottom_hole(g : t_map; W : natural; H : natural) return boolean;

  -- global 1-indexed clock edge on which column c starts receiving clocks
  function g_edge(g : t_map; W : natural; H : natural; c : natural) return natural;

  -- global 1-indexed clock edge after which bottom(c).B_W must be set ('1')
  function bw_set_edge(g : t_map; W : natural; H : natural; c : natural) return natural;

  -- 16-bit frame in wire order (index 0 = first bit on the wire)
  function frame_wire(g : t_map; W : natural; H : natural;
                      c : natural; r : natural;
                      buttons : std_logic_vector(11 downto 0))
    return std_logic_vector;

  -- whole expected stream: traversal frames, then idle '0' tail
  function expected_stream(g : t_map; W : natural; H : natural;
                           bmode : natural; nbits : natural)
    return std_logic_vector;

  -- key stimulus patterns (independent stimulus generation; bmode:
  -- 0 = per-tile distinctive pattern carrying (c, r) identity,
  -- 1 = all pressed, 2 = all released)
  function buttons_for(bmode : natural; c : natural; r : natural)
    return std_logic_vector;

end package;

package body tile_reg_pkg is

  function parse_present(s : string; W : natural; H : natural) return t_map is
    variable g : t_map(0 to W*H - 1);
    variable r, c : natural;
  begin
    assert s'length = W*H
      report "PRESENT length " & integer'image(s'length) &
             " /= W*H = " & integer'image(W*H)
      severity failure;
    for i in 0 to W*H - 1 loop
      r := i / W + 1;            -- row 0 string slice first = bottom row
      c := i mod W + 1;          -- within row: right-to-left
      assert s(s'low + i) = '0' or s(s'low + i) = '1'
        report "PRESENT: bad char '" & s(s'low + i) & "'" severity failure;
      g((r - 1)*W + (c - 1)) := (s(s'low + i) = '1');
    end loop;
    return g;
  end;

  function present_at(g : t_map; W : natural; H : natural; c : natural; r : natural)
    return boolean is
  begin
    if c < 1 or c > W or r < 1 or r > H then
      return false;
    end if;
    return g((r - 1)*W + (c - 1));
  end;

  function contig_height(g : t_map; W : natural; H : natural; c : natural) return natural is
    variable hh : natural := 0;
  begin
    while hh < H and present_at(g, W, H, c, hh + 1) loop
      hh := hh + 1;
    end loop;
    return hh;
  end;

  function traversed_columns(g : t_map; W : natural; H : natural) return natural is
    variable n : natural := 0;
  begin
    while n < W and present_at(g, W, H, n + 1, 1) loop
      n := n + 1;
    end loop;
    return n;
  end;

  function reachable_frames(g : t_map; W : natural; H : natural) return natural is
    variable n : natural := 0;
  begin
    for c in 1 to traversed_columns(g, W, H) loop
      n := n + contig_height(g, W, H, c);
    end loop;
    return n;
  end;

  function count_present(g : t_map; W : natural; H : natural) return natural is
    variable n : natural := 0;
  begin
    for i in g'range loop
      if g(i) then
        n := n + 1;
      end if;
    end loop;
    return n;
  end;

  function stop_by_bottom_hole(g : t_map; W : natural; H : natural) return boolean is
  begin
    return traversed_columns(g, W, H) < W;
  end;

  function g_edge(g : t_map; W : natural; H : natural; c : natural) return natural is
    variable e : natural := 1;
  begin
    for i in 1 to c - 1 loop
      e := e + FRAME_BITS * (contig_height(g, W, H, i) - 1);
    end loop;
    return e;
  end;

  function bw_set_edge(g : t_map; W : natural; H : natural; c : natural) return natural is
  begin
    return g_edge(g, W, H, c) - 1 + FRAME_BITS * contig_height(g, W, H, c);
  end;

  function buttons_for(bmode : natural; c : natural; r : natural)
    return std_logic_vector is
    variable v : unsigned(11 downto 0);
  begin
    case bmode is
      when 1 =>                         -- all keys pressed
        return x"FFF";
      when 2 =>                         -- all keys released
        return x"000";
      when others =>                    -- distinctive: embeds (c, r) + hash
        v := to_unsigned(c mod 16, 4) & to_unsigned(r mod 16, 4) &
              to_unsigned((c*5 + r*9 + c*r*3 + 6) mod 16, 4);
        return std_logic_vector(v);
    end case;
  end;

  function frame_wire(g : t_map; W : natural; H : natural;
                      c : natural; r : natural;
                      buttons : std_logic_vector(11 downto 0))
    return std_logic_vector is
    variable f : std_logic_vector(0 to FRAME_BITS - 1);
  begin
    for j in 0 to 11 loop
      f(j) := buttons(11 - j);          -- buttons(11) first on the wire
    end loop;
    f(12) := '1';                       -- markers
    f(13) := '1';
    if present_at(g, W, H, c + 1, r) then
      f(14) := '0';                     -- L_endrow: 0 = tile to the left
    else
      f(14) := '1';
    end if;
    if present_at(g, W, H, c, r + 1) then
      f(15) := '0';                     -- T_endcol: 1 = top of column
    else
      f(15) := '1';
    end if;
    return f;
  end;

  function expected_stream(g : t_map; W : natural; H : natural;
                           bmode : natural; nbits : natural)
    return std_logic_vector is
    variable ret : std_logic_vector(0 to nbits - 1) := (others => '0');
    variable f   : std_logic_vector(0 to FRAME_BITS - 1);
    variable idx : natural := 0;
    variable hh  : natural;
  begin
    for c in 1 to traversed_columns(g, W, H) loop
      hh := contig_height(g, W, H, c);
      for r in 1 to hh loop
        f := frame_wire(g, W, H, c, r, buttons_for(bmode, c, r));
        for j in 0 to FRAME_BITS - 1 loop
          if idx < nbits then
            ret(idx) := f(j);
          end if;
          idx := idx + 1;
        end loop;
      end loop;
    end loop;
    return ret;                         -- tail stays '0'
  end;

end package body;
