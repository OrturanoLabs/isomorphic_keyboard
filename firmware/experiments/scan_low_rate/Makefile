# Configurazione dei percorsi e dei file
OSS_CAD_BIN = $(HOME)/Pacchetti/oss-cad-suite/bin
DFU_UTIL    = $(OSS_CAD_BIN)/dfu-util

# File del progetto
TOP_ENTITY  = top
VHDL_FILE   = top.vhd
DEP1 	    = i2c_master.vhd
PCF_FILE    = up5k.pcf

# ID e Seriale della pico-ice (inserisci i tuoi dati)
USB_ID      = 1209:b1c0
SERIAL_NUM  = DE64481247531337

# File generati dalla toolchain
JSON_FILE   = hardware.json
ASC_FILE    = hardware.asc
BIN_FILE    = hardware.bin

# Target principale: compila tutto fino al bitstream
all: $(BIN_FILE)

# 1. Sintesi (dipende dal file VHDL)
$(JSON_FILE): $(VHDL_FILE)
	$(OSS_CAD_BIN)/yosys -m ghdl -p "ghdl -fsynopsys -fexplicit $(DEP1) $(VHDL_FILE) -e $(TOP_ENTITY); synth_ice40 -json $(JSON_FILE)"

# 2. Place & Route (dipende dal JSON della sintesi e dal PCF)
$(ASC_FILE): $(JSON_FILE) $(PCF_FILE)
	$(OSS_CAD_BIN)/nextpnr-ice40 --up5k --package sg48 --json $(JSON_FILE) --pcf $(PCF_FILE) --asc $(ASC_FILE)

# 3. Generazione Bitstream (dipende dall'ASC del P&R)
$(BIN_FILE): $(ASC_FILE)
	$(OSS_CAD_BIN)/icepack $(ASC_FILE) $(BIN_FILE)

# Target per caricare nella Flash permanente (alt 0)
upload-flash: $(BIN_FILE)
	sudo $(DFU_UTIL) -d $(USB_ID) -S $(SERIAL_NUM) -a 0 -R -D $(BIN_FILE)

# Target per caricare al volo nella CRAM volatile (alt 1)
upload-ram: $(BIN_FILE)
	sudo $(DFU_UTIL) -d $(USB_ID) -S $(SERIAL_NUM) -a 1 -D $(BIN_FILE)

# Pulizia dei file temporanei generati
clean:
	rm -f $(JSON_FILE) $(ASC_FILE) $(BIN_FILE) e~*.o work-obj93.cf

.PHONY: all upload-flash upload-ram clean
