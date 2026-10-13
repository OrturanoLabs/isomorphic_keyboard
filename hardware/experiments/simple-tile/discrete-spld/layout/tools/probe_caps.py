import pcbnew, math
b = pcbnew.LoadBoard('/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/hardware/experiments/simple-tile/discrete-spld/boards/variant_a/tile_variant_a.kicad_pcb')
pos = {}
for f in b.GetFootprints():
    r = str(f.GetFPID().GetLibItemName())
    p = f.GetPosition()
    pos[r] = (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
for i in range(1, 10):
    u = pos.get(f'UA{i}'); c = pos.get(f'CA{i}')
    if u and c:
        print(f'UA{i} {u}  CA{i} {c}  d={math.hypot(u[0]-c[0], u[1]-c[1]):.2f}')
print('CB1', pos.get('CB1'))
