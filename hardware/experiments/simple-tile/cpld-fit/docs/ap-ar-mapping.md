<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->

# AP/AR orthogonal mapping: the 74x165-transparent load on ATF1502ASV

## What must be built

The rev-A scan protocol (docs/architecture/protocol.md step 1–2) works like
this: a latch pulse loads all 16 tile bits in parallel; the controller then
samples `B_data` **before** producing the first shift clock. Physically the
two 74LVC165A do this with an **asynchronous, level-sensitive /PL**: while
/PL is low, every stage follows its parallel input; the last-loaded value is
held when /PL rises; no clock is involved in the load.

The one-chip candidate must reproduce exactly that behaviour using ATF1502ASV
macrocells. The reference (`logic/cpld/tile_full.vhdl`, read-only) and the
Verilog candidate here (`src/tile_cpld.v`) both model level transparency;
the self-checking TB pins it down by wiggling keys inside the latch window
and requiring the chain output to track, plus the explicit "first bit valid
before the first clock" assertion per scan.

## Device mechanism used (sourcing)

DS20006485A, "Flip-Flop" section (© 2020 Microchip, text p.3):

* "The flip-flop's Asynchronous Reset (AR) can be either the Global Clear
  (GCLEAR), a **product term**, or always off. AR can also be a logic OR of
  GCLEAR with a product term. The Asynchronous Preset (AP) can be a
  **product term** or always off."
* Clock: global GCK[0:2] or a product term; with a global clock, "one of the
  macrocell product terms can be selected as a clock enable".
* The FF data input comes from the OR/XOR sum term, a separate product term,
  or directly from the I/O pin ("fast registered input").

So each macrocell's **AP and AR are orthogonal product terms, independent of
the data path**. That is precisely what a 165-style transparent load needs:
the load acts through the *set/clear controls*, not through the D input, so
no load/shift mux steals product terms from the shift path.

Naming caution: the specific product-term numbers (AR on "PT3", AP on "PT5")
come from the **prjbureau** ATF150x fuse-map fuzzing documentation, a
secondary source; this session had **no network access** and did not
re-verify it. The DS text above (orthogonal AP/PT and AR/PT) is the primary
source for everything load-bearing here. The fuse-level question (does the
real fitter allocate AR and AP on the *same* macrocell simultaneously without
conflict, and with which exact fuse bits) stays on the fitter-verification
list.

## The mapping (per chain stage i = 0..15)

```
  AP[i]  =  latch &  pd[i]      (PT: 2 literals -- preset when pd_i=1)
  AR[i]  =  latch & ~pd[i]      (PT: 2 literals -- clear  when pd_i=0)
  D[i]   =  shreg[i-1]  (i>0)   (sum term: shift path, feedback from the
           dsin         (i=0)    previous stage's buried feedback)
  CE[i]  = ~latch               (PT: shift only outside the load window;
                                 belt-and-braces with AP/AR dominance)
```

While `latch` is high, stage i is forced to pd[i] as a *level* function (AP_i
or AR_i active — the other inactive; one product term per direction, which is
why the RTL writes the two control terms in one ordered comb process). When
`latch` falls, the register simply holds the value — the 165 behaviour at
/PL rising. A rising clock during the latch window is a no-op for the chain
(`!latch` gate), matching tile_full.vhdl's `if latch ... elsif rising_edge`
priority and the real 165 (clock ignored while /PL active).

## Why not the alternatives

* **DS flow-through "latch mode"** ("data passes through when the clock is
  high and is latched when the clock is low"): the transparency would be
  gated by *bclk*, not by `latch` — the wrong control signal for the 165
  /PL semantic, and it reregisters the D path. Rejected.
* **GCLEAR for `latch`**: can only clear — cannot preset the '1' bits of the
  parallel word. (Marker bits pd[3:2]='1' and any pressed key need AP.)
  Rejected; GCLR left unconnected (pin 39 unused).
* **Synchronous load through the D mux**: breaks the protocol
  (first bit would need a clock). Rejected; this mistake is exactly the
  `sim/mutants/tile_cpld_syncload.v` control, and the TB catches it.

## Product-term budget per macrocell (DS: 5 PT per macrocell, expandable to
40 via the PTMUX/foldback/cascade — "PRODUCT TERMS AND SELECT MUX")

| usage | PTs |
|---|---|
| chain stage: D(shift-in) 1 + AP 1 + AR 1 + CE 1 | 4 of 5 |
| counter bit: next-state (toggle chain, ≤ a few PTs per bit; 4-bit ripple of T = q^carry) 1–2 + AR(latch) 1 | ≤3 of 5 |
| B_W flag: D='1' 0 (tie), CE = dout·(cnt==15) 1 (6 literals) + AR 1 | 2 of 5 |
| tclk/lclk: data = bclk (fed via pin/clock net), OE = w resp. /w | 1 PT-OE each |

All within the 5-PT floor — comfortable, but **not a fit**: actual PT
assignment, switch-matrix routing of the 5 global signals and 16-deep
feedback chain, and fuse generation are the proprietary fitter's job
(fit/run_fitter.sh, currently BLOCKED). Prior yosys-proxy work reached the
same "21 FF bits, structure-only" conclusion; the techmapped netlist here
(16× FF_D_SR_CE + 4× FF_D_AR + 1× FF_D_AR_CE + 2× OBUF_TRI) is the same
structure expressed in ATF1502 primitives, nothing more.

## What would prove it on silicon

1. fitter report showing AP **and** PT-AR product terms both allocated on the
   same macrocell for a chain stage (the orthogonality statement, checked on
   real tool output — not available);
2. POF2JED .jed with `-power_reset` per DS power-up-reset note;
3. time-zero behaviour of the programmed part (transparent-load scope check
   vs the TB vectors in `src/tile_cpld_tb.v`).
