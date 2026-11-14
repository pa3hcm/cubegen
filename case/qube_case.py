#!/usr/bin/env python3
"""
QubeRG cube case generator (ESP32 + Si5351 + 0.96" OLED + 4 buttons)
(c) 2026 PA3HCM - CC BY-NC 4.0

Generates the 3D-printable parts as STL files:

  stl/qube_bottom.stl   bottom part (floor + 4 walls), print as-is
  stl/qube_top.stl      top part (lid with SMA hole), already flipped for printing
  stl/qube_buttons.stl  4 button caps, print flange-down

Usage:
  pip install manifold3d numpy matplotlib
  python3 qube_case.py            # write STLs
  python3 qube_case.py --check    # also run a fit check against dummy boards
  python3 qube_case.py --preview  # also render preview PNGs to ../docs

All dimensions are in mm. MEASURE YOUR BOARDS and adjust the parameters
below before printing - board sizes differ between suppliers.

Coordinate system (assembled cube):
  X: left -> right   (USB connector on the LEFT side, x = 0)
  Y: front -> back   (display on the FRONT, y = 0; buttons on the BACK)
  Z: bottom -> top   (ESP32 on the bottom, SMA connector on TOP)
"""

import os
import sys
import struct

import numpy as np
from manifold3d import Manifold, CrossSection, FillRule

# =====================================================================
# Parameters
# =====================================================================

NAME = "QubeRG"         # engraved on the front

# ---- cube -------------------------------------------------------------
S = 90.0                # outer size of the cube
WALL = 3.0              # wall thickness
R_EDGE = 3.0            # rounding radius of the outer edges
SPLIT = 70.0            # height where bottom and top part meet
TONGUE_H = 6.0          # height of the tongue on the bottom part
TONGUE_T = 1.4          # thickness of the tongue
FIT = 0.2               # clearance between tongue and top part
SNAP_R = 0.6            # snap ridge radius (sticks out SNAP_R - FIT = 0.4)
SNAP_LEN = 20.0         # snap ridge length (one ridge per side)
ENGRAVE = 0.6           # engraving depth of text

# ---- ESP32 devboard (component side up, header pins pointing DOWN) -----
ESP_L = 55.0            # PCB length (USB end to antenna end)
ESP_W = 28.0            # PCB width
ESP_T = 1.6             # PCB thickness
ESP_LIFT = 20.0         # PCB bottom above floor (room for dupont plugs on the pins)
ESP_Y = S / 2           # PCB centre line (y)
USB_OVERHANG = 1.0      # USB connector sticks out this much past the PCB edge
USB_H = 3.0             # USB connector height above PCB
USB_HOLE_W = 12.0       # hole for the USB plug (width, height)
USB_HOLE_H = 8.0
ESP_HOOK_IN = 0.8       # how far the snap hooks reach over the PCB edge
ESP_HOOK_X = (0.5, 3.0) # hook/support zone measured from each PCB end

# ---- Si5351 board (hangs from the top on the SMA chain, SMAs pointing up)
SI_W = 40.0             # PCB width (along the edge with the SMA connectors)
SI_H = 30.0             # PCB height (perpendicular to that edge)
SI_T = 1.6
SMA_X = S / 2           # SMA bulkhead position on the top panel (centre)
SMA_Y = S / 2           # the Si5351 stands parallel to the front wall, right below it
SI_CLK0_OFF = 0.0       # CLK0 position on the SMA edge, relative to the board centre
SI_SMA_PITCH = 12.0     # spacing of the 3 SMA connectors (only used for the fit check)
SI_CHAIN = 26.0         # inner top surface -> Si5351 PCB edge (bulkhead + M-M adaptor + jack)
SMA_HOLE_D = 6.6        # hole for the SMA F-F bulkhead (1/4"-36 thread = 6.35 mm)

# ---- OLED display GM009605v4 (SSD1306 0.96") -----------------------------
D_W = 27.3              # PCB width
D_H = 27.8              # PCB height
D_T = 1.2               # PCB thickness
D_STACK = 2.4           # glass + adhesive in front of the PCB
D_CZ = 45.0             # PCB centre height
D_WIN_W = 24.0          # display window
D_WIN_H = 14.0
D_WIN_DZ = 1.5          # window centre above PCB centre (glass sits towards the header)

# ---- button board (4 tactile switches facing the back wall) ------------
B_W = 45.0              # PCB width
B_H = 20.0              # PCB height
B_T = 1.6
B_CZ = 45.0             # PCB centre height
B_XS = (-16.5, -5.5, 5.5, 16.5)   # switch positions relative to PCB centre (x, seen from inside)
B_SW_H = 5.0            # switch height incl. stem, above PCB
B_SW = 6.0              # switch body size
CAP_D = 6.0             # button cap plunger diameter
CAP_HOLE_D = 6.6        # hole in the back wall
CAP_FLANGE_D = 9.0      # cap flange (keeps the cap inside)
CAP_FLANGE_T = 1.2
CAP_OUT = 1.5           # cap sticks out of the wall this much
CAP_GAP = 0.3           # gap between cap and switch stem
BUTTON_LABELS = ("\u25B2", "\u25BC", "D", "M")   # button 1..4: up, down, Digit, Mode

# =====================================================================
# Helpers
# =====================================================================

SEG = 48


def box(x0, y0, z0, x1, y1, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl_z(cx, cy, z0, h, r, r2=None, seg=SEG):
    return Manifold.cylinder(h, r, r if r2 is None else r2, seg).translate((cx, cy, z0))


def cyl_y(cx, y0, cz, h, r, seg=SEG):
    # cylinder along +y starting at y0
    return Manifold.cylinder(h, r, r, seg).rotate((-90, 0, 0)).translate((cx, y0, cz))


def cyl_x(x0, cy, cz, h, r, seg=SEG):
    # cylinder along +x starting at x0
    return Manifold.cylinder(h, r, r, seg).rotate((0, 90, 0)).translate((x0, cy, cz))


def union(parts):
    parts = [p for p in parts if p is not None]
    return Manifold.batch_boolean(parts, manifold3d_add()) if parts else Manifold()


def manifold3d_add():
    from manifold3d import OpType
    return OpType.Add


def rounded_cube(size, r):
    pts = []
    for x in (r, size - r):
        for y in (r, size - r):
            for z in (r, size - r):
                pts.append(Manifold.sphere(r, 32).translate((x, y, z)))
    return Manifold.batch_hull(pts)


def text_section(s, height):
    """2D cross-section of a text string, centred on the origin."""
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    tp = TextPath((0, 0), s, size=height, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys = [np.asarray(p, dtype=float) for p in tp.to_polygons() if len(p) >= 3]
    cs = CrossSection(polys, FillRule.EvenOdd)
    (x0, y0, x1, y1) = cs.bounds()
    return cs.translate((-(x0 + x1) / 2, -(y0 + y1) / 2))


def engrave_front(s, h, x, z, depth=ENGRAVE):
    """Text cutter for the front face (y = 0), readable from the front."""
    m = Manifold.extrude(text_section(s, h), depth + 1).translate((0, 0, -depth))
    return m.rotate((90, 0, 0)).translate((x, 0, z))


def engrave_back(s, h, x, z, depth=ENGRAVE):
    m = Manifold.extrude(text_section(s, h), depth + 1).translate((0, 0, -depth))
    return m.rotate((90, 0, 0)).rotate((0, 0, 180)).translate((x, S, z))


def engrave_left(s, h, y, z, depth=ENGRAVE):
    m = Manifold.extrude(text_section(s, h), depth + 1).translate((0, 0, -depth))
    return m.rotate((90, 0, 0)).rotate((0, 0, -90)).translate((0, y, z))


def engrave_top(s, h, x, y, depth=ENGRAVE):
    m = Manifold.extrude(text_section(s, h), depth + 1)
    return m.translate((x, y, S - depth))


def wedge_hook(x0, x1, y_out, y_in, z0, thick):
    """Snap hook lip: flat underside at z0, sloped lead-in on top.
    y_out = side of the arm, y_in = tip reaching over the PCB."""
    lo_y, hi_y = min(y_out, y_in), max(y_out, y_in)
    bottom = box(x0, lo_y, z0, x1, hi_y, z0 + 0.4)
    tip = y_out + (0.15 if y_in > y_out else -0.15)
    lo2, hi2 = min(y_out, tip), max(y_out, tip)
    top = box(x0, lo2, z0 + thick, x1, hi2, z0 + thick + 0.01)
    return Manifold.batch_hull([bottom, top])


# =====================================================================
# Derived positions
# =====================================================================

IN0, IN1 = WALL, S - WALL                  # inner faces

# ESP32
ESP_X0 = IN0 + 0.3 + USB_OVERHANG
ESP_X1 = ESP_X0 + ESP_L
ESP_Y0 = ESP_Y - ESP_W / 2
ESP_Y1 = ESP_Y + ESP_W / 2
ESP_Z0 = IN0 + ESP_LIFT
ESP_Z1 = ESP_Z0 + ESP_T
USB_CZ = ESP_Z1 + USB_H / 2

# Display
D_X0, D_X1 = S / 2 - D_W / 2, S / 2 + D_W / 2
D_Z0, D_Z1 = D_CZ - D_H / 2, D_CZ + D_H / 2
D_PCB_Y0 = IN0 + D_STACK
D_PCB_Y1 = D_PCB_Y0 + D_T

# Buttons
B_X0, B_X1 = S / 2 - B_W / 2, S / 2 + B_W / 2
B_Z0, B_Z1 = B_CZ - B_H / 2, B_CZ + B_H / 2
B_STEM_Y = IN1 - CAP_FLANGE_T - CAP_GAP          # top of the switch stems
B_PCB_Y1 = B_STEM_Y - B_SW_H                      # switch side of the PCB
B_PCB_Y0 = B_PCB_Y1 - B_T                         # back side of the PCB

# Si5351
SI_TOP = IN1 - SI_CHAIN
SI_BOT = SI_TOP - SI_H
SI_XC = SMA_X - SI_CLK0_OFF                   # board centre (along x)

# =====================================================================
# Parts
# =====================================================================


def shell():
    return rounded_cube(S, R_EDGE) - box(IN0, IN0, IN0, IN1, IN1, IN1)


def snap_ridges(r):
    """Horizontal half-round ridges on the outer face of the tongue."""
    z = SPLIT + TONGUE_H / 2
    f = IN0 - TONGUE_T            # outer face of the tongue (front / left)
    b = IN1 + TONGUE_T            # outer face of the tongue (back / right)
    L = SNAP_LEN
    return [
        cyl_x(S / 2 - L / 2, f, z, L, r),
        cyl_x(S / 2 - L / 2, b, z, L, r),
        cyl_y(f, S / 2 - L / 2, z, L, r),
        cyl_y(b, S / 2 - L / 2, z, L, r),
    ]


def esp32_cradle():
    parts = []
    hz0, hz1 = ESP_HOOK_X
    for end in (0, 1):
        if end == 0:   # USB end
            xa, xb = ESP_X0 + hz0, ESP_X0 + hz1
        else:          # antenna end
            xa, xb = ESP_X1 - hz1, ESP_X1 - hz0
        # support block under the PCB end (between the header rows)
        blk = box(xa, ESP_Y0 + 0.7, IN0 - 0.01, xb, ESP_Y1 - 0.7, ESP_Z0)
        if end == 0:
            # notch for USB shell tabs under the PCB
            blk = blk - box(xa - 1, ESP_Y - 6, ESP_Z0 - 1.5, xb + 1, ESP_Y + 6, ESP_Z0 + 1)
        else:
            # end stop beyond the antenna end
            blk = blk + box(xb, ESP_Y0 + 0.7, IN0 - 0.01, ESP_X1 + 1.8, ESP_Y1 - 0.7, ESP_Z0)
            blk = blk + box(ESP_X1 + 0.3, ESP_Y0 + 0.7, IN0 - 0.01, ESP_X1 + 1.8, ESP_Y1 - 0.7, ESP_Z1 + 1.0)
        parts.append(blk)
        # flexible snap arms at both long edges
        for side in (0, 1):
            if side == 0:
                ya, yb = ESP_Y0 - 0.2 - 2.0, ESP_Y0 - 0.2
                y_out, y_in = yb, ESP_Y0 + ESP_HOOK_IN
            else:
                ya, yb = ESP_Y1 + 0.2, ESP_Y1 + 0.2 + 2.0
                y_out, y_in = ya, ESP_Y1 - ESP_HOOK_IN
            zt = ESP_Z1 + 0.15
            parts.append(box(xa, ya, IN0 - 0.01, xb, yb, zt + 1.4))
            parts.append(wedge_hook(xa, xb, y_out, y_in, zt, 1.4))
    return union(parts)


def display_mount():
    parts = []
    back = D_PCB_Y1 + 0.3            # back face of the slot
    lip_y1 = back + 1.5
    z_bot = D_Z0 - 2.0
    for side in (-1, 1):
        edge = D_X1 if side > 0 else D_X0
        gx0, gx1 = sorted((edge + side * 0.3, edge + side * 2.8))
        lx0, lx1 = sorted((edge - side * 1.2, edge + side * 2.8))
        guide = box(gx0, IN0 - 0.01, z_bot, gx1, lip_y1, SPLIT)
        lip = box(lx0, back, z_bot, lx1, lip_y1, SPLIT)
        # bottom stop with 45 degree underside (printable without support)
        stop_top = box(lx0, IN0 - 0.01, z_bot, lx1, lip_y1, D_Z0)
        stop_root = box(lx0, IN0 - 0.01, z_bot - (lip_y1 - IN0), lx1, IN0 + 0.01, D_Z0)
        parts += [guide, lip, Manifold.batch_hull([stop_top, stop_root])]
    return union(parts)


def buttons_mount():
    parts = []
    s0 = B_PCB_Y0 - 0.15
    s1 = B_PCB_Y1 + 0.15
    y_start = s0 - 1.5
    z_bot = B_Z0 - 2.0
    for side in (-1, 1):
        edge = B_X1 if side > 0 else B_X0
        bx0, bx1 = sorted((edge - side * 1.2, edge + side * 2.8))
        sx0, sx1 = sorted((edge - side * 1.3, edge + side * 0.3))
        rail = box(bx0, y_start, z_bot, bx1, IN1 + 0.01, SPLIT)
        rail = rail - box(sx0, s0, B_Z0 - 0.01, sx1, s1, SPLIT + 1)
        # 45 degree underside
        root = box(bx0, IN1 - 0.01, z_bot - (IN1 - y_start), bx1, IN1 + 0.01, z_bot + 0.01)
        under = Manifold.batch_hull([box(bx0, y_start, z_bot, bx1, IN1 + 0.01, z_bot + 0.01), root])
        parts += [rail, under]
    return union(parts)


def bottom_part():
    base = shell() ^ box(-1, -1, -1, S + 1, S + 1, SPLIT)
    tongue = (box(IN0 - TONGUE_T, IN0 - TONGUE_T, SPLIT - 0.01, IN1 + TONGUE_T, IN1 + TONGUE_T, SPLIT + TONGUE_H)
              - box(IN0, IN0, SPLIT - 1, IN1, IN1, SPLIT + TONGUE_H + 1))
    tongue = tongue + union(snap_ridges(SNAP_R))
    tongue = tongue ^ box(IN0 - TONGUE_T - 1, IN0 - TONGUE_T - 1, SPLIT - 0.01,
                          IN1 + TONGUE_T + 1, IN1 + TONGUE_T + 1, SPLIT + TONGUE_H)
    m = union([base, tongue, esp32_cradle(), display_mount(), buttons_mount()])

    cuts = []
    # display window with 45 degree chamfer on the outside
    wz = D_CZ + D_WIN_DZ
    win = box(S / 2 - D_WIN_W / 2, -1, wz - D_WIN_H / 2, S / 2 + D_WIN_W / 2, IN0 + 1, wz + D_WIN_H / 2)
    ch = 1.0
    cham = Manifold.batch_hull([
        box(S / 2 - D_WIN_W / 2 - ch, -0.01, wz - D_WIN_H / 2 - ch, S / 2 + D_WIN_W / 2 + ch, 0.0, wz + D_WIN_H / 2 + ch),
        box(S / 2 - D_WIN_W / 2, ch - 0.01, wz - D_WIN_H / 2, S / 2 + D_WIN_W / 2, ch, wz + D_WIN_H / 2),
    ])
    cuts += [win, cham.translate((0, -0.005, 0))]
    # USB hole (rounded rectangle) in the left wall
    rr = 1.5
    usb = Manifold.batch_hull([
        cyl_x(-1, ESP_Y + sy * (USB_HOLE_W / 2 - rr), USB_CZ + sz * (USB_HOLE_H / 2 - rr), IN0 + 2, rr)
        for sy in (-1, 1) for sz in (-1, 1)
    ])
    cuts.append(usb)
    # button holes in the back wall
    for bx in B_XS:
        cuts.append(cyl_y(S / 2 + bx, IN1 - 1, B_CZ, WALL + 2, CAP_HOLE_D / 2))
    # engravings
    cuts.append(engrave_front(NAME, 6.0, S / 2, (D_Z1 + SPLIT) / 2))
    cuts.append(engrave_left("USB", 4.0, ESP_Y, USB_CZ - USB_HOLE_H / 2 - 5))
    for i, bx in enumerate(B_XS):
        # symbols above the buttons; button 1..4 from left to right seen from the back
        cuts.append(engrave_back(BUTTON_LABELS[3 - i], 4.5, S / 2 + bx, B_CZ + 7.5))
    return m - union(cuts)


def top_part():
    top = shell() ^ box(-1, -1, SPLIT, S + 1, S + 1, S + 1)
    pocket = box(IN0 - TONGUE_T - FIT, IN0 - TONGUE_T - FIT, SPLIT - 1,
                 IN1 + TONGUE_T + FIT, IN1 + TONGUE_T + FIT, SPLIT + TONGUE_H + FIT)
    top = top - pocket - union(snap_ridges(SNAP_R + 0.1))

    zj = SPLIT + TONGUE_H + FIT   # above this the fingers may touch the walls
    fingers = []
    # display hold-down fingers (press on the top edge of the display PCB)
    for dx in (-10, 10):
        x0, x1 = S / 2 + dx - 1.5, S / 2 + dx + 1.5
        fingers.append(box(x0, IN0 + 0.3, D_Z1 + 0.3, x1, D_PCB_Y1, IN1 + 0.01))
        fingers.append(box(x0, IN0 - 0.01, zj, x1, D_PCB_Y1, IN1 + 0.01))
    # button board hold-down fingers
    for dx in (-11, 11):
        x0, x1 = S / 2 + dx - 1.5, S / 2 + dx + 1.5
        fingers.append(box(x0, B_PCB_Y0 + 0.1, B_Z1 + 0.3, x1, IN1 - 0.3, IN1 + 0.01))
        fingers.append(box(x0, B_PCB_Y0 + 0.1, zj, x1, IN1 + 0.01, IN1 + 0.01))
    top = top + union(fingers)

    cuts = [cyl_z(SMA_X, SMA_Y, IN1 - 1, WALL + 2, SMA_HOLE_D / 2)]
    # pry notch on the right side, to open the cube with a coin / screwdriver
    cuts.append(box(S - (IN0 - TONGUE_T - FIT) - 0.01, S / 2 - 6, SPLIT - 0.01, S + 1, S / 2 + 6, SPLIT + 1.5))
    cuts.append(engrave_top("RF", 6.0, SMA_X, SMA_Y - 11))
    return top - union(cuts)


def button_cap():
    flange = cyl_z(0, 0, 0, CAP_FLANGE_T, CAP_FLANGE_D / 2)
    plen = WALL + CAP_OUT
    plunger = cyl_z(0, 0, CAP_FLANGE_T - 0.01, plen - 0.5 + 0.01, CAP_D / 2)
    tip = cyl_z(0, 0, CAP_FLANGE_T + plen - 0.5, 0.5, CAP_D / 2, CAP_D / 2 - 0.5)
    return flange + plunger + tip


def button_caps_print():
    caps = [button_cap().translate((i * (CAP_FLANGE_D + 4), 0, 0)) for i in range(4)]
    return union(caps)


def button_caps_assembled():
    """Caps in their assembled position (flange against the back wall)."""
    caps = []
    for bx in B_XS:
        c = button_cap().rotate((-90, 0, 0))      # flange at y=0, plunger towards +y
        caps.append(c.translate((S / 2 + bx, IN1 - CAP_FLANGE_T, B_CZ)))
    return union(caps)


# =====================================================================
# Dummy boards for the fit check
# =====================================================================


def dummies():
    d = {}
    # ESP32: PCB, module, USB, header strips + pins + dupont plugs below
    esp = box(ESP_X0, ESP_Y0, ESP_Z0, ESP_X1, ESP_Y1, ESP_Z1)
    esp += box(ESP_X1 - 18, ESP_Y - 9, ESP_Z1, ESP_X1, ESP_Y + 9, ESP_Z1 + 3.2)
    esp += box(ESP_X0 - USB_OVERHANG, ESP_Y - 4, ESP_Z1, ESP_X0 + 5, ESP_Y + 4, ESP_Z1 + USB_H)
    for ya, yb in ((ESP_Y0, ESP_Y0 + 2.54), (ESP_Y1 - 2.54, ESP_Y1)):
        esp += box(ESP_X0 + 3.3, ya, ESP_Z0 - 16.5, ESP_X1 - 3.3, yb, ESP_Z0)
    d["ESP32 + dupont plugs"] = esp
    d["USB plug"] = box(-25, ESP_Y - 5.5, USB_CZ - 3.5, IN0 - 0.3 - USB_OVERHANG, ESP_Y + 5.5, USB_CZ + 3.5) \
        - box(-26, -100, -100, 0, 100, 100) + box(IN0 - 0.3 - USB_OVERHANG - 1.0, ESP_Y - 4, USB_CZ - 1.3,
                                                IN0 - 0.3 - USB_OVERHANG + 0.01, ESP_Y + 4, USB_CZ + 1.3)
    # Display: PCB, glass, header + dupont plugs at the back
    disp = box(D_X0, D_PCB_Y0, D_Z0, D_X1, D_PCB_Y1, D_Z1)
    disp += box(S / 2 - 26.7 / 2, IN0 + 0.05, D_Z1 - 4.0 - 19.3, S / 2 + 26.7 / 2, D_PCB_Y0, D_Z1 - 4.0)
    disp += box(S / 2 - 5.1, D_PCB_Y1, D_Z1 - 2.6, S / 2 + 5.1, D_PCB_Y1 + 25, D_Z1)
    d["display"] = disp
    # Buttons: PCB, switches, header + plugs on the back side
    btn = box(B_X0, B_PCB_Y0, B_Z0, B_X1, B_PCB_Y1, B_Z1)
    for bx in B_XS:
        btn += box(S / 2 + bx - B_SW / 2, B_PCB_Y1, B_CZ - B_SW / 2, S / 2 + bx + B_SW / 2, B_PCB_Y1 + 3.5, B_CZ + B_SW / 2)
        btn += cyl_y(S / 2 + bx, B_PCB_Y1 + 3.4, B_CZ, B_SW_H - 3.4, 1.75)
    btn += box(S / 2 - 6.5, B_PCB_Y0 - 25, B_Z1 - 2.6, S / 2 + 6.5, B_PCB_Y0, B_Z1)
    d["button board"] = btn
    # Si5351: PCB, components, 3 SMA jacks, adaptor + bulkhead up to the top
    si = box(SI_XC - SI_W / 2, SMA_Y - SI_T / 2, SI_BOT, SI_XC + SI_W / 2, SMA_Y + SI_T / 2, SI_TOP)
    si += box(SI_XC - SI_W / 2 + 2, SMA_Y + SI_T / 2, SI_BOT + 2, SI_XC + SI_W / 2 - 2, SMA_Y + SI_T / 2 + 3, SI_TOP - 2)
    for k in (-1, 0, 1):
        si += cyl_z(SMA_X + k * SI_SMA_PITCH, SMA_Y, SI_TOP, 9, 4.0)
    si += cyl_z(SMA_X, SMA_Y, SI_TOP + 8.9, IN1 - SI_TOP - 8.9 - 0.02, 4.6)
    d["Si5351 + SMA chain"] = si
    return d


# =====================================================================
# Output
# =====================================================================


def write_stl(m, path, name):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=np.float32)[:, :3]
    t = np.asarray(mesh.tri_verts, dtype=np.int64)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    n = np.cross(b - a, c - a)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.where(ln == 0, 1, ln)
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("a", "<f4", 3), ("b", "<f4", 3), ("c", "<f4", 3), ("attr", "<u2")])
    rec["n"], rec["a"], rec["b"], rec["c"] = n, a, b, c
    with open(path, "wb") as f:
        f.write(name.encode()[:80].ljust(80, b" "))
        f.write(struct.pack("<I", len(t)))
        f.write(rec.tobytes())


def on_bed(m):
    (x0, y0, z0, x1, y1, z1) = m.bounding_box()
    return m.translate((-(x0 + x1) / 2, -(y0 + y1) / 2, -z0))


def fit_check(bottom, top, caps):
    print("Fit check (overlap volumes in mm^3, should be ~0):")
    ok = True
    case = {"bottom": bottom, "top": top, "button caps": caps}
    for dn, dm in dummies().items():
        for cn, cm in case.items():
            v = (dm ^ cm).volume()
            if v > 0.01:
                ok = False
                print(f"  COLLISION  {dn:22s} x {cn:12s}: {v:8.2f}")
    # parts against each other (snap ridges are an intentional interference)
    ridges = union(snap_ridges(SNAP_R + 0.1))
    v = ((bottom ^ top) - ridges).volume()
    print(f"  bottom x top (excluding snap ridges): {v:.2f}")
    ok &= v < 0.01
    v = (caps ^ (bottom + top)).volume()
    print(f"  button caps x case: {v:.2f}")
    ok &= v < 0.01
    print("  result:", "OK" if ok else "PROBLEMS FOUND")
    return ok


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "stl")
    os.makedirs(out, exist_ok=True)

    bottom = bottom_part()
    top = top_part()
    caps_asm = button_caps_assembled()

    write_stl(on_bed(bottom), os.path.join(out, "qube_bottom.stl"), "QubeRG bottom")
    write_stl(on_bed(top.rotate((180, 0, 0))), os.path.join(out, "qube_top.stl"), "QubeRG top")
    write_stl(on_bed(button_caps_print()), os.path.join(out, "qube_buttons.stl"), "QubeRG button caps")
    for n, m in (("bottom", bottom), ("top", top)):
        print(f"{n}: volume {m.volume() / 1000:.1f} cm^3, {m.num_tri()} triangles, genus {m.genus()}")

    if "--check" in sys.argv:
        fit_check(bottom, top, caps_asm)
    if "--preview" in sys.argv:
        import qube_preview
        qube_preview.render(bottom, top, caps_asm, dummies(), os.path.join(here, "..", "docs"))


if __name__ == "__main__":
    main()
