# galette 0.3.0 run log (podman image localhost/galette)
golden: assembled clean; results/tile_glue_golden.jed byte-identical to committed hardware/gal/tile_glue.jed (diff clean)
truez:  first attempt failed: 'line 32: tristate control without previous .T' (HX helper needed .T); fixed; assembles clean
truez_npl probe: FAILS as expected: 'line 23: this pin can't be used as output' (pin 13 is input-only; the 22V10 has exactly 10 output macrocells, pins 14-23) -> true-Z T_clk + NPL together do NOT fit; dropping NPL to an external 74LVC1G04 is what makes true-Z possible
fuse listings: golden TCLK OE row (49) empty (always driven, BCLK*/TW+BCLK*/BFIRST in data rows 50-51); truez TCLK OE row 49 carries one feedback literal (HX) with data row 50 = BCLK
