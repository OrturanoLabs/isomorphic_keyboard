# Checkpoint: Gowin vendor documents on PCB layer count, grounding, decoupling and stackup (GW1NZ-LV1QN48)

Date: 2026-10-16. Scope: read-only vendor-document research for FPGA-02 layer-count
decision. No design edits, no gate changes, no tool runs. Owner of this file only;
does not modify `fpga-01.md` or any board artifact.

Question asked upstream: is the tile still required to be 2-layer, should it move to
4-layer, and what exactly does the FPGA vendor recommend? Answer below with sourced
quotes; headline: **no Gowin document mandates or recommends any specific PCB layer
count for GW1NZ**, family-general or device-specific. The layer-count decision is
board-design engineering judgment informed by the vendor's grounding/decoupling/EPAD
recommendations and by our 20 MHz return-path requirements, not something that can be
offloaded to Gowin.

## 1. Document provenance (all re-fetched 2026-10-16 to /tmp/opencode/gowindocs/)

| Doc | Title / rev | Source URL | sha256 of fetched bytes | Status vs repo pins |
|---|---|---|---|---|
| DS841E.pdf (69 PDF pages) | GW1NZ series Datasheet, DS841-2.8E, 04/03/2026 | https://cdn.gowinsemi.com.cn/DS841E.pdf | a19cdd7a2aa17b798c92b5cfd2be936b82ca53a10a0ba2e86fa6ac8c48c7dbc4 | **exact match** to pinned hash in `board/data/pins_gw1nz_qn48.json` |
| UG842E.pdf (7 p.) | GW1NZ-1 Pinout, UG842-1.6.8E | https://cdn.gowinsemi.com.cn/UG842E.pdf | b7f0dd8ebd51a88d4f5b895ec80ee34d908db541d79adae45cc6ce54517e099d | **exact match** to pinned hash |
| UG293E.pdf (17 PDF pages, printed 1..16) | GW1NZ series Schematic Manual, UG293-1.3.4E | https://cdn.gowinsemi.com.cn/UG293E.pdf | 6b6035b17eeaac35ae48bf5bedeff1f52ce4ea0000d2a4c9bb817d42c25d4c2b | not previously hash-pinned; recorded here |
| UG846E.pdf (13 PDF pages) | GW1NZ series (Automotive) Package & Pinout, UG846-1.1E, 09/28/2023 | https://cdn.gowinsemi.com.cn/UG846E.pdf | 1fab1bc3cc461bc9a021a27bc6fa555ce8ff269a978b99c9b4d30314af9dd8c5 | not previously hash-pinned; recorded here |

Fetch note: cdn.gowinsemi.com.cn rejects curl with `x-error-detail: ua-black` (HTTP
403); a browser User-Agent header is required. Same behaviour on DS841E/UG846E, so it
is UA filtering, not a per-file outage.

Page citations use the **printed page numbers** in the document footers (e.g. UG293
"4(16)"). PDF-image offset for DS841 is +12 (printed p.35 = PDF page 47).

Gowin documentation database (https://www.gowinsemi.com/en/support/database/1871),
snapshot 2026-10-16, lists for GW1NZ only the categories "White Papers", "Data Sheet",
"Pinout and Package", "User Guide" — no application-note tier with layout, PDN,
impedance or stackup guidance. **No Gowin board-layout/stackup/PDN appnote for GW1NZ
was found.** The board-level vendor content for GW1NZ is therefore exactly: DS841
(DC/AC only), UG293 (schematic manual), UG842 (pinout + operating conditions + EPAD
note), UG846 (package drawings incl. land pattern, automotive-titled).

## 2. What Gowin mandatorily requires — datasheet constraints (DS841-2.8E)

These constrain the electrical design, none of them constrain layer count:

- Operating conditions, Table 3-2, printed p.35: VCC (LV) 1.07–1.26 V; VCCIO
  1.14–3.6 V; VCCX 1.71–3.6 V; junction temp commercial 0..+85 °C.
  Exact note: "[3] The allowable ripples on VCC, VCCIO, and VCCX are 3%, 5%, and 5%
  respectively."
- Ramp rates, Table 3-3, printed p.35: VCC 0.6–6 mV/µs; VCCX 0.6–10 mV/µs; VCCIO
  0.1–10 mV/µs; "A monotonic ramp is required for all power supplies."
- POR trip points, Table 3-5, printed p.36 (GW1NZ-1): VPOR_UP VCC 0.8 V, VCCX 1.5 V,
  VCCIO 0.9 V.
- Package info, Table 1-2, printed p.2 (PDF p.14): QN48 0.4 mm pitch, 6x6 mm,
  GW1NZ-1 max 41 user I/O. QN48 identified as QFN48, 0.4 mm in §5 terminology.
- **Zero occurrences in DS841 of layer count, stackup, decoupling capacitors, PCB
  layout, ground planes, thermal pads or via guidance** (text searched: layer,
  stack, decoupling, capacitor, PCB, board, ground plane, thermal, EPAD; only
  MIPI-link-layer and standard-IO-use matches).

## 3. What UG293-1.3.4E (the GW1NZ schematic manual, device-family-specific) says

UG293 is the hardware board-design guide for the exact GW1NZ series (not a generic
all-Gowin document; its References list points to DS841/UG842/UG845/UG847). Complete
coverage of its board-level content:

1. Decoupling — printed p.4(16), section "Power Filter":
   > "Each FPGA power input pin is connected to the ground with a 0.1uF ceramic
   > capacitor. The input end of the VCC core voltage should conduct the noise
   > processing." … "FB is a ferrite bead, and the reference model is MH2029-221Y.
   > The ceramic capacitance is 4.7uF, and It offers an accuracy of ±20%."
   (Figure "Noise Processing": VCC source → FB → VCC pin, 4.7uF to ground.)
2. Power sequencing/integrity — printed p.2(16): "VCCX should power on no later than
   VCC. VCCX must be greater than or equal to VCCIO, otherwise VCCIO will leak
   current." Note warns of hundreds-of-mA VCCIO current if VCCX < VCCIO during ramp.
   Printed p.3(16): flash-init condition "VCC≥1.08V & VCCX≥1.62V" at start of config
   access; VCC power-on time recommended 0.2–2 ms.
3. Strap/pull values — TCK: "TCK needs to connect a 4.7K pull-down resistor on the
   PCB." printed p.5(16). READY/RECONFIG_N/DONE: 4.7K pull-ups to VCCIO0, printed
   p.9(16). MODE: "It is recommended to use a 4.7K resistor for pull-up or a 1K
   resistor for pull-down." printed p.10(16). MSPI MCLK: 1K pull-down, printed
   p.7(16) (MSPI only; not needed in AUTO BOOT).
4. Signal integrity — exactly one PCB-geometry statement, printed p.8(16), in the
   LVDS/differential section: "The different line impedance of PCB is controlled at
   about 100 ohms." Nothing about reference planes, return paths, vias, layer
   transitions, crosstalk or single-ended trace geometry.
5. Configuration modes per package — Table 9, printed p.14(16): GW1NZ-1 QN48
   supports JTAG, AUTO BOOT, SSPI, MSPI (not SERIAL). MODE[2:0]=000 = AUTO BOOT,
   Table 6, printed p.10(16).
6. Clock input guidance, printed p.8(16): prefer GCLK_T for global clock entry,
   PLL_T for PLL input. Relevant to the tile's clock-entry pin choice only; no
   board-geometry consequence.

**UG293 says nothing anywhere about PCB layer count, layer assignment, plane usage,
EPAD soldering or vias.** Its name is accurate: it is a schematic (netlist-level)
manual. There is no thermal or gradient guidance either. It is neither a mandate
nor a recommendation to use a 4-layer stackup for GW1NZ.

## 4. EPAD and package/land documents

- UG842-1.6.8E printed p.5(7), Power sheet (the sheet covering the FN32/FN32F/QN48
  packages), exact note: "It is highly recommended that the EPAD connect to GND,
  but not a requirement."
  => EPAD-to-GND is the only grounding recommendation touching pads; it is a
  recommendation, explicitly not mandatory. Nothing about EPAD via arrays or
  thermal relief geometry.
- UG846-1.1E (Automotive) printed p.7(7), Figure 4-2 "Recommended PCB Layout QN48":
  land pattern GW1NZ_QN48_6R00_6R00_0R40: D=E=6.00, D2=E2=2.70, P=5.90, e=0.40,
  L=0.85, b=0.20 (mm). Uncertainty: this figure lives in the **automotive** package
  document; the package itself is the same commercial QN48 outline (D/E/D2/E2
  identical), and no commercial-document equivalent land figure was located in this
  run. Use it as the land-pattern source with the provenance caveat; DO NOT use
  UG846 for the pin map (next section).

## 5. Automotive pinout hazard — verified from both documents

- UG846-1.1E, Table 3-1 "Other pins in GW1NZ-1 QN48", printed p.5(7): **VCC = pins
  "9,12,37"**; VSS = 2,26; VCCIO0 = 1; VCCIO1 = 25; VCCX = 36. Automotive QN48
  therefore has 40 user I/Os (Table 2-1, printed p.2(7)), not 41.
- UG842-1.6.8E commercial Pin List, printed p.6–7(7): QN48 column gives pin 9 =
  **IOR2A** (user I/O), VCC = 12 and 37 only; power pins = {1 VCCIO0, 2 VSS,
  12 VCC, 25 VCCIO1, 26 VSS, 36 VCCX, 37 VCC}. UG842 version history 1.5.1E:
  "The location of pin 9 in QN48 package modified."
- Consequence: the automotive doc does NOT apply to the commercial
  GW1NZ-LV1QN48C6/I5 (Tang Nano 1K and our tile both use the commercial order
  number). Existing repo decision stands and is hereby vendor-confirmed from the
  primary documents: **keep pin 9 excluded from routing (order-code hazard)**
  because the two documents disagree on the physical pin 9 bonding, and a part
  sourced from an automotive-adjacent reel or a vendor "clarification" would fry a
  VCC-pin connected to a driven IO. This is the documented "automotive misleading
  pinout" issue.

## 6. Layer count: what is and is not sourced

- No retrieved Gowin document — DS841, UG293, UG842, UG846 — mentions PCB layer
  count at all. Searched full texts; zero matches for layer/stack/stackup/2-layer/
  4-layer guidance. The Gowin documentation database lists no layout/PDN/SI
  application note for GW1NZ either (§1).
- Therefore: **"Gowin recommends a 4-layer board for GW1NZ" is unsourceable; so is
  "2 layers suffice per Gowin".** Any 2-vs-4 decision must be argued from our own
  return-path analysis (20 MHz shift clock forwarded along a 16-tile chain,
  key-matrix edges, contact-interface crossing) and fab cost, and recorded as such
  in FPGA-02 — not attributed to the vendor.
- Analogous device-family guides are NOT independent: the UG293 power-filter section
  text (FB + 4.7uF, per-pin 0.1uF) is the same guidance pattern Gowin uses for
  GW1N(R) too (family-level note in the manual text). Treat its decoupling numbers
  as GW1NZ-specific because the manual is GW1NZ-titled, but the writing style is
  shared-family boilerplate.

## 7. Tang Nano 1K reference design (GW1NZ-LV1QN48C6/I5, commercial)

- Sipeed wiki page, snapshot 2026-10-16
  (https://wiki.sipeed.com/hardware/en/tang/Tang-Nano-1K/Nano-1k.html) lists only:
  Speech/Specification, Schematic, Bit number map, Dimensional drawing, 3D file,
  Chip Manual. Complete directory listing via
  https://api.dl.sipeed.com/fileList/TANG/Nano%201K returns exactly these 6 folders:
  **no PCB source files, no Gerbers**.
- Schematic PDF downloaded and text-checked
  (Tang_Nano_6100-SCH(1).pdf, 893 KB, 1 page, title "02_Tang_Nano_6100.pdf"):
  contains the full circuit (BL702 debug MCU, buck converter, bank-voltage rails at
  3V3) but **zero statements on layer count or stackup** (grep: layer/stack/
  impedance/层 — no hits).
- Conclusion: **Tang Nano 1K's PCB layer stackup is NOT verifiable from published
  files.** Do not cite it as "2-layer works" or "vendor-style reference". Recorded
  as an unverifiable external board done on this exact commercial part.

## 8. Actionable stackup proposal for FPGA-02 (engineering judgment, NOT vendor-sourced)

Geometry facts to respect: U1 GW1NZ and U2 sit on B.Cu; the 20 MHz shift clock and
data enter and leave the tile as B.Cu-adjacent nets at the FPGA pins, so the fastest
signals on the board reference the B.Cu-adjacent layer. Vendor constraints to honour
anyway: per-pin 0.1uF to GND (UG293 p.4), 3%/5%/5% rail ripple limits (DS841
Table 3-2), EPAD highly recommended to GND (UG842 p.5), land pattern per
UG846 Fig.4-2.

Recommended default for the FPGA-02 4-layer comparison arm:

- L1 (F.Cu): signal — key matrix scan lines, contact-pad interface nets.
- L2 (In1.Cu): **solid GND plane**, continuous under the connectors matrix.
- L3 (In2.Cu): **solid GND plane**, continuous under the FPGA and clock/data routes.
- L4 (B.Cu): signal + power pours: 3V3 (VCCIO0/1 + VCCX) and 1V2 (VCC core) routed
  as wide pours under/next to the FPGA with a stitched moat of GND vias; every
  B.Cu power pour sits on top of L3 GND, and every B.Cu fast net references L3.

Rationale recorded explicitly as ours: with both inner layers GND, every B.Cu fast
net (clock in/out, shift data in/out, column latch) has direct signal-ground
adjacency on its reference layer, and every F.Cu net likewise; single-ended 20 MHz
LVCMOS return current flows on the adjacent plane with short via jumpers at any
layer transition. Power integrity does not suffer materially here because the rail
set is tiny (1.2 V core + single-rail 3.3 V I/O, mA-class loads) and all supply
pins still get the vendor-mandated per-pin 0.1uF to GND plus the 4.7uF+FB filter on
the core input.

Alternatives to record in the FPGA-02 comparison, with statuses:
- Conventional L2=GND / L3=3V3+1V2 split: workable but every B.Cu fast net then
  references a power plane; would need stitching vias at each driver/receiver end
  through the clock path and is inferior on the stated adjacency concern. Only pick
  this if a fab/stack gearing forces a power plane (not anticipated).
- Strict 2-layer F/B: vendor does not forbid it; the earlier discrete-layout study
  already found 2-layer escape for 0.4 mm QFN plausible. Decision driver must be
  measured/argued return continuity across the contact interface, not a vendor
  rule. Keep as the low-cost arm; the GND-one-side/SIG-other-side discipline
  applies and the 0.1uF/EPAD/strap vendor items are unchanged.
- EPAD: implement GND-connected EPAD (per UG842's "highly recommended") with a
  2x2 or 3x3 thermal-via array drilled 0.3 mm inside the 2.7x2.7 mm pad if the fab
  rules allow; flagged as best practice — Gowin gives no thermal-via or package
  thermal data (DS841 has none), so the thermal margin remains an open item for
  FPGA-04 bench measurement.

Layer-selection criterion for FPGA-02 gate: routing feasibility + a continuous GND
reference adjacent to every 20 MHz path + finished fab quote. Do not report any of
this as a Gowin requirement; it is the tile's engineering choice, citation-sourced
here.

## 9. Residual uncertainties / open items

1. No commercial (non-automotive) land-pattern figure located; UG846 Fig 4-2 used
   with package-identical rationale. Could try Gowin "PCB Package Library" CAD
   download later if land-pattern amber needs removal.
2. UG293E and UG846E previously had no pinned sha256 in repo data; hashes recorded
   in §1 for future pinning (only DS841/UG842 hash-match today's pins).
3. UG290 (config guide) not re-fetched — not needed for stackup; its MODE table is
   fully duplicated by UG293 Table 6 which I did quote.
4. No Gowin appnote tier exists for GW1NZ as of 2026-10-16 (database snapshot);
   recheck only if a "Design Advisory"/application note appears later.
5. Thermal: no vendor thermal resistance or EP-via recommendation anywhere in the
   four docs; bench validation per FPGA-04 remains mandatory.

## 10. Commands run (bounded, reproducible)

- `curl -A "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) ..." https://cdn.gowinsemi.com.cn/{DS841,UG842,UG293,UG846}E.pdf` → /tmp/opencode/gowindocs/, sha256-stamped (§1).
- `pdftotext -layout` on all four (poppler, host-installed); full-text grep for
  layer/stackup/decoupling/PCB/thermal/EPAD/via terms.
- `webfetch` Sipeed Tang Nano 1K wiki; `curl` on api.dl.sipeed.com fileList +
  schematic download; text-scan of schematic.
- `curl` Gowin documentation database page; category scan for GW1NZ.
- No synth/route/tool runs, no installs, no commits, no purchases. Working tree
  untouched except this file.
