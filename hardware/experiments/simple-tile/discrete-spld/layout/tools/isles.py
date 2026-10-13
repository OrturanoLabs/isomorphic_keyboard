import pcbnew
b=pcbnew.LoadBoard('hardware/experiments/simple-tile/discrete-spld/layout/tile_variant_a_routed.kicad_pcb')
b.BuildConnectivity()
def mm(v): return round(pcbnew.ToMM(v),3)
nets=['SWN1','SWN3','latch_drv','W','T_endcol','flag_and','flag_d']
items={}
for fp in b.GetFootprints():
    for p in fp.Pads():
        lays=[]
        if p.IsOnLayer(pcbnew.F_Cu): lays.append(pcbnew.F_Cu)
        if p.IsOnLayer(pcbnew.B_Cu): lays.append(pcbnew.B_Cu)
        for lay in lays:
            items.setdefault(p.GetNetname(),[]).append((f'{fp.GetReference()}.{p.GetNumber()} pad',p,{lay}))
for t in b.GetTracks():
    if t.Type()==pcbnew.PCB_VIA_T:
        lays={pcbnew.F_Cu,pcbnew.B_Cu}
        nm='via'
    else:
        lays={t.GetLayer()}
        nm='trk'
    items.setdefault(t.GetNetname(),[]).append((nm,t,lays))
for n in nets:
    it=items.get(n,[])
    parent=list(range(len(it)))
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,c):
        ra,rb=find(a),find(c)
        if ra!=rb: parent[ra]=rb
    for i in range(len(it)):
        for j in range(i+1,len(it)):
            a,c=it[i],it[j]
            for lay in a[2]&c[2]:
                if a[1].GetEffectiveShape(lay).Collide(c[1].GetEffectiveShape(lay),0):
                    union(i,j);break
    isles={}
    for i in range(len(it)):
        isles.setdefault(find(i),[]).append(i)
    print('=== NET',n,'islands:',len(isles))
    for root,mem in sorted(isles.items(),key=lambda kv:-len(kv[1])):
        desc=[f"{it[k][0]}@({mm(it[k][1].GetPosition().x)},{mm(it[k][1].GetPosition().y)}){'B' if pcbnew.B_Cu in it[k][2] else 'F'}" for k in mem]
        print('  island[%d]:'%len(mem), desc[:8], '...' if len(desc)>8 else '')
for z in b.Zones():
    if z.GetNetname()=='GND' and z.GetLayer()==pcbnew.B_Cu:
        fl=z.GetFilledPolysList(pcbnew.B_Cu)
        print('B.Cu GND zone islands:', fl.OutlineCount())
        for i in range(fl.OutlineCount()):
            bb=fl.Outline(i).BBox()
            print('  island bbox x',mm(bb.GetX()),'..',mm(bb.GetRight()),' y',mm(bb.GetY()),'..',mm(bb.GetBottom()))
