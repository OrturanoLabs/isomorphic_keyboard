#!/usr/bin/env python3
# FPGA-02 bounded manual repair (runs inside flatpak pcbnew runtime).
#  1) remove the one router via-in-chassis-pad at (-7.0143, 22.9493)
#  2) attempt bounded same-net opens repairs: straight or single-L segments
#     on a compatible copper layer, conservative pure-math collision check
#  3) refill all zones, save repaired board, emit JSON report.
# NEVER touches the canonical 2L board. Input/output stay under four-layer/out.
import json, math, sys, os
import traceback, warnings, re  # pre-import: lazy compile of these segfaults
# in the flatpak kicad runtime once pcbnew C++ state is touched (fpga-02 trap)

import pcbnew  # flatpak kicad python

BASE = os.environ.get('MR_BASE') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'out')
SRC = os.path.join(OUT, 'tile_gw1nz_4l_routed.kicad_pcb')
DST = os.path.join(OUT, 'tile_gw1nz_4l_repaired.kicad_pcb')
DRC = os.path.join(OUT, 'tile_gw1nz_4l_routed.drc.json')
REP = os.path.join(OUT, 'manual_repair_report.json')

TRACE_W = 0.2
CLEAR = 0.2
HALF = TRACE_W / 2.0
MAXDIST = 6.0          # mm, straight-line endpoint distance cap
VIA_IN_PAD = (-7.0143, 22.9493)

rep = {'src': SRC, 'dst': DST, 'removed_vias': [], 'pairs': [],
       'n_pairs': 0, 'n_repaired': 0, 'n_skip_dist': 0,
       'n_skip_layer': 0, 'n_skip_mixednet': 0, 'n_skip_item': 0,
       'n_failed_collision': 0}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def seg_pt_dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def seg_seg_dist(p1, p2, q1, q2):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    def on(a, b, c):
        return (min(a[0], b[0]) - 1e-9 <= c[0] <= max(a[0], b[0]) + 1e-9 and
                min(a[1], b[1]) - 1e-9 <= c[1] <= max(a[1], b[1]) + 1e-9)
    d1 = orient(q1, q2, p1); d2 = orient(q1, q2, p2)
    d3 = orient(p1, p2, q1); d4 = orient(p1, p2, q2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(seg_pt_dist(p1, q1, q2), seg_pt_dist(p2, q1, q2),
               seg_pt_dist(q1, p1, p2), seg_pt_dist(q2, p1, p2))


def mm(v):
    return v / 1e6


def main():
    print('M_load', flush=True)
    board = pcbnew.LoadBoard(SRC)
    nets = {}  # netname -> netinfo
    for i in range(board.GetNetCount()):
        ni = board.FindNet(i)
        if ni is not None:
            nets[ni.GetNetname()] = ni

    print('M_preclean', flush=True)
    # obstacle extraction FIRST (swig proxies for pads die after Remove();
    # fpga-02 trap), via-in-pad removed afterwards ----------------------
    pads = []
    for pad in board.GetPads():
        c = pad.GetPosition()
        s = pad.GetSize()
        r = math.hypot(mm(s.x), mm(s.y)) / 2.0   # conservative disk
        ls = set()
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            ls = {pcbnew.F_Cu, pcbnew.B_Cu}
        else:
            if pad.IsOnLayer(pcbnew.F_Cu):
                ls.add(pcbnew.F_Cu)
            if pad.IsOnLayer(pcbnew.B_Cu):
                ls.add(pcbnew.B_Cu)
        pads.append({'kind': 'disk', 'c': (mm(c.x), mm(c.y)), 'r': r,
                     'net': pad.GetNetname(), 'layers': ls,
                     'uuid': pad.m_Uuid.AsString()})
    print('M_ppads', flush=True)
    obstacles = list(pads)
    items_by_uuid = {p['uuid']: ('pad', p) for p in pads}
    to_remove = []
    for t in board.GetTracks():
        a = t.GetStart(); b = t.GetEnd()
        if t.Type() == pcbnew.PCB_VIA_T:
            vp = (mm(a.x), mm(a.y))
            if dist(vp, VIA_IN_PAD) < 0.02:
                rep['removed_vias'].append({'pos': vp, 'net': t.GetNetname()})
                to_remove.append(t)
                continue   # excluded from obstacles once removed
            obstacles.append({'kind': 'disk',
                              'c': vp,
                              'r': mm(t.GetWidth()) / 2.0,
                              'net': t.GetNetname(),
                              'layers': {pcbnew.F_Cu, pcbnew.B_Cu},
                              'uuid': t.m_Uuid.AsString()})
            items_by_uuid[t.m_Uuid.AsString()] = ('via', obstacles[-1])
        else:
            obstacles.append({'kind': 'seg',
                              'a': (mm(a.x), mm(a.y)),
                              'b': (mm(b.x), mm(b.y)),
                              'w': mm(t.GetWidth()),
                              'net': t.GetNetname(),
                              'layers': {t.GetLayer()},
                              'uuid': t.m_Uuid.AsString()})
            items_by_uuid[t.m_Uuid.AsString()] = ('track',
                                            obstacles[-1])
    # zones: snapshot uuid -> net/layers BEFORE removal (proxies go stale)
    zones = {}
    for z in board.Zones():
        ls = set()
        for ln in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            try:
                if z.IsOnLayer(ln):
                    ls.add(ln)
            except Exception:
                pass
        zones[z.m_Uuid.AsString()] = {'net': z.GetNetname(), 'layers': ls}
    # --- 1. remove the via-in-chassis-pad (after extraction) ------------
    for t in to_remove:
        board.Remove(t)
    removed = len(to_remove)
    rep['removed_count'] = removed
    to_remove = None
    print('M_premove removed=%d' % removed, flush=True)

    print('M_ptracks', flush=True)
    def collides(path, layer, net, guard_pts):
        for ob in obstacles:
            if ob['net'] == net:
                continue
            if layer not in ob['layers']:
                continue
            if ob['kind'] == 'disk':
                reff = ob['r'] + CLEAR + HALF
                for i in range(len(path) - 1):
                    # allow touching geometry that owns an endpoint
                    skip = False
                    for g in guard_pts:
                        if dist(ob['c'], g) < ob['r']:
                            skip = True
                    if skip:
                        continue
                    if seg_pt_dist(ob['c'], path[i], path[i + 1]) < reff - 1e-9:
                        return True
            else:
                reff = ob['w'] / 2.0 + CLEAR + HALF
                for i in range(len(path) - 1):
                    skip = False
                    for g in guard_pts:
                        if (dist(ob['a'], g) < 1e-6 or
                                dist(ob['b'], g) < 1e-6):
                            skip = True
                    if skip:
                        continue
                    if seg_seg_dist(path[i], path[i + 1],
                                    ob['a'], ob['b']) < reff - 1e-9:
                        return True
        return False

    print('M_pcolldef', flush=True)
    # --- 3. parse opens, attempt bounded repairs ------------------------
    drc = json.load(open(DRC))
    pairs = []
    for x in drc['unconnected_items']:
        if len(x['items']) != 2:
            continue
        nn = []
        ok = True
        for it in x['items']:
            de = it['description']
            m = re.search(r'\[([^\]]+)\]', de)
            if not m:
                ok = False
                break
            nn.append(m.group(1))
        if not ok or len(set(nn)) != 1:
            rep['n_skip_mixednet'] += 1
            continue
        pairs.append({'net': nn[0], 'items': x['items']})
    rep['n_pairs'] = len(pairs)

    print('M_ppairs', flush=True)
    for pr in pairs:
        net = pr['net']
        uu = [it['uuid'] for it in pr['items']]
        pos = [(it['pos']['x'], it['pos']['y']) for it in pr['items']]
        desc = [it['description'] for it in pr['items']]
        rec = {'net': net, 'uuid': uu, 'desc': [d[:70] for d in desc]}
        rec['dist'] = round(dist(pos[0], pos[1]), 4)
        layers = []
        ok = True
        for u, it, d in zip(uu, pr['items'], desc):
            if d.startswith('Pad') or d.startswith('Track') or d.startswith('Via'):
                if u not in items_by_uuid:
                    ok = False
                    break
                kind, ob = items_by_uuid[u]
                layers.append(ob['layers'])
                if ob['net'] != net:
                    ok = False
                    break
            elif u in zones:  # zone endpoint: connect to its pour edge
                if zones[u]['net'] != net:
                    ok = False
                    break
                layers.append(zones[u]['layers'])
            else:  # unknown item (incl. removed via uuid)
                ok = False
                break
        if not ok:
            rep['n_skip_item'] += 1
            rec['result'] = 'skip_item'
            rep['pairs'].append(rec)
            continue
        if dist(pos[0], pos[1]) > MAXDIST:
            rep['n_skip_dist'] += 1
            rec['result'] = 'skip_dist'
            rep['pairs'].append(rec)
            continue
        common = layers[0] & layers[1]
        if not common:
            rep['n_skip_layer'] += 1
            rec['result'] = 'skip_layer'
            rep['pairs'].append(rec)
            continue
        layer = next(l for l in (pcbnew.F_Cu, pcbnew.B_Cu,
                                 pcbnew.In2_Cu, pcbnew.In1_Cu)
                     if l in common)
        # candidate paths: straight, then two single-L variants
        a, b = pos
        cands = [[a, b],
                 [a, (b[0], a[1]), b],
                 [a, (a[0], b[1]), b]]
        placed = False
        for path in cands:
            # drop degenerate middle point
            path = [p for i, p in enumerate(path)
                    if i == 0 or dist(p, path[i - 1]) > 1e-6]
            if len(path) < 2:
                continue
            if collides(path, layer, net, [a, b]):
                continue
            ni = nets.get(net)
            ncode = ni.GetNetCode() if ni is not None else 0
            for i in range(len(path) - 1):
                seg = pcbnew.PCB_TRACK(board)
                seg.SetStart(pcbnew.VECTOR2I(int(round(path[i][0] * 1e6)),
                                             int(round(path[i][1] * 1e6))))
                seg.SetEnd(pcbnew.VECTOR2I(int(round(path[i + 1][0] * 1e6)),
                                           int(round(path[i + 1][1] * 1e6))))
                seg.SetWidth(int(TRACE_W * 1e6))
                seg.SetLayer(layer)
                seg.SetNetCode(ncode)
                board.Add(seg)
                obstacles.append({'kind': 'seg',
                                  'a': path[i], 'b': path[i + 1],
                                  'w': TRACE_W, 'net': net,
                                  'layers': {layer},
                                  'uuid': 'repair'})
            rec['result'] = 'repaired'
            rec['path'] = path
            rec['layer'] = 'F.Cu' if layer == pcbnew.F_Cu else 'B.Cu'
            placed = True
            break
        if placed:
            rep['n_repaired'] += 1
        else:
            rep['n_failed_collision'] += 1
            rec['result'] = 'failed_collision'
        rep['pairs'].append(rec)

    print('M_ploop', flush=True)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(DST, board)
    print('M_psave', flush=True)
    json.dump(rep, open(REP, 'w'), indent=1)
    print('REPAIR_OK removed=%d pairs=%d repaired=%d coll=%d dist=%d layer=%d item=%d mixed=%d'
          % (removed, rep['n_pairs'], rep['n_repaired'],
             rep['n_failed_collision'], rep['n_skip_dist'],
             rep['n_skip_layer'], rep['n_skip_item'],
             rep['n_skip_mixednet']))


if __name__ == '__main__':
    main()
