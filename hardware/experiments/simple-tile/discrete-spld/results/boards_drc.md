# Board DRC digests (kicad-cli 10.0.6 flatpak, final round-2 state)

Board copies normalize the vendored Kailh courtyard to a closed B-side polygon and drop the front-side square (pure-key front face; documented in tools/board_gen.py). The vendored library files are not touched.

Silkscreen warnings are library-default artifacts (same class as rev-A usage), not errors. Unconnected items are the honest unrouted prototype counts (0 tracks by design).

## boards/variant_a/tile_variant_a.kicad_pcb (sha256:90498129630f71e9...)

* error-severity violations: **0**
* warnings: 218 -> 142x silk_over_copper, 69x silk_overlap, 7x silk_edge_clearance
* unconnected items: 175 pads on 52 distinct nets (placement prototype, 0 tracks routed by design)

## boards/variant_b2/tile_variant_b2.kicad_pcb (sha256:0c910c89d87d32c0...)

* error-severity violations: **0**
* warnings: 187 -> 110x silk_over_copper, 70x silk_overlap, 7x silk_edge_clearance
* unconnected items: 129 pads on 44 distinct nets (placement prototype, 0 tracks routed by design)

