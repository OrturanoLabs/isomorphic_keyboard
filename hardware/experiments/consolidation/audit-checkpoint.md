# Consolidation audit checkpoint (read-only audit)

Task: audit consolidation of isomorphic_keyboard-revc (linked worktree, branch rev-c @ 6572e0f,
1 ahead of origin/rev-c, dirty) into main worktree isomorphic_keyboard (branch rev-b @ d358953, clean).
Auditor must not modify either repo except this checkpoint. Caller performs migration.

## Baseline provenance (verified 2026-10-12)
- Main: /home/marco/Documents/OrturanoLabs/isomorphic_keyboard, rev-b d358953, `git status` clean.
- Linked: /home/marco/Documents/OrturanoLabs/isomorphic_keyboard-revc, rev-c 6572e0f, ahead 1 of origin/rev-c.
- `git merge-base --is-ancestor rev-b rev-c` = true → fast-forward from rev-b to rev-c is possible.
- rev-b..rev-c = 13 commits (6572e0f single-board tile experiments; 9be96ae/a8090d3/48daf7f Rev C MCU tile;
  9dec784 GAL ATF22V10C; 01cfb66/6561694 MCU tile placement/arch; 55eba9f/81112ec rework WIP;
  2852c07 merge rev-b; 3ccb259 oblique tiling figure; 8444cae TH connectors ruled out; eeadba3 single-board study).

## Dirty state in revc worktree (uncommitted, MUST preserve pre-FF)
- Modified: hardware/experiments/simple-tile/README.md, hardware/experiments/simple-tile/RESULTS.md
- Untracked: hardware/experiments/simple-tile/FOLLOWUP_RESULTS.md
- Untracked dirs: hardware/experiments/simple-tile/{checkpoints,connector-next,cpld-fit,discrete-spld,fpga,timing-chain}/
- Untracked top: checkpoints/ (revc worktree root)

## Audit artifact note
`?? hardware/experiments/` in MAIN worktree = THIS checkpoint dir only (created by auditor, authorized).
Main was otherwise fully clean before audit.

## Ignored inventory — MAIN (rev-b)
- 32 ignored entries. Sizes: WhatsApp jpeg 336K, WhatsApp zip 13M, production/ 68M.
- SI captures (MUST PRESERVE): hardware/si/*.png, hardware/si/measurements/* (fit/probe/scope ppm+pngs, tile_hop_ibis)
- Vendor IBIS models (preserve, referenced by SI model): hardware/si/models/sn74lvc1g04.ibs, sn74lvc2g125.ibs, sn74lvc2g126.ibs
- firmware build outputs: firmware/experiments/{i2c_picoice,scan_low_rate,scan_low_rate_i2c}/*.{asc,bin,json} + wave.vcd/.ghw; firmware/ice40/build/; firmware/ice40/sim/build/
- Regenerable: hardware/kicad/tile/isomorphic_tile.kicad_prl, scripts/__pycache__/, hardware/si/__pycache__/, hardware/simulation/build/

## Ignored inventory — REVC (rev-c)
- 440 ignored: 436 under hardware/experiments/simple-tile: timing-chain 411, fpga 7, regression 4, connectors 4, connector-next 4, discrete-spld 3, logic 2, cpld-fit 1
- Plus: hardware/kicad/revc-mcu-tile/revc_mcu.kicad_prl, hardware/kicad/tile/isomorphic_tile.kicad_prl, scripts/__pycache__/, production/

## revc simple-tile composition (untracked source / ignored generated, counts + bytes)
- fpga: 22 untracked (144K) / 134 ignored (21M). Ignored = sim/build+logs (6.5M, 57 sim logs), synth/results (14M: 31 logs + 27 build incl 6 bitstreams bin/asc)
- timing-chain: 19 untracked (476K) / 420 ignored (7.2M). Ignored = results/*.log 402 scenario logs + build/chain_tb; si/models/*.ibs are md5-identical copies of main's hardware/si/models (fetch.sh re-fetches)
- connector-next: 41 untracked (3.5M incl KiCad coupons + vendor PDFs/STP) / 8 ignored (284K, pycache+coupon prl only)
- cpld-fit: 25 untracked (220K) / 3 ignored (720K, only results/build/*.vvp → regenerable)
- discrete-spld: 41 untracked (1.5M) / 3 ignored (36K, prl+pyc → regenerable)
- total revc transplant: 818 files ≈ 55M (incl production/revc{,18,_mcu},schtest 20M + checkpoints 20K)

## Tree diff rev-b..rev-c
- 103 files, +86241/-5 lines, ZERO file deletions → rev-c is purely additive over rev-b (FF-safe for content).
- Modified(M): docs/LEDGER.md, hardware/kicad/tile/scripts/revb_pcb.py (inner-layer via check), tools/scripts/check_via_in_pad.py (same-net rule)
- Added: simple-tile {logic(29),connectors(23),regression(6),checkpoints(3)}, revc-mcu-tile KiCad (36k-line pcb), revc_* scripts, hardware/gal (galette ATF22V10C: pld/jed/fus/chp/pin), docs/media revc figs, docs/architecture/revc-*, tools/containers/galette
- firmware/ tree identical rev-b vs rev-c (golden firmware preserved by FF)

## Collisions between the two worktrees' ignored sets
- hardware/kicad/tile/isomorphic_tile.kicad_prl: identical md5 348a6293… → no conflict
- hardware/kicad/tile/scripts/__pycache__/: overlap only revb_pcb.cpython-313.pyc (regenerable)
- production/: ZERO path overlap (main=flat files+bench,panel,reference,rev-b; revc=revc,revc18,revc_mcu,schtest only)
- main-unique ignored NOT in revc: WhatsApp jpeg(336K)+zip(13M), hardware/si pngs+ppm+ibs, firmware/* builds, hardware/simulation/build → stay in place, untouched by FF

## Hardcoded -revc path references
- RUNTIME-BREAKING (fix after move): hardware/experiments/simple-tile/discrete-spld/tools/keymap_check.py:22 absolute PATH constant
- Record-only (provenance, keep): cpld-fit/results/logs/env.log, discrete-spld placement_report.txt ×2, battery.log, reva_kicad_export.xml, reva_reference.json source field, timing-chain/results/report.md:15, checkpoints/cpld-fit.md:11
- Tracked tree at rev-c: zero absolute OrturanoLabs paths. Sibling projects Pico-iCE/Hex7/ZeroStuff/Docs: zero references to -revc.

## Runtime dependencies (must survive move)
- fpga/sim/run_sims.sh: ROOT_REL + hardware/simulation/{74hc165,tile}.vhdl (tracked) + ../../regression/tile_reg_pkg.vhdl (tracked rev-c) → portable, depth preserved
- timing-chain/si/run_si.sh: needs si/models/*.ibs (fetch hardware/si/models/fetch.sh; or copy md5-identical main copies)
- timing-chain needs logic/timing/timing.json (tracked rev-c drift guard)
- regression+logic tracked dirs land via FF — no action

## Must-preserve hashes (sha256)
- WhatsApp jpeg 31261672…f7df ; WhatsApp zip 2be240d2…7eba
- SI: clock_link_falling.png f25edccd…, clock_link_rising.png f31d8cae…, scope_2026-06-15.ppm 1a5cae55…
- IBIS: 1g04 03033638…, 2g125 5043fd40…, 2g126 a29fd013…
- new.net = rev-b schematic netlist (src path embedded, 2026-09-27) → fabricated-netlist evidence, keep
- golden JEDEC/equations: logic/pld/results/*golden*/truez* tracked at 6572e0f; discrete-spld jeddec/galcheck goldens untracked (move as source)

## Status: AUDIT COMPLETE — report returned to caller. No migration/deletion executed.
- [x] baseline git state
- [x] ignored inventory both worktrees
- [x] revc untracked/ignored classification
- [x] tree diff rev-b vs rev-c
- [x] collision + dependency scan
- [x] hardcoded path scan
- [x] manifest + commands delivered in final reply
