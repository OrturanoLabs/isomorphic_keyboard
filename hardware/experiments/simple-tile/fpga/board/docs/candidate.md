# Candidate choice for the single-PCB FPGA tile

Status: decided for the placement-prototype stage. Primary
**GW1NZ-LV1QN48C6/I5** (Gowin LittleBee GW1NZ-1, QFN48 6x6 mm, 0.4 mm
pitch); fallback **iCE40UP5K-SG48I** tracked but placement-blocked.

## Why GW1NZ is the primary

| criterion | GW1NZ-LV1QN48 | iCE40UP5K-SG48 |
|---|---|---|
| configuration | on-chip flash, AUTO BOOT few ms (DS841 2.13-2.14, UG290 MODE=000) | OTP NVCM (open flow unproven) or **external SPI flash** (TN02001) |
| rails | VCC 1.2 V core + VCCIO/VCCX 3.3 V, one small LDO | VCC 1.2 V + VCCPLL 1.2 V + VCCIO 3.3 V + VPP_2V5, LDO + filters |
| pad pulls | UP **and DOWN** (LVCMOS33) -> key/latch pull-downs are free | pull-UP only -> **+16 external 10k** |
| tile IO fit | 26/30 eligible pads (pin 9 excluded, see hazard) | 26/39 |
| package on tile | QFN 6x6 FITS bottom side (U1 at 7.86, 5.40) | SG48 7x7 **NOFIT** (needs 7.6mm court vs ~7.5 mm free) |
| open flow | yosys+nextpnr-himbaechel, bitstream packed (351954 B .fs) | yosys+nextpnr-ice40, bitstream packed (104090 B .bin) |

The deciding physical fact: the UP5K's SG48 body does not fit anywhere on
the tile's bottom side next to the 12 sockets + 19 chassis pads (GK gate
"GKN", largest free square ~7.5 mm). Concession options if the fallback
ever becomes load-bearing: (a) 6x6-class iCE40 part does not exist for
UltraPlus -> re-lattice to UP5K-UWG30/WLCSP (harder assembly), (b) enlarge
the tile outline (NOT allowed: breaks the 6-neighbour 1.0 mm contract),
(c) sacrifice a key column. None is currently attractive; GW1NZ remains
the lead.

## Pin-9 order-code hazard (GW1NZ)

Commercial pinout UG842-1.6.8E lists QN48 pin 9 = user IO `IOR2A`;
automotive package doc UG846-1.1E (and UG842-1.5.1E's change note) list
pin 9 = VCC. Ordering the automotive variant on a board that wired pin 9
as IO would short VCC into a logic net. Pin 9 is therefore **excluded**
from tile assignment (unused pads on the board: 6, 9, 14, 15, 29 --
checker N7). 26 tile IOs fit without it.

## Configuration / JTAG / straps (GW1NZ, as built on the board)

- MODE[2:0] = 000 = AUTO BOOT from embedded flash (UG290 Table 5-1);
  MODE2 internally GND on QN48; **MODE1 (pin 42), MODE0 (pin 43) strapped
  to GND via R2/R1 1k** (UG293 guidance).
- JTAG = MODE-independent (UG290 note); pins 3/4/5/7 TCK/TMS/TDI/TDO on
  test pads; **TCK pulled down 4.7k on PCB (R3)**; JTAGSEL_N (pin 44)
  floating (internal weak pull-up keeps JTAG function; TP_JTAGSEL
  provided).
- READY (45) / DONE (46) / RECONFIG_N (48): open-drain/active-low status;
  **4.7k pull-ups to VCC (R4/R5/R6)**; all three on test pads.
- Power-up conditions to note for the board review: ramp monotonic, rates
  VCC 0.6-6 mV/us, VCCX 0.6-10, VCCIO 0.1-10 (DS841 3.1.3); POR trips
  VCC 0.8 V / VCCX 1.5 V / VCCIO 0.95 V (DS841 3.1.5); flash init needs
  VCC>=1.08 V and VCCX>=1.62 V at config start (UG293).

## Land-pattern provenance

- GW1NZ-QN48 footprint: rows +/-2.95 (P=5.90), lands 0.85x0.20, EP 2.70,
  body 6.00, pin-1 top-left CCW -- matches UG846 Fig 4-1/4-2 *recommended
  PCB layout* dims (machine-checked, `tools/footprint_verify.py`).
- UP5K-SG48 footprint: package dims verified vs FPGA-DS-02053-8.8 sec. 31;
  the *land geometry* (rows +/-3.45, 0.8x0.25) is KiCad stock practice --
  **LAND-TBD**, no vendor recommended-land captured; flagged, not hidden.

## Logic-level fit (production pin maps, real PnR)

`tools/run_board_pnr.sh` (oss container): 4/4 PASS. GW1NZ fall+track:
34/1152 LUT4, 24/48 IOB (26 tile IO incl. clock/GCLK pad), clk interior
Fmax 213-342 MHz vs the 20 MHz target. UP5K: 26/39 SB_IO, 62-69 MHz.
A BEL control against the OLD empirical cst moved 25/26 IO cells,
proving the production `.cst` was really applied.

## Honest open items

- Board not routed; silkscreen cleanup pending; see docs/readiness.md.
- LDO part class only (TLV75512-class SOT-23-5); exact part + quiescent
  choice TBD (docs/power_reg.md).
- Bench confirm of pad pull-DOWN strength on keys (cst note: external 10k
  fallback exists).
- 21-contact rev-B interface: needs a connector-next certification run
  first; board implements the certified 19-contact interface.
