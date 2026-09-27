#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Draw how tiles tessellate: rev A/B (key board + logic board under it) vs rev C (single
board). Coordinates are the real ones (mm, key-board frame, y down), taken from the rev-B
board: key-board outline, logic-board outline and edge-connector pads mapped by the stack
offset (+10.96, -60.90), tile lattice (+80, 0) right and (+10, -51.96) up.
Output: docs/media/revc-lattice.png (runs in the ngspice container, needs matplotlib)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

KEY = [(127.5, 45), (204.5, 45), (204.5, 61), (194.5, 61), (194.5, 79), (184.5, 79), (184.5, 96),
       (107.5, 96), (107.5, 80), (117.5, 80), (117.5, 62), (127.5, 62)]
LOGIC = (119.96, 47.85, 193.21 - 119.96, 93.10 - 47.85)
SW = [(135.92, 53.08), (155.92, 53.08), (175.92, 53.08), (195.92, 53.08),
      (125.96, 70.40), (145.96, 70.40), (165.96, 70.40), (185.96, 70.40),
      (115.92, 87.72), (135.92, 87.72), (155.96, 87.72), (175.96, 87.72)]
# edge connector pad rows in key-board coordinates (rev A/B)
CONN = {"J101 left": [(123.61, 63.9 + 2.54 * i) for i in range(6)],
        "J104 right": [(189.70, 63.87 + 2.54 * i) for i in range(6)],
        "J102 top": [(152.22 + 2.54 * i, 51.45) for i in range(8)],
        "J103 bottom": [(142.22 + 2.54 * i, 89.51) for i in range(8)]}
# rev C concept: contacts on the edge segments that face the neighbour (1.27 mm pitch)
REVC = {"left (passive)": [(117.5, 66.2 + 1.27 * i) for i in range(6)],
        "right (springs)": [(194.5, 66.2 + 1.27 * i) for i in range(6)],
        "top (passive)": [(150.0 + 1.27 * i, 45.0) for i in range(8)],
        "bottom (springs)": [(140.0 + 1.27 * i, 96.0) for i in range(8)]}
LAT = [(i * 80 + j * 10, -j * 51.96) for j in range(2) for i in range(3)]


def tile(ax, dx, dy, rev_c):
    ax.add_patch(Polygon([(x + dx, y + dy) for x, y in KEY], closed=True, fc="#dde8f7", ec="#2c5f9e", lw=1.2))
    for x, y in SW:
        ax.add_patch(Rectangle((x + dx - 7, y + dy - 7), 14, 14, fc="white", ec="#9aa9bb", lw=0.6))
    if not rev_c:
        x, y, w, h = LOGIC
        ax.add_patch(Rectangle((x + dx, y + dy), w, h, fc="none", ec="#2e8b57", lw=1.4, ls="--"))
        for name, pads in CONN.items():
            xs = [p[0] + dx for p in pads]; ys = [p[1] + dy for p in pads]
            ax.plot(xs, ys, "s", ms=2.2, c="#c0392b")
    else:
        for name, pads in REVC.items():
            xs = [p[0] + dx for p in pads]; ys = [p[1] + dy for p in pads]
            ax.plot(xs, ys, "o", ms=2.2, c="#c0392b" if "springs" in name else "#e67e22")


def main():
    fig, axs = plt.subplots(1, 2, figsize=(16, 7.6))
    for ax, rev_c, title in ((axs[0], False, "rev A/B: logic board (dashed) under the stepped key board"),
                             (axs[1], True, "rev C: one board, contacts on the stepped edges")):
        for dx, dy in LAT:
            tile(ax, dx, dy, rev_c)
        # mating links of the middle-bottom tile
        ox, oy = 80, 0
        if not rev_c:
            ax.annotate("", xy=(203.61 + ox, 70.2 + oy), xytext=(189.70 + ox, 70.2 + oy),
                        arrowprops=dict(arrowstyle="<->", color="k"))
            ax.annotate("", xy=(161.1 + ox, 37.55 + oy), xytext=(161.1 + ox, 51.45 + oy),
                        arrowprops=dict(arrowstyle="<->", color="k"))
            ax.text(196 + ox, 67 + oy, "13.9 mm\nalong x", fontsize=7, ha="center")
            ax.text(163 + ox, 44 + oy, "13.9 mm along y", fontsize=7)
        ax.set_title(title, fontsize=10)
        ax.set_aspect("equal"); ax.set_ylim(105, -35)
        ax.set_xlabel("mm"); ax.grid(alpha=.15)
    axs[0].text(105, -12, "lattice: right (+80, 0) mm, up (+10, -51.96) mm\n"
                         "J102 (top) and J103 (bottom) are 10 mm apart in x,\nso every link stays straight",
                fontsize=8, va="bottom")
    axs[1].text(105, -12, "orange = passive pads / castellations (top, left)\n"
                         "red = spring contacts (bottom, right)\n"
                         "top contacts sit 10 mm right of the bottom ones",
                fontsize=8, va="bottom")
    plt.tight_layout()
    plt.savefig("docs/media/revc-lattice.png", dpi=110)


if __name__ == "__main__":
    main()
