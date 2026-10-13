# pincon_check report

| check | desc | result | detail |
|---|---|---|---|
| **GW1NZ_QN48** (GW1NZ-LV1QN48C6/I5) | | **PASS** | |
| GW1NZ_QN48:B1a | constraint assigns exactly the 26 tile nets | PASS | missing=[] extra=[] |
| GW1NZ_QN48:B1b | 26 distinct pads | PASS | 26 assignments / 26 distinct |
| GW1NZ_QN48:B2 | every assigned pad is a vendor-verified user IO | PASS | all 26 pads IO-classed |
| GW1NZ_QN48:B3a | no tile net lands on a reserved pad (JTAG/strap/config/power) | PASS | clash=[] |
| GW1NZ_QN48:B3b | config/JTAG/strap pads are enumerated for the board test pads | PASS | reserved cfg/jtag pads: ['3', '4', '42', '43', '45', '46', '48', '5', '7'] |
| GW1NZ_QN48:B4 | vendor power/ground(/config-only) pad set == chipdb-missing set (power fact now sourced from the vendor pin list, not inferred) | PASS | vendor=[1, 2, 12, 25, 26, 36, 37] empirical=[1, 2, 12, 25, 26, 36, 37] |
| GW1NZ_QN48:B5 | pad pull directions: 5xUP; 4xDOWN only where the silicon can | PASS | pulls consistent |
| GW1NZ_QN48:B6 | key pull strategy = pad-down | PASS | key pulls on pads: ['DOWN'] |
| GW1NZ_QN48:H1 | excluded-hazard/LED pads unused by tile nets | PASS | used=[] excluded=['9'] |
| GW1NZ_QN48:S1 | pin DB cites vendor primary sources (URL + sha256), pin list present | PASS |  |
| **UP5K_SG48** (iCE40UP5K-SG48I (fallback board variant)) | | **PASS** | |
| UP5K_SG48:B1a | constraint assigns exactly the 26 tile nets | PASS | missing=[] extra=[] |
| UP5K_SG48:B1b | 26 distinct pads | PASS | 26 assignments / 26 distinct |
| UP5K_SG48:B2 | every assigned pad is a vendor-verified user IO | PASS | all 26 pads IO-classed |
| UP5K_SG48:B3a | no tile net lands on a reserved pad (JTAG/strap/config/power) | PASS | clash=[] |
| UP5K_SG48:B3b | config/JTAG/strap pads are enumerated for the board test pads | PASS | reserved cfg/jtag pads: ['14', '15', '16', '17', '7', '8'] |
| UP5K_SG48:B4 | vendor power/ground(/config-only) pad set == chipdb-missing set (power fact now sourced from the vendor pin list, not inferred) | PASS | vendor=[1, 5, 7, 8, 22, 24, 29, 30, 33] empirical=[1, 5, 7, 8, 22, 24, 29, 30, 33] |
| UP5K_SG48:B5 | pad pull directions: 5xUP; 4xDOWN only where the silicon can | PASS | pulls consistent |
| UP5K_SG48:B6 | key pull strategy = external-10k | PASS | key pulls on pads: [None] |
| UP5K_SG48:H1 | excluded-hazard/LED pads unused by tile nets | PASS | used=[] excluded=['39', '40', '41'] |
| UP5K_SG48:S1 | pin DB cites vendor primary sources (URL + sha256), pin list present | PASS |  |
