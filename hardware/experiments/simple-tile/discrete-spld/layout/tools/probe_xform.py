import pcbnew, math, re, json
b = pcbnew.LoadBoard('/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/hardware/experiments/simple-tile/discrete-spld/boards/variant_a/tile_variant_a.kicad_pcb')
got={}
for f in b.GetFootprints():
    i=f.GetFPID(); nm=i.GetLibItemName()
    if str(nm).startswith(('UA','RO')):
        p=f.GetPosition()
        got[str(nm)]=dict(x=pcbnew.ToMM(p.x),y=pcbnew.ToMM(p.y),rot=f.GetOrientationDegrees(),
                     pads={pd.GetNumber():(pcbnew.ToMM(pd.GetPosition().x),pcbnew.ToMM(pd.GetPosition().y)) for pd in f.Pads()})
print(json.dumps(got, indent=0))
