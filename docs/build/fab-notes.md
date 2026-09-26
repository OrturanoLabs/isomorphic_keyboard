# Fabrication notes — isomorphic tile, rev B

| Item | Value |
|---|---|
| Layers | 4 (F.Cu signal / In1.Cu GND planes / In2.Cu VCC planes / B.Cu signal) |
| Thickness | 1.6 mm, FR-4, Tg ≥ 150 °C |
| Stack-up | 35 µm Cu / 0.21 mm prepreg / 15 µm Cu / 1.065 mm core / 15 µm Cu / 0.21 mm prepreg / 35 µm Cu |
| Impedance | not controlled by the fab; 0.3 mm outer tracks are ~55 Ω by design, ±15 % is fine |
| Min track / space | 0.15 mm / 0.2 mm |
| Min drill / via | 0.3 mm drill, 0.6 mm pad |
| Finish | ENIG |
| Solder mask / silkscreen | both sides / both sides |
| Outline | two boards (key board + logic board) joined by two tabs with 0.5 mm NPTH mouse bites; do not rout the tabs |
| Assembly | key board: SMD on **bottom** only (Kailh hot-swap sockets, 0603); logic board: SMD on **top** only; THT connectors hand/selective soldered after reflow |
| Fiducials | 1 mm copper, 2 mm mask opening: FID1–3 (key board, bottom), FID4–6 (logic board, top) |

## Assembly notes

- `assembly/pick_and_place.csv` contains SMD parts only; board coordinates in mm, viewed
  from the top, KiCad rotation convention.
- **SW101–SW112 are the Kailh CPG151101S11 hot-swap sockets, soldered on the bottom
  side.** Their footprint lives on the top layer (the switch is inserted from the top),
  so the position file rewrites them as `bottom`. Please verify their orientation against
  `assembly/assembly_bottom.pdf` during DFM.
- Not assembled by machine (hand/selective solder after reflow): J101–J104 (right-angle
  edge connectors), J105/J106 (vertical sockets, logic board top), J107/J108 (vertical
  headers, key board bottom). The MX switches are inserted by the user.
- Parts without an MPN yet: C105 (100 µF ≥ 10 V SMD aluminium, 6.3 × 7.7 mm) and
  J105–J108 (2.54 mm 1×8 vertical socket/header; the mated height sets the gap between the
  boards).
