import pcbnew, math
P = '/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/hardware/experiments/simple-tile/discrete-spld/layout/tile_variant_a_4l.kicad_pcb'
b = pcbnew.LoadBoard(P)
items = [p for fp in b.GetFootprints() for p in fp.Pads()] + list(b.GetTracks())
MM = pcbnew.FromMM
REF, PN = 'UA1','4'
f = b.FindFootprintByReference(REF); pad = f.FindPadByNumber(PN)
c = pad.GetPosition(); half = max(pad.GetSizeX(), pad.GetSizeY())/2
layer = pcbnew.B_Cu
print('pad pos', pcbnew.ToMM(c.x), pcbnew.ToMM(c.y), 'net', pad.GetNetname(), 'half', pcbnew.ToMM(half))
dist = 1.5
seen = {}
for k in range(48):
    a = 2*math.pi*k/48
    pos = pcbnew.VECTOR2I(int(c.x + math.cos(a)*(half+MM(dist))), int(c.y + math.sin(a)*(half+MM(dist))))
    trk = pcbnew.PCB_TRACK(b); trk.SetStart(c); trk.SetEnd(pos); trk.SetWidth(MM(0.25)); trk.SetLayer(layer); trk.SetNet(pad.GetNet())
    for it in items:
        same_pad = isinstance(it, pcbnew.PAD) and it.GetNetCode() == pad.GetNetCode()
        if it.GetNetCode() == pad.GetNetCode() and not isinstance(it, pcbnew.PAD): continue
        if same_pad: continue
        if not it.IsOnLayer(layer): continue
        if trk.GetEffectiveShape(layer).Collide(it.GetEffectiveShape(layer), MM(0.2)):
            key = (it.GetParentFootprint().GetReference() if isinstance(it, pcbnew.PAD) else 'track', it.GetNumber() if isinstance(it, pcbnew.PAD) else 0, it.GetNetname())
            if str(key) not in seen:
                seen[str(key)] = (k, pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
for k, v in list(seen.items())[:15]:
    print('collide with', k, 'e.g. at angle k', v)
