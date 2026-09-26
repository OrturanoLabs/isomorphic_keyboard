# SPDX-License-Identifier: GPL-3.0-or-later
#
# iCE40UP5K (pico-ice) firmware: synthesis, place & route, upload and simulation.
#
# Toolchain: OSS CAD Suite (ghdl, yosys + ghdl plugin, nextpnr-ice40, icepack, dfu-util).
#   - tools on PATH:            make
#   - explicit install:         make OSS_CAD_SUITE=$HOME/opt/oss-cad-suite
#   - rootless container:       ../../tools/oss.sh make        (see docs/build/firmware.md)

# ==============================================================================
# TOOLS
# ==============================================================================
OSS_CAD_SUITE ?=
BIN_PREFIX    := $(if $(OSS_CAD_SUITE),$(OSS_CAD_SUITE)/bin/,)
GHDL          := $(BIN_PREFIX)ghdl
YOSYS         := $(BIN_PREFIX)yosys
NEXTPNR       := $(BIN_PREFIX)nextpnr-ice40
ICEPACK       := $(BIN_PREFIX)icepack
DFU_UTIL      := $(BIN_PREFIX)dfu-util
GTKWAVE       := $(BIN_PREFIX)gtkwave

# ==============================================================================
# PROJECT LAYOUT
# ==============================================================================
SRC_DIR       = src
SIM_DIR       = sim
CONSTR_DIR    = constraints
BUILD_DIR     = build
SIM_BUILD_DIR = $(SIM_DIR)/build

TOP_ENTITY    = top
PCF_FILE      = $(CONSTR_DIR)/up5k.pcf

# Testbench to simulate: make sim TB=<entity>
TB           ?= top_tb
TB_ENTITY     = $(TB)
STOP_TIME    ?= 15ms

JSON_FILE     = $(BUILD_DIR)/hardware.json
ASC_FILE      = $(BUILD_DIR)/hardware.asc
BIN_FILE      = $(BUILD_DIR)/hardware.bin
GHW_FILE      = $(SIM_BUILD_DIR)/$(TB_ENTITY).ghw

# All VHDL sources at any depth below src/ (includes the vendored open-logic subset)
VHDL_FILES   := $(shell find $(SRC_DIR) -name "*.vhd" | sort)
SIM_FILES     = $(wildcard $(SIM_DIR)/*.vhd)

# pico-ice USB id; set PICO_ICE_SERIAL when more than one board is attached
USB_ID           = 1209:b1c0
PICO_ICE_SERIAL ?=
DFU_SERIAL       = $(if $(PICO_ICE_SERIAL),-S $(PICO_ICE_SERIAL),)

GHDL_FLAGS    = -fsynopsys -fexplicit --std=08

# ==============================================================================
# SYNTHESIS FLOW
# ==============================================================================
all: $(BIN_FILE)

$(BUILD_DIR) $(SIM_BUILD_DIR):
	mkdir -p $@

$(JSON_FILE): $(VHDL_FILES) | $(BUILD_DIR)
	# Start from a clean implementation library
	$(GHDL) --remove --workdir=$(BUILD_DIR)
	# Synthesise with yosys + ghdl plugin, using build/ as the work library
	$(YOSYS) -m ghdl -p "ghdl $(GHDL_FLAGS) --workdir=$(BUILD_DIR) $(VHDL_FILES) -e $(TOP_ENTITY); synth_ice40 -json $(JSON_FILE)"

$(ASC_FILE): $(JSON_FILE) $(PCF_FILE)
	$(NEXTPNR) --up5k --package sg48 --json $(JSON_FILE) --pcf $(PCF_FILE) --asc $(ASC_FILE)

$(BIN_FILE): $(ASC_FILE)
	$(ICEPACK) $(ASC_FILE) $(BIN_FILE)

# Upload over USB DFU. Needs a udev rule for 1209:b1c0 (docs/build/firmware.md), not sudo.
upload-flash: $(BIN_FILE)
	$(DFU_UTIL) -d $(USB_ID) $(DFU_SERIAL) -a 0 -R -D $(BIN_FILE)

upload-ram: $(BIN_FILE)
	$(DFU_UTIL) -d $(USB_ID) $(DFU_SERIAL) -a 1 -D $(BIN_FILE)

# ==============================================================================
# SIMULATION FLOW
# ==============================================================================
sim: $(VHDL_FILES) $(SIM_FILES) | $(SIM_BUILD_DIR)
	# 1. Clean the simulation library in sim/build/
	$(GHDL) --remove --workdir=$(SIM_BUILD_DIR)
	# 2. Import all sources into sim/build/
	$(GHDL) -i $(GHDL_FLAGS) --workdir=$(SIM_BUILD_DIR) $(VHDL_FILES) $(SIM_FILES)
	# 3. Elaborate the testbench, executable in sim/build/
	$(GHDL) -m $(GHDL_FLAGS) --workdir=$(SIM_BUILD_DIR) -o $(SIM_BUILD_DIR)/$(TB_ENTITY) $(TB_ENTITY)
	# 4. Move the temporary e~*.o into sim/build/
	@mv -f e~$(TB_ENTITY).o $(SIM_BUILD_DIR)/ 2>/dev/null || true
	# 5. Run, writing the waveform into sim/build/
	$(SIM_BUILD_DIR)/$(TB_ENTITY) --wave=$(GHW_FILE) --stop-time=$(STOP_TIME)

wave:
	nohup $(GTKWAVE) $(GHW_FILE) >/dev/null 2>&1 &

clean:
	$(GHDL) --remove --workdir=$(BUILD_DIR) 2>/dev/null || true
	$(GHDL) --remove --workdir=$(SIM_BUILD_DIR) 2>/dev/null || true
	rm -rf $(BUILD_DIR) $(SIM_BUILD_DIR)

.PHONY: all upload-flash upload-ram sim wave clean
