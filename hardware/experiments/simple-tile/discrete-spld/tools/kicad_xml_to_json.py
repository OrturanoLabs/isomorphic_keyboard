#!/usr/bin/env python3
"""Convert a kicad-cli 'sch export netlist --format kicadxml' file into the
machine-readable pin-level circuit JSON used by the discrete-spld experiment.

The JSON schema (see ../circuits/schema.md):

{
  "circuit": "<id>",
  "title": "<human name>",
  "source": "<provenance of this description>",
  "components": [{"ref","device","value","footprint","mpn","notes"}],
  "nets": {"<net>": [["<ref>","<pin>"], ...]},      # ref/pin strings
  "interface": {"<signal>": "<net>"}                # candidate tile I/O
}

Only stdlib is used.  The converter keeps every component and net verbatim;
signal-name cleanup (strip leading sheet prefix like '/tile/') is done as an
explicit, reviewable transformation listed in 'renames'.
"""
import json
import sys
import xml.etree.ElementTree as ET

def main(src, dst):
    root = ET.parse(src).getroot()
    design = root.find('design')
    title = design.findtext('source') if design is not None else src
    comps = []
    for c in root.find('components'):
        ref = c.get('ref')
        lib = c.find('libsource')
        device = lib.get('part') if lib is not None else ''
        props = {}
        sheetprops = c.find('propertysheet')
        for prop in c.iter('property'):
            props[prop.get('name')] = prop.text
        fp = c.findtext('footprint') or ''
        comps.append({
            'ref': ref,
            'device': device,
            'value': c.findtext('value') or '',
            'footprint': fp,
            'mpn': props.get('MPN', ''),
            'lib': f"{lib.get('lib')}:{device}" if lib is not None else '',
        })
    nets = {}
    renames = {}
    for n in root.find('nets'):
        name = n.get('name')
        pins = sorted([[p.get('ref'), p.get('pin')]
                       for p in n.findall('node')
                       if p.get('pinfunction') is None or True])
        clean = name.rsplit('/', 1)[-1] if name.startswith('/') else name
        if clean != name:
            renames[name] = clean
        if clean in nets:
            raise SystemExit(f"net name collision after cleanup: {clean}")
        nets[clean] = pins
    out = {
        'circuit': 'reva_reference',
        'title': 'rev-A tile (KiCad export via kicad-cli, hierarchical)',
        'source': f'kicad-cli sch export netlist of {title}',
        'components': comps,
        'nets': nets,
        'interface': {},
        'renames': renames,
    }
    with open(dst, 'w') as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"{dst}: {len(comps)} components, {len(nets)} nets, "
          f"{len(renames)} sheet-prefix renames")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
