# Machine-readable pin-level circuit schema (discrete-spld)

JSON documents, one per circuit variant.  All fields are plain data; the
simulator (`tools/sim_tile.py`) and the BOM checker (`tools/bom_check.py`)
consume them.  The schema version is `1`.

```jsonc
{
  "schema": 1,
  "circuit": "variant_a",          // id
  "title": "human name",
  "source":  "how this description was produced (provenance)",

  // device library: behavioural model + pin map per device type
  "devices": {
    "SN74LVC165A": {
      "sim": "ic_74lvc165a",        // model id in tools/pinmodel.py
      "package": "SOIC-16",
      "pins": {"1": "SH/LD", ...},  // pin number (string) -> pin name
      "power": {"VCC": "16", "GND": "8"},
      "datasheet": "url"
    }
  },

  // parts list
  "components": [
    {"ref": "U1", "device": "SN74LVC165A", "value": "SN74LVC165AD",
     "footprint": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
     "unit_price_usd": 0.0, "price_source": "..."}   // optional, BOM step
  ],

  // connectivity: net name -> [[ref, pin], ...]; pins are strings
  "nets": { "B_clk": [["J3","2"],["U1","2"]] },

  // candidate-tile interface (signal -> net), incl. per-edge connector pad
  "interface": {
    "signals": {"T_clk": "T_clk", ...},
    "keys":    {"key0": "K0_N", ...},   // 12 key switch nets
    "edges":   {"top":    {"VCC": ["J2","1"], ...},   // pad-level view
                "bottom": {...}, "left": {...}, "right": {...}}
  },

  // free-form verification hooks consumed by sim_tile.py self-checks
  "checks": {
    "frame": {"order": ["U4.D7..D0", "U3.D7..D0"], "protocol": "see docs/architecture/protocol.md"}
  }
}
```

Rules:

* Nets are exact point-to-point connectivity; a resistor is a component with
  two pins on two nets (the simulator resolves pull-up/down/series as
  electrical devices, no hidden wire merging).
* `interface.edges` mirrors docs/architecture/protocol.md and
  `connectors/out/placement.json` (`J101` left / `J102` top / `J103` bottom /
  `J104` right numbering of rev A is kept so nets stay diff-able).
* Passive-only nets (pull-ups, series resistors) keep rev-A net names
  (`T_clk_drv`, `latch_drv`, `data_drv`, `B_W_drv`, `*_T` rails) where present.
