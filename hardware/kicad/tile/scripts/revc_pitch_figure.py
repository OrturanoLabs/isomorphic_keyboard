#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare key lattices for Cherry MX switches (15.6 mm body, datasheet):
  * today: equilateral, 20 mm
  * minimum equilateral: 18.36 mm (rows 15.9 mm)
  * squeezed: 15.9 mm in the row and between rows, rows offset by half a pitch
Draws switch bodies (15.6 mm), the Kailh hot-swap socket outline under them (dashed),
keycaps = lattice Voronoi cell shrunk to leave 0.8 mm between caps, one 4x3 tile
highlighted, and the neighbour distances of one key. Same scale for all panels.
Output: docs/media/revc-pitch-comparison.png (ngspice container, matplotlib)."""
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

BODY, CAP_GAP = 15.6, 0.8
CASES = [("today: equilateral 20 mm", 20.0, 20.0 * math.sqrt(3) / 2),
         ("minimum equilateral 18.4 mm", 18.36, 15.9),
         ("squeezed 15.9 x 15.9 mm", 15.9, 15.9)]


def clip(poly, n, d):
    """Keep the part of polygon `poly` with n.x <= d (Sutherland-Hodgman, one half-plane)."""
    out = []
    for i in range(len(poly)):
        p, q = np.array(poly[i]), np.array(poly[(i + 1) % len(poly)])
        fp, fq = n @ p - d, n @ q - d
        if fp <= 0:
            out.append(tuple(p))
        if fp * fq < 0:
            t = fp / (fp - fq)
            out.append(tuple(p + t * (q - p)))
    return out


def voronoi_cell(a, r):
    cell = [(-50, -50), (50, -50), (50, 50), (-50, 50)]
    for v in [(a, 0), (-a, 0), (a / 2, r), (-a / 2, r), (a / 2, -r), (-a / 2, -r)]:
        v = np.array(v, float)
        cell = clip(cell, v / np.linalg.norm(v), np.linalg.norm(v) / 2)
    return cell


def keys(a, r, rows=5, cols=7):
    pts = []
    for j in range(rows):
        for i in range(cols):
            pts.append((i * a - (j % 2) * a / 2 - (j // 2) * a, j * r, i, j))
    return pts


def main():
    fig, axs = plt.subplots(1, 3, figsize=(18, 7.2))
    for ax, (title, a, r) in zip(axs, CASES):
        cell = voronoi_cell(a, r)
        # shrink the cell so neighbouring caps keep CAP_GAP between them
        inr = min(abs(np.linalg.norm(v) / 2) for v in [np.array((a, 0.)), np.array((a / 2, r))])
        k = (inr - CAP_GAP / 2) / inr
        cap = [(x * k, y * k) for x, y in cell]
        pts = keys(a, r)
        # tile: 4 keys per row, 3 rows, starting at row 1 col 1
        tile = {(i, j) for i in range(1, 5) for j in range(1, 4)}
        for x, y, i, j in pts:
            intile = (i, j) in tile
            ax.add_patch(Polygon([(x + u, y + v) for u, v in cap], closed=True,
                                 fc="#f6c28b" if intile else "#eeeeee", ec="#8a5a2b" if intile else "#bbbbbb", lw=0.8))
            ax.add_patch(Rectangle((x - BODY / 2, y - BODY / 2), BODY, BODY, fc="none",
                                   ec="#2c5f9e", lw=0.9))
            # hot-swap socket (bottom side) outline, relative to the key centre
            ax.add_patch(Rectangle((x - 6.0, y - 6.8), 10.8, 6.0, fc="none", ec="#27ae60", lw=0.6, ls="--"))
            ax.plot(x, y, ".", c="#2c5f9e", ms=2)
        # neighbour distances of one key
        cx, cy = next((x, y) for x, y, i, j in pts if (i, j) == (2, 2))
        for dx, dy in ((a, 0), (a / 2, r), (-a / 2, r)):
            ax.annotate("", xy=(cx + dx, cy + dy), xytext=(cx, cy),
                        arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.2))
            ax.text(cx + dx * 0.55 + 0.8, cy + dy * 0.55, f"{math.hypot(dx, dy):.1f}", color="#c0392b", fontsize=8)
        tw = 4 * a
        ax.set_title(f"{title}\nrow {r:.1f} mm, tile 4x3 about {tw:.0f} x {3 * r:.0f} mm, "
                     f"cap {2 * inr * k:.1f} mm across", fontsize=10)
        ax.set_aspect("equal"); ax.set_xlim(-50, 95); ax.set_ylim(85, -15); ax.axis("off")
    fig.text(0.5, 0.02, "blue: MX switch body 15.6 mm (datasheet) - green dashed: hot-swap socket under the "
             "PCB - orange: one 4x3 tile, keycaps = Voronoi cell minus 0.8 mm - red: distance to neighbours (mm)",
             ha="center", fontsize=9)
    plt.tight_layout(rect=(0, 0.04, 1, 1))
    plt.savefig("docs/media/revc-pitch-comparison.png", dpi=110)


if __name__ == "__main__":
    main()
