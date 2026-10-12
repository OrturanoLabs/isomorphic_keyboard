# Simple-tile logic experiments: discrete vs 22LV10 glue vs ATF1502ASV

Scope answered here: for the 16-tile, 20 MHz shift-clock, drop-in chassis with no
tile-side MCU/LED/Hall and a strong open-flow preference, compare

- **A – optimized discrete:** rev-A glue set rebuilt in LVC (+ SN74LV161A counter,
  see below), two 74LVC165A.
- **B – ATF22LV10C glue + two 74LVC165A:** the committed `hardware/gal/tile_glue.pld`
  (variant **B1**) and a corrected true-tri-state variant (variant **B2**).
- **C – ATF1502ASV full tile** (glue + both shift registers inside the CPLD).

All work is zero-install, in existing containers (`tools/oss.sh`, `podman run localhost/galette`)
plus host `python3`/`wget`/`pdftotext`.

## 1. Functional equivalence (GHDL, self-checking, not timing)

`equivalence/` (run: `tools/oss.sh make -C hardware/experiments/simple-tile/logic/equivalence clean all`):
a reference rev-A glue model (`ref_glue.vhdl`, true-Z T_clk), a 1:1 transliteration of the
committed PLD (`gal_glue.vhdl`), the corrected variant (`gal_glue_v2.vhdl`), and the full-tile
CPLD RTL (`cpld/tile_full.vhdl`), each wrapped with two `T74HCT165` models, are driven
identically and compared against each other AND against an expected-behavior model that
encodes: frame bit order, **first bit valid before the first clock** (asynchronous
transparent /PL), the 16-bit counter boundary, the sticky B_W flag, latch-source merge,
DS mux selection, and the T_clk/L_clk OE selections.

Result, final clean run:

```
frames=344 samples=261716 documented TCLK Z-vs-0 deltas (gal v1 only, W=1) =3630 mismatches=0
GLUE EQUIVALENCE: PASS
```

- B2 and C match the rev-A reference **exactly**, T_clk included.
- B1 differs only in the committed-design way: T_clk driven low when unselected.
  The delta is **not glossed**: the checker allows exactly the pattern
  (ref='Z', gal='0', W=1) and counts it — 3,630 occurrences exercised in the run;
  zero unexplained mismatches.
- **Method gap, stated plainly:** the simulated GAL models are transliterations of the
  *source equations* (.pld), not simulations of the assembled JEDEC fuse maps. The golden
  .jed was byte-reproduced by galette, which ties source↔product for the *assembler*, but
  no JEDEC-to-simulation check was run. Single-tile equivalence also says nothing about
  inter-tile topology behavior — B1 (and B2) still need multi-tile/board-level validation
  before either is "valid".

## 2. W-transition hazard probe — characterization, NOT a safety proof

`hazard_tb.vhdl` counts rising edges the neighbor's clock *net* would see
(undriven nets held by the pull-up) when W moves while BCLK is low and while BCLK is high:

```
T_clk net rising edges:  ref=2  gal_v1=3  gal_v2=2
L_clk net rising edges:  ref=3  gal_v1=3  gal_v2=3   (identical in all designs)
```

These counts are **observed edge behavior in a zero-delay model**; they characterize the
designs, they do **not** prove safety:

- Tri-stated forwarding (rev A, B2, C) produces a **release edge** when a low-driven clock
  net is let go and floats up through the pull-up. That edge occurs in rev-A hardware
  today. Whether it is harmless depends on ordering assumptions this experiment did not
  prove: W = T_W·B_first is driven by the B_W flag of the tile above, which **sets
  synchronously at a board-clock rising edge**; "W settles while the clock is low" is
  true only if the controller holds BCLK low long enough after the 16th bit — an ordering
  the current FSM provides but a not-yet-written 20 MHz/16-tile controller must be
  *re-proven* for. Hot-plug transitions are fully asynchronous to the clock regardless.
- B1 (driven-low T_clk) has no release edge but adds a different class: W 1→0 while
  BCLK=1 emits a driven 0→1 rise into the column above.
- The protocol's two marker bits catch *some* framing corruption; nothing here shows they
  catch *all* of it. Do not read the probe as "hazards are handled".

## 3. PLD fit with the open flow (galette)

`pld/` (run: `podman run --rm --userns=keep-id -v $PWD:/work:Z -w /work localhost/galette <file.pld>`):

| file | result |
|---|---|
| `tile_glue_golden.pld` (= committed source) | assembles; `jed` **byte-identical** to committed `hardware/gal/tile_glue.jed` |
| `tile_glue_truez.pld` (B2) | assembles; fuse listing shows TCLK OE row = one feedback literal (HX), data row = BCLK — true tri-state |
| `tile_glue_truez_npl.pld` (probe: true-Z **and** keep NPL) | **fails**: "this pin can't be used as output" — pin 13 is input-only; the 22V10 has exactly 10 output macrocells |

The probe proves the padding: there is no 11-macrocell escape. B2 buys true tri-state by
dropping the NPL macrocell and using an external 74LVC1G04 for the '165 /PL (tile becomes
GAL + 2×165 + 1G04 = **4 ICs**). B1 stays **3 ICs** with the driven-low T_clk delta above.
Ranking on *this* evidence: **B2 > B1** for robustness (exact source-level equivalence,
rev-A-identical hazard characterization). Neither B1 nor B2 can be called valid or
recommended without the pending multi-tile/topology validation and the LV10C programming
check below.

## 4. CPLD candidate C status — behavior yes, silicon mapping blocked

`cpld/tile_full.vhdl` preserves the /PL asynchronous *transparent* load (the chain output
shows the first bit before any clock; single-storage-array model, no sync-load cheat).
It passes the full equivalence suite (§1).

- yosys proxy (container, generic target): `$aldff` ×16 (async-load chain) + `$adff`
  ×4 + `$adffe` = 21 FF bits, 2 `$tribuf`. **Synthesis-structure proxy only — not an
  ATF1502 fit** (no fit claim from register counts).
- Architecture check (DS20006485A + prjbureau fuzzed fusemap, `options/logic.html`):
  per-macrocell AR comes from PT3 (or GCLR) and AS from PT5 — **orthogonal product
  terms**, so the transparent-load mapping
  (`AR_i = latch·/pd_i`, `AP_i = latch·pd_i`) is architecturally consistent with the
  device. The caught risk remains: this composition is unverified in a real fitter, and
  the ATF1500 flow is closed (microchip ProChip Designer; palette of open tools ends at
  prjbureau fuse utilities) → **hardware realization is explicitly BLOCKED/unverified.**
- 22V10 vs LV10C is real: doc0780's LV section DC-tests at 3.6 V / CL=35 pF output loads;
  plain ATF22V10C is 5 V-only and disqualified on the 3.3 V rail. ATF1502AS ≠ ASV likewise
  (AS = 5 V).

## 5. Timing at 20 MHz — component-level constraints, NO system sign-off

`timing/timing.json` holds every datasheet value with doc + table + conditions, and an
`assumptions` block of system/interconnect parameters that all start `null` (never
invented). `timing/calc_timing.py` (host `python3`, stdlib; `--set
assumptions.route_delays_ns.<key>.value=<ns>` overrides, `--selftest` synthetic cases)
emits three kinds of verdicts in `timing/results/budget.txt`:

- **NECESSARY-ONLY** — datasheet component sums. The design cannot beat these, but they
  prove nothing about the 16-tile system by themselves.
- **UNKNOWN** — needs a measured interconnect/controller parameter (currently all system
  rows: hop setup/hold incl. routing, controller return incl. FPGA tCO launch + cable
  out/in + sampling route, latch pulse width for the unimplemented 20 MHz/16-tile
  controller, latch deassert→first-clock recovery at the last tile incl. the 16-tile
  latch forward chain and skew, first-bit path incl. latch-path/capacitive recovery).
- **PROVISIONAL** — CPLD composed estimates (tIN+tFSU is *not* a fitted DS mux), pending
  closed-fitter STA.

Component bounds computed (50 ns period; CL=50 pF LVC, CL=35 pF doc0780/ATF1502):

| bound | A discrete | B LV10C-15 | B LV10C-10 | C CPLD |
|---|---|---|---|---|
| hop setup, component | 29.1 ns used | 48.5 ns used | 38.5 ns used | 28.0/31.0 ns (provisional) |
| hop hold, min-corner | +3.3 ns | +6.5 ns | +6.5 ns | pending STA |
| flag RCO→AND→OR→FF t_su (incl. the OR) | 28.0 ns | in-array tS path 26.5 ns | 22.0 ns | provisional |
| counter fmax | 50 MHz (LV161A) | 50/80 MHz int-feedback | ← | 76.9 MHz |
| return setup bound incl. FPGA tCO 10 + tSU −0.5 | 24.0 ns used | same (165 CQ) | ← | 17.5–20.5 ns |
| HC161 counter @3.3 V (rev A as built) | **UNKNOWN** (2/4.5/6 V-only datasheet) | — | — | — |
| return hold at FPGA | **UNKNOWN** (FPGA tCO min unpublished + unmeasured cables) | | | |

The earlier "aggregate clock skew is absorbed by sample-before-clock" claim is **removed**:
per-hop registered slack was shown, system phase/clock-chain behavior was not — it is an
open check. `calc_timing.py --selftest` verifies: default-null → UNKNOWN; zero fills →
system == component bound; +1.0 ns fills → bound + 2.0 exactly; 100 ns fills → FAIL;
negative hold → FAIL (helper corrected: negative hold is FAIL, not UNKNOWN).

## 6. Licensing / programmer gaps (costs NOT quoted — unsourced)

- **A/B:** galette (open) assembles. Afterburner (open hardware) lists ATF22V10B/C/CQZ,
  **not ATF22LV10C** → the 3.3 V part's programmability is unverified; until one real chip
  programs and reads back, the "open flow" for B is **not established**. (A 5 V ATF22V10C
  is not usable on this 3.3 V rail.)
- **C:** .jed→.xsvf and JTAG programming have open tooling (prjbureau; Afterburner ≥0.6.0,
  experimental; ASV needs a 3.3 V-IOREF Arduino), but producing the .jed needs Microchip's
  closed ProChip fitter → decisive flow gap vs the strong-open preference.
- Discrete 74-logic needs no programmer at all.

## Conditional candidate summary

**B2** (`pld/tile_glue_truez.pld` + external 74LVC1G04, ATF22LV10C-**10** speed grade) is
the leading *candidate*: exact source-level equivalence with rev A (counter, sticky flag,
reset, DS, OE selections; driven-low-vs-Z delta eliminated), hazard characterization
identical to rev A, 9 ICs → 4. All conditions remain open before it can be recommended:

1. program one real ATF22LV10C with the open Afterburner (not listed) or fall back to A;
2. fill the null system assumptions (interconnect flight/skew, cable out/in, FPGA sample
   route, controller latch pulse and deassert→first-clock gap at the last of 16 tiles)
   and re-run `calc_timing.py` to real PASS/FAIL;
3. multi-tile topology/board-level validation (single-tile equivalence is shown; inter-tile
   is not);
4. keep the FPGA-side return-hold check (FPGA tCO min unpublished) on the critical list.

A (all-LVC + LV161A) is the programmer-free fallback; regardless of candidate, note the
rev-A finding: the HC161 counter has no 3.3 V characterization — use LV161A. Do **not**
take C forward on this evidence: function proven in simulation only, fitter flow closed,
AP/AR transparent-load mapping unverified on silicon. Nothing here is manufacturing-ready;
no 20 MHz sign-off is claimed anywhere in this folder; no parts have been costed or ordered.
