import pcbnew, math
P = '/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/hardware/experiments/simple-tile/discrete-spld/layout/tile_variant_a_4l.kicad_pcb'
b = pcbnew.LoadBoard(P)
outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, False)
items = [p for fp in b.GetFootprints() for p in fp.Pads()] + list(b.GetTracks())
MM = pcbnew.FromMM
def outline_ok(pos, margin=0.6):
    return all(outline.Contains(pcbnew.VECTOR2I(pos.x+MM(dx), pos.y+MM(dy))) for dx,dy in ((margin,0),(-margin,0),(0,margin),(0,-margin)))
for REF, PN in (('UA1','4'),('UA2','4'),('RPTW','2')):
    f = b.FindFootprintByReference(REF); pad = f.FindPadByNumber(PN)
    c = pad.GetPosition(); half = max(pad.GetSizeX(), pad.GetSizeY())/2
    layer = pcbnew.B_Cu
    best = []
    for dist in (0.65, 0.9, 1.2, 1.5, 1.9, 2.4, 2.9, 3.5, 4.2, 5.0, 6.0, 8.0):
        okc = 0; stub_fail = 0; via_fail = 0; out_fail = 0; hole_fail = 0; free = []
        for k in range(48):
            a = 2*math.pi*k/48
            pos = pcbnew.VECTOR2I(int(c.x + math.cos(a)*(half+MM(dist))), int(c.y + math.sin(a)*(half+MM(dist))))
            trk = pcbnew.PCB_TRACK(b); trk.SetStart(c); trk.SetEnd(pos); trk.SetWidth(MM(0.25)); trk.SetLayer(layer)
            via = pcbnew.PCB_VIA(b); via.SetPosition(pos); via.SetWidth(MM(0.6)); via.SetDrill(MM(0.3))
            reason = None
            for it in items:
                same_pad = isinstance(it, pcbnew.PAD) and it.GetNetCode() == pad.GetNetCode()
                if it.GetNetCode() == pad.GetNetCode() and not same_pad: continue
                if same_pad:
                    if it.IsOnLayer(layer) and via.GetEffectiveShape(layer).Collide(it.GetEffectiveShape(layer), MM(0.3)):
                        reason = 'samepad'; break
                    continue
                if it.IsOnLayer(layer) and trk.GetEffectiveShape(layer).Collide(it.GetEffectiveShape(layer), MM(0.2)):
                    reason = 'stub'; break
                hit = False
                for lay in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
                    if it.IsOnLayer(lay) and via.GetEffectiveShape(lay).Collide(it.GetEffectiveShape(lay), MM(0.2)):
                        reason = 'via'; hit = True; break
                if hit: break
            if reason is None:
                for it in items:
                    if isinstance(it, pcbnew.PCB_VIA) or (isinstance(it, pcbnew.PAD) and it.HasHole()):
                        if (it.GetPosition() - pos).EuclideanNorm() < MM(0.55) + (it.GetDrillSizeX() if isinstance(it, pcbnew.PAD) else it.GetDrill())/2 + MM(0.15):
                            reason = 'hole'; break
            if reason is None and not outline_ok(pos):
                reason = 'outline'
            if reason is None:
                free.append(k)
            else:
                if reason == 'stub': stub_fail += 1
                elif reason == 'via': via_fail += 1
                elif reason == 'hole': hole_fail += 1
                elif reason == 'outline': out_fail += 1
                else: pass
        if free:
            best.append((dist, len(free)))
        print(f'{REF}.{PN} dist={dist}: stub={stub_fail} via={via_fail} hole={hole_fail} outline={out_fail} FREE={len(free)}')
    print(f'{REF}.{PN} first free distances: {best[:4]}')
