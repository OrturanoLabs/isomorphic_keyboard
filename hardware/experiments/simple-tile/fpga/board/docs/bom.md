# BOM + sourcing evidence -- gw1nz production tile (rev-A)

Status: **every placed part has dated supplier evidence** (fetched
2026-10-14). Assembly quote remains a **blocked gate** (needs account +
file upload; public pricing evidence recorded instead).

Quantities are per tile; reference list is generated (kicad/board_gen.py
`parts_gw1nz()`) and cross-checked by tools/schematic_check.py (S1..S7).
The 19 chassis contact pads and 11 test points (TP_DONE/GND/JTAGSEL/
READY/RECFG/TCK/TDI/TDO/TMS/VCC/VCC1V2) are board features, not BOM
lines.

## Sourced lines (evidence URLs + prices all fetched 2026-10-14)

| refs | qty | part | supplier evidence |
|---|---|---|---|
| U1 | 1 | Gowin GW1NZ-LV1QN48C6/I5 (FPGA, QFN-48 0.4 mm) | **LCSC C5799569**, `https://www.lcsc.com/product-detail/C5799569.html` -- stock 888-924; US$6.6772@1, 5.6426@10, 5.012@30, 4.4832@100. Mouser also lists GW1NZ-LV1QN48C6/I5 (product page up; price not captured). Win Source broker 1080 @ ~US$2.19-3.28 (broker, not primary sourcing). |
| U2 | 1 | TI TLV75512PDBVR (LDO 1.2 V 500 mA, SOT-23-5) | **DigiKey 296-TLV75512PDBVR**, `https://www.digikey.com/en/products/detail/texas-instruments/TLV75512PDBVR/9356525` -- stock 8,346-8,377; US$0.30@1, 0.206@10, 0.1832@25, 0.1573@100, 0.1239@3000(T&R). |
| SW1-SW12 | 12 | Kailh MX hotswap socket CPG1511 (CPG151101S11) | **kailhswitch.net** (official Kailh store), `https://kailhswitch.net/products/kailh-hotswap-sockets-mx-and-choc-switch-mechanical-keyboard-switches-socket` -- "$0.21USD ea" (SKU CPG151101S11-16). AliExpress 500-pc packs also listed (600-INCH Official Store). Keyboard-market part: NOT in LCSC/JLC PCBA libraries -> hand-solder or consigned at assembly. |
| FB1 | 1 | Ferrite bead 120 ohm@100 MHz, 0603, 2 A (Murata BLM18PG121SN1D; UG293 class) | **LCSC C14709**, `https://www.lcsc.com/product-detail/C14709.html` -- stock 1,294,550; US$0.0147@50 (min 50). DigiKey (digikey.sg listing) 1.57 M stock, US$0.14@1. |

## Commodity lines (spec'd, not individually quoted)

| refs | qty | spec |
|---|---|---|
| C1, C2, C3 | 3 | 100 nF 50 V X7R 0603 (e.g. Yageo CC0603KRX7R9BB104) -- VCC decoupling |
| C4, C5 | 2 | 100 nF 50 V X7R 0603 -- VCC1V2 decoupling |
| C8, C9 | 2 | 1 uF 25 V X5R/X7R 0603 -- TLV755P required COUT (before FB1) / CIN (SBVS320D 5.3) |
| C6, C7 | 2 | 4.7 uF 16 V X5R/X7R 1206 -- VCC1V2 / VCC bulk |
| R1, R2 | 2 | 1 k 0603 -- MODE0/MODE1 auto-boot straps (UG293) |
| R3-R6 | 4 | 4.7 k 0603 -- TCK pull-down + READY/DONE/RECONFIG pulls |
| R7-R11 | 5 | 0R jumper 0402 -- series-termination positions on the 5 forward-driven outputs (docs/termination.md); POPULATED 0R by default == today's circuit, value selected after bench B2 (33-100 ohm class); never DNP at fab (DNP would open the net) |

Commodity passives are megastock at every distributor (representative
100 nF 0603: Yageo CC0603KRX7R9BB104 class; LCSC/DigiKey stock in the
millions). Priced at the assembly house; no single-source risk. Honest
est. << US$0.10 total per tile.

## Cost roll-up (single-piece component cost, no shipping/PCBA)

- U1 6.68 + U2 0.30 + sockets 12x0.21 = 2.52 + FB1 0.02 + passives ~0.10
- **~US$9.6 / tile** (components only). At qty 10: U1 5.64 -> ~$8.6.

## Assembly quote -- BLOCKED GATE (recorded honestly)

JLCPCB formal PCBA quote requires account sign-in + Gerber/BOM/CPL upload;
not obtainable from this workspace. Public evidence captured 2026-10-14
(`https://jlcpcb.com/pcb-assembly`):

- "$6 / $9 / $10 monthly SMT coupons -- No Setup Fee"
- "680,000+ in-stock components with smart BOM matching" (LCSC-fed)
- "Supports BGA & fine-pitch components (>=0.35 mm)" -> QFN-48 0.4 mm OK.
- GOWIN x JLCPCB cooperation announcement (gowinsemi.com, 2026-04-30) --
  Gowin parts, GW1NZ included via LCSC C5799569, on JLC PCBA.

Consequence: PCBA line item is **TBD-quote**, flagged in every cost
statement; expect order-of-magnitude US$30-100/tile at prototype qty
(2-5 boards) from published-structure reasoning, NOT a quote. Kailh
sockets are consigned/hand-soldered (see above).

## up5k fallback BOM delta (NOFIT review artifact, not for ordering)

Same U2/FB1 class + iCE40UP5K-SG48 + SPI flash (SOIC-8, NOFIT on rev-A)
+ 16 extra 10 k pull-downs (iCE40 pads pull-UP only) + one 100 ohm
VCCPLL RC filter. See kicad/board_gen.py `parts_up5k()`; the up5k
land is LAND-TBD and the body is NOFIT (docs/candidate.md).
