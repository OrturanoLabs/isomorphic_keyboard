# SPDX-License-Identifier: CERN-OHL-S-2.0
# Self-checking glue-equivalence experiments for the simple-tile candidates.
# Run inside the OSS CAD Suite container from the repo root:
#   cd hardware/experiments/simple-tile/logic/equivalence
#   ../../../../tools/oss.sh make
# or, with ghdl 7 installed on the host, plain `make`.

GHDL    ?= ghdl
STD     ?= 08
BUILD   := results/build
SRC     := ../../../../simulation/74hc165.vhdl \
           ref_glue.vhdl gal_glue.vhdl gal_glue_v2.vhdl \
           ../cpld/tile_full.vhdl tile_wrappers.vhdl
GFLAGS  := --std=$(STD) -fsynopsys --workdir=$(BUILD)

all: equiv hazard

$(BUILD):
	mkdir -p $(BUILD)

equiv: | $(BUILD)
	$(GHDL) -a $(GFLAGS) $(SRC) glue_equiv_tb.vhdl
	$(GHDL) -e $(GFLAGS) -o $(BUILD)/glue_equiv_tb glue_equiv_tb
	$(BUILD)/glue_equiv_tb

hazard: | $(BUILD)
	$(GHDL) -a $(GFLAGS) $(SRC) hazard_tb.vhdl
	$(GHDL) -e $(GFLAGS) -o $(BUILD)/hazard_tb hazard_tb
	$(BUILD)/hazard_tb

clean:
	rm -rf results

.PHONY: all equiv hazard clean
