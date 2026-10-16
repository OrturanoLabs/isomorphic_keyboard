# board_net_check report

## gw1nz: PASS

- [OK] N1: 49/49 FPGA pad nets exact
- [OK] N2: FPGA pads per rail: {'GND': [2, 26, 49], 'VCC': [1, 25, 36], 'VCC1V2': [12, 37]}
- [OK] N3: straps+filters: OK
- [OK] N4: TP coverage: all 11 nets have exactly one TP
- [OK] N5: 100n: VCC x3 VCC1V2 x2; 4u7: VCC x1 VCC1V2 x1; 1u: VCC x1 VCC1V2_RAW x1; VCC1V2_RAW pads=['C8.1', 'FB1.1', 'U2.5'] (want exactly [C8.1, FB1.1, U2.5] = LDO COUT cap + ferrite series)
- [OK] N6: sockets bad=[]; JP count=19; JP nets == 14 signals+VCC+GND: True; presence refs present: ['JP_GND_DET_T', 'JP_GND_DET_B', 'JP_GND_DET_R']
- [OK] N7: no-net FPGA pads [6, 9, 14, 15, 29] == expected unused [6, 9, 14, 15, 29]
- [OK] N8: single-pad nets={}; unexpected={} (gw1nz: NONE allowed; up5k NOFIT: only U1-facing nets allowed)
- [OK] N9: presence pads bonded to GND: ['GND', 'GND', 'GND']; required GND nodes missing=[]
- [OK] N10: series-R split R7..R11 exact (U1--Rn.1, Rn.2--JP; DRV nets mirror interface)

## up5k: PASS

- [OK] N1: U1 ABSENT (up5k NOFIT board is a placement-review artifact by design)
- [OK] N2: skipped (U1 absent)
- [OK] N3: straps+filters: OK
- [OK] N4: TP coverage: all 9 nets have exactly one TP
- [OK] N5: 100n: VCC x4 VCC1V2 x2; 1u: VCC x1 VCC1V2 x1; VCCPLL caps x2
- [OK] N6: sockets bad=[]; JP count=19; JP nets == 14 signals+VCC+GND: True; presence refs present: ['JP_GND_DET_T', 'JP_GND_DET_B', 'JP_GND_DET_R']
- [OK] N7: skipped (U1 absent); expected unused=[6, 21, 39, 40, 41, 45, 46, 47, 48]
- [OK] N8: single-pad nets={'B_W': 'JP_B_W.1', 'B_clk': 'JP_B_clk.1', 'B_data': 'JP_B_data.1', 'B_first': 'JP_B_first.1', 'CFG_DONE': 'TP_CDONE.1', 'L_clk': 'JP_L_clk.1', 'L_endrow': 'JP_L_endrow.1', 'L_latch': 'JP_L_latch.1', 'T_W': 'JP_T_W.1', 'T_clk': 'JP_T_clk.1', 'T_endcol': 'JP_T_endcol.1'}; unexpected={} (gw1nz: NONE allowed; up5k NOFIT: only U1-facing nets allowed)
- [OK] N9: presence pads bonded to GND: ['GND', 'GND', 'GND']; required GND nodes missing=[]
- [OK] N10: n/a (series positions are gw1nz-only)

## negative control (must all FAIL to be meaningful)

- [OK] expected pin12=GND (wrong): 49 pads compared; diffs=['pin 12: board=VCC1V2 expected=GND'] extra=[]
- [OK] parsed board SW1.2 renamed to K2: sockets bad=['SW1']; JP count=19; JP nets == 14 signals+VCC+GND: True; presence refs present: ['JP_GND_DET_T', 'JP_GND_DET_B', 'JP_GND_DET_R']
- [OK] JP_GND_DET_B rebound to isolated net GND_DET_B (pre-fix defect class): N8 ok=False N9 ok=False (both must be False)
