# Project libraries

| Library | Source | License |
|---|---|---|
| `Switch_Keyboard_Hotswap_Kailh.pretty/SW_Hotswap_Kailh_MX_1.00u` and `3dmodels/SW_Hotswap_Kailh_MX.*` | [perigoso/keyswitch-kicad-library](https://github.com/perigoso/keyswitch-kicad-library) v2.3 (the 3D model path was changed to `${KIPRJMOD}/../lib/3dmodels/`) | CC-BY-SA 4.0 with a design exception (see `LICENSE-keyswitch-kicad-library-CC-BY-SA.txt`) |

The footprint's origin is the **switch centre**. KiCad's own `SW_Cherry_MX_1.00u_PCB`
has its origin on pin 1, i.e. (+2.54, −5.08) mm from the centre. Keep this in mind when you
swap between the two footprints.

`SW_Hotswap_Kailh_MX_1.00u_EdgeTrim` is a local variant: pad 1 is 2.25 mm long instead of
2.55 mm. The inner edge is unchanged and the outer edge is 0.3 mm further in. Without the
trim, the switches next to the stepped outline (SW102/104/106) would have copper 0.06 mm
from the board edge. The switch positions and the outline are frozen, so the pad had to
change instead.
