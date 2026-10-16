# Checkpoint: GW1NZ-LV1QN48 open programming path review (read-only, bench-nothing)

Updated: 2026-10-14 (rev 2, review-tightened). Scope: independent read-only review of
the fully-open bitstream programming path for the exact selected part
(GW1NZ-LV1QN48C6/I5). No physical programming, no USB/hardware access, no installs, no
container runs, no board/** inspection (electrical worker active). Owned file: this
note only. FPGA-01 stays with the electrical worker; FPGA-02..04 stay pending.

## Question

Does the open source boot-programming story (JTAG SRAM + persistent embedded flash, no
vendor tools) hold for GW1NZ-LV1QN48, or does a gap block FPGA-01 schematic closure?
Which signals must the schematic reserve?

## Verdict

**No source-code support gap identified.** In upstream openFPGALoader (pinned commit
`bf2b52916e7b6216ba1cc0b30933827d7735b05d`, 2026-10-05, post-v1.1.1 master) the exact
idcode 0x0100681b ("GW1NZ-1") is listed for BOTH JTAG SRAM load (`-m`) and embedded
internal-flash write (`-f`), and the code paths exist. Field reports show flash
success on the same die. **Unverified and NOT covered by this verdict: our physical
board, our JTAG cable, our .fs on a real chip, and the exact openFPGALoader build
bundled in the pinned local container image.** Nothing here claims bench evidence.

## Evidence — support for the exact idcode (upstream, commit-pinned)

Base: https://github.com/trabucayre/openFPGALoader/blob/bf2b52916e7b6216ba1cc0b30933827d7735b05d

- idcode table entry: GW1NZ-1 = 0x0100681b, irlen 8 — `src/part.hpp#L447`
  (…/src/part.hpp). Our in-tree build's bitstream header carries exactly this idcode:
  `synth/results/build/gw1nz_fall.fs` line 3 = key-0x06 record `val=0x60000000100681b`
  (decode method per `src/fsparser.cpp#L84`-L93).
- Support matrix: LittleBee (GW1N) list includes **GW1NZ-1; Memory: OK; Flash: IF** —
  `doc/FPGAs.yml#L55`-L66; board preset `tangnano1k` = "littleBee GW1NZ-1, Memory OK,
  Flash IF" — `doc/boards.yml#L880`-L885.
- Code paths: `detectFamily()` maps 0x0100681b into the generic GW1N path with no
  NZ-specific rejection (`src/gowin.cpp#L200`-L228); `program()` dispatches FLASH_MODE
  → `programFlash()` / MEM_MODE → `programSRAM()` (`src/gowin.cpp#L410`-L422);
  embedded-flash writer implements Gowin TN653 (`src/gowin.cpp#L588`-L589).
- Field demonstration: issue #648 (open 2026-04-17) — one user's `-f` CRC failure on
  Tang Nano 1K, but commenter yrabbit (apicula author) and maintainer trabucayre
  (2026-04-30) both flashed the same board class successfully with
  `openFPGALoader -b tangnano1k -f blinky.fs`; maintainer attributes the failure to
  that board's clone-FTDI debugger firmware: https://github.com/trabucayre/openFPGALoader/issues/648
- idcode-mismatch semantics ("wrong-device bitstream" error): closed issue #252
  https://github.com/trabucayre/openFPGALoader/issues/252. tangnano1k board preset was
  merged 2022 via PR #171: https://github.com/trabucayre/openFPGALoader/pull/171.

## Known limits (exact, not general)

- User-data flash (`--user-flash`) and MCU-firmware paths are GW1N(R)-9(C)-only
  (`src/gowin.cpp#L155`-L170). Irrelevant: config flash is what we need.
- Internal-flash write has NO readback verify: "writing verification not supported"
  (`src/gowin.cpp#L322`-L323); confidence = the USERCODE CRC printout.
- Flash flow forces 2.5 MHz JTAG (`src/gowin.cpp#L282`) — normal, not a board issue.
- Doc asymmetry: `doc/vendors/gowin.rst#L45`-L62 still documents `-f` only for
  tec0117/runber/brs-100-gw1nr9/epm11 boards; the compatibility table covers GW1NZ-1.
  Treat tangnano1k-class flash write as field-proven, not doc-certified.
- Local pinned container image is oss-cad-suite **2026-09-26**; its bundled
  openFPGALoader version/support list cannot be inferred from the image date and is
  NOT verified here (container runs forbidden in this review). The version/listing
  check is recorded below as the first light-weight bench-preparation step.
- Apicula hardware-in-the-loop CI (`examples/Makefile`, YosysHQ/apicula master
  cc579322ba1d45c10162b6fab6fff0d86be08033, 2026-10-13) exercises openFPGALoader SRAM
  loads on other Gowin boards; no tangnano1k `-f` CI was found — flash evidence stays
  the issue-#648 logs above.

## SecurityBit / readback-protection — sourced facts and explicit unknowns

Sourced:
- Our in-tree `synth/results/build/gw1nz_fall.fs` (351954 B, built 2026-10-12 in the
  pinned oss-cad-suite 2026-09-26 image) header records (decoded per fsparser key table): line 3 key
  0x06 idCode 0x0100681b; **line 6 key 0x0B (32-bit) — the record fsparser labels
  "only present when bit_security is set"**; line 9 key 0x3B = last header line with
  crc + cfg length (`src/fsparser.cpp#L84`-L105, #L158-L164).
- That 0x0B record is a fixed artifact of gowin_pack's GW1N-class .fs writer:
  `fill_header_footer` docstring "Currently limited to checksum with CRC_check and
  security_bit_enable set" — apycula/gowin_pack.py#L6964-L6983 (YosysHQ/apicula @
  cc579322ba1d45c10162b6fab6fff0d86be08033). gowin_pack offers NO security CLI option
  (full arg list: gowin_pack.py#L23-L46) — the flag is not a user-selected choice in
  the open flow.
- openFPGALoader only parses/displays the record (`_hdr["SecurityBit"]="ON"`,
  fsparser.cpp#L99-L105) and erases header records from the payload written to the
  device (fsparser.cpp#L267-L268). No writer-side security path exists in gowin.cpp
  beyond status-register display strings ("Security Final", "FLASH lock",
  gowin.cpp#L54, #L483-L492) — those decode READ status bits; openFPGALoader does not
  set them.
- Empirical (weak): the working tangnano1k logs in issue #648 also show
  `SecurityBit: ON` in their header dumps, and those boards remained
  JTAG-(re)programmable across reported flash cycles. Anecdotal, not a guarantee.

Explicitly UNVERIFIED (vendor document required; do NOT source from this note):
- What the GW1NZ-1 DEVICE does with bit-security: its exact relation to configuration
  readback protection, any one-way/latching behavior, and interaction with the
  status register's "Security Final"/"FLASH lock" bits. These names must not be
  conflated with the .fs header flag; none of that device-side semantics is
  established here.

Safe bench hold point: the first `-f` flash on real hardware must include an
erase → re-flash → power-cycle cycle early (FPGA-04) to demonstrate the board stays
re-programmable with our image. DO NOT experiment with any security, lock or
encryption feature (vendor tool or fuse options) until Gowin's device-side semantics
are verified against the vendor documents; treat such experiments as permanently
device-risking and out of scope for the open-flow path.

## Schematic requirements the electrical worker (FPGA-01) should review against DS841

1. JTAG access: expose TCK/TMS/TDI/TDO + GND + 3.3 V reference on reachable pads/header
   on EVERY tile (identical images; one-time programming at assembly; pogo/fixture
   footprint is a layout decision for FPGA-02).
2. Keep JTAG pins un-consumed by user logic: the production flow does not pass
   `--jtag_as_gpio` (cst comment "JTAG left live"; flag exists at
   gowin_pack.py#L30). If JTAG pins were ever consumed as GPIO, JTAG-detection loss
   applies (openFPGALoader doc note for GW1N-4K, doc/vendors/gowin.rst#L67-L70):
   confirm whether QN48 carries JTAGSEL_N; if so, strap it to keep JTAG enabled.
3. Confirm MODE pin strap = autoboot-from-embedded-flash with JTAG enabled (DS841 mode
   table; worker owns the vendor-doc check — NOT re-verified here).
4. RECONFIG_N: keep as the dedicated config pin (flow does not pass
   `--reconfign_as_gpio`, gowin_pack.py#L35); keep it accessible/pulleable for bench
   re-boot forcing; confirm DS841 pull requirements.
5. JTAG bank's VCCIO must be powered at 3.3 V at programming time (cable reference).
6. DONE/READY-type status visibility (test pad or spare net) is free bench
   observability for the FPGA-04 boot test — nice-to-have, not a blocker.
7. Cable: program with a 3.3 V probe; openFPGALoader supports many
   (FT2232/FT232H-class, CH347, CMSIS-DAP, dirtyJtag, ... — doc/cable.yml). No on-tile
   programmer exists or is desired (no tile MCU).

## Recorded-not-run procedures (physical access / orchestrator approval needed)

1. In pinned image: `tools/oss.sh openFPGALoader -V` and
   `tools/oss.sh openFPGALoader --list-fpga | grep -i gw1nz` — records the ACTUAL
   bundled version and listing; do not infer support from the image date.
2. `openFPGALoader --detect` on one assembled tile → expect idcode 0x0100681b.
3. Volatile path: `openFPGALoader -m synth/results/build/tile_gw1nz_fall.fs` → behavior
   check; also validates device-vs-bitstream idcode match (cf. #252 error text).
4. Persistent path: `openFPGALoader -f <tile>.fs`, then erase + re-flash + power-cycle
   (hold point above); confirm unassisted boot (acceptance lives in FPGA-04 task 2).
5. Failure handling: a "-f CRC FAIL / Read 0x00000000" symptom matches open issue
   #648 — retry/replace the JTAG probe before suspecting the chip.

## Uncertainty statement

Embedded-flash support is source-listed, code-present and field-reported, but NOT
vendor-doc-certified by openFPGALoader's board docs, NOT version-verified in our
pinned local image, and NOT bench-validated on our board, pads, cable or .fs. This
note changes no task status and claims no hardware result.
