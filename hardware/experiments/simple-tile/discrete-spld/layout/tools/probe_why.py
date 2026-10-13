import pcbnew, math, sys
sys.path.insert(0, '/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/hardware/experiments/simple-tile/discrete-spld/layout')
b = pcbnew.LoadBoard('/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/hardware/experiments/simple-tile/discrete-spld/layout/tile_variant_a_4l.kicad_pcb')
outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, False)
items = [p for fp in b.GetFootprints() for p in fp.Pads()] + list(b.GetTracks())
MM = pcbnew.FromMM
for ref, pn in (('CA2','1'),('CA8','1'),('RPLER','2'),('RPTW','2'),('RK0','2')):
    f = b.FindFootprintByReference(ref)
    pad = f.FindPadByNumber(pn)
    c = pad.GetPosition(); half = max(pad.GetSizeX(), pad.GetSizeY())/2
    reasons = {}
    for dist in (0.65, 0.9, 1.2, 1.9, 2.9):
        for k in range(24):
            a = 2*math.pi*k/24
            pos = pcbnew.VECTOR2I(int(c.x + math.cos(a)*(half+MM(dist))), int(c.y + math.sin(a)*(half+MM(dist))))
            via = pcbnew.PCB_VIA(b); via.SetPosition(pos); via.SetWidth(MM(0.6)); via.SetDrill(MM(0.3))
            r = None
            for it in items:
                same_pad = isinstance(it, pcbnew.PAD) and it.GetNetCode() == pad.GetNetCode()
                if it.GetNetCode() == pad.GetNetCode() and not same_pad: continue
                if same_pad:
                    if it.IsOnLayer(pcbnew.B_Cu) and via.GetEffectiveShape(pcbnew.B_Cu).Collide(it.GetEffectiveShape(pcbnew.B_Cu), MM(0.3)):
                        r = f'samepad {it.GetParentFootprint().GetReference()}.{it.GetNumber()}'; break
                    continue
                for lay in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
                    if it.IsOnLayer(lay) and via.GetEffectiveShape(lay).Collide(it.GetEffectiveShape(lay), MM(0.2)):
                        r = f'clear {it.GetParentFootprint().GetReference() if isinstance(it, pcbnew.PAD) else "track"}.{it.GetNumber() if isinstance(it, pcbnew.PAD) else ""} net={it.GetNetname()}'; break
                if r: break
            if r is None:
                for it in items:
                    if isinstance(it, pcbnew.PCB_VIA) or (isinstance(it, pcbnew.PAD) and it.HasHole()):
                        if (it.GetPosition() - pos).EuclideanNorm() < MM(0.3+0.25) + (it.GetDrillSizeX() if isinstance(it, pcbnew.PAD) else it.GetDrill())/2 + MM(0.15):
                            r = f'hole {it.GetNetname()}'; break
            if r is None and not all(outline.Contains(pcbnew.VECTOR2I(pos.x+MM(dx), pos.y+MM(dy))) for dx,dy in ((0.6,0),(-0.6,0),(0,0.6),(0,-0.6))):
                r = 'outline'
            reasons[r or 'FREE'] = reasons.get(r or 'FREE', 0) + 1
    print(ref, pn, reasons)
