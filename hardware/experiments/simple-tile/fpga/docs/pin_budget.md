# Pin budget — single-PCB FPGA tile (per-tile FPGA pin count, exact)

Rev-A net merges from the protocol pin table (docs/architecture/protocol.md)
applied: B_clk/R_clk are ONE board net (J103.2 = J104.2) → one `clk_pin`;
latch forward T_latch = L_latch (J102.6 = J101.5) → one `latcho`;
chain out B_data = R_data (J103.3 = J104.3) → one `dout`. Presence straps
T_first/B_endcol/R_endrow are PCB GND, no FPGA pin.

| tile net | connector pin(s) | direction | pull | FPGA pins |
|---|---|---|---|---|
| 12 keys (SMD hotswap, one key/contact) | – | in | none | 12 |
| shift clock in (merged) | J103.2 = J104.2 | in | UP | 1 |
| latch in ×2 | J103.6 (below), J104.5 (right) | in | DOWN | 2 |
| serial data in ×2 | J102.3 (top), J101.3 (left) | in | DOWN | 2 |
| presence straps in ×4 | J102.7 T_W, J102.4 T_endcol, J103.5 B_first, J101.4 L_endrow | in | UP | 4 |
| clock out top (tri-state) | J102.2 | out (Z-able) | – | 1 |
| clock out left (tri-state) | J101.2 | out (Z-able) | – | 1 |
| latch forward out | J102.6 = J101.5 | out | – | 1 |
| chain data out | J103.3 = J104.3 | out | – | 1 |
| B_W column-end out | J103.7 | out | – | 1 |
| **total user I/O** | | | | **26** |

(+1 spare-input-quality note: in SNAP_MODE="track" the snapshot clock is
on-chip: OSCZ / SB_HFOSC, no pin; only the LP8K top carries a `sysclk_pin`
for the BX module osc, see synth/tile_lp8k.pcf. In "fall" mode no sysclk pin
is consumed anywhere.)

The RTL sim core keeps B_clk/R_clk as two ports (wired to the one pin in the
tops) to preserve the reference TB wiring; nextpnr places one pad IBUF plus
the automatic clock BUFG on the same pad (cells `u_tile.b_clk_IBUF_O` +
`u_tile.b_clk_BUFG` in results/build/*_pnr.json) — pad total stays 26.

## Empirical usable-I/O census (nextpnr chipdb probes)

| device / package | IO pads available (probe) | needed (26) | fit |
|---|---|---|---|
| GW1NZ-LV1QN48 (QN48) | 41 of 48 (missing: 1,2,12,25,26,36,37) | 26 | OK |
| iCE40UP5K-SG48 | 39 (missing: 1,5,7,8,22,24,29,30,33) | 26 | OK |
| iCE40LP8K-CM81 (TinyFPGA BX dev) | 60 IO-capable; BX edge exposes 31 GPIO + clk B2 | 26 (+1 sysclk in track) | OK (tight) |

Method: one-output design with `IO_LOC "o" <n>` / `set_io o <pad>` swept over
pads; logs/scripts used the /tmp/opencode/fpga-probe scratch dir (throwaway);
the same pad==usable criterion is self-checking inside run_synth.sh runs.
Vendor datasheet pinout cross-check (Gowin DS861) still pending — the QN48
power-JTAG pin identity {1,2,12,25,26,36,37} is inferred ("not placeable"),
not datasheet-named.

## Pad pulls

- Gowin LVCMOS33 pads implement PULL_MODE=UP **and** DOWN: all ten rev-A pin
  pulls map to pad config, zero BOM delta (synth/tile_gw1nz.cst).
- iCE40 pads implement pull-UP only: the four rev-A DOWN pulls (t_data,
  l_data, b_latch, r_latch) need **+4 board resistors (10 k 0402 class)** per
  tile on the UP5K/LP8K variants.

## True tri-state clock outputs

T_clk/L_clk synth to real tri-state IO cells: TBUF on GW1NZ, SB_IO tristate
on iCE40 (verified in results/build/*_pnr.json and synth logs, both modes).
