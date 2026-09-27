#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Digitise the phone photo of the Analog Discovery 2 capture (2026-06-15) into CSV.

Calibration (pixels of the 2040x1530 original, found by detecting the grid lines):
  * vertical grid lines at the top band (y~365) and bottom band (y~1175) differ slightly
    (keystone from the photo angle) -> time is interpolated along y;
  * bottom-band lines 300, 507, 719, 928, 1140, 1351, 1560, 1769 px = -0.238 ... 2.072 us
    (0.33 us/div);
  * horizontal lines 443 ... 1386 px = 7.2 ... -2.4 V (1.2 V/div, ~99 px/V);
  * channel 2 (blue) is displayed with a +3.6 V offset, channel 1 (yellow) with 0 V.
Output: measurements/scope_2026-06-15.csv with t_ns, ch1_V, ch2_V (NaN where not found).
Run inside the ngspice container (numpy), after
  ffmpeg -i measurements/scope_2026-06-15_clock.jpg -vcodec ppm measurements/scope_2026-06-15.ppm
"""
import numpy as np

SRC = "measurements/scope_2026-06-15.ppm"
X_TOP = np.array([284, 496, 712, 927, 1144, 1361, 1576, 1791])   # y ~ 365
X_BOT = np.array([300, 507, 719, 928, 1140, 1351, 1560, 1769])   # y ~ 1175
T_US = -0.238 + 0.33 * np.arange(8)
Y_LINES = np.array([443, 564, 685, 804, 922, 1039, 1157, 1272, 1386])
V_LINES = 7.2 - 1.2 * np.arange(9)
CH2_OFFSET = 3.6


def load(path):
    d = open(path, "rb").read()
    head, rest = d.split(b"\n", 3)[:3], d.split(b"\n", 3)[3]
    w, h = map(int, head[1].split())
    return np.frombuffer(rest, np.uint8).reshape(h, w, 3).astype(int)


def x_to_t(x, y):
    a = np.clip((y - 365) / (1175 - 365), 0, 1)
    xs = X_TOP * (1 - a) + X_BOT * a
    return np.interp(x, xs, T_US, left=np.nan, right=np.nan) * 1e3 if xs[0] <= x <= xs[-1] else \
        (T_US[0] + (x - xs[0]) / (xs[1] - xs[0]) * 0.33) * 1e3


def y_to_v(y):
    k, q = np.polyfit(Y_LINES, V_LINES, 1)          # linear: extrapolates above the top line
    return k * y + q


def main():
    im = load(SRC)
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    blue = (R < 110) & (G > 140) & (B > 190)
    yellow = (R > 190) & (G > 170) & (B < 120)
    rows = []
    for x in range(110, im.shape[1] - 40):
        out = []
        for mask, band in ((yellow, (250, 1400)), (blue, (250, 1400))):   # y<250: WaveForms toolbar
            ys = np.nonzero(mask[band[0]:band[1], x])[0] + band[0]
            out.append(np.nan if len(ys) < 2 else float(np.median(ys)))
        yref = out[1] if not np.isnan(out[1]) else (out[0] if not np.isnan(out[0]) else 800)
        t = x_to_t(x, yref)
        v1 = y_to_v(out[0]) if not np.isnan(out[0]) else np.nan
        v2 = y_to_v(out[1]) - CH2_OFFSET if not np.isnan(out[1]) else np.nan
        rows.append((t, v1, v2))
    a = np.array(rows)
    np.savetxt("measurements/scope_2026-06-15.csv", a, delimiter=",", fmt="%.3f",
               header="t_ns,ch1_V,ch2_V", comments="")
    print("points:", len(a), "ch2 levels: low %.2f V high %.2f V" %
          (np.nanpercentile(a[:, 2], 10), np.nanpercentile(a[:, 2], 90)))


if __name__ == "__main__":
    main()
