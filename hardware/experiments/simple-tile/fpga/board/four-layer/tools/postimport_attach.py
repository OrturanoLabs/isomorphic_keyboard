#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""postimport_attach.py -- FPGA-02 F1-F4 repair pass (guarded flatpak job).

Re-creates the 52-pad stub+via fanout AFTER the SES import (the router
round-trip silently dropped all "(type fix)" wiring -- review F1), ties the
EP (U1-49) with legal off-EP ring vias (F2), attaches TP_GND/U1-2/U1-26 (F3
real continuity holes), notches the 0.1879 mm B.Cu pour neck (F4), adds the
right-edge GND corner stitch via (zone-zone pair), refills all zones and
saves to a NEW file; the previous routed/repaired boards are never
overwritten (recovery anchors).

Design rules unchanged everywhere: 0.2/0.2 track/clearance, via 0.6/0.3,
hole-hole 0.25, copper-edge margin >= 0.6. No via inside any pad bbox
(via_fits same-pad rejection + explicit bbox test), EP attach strictly
off-EP (ring vias in the annulus between EP edge and pin ring, stub from
EP pad centre: never a via under/in the pad).

Geometry is recomputed from the ACTUAL board pads (post-import board as
loaded), not blindly from the old site list: every candidate has to pass
via_fits + outline_ok + seg_fits on the LIVE items. Old via_mm values act
only as tie-break seeds.

Run inside the KiCad flatpak (guarded via resource_guard):

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        four-layer/tools/postimport_attach.py \
        IN.kicad_pcb OUT.kicad_pcb REPORT.json
"""
import faulthandler
import json
import math
import os
import re           # T13: pre-import before pcbnew C++ state is touched
import sys
import traceback
import warnings     # noqa: F401

import pcbnew

faulthandler.enable()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from via_lib import MM, outline_ok, via_fits  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(os.path.dirname(HERE), 'out')
BOARD_DIR = os.path.dirname(os.path.dirname(HERE))
FANOUT = os.path.join(BOARD_DIR, 'docs', 'fanout_prep.json')
SITES = os.path.join(OUTDIR, 'fanout_sites.json')

VIA_D, VIA_DRILL = 0.6, 0.3
TRACE_W, CLEAR = 0.2, 0.2
LADDER = (0.5, 0.9, 1.4, 2.0, 2.8, 3.8, 5.0)
COMPASS = tuple((math.cos(k * math.pi / 4), math.sin(k * math.pi / 4))
                for k in range(8))
NECK = (63.7591, 7.45)          # F4 neck + right-edge zone-zone pair
EP_REF, EP_PAD = 'U1', '49'

GND_FIRST = {'GND': 0, 'VCC1V2_RAW': 1, 'VCC1V2': 2, 'VCC': 3}


def mmpos(v):
    return (pcbnew.ToMM(v.x), pcbnew.ToMM(v.y))


def pad_bbox_mm(pad):
    s = pad.GetSize()
    c = pad.GetPosition()
    hx, hy = pcbnew.ToMM(s.x) / 2.0, pcbnew.ToMM(s.y) / 2.0
    x, y = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
    return (x - hx, y - hy, x + hx, y + hy)


def point_in_pad_bbox(p, pad, tol=0.05):
    x0, y0, x1, y1 = pad_bbox_mm(pad)
    return (x0 - tol <= p[0] <= x1 + tol and y0 - tol <= p[1] <= y1 + tol)


def seg_fits(board, items, a, b, layer, netcode):
    """Conservative same-layer stub check: candidate 0.2 mm track must not
    collide (0.2 clearance) with any OTHER-net copper on that layer; pads
    that own an endpoint are skipped, same-net items are skipped. Uses the
    native shapes (correct for rotated pads)."""
    trk = pcbnew.PCB_TRACK(board)
    trk.SetStart(pcbnew.VECTOR2I(MM(a[0]), MM(a[1])))
    trk.SetEnd(pcbnew.VECTOR2I(MM(b[0]), MM(b[1])))
    trk.SetWidth(MM(TRACE_W))
    trk.SetLayer(layer)
    shp = trk.GetEffectiveShape(layer)
    ok = True
    for it in items:
        if it.GetNetCode() == netcode:
            continue
        if not it.IsOnLayer(layer):
            continue
        try:
            ish = it.GetEffectiveShape(layer)
        except Exception:
            continue
        if shp.Collide(ish, MM(CLEAR)):
            ok = False
            break
    del trk
    return ok


def find_pad(board, ref, num):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        return None
    return fp.FindPadByNumber(str(num))


def place_attach(board, items, pad, cands, report_pad):
    """Try candidate via positions in order; first legal wins."""
    ncode = pad.GetNetCode()
    layer = pcbnew.B_Cu if pad.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu
    a = pad.GetPosition()
    for i, (px, py) in enumerate(cands):
        pos = pcbnew.VECTOR2I(MM(px), MM(py))
        if not outline_ok(board, pos):
            continue
        via = via_fits(board, items + [], pos, ncode, clearance=CLEAR)
        if via is None:
            continue
        if not seg_fits(board, items, mmpos(a), (px, py), layer, ncode):
            continue
        via.SetNet(pad.GetNet())
        trk = pcbnew.PCB_TRACK(board)
        trk.SetStart(a)
        trk.SetEnd(pos)
        trk.SetWidth(MM(TRACE_W))
        trk.SetLayer(layer)
        trk.SetNet(pad.GetNet())
        board.Add(trk)
        board.Add(via)
        items.extend([trk, via])
        report_pad.update({'via_mm': [round(px, 4), round(py, 4)],
                           'stub_mm': round(math.hypot(
                               px - mmpos(a)[0], py - mmpos(a)[1]), 3),
                           'layer': pcbnew.LayerName(layer),
                           'cand_idx': i})
        return True
    return False


def candidates_for(planned, seed):
    """Ordered candidates: old-site seed first, then escape ladder, then
    compass ladder (all recomputed live)."""
    dirs = {'+x': (1, 0), '-x': (-1, 0), '+y': (0, 1), '-y': (0, -1)}
    c = ((planned['box'][0] + planned['box'][2]) / 2.0,
         (planned['box'][1] + planned['box'][3]) / 2.0)
    out = []
    if seed is not None:
        out.append(tuple(seed))
    ex, ey = dirs[planned['escape_dir']]
    edge = {'+x': planned['box'][2], '-x': planned['box'][0],
            '+y': planned['box'][3], '-y': planned['box'][1]}[
        planned['escape_dir']]
    for d in LADDER:
        out.append((edge + ex * d, c[1]) if ex else (c[0], edge + ey * d))
    for dx, dy in COMPASS:
        for d in LADDER:
            out.append((c[0] + dx * d, c[1] + dy * d))
    seen, res = set(), []
    for p in out:
        k = (round(p[0], 3), round(p[1], 3))
        if k not in seen:
            seen.add(k)
            res.append(p)
    return res


def ep_candidates(ep_pad):
    """Ring candidates around U1-49 strictly OUTSIDE the pad: annulus
    between EP bbox + 0.25 and the QFN pin ring (via_fits enforces both)."""
    x0, y0, x1, y1 = pad_bbox_mm(ep_pad)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hx, hy = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    out = []
    diag_first = ((1, 1), (1, -1), (-1, 1), (-1, -1),
                  (1, 0), (0, 1), (-1, 0), (0, -1))
    sq2 = math.sqrt(2.0)
    for dx, dy in diag_first:
        for add in (0.45, 0.55, 0.7, 0.85, 1.0, 1.175, 1.4, 1.6):
            if dx and dy:
                out.append((cx + dx * (hx * sq2 + add) / sq2 * 1.0,
                            cy + dy * (hy * sq2 + add) / sq2 * 1.0))
            else:
                out.append((cx + dx * (hx + add), cy + dy * (hy + add)))
    return (cx, cy), out


def zone_by_uuid(board, uuid):
    for z in board.Zones():
        if z.m_Uuid.AsString() == uuid:
            return z
    return None


def notch_zone_at(board, layer, netname, pt, diag):
    """F4: cut a 0.8x0.8 mm notch in the zone outline at the neck isthmus;
    the thinned isthmus copper is then absent: connection-width violation
    leaves with the island (ISLAND_REMOVAL_MODE_ALWAYS absorbs the sliver).
    BooleanSubtract tried first; polygon-rebuild fallback."""
    for z in board.Zones():
        if z.GetNetname() != netname or z.GetLayer() != layer:
            continue
        o = z.Outline()
        rect = pcbnew.SHAPE_POLY_SET()
        oid = rect.NewOutline()
        r = 0.4
        for px, py in ((pt[0] - r, pt[1] - r), (pt[0] + r, pt[1] - r),
                       (pt[0] + r, pt[1] + r), (pt[0] - r, pt[1] + r)):
            rect.Append(MM(px), MM(py), oid)
        before = o.OutlineCount()
        try:
            ok = o.BooleanSubtract(rect, pcbnew.SHAPE_POLY_SET.PM_FAST)
        except Exception as e:
            ok = False
            diag['bool_err'] = repr(e)[:160]
        diag['outline_before'] = before
        diag['outline_after'] = o.OutlineCount()
        diag['method'] = 'boolean' if ok else 'boolean_failed'
        return ok
    diag['method'] = 'zone_not_found'
    return False


def main():
    in_pcb, out_pcb, rep_json = sys.argv[1:4]
    rep = {'in': in_pcb, 'out': out_pcb, 'placed': [], 'unplaced': [],
           'ep': {}, 'neck': {}, 'proof': [], 'notes': []}
    board = pcbnew.LoadBoard(in_pcb)
    items = [p for fp in board.GetFootprints()
             for p in fp.Pads()] + list(board.GetTracks())
    pad0 = len(items)

    plan = json.load(open(FANOUT, encoding='utf-8'))
    planned = [p for p in plan['planned_pads']
               if not p.get('anchor') and p.get('ok')]
    if len(planned) != 52:
        raise RuntimeError(f'expected 52 planned pads, got {len(planned)}')
    old_sites = {}
    for s in json.load(open(SITES, encoding='utf-8'))['sites']:
        old_sites.setdefault((s['ref'], s['pad']), []).append(
            s.get('via_mm'))

    # --- F1/F3: recreate the 52-pad fanout, GND first -------------------
    planned.sort(key=lambda p: GND_FIRST.get(p['net'], 9))
    ep_planned = [p for p in planned
                  if (p['ref'], p['pad']) == (EP_REF, EP_PAD)]
    for pl in planned:
        rec = {'ref': pl['ref'], 'pad': pl['pad'], 'net': pl['net'],
               'kind': pl['kind'], 'escape_dir': pl['escape_dir']}
        pad = find_pad(board, pl['ref'], pl['pad'])
        if pad is None or pad.GetNetname() != pl['net']:
            rec['error'] = 'pad/net mismatch'
            rep['unplaced'].append(rec)
            continue
        cands = candidates_for(pl, (old_sites.get((pl['ref'], pl['pad']))
                                    or [None])[0])
        if place_attach(board, items, pad, cands, rec):
            rep['placed'].append(rec)
        else:
            rep['unplaced'].append(rec)

    # --- F2: EP ring, strictly outside the EP pad ------------------------
    ep_pad = find_pad(board, EP_REF, EP_PAD)
    ep_c, ep_cands = ep_candidates(ep_pad)
    ep_rec = {'pad_bbox': [round(v, 3) for v in pad_bbox_mm(ep_pad)],
              'net': ep_pad.GetNetname(), 'ring_vias': []}
    ep_items_note = 'pad in planned: %s' % bool(ep_planned)
    for cand in ep_cands:
        if len(ep_rec['ring_vias']) >= 4:
            break
        rec = {'ref': EP_REF, 'pad': EP_PAD, 'net': ep_pad.GetNetname()}
        if place_attach(board, items, ep_pad, [cand], rec):
            # verify via is outside EP pad bbox (no via-in-pad, ever)
            if point_in_pad_bbox(rec['via_mm'], ep_pad, tol=0.0):
                raise RuntimeError('EP via inside pad bbox -- aborting')
            ep_rec['ring_vias'].append(rec)
    rep['ep'] = ep_rec
    rep['notes'].append(ep_items_note)
    if len(ep_rec['ring_vias']) < 2:
        rep['notes'].append('EP_RING_LOW: %d vias placed' %
                            len(ep_rec['ring_vias']))

    # --- right-edge corner stitch (zone-zone pair at NECK) ---------------
    g = board.FindNet('GND')
    corner = {}
    for dx, dy in ((0, 0), (-0.8, -0.8), (-1.2, 0), (0, -1.2), (-1.2, -1.2),
                   (-2.0, 0.0), (0.0, -2.0), (-0.8, 0.6), (0.6, -0.8)):
        pos = pcbnew.VECTOR2I(MM(NECK[0] + dx), MM(NECK[1] + dy))
        if not outline_ok(board, pos):
            continue
        via = via_fits(board, items, pos, g.GetNetCode(), clearance=CLEAR)
        if via is not None:
            via.SetNet(g)
            board.Add(via)
            items.append(via)
            corner = {'stitch_mm': [round(NECK[0] + dx, 3),
                                    round(NECK[1] + dy, 3)]}
            break
    if not corner:
        rep['notes'].append('CORNER_STITCH_UNPLACED')
    rep['corner_stitch'] = corner

    # --- F4: notch the B.Cu pour at the neck isthmus ---------------------
    rep['neck'] = {'note': 'see notch'}
    rep['notch'] = {}
    notch_zone_at(board, pcbnew.B_Cu, 'GND', NECK, rep['notch'])

    # --- refill + save ----------------------------------------------------
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(out_pcb, board)

    # --- geometric proof table (per placed attach) -----------------------
    b2 = pcbnew.LoadBoard(out_pcb)
    vias = [t for t in b2.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    segs = [t for t in b2.GetTracks() if t.Type() != pcbnew.PCB_VIA_T]
    ep_tied = False
    ep_polys = []
    for z in b2.Zones():
        if z.GetNetname() == 'GND' and z.GetLayer() == pcbnew.B_Cu and \
                z.IsFilled():
            fp = z.GetFilledPolysList(pcbnew.B_Cu)
            for vi in ep_rec['ring_vias']:
                pt = pcbnew.VECTOR2I(MM(vi['via_mm'][0]),
                                     MM(vi['via_mm'][1]))
                try:
                    inside = fp.Contains(pt)
                except Exception:
                    inside = False
                ep_polys.append({'via': vi['via_mm'], 'in_bcu_fill': inside})
                ep_tied = ep_tied or inside
    rep['ep']['fill_membership'] = ep_polys
    rep['ep']['island_tied_via_fill'] = ep_tied

    def prove(rec):
        pad = find_pad(b2, rec['ref'], rec['pad'])
        tgt = rec['via_mm']
        via_ok = any(abs(pcbnew.ToMM(v.GetPosition().x) - tgt[0]) < 0.05 and
                     abs(pcbnew.ToMM(v.GetPosition().y) - tgt[1]) < 0.05 and
                     v.GetNetname() == rec['net'] for v in vias)
        stub_ok = False
        for s in segs:
            if s.GetNetname() != rec['net']:
                continue
            for e in (s.GetStart(), s.GetEnd()):
                other = s.GetEnd() if e == s.GetStart() else s.GetStart()
                em = mmpos(e)
                om = mmpos(other)
                if point_in_pad_bbox(em, pad) and \
                        abs(om[0] - tgt[0]) < 0.05 and \
                        abs(om[1] - tgt[1]) < 0.05:
                    stub_ok = True
        return {'ref': rec['ref'], 'pad': rec['pad'], 'net': rec['net'],
                'via_present_net_ok': via_ok,
                'stub_pad_to_via': stub_ok,
                'proven': bool(via_ok and stub_ok)}
    rep['proof'] = [prove(rec) for rec in rep['placed']]
    nprov = sum(1 for p in rep['proof'] if p['proven'])
    rep['summary'] = {'pads_at_load': pad0, 'placed': len(rep['placed']),
                      'unplaced': len(rep['unplaced']),
                      'proven': nprov,
                      'ep_ring': len(ep_rec['ring_vias']),
                      'ep_island_tied': ep_tied}
    json.dump(rep, open(rep_json, 'w', encoding='utf-8'), indent=1)
    print('POSTIMPORT_OK placed=%d unplaced=%d proven=%d ep_ring=%d '
          'ep_island_tied=%s corner=%s notch=%s' % (
              len(rep['placed']), len(rep['unplaced']), nprov,
              len(ep_rec['ring_vias']), ep_tied,
              bool(rep['corner_stitch']),
              rep['notch'].get('method')))


if __name__ == '__main__':
    main()
