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
