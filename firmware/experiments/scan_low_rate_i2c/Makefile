# Paths and files
OSS_CAD_SUITE ?=
OSS_CAD_BIN = $(if $(OSS_CAD_SUITE),$(OSS_CAD_SUITE)/bin,$(patsubst %/yosys,%,$(shell command -v yosys)))
DFU_UTIL    = $(OSS_CAD_BIN)/dfu-util

# Project files
TOP_ENTITY  = top
PCF_FILE    = up5k.pcf

# Testbench files
TB_ENTITY   = top_tb
TB_FILE     = top_tb.vhd

# these files are added only for simulation
SIM_FILES   = $(wildcard *sim.vhd)

# Pick up ALL .vhd files in this folder...
ALL_VHDL    = $(wildcard *.vhd)

# ...but exclude the testbench and simulation-only files from synthesis!
VHDL_FILES  = $(filter-out $(TB_FILE) $(SIM_FILES), $(ALL_VHDL))

# pico-ice USB id and serial number
USB_ID      = 1209:b1c0
SERIAL_NUM  = DE64481247531337

# Generated files
JSON_FILE   = hardware.json
ASC_FILE    = hardware.asc
BIN_FILE    = hardware.bin
VCD_FILE    = wave.vcd
GHW_FILE    = wave.ghw

GHDL_FLAGS  = -fsynopsys -fexplicit

# Default target
all: $(BIN_FILE)

# --- SYNTHESIS FLOW ---

$(JSON_FILE): $(VHDL_FILES)
	# Remove the GHDL library to avoid clashes with the simulation
	ghdl --remove
	# Synthesis with yosys
	$(OSS_CAD_BIN)/yosys -m ghdl -p "ghdl $(GHDL_FLAGS) $(VHDL_FILES) -e $(TOP_ENTITY); synth_ice40 -json $(JSON_FILE)"

$(ASC_FILE): $(JSON_FILE) $(PCF_FILE)
	$(OSS_CAD_BIN)/nextpnr-ice40 --up5k --package sg48 --json $(JSON_FILE) --pcf $(PCF_FILE) --asc $(ASC_FILE)

$(BIN_FILE): $(ASC_FILE)
	$(OSS_CAD_BIN)/icepack $(ASC_FILE) $(BIN_FILE)

upload-flash: $(BIN_FILE)
	$(DFU_UTIL) -d $(USB_ID) -S $(SERIAL_NUM) -a 0 -R -D $(BIN_FILE)

upload-ram: $(BIN_FILE)
	$(DFU_UTIL) -d $(USB_ID) -S $(SERIAL_NUM) -a 1 -D $(BIN_FILE)


# --- SIMULATION FLOW ---

# Run the simulation, write the waveform and open GTKWave
sim: $(VHDL_FILES) $(TB_FILE)
	# 1. Remove the old library so it does not clash with yosys
	ghdl --remove
	# 2. Import all files (testbench included)
	ghdl -i $(GHDL_FLAGS) $(VHDL_FILES) $(TB_FILE) $(SIM_FILES)
	# 3. Elaborate the testbench
	ghdl -m $(GHDL_FLAGS) $(TB_ENTITY)
	# 4. Run with a safe time limit (e.g. 5 ms) and write the VCD
	#ghdl -r $(TB_ENTITY) --vcd=$(VCD_FILE) --stop-time=5ms
	ghdl -r $(TB_ENTITY) --wave=$(GHW_FILE) --stop-time=5ms
	# 5. Open GTKWave
	gtkwave $(GHW_FILE)


# Full clean
clean:
	ghdl --remove
	rm -f $(JSON_FILE) $(ASC_FILE) $(BIN_FILE) $(VCD_FILE) $(GHW_FILE) e~*.o work-obj*.cf

.PHONY: all upload-flash upload-ram sim clean
