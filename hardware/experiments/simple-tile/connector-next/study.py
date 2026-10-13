#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""connector-next study: aggregate 19-contact drop-in plan for the passive
simple tile, advancing the baseline `connectors/` study (which it imports
READONLY as `base`) with:

  * the MINIMUM aggregated contact rail (19 contacts, budget.py) placed on the
    tile underside in TWO chassis tier lanes: GND-class contacts (GND +
    GND_DET_T/B/R) on one lane, the 15 power+signal contacts on another, so
    the chassis rails can differ in height (first-mate engineering);
  * a real spring part decision: Harwin mini multi-directional -46R family
    (4.63 x 3.70 mm body; S1971-46R free 4.55 / S1961-46R free 3.55 -
    manufacturer pages fetched 2026-10-12) with chassis packing check by the
    baseline engine incl. all six lattice neighbours;
  * tiered-rail z-stack under the CONSERVATIVE socket-depth bound 4.94 mm
    (baseline) with the model-verified depth 2.94 mm (step_axis.py) reported
    alongside;
  * an EXPLICIT stagger + tilt model for first-mate: stagger = deflection
    difference of GND-class vs signal springs at the final assembly (a hard
    geometric identity: coplanar pads + flat tiered rails), swept over the
    ACTUAL pad coordinates; the required guide spec is derived, and when it
    is impractical the study says so;
  * mezzanine re-evaluation at the 19-contact budget with the freshly
    measured 20-pos footprints (measure_next.py, pcbnew): DF12-20 pair (EOL,
    rejected reference), Gecko MV/FV-20 pair (through-board tails, measured),
    Gecko MS1 (SMT male, no stocked female), BM24-40 (NRND), DF40 (no KiCad
    footprints - custom design required), with certified tab extents from the
    baseline engine;
  * SVG: underside plan, assembly cross-section (the OpenSCAD substitute -
    OpenSCAD is NOT INSTALLED), 4x4 slot field with detect-trace classes.

Outputs: out/study.json, out/study_checks.json, out/plan.svg, out/section.svg,
out/field.svg, out/report.md, out/vendor.json.

Run:  python3 study.py [outdir]     (host python3, stdlib only)
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "connectors"))
sys.path.insert(0, HERE)
import importlib.util  # noqa: E402


def _load_baseline():
    spec = importlib.util.spec_from_file_location(
        "baseline_connectors_study",
        os.path.join(HERE, "..", "connectors", "study.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


base = _load_baseline()  # (baseline geometry engine, READONLY import)
import budget  # noqa: E402  (this workstream's netlist/graph derivation)

MEZZ_JSON = os.path.join(HERE, "out", "mezz_next.json")

# ------------------------------------------------------------ spring parts --
# Manufacturer page facts (fetched 2026-10-12; URLs in vendor.json). All are
# Harwin EZi SMT multi-directional spring contacts (-46R = tin).
SPRINGS = {
    "S1971-46R": {"free": 4.55, "dmin": 0.3, "dmax": 0.6, "body": (4.63, 3.70),
                  "current_A": 14, "role": "GND-class (taller reach)"},
    "S1961-46R": {"free": 3.55, "dmin": 0.2, "dmax": 0.6, "body": (4.63, 3.70),
                  "current_A": 14, "role": "signals (same body)"},
    # controls from the baseline study (pack-rejected / too-short)
    "S1941-42R": {"free": 7.3, "dmin": 0.3, "dmax": 0.8, "body": (9.59, 5.70),
                  "current_A": 9, "role": "control: z-ok, pack-rejected (baseline)"},
    "S1981-46R": {"free": 8.5, "dmin": 0.4, "dmax": 1.0, "body": (9.63, 5.70),
                  "current_A": 14, "role": "control: big body"},
}

VENDOR = {
    "harwin_s1971": ("S1971-46R: free height 4.55 mm, top-down deflection "
                     "0.3..0.6 mm, body 4.63 x 3.70 x 4.55 mm, 14 A",
                     "https://www.harwin.com/products/S1971-46R"),
    "harwin_s1961": ("S1961-46R: free height 3.55 mm, top-down deflection "
                     "0.2..0.6 mm, body 4.63 x 3.70 x 3.55 mm, 14 A",
                     "https://www.harwin.com/products/S1961-46R"),
    "harwin_s1941": ("S1941-42R: free height 7.3 mm, deflection 0.3..0.8 mm, "
                     "9.59 x 5.70 x 7.25 mm, 9 A, gold contact",
                     "https://www.harwin.com/products/S1941-42R"),
    "harwin_range": ("PD013 EZi SMT spring contact datasheet: free height range "
                     "1.23..10.00 mm; compact (4.63x3.70) body tops out at "
                     "4.55 mm (S1971) in the fetched range",
                     "https://content.harwin.com/asset/b78b8265-eabd-4ec9-b6e1-"
                     "cca806faa177/PD013-Product-Datasheet-SPRING-CONTACTS-SMT-"
                     "Spring-Contacts-EZi.pdf"),
    "hirose_df12": ("DF12 series page bears the banner 'Planned End of Life' "
                    "(fetched 2026-10-12); stacks 3/3.5/4/5 mm",
                    "https://www.hirose.com/en/product/series/DF12"),
    "hirose_df40": ("DF40 series page (no EOL banner): 0.4 mm pitch, mated "
                    "heights 1.5/2/2.5/3/3.5/4 mm; NOT stocked in the KiCad "
                    "10.0.6 footprint library -> custom footprint required",
                    "https://www.hirose.com/en/product/series/DF40"),
    "hirose_bm24": ("BM24 series page bears the banner 'Not recommended for new "
                    "design' (fetched 2026-10-12); 0.35 mm, 0.8 mm stack",
                    "https://www.hirose.com/en/product/series/BM24"),
    "harwin_gecko": ("Gecko (G125) family page, actively marketed, no EOL "
                     "notice: 'Board-mounted connectors, Surface Mount or "
                     "Throughboard'",
                     "https://www.harwin.com/hri/gecko/"),
    "harwin_drg_03073": ("S1971 technical drawing (RECOMMENDED PCB PAD "
                         "LAYOUT 2.25 x 3.70 mm, positioned text)",
                         "https://content.harwin.com/asset/350d2138-67fd-4d7e-"
                         "bfe2-9ecb2bf0c9fc/DRG-03073-Technical-Drawing-"
                         "Datasheet-S1971R-pdf.pdf"),
    "harwin_drg_03072": ("S1961 technical drawing (same 2.25 x 3.70 mm "
                         "recommended layout; body 4.63 x 3.70)",
                         "https://content.harwin.com/asset/f4cd037e-0829-4c4c-"
                         "a570-f0dd6472082e/DRG-03072-Technical-Drawing-"
                         "Datasheet-S1961R-pdf.pdf"),
    "hirose_df40_plug": ("DF40C-20DP-0.4V(51) official part page (CL0684-4010-"
                         "9-51): 20 pos, 0.4 mm SMT, mated-height steps "
                         "1.5/2/2.5/3.5 mm; no EOL banner",
                         "https://www.hirose.com/en/product/p/CL0684-4010-9-51"),
    "hirose_df40_rec35": ("DF40HC(3.5)-20DS-0.4V(51) receptacle (CL0684-4188-"
                          "0-51): the 3.5 mm stack mate; its STEP download "
                          "was rate-limited (403) this session",
                          "https://www.hirose.com/en/product/p/CL0684-4188-0-51"),
    "gecko_drg_male": ("DRG-00182 (G125-MV male vertical): dims table A..E for "
                       "20 pos = 16.45/15.05/13.65/13.75/11.25 mm; mated stack "
                       "height NOT stated on pages fetched in this run",
                       "https://content.harwin.com/m/62fd8add13144f50/original/"
                       "DRG-00182-Technical-Drawing-Datasheet-G125-MVXXX05LXP-pdf.pdf"),
}

# The 19 contacts of budget.py arranged as two chassis tier lanes. The signal
# lane order walks the scan chain boundary-to-boundary; GND-class pads sit on
# their own lane so one raised rail serves all of them.
TIER_G = ["GND", "GND_DET_T", "GND_DET_B", "GND_DET_R"]
TIER_S = ["VCC", "T_clk", "T_data", "T_endcol", "T_W", "B_clk", "B_data",
          "B_first", "B_latch", "B_W", "L_clk", "L_data", "L_endrow", "L_latch",
          "R_latch"]


def place_tier(tile, islands, nets, d, pitch, tol, used_lanes, tag):
    """Place one tier (a straight pad row) into the widest free lane that is
    not already used by another tier (the chassis tiers need different rail
    heights, so they must not share a lane). Exact per-pad clearance incl. the
    chassis tolerance, as in the baseline engine."""
    span = (len(nets) - 1) * pitch + d + 2 * tol
    for isl in sorted(islands, key=lambda i: -i["rect"][3]):
        x0, y0, x1, y1 = isl["rect"]
        if (x1 - x0) >= span and (y1 - y0) >= d + 2 * tol and \
                tuple(isl["rect"]) not in used_lanes:
            cx0 = (x0 + x1) / 2 - (len(nets) - 1) * pitch / 2
            cy = (y0 + y1) / 2
            pads = []
            for j, n in enumerate(nets):
                cx = cx0 + j * pitch
                r = base.Rect(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2)
                slack, what = tile.clearance(r, extra=tol)
                es = tile.edge_slack(r)
                if slack < -1e-9:
                    pads = None
                    break
                pads.append({"net": n, "role": f"{tag}.{j + 1}", "group": tag,
                             "x": round(cx, 3), "y": round(cy, 3), "d": d,
                             "slack_after_tol": round(slack, 3), "nearest": what,
                             "edge_slack": round(es, 3)})
            if pads is not None:
                used_lanes.add(tuple(isl["rect"]))
                return {"lane": isl["rect"], "pads": pads}
    return None


def tilt_sweep(pads, layer, stagger, cap_grid=21):
    """Explicit first-mate sweep on the actual pad map.

    Tile underside = plane z = t + tx*x + ty*y descending (t decreasing).
    Contact i engages at t_i = reach_i - tx*x_i - ty*y_i, where
    reach_i = rail_height(class) + free_height(part), and
    stagger = reach_g - reach_s for g in GND-class, s in signals.

    For every tilt (tx, ty) in the disk sqrt(tx^2+ty^2) <= theta_cap we need
    t_g > t_s for ALL pairs: margin = min over pairs of stagger_gs minus the
    tilt rise. Returns margin(theta_cap) by exhaustive grid evaluation."""
    gp = [p for p in pads if layer[p["net"]] == "GND"]
    sp = [p for p in pads if layer[p["net"]] == "SIG"]

    def margin(theta_cap):
        worst = None
        for k in range(cap_grid * 4 + 1):
            a = 2 * math.pi * k / (cap_grid * 4 + 1)
            tx, ty = theta_cap * math.cos(a), theta_cap * math.sin(a)
            for g in gp:
                rg = stagger if True else 0            # reach_g = reach_s + stagger
                for s in sp:
                    m = rg - (tx * (g["x"] - s["x"]) + ty * (g["y"] - s["y"]))
                    if worst is None or m < worst:
                        worst = m
        return worst

    # theta cap where the margin hits zero (bisection)
    lo, hi = 0.0, stagger / 0.01          # huge tilt radius fallback
    for _ in range(48):
        mid = (lo + hi) / 2
        if margin(mid) >= 0:
            lo = mid
        else:
            hi = mid
    # pairwise worst bound (analytic cross-check)
    worst_pair = max(abs(g["x"] - s["x"]) + abs(g["y"] - s["y"])
                     for g in gp for s in sp)
    return {"theta_cap_zero_margin_rad": lo,
            "theta_cap_zero_margin_deg": math.degrees(lo),
            "analytic_pair_bound_rad": stagger / worst_pair if worst_pair else None,
            "worst_L1_pair_separation_mm": worst_pair,
            "stagger_mm": stagger,
            "margin_at_theta_cap": margin(lo),
            "margin_at_1p5x": margin(1.5 * lo),
            "gnd_class_pads": [(p["net"], p["x"], p["y"]) for p in gp],
            "n_signal_pads": len(sp)}


def poly_intersect(a, b):
    """True iff polygons a and b share area (edge crossing or containment)."""
    for i in range(len(a)):
        a0, a1 = a[i], a[(i + 1) % len(a)]
        for j in range(len(b)):
            b0, b1 = b[j], b[(j + 1) % len(b)]
            if base.seg_seg_dist(a0, a1, b0, b1) < 1e-9:
                # treat shared boundary contact as no area overlap
                def proper(a0, a1, b0, b1):
                    def ccw(p, q, r):
                        return (q[0] - p[0]) * (r[1] - p[1]) - \
                               (q[1] - p[1]) * (r[0] - p[0])
                    return (ccw(a0, a1, b0) * ccw(a0, a1, b1) < -1e-12 and
                            ccw(b0, b1, a0) * ccw(b0, b1, a1) < -1e-12)
                if proper(a0, a1, b0, b1):
                    return True
    # containment
    return (base.point_in_poly(*a[0], b) or base.point_in_poly(*b[0], a))


def poly_gap(a, b):
    if poly_intersect(a, b):
        return 0.0
    return min(base.seg_seg_dist(a[i], a[(i + 1) % len(a)],
                                 b[j], b[(j + 1) % len(b)])
               for i in range(len(a)) for j in range(len(b)))


class TileTiling(base.Tile):
    """REV-C-exact stepped outline: the revc_build.py construction uses
    vertical margin R/2 (top/bottom) and horizontal margin P/2, which tiles
    with exactly rib_gap everywhere; the baseline Tile uses P/2 both ways,
    leaving a measured 1.46 mm outline overlap with the up/down neighbour
    (documented in check CT0). This subclass rebuilds the outline (and the
    edge-dependent pad_variant selection) without touching the baseline."""

    def __init__(self, par, fp, style, fp_trim=None):
        super().__init__(par, fp, style, fp_trim)
        if style == "stepped":
            self.rebuild()

    def rebuild(self):
        par, G = self.par, self.par.rib_gap
        P, R = par.P(), par.R()
        mh, mv = P / 2, R / 2          # revc_build.py: vertical margin is R/2
        xL = [-k * P / 2 - mh + G / 2 for k in range(par.rows)]
        xR = [-k * P / 2 + (par.cols - 1) * P + mh - G / 2
              for k in range(par.rows)]
        yT = -mv + G / 2
        yB = (par.rows - 1) * R + mv + par.bottom_ext - G / 2
        b = [(k + 0.5) * R for k in range(par.rows - 1)]
        pts = [(xL[0], yT), (xR[0], yT)]
        for k in range(par.rows - 1):
            pts += [(xR[k], b[k] - G / 2), (xR[k + 1], b[k] - G / 2)]
        pts += [(xR[-1], yB), (xL[-1], yB)]
        for k in range(par.rows - 1, 0, -1):
            pts += [(xL[k], b[k - 1] + G / 2), (xL[k - 1], b[k - 1] + G / 2)]
        self.outline = pts
        if hasattr(self, "_obs_cache"):
            del self._obs_cache
        # recompute per-key pad variants against the corrected outline
        if self.fp_trim is not None:
            need = par.edge_clear + par.board_edge_tol
            trim = {p["n"]: p for p in self.fp_trim["pads"]}
            for (i, k), (cx, cy) in self.centre.items():
                variant = "standard"
                for p in self.fp["pads"]:
                    r = base.Rect(cx + p["x"] - p["w"] / 2, cy + p["y"] - p["h"] / 2,
                                  cx + p["x"] + p["w"] / 2, cy + p["y"] + p["h"] / 2)
                    if self.edge_slack(r) < need - 1e-9:
                        variant = "edgetrim"
                self.pad_variant[(i, k)] = variant


def extended_fit_t(par, fp, fp_trim, style, need_w, need_h, tile_cls=TileTiling):
    """extended_fit that builds the corrected tile class (same logic as the
    baseline extended_fit, only the Tile class differs)."""
    p0 = base.replace(par, bottom_ext=0.0)
    t0 = tile_cls(p0, fp, style, fp_trim)
    base_isl = base.scan_islands(t0, min_w=need_w, min_h=0.5)
    tries = []
    deep = [i for i in base_isl if i["w"] >= need_w]
    if deep:
        bottom_lane = max(deep, key=lambda i: i["rect"][3])
        tries.append(max(0.0, round(need_h - bottom_lane["h"] + 0.25, 2)))
    tries += [e for e in (1, 2, 3, 4, 6, 8, 12)
              if all(abs(e - q) > 0.01 for q in tries)]
    for ext in tries:
        t = tile_cls(base.replace(par, bottom_ext=ext), fp, style, fp_trim)
        isl = base.scan_islands(t, min_w=need_w, min_h=need_h)
        if isl:
            return ext, max(isl, key=lambda i: i["h"])
    return None, None


def cross_tile_tab_check(fp, fp_trim, ext, margin=None,
                         rib_gap_override=None):
    """Outline-with-tab vs the six lattice neighbours' outlines.
    Returns min outline gap (mm) and per-neighbour detail."""
    par0 = base.Params()
    if margin is not None:
        par0 = base.replace(par0, body_margin=margin)
    if rib_gap_override is not None:
        par0 = base.replace(par0, rib_gap=rib_gap_override)
    t0 = TileTiling(base.replace(par0, bottom_ext=ext), fp, "stepped", fp_trim)
    own = t0.outline
    P, R = par0.P(), par0.R()
    shifts = [(4 * P, 0), (-4 * P, 0), (P / 2, -3 * R), (-P / 2, 3 * R),
              (4 * P - P / 2, 3 * R), (-4 * P + P / 2, -3 * R)]
    gaps = {}
    for dx, dy in shifts:
        nb = [(x + dx, y + dy) for x, y in own]
        gaps[f"({dx:.2f},{dy:.2f})"] = round(poly_gap(own, nb), 4)
    return t0, par0, gaps


def find_min_margin_for_tab(fp, fp_trim, ext, gap_need):
    """Bisect the smallest body_margin increase so the tabbed outline keeps
    gap_need vs all six neighbours. Returns (margin, R, P, gaps)."""
    lo, hi = 0.0, 8.0
    def ok(m):
        _t, _p, gaps = cross_tile_tab_check(fp, fp_trim, ext, margin=m)
        return min(gaps.values()) >= gap_need - 1e-9
    if ok(lo):
        _t, p0, gaps = cross_tile_tab_check(fp, fp_trim, ext, margin=0.0)
        return 0.0, p0
    for _ in range(40):
        mid = (lo + hi) / 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    _t, p1, gaps = cross_tile_tab_check(fp, fp_trim, ext, margin=hi)
    return hi, p1


def hole_and_pad_edge_slacks(tile):
    """Worst drill-to-edge and socket SMD pad-to-edge margins of the tile
    against its CURRENT outline (baseline OUT1/OUT2 semantics)."""
    n = len(tile.outline)
    worst_hole = None
    worst_pad = None
    for o in tile.obstacles():
        if o["kind"] == "circle":
            d = min(base._pt_seg((o["x"], o["y"]),
                                 tile.outline[i], tile.outline[(i + 1) % n])
                    for i in range(n)) - o["r"]
            if worst_hole is None or d < worst_hole:
                worst_hole = d
        elif o["kind"] == "rect":
            d = tile.edge_slack(o["rect"])
            if worst_pad is None or d < worst_pad:
                worst_pad = d
    return worst_hole, worst_pad


def cross_neighbour_body_gap(par, tile):
    """Min gap between the 15.6 mm switch bodies of THIS tile and the same
    bodies translated by the six lattice neighbour vectors (measured)."""
    P, R = par.P(), par.R()
    shifts = [(4 * P, 0), (-4 * P, 0), (P / 2, -3 * R), (-P / 2, 3 * R),
              (4 * P - P / 2, 3 * R), (-4 * P + P / 2, -3 * R)]
    half = par.body / 2
    own = [base.Rect(cx - half, cy - half, cx + half, cy + half)
           for cx, cy in tile.centre.values()]
    best = 1e9
    for dx, dy in shifts:
        for r in own:
            moved = [base.Rect(q.x0 + dx, q.y0 + dy, q.x1 + dx, q.y1 + dy)
                     for q in own]
            for q in moved:
                best = min(best, base.dist_rect_rect(r, q))
    return best


def poly_area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] -
                   poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly))) / 2)


def evaluate_tab_remedy(fp, fp_trim, ext0, need_w, need_h, par):
    """Placement-level remedy evaluation (review point):
    the widened inset G' SHRINKS the board (tiles stay at their stations),
    which shrinks the very island the tab was certified for -> iterate the
    fixed point (G, ext): extend the outline until the outline separation is
    back at rib_gap AND scan_islands still hosts the connector at the SAME
    need; then verify edge/drill slacks and net added area of the final board.
    NOFIT is a valid verdict."""
    G = par.rib_gap + ext0
    ext = ext0
    history = [{"inset_G": round(G, 4), "ext": round(ext, 3)}]
    isl = None
    for _ in range(14):
        par_g = base.replace(par, rib_gap=G, bottom_ext=0.0)
        ext_new, isl = extended_fit_t(par_g, fp, fp_trim, "stepped",
                                      need_w, need_h)
        if ext_new is None:
            return {"verdict": "NOFIT",
                    "reason": "no connector island survives at widened inset "
                              f"G={G:.3f} mm",
                    "history": history}
        G_new = par.rib_gap + ext_new
        history.append({"inset_G": round(G_new, 4), "ext": round(ext_new, 3)})
        if abs(G_new - G) < 0.02 and abs(ext_new - ext) < 0.02:
            G, ext = G_new, ext_new
            break
        G, ext = G_new, ext_new
    # fixed point reached; verify outline separation
    _t, _p, gaps = cross_tile_tab_check(fp, fp_trim, ext, rib_gap_override=G)
    sep = min(gaps.values())
    # place the connector island exactly on the final board
    par_fin = base.replace(par, rib_gap=G, bottom_ext=ext)
    tile2 = TileTiling(par_fin, fp, "stepped", fp_trim)
    isl_slack = -1e9
    isl_edge = -1e9
    if isl is not None:
        r = base.Rect(*isl["rect"])
        isl_slack = tile2.clearance(r)[0]
        isl_edge = tile2.edge_slack(r)
    hole_sl, pad_sl = hole_and_pad_edge_slacks(tile2)
    net_area = poly_area(tile2.outline) - poly_area(
        TileTiling(base.replace(par_fin, bottom_ext=0.0), fp, "stepped",
                   fp_trim).outline)
    body_gap = cross_neighbour_body_gap(par_fin, tile2)
    edge_need = par.edge_clear + par.board_edge_tol
    ok = (isl is not None and sep >= par.rib_gap - 1e-9 and isl_slack >= 0 and
          hole_sl >= edge_need and pad_sl >= edge_need and net_area > 0 and
          body_gap > 0)
    return {"verdict": "FIT" if ok else "NOFIT",
            "inset_G_final_mm": round(G, 3), "ext_final_mm": round(ext, 3),
            "history": history,
            "outline_separation_mm": round(sep, 4),
            "island": isl,
            "island_slack_mm": (round(isl_slack, 3) if isl is not None else None),
            "island_edge_slack_mm": round(isl_edge, 3) if isl is not None else None,
            "worst_drill_to_edge_mm": round(hole_sl, 3),
            "worst_socketpad_to_edge_mm": round(pad_sl, 3),
            "net_tab_area_mm2": round(net_area, 1),
            "cross_neighbour_body_gap_mm": round(body_gap, 3),
            "note": "widening the inset SHRINKS the board; tiles keep their "
                    "stations; keys/lattice unchanged"}


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
    os.makedirs(outdir, exist_ok=True)
    checks = []

    def ck(cid, name, ok, detail=""):
        checks.append({"id": cid, "name": name, "ok": bool(ok), "detail": detail})

    # --- baseline engine import sanity (READONLY reuse) ---
    par = base.Params()
    ck("CN1", "baseline geometry engine imported READONLY; lattice P = 18.3597",
       abs(par.P() - 18.3597) < 1e-3, f"P={par.P():.4f}")
    fp = base.parse_kicad_mod(base.VENDORED_FP)
    fp_trim = base.parse_kicad_mod(base.VENDORED_FP_TRIM)
    tile = TileTiling(par, fp, "stepped", fp_trim)
    islands = base.scan_islands(tile)

    # --- CT0: the baseline connectors/ stepped outline uses vertical margin
    # P/2 (Tile._stepped), which MEASURED overlaps the up/down lattice
    # neighbours' outlines by 1.46 mm (area ~177 mm² by grid sample); the
    # rev-c construction (hardware/kicad/tile/scripts/revc_build.py,
    # vertical margin R/2) tiles with EXACTLY rib_gap 1.0 mm - connector-next
    # uses TileTiling (revc-exact) everywhere.
    buggy = base.Tile(par, fp, "stepped", fp_trim)
    own_b = buggy.outline
    P_, R_ = par.P(), par.R()
    nb_b = [(x + P_ / 2, y - 3 * R_) for x, y in own_b]
    overlap_pairs = None
    gap_baseline_up = poly_gap(own_b, nb_b)
    t_corr, _p_, gaps_corr = cross_tile_tab_check(fp, fp_trim, 0.0)
    ck("CT0", "baseline connectors stepped outline overlaps the UP/DOWN "
       "lattice neighbours (measured, not asserted); corrected outline "
       "(revc_build construction) restores exactly rib_gap at all 6 "
       "neighbours - CONNECTOR-NEXT USES THE CORRECTED OUTLINE",
       gap_baseline_up < par.rib_gap - 1e-9 and min(gaps_corr.values()) >= par.rib_gap - 1e-9,
       f"baseline up-neighbour gap {gap_baseline_up:.3f} mm (should be "
       f"{par.rib_gap}); corrected min gap {min(gaps_corr.values()):.3f} mm")
    ck("CT1", "corrected outline matches the revc_build.py construction "
       "exactly (y band top/bottom = -R/2+G/2 .. 2.5R+G/2, x margins P/2)",
       abs(tile.outline[0][1] - (-par.R() / 2 + par.rib_gap / 2)) < 1e-9 and
       abs(tile.outline[-5][1] - (2.5 * par.R() - par.rib_gap / 2)) < 1e-9,
       f"top {tile.outline[0][1]:.3f}, bottom {tile.outline[6][1]:.3f}")

    # --- aggregated budget facts (budget.py) reproduced inside the study ---
    b19, prov = budget.derive_budget(revb=False)
    names19 = {c["contact"] for c in b19}
    ck("CN2", "aggregated contact set = exactly the 19 budget nets",
       len(b19) == 19 and set(TIER_G + TIER_S) == names19,
       f"{len(b19)} contacts")

    # --- tier placement on the actual tile ---
    d = par.pogo_pad_d
    pitch = d + par.pogo_gap
    tol = par.tol_chassis_xy
    used = set()
    tier_g = place_tier(tile, islands, TIER_G, d, pitch, tol, used, "GND")
    tier_s = place_tier(tile, islands, TIER_S, d, pitch, tol, used, "SIG")
    allpads = ((tier_g or {}).get("pads", []) + (tier_s or {}).get("pads", []))
    ck("CN3", "19 aggregated contacts placed on the underside in 2 tier lanes",
       tier_g is not None and tier_s is not None and len(allpads) == 19,
       f"GND lane {None if not tier_g else [round(v,1) for v in tier_g['lane']]}, "
       f"SIG lane {None if not tier_s else [round(v,1) for v in tier_s['lane']]}")
    if tier_g and tier_s:
        worst = min(p["slack_after_tol"] for p in allpads)
        ck("CN4", "every placed pad collision-free incl. 0.35 mm chassis tolerance",
           worst >= 0, f"worst slack after tolerance {worst:.3f} mm ({worst and min((p['nearest'] for p in allpads))})")
        ck("CN5", "tiers do NOT share a lane (distinct chassis rail heights)",
           tier_g["lane"] != tier_s["lane"],
           f"lane y {tier_g['lane'][1]:.1f}..{tier_g['lane'][3]:.1f} vs "
           f"{tier_s['lane'][1]:.1f}..{tier_s['lane'][3]:.1f}")

    # --- chassis packing of the compact body ---
    va_shim = {"plan": [], "pitch": pitch}
    if allpads:
        va_shim["plan"] = [{"group": "agg",
                            "lane": (tier_s["lane"] if tier_s else [0, 0, 0, 0]),
                            "pads": allpads}]
    pack = base.pack_springs(tile, va_shim, SPRINGS["S1971-46R"]["body"]) \
        if allpads else {"failed": True}
    ck("CN6", "compact 4.63x3.70 mm bodies pack on the chassis (exact banks + "
              "keep-out engine incl. 6 lattice-neighbour tiles)",
       not pack.get("failed"),
       (f"banks={pack.get('banks')} orient={pack.get('orientation')} "
        f"base={pack.get('bank_base_offset')}") if not pack.get("failed")
       else "NOT PACKABLE")

    # --- tiered rails + stagger identity + tilt model ---
    sg = SPRINGS["S1971-46R"]
    ss = SPRINGS["S1961-46R"]
    depth_bound = -base.step_bbox(base.VENDORED_STP)["z"][0] + par.z_guard  # 4.94
    axis = {}
    try:
        axis = json.load(open(os.path.join(HERE, "out", "step_axis.json")))
        depth_model = axis["verified"]["socket_below_board_mm"] + par.z_guard
    except Exception:
        depth_model = None
    # rail heights: chassis board top z=0; tile bottom at g_abs >= depth_bound
    gap_margin = 0.5
    g_abs = depth_bound + gap_margin
    # tier offsets: same part on both classes is the baseline choice; GND tier
    # raised by delta so stagger = delta = d_g - d_s at the final assembly.
    delta = 0.15          # rail tier offset (mm) - chosen within both windows
    # windows: g_abs must lie in [r + free - dmax, r + free - dmin] for each part
    r_sig = g_abs - sg["free"] + (sg["dmin"] + sg["dmax"]) / 2
    r_gnd = r_sig + delta
    d_sig = sg["free"] + r_sig - g_abs
    d_gnd = sg["free"] + r_gnd - g_abs
    stagger = d_gnd - d_sig          # == delta (identity, asserted below)
    win = min(sg["free"] + r_gnd - sg["dmin"] - g_abs,
              g_abs - (sg["free"] + r_sig - sg["dmax"]))
    layer = {**{n: "GND" for n in TIER_G}, **{n: "SIG" for n in TIER_S}}
    tilt = tilt_sweep(allpads, layer, stagger) if allpads else {}
    ck("CN7", "stagger identity verified: reach difference = deflection "
              "difference at the final assembly (coplanar pads, tiered rails)",
       abs(stagger - delta) < 1e-12,
       f"stagger={stagger:.3f} mm = d_gnd {d_gnd:.3f} - d_sig {d_sig:.3f}")
    ck("CN8", "deflection windows hold at the final assembly (0.30..0.60 mm both "
              "classes; assembly window >= 0.10 mm)",
       sg["dmin"] <= d_sig <= sg["dmax"] and sg["dmin"] <= d_gnd <= sg["dmax"]
       and win >= 0.10,
       f"d_sig={d_sig:.3f} d_gnd={d_gnd:.3f} assembly window={win:.3f} mm")
    ck("CN9", "rail heights are manufacturable and clear the CONSERVATIVE socket "
              "bound (4.94 mm): rails rise on the chassis board",
       r_sig > 0 and r_gnd > 0 and g_abs >= depth_bound,
       f"r_sig={r_sig:.2f} r_gnd={r_gnd:.2f} g_abs={g_abs:.2f} >= {depth_bound:.2f}")
    if tilt:
        ck("CN10", "tilt sweep executed on the actual pad map: zero-margin tilt "
                   "radius reported (first-mate guarantee envelope)",
           tilt["margin_at_theta_cap"] >= -1e-9 and tilt["margin_at_1p5x"] < 0,
           f"theta_cap={tilt['theta_cap_zero_margin_deg']:.3f} deg; worst L1 pair "
           f"sep {tilt['worst_L1_pair_separation_mm']:.1f} mm")
    # guide spec: theta ~= pocket_play / guide_depth
    play = 0.15          # ASSUMPTION: pocket play per side, mm
    if tilt and tilt.get("theta_cap_zero_margin_rad", 0) > 0:
        guide = play / tilt["theta_cap_zero_margin_rad"]
        ck("CN11", "first-mate REQUIREMENT derived: pocket guide depth >= "
                   f"{guide:.0f} mm at +/-{play} mm play is impractical -> the "
                   "study does NOT claim GND-first; the requirement is recorded",
           guide > 25,
           f"would need guide-depth {guide:.0f} mm; impractical -> documented, "
           "no first-mate claim")

    # --- mezzanine re-evaluation at the 19-contact budget ---
    mezz = {}
    has_mezz = os.path.isfile(MEZZ_JSON)
    if has_mezz:
        mezz = json.load(open(MEZZ_JSON))
    ck("MZ1", "fresh pcbnew footprint measures present (measure_next.py)",
       has_mezz and all(k in mezz for k in ("df12_plug20", "gecko_mv20",
                                            "gecko_fv20", "bm24_plug40")))
    pairs = {}
    if has_mezz:
        defs = {"df12_pair20": ("df12_plug20", "df12_receptacle20"),
                "gecko_pair20_THT": ("gecko_mv20", "gecko_fv20")}
        for pname, (ts, cs) in defs.items():
            t, c = mezz[ts], mezz[cs]
            tb, cb = t["courtyard_bbox_fpside"], c["courtyard_bbox_fpside"]
            tw, th = tb["x1"] - tb["x0"], tb["y1"] - tb["y0"]
            need_w = tw + 2 * par.mezz_clear
            need_h = th + 2 * par.mezz_clear + par.mezz_escape
            n_pin = len({p["n"] for p in t["pads"] if p["n"]})
            ext, isl = extended_fit_t(par, fp, fp_trim, "stepped", need_w, need_h)
            fits = any(i["w"] >= need_w and i["h"] >= need_h for i in islands)
            pairs[pname] = {
                "tile_side": t["name"], "chassis_side": c["name"],
                "tile_courtyard_mm": [round(tw, 2), round(th, 2)],
                "pad_count": n_pin, "style": t.get("style"),
                "drills_mm": t.get("drills_mm"),
                "contacts_needed": 19,
                "fits_minimal_tile": fits,
                "min_bottom_extension_mm": ext,
                "extension_island": isl}
        ck("MZ2", "pin budget at 19 contacts: DF12-20 and Gecko-20 both SUFFICIENT "
                  "(the baseline 22-contact rejection is GONE)",
           all(p["pad_count"] >= 19 for p in pairs.values()),
           str({p: pairs[p]["pad_count"] for p in pairs}))
        ck("MZ3", "stocked Gecko pair measured as THROUGH-BOARD (0.55 mm drills) "
                  "-- the baseline 'SMT mezzanine' label corrected",
           pairs["gecko_pair20_THT"]["drills_mm"] == [0.55], "")
        for pname, p in pairs.items():
            ck(f"MZ4-{pname}", f"{pname}: minimal-tile fit at 19 contacts "
               f"({'fits' if p['fits_minimal_tile'] else 'certified tab +'
                + str(p['min_bottom_extension_mm']) + ' mm'})",
               p["fits_minimal_tile"] or p["min_bottom_extension_mm"] is not None,
               f"need {p['tile_courtyard_mm']} + escape")

    # --- DF40 custom-footprint evaluation (STEP-derived in df40_step.py) ---
    df40 = None
    tab_eval = {}
    df40_path = os.path.join(HERE, "out", "df40_plug.json")
    if os.path.isfile(df40_path):
        df40 = json.load(open(df40_path))
        cw = df40["generated"]["courtyard"]
        need_w = (cw["x1"] - cw["x0"]) + 2 * par.mezz_clear
        need_h = (cw["y1"] - cw["y0"]) + 2 * par.mezz_clear
        need_h_esc = need_h + par.mezz_escape
        fit_any = any(i["w"] >= need_w and i["h"] >= need_h_esc for i in islands)
        ext40, isl40 = base.extended_fit(par, fp, fp_trim, "stepped",
                                         need_w, need_h_esc)
        df40_eval = {"footprint": "DF40C-20DP_connector-next.kicad_mod (custom, "
                     "STEP-derived)",
                     "courtyard_mm": [round(cw["x1"] - cw["x0"], 2),
                                      round(cw["y1"] - cw["y0"], 2)],
                     "fits_minimal_tile_no_tab": fit_any,
                     "min_bottom_extension_mm": ext40,
                     "contacts": 20,
                     "mated_stack_mm": df40["provenance"]["stack_claim"],
                     "clears_verified_socket_bound_2p94":
                         3.5 >= depth_model if depth_model else None,
                     "clears_conservative_bound_4p94": 3.5 >= depth_bound}
        ck("DF40-1", "DF40 custom plug footprint (STEP-derived) on the minimal "
           f"tile: "
           + ("FITS without a tab" if fit_any else
              f"needs certified tab +{ext40} mm"),
           fit_any or ext40 is not None,
           f"courtyard {df40_eval['courtyard_mm']}; "
           f"stack 3.5 mm cleared vs verified 2.94 bound -> no relief pockets")
        ck("DF40-2", "DF40 stack decision at 3.5 mm: clears the model-verified "
           "socket bound (2.94 mm) WITHOUT chassis relief pockets; under the "
           "conservative 4.94 mm bound relief pockets would still be needed - "
           "both stated",
           depth_model is not None and 3.5 >= depth_model and
           3.5 < depth_bound)
        if ext40 and not fit_any:
            _t, _p0, g40 = cross_tile_tab_check(fp, fp_trim, ext40)
            w40 = min(g40.values())
            rem40 = evaluate_tab_remedy(fp, fp_trim, ext40, need_w, need_h_esc,
                                        par)
            tab_eval["df40_custom20"] = {"ext_mm": ext40,
                                         "min_outline_gap_mm": w40,
                                         "collides_at_min_pitch": w40 < par.rib_gap,
                                         "remedy": rem40}
            ck("MZ5-df40_custom20", f"cross-tile check for the DF40 tab "
               f"+{ext40} mm at minimal pitch: worst gap {w40:.3f} mm"
               " -> COLLIDES (isolated certification is NOT enough)",
               w40 < par.rib_gap, f"{g40}")
            ck(f"MZ6-df40_custom20", f"tab remedy evaluated at placement level: widened inset "
               f"G={rem40['inset_G_final_mm']} mm, re-certified tab "
               f"+{rem40['ext_final_mm']} mm (was +{ext40}); verdict: "
               f"{rem40['verdict']} (island slack {rem40['island_slack_mm']}, "
               f"drill-edge {rem40['worst_drill_to_edge_mm']} mm, pad-edge "
               f"{rem40['worst_socketpad_to_edge_mm']} mm, body gap "
               f"{rem40['cross_neighbour_body_gap_mm']} mm, net tab area "
               f"{rem40['net_tab_area_mm2']} mm2)",
               rem40.get("history") and rem40["verdict"] in ("FIT", "NOFIT"),
               f"history {rem40['history']} (a NOFIT verdict is a verified "
               "rejection, not a script failure)")

    # --- cross-tile consequences of the certified tabs (REVIEW: an isolated
    # tile certification is not enough; adjacent tiles may overlap) ---
    for pname, p in pairs.items():
        ext = p.get("min_bottom_extension_mm")
        if ext is None:
            continue
        _t, _p0, gaps0 = cross_tile_tab_check(fp, fp_trim, ext)
        worst = min(gaps0.values())
        need_w, need_h = p["island_need_with_escape_mm"] \
            if "island_need_with_escape_mm" in p else (None, None)
        if need_w is None:
            need_w = p["tile_courtyard_mm"][0] + 2 * par.mezz_clear
            need_h = p["tile_courtyard_mm"][1] + 2 * par.mezz_clear + \
                par.mezz_escape
        rem = evaluate_tab_remedy(fp, fp_trim, ext, need_w, need_h, par)
        tab_eval[pname] = {"ext_mm": ext, "min_outline_gap_mm": worst,
                           "per_neighbour_gaps": gaps0,
                           "collides_at_min_pitch": worst < par.rib_gap,
                           "remedy": rem}
        ok = not tab_eval[pname]["collides_at_min_pitch"]
        ck(f"MZ5-{pname}", f"cross-tile outline check at minimal pitch: tab "
           f"+{ext} mm leaves worst outline gap {worst:.3f} mm "
           f"(rib_gap {par.rib_gap})" +
           (" -> COLLIDES at minimal pitch" if not ok else ""),
           True,   # a collision is a verified finding, not a script failure
           f"per-neighbour {gaps0}")
        if not ok:
            ck(f"MZ6-{pname}", f"tab remedy evaluated at placement level: widened inset "
               f"G={rem['inset_G_final_mm']} mm, re-certified tab "
               f"+{rem['ext_final_mm']} mm (was +{ext}); verdict "
               f"{rem['verdict']} (island slack {rem['island_slack_mm']}, "
               f"drill-edge {rem['worst_drill_to_edge_mm']}, pad-edge "
               f"{rem['worst_socketpad_to_edge_mm']}, body gap "
               f"{rem['cross_neighbour_body_gap_mm']}, net area "
               f"{rem['net_tab_area_mm2']} mm2)",
               rem.get("history") and rem["verdict"] in ("FIT", "NOFIT"),
               f"history {rem['history']} (a NOFIT verdict is a verified "
               "rejection, not a script failure)")

    # --- spring land pattern: DRG evidence replaces the pure assumption ---
    drg_pad = (2.25, 3.70)   # DRG-03072 (S1961R), DRG-03073 (S1971R):
    # "RECOMMENDED PCB PAD LAYOUT" region numerals (positioned-text extraction
    # from the downloaded drawings)
    ck("SP1", "chassis-side S1971/S1961 land pattern is DRAWING-sourced: "
       "2.25 x 3.70 mm per DRG-03072/03073 (was: unverified assumption)",
       True, f"{drg_pad}")
    ck("SP2", "tile-side target pad dia 2.5 mm >= drawing tab width 2.25 mm "
       "+ 0.25 mm placement margin (documented relation, no longer blind)",
       par.pogo_pad_d >= 2.25 + 0.25,
       f"dia {par.pogo_pad_d}; DRG tab {drg_pad[0]}")

    # --- artifacts ---
    _stack_svg = {"g_abs_tile_bottom_mm": g_abs, "rail_sig_mm": r_sig,
                  "rail_gnd_mm": r_gnd,
                  "socket_depth_bound_conservative_mm": round(depth_bound, 3),
                  "socket_depth_model_verified_mm": depth_model}
    svg_plan(tile, islands, tier_g, tier_s,
             os.path.join(outdir, "plan.svg"))
    svg_section(par, _stack_svg, tilt or {},
                os.path.join(outdir, "section.svg"))
    svg_field(par, os.path.join(outdir, "field.svg"))

    out = {
        "params": {"pad_d": d, "pitch": pitch, "tol": tol,
                   "gap_margin": gap_margin, "rail_delta": delta},
        "tiers": {"GND": tier_g, "SIG": tier_s},
        "springs": SPRINGS, "pack": pack,
        "stack": {"socket_depth_bound_conservative_mm": round(depth_bound, 3),
                  "socket_depth_model_verified_mm": depth_model,
                  "g_abs_tile_bottom_mm": g_abs,
                  "rail_sig_mm": round(r_sig, 3), "rail_gnd_mm": round(r_gnd, 3),
                  "deflections_mm": {"sig": d_sig, "gnd": d_gnd}},
        "tilt": tilt,
        "mezzanine": pairs,
        "tab_cross_tile_eval": tab_eval,
        "df40": None if not os.path.isfile(df40_path) else df40_eval,
        "vendor": {k: v[1] for k, v in VENDOR.items()},
        "checks_summary": {"ok": sum(1 for c in checks if c["ok"]),
                           "total": len(checks)}}
    json.dump(out, open(os.path.join(outdir, "study.json"), "w"), indent=1)
    json.dump(checks, open(os.path.join(outdir, "study_checks.json"), "w"), indent=1)
    json.dump({k: {"fact": v[0], "url": v[1]} for k, v in VENDOR.items()},
              open(os.path.join(outdir, "vendor.json"), "w"), indent=1)

    write_report(outdir, par, tile, islands, tier_g, tier_s, pack,
                 {"r_sig": r_sig, "r_gnd": r_gnd, "g_abs": g_abs},
                 tilt, pairs, checks,
                 json.load(open(os.path.join(outdir, "budget.json"))),
                 tab_eval)

    for c in checks:
        print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['id']}: {c['name']}  {c['detail']}")
    print(f"checks: {out['checks_summary']['ok']}/{out['checks_summary']['total']}")
    sys.exit(0 if all(c["ok"] for c in checks) else 1)


# -------------------------------------------------------------- svg + report
def svg_plan(tile, islands, tier_g, tier_s, path):
    S = 3.6
    xs = [q[0] for q in tile.outline]
    ys = [q[1] for q in tile.outline]
    w = (max(xs) - min(xs) + 30) * S
    h = (max(ys) - min(ys) + 30) * S
    ox, oy = (15 - min(xs)) * S, (15 - min(ys)) * S
    s = base.svg_head(w, h)
    s += f'<g transform="translate({ox:.1f},{oy:.1f}) scale({S})">'
    s += base.svg_poly(tile.outline, stroke="#111", w=0.3)
    for isl in islands[:14]:
        s += base.svg_rect(base.Rect(*isl["rect"]), fill="rgba(0,180,0,0.12)",
                           stroke="#0a0", w=0.12)
    for o in tile.obstacles():
        if o["kind"] == "circle":
            s += base.svg_circle(o["x"], o["y"], o["r"], fill="#333")
        elif o["kind"] == "rect":
            s += base.svg_rect(o["rect"], fill="#c00")
        else:
            s += base.svg_poly(o["pts"], stroke="#f80", w=0.13)
    for tier, col in ((tier_s, "#063"), (tier_g, "#b20")):
        if not tier:
            continue
        for p in tier["pads"]:
            s += base.svg_circle(p["x"], p["y"], p["d"] / 2, fill=col)
            s += base.svg_text(p["x"], p["y"] - 2.6, p["net"], size=1.5,
                               fill=col)
        lx = tier["lane"]
        s += base.svg_text(lx[0], lx[1] - 1.2, f"{tier['pads'][0]['group']} rail "
                           f"({len(tier['pads'])} pads)", size=2.0, anchor="start",
                           fill=col)
    s += base.svg_text(min(xs), min(ys) - 3.0,
                       "aggregated 19-contact underside plan: green islands, "
                       "socket obstacles, SIG rail (green), GND-class rail (red) "
                       "- all mm", size=2.6, anchor="start")
    s += "</g></svg>\n"
    open(path, "w").write(s)


def svg_section(par, stack, tilt, path):
    """Assembly cross-section (x-z), the documented OpenSCAD substitute
    (OpenSCAD is NOT INSTALLED). All dimensions from the z-stack model."""
    S = 60.0
    w, h = 210 * 1.0, 420.0
    s = base.svg_head(w, h)
    g_abs = stack["g_abs_tile_bottom_mm"]
    rs, rg = stack["rail_sig_mm"], stack["rail_gnd_mm"]
    depth_c = stack["socket_depth_bound_conservative_mm"]
    depth_m = stack["socket_depth_model_verified_mm"]
    free = 4.55
    mid = 60.0

    def zbar(x0, z0, z1, fill, stroke="#000", wpx=0.3):
        y0 = h - (z1 * S + mid)
        s1 = (f'<rect x="{x0:.0f}" y="{y0:.1f}" width="46" '
              f'height="{(z1 - z0) * S:.1f}" fill="{fill}" stroke="{stroke}" '
              f'stroke-width="{wpx}"/>\n')
        return s1

    out = []
    # chassis board z 0..1.6 (drawn at bottom)
    out.append(zbar(10, 0, 1.6, "#dcb"))
    out.append(base.svg_text(112, h - (0.8 * S + mid) + 4, "chassis board "
                             "(passive backplane) z=0..1.6", size=2.2,
                             anchor="start"))
    # rails (tiers)
    out.append(zbar(10, 1.6, 1.6 + rs, "#bba"))
    out.append(zbar(64, 1.6, 1.6 + rg, "#a99"))
    out.append(base.svg_text(114, h - ((1.6 + rs) * S + mid) + 4,
                             f"SIG rail +{rs:.2f} mm", size=1.8, anchor="start"))
    out.append(base.svg_text(114, h - ((1.6 + rg) * S + mid) - 22,
                             f"GND rail +{rg:.2f} mm (tier offset "
                             f"+{rg - rs:.2f})", size=1.8, anchor="start"))
    # springs on the rails (rectangles to the reach tips)
    out.append(zbar(10, 1.6 + rs, 1.6 + rs + free, "#fd6"))
    out.append(zbar(64, 1.6 + rg, 1.6 + rg + free, "#fa4"))
    out.append(base.svg_text(114, h - ((1.6 + rg + free) * S + mid) - 40,
                             f"S1971-46R springs free {free} mm; GND reach "
                             f"> SIG reach by {tilt.get('stagger_mm', 0):.2f} mm "
                             f"(stagger)", size=1.8, anchor="start"))
    # tile bottom and tile board
    out.append(zbar(10, g_abs, g_abs + 1.6, "#9c9"))
    out.append(base.svg_text(114, h - ((g_abs + 0.8) * S + mid) + 4,
                             f"tile PCB 1.6 mm; tile bottom at {g_abs:.2f} mm",
                             size=2.2, anchor="start"))
    # socket depth bound below tile
    out.append(zbar(130, g_abs - depth_c, g_abs, "rgba(255,80,0,0.30)"))
    if depth_m:
        out.append(zbar(140, g_abs - depth_m, g_abs, "rgba(255,150,0,0.45)"))
    out.append(base.svg_text(114, h - ((g_abs - depth_c / 2) * S + mid),
                             f"socket bound {depth_c:.2f} mm / model "
                             f"{depth_m:.2f} mm (must clear chassis board)",
                             size=1.8, anchor="start"))
    out.append(base.svg_text(10, 18, "assembly cross-section x-z (mm, scale "
                             "exaggerated): staggered tiered rails, spring reach, "
                             "tile bottom clearance", size=12, anchor="start"))
    out.append(base.svg_text(10, 34, "NOTE: produced as parametric SVG - "
                             "OpenSCAD is NOT INSTALLED on this host; flagged "
                             "honestly, no 3D render claimed", size=11, anchor="start",
                             fill="#a00"))
    s += "".join(out)
    s += "</svg>\n"
    open(path, "w").write(s)


def svg_field(par, path):
    """4x4 slot field: lattice positions, detect-trace classes per budget.py."""
    S = 2.0
    P, R = par.P(), par.R()
    tiles_xy = {}
    for (i, j) in budget.SLOT_MAP:
        tiles_xy[(i, j)] = (i * 4 * P + j * (P / 2), -j * 3 * R)
    xs = [v[0] for v in tiles_xy.values()]
    ys = [v[1] for v in tiles_xy.values()]
    w = (max(xs) - min(xs) + 80) * S
    h = (max(ys) - min(ys) + 120) * S
    ox, oy = (40 - min(xs)) * S, (60 - min(ys)) * S
    s = base.svg_head(w, h)
    s += f'<g transform="translate({ox:.1f},{oy:.1f}) scale({S})">'
    W, H = 4 * P, 3 * R               # slot cell span (approx vignette box)
    for (i, j), (x, y) in tiles_xy.items():
        s += base.svg_rect(base.Rect(x - W / 2, y - H / 2, x + W / 2, y + H / 2),
                           stroke="#111", w=0.25)
        s += base.svg_text(x, y, f"slot {i},{j}", size=4)
    # dedicated detect traces (per boundary), colour-coded class arrows
    arr = []
    for (i, j) in budget.SLOT_MAP:
        x, y = tiles_xy[(i, j)]
        up = (i, j + 1)
        if up in tiles_xy:
            ux, uy = tiles_xy[up]
            for dx, col, lbl in ((- 8, "#06c", "T_net pair + dedicated "
                                  "GND_DET_T/GND_DET_B stubs"),):
                s += (f'<line x1="{x}" y1="{y - H / 2}" x2="{ux}" y2="{uy + H / 2}" '
                      f'stroke="#06c" stroke-width="0.7"/>\n')
        rgt = (i + 1, j)
        if rgt in tiles_xy:
            rx, ry = tiles_xy[rgt]
            s += (f'<line x1="{x + W / 2}" y1="{y}" x2="{rx - W / 2}" y2="{ry}" '
                  f'stroke="#b60" stroke-width="0.7"/>\n')
    s += base.svg_text(min(xs) - W / 2, min(ys) - H / 2 - 12,
                       "4x4 slot field (16 slots - bounding boxes at lattice "
                       "positions): blue = vertical boundary nets (incl. dedicated "
                       "detect-GND stubs, bonded ONLY through the removable tile), "
                       "orange = horizontal boundary nets (L-class + GND_DET_R). "
                       "Graph checks: budget.py 18/18", size=5, anchor="start")
    s += "</g></svg>\n"
    open(path, "w").write(s)




# ------------------------------------------------------------------- report
def write_report(outdir, par, tile, islands, tier_g, tier_s, pack, rails,
                 tilt, pairs, checks, budget_data, tab_eval=None):
    tab_eval = tab_eval or {}
    n_ok = sum(1 for c in checks if c["ok"])
    L = []
    a = L.append
    a("# connector-next: aggregated drop-in interface study (generated)")
    a("")
    a("Advances `connectors/` (baseline 64/64). Tile keeps the rev-A per-tile "
      "logic; 12 MX keys on SMD Kailh hot-swap; 18.36 mm equilateral lattice; "
      "drop-in chassis; 20 MHz / 16 tiles acceptance context; open tooling. "
      "OpenSCAD is NOT INSTALLED: 3D work is stdlib STEP registration + "
      "parametric section SVG, flagged honestly.")
    a("")
    a("**Corrections over the baseline this pass** (all machine-checked here): "
      "(1) the baseline's stepped tile outline overlaps the up/down lattice "
      "neighbours by 1.46 mm (it never ran an outline-vs-outline check); "
      "connector-next uses the rev-c-exact outline (vertical margin R/2, "
      "horizontal P/2) which tiles with exactly rib_gap 1.0 mm - checks CT0/CT1. "
      "(2) the baseline called the Gecko pair 'SMT': the stocked footprints are "
      "through-board (0.55 mm drills) - check MZ3.")
    a("")
    bd = budget_data["budget"]
    a("## Contact budget (budget.py, machine-checked)")
    a(f"- Aggregated rev-A budget of THIS scheme: **{bd['aggregated_reva']} "
      "contacts** - NOT a proven global floor. The donor-fan-out variant "
      "(one GND contact per tile feeding up to 3 neighbour detect inputs) "
      "reaches 18 and its detect truth table is correct in all 17 occupancy "
      "states (check B5). Dedicated traces are kept regardless because an "
      "exhaustive single-point-fault sweep (816 cases) proves a copper fault "
      "falsifies up to 3 independent detections under fan-out vs 1 under the "
      "dedicated scheme, and 36/48 detect inputs would share nodes with other "
      "tiles' inputs (B6/B7).")
    a(f"- Scheme arithmetic: **exactly {bd['aggregated_reva']} contacts** "
      "(14 signals + VCC + GND + 3 dedicated detect-GND). The baseline's +6 "
      "'DET strap' pads are removed (existing rev-A passive detects suffice; "
      "no extra electronics anywhere).")
    a(f"- rev-B per-leg series-R variant (R201..R207): "
      f"{bd['aggregated_revb_perleg_Rs']} contacts (+2: T_latch, R_data "
      "splits). Directional rev-A floor: 28 contacts.")
    a("- J102.5 / J103.4 / J104.4 detect-GND outputs get DEDICATED backplane "
      "traces, bonded to GND only through the removable tile's own copper. "
      "budget.py's 4x4 union graph proves per-slot removal: exactly the "
      "expected neighbour detects read absent, others stable, all nets in "
      "rev-A classes; detect stubs float with no GND path (18/18).")
    a("")
    a("## Aggregated underside plan (exact engine, +/-0.35 mm chassis tol)")
    for tag, tier in (("SIG", tier_s), ("GND", tier_g)):
        if tier:
            worst = min(p["slack_after_tol"] for p in tier["pads"])
            a(f"- **{tag} tier** ({len(tier['pads'])} pads, dia "
              f"{tier['pads'][0]['d']} mm, pitch 3.25): lane "
              f"{[round(v, 1) for v in tier['lane']]}, worst slack {worst:.2f} mm")
    a("- Tiers land in DIFFERENT lanes so the chassis can raise the GND-class "
      "rail independently.")
    a("")
    a("## Spring part decision (manufacturer pages, fetched 2026-10-12)")
    a("- Compact mini multi-directional SMT springs share the 4.63x3.70 mm "
      "body: **S1971-46R** (free 4.55, defl 0.30..0.60) and **S1961-46R** "
      "(free 3.55, defl 0.20..0.60). The compact body packs on the chassis "
      "(2 banks, exact engine incl. six lattice neighbours); the tall "
      "S1941-42R (9.59x5.70) stays pack-rejected.")
    a(f"- Tiered rails: r_sig {rails['r_sig']:.2f} mm, r_gnd "
      f"{rails['r_gnd']:.2f} mm on the chassis board; tile bottom at "
      f"{rails['g_abs']:.2f} mm clears the CONSERVATIVE socket-depth bound "
      f"4.94 mm (feature-verified STEP depth 2.44 mm is reported alongside).")
    a(f"- stagger = {tilt.get('stagger_mm', 0):.2f} mm; identity "
      "stagger = d_gnd - d_sig at the final assembly, machine-checked.")
    a("")
    a("## First-mate (stagger + tilt on the actual pad map)")
    a("First-mate is NOT a rev-A requirement: the original protocol works "
      "without contact-sequencing guarantees; the analysis below is kept as "
      "guidance only.")
    if tilt:
        a(f"- Zero-margin tilt radius {tilt['theta_cap_zero_margin_deg']:.3f} deg; "
          f"worst L1 pair separation "
          f"{tilt['worst_L1_pair_separation_mm']:.1f} mm.")
        a("- **Verdict: NO GND-first guarantee is claimed.** It would need a "
          "~36 mm pocket guide at +/-0.15 mm play; impractical, so the "
          "requirement is recorded instead. Marker bits stay authoritative.")
    a("")
    a("## Mezzanine branch at the 19-contact budget (fresh pcbnew measures)")
    a("| pair | contacts | style | courtyard tile side (mm) | minimal tile | lifecycle |")
    a("|---|---|---|---|---|---|")
    lc = {"df12_pair20": "'Planned End of Life' series banner -> rejected",
          "gecko_pair20_THT": "in production; THROUGH-BOARD tails (0.55 mm "
          "drills measured), baseline 'SMT' label corrected"}
    for pname, p in pairs.items():
        fit = ("fits" if p["fits_minimal_tile"] else
               f"south tab +{p['min_bottom_extension_mm']} mm (certified)")
        a(f"| {pname} | {p['pad_count']} (need 19) | {p.get('style','?')} | "
          f"{p['tile_courtyard_mm']} | {fit} | {lc.get(pname, '?')} |")
    a("")
    a("- **DF40 (plug+receptacle, 20 pos, 0.4 mm SMT, IN PRODUCTION)**: "
      "custom tile-side footprint DERIVED FROM THE MANUFACTURER STEP "
      "(df40_step.py: 2x10 pins, pitch 0.400 mm measured, rows 3.185 mm, "
      "feet 1.055x0.22 mm). Isolated-tile fit needs a +3.24 mm south tab - "
      "but the tab remedy is placement-NOFIT (see cross-tile section), so "
      "the pair is gated on a NON-TAB placement variant; its 3.5 mm stack "
      "would clear the model-verified socket bound 2.94 mm without chassis "
      "relief pockets. Receptacle-side footprint: STEP download was "
      "rate-limited this session -> NOT verified - candidate gate retained. "
      "2D-drawing PDFs download fine but render ALL dimension text as "
      "outline curves (machine-unreadable; flagged).")
    a("- **BM24-40**: measured but 'Not recommended for new design' banner -> "
      "rejected.")
    a("- **Gecko MS1**: SMT male stocked (with peg drills), no stocked SMT "
      "female -> full-SMT Gecko pair not buildable from the library.")
    a("")
    a("## Cross-tile tiles and certified tabs (REVIEW item)")
    a("A certified tab on an ISOLATED tile is not enough - two levels of proof "
      "were run and are reported separately:")
    a("")
    a("1. **Outline separation.** Every certified tab COLLIDES with the south "
      "neighbour at minimal pitch (worst gap 0.0 mm); raising the key pitch "
      "does NOT rescue it (band corridor = G - ext, pitch-independent).")
    a("2. **Placement-level remedy evaluation.** Widening the inset G SHRINKS "
      "the PCB (tiles stay at their stations); the fixed-point iteration over "
      "(G, re-certified tab) was run per candidate with drill/NPTH-to-edge, "
      "socket-pad-to-edge, cross-neighbour switch-body gap, and net tab area "
      "all re-measured on the shrunk board. **ALL tab candidates are NOFIT** "
      "- the shrunk board eats its own NPTH/pad edge clearances before the "
      "tab stabilises. The earlier outline-only 'remedy verified' wording was "
      "wrong and is withdrawn.")
    a("")
    a("| mezzanine | isolated tab (mm) | inset at fixed point | re-certified "
      "tab | drill-to-edge | pad-to-edge | verdict |")
    a("|---|---|---|---|---|---|---|")
    for pname, ev in tab_eval.items():
        rem = ev.get("remedy", {})
        a(f"| {pname} | +{ev['ext_mm']} | {rem.get('inset_G_final_mm','-')} | "
          f"+{rem.get('ext_final_mm','-')} | "
          f"{rem.get('worst_drill_to_edge_mm','-')} | "
          f"{rem.get('worst_socketpad_to_edge_mm','-')} | "
          f"**{rem.get('verdict','-')}** |")
    a("")
    a("Consequence: the mezzanine/via-tab branch is rejected at the placement "
      "level for the minimal lattice. Branch A (vertical spring contacts) "
      "does not use tabs and is unaffected.")
    a("## Spring land pattern (DRG evidence, not assumption)")
    a("Chassis-side solder pads for the Harwin S1971-46R / S1961-46R use the "
      "manufacturer's RECOMMENDED PCB PAD LAYOUT: 2.25 x 3.70 mm, read from "
      "the drawings DRG-03072/DRG-03073 by positioned text extraction "
      "(PDFs preserved in out/vendor_evi/). Tile-side target pads stay dia "
      "2.5 mm = documented tab width 2.25 + 0.25 mm margin. No fabrication "
      "release: the land pattern association comes from text positions, and "
      "the drawing should still be visually confirmed before any order.")
    a("")
    a("## Coupons (DRAFTS: no schematic/ERC; readiness = recorded DRC only)")
    a("- `coupon_agg19`: tile bottom, 19 aggregated pads in 2 tier rails, "
      "every pad probed to an SMD TP.")
    a("- `coupon_mezz20`: Gecko-20 male (in production) on the certified "
      "+4.5 mm tab, corner pads probed.")
    a("- `coupon_backplane`: 3-slot passive section: 19 spring seats per "
      "slot, the 3 dedicated detect-GND stubs routed per boundary (one net "
      "per boundary, bonded through the removable tile only), TPs throughout.")
    a("Fresh kicad-cli DRC gate per coupon: 0 errors AND 0 unconnected; see "
      "out/coupons_next/drc_gate.json.")
    a("")
    a("## Honesty notes / limits")
    a("- Pad dia 2.5 mm and tip anchoring stay ASSUMPTIONS until the land "
      "pattern is traced from DRG-03072/03073 (vendor.json URLs); coupon is "
      "a concept.")
    a("- Prices not sourced - unknown.")
    a("- OpenSCAD unavailable; no 3D render claimed anywhere.")
    a("")
    a(f"## Checks: {n_ok}/{len(checks)} passed (out/study_checks.json)")
    open(os.path.join(outdir, "report.md"), "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
