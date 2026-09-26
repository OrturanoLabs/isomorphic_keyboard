# Project libraries

| Library | Source | License |
|---|---|---|
| `Switch_Keyboard_Hotswap_Kailh.pretty/SW_Hotswap_Kailh_MX_1.00u` and `3dmodels/SW_Hotswap_Kailh_MX.*` | [perigoso/keyswitch-kicad-library](https://github.com/perigoso/keyswitch-kicad-library) v2.3 (the 3D model path was changed to `${KIPRJMOD}/../lib/3dmodels/`) | CC-BY-SA 4.0 with a design exception (see `LICENSE-keyswitch-kicad-library-CC-BY-SA.txt`) |

The footprint's origin is the **switch centre**. KiCad's own `SW_Cherry_MX_1.00u_PCB`
has its origin on pin 1, i.e. (+2.54, −5.08) mm from the centre. Keep this in mind when you
swap between the two footprints.
