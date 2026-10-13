import pcbnew
b = pcbnew.LoadBoard('/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/hardware/experiments/simple-tile/discrete-spld/layout/tile_variant_a_4l.kicad_pcb')
for r in ('RPTW','RPLER','RPTEC','RPLDA','CA2','RPRLA','RPBFI','SW2','SW3','SW4'):
    f = b.FindFootprintByReference(r)
    if f:
        p = f.GetPosition()
        print(r, f'{pcbnew.ToMM(p.x):.3f} {pcbnew.ToMM(p.y):.3f}')
