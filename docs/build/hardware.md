# Working on the hardware

## KiCad project

- Project: `hardware/kicad/tile/isomorphic_tile.kicad_pro`. It is one project that
  contains both the key board and the logic board (see [mechanical](../architecture/mechanical.md)).
- Rev A is saved in the **KiCad 9** format. The project will be migrated to **KiCad 10** in
  a dedicated commit after rev A is merged into `main`. After that, KiCad 9 can no longer
  open it.
- KiCad is installed as a user-level flatpak:

  ```sh
  flatpak install --user flathub org.kicad.KiCad
  tools/kicad-cli.sh version          # kicad-cli wrapper
  ```

  The flatpak sandbox has its own private `/tmp`. Give it access to extra host paths with
  `KICAD_EXTRA_FS=/path/one:/path/two tools/kicad-cli.sh ...`.
- `kicad-cli` rewrites `*.kicad_prl` even for read-only commands. The file is git-ignored.

## Checks before every hardware commit

```sh
# reference design (tag rev-a-prototype) -> production/reference/ref.{kicad_pcb,net}
tools/scripts/export_reference.sh

cd hardware/kicad/tile
K=../../../tools/kicad-cli.sh
KICAD_EXTRA_FS=/tmp $K sch erc --format json -o /tmp/erc.json isomorphic_tile.kicad_sch
KICAD_EXTRA_FS=/tmp $K pcb drc --schematic-parity --format json -o /tmp/drc.json isomorphic_tile.kicad_pcb
$K sch export netlist --format kicadsexpr -o ../../../production/new.net isomorphic_tile.kicad_sch
cd ../../..
tools/scripts/check_invariants.py pcb production/reference/ref.kicad_pcb hardware/kicad/tile/isomorphic_tile.kicad_pcb
tools/scripts/check_invariants.py netlist production/reference/ref.net production/new.net \
    --series <added series resistors> --ignore <added capacitors>
```

(In zsh, `$K` must be a single word such as the script path above. zsh does not split a
variable that holds a whole command line.)

`check_invariants.py` fails when a switch or connector has moved or rotated, when the
outline has changed, or when any logic connection has changed. Series resistors inserted
into a net and decoupling capacitors that were only added are tolerated when you list them.

## Rev-B PCB pipeline (scripted)

The rev-B board was produced from the rev-A board by scripts, so every step can be
repeated and reviewed:

```sh
# 0. rev-B schematic edits (already applied; the script refuses to run twice)
#    hardware/kicad/tile/scripts/revb_schematic.py
# 1. netlist of the current schematic
(cd hardware/kicad/tile && ../../../tools/kicad-cli.sh sch export netlist --format kicadsexpr \
    -o ../../../production/new.net isomorphic_tile.kicad_sch)
# 2. stage 1: footprints from the netlist, 4 layers + inner planes, single-sided placement,
#    fiducials, power fan-out, DSN export -> production/isomorphic_tile.dsn
#    (start from the rev-A board: git show <rev-a commit>:hardware/kicad/tile/isomorphic_tile.kicad_pcb)
flatpak run --filesystem="$PWD" --command=python3 org.kicad.KiCad \
    hardware/kicad/tile/scripts/revb_pcb.py production/new.net
# 3. autoroute (rootless container, about 3 minutes)
podman build -t localhost/freerouting:2.4.1 tools/containers/freerouting
(cd production && podman run --rm --userns=keep-id -e HOME=/tmp -v "$PWD":/work:Z -w /work \
    localhost/freerouting:2.4.1 -de isomorphic_tile.dsn -do isomorphic_tile.ses -mp 40 --gui.enabled=false)
# 4. stage 2: import the routes, ground stitching, outer pours, zone fill, clean-ups
flatpak run --filesystem="$PWD" --command=python3 org.kicad.KiCad \
    hardware/kicad/tile/scripts/revb_pcb.py --route-in "$PWD/production/isomorphic_tile.ses"
```

The autorouted result is a **starting point for review in the KiCad GUI**, not a finished
layout. It passes DRC with 0 errors, 0 unconnected items and 0 schematic-parity issues;
the remaining warnings are silkscreen cosmetics. A human should still review the clock
routing, the silkscreen and the courtyard edits before ordering.

## Behavioural simulation of the tiles

```sh
cd hardware/simulation
../../tools/oss.sh make          # runs tile_tb and tile_tb_2, VCD in build/
make TB=tile_tb wave             # GTKWave on the host
```

## Fabrication records

`hardware/fabrication/rev-a/` holds the gerbers and the BOM of the boards that were
actually manufactured for rev A. Newer outputs are generated into `production/`, which is
git-ignored and published as release assets.
