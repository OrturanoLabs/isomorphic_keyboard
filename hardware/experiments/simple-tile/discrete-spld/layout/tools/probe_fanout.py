import pcbnew, math
b = pcbnew.LoadBoard('/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/hardware/experiments/simple-tile/discrete-spld/layout/tile_variant_a_4l.kicad_pcb')
outline = pcbnew.SHAPE_POLY_SET()
b.GetBoardPolygonOutlines(outline, False)
for ref, pn in (('CA3','1'), ('RK2','2')):
    f = b.FindFootprintByReference(ref)
    p = f.FindPadByNumber(pn)
    c = p.GetPosition()
    print(ref, pn, 'at', pcbnew.ToMM(c.x), pcbnew.ToMM(c.y), 'net', p.GetNetname(), 'half', max(p.GetSizeX(), p.GetSizeY())/2)
    # neighbours within 2.5 mm: list pads/vias
    for fp in b.GetFootprints():
        for q in fp.Pads():
            d = (q.GetPosition()-c).EuclideanNorm()
            if 0 < pcbnew.ToMM(d) < 2.5:
                print('   pad', fp.GetReference(), q.GetNumber(), q.GetNetname(), f'{pcbnew.ToMM(d):.2f} mm')
    for v in b.GetTracks():
        if v.Type() != pcbnew.PCB_VIA_T: continue
        d = (v.GetPosition()-c).EuclideanNorm()
        if pcbnew.ToMM(d) < 2.5:
            print('   via', v.GetNetname(), f'{pcbnew.ToMM(d):.2f} mm')
    # edge distance
    print('   outline margin test 0.6:', outline.Contains(pcbnew.VECTOR2I(c.x+pcbnew.FromMM(0.6), c.y)), outline.Contains(pcbnew.VECTOR2I(c.x-pcbnew.FromMM(0.6), c.y)), outline.Contains(pcbnew.VECTOR2I(c.x, c.y+pcbnew.FromMM(0.6))), outline.Contains(pcbnew.VECTOR2I(c.x, c.y-pcbnew.FromMM(0.6))))
