# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Behavioural VHDL model of one tile (two '165 shift registers + chaining logic) and
# testbenches with small grids of tiles. Run with GHDL, view with GTKWave.
#   make            # run every testbench
#   make TB=tile_tb run wave
# Container: ../../tools/oss.sh make

GHDL      ?= ghdl
GTKWAVE   ?= gtkwave
STD       ?= 93
BUILD     := build
SRC       := 74hc165.vhdl logic74lib/jkff.vhdl tile.vhdl
TBS       := tile_tb tile_tb_2
TB        ?= tile_tb
STOP_TIME ?= 10us
GFLAGS    := --std=$(STD) -fsynopsys --workdir=$(BUILD)

all: $(TBS:%=run-%)

$(BUILD):
	mkdir -p $@

run-%: | $(BUILD)
	$(GHDL) -a $(GFLAGS) $(SRC) $*.vhdl
	$(GHDL) -e $(GFLAGS) -o $(BUILD)/$* $*
	$(BUILD)/$* --vcd=$(BUILD)/$*.vcd --stop-time=$(STOP_TIME)

run: run-$(TB)

wave:
	nohup $(GTKWAVE) $(BUILD)/$(TB).vcd >/dev/null 2>&1 &

clean:
	rm -rf $(BUILD)

.PHONY: all run wave clean
