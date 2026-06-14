# Configurazione dei percorsi e dei file
OSS_CAD_BIN = $(HOME)/Pacchetti/oss-cad-suite/bin
DFU_UTIL    = $(OSS_CAD_BIN)/dfu-util

# File del progetto
TOP_ENTITY  = top
PCF_FILE    = up5k.pcf

# File del Testbench
TB_ENTITY   = top_tb
TB_FILE     = top_tb.vhd

# questi file devono essere aggiunti solo in simulazione
SIM_FILES   = $(wildcard *sim.vhd)

# Prende AUTOMATICAMENTE tutti i file .vhd nella cartella...
ALL_VHDL    = $(wildcard *.vhd)

# ...e scarta sia il testbench che i file di simulazione per la sintesi!
VHDL_FILES  = $(filter-out $(TB_FILE) $(SIM_FILES), $(ALL_VHDL))

# ID e Seriale della pico-ice
USB_ID      = 1209:b1c0
SERIAL_NUM  = DE64481247531337

# File generati
JSON_FILE   = hardware.json
ASC_FILE    = hardware.asc
BIN_FILE    = hardware.bin
VCD_FILE    = wave.vcd
GHW_FILE    = wave.ghw

GHDL_FLAGS  = -fsynopsys -fexplicit

# Target principale
all: $(BIN_FILE)

# --- FLUSSO DI SINTESI HARWARE ---

$(JSON_FILE): $(VHDL_FILES)
	# Rimuove la libreria GHDL per evitare conflitti con la simulazione
	ghdl --remove
	# Sintesi con Yosys
	$(OSS_CAD_BIN)/yosys -m ghdl -p "ghdl $(GHDL_FLAGS) $(VHDL_FILES) -e $(TOP_ENTITY); synth_ice40 -json $(JSON_FILE)"

$(ASC_FILE): $(JSON_FILE) $(PCF_FILE)
	$(OSS_CAD_BIN)/nextpnr-ice40 --up5k --package sg48 --json $(JSON_FILE) --pcf $(PCF_FILE) --asc $(ASC_FILE)

$(BIN_FILE): $(ASC_FILE)
	$(OSS_CAD_BIN)/icepack $(ASC_FILE) $(BIN_FILE)

upload-flash: $(BIN_FILE)
	sudo $(DFU_UTIL) -d $(USB_ID) -S $(SERIAL_NUM) -a 0 -R -D $(BIN_FILE)

upload-ram: $(BIN_FILE)
	sudo $(DFU_UTIL) -d $(USB_ID) -S $(SERIAL_NUM) -a 1 -D $(BIN_FILE)


# --- FLUSSO DI SIMULAZIONE ---

# Comando per lanciare la simulazione, generare le onde e aprire GTKWave
sim: $(VHDL_FILES) $(TB_FILE)
	# 1. Pulisce la vecchia libreria per non andare in conflitto con Yosys
	ghdl --remove
	# 2. Importa tutti i file (incluso il testbench)
	ghdl -i $(GHDL_FLAGS) $(VHDL_FILES) $(TB_FILE) $(SIM_FILES)
	# 3. Elabora il testbench
	ghdl -m $(GHDL_FLAGS) $(TB_ENTITY)
	# 4. Esegue con un limite di tempo sicuro (es. 5ms) e genera il VCD
	#ghdl -r $(TB_ENTITY) --vcd=$(VCD_FILE) --stop-time=5ms
	ghdl -r $(TB_ENTITY) --wave=$(GHW_FILE) --stop-time=5ms
	# 5. Apre automaticamente GTKWave
	gtkwave $(GHW_FILE)


# Pulizia totale
clean:
	ghdl --remove
	rm -f $(JSON_FILE) $(ASC_FILE) $(BIN_FILE) $(VCD_FILE) $(GHW_FILE) e~*.o work-obj*.cf

.PHONY: all upload-flash upload-ram sim clean
