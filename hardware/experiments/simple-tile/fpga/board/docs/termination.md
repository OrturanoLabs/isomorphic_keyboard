# Termination -- merged tile outputs on the certified 19-contact frame

Status: **DECISION RECORDED, NOT EVIDENCE-CLOSED** (2026-10-15, rewritten
after the independent review fpga-01-review P1/P2/P3/P7). "Keep the
certified 19-contact geometry" is an engineering decision whose closure
requires bench evidence (B2) -- no argument here closes it. A structural,
frame-neutral mitigation **is implemented** on the board (r6, section
"Implemented mitigation") so the decision no longer rests on hope alone.

## The question

Five tile outputs are forward-driven toward the chassis contacts:
`T_clk`, `L_clk` (true tri-state TBUF), `L_latch` (= rtl `latcho_pin`,
merged T_latch/L_latch), `B_data` (= rtl `dout_pin`, merged B_data/R_data)
and `B_W`. Is the certified 19-contact frame electrically sufficient, and
what structural mitigation exists that does NOT touch the certified
contact coordinates?

## Net classes and failure physics (from the actual sources)

Topology per connectors/out/report.md (backplane adjacency PASS lines),
rtl/top_gw1nz.vhdl header, and the board JP census:

| net | electrical class | chassis topology |
|---|---|---|
| T_clk (out) | clock, edge-critical | point-to-point to the above tile's merged clk net (one other TBUF driver parked at Z) |
| L_clk (out) | clock, edge-critical | point-to-point, left tile |
| L_latch (out) | latch strobe, edge-critical | **2 branches** (T_latch + L_latch merged): up + left receivers |
| B_data (out) | data level | **2 branches** (B_data + R_data merged): down + right receivers |
| B_W (out) | write level | point-to-point |

Failure rules that follow (and that the pre-review text got wrong):

1. On **edge-critical** nets (clock/strobe) any reflection that re-crosses
   the input threshold -- even if it settles long before the bit cell
   ends -- is a spurious shift/latch edge. Settling is *necessary, not
   sufficient*. The old "settles inside the 50 ns cell" argument is valid
   only for level nets (B_data, B_W).
2. Double-sampling in the destination tile's snap flops is **not line
   termination**: high-Z CMOS inputs reflect with |Γ|≈1; sampling twice
   adds zero damping. The honest pre-B2 description of the interface is
   "unterminated, full far-end reflection; margin rests on edge-rate vs
   run-length and is bench-gated".
3. nextpnr interior-fabric STA (Fmax 213-342 MHz on `u_tile.b_clk`) says
   nothing about board/chassis interconnect -- the driver script itself
   states it "does NOT close board-level 20 MHz system timing". Citing it
   as closure for the chassis nets is a category error (review P1.3).

## Evidence vs assumptions (kept separate on purpose)

**Evidence (machine-reproducible):**
- The cst port attributes `DRIVE=… / SLEW(SLEW_RATE)=…` are *dead in the
  OSS flow*: A/B nextpnr-himbaechel runs (oss-cad-suite 2026-09-26)
  differing only in `DRIVE=2 SLEW=SLOW` vs `DRIVE=24 FAST` produced
  byte-identical bitstreams (out/pnr/tmp/ab_A.fs == ab_B.fs, sha256
  3918ac9c… both; no slew-attribute string in the libexec binary).
- The **RTL attribute path works**: variant B of tools/drive_attr_ab.sh
  (VHDL `attribute DRIVE of <port> : signal is "24"` on the five outputs)
  vs variant A differs in exactly 10 bitstream rows (5 pads × 2 rows);
  the pnr-json diff shows `DRIVE=24` on exactly the five OBUF/TBUF cells,
  nothing else (out/pnr/tmp/rtl_ab/, 2026-10-15). An attr-free cst copy
  was used so the cst path cannot be the cause; fs_A sha == the previous
  production hash (3918ac9c…), re-anchoring the chain.
- The board-level facts (JP coords, socket lattice, placement) are
  machine-checked every regen (GK1..GK7, N1..N10, S1..S7).

**Assumptions (asserted, not derived -- do not quote as evidence):**
- A1: worst-case chassis run per hop ≤ ~0.25 m. No derivation, no
  impedance/return-path/load-capacitance model, no SI simulation exists.
- A2: spring-contact parasitics + backplane trace geometry
  uncharacterized until the chassis carrier exists.
- A3: the Gowin `DRIVE` value-to-edge-rate mapping per UG289/datasheet IO
  tables (the RTL attr flips documented config bits; WHAT they do to the
  edge is vendor documentation + bench).
- A4: any vendor-flow behavior. No Gowin-EDA run has ever been executed
  here; the cst keeps the SUG935-1.3E-documented spelling
  `SLEW_RATE=SLOW` + `DRIVE=2` as a *costless, unverified* hint only.

## Options compared -- all preserve the certified 19 pad coordinates

| | A: direct (old baseline) | B: RTL DRIVE attribute | C: in-tile series-R positions **(IMPLEMENTED r6)** | D: backplane per-leg R positions | E: rev-B 21-contact per-leg |
|---|---|---|---|---|---|
| mechanism | none | silicon edge-rate control | series damping at the driver node, upstream of the chassis fork | per-branch damping right after the fork | true per-leg source termination |
| frame impact | none | none | none (19 coords untouched) | none for the tile | new connector set → recertification |
| delta | — | 6 lines in fpga/rtl (other workstream's file) | +5× 0402 (nets 40→45, parts 60→65) | backplane BOM only | full respin |
| star handling (L_latch/B_data) | n/a | partial (edge rate only) | partial (damps returns at the common node) | good (per leg) | full |
| owner / status | superseded by C@0R | recommended, free (fpga workstream) | this worker, r6 | recommendation to connector-next | withdrawn unless B2 fails and B+C insufficient |

## Implemented mitigation (board r6, this workstream)

- **R7..R11 (0402, 0R populated by default)** in-line on T_clk/L_clk/
  L_latch/B_data/B_W: U1 pin nets renamed `<net>_DRV` (U1.35/19/31/30/27
  → Rn.1), the JP pads keep the interface net (Rn.2 → JP_<net>). 0R
  reproduces today's circuit exactly; the positions exist so a measured
  value (33–100 Ω class) can be dropped in without a board respin.
  Guarded by N10 (pcb), S6 (schematic), S5 alias, S3 census (45), plus
  the usual GK/ERC/DRC battery.
- Routing feasibility note (honest): no tracks exist yet (placement
  prototype). The series parts sit in the QFN escape corridor near the
  output pins; the corridor carries exactly the same number of nets as
  before (each trace is interrupted by the part, not added to). Real
  escape is FPGA-02 scope; placement-level feasibility is proven by the
  generator's free-space lattice (GK4/GK5 re-passed).
- BOM impact: +5 × 0R 0402, commodity, ≪ US$0.02 (docs/bom.md).

## Evidence-backed recommendation to the fpga workstream

The first-line, free edge-rate knob lives in THEIR tree (not mine to
edit -- recommendation only):

```vhdl
  attribute DRIVE : string;
  attribute DRIVE of t_clk_pin  : signal is "2";   -- softest documented
  attribute DRIVE of l_clk_pin  : signal is "2";   -- setting (A3)
  attribute DRIVE of latcho_pin : signal is "2";
  attribute DRIVE of dout_pin   : signal is "2";
  attribute DRIVE of b_w_pin    : signal is "2";
```

Path proven by tools/drive_attr_ab.sh (ghdl → synth_gowin → nextpnr →
gowin_pack). A SLEW attribute via the same path is untested (could be
probed with one more A/B; the cst hint remains as the SUG935-spelled
vendor fallback).

## Bench items (unchanged pre-scaling gates)

- **B1**: TLV75512PDBVR soft-start ramp inside the Gowin VCC rise window
  (docs/power_reg.md).
- **B2 (extended per review P7)**: scope **T_clk, L_latch and B_data**
  (one point-to-point clock, the strobe-class 2-branch net, one
  2-branch level net) at the FAR chassis contact of the longest run,
  20 MHz, production bitstream. Acceptance: no non-monotonicity through
  the input threshold window during the sample aperture; overshoot
  < 0.6 V over rail AND undershoot > −0.4 V (unterminated reflections
  ring both ways; the overshoot bound ≈ LVCMOS33 abs-max VCCIO+0.5 --
  it is a *screen*, not a margin target). Failure ladder: (1) RTL DRIVE
  attrs (option B, free), (2) populate tuned R7..R11 values (option C),
  (3) only then consider D/E.
- **B3**: flash-free AUTO BOOT blink test (config path end-to-end).

## What this doc deliberately does NOT claim

- That the interface is proven safe. It is bench-gated (B2).
- That the vendor flow honors anything. No vendor run exists (A4).
- That interior STA bounds chassis behavior. Category error (item 3).
- That sampling terminates a line. It does not (item 2).
