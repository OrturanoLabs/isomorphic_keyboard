# ==============================================================================
# CONFIGURAZIONE DEI PERCORSI E DEI STRUMENTI
# ==============================================================================
OSS_CAD_BIN = $(HOME)/Pacchetti/oss-cad-suite/bin
DFU_UTIL    = $(OSS_CAD_BIN)/dfu-util

# Cartelle del progetto
SRC_DIR        = src
SIM_DIR        = sim
CONSTR_DIR     = constraints
BUILD_DIR      = build
SIM_BUILD_DIR  = $(SIM_DIR)/build

# File di sintesi
TOP_ENTITY  = top
PCF_FILE    = $(CONSTR_DIR)/up5k.pcf

# --- GESTIONE DINAMICA TESTBENCH ---
TB          ?= top_tb
TB_ENTITY   = $(TB)

# File generati per l'implementazione (in build/)
JSON_FILE   = $(BUILD_DIR)/hardware.json
ASC_FILE    = $(BUILD_DIR)/hardware.asc
BIN_FILE    = $(BUILD_DIR)/hardware.bin

# File generati per la simulazione (in sim/build/)
GHW_FILE    = $(SIM_BUILD_DIR)/$(TB_ENTITY).ghw

# Sorgenti
# VHDL_FILES  = $(wildcard $(SRC_DIR)/*.vhd)
# Prendiamo i file vhdl sorgenti da qualsiasi profondità
VHDL_FILES := $(shell find $(SRC_DIR) -name "*.vhd")
SIM_FILES   = $(wildcard $(SIM_DIR)/*.vhd)

# ID e Seriale della pico-ice
USB_ID      = 1209:b1c0
SERIAL_NUM  = DE64481247531337

# Flag base di GHDL (senza workdir, che gestiamo dinamicamente)
GHDL_FLAGS  = -fsynopsys -fexplicit --std=08

# ==============================================================================
# TARGET PRINCIPALI
# ==============================================================================
all: $(BUILD_DIR) $(BIN_FILE)

# Creazione delle cartelle di output
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(SIM_BUILD_DIR):
	mkdir -p $(SIM_BUILD_DIR)

# --- FLUSSO DI SINTESI HARDWARE ---

$(JSON_FILE): $(VHDL_FILES) | $(BUILD_DIR)
	# Pulisce la libreria specifica dell'implementazione
	ghdl --remove --workdir=$(BUILD_DIR)
	# Sintesi con Yosys usando la cartella build/ come ambiente isolato
	$(OSS_CAD_BIN)/yosys -m ghdl -p "ghdl $(GHDL_FLAGS) --workdir=$(BUILD_DIR) $(VHDL_FILES) -e $(TOP_ENTITY); synth_ice40 -json $(JSON_FILE)"

$(ASC_FILE): $(JSON_FILE) $(PCF_FILE)
	$(OSS_CAD_BIN)/nextpnr-ice40 --up5k --package sg48 --json $(JSON_FILE) --pcf $(PCF_FILE) --asc $(ASC_FILE)

$(BIN_FILE): $(ASC_FILE)
	$(OSS_CAD_BIN)/icepack $(ASC_FILE) $(BIN_FILE)

upload-flash: $(BIN_FILE)
	sudo $(DFU_UTIL) -d $(USB_ID) -S $(SERIAL_NUM) -a 0 -R -D $(BIN_FILE)

upload-ram: $(BIN_FILE)
	sudo $(DFU_UTIL) -d $(USB_ID) -S $(SERIAL_NUM) -a 1 -D $(BIN_FILE)


# --- FLUSSO DI SIMULAZIONE MULTI-TESTBENCH ---

sim: $(VHDL_FILES) $(SIM_FILES) | $(SIM_BUILD_DIR)
	# 1. Pulisce la libreria specifica della simulazione in sim/build/
	ghdl --remove --workdir=$(SIM_BUILD_DIR)
	# 2. Importa tutti i file dentro sim/build/
	ghdl -i $(GHDL_FLAGS) --workdir=$(SIM_BUILD_DIR) $(VHDL_FILES) $(SIM_FILES)
	# 3. Elabora il testbench forzando l'eseguibile finale dentro sim/build/
	ghdl -m $(GHDL_FLAGS) --workdir=$(SIM_BUILD_DIR) -o $(SIM_BUILD_DIR)/$(TB_ENTITY) $(TB_ENTITY)
	# 4. Sposta il file temporaneo e~*.o dentro sim/build/
	@mv -f e~$(TB_ENTITY).o $(SIM_BUILD_DIR)/ 2>/dev/null || true
	# 5. Esegue il binario da sim/build/ salvando il file d'onda lì dentro
	$(SIM_BUILD_DIR)/$(TB_ENTITY) --wave=$(GHW_FILE) --stop-time=5ms

wave:
	# 6. Apre GTKWave
	# gtkwave $(GHW_FILE)
	nohup gtkwave $(GHW_FILE) >/dev/null 2>&1 &


# Pulizia totale
clean:
	ghdl --remove --workdir=$(BUILD_DIR) 2>/dev/null || true
	ghdl --remove --workdir=$(SIM_BUILD_DIR) 2>/dev/null || true
	rm -rf $(BUILD_DIR) $(SIM_BUILD_DIR)

.PHONY: all upload-flash upload-ram sim clean
