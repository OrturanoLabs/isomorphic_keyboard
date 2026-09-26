# Bill of materials (rev A, per tile)

Source: `hardware/fabrication/rev-a/bom.csv`, exported from the rev-A schematic and kept
unchanged as the record of what was ordered. The values below were corrected where the
symbol value disagreed with the ordered part (see [electrical](../architecture/electrical.md)).

| Refs | Qty | Part | MPN (rev A) | Footprint |
|---|---|---|---|---|
| SW101–SW112 | 12 | Cherry MX compatible switch | – | Cherry MX 1u, THT |
| R101–R109, R122–R133 | 21 | 10 kΩ 1 % | RMCF0805FT10K0 | 0805 |
| R110–R121 | 12 | 100 Ω 1 % | CRCW0805100RFKEA | 0805 |
| C101, C102 | 2 | 100 nF X7R 50 V | C0805C104K5RACTU | 0805 |
| C103, C104 | 2 | 4.7 µF X7R 25 V | CL31B475KAHNNNE | 1206 |
| C105 | 1 | 100 µF electrolytic | 860040573004 | radial 6.3 mm, THT |
| U101 | 1 | 2× buffer, OE high | 74LVC2G126DCTRG4 | VSSOP-8 (DCT) |
| U102 | 1 | 2× AND | SN74LVC2G08IDCTRQ1 | VSSOP-8 (DCT) |
| U103, U104 | 2 | 8-bit PISO shift register | SN74LVC165ADR | SOIC-16 |
| U105 | 1 | inverter | SN74LVC1G04DBVR | SOT-23-5 |
| U106 | 1 | 2× OR | SN74LVC2G32DCTR | VSSOP-8 (DCT) |
| U107 | 1 | 2× buffer, OE low | SN74LVC2G125DCTR | VSSOP-8 (DCT) |
| U108 | 1 | D flip-flop | SN74LVC2G74DCTR | VSSOP-8 (DCT) |
| U109 | 1 | 4-bit binary counter | SN74HC161DR | SOIC-16 |
| J101 | 1 | 1×6 socket, 2.54 mm, right angle | 613010143121 | THT |
| J102 | 1 | 1×8 socket, 2.54 mm, right angle | 613010143121 | THT |
| J103 | 1 | 1×8 header, 2.54 mm, right angle | 61300811021 | THT |
| J104 | 1 | 1×6 header, 2.54 mm, right angle | 61300811021 | THT |
| J105, J106 | 2 | 1×8 socket, 2.54 mm, vertical | – | THT |
| J107, J108 | 2 | 1×8 header, 2.54 mm, vertical | – | THT |

The rev-A PCB uses the KiCad `MSOP-8_3x3mm_P0.65mm` footprint for the DCT-package parts.
Rev B will define fields for MPN, manufacturer and alternates on every symbol, and export
the BOM with `kicad-cli` (see [assembly](assembly.md)).

## Identifying the mounted logic parts

Small packages carry a short marking code instead of the part name. The codes below come
from the TI datasheets (package option addendum, fetched 2026-09-27). The marking may
carry an extra date/lot character. Read it with a magnifier or a phone macro photo:

- U101, U104, U107 and U109 are on the **bottom** of the logic board;
- the other ICs are on the top, under the key board.

| Ref | Ordered part (rev A) | Marking if ordered part | Marking if the symbol value was fitted instead |
|---|---|---|---|
| U101 | 74LVC2G126DCTRG4 | `C26` | 74AUC2G126: `U26` |
| U102 | SN74LVC2G08IDCTRQ1 | automotive part, check its own datasheet | 74AUC2G08: `U08` |
| U103, U104 | SN74LVC165ADR | `LVC165A` | 74HC165: `HC165` |
| U105 | SN74LVC1G04DBVR | `C04` + one character | 74AHC1G04: `A04` + one character |
| U106 | SN74LVC2G32DCTR | `C32` | – |
| U107 | SN74LVC2G125DCTR | `C25` | 74AUC2G125: `U25` |
| U108 | SN74LVC2G74DCTR | `C74` | – |
| U109 | SN74HC161DR | `HC161` | 74LS161: `LS161` |

A `U..` code (74AUC) on a 3.3 V tile is out of specification and must be replaced by the
LVC equivalent, which has the same pinout.
