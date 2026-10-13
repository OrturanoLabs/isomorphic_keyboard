<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->

# cpld-fit — ATF1502ASV one-chip tile candidate (16 tiles, 20 MHz, no MCU/Hall/LED)

**Retired from the active shortlist; verification handoff retained as reference.**
The current work targets FPGA and the discrete baseline. See
[current development](../../../../docs/architecture/current-development.md).

Advances candidate **C** of the simple-tile logic study (one ATF1502ASV-15AU44
CPLD per tile: glue + both 74LVC165A chains inside) from "behaviour proven in
VHDL, silicon mapping blocked" (logic/README.md §4) to a complete,
machine-checked hand-off package: verified Verilog candidate, device-shaped
techmapped EDIF, real TQFP-44 pin plan, sourced power/BOM/JTAG notes, and the
exact 20 MHz timing gaps. **No device fit is produced or claimed** — the
ATF1500 fitter is proprietary (Microchip ProChip/WinCUPL) and is not present
on this system; `fit/run_fitter.sh` takes a user-provided path and fails
loudly otherwise. Working tree writes are confined to this folder.

## Layout

| path | what |
|---|---|
| `src/tile_cpld.v` | candidate RTL (Verilog port of the read-only `logic/cpld/tile_full.vhdl`); per-bit AP/AR transparent parallel load |
| `src/tile_cpld_tb.v` | self-checking TB: DUT vs tile.vhdl-structured rev-A reference (two transparent '165s + glue) vs a third, docs-derived expected model |
| `sim/mutants/` | two control mutants the TB **must** reject (synchronous load; swapped frame flags) |
| `sim/run_sims.sh` | container runner; PASS requires candidate pass AND mutants caught |
| `synth/atf1502_cells.v` | blackbox ATF1502 primitives (D-FF with AP/AR/CE; tri-state OBUF) per DS20006485A "Flip-Flop"/"I/O Control" |
| `synth/atf1502_techmap.v` | $dffsre/$adff/$adffe/$tribuf → device cells |
| `synth/tile_cpld_atf1502.ys` + `synth/run_synth.sh` | Yosys → techmap → EDIF + structural EDIF validation |
| `constraints/tile_cpld_tqfp44.csv` + `constraints/check_pins.py` | pin plan + checker against a DS Tables 1-6/1-7 capability DB |
| `fit/run_fitter.sh` | explicit-path licensed-fitter wrapper; exit 2 when absent; installs nothing |
| `docs/tqfp44-pinmap.md` | full 44-pin map, capabilities, rationale, fitter risks |
| `docs/ap-ar-mapping.md` | the orthogonal AP/AR transparent-load mapping + PT budget + sourcing |
| `docs/bom-jtag-timing.md` | sourced BOM, JTAG pads, power, 20 MHz phase gaps |
| `results/` | run logs (env/sha pinned), techmapped EDIF (`tile_cpld_atf1502.edif`) |

## Reproduce

```sh
bash hardware/experiments/simple-tile/cpld-fit/sim/run_sims.sh        # TB
bash hardware/experiments/simple-tile/cpld-fit/synth/run_synth.sh     # EDIF
python3 hardware/experiments/simple-tile/cpld-fit/constraints/check_pins.py
bash hardware/experiments/simple-tile/cpld-fit/fit/run_fitter.sh /path/to/fit1502   # needs a licensed fitter
```

Tooling: container `localhost/oss-cad-suite:2026-09-26` (image
58f58619c735ff1e...; Icarus 14.0 devel, Yosys 0.69+154) via `tools/oss.sh`;
host python3 for the checker. No installs anywhere.

## Verified results (this folder's runs at HEAD 6572e0f)

* **Behaviour**: candidate == rev-A-structure reference == docs-derived
  expectation on **1180 checks, 0 errors** — 2 scans (2-tile column traversal
  with mid-scan W flip after edge 16, and rlatch reset) + 4-edge idle tails.
  Pinned: first frame bit valid **before the first shift clock**; key changes
  **during** the latch window tracked (transparent load); frame wire order
  buttons[11..0],1,1,endrow,endcol; B_W set at exactly edge 16·h and sticky;
  tclk/lclk driven/released-**Z** per W; counter reset by both latch sources.
* **TB self-test**: mut_syncload caught on the first-bit + transparency
  checks; mut_flagswap caught on stream bits + B_W timing. (A TB that passes
  either mutant fails the runner.)
* **Mapping (not a fit)**: Yosys stats — 16× ATF1502_FF_D_SR_CE (the AP/AR
  chain), 4× ATF1502_FF_D_AR (counter), 1× ATF1502_FF_D_AR_CE (B_W),
  2× ATF1502_OBUF_TRI (tclk/lclk OE), 60 generic glue cells for the fitter to
  pack into product terms. EDIF validated: balanced s-exprs, 5 device cell
  types, all 17 ports, `buttons[b]` → array member 11−b mapping consistent,
  exact instance counts.
* **Pin plan**: 25 user I/O + GCLK1(bclk); 4 JTAG reserved (1,7,26,32); PD1/PD2
  spare; 1 spare; 44-pin accounting reconciles. Checker negative control
  (bclk on GCLR pin, tclk on TMS pin) fails with 3 errors.

## Blockers (unchanged + sharpened; nothing here is "ready")

1. **Device fit BLOCKED**: no licensed fitter/wine on the system; wrapper
   exits 2; no install performed or offered. Generic cell counts are never a
   fit argument.
2. **STA BLOCKED** with the fit (PT-packing-dependent adders); system timing
   UNKNOWN while `logic/timing/timing.json` assumptions are null.
3. AP/AR same-macrocell allocation to be demonstrated in real fitter output;
   PT3/PT5 numbering is prjbureau-secondary (no network to re-verify).
4. Dynamic power at 20 MHz not in the datasheet; ICC figures are typical
   standby (16 tiles ≈ 0.72 A typ @ standard power).
5. Programming path: SVF/XSVF+JTAG tooling exists (logic/README §6) but the
   .jed input needs the fitter.
