"""
Preview renderer for the QubeRG case (matplotlib, no OpenGL needed).
(c) 2026 PA3HCM - CC BY-NC 4.0

Called from qube_case.py --preview. Writes:
  docs/qubeRG.png        the finished product
  docs/case_inside.png   inside view: bottom part with boards, top part with Si5351
"""

import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import qube_case as qc
from qube_case import Manifold, box, cyl_z

CASE_COLOR = (0.93, 0.45, 0.10)      # orange PETG
CASE_COLOR2 = (0.20, 0.22, 0.25)     # dark grey PETG (top)
GOLD = (0.85, 0.68, 0.25)


def tris(m, color, max_len=3.0):
    m = m.refine_to_length(max_len)
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    t = np.asarray(mesh.tri_verts)
    return v[t], np.tile(np.asarray(color, float), (len(t), 1))


def draw(ax, items, elev, azim, light=(-0.35, -0.75, 0.75), lim=None):
    polys = np.concatenate([p for p, _ in items])
    cols = np.concatenate([c for _, c in items])
    n = np.cross(polys[:, 1] - polys[:, 0], polys[:, 2] - polys[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    L = np.asarray(light, float)
    L /= np.linalg.norm(L)
    shade = 0.42 + 0.58 * np.clip(n @ L, 0, 1)
    fc = np.clip(cols * shade[:, None], 0, 1)
    pc = Poly3DCollection(polys, facecolors=fc, edgecolors=fc, linewidths=0.15)
    ax.add_collection3d(pc)
    lo, hi = lim if lim else (polys.reshape(-1, 3).min(0), polys.reshape(-1, 3).max(0))
    c = (np.asarray(lo) + np.asarray(hi)) / 2
    r = (np.asarray(hi) - np.asarray(lo)).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()


def sma_connector():
    S = qc.S
    hexf = Manifold.cylinder(2.0, 4.6, 4.6, 6).translate((qc.SMA_X, qc.SMA_Y, S))
    body = cyl_z(qc.SMA_X, qc.SMA_Y, S + 2.0, 7.0, 3.17)
    pin = cyl_z(qc.SMA_X, qc.SMA_Y, S + 2.0, 7.2, 2.2) - cyl_z(qc.SMA_X, qc.SMA_Y, S + 4.0, 6.0, 1.9)
    return body - cyl_z(qc.SMA_X, qc.SMA_Y, S + 4.0, 6.0, 2.4) + pin, hexf


def render(bottom, top, caps, dummies, outdir):
    os.makedirs(outdir, exist_ok=True)
    S = qc.S

    # ------------------------------------------------------------------ product
    sma_body, sma_hex = sma_connector()
    glass = box(S / 2 - 13, qc.IN0 + 0.05, qc.D_Z1 - 23.3, S / 2 + 13, qc.D_PCB_Y0, qc.D_Z1 - 4.0)
    inner = box(qc.IN0 + 0.5, qc.IN0 + 4, qc.IN0 + 0.5, qc.IN1 - 0.5, qc.IN1 - 0.5, qc.IN1 - 0.5)
    usb = box(qc.IN0 - 0.3 - qc.USB_OVERHANG, qc.ESP_Y - 4, qc.ESP_Z1, qc.IN0 + 4, qc.ESP_Y + 4, qc.ESP_Z1 + qc.USB_H)
    items = [
        tris(bottom, CASE_COLOR), tris(top, CASE_COLOR2), tris(caps, CASE_COLOR2),
        tris(glass, (0.03, 0.03, 0.05)), tris(inner, (0.10, 0.10, 0.10), 8),
        tris(usb, (0.75, 0.75, 0.78)),
        tris(sma_body, GOLD, 1.0), tris(sma_hex, GOLD, 1.0),
    ]
    fig = plt.figure(figsize=(8, 8), dpi=150)
    ax = fig.add_subplot(projection="3d")
    draw(ax, items, elev=24, azim=-118, lim=((0, 0, 0), (S, S, S + 9)))
    wz = qc.D_CZ + qc.D_WIN_DZ
    ax.text(S / 2, -0.2, wz + 1.2, "10.000.000", zdir="x", color=(0.5, 0.95, 1.0),
            fontsize=13, family="DejaVu Sans Mono", ha="center", va="center", zorder=10)
    ax.text(S / 2, -0.2, wz - 4.0, "Mode: OFF", zdir="x", color=(0.5, 0.95, 1.0),
            fontsize=7, family="DejaVu Sans Mono", ha="center", va="center", zorder=10)
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(os.path.join(outdir, "qubeRG.png"), facecolor="white")
    plt.close(fig)

    # ------------------------------------------------------------------ inside
    colors = {
        "ESP32 + dupont plugs": (0.15, 0.25, 0.45),
        "USB plug": (0.6, 0.6, 0.6),
        "display": (0.10, 0.30, 0.65),
        "button board": (0.15, 0.45, 0.20),
        "Si5351 + SMA chain": (0.45, 0.15, 0.55),
    }
    fig = plt.figure(figsize=(14, 7), dpi=130)
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    items = [tris(bottom, CASE_COLOR), tris(caps, CASE_COLOR2)]
    items += [tris(m, colors[n]) for n, m in dummies.items() if n not in ("Si5351 + SMA chain", "USB plug")]
    draw(ax1, items, elev=52, azim=-62, light=(0.3, -0.5, 0.8), lim=((0, 0, 0), (S, S, S)))
    ax1.set_title("Bottom part: ESP32 (snap hooks), display & button board (slide-in rails)", fontsize=10)

    ax2 = fig.add_subplot(1, 2, 2, projection="3d")
    flip = lambda m: m.rotate((180, 0, 0)).translate((0, S, S))
    items = [tris(flip(top), CASE_COLOR2), tris(flip(dummies["Si5351 + SMA chain"]), colors["Si5351 + SMA chain"]),
             tris(flip(sma_body), GOLD, 1.0), tris(flip(sma_hex), GOLD, 1.0)]
    draw(ax2, items, elev=40, azim=-62, light=(0.3, -0.5, 0.8), lim=((0, 0, 0), (S, S, S)))
    ax2.set_title("Top part (upside down): SMA bulkhead with Si5351, hold-down fingers", fontsize=10)
    fig.subplots_adjust(0, 0, 1, 0.95, 0.0)
    fig.savefig(os.path.join(outdir, "case_inside.png"), facecolor="white")
    plt.close(fig)
    print("previews written to", os.path.abspath(outdir))
