# Discrete-glue IC count: survey of consolidation options (corrected)

**Correction (2026-10-12):** an earlier draft of this file claimed a
"7-IC floor" from a 17-function inventory plus a limited catalog survey of
small-gate ICs.  That argument does NOT prove a minimum: function counts do
not lower-bound package counts (a package can implement different function
shapes), and a partial catalog pass cannot exclude every multi-function
part.  The claims below are re-scoped accordingly.

## What is actually defensible

* Baseline partition (call it the *rev-A-derived glue partition*):
  **7 glue ICs** — SN74LVC2G126, SN74LVC2G125, SN74LVC2G08, SN74LVC2G32,
  SN74LVC2G74, SN74LVC1G04, SN74LV161A — plus the two SN74LVC165A shift
  registers the protocol fixes: **9 ICs total** (variant A).
* This partition has every 2-gate package fully used and is
  *simulation-proven* (33-config protocol suite, results/sim_suite.txt).
* No lower bound on the number of discrete SSI ICs for this function set
  is claimed or provable from the evidence collected here.

## Surveyed alternatives (all show what they show; nothing extrapolated)

* **C1 — 2x SN74LVC2G241 instead of 2G125+2G126 (variant A2):**
  same SM8 pinout, one active-lo + one active-hi OE per package,
  *count-neutral* (2 packages -> 2 packages).  Emulation proof: variant A2
  passes the full 33-config protocol suite.  Recorded as a documented
  swap, not a consolidation.
* **C2 — 2G32+1G04 -> 1x 2G02:** covers latch-merge + inversion, but the
  flag sticky-OR then needs a new home (one more SSI package): net zero.
* **C3 — fold the flag OR into the 2G74's free /Q or /PRE:** no truthful
  wiring; would also break the documented "sets exactly at the 16th
  clock" timing.
* **C4 — configurable gates (SN74LVC1G57/58/97/98/99):** one function per
  package; neutral.
* **C5 — counter repartition (e.g. dual ripple counter):** moves the
  terminal decode outside / adds glitch risk; not pursued.

## Genuine consolidation that exists

The SPLD route (variant B2) collapses the 7 glue ICs to
ATF22LV10C + 1G04 (with 2x 165 per protocol) = **4 ICs**, proven at the
fuse level (20/20 equation MATCH from the decoded 5892-fuse map) and at
protocol level (full suite).  It is blocked on the tile's geometry, not on
function (see results/rotation_study.md).

Any further *discrete* minimum claim would need a complete search over the
orderable SSI catalog with a proof the function partition can't merge
gates differently - out of scope; nothing smaller is asserted here.
