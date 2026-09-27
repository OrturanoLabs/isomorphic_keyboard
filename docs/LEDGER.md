# Engineering ledger

Chronological log of attempts, tool setups, measurements and lessons learned.
Its purpose is to stop future sessions from repeating the same mistakes.
Newest entries at the bottom. Each entry has: **Goal**, **What was done**, **Result**,
**Lesson** (when there is one).

Conventions (apply to every session):

- Everything in the repository is written in English (docs, comments, commit messages).
- Software is installed only as a user-level flatpak (`flatpak --user`) or as a rootless
  podman container. Container recipes live in `tools/containers/`.
- Function freeze for rev B: switch positions, connector positions, connector pinouts and
  logic ICs must not change. The rev-A prototype behaviour is the regression baseline
  (hot-plug of tiles, any arrangement, automatic above/below/beside detection, MIDI out).

---

## 2026-09-26 — Kick-off: review of the prototype material

**Goal:** understand the state of the double-stack prototype before planning the doc/reorg,
signal-integrity and PCBA work.

**What was done**

- Reviewed the WhatsApp media dropped in the repo root (not committed):
  - `WhatsApp Image 2026-09-26 at 15.04.20.jpeg`: an Analog Discovery 2 capture from
    2026-06-15 (100 MS/s, 8192 samples). Channel 2 (blue) is a board clock and channel 1
    (yellow) a neighbouring line.
  - ZIP with 3 photos and 2 videos. Two of the photos (2026-06-25) show an HP monitor and
    are **unrelated to the project**. The 2026-06-13 photo shows a 3-board stack wired to the
    pico-ice with ~20 cm dupont wires.
  - Videos (2026-06-30): ~8 tiles played live. Tiles are unplugged and replugged while the
    system runs, rearranged, and still located correctly. The audio contains synth output
    (scales and chords) and ~11 s of speech.
- Audio was extracted with ffmpeg and inspected as a spectrogram
  (`ffmpeg -i x.mp4 -ac 1 -ar 16000 x.wav`, then
  `-lavfi showspectrumpic=s=1600x500:scale=log:stop=4000`).
  No speech-to-text tool was installed, so the author summarised the speech: the videos
  demonstrate hot-plug and auto-arrangement, and **this must not regress**.

**Result (scope capture):** ~40 % overshoot, ~1 V undershoot below GND and ~20–30 MHz
ringing after every clock edge. The adjacent channel shows ~0.4 V spikes coupled at every
edge (ground bounce/crosstalk).

**Lesson**

- The AD2 analog bandwidth is only ~30 MHz. A long probe ground lead plus dupont wiring
  adds its own LC ringing. Re-measure with a spring ground tip at the receiver pins before
  drawing conclusions about the PCB alone.
- Media dropped in the root can contain unrelated files; check before committing anything.

## 2026-09-26 — Hardware facts extracted from the KiCad project

- `hardware/kicad/module-tile/tastiera_isomorfa.*` is KiCad 9 format (pcb `20241229`,
  sch `20250114`). A single PCB file contains **two boards**:
  - the key board: 12 Cherry MX switches, R110–R133, stacking headers J107/J108;
  - the logic board: U101–U109, inter-tile connectors J101–J104, stacking sockets
    J105/J106.

  They are separated by 68 custom 0.5 mm NPTH footprints called `Senza-titolo` (mouse bites).
- 2 layers, no stackup defined. GND pour on F.Cu and VCC pour on B.Cu, both cut up by
  FreeRouting-autorouted 0.2 mm tracks. A single netclass. Only 2×100 nF + 2×4.7 µF + 100 µF
  of decoupling for 9 ICs.
- Signal directions: clock and latch enter from the bottom/right connectors (J103/J104) and
  are re-buffered outward (U101 → L_clk, U107 → T_clk, U106 → L_latch). Data returns inward
  (U104 Q7 → B_data, which drives **both** J103 and J104). `B_clk` is a 141 mm multi-drop net.
  No driver has a series termination.
- BOM inconsistency: the symbol values (74AUC2G126/125/08, 74HC165, 74LS161) do not match
  the ordered parts (74LVC2G…, SN74LVC165A, SN74HC161). 74AUC is **not rated for 3.3 V**.
  Check the chip markings on a built tile before trusting either list.

## 2026-09-26 — Tooling setup

- **OSS CAD Suite** as a rootless podman image built from
  `tools/containers/oss-cad-suite/Containerfile` (release 2026-09-26):

  ```
  podman build -t localhost/oss-cad-suite:2026-09-26 tools/containers/oss-cad-suite
  podman run --rm --userns=keep-id -v "$PWD":/work:Z -w /work localhost/oss-cad-suite:2026-09-26 make
  ```

  It works. The build of the unmodified rev-A firmware is **deterministic**:
  `hardware.bin` sha256 `e3a7eaf9facde7d328df700aebb1f1d297bbbdcd1ccf5ca79be39f0315fec8d5`.
  3608/5280 LCs (68 %), Fmax 18 MHz at 12 MHz.
  The bitstream committed in git (`c11659f2…`) was built with an older toolchain, so its
  hash differs. **Always compare against the container build, not the committed binary.**
- The `ghdl` calls in the original Makefile have no path prefix, so they rely on `PATH`.
  Inside the container this works because `/opt/oss-cad-suite/bin` is on `PATH`.
- **KiCad**: `flatpak install --user flathub org.kicad.KiCad` installs **KiCad 10.0.6**.
  Flathub only offers the `stable` branch, and there is no easy way to pin 9.x. Decision
  (project owner): **migrate the project to KiCad 10** in one dedicated commit, after rev A
  has been merged into `main`. Until then, use kicad-cli 10 only for read-only checks.
  Never save the v9 files with v10 by accident.
- `kicad-cli` wrapper: `tools/kicad-cli.sh`.
  - Flatpak's `/tmp` is private, so pass host paths with
    `KICAD_EXTRA_FS=/path/a:/path/b`.
  - In zsh, `K="flatpak run …"; $K` fails because zsh does not word-split variables. Use
    the wrapper script instead.
- kicad-cli **rewrites `*.kicad_prl`** even for read-only commands such as ERC/DRC/export.
  Revert it with `git checkout`; it will be ignored by `.gitignore` anyway.
- Alternative kept in reserve: the KiKit container `docker.io/yaqwsx/kikit:v1.8.1-v10`
  (use `-v9` for KiCad 9).

## 2026-09-26 — Baseline checks of rev A (kicad-cli 10.0.6, read-only)

- Netlist export: OK. Kept as the reference for the connectivity-invariant checks.
- ERC: 4 errors `power_pin_not_driven` (no PWR_FLAG). The remaining 201 are warnings:
  122 `lib_symbol_issues` and 75 `footprint_link_issues`, both caused by v9/v10 library
  differences, plus 4 `multiple_net_names`.
- DRC: 0 errors and 0 unconnected items.
  - Warnings: 68 `missing_courtyard` (the mouse-bite footprints) and 67
    `lib_footprint_issues`.
  - Schematic parity: 68 `extra_footprint` (mouse bites have no symbol), 50
    `duplicate_footprints` (the mouse bites reuse `REF**n`) and 67
    `footprint_symbol_field_mismatch`.
- Git tag `rev-a-prototype` → commit `96515e9` (the last commit before any cleanup).

## 2026-09-26 — Phase 1: cleanup, English translation, documentation

**What was done**

- Untracked the generated files and added `.gitignore`. Git history was **not** rewritten.
- Moved folders with `git mv`:
  - `firmware/iCE40_firmware` → `firmware/ice40`
  - `firmware/test_parziali/*` → `firmware/experiments/*`
  - `hardware/kicad/module-tile` → `hardware/kicad/tile`
- Renamed the KiCad project `tastiera_isomorfa` → `isomorphic_tile`. This is a plain `sed`
  over `*.kicad_sch`, `*.kicad_pcb` and `*.kicad_pro`. It also rewrites the
  `(project "…")` instance blocks and the `(sheetfile "…")` references in the PCB. The
  netlist stayed identical.
- Renamed the KiCad field `Codice` → `MPN` and the footprint `Senza-titolo` →
  `MouseBite_NPTH_0.5mm` with text edits. Netlist, invariants and DRC counts are unchanged.
- Translated all comments to English. The firmware Makefile no longer hardcodes
  `~/Pacchetti/...` and no longer calls `sudo`.
- Pruned the vendored open-logic 4.5.0 to the 9 files used and added the upstream
  `License.txt` (PSI HDL Library License 1.0 = LGPL with an FPGA/static-link exception).
- Added `tools/scripts/check_invariants.py`, `tools/scripts/export_reference.sh`,
  `tools/oss.sh` and `tools/kicad-cli.sh`, plus the whole `docs/` tree.

**Result:** after every step the firmware bitstream hash stays at `e3a7eaf9…`, and the
tile netlist is identical to rev A.

**Lesson**

- **Comments and line shifts do not change the bitstream** with this toolchain (checked
  by adding lines at the top of `top.vhd`). The bitstream hash is therefore a valid
  regression check for text-only firmware changes.
- The OSS CAD Suite GHDL (2026-09-26) needs **glibc ≥ 2.38 and a C compiler** to
  elaborate simulations. The `bookworm` base failed with `cc not found`, then with
  `undefined reference to __isoc23_strtol`. Use `debian:trixie-slim` + `gcc libc6-dev
  zlib1g-dev`.
- With `podman --userns=keep-id`, `HOME` points at the work directory. yosys then drops
  `.config/` and `.local/` into the repo. `tools/oss.sh` sets `-e HOME=/tmp`.
- A bare `build/` line in `.gitignore` also ignores `docs/build/`. Anchor such patterns
  (`firmware/**/build/`).
- kicad-cli 10 writes the netlist as multi-line s-expressions. Parsers must be
  whitespace-agnostic (`check_invariants.py` initially found 0 nets).
- Always run a negative test of a checker (move one switch by 0.04 mm, swap one pin) to
  prove that it can fail.

## 2026-09-26 — First SPICE model of the board clock (preliminary)

**Goal:** check whether simulation can show, before fabrication, that rev B is better.

**What was done:** built the ngspice container (`tools/containers/ngspice`, ngspice 44.2)
and wrote `hardware/si/clock_link.py`. The model uses generic parameters:

- pico-ice driver: 20 Ω, 1.5 ns edges;
- 20 cm dupont wire: 200 Ω T-line plus 150 nH of return inductance;
- 70 mm tile track: 100 Ω;
- 30 pF of lumped load.

It sweeps the series resistor Rs at the driver.

**Result (at the tile inputs)**

| Rs | Overshoot | Undershoot | Rise 10–90 % | Falling edge rings back above VIL (0.8 V)? |
|---|---|---|---|---|
| 0 Ω (rev A) | 72 % | −2.4 V | 3.7 ns | **yes, twice (up to 1.7 V) → risk of double clocking** |
| 33 Ω | 40 % | −1.3 V | 4.4 ns | no |
| 68 Ω | 19 % | −0.6 V | 5.3 ns | no |
| 150 Ω | 0 % | +0.05 V | 9.9 ns | no |

- The model rings at about 22 MHz, like the scope (20–30 MHz). The amplitude, however,
  is larger than measured: 72 % vs about 40 %.
- Missing from the model: the input ESD clamp diodes, which limit the undershoot to about
  −0.5 V; conductor and dielectric losses; and the AD2 bandwidth (about 30 MHz, which
  attenuates the peaks).

**Lesson**

- Plain T-lines plus ideal loads over-predict the ringing. Use **IBIS models** of the
  actual parts: TI publishes them for the LVC parts, and the iCE40UP5K model is published
  by Lattice. ngspice/KiCad can use them through KiCad's KIBIS converter.
- Calibrate the model against a clean measurement first (spring ground tip); only then
  compare the rev-B options.
- The scan clock is slow (≈350 kHz), so slowing the edges (Rs ≈ 68–150 Ω into the load
  capacitance) costs nothing in timing. Check the input transition-rate limit in the
  LVC datasheets (Δt/ΔV).
- Only the controller → first-tile link was modelled. The tile → tile hops
  (U101/U107 → connector → neighbour) still need their own model.

## 2026-09-27 — Which logic parts are mounted? (open)

- The project owner does not know the chip markings, and they cannot be read from the
  media: the videos are 474×850 and the ICs are hidden under the key board.
- **Working assumption for rev B: the ordered parts** (74LVC family, SN74HC161; see
  `hardware/fabrication/rev-a/bom.csv`). The rev-B schematic values will state these parts.
  SI models use LVC/HC IBIS data.
- A marking-code table was added to `docs/build/bom.md` so that anyone can check a built
  tile in one minute. Update this entry once a tile has been checked.
- Source: TI datasheets downloaded from `https://www.ti.com/lit/ds/symlink/<part>.pdf`.
  `pdftotext -layout` is available on the host and extracts the "Device Marking" column.

## 2026-09-27 — KiCad 10 migration and SI models with input clamps

- **Migration:** `kicad-cli sch upgrade` on every sheet, plus `pcb upgrade`.
  - Netlist identical, invariants OK, same ERC/DRC counts.
  - Committed on its own on `rev-b`.
- **Library warnings after the migration:** the flatpak starts without global library
  tables, which caused the ERC warnings `lib_symbol_issues` and `footprint_link_issues`.
  Fix, once per machine:
  `cp /app/extensions/Library/template/{sym,fp}-lib-table ~/.var/app/org.kicad.KiCad/config/kicad/10.0/`
  (run inside the flatpak).
  - The library files live on the host in
    `~/.local/share/flatpak/runtime/org.kicad.KiCad.Library.Footprints/x86_64/stable/active/files/footprints`.
- **pcbnew Python API:** available in the flatpak.
  `flatpak run --filesystem=<dir> --command=python3 org.kicad.KiCad script.py` gives
  KiCad 10.0.6 on Python 3.13.
- **Inter-board net lengths (rev A)**, measured with pcbnew:

  | Net | Length | Vias |
  |---|---|---|
  | B_clk | 141 mm | 6 |
  | L_clk | 14 mm | 0 |
  | T_clk | 8 mm | 0 |
  | L_latch | 83 mm | 3 |
  | B_data | 87 mm | 2 |
  | B_W | 34 mm | 0 |
- **SI models now include input clamp diodes.** This changes the picture a lot compared
  with the plain T-line model.
  - `clock_link.py` (pico-ice → first tile over dupont wires):
    - Rs 0 Ω: 26 % overshoot, −0.86 V undershoot;
    - Rs 68 Ω: 19 %, −0.59 V;
    - Rs 150 Ω: 0 %, no undershoot, rise time 9.9 ns;
    - no double threshold crossings in any case.
  - `tile_hop.py` (U101/U107 → connector → neighbour's B_clk tree):
    - rev A (2 layers, about 110 Ω, 141 mm tree): 22 % overshoot, −0.73 V, single
      crossings;
    - rev B (4 layers, about 55 Ω, 100 mm tree) with Rs = 33 Ω: 0 % overshoot, −0.01 V.
- **Conclusion (preliminary, generic models):** rev A is noisy but within the thresholds
  in the model. The ringing on the scope is dominated by the controller link (dupont wires
  + probe).
- **Decisions:**
  - rev B: 33 Ω series resistors at every driver that leaves the tile;
  - controller link: an adapter with about 100–150 Ω series resistance and a GND wire
    next to each signal.
- **Metric pitfall:** "value one ns after the crossing" gives false alarms on slow edges.
  Count threshold crossings instead (a clean edge crosses once).

## 2026-09-27 — Rev-B schematic and scripted PCB transformation

**Schematic** (`hardware/kicad/tile/scripts/revb_schematic.py`, applied once)

- The inter-board hierarchical labels on the driver side became local `*_drv` labels. New
  33 Ω resistors R201–R207 run from those labels to new hierarchical labels with the
  original names, so the root sheet and the connectors are untouched.
- Added C201–C209 (100 nF per IC) and PWR_FLAGs on VCC, GND, VCC_T and GND_T.
- Result: netlist identical to rev A after `--series R201..R207 --ignore C201..C209`.
  ERC: 0 errors (4 in rev A).
- The ERC errors on `VCC_T`/`GND_T` came from **power symbols in the root sheet whose value
  names the net** (`power:VCC` with value `VCC_T`). The PWR_FLAG has to sit on those same
  symbols.

**Key-switch footprint:** `SW_Cherry_MX_1.00u_PCB` (KiCad stock library) has its origin on
**pin 1**, i.e. the centre plus (+2.54, −5.08). The Kailh hot-swap footprint (vendored from
keyswitch-kicad-library v2.3) has its origin on the **centre**.
`check_invariants.py` therefore locates switches by their 4 mm centre hole. The hot-swap
pads 1 and 2 sit where the Cherry pins 2 and 1 were. This is harmless for a switch.

**pcbnew Python API (KiCad 10.0.6) pitfalls, all hit today**

- `board.Remove(item)` → segfault on the next board access. Use `board.Delete(item)`.
- `fp.SetLayerAndFlip()` on a footprint not yet added to the board → segfault.
  `board.Add(fp)` first.
- `zone.SetOutline(SHAPE_POLY_SET(...))` takes ownership of a Python temporary →
  segfault in `SaveBoard`. Append to `zone.Outline()` in place instead.
- `ZONE_FILLER.Fill()` segfaulted right after creating the zones. Call
  `board.BuildConnectivity()` first, and only fill after routing.
- Other API differences:
  - `LIB_ID.Format()` is not callable from Python; use `GetLibNickname()` / `GetLibItemName()`.
  - `FOOTPRINT.GetFieldByName` does not exist; use `HasField` / `GetField` / `SetField`.
    There is no `RemoveField`.
  - `GetBoardPolygonOutlines(outline, infer)` needs 2 arguments.
  - `BOARD_STACKUP` is not exposed, so the stack-up block is written as text into `(setup)`.
- Wrap scripts with `faulthandler.enable()` to get a Python stack when pcbnew segfaults.
- Net-class patterns are wildcards (`*`, `?`) only; `[LTBR]_*` silently matched nothing.

**Tools**

- Freerouting 2.4.1 needs **Java 25** (class file 69). The `eclipse-temurin:21` image fails
  with `UnsupportedClassVersionError`.
- Headless flags: `-de in.dsn -do out.ses -mp N --gui.enabled=false`.
- Layer SVG export for review: `kicad-cli pcb export svg --mode-single --layers ... --fit-page-to-board`,
  then `rsvg-convert` (on the host) to get a PNG.

## 2026-09-27 — Rev-B PCB produced by script + Freerouting

**Result:** 4-layer board. KiCad DRC: **0 errors, 0 unconnected items, 0 schematic-parity
issues**. Remaining warnings: 41 silk over copper, 23 silk overlap, 8 silk-to-edge (these
three are cosmetic), 11 connection width, and 11 library-footprint mismatches (the rev-A
connector footprints come from the v9 library). Switch/connector/outline invariants OK.

**Iterations and lessons**

1. First routing run: 34 unrouted. They were almost all power pads.
   **Freerouting does not connect SMD pads to plane layers.** Fix: a scripted fan-out (stub
   + via) for every SMD power pad, done **before** routing so the router works around the
   vias. Done after routing, U106/U107 pads could not find room.
2. Copper text "TORTIRE v0.1" on B.Cu (rev A) collided with the hot-swap sockets. Moved to
   silkscreen.
3. The placer checked courtyards only. The hot-swap socket **pads stick out of the socket
   courtyard**, so a fiducial landed on a pad. SMD pads are now obstacles too.
4. The left socket pad came 0.06 mm from the stepped outline (SW102/104/106). Local
   footprint variant `SW_Hotswap_Kailh_MX_1.00u_EdgeTrim` with pad 1 trimmed by 0.3 mm on
   the outer side.
5. `R_latch` stayed unrouted twice: U106 pin 2 was boxed in. Placing **U106 at 180°** (its
   inputs facing R106/J104) fixed it. A second Freerouting pass on the routed board did not.
6. J107 (frozen) vs SW111 socket: the courtyards overlapped by 0.1 mm, while the bodies are
   0.49 mm apart. A DRC exclusion in `.kicad_pro` did not match: the key format
   (`type|x|y|uuid|uuid`, marker position in nm) needs the exact marker position, which
   kicad-cli does not print. `pcbnew.WriteDRCReport` from Python asserts outside the GUI
   (`Pgm()`). Instead, the J107 courtyard edge towards the socket was pulled in to a
   0.3 mm margin.
7. `SetField()` creates **visible** silkscreen fields (MPN/Manufacturer showed up on the
   silk). Hide every field except Reference/Value.
8. Board-only items (mouse bites, fiducials): `SetBoardOnly`, `SetAllowMissingCourtyard`,
   excluded from BOM/CPL, unique references MB1..MB68. This cleared 124 parity warnings.
9. Freerouting's own "violations" count (181) did not correspond to KiCad DRC errors.
   **Always judge with KiCad DRC.**

**Rev-B routed lengths:**

| Net | Length |
|---|---|
| B_clk | 141 mm (the two input connectors are far apart) |
| L_clk_drv / L_clk | 2.5 / 17.9 mm |
| T_clk_drv / T_clk | 3.8 / 23.1 mm |
| data_drv | 34 mm (4 vias) |
| latch_drv | 33 mm |

SPICE for the hop as routed, with 33 Ω: 1 % overshoot, −0.03 V undershoot. Rev A: 22 %,
−0.73 V.

**Follow-up (same day):** the placer now places the series resistors **before** the
decoupling caps.

- Every series resistor is now 1.9–2.6 mm (straight line) from its driver pin.
- `data_drv` (53 mm) and `latch_drv` (30 mm) are still long, but only because those nets
  also feed internal inputs (U102.1 column-end detector, U105 latch inverter). The
  inter-board side starts at the resistor.
- The whole PCB is rebuilt in about 3 minutes by
  `hardware/kicad/tile/scripts/revb_pipeline.sh`.
  - Result: DRC 0 errors / 0 unconnected / 0 parity; invariants OK.
  - Remaining warnings: silkscreen cosmetics, 11 library mismatches, 3 connection widths.

**Open for human review:** silkscreen cleanup, 3D stack-height check (C105 is 7.7 mm tall),
C105 MPN, and the clock routing in the GUI.

## 2026-09-27 — Production outputs and panel

- `production.sh` (kicad-cli only) first runs ERC/DRC with `--exit-code-violations
  --severity-error` and stops on errors. It then exports:
  - Gerber X2 for 4 layers, Excellon drill files and drill maps;
  - IPC-2581, BOM, pick-and-place, assembly PDFs, schematic PDF, STEP.
- `zip` is not installed on the host; use `python3 -m zipfile -c`.
- **Pick-and-place pitfall:** the Kailh hot-swap footprint sits on F.Cu, with the socket
  pads on B.Cu. KiCad therefore reports the sockets as `top`. The script rewrites SW*
  rows as `bottom` and `FAB-NOTES.md` asks the assembler to verify their orientation.
  Also use `--smd-only`, so the hand-soldered THT connectors are left out.
- **KiKit** `docker.io/yaqwsx/kikit:v1.8.1-v10` works rootless (it prints a harmless
  wx assert at start-up).
  - Without `--post 'refillzones: true'` the panel has 199 `hole_clearance` errors: the
    old zone fills overlap the new mouse-bite holes.
  - With the refill: panel DRC 0 errors.

## 2026-09-27 — SPICE refinement without new hardware (branch `rev-b`)

- **Digitised the scope photo** (`hardware/si/digitize_scope.py`).
  - Grid lines are detected by colour, and there is a keystone correction (the photo is
    oblique: 215 px/div at the top vs 210 px/div at the bottom).
  - Channel 2 has a +3.6 V display offset.
  - Pitfalls: `np.interp` clamps outside the calibration range (use a linear fit), and the
    WaveForms toolbar has blue/yellow pixels (ignore y < 250 px).
  - Result: levels 3.05 / −0.1 V, overshoot to 3.9 V, undershoot to −1.0 V, ringing
    ~16–20 MHz, and only 10 ns per sample (100 MS/s).
- **Vendor models:** TI IBIS files come from `https://www.ti.com/lit/zip/<id>`. The IDs
  are listed on the product pages: SCEM288 (LVC2G125), SCEM283 (LVC2G126), SCEM216
  (LVC1G04); the `.cir` SPICE models (SCEM6xx) are TINA behavioural models from datasheet
  values, less useful. No IBIS was found for SN74LVC165A or the iCE40UP5K. LVC inputs have
  a GND clamp only.
- `ibis_lite.py`: IBIS → ngspice with B-sources + `pwl()` tables, and linear switching
  coefficients from `[Ramp]`.
- **Bug found and fixed:** my AD2 Butterworth had Q = 1.41 instead of 0.707, so it rang
  by itself (30 % overshoot). Always check a filter's step response
  (now 4.3 % overshoot and 11.4 ns rise, as expected). The first calibration run, done
  with the bad filter, was thrown away.
- **Calibration** (Nelder–Mead on 9 parameters, about 10 minutes): RMS 0.20 V. Several
  parameters hit their bounds, so the model is plausible but not unique.
  - The AD2 views, the node view and the controller-R sweep are in
    `docs/architecture/electrical.md`.
  - Main answers: the spring tip barely matters with a 30 MHz instrument; the real node at
    the first tile rings more than the capture shows; a series resistor at the pico-ice
    (about 100 Ω) fixes the controller link.
- **IBIS tile hop:** rev A far load 76 % overshoot with 7 VIH crossings (pessimistic
  lossless model); rev B with 33 Ω: 14 %, clean. 47 Ω dwells on VIL, so 33 Ω stays.
- **ngspice pitfalls:**
  - Some parameter corners make ngspice crawl. Every run now has a subprocess timeout,
    and the fit treats a timeout as a high cost.
  - A 200 MHz front-end view stalled the solver, so it was dropped (the node view is the
    ideal-instrument reference).
- **Shell pitfall:** `pkill -f <pattern>` / `pgrep -f` also match the invoking shell when
  the pattern appears in the same command line, and exit 144 kills the tool call. Kill by
  PID or with `pgrep -x ngspice`.
