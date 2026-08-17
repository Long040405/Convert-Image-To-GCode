"""
Image to G-Code Converter — Advanced 7-Method Engine
=====================================================
Converts images into standard CNC / Plotter G-Code for 3-Axis Linear Motion Systems (X, Y, Z).

7 DRAWING ALGORITHMS:
  1. COLOR    — Flat color artwork (cartoons, logos, vector graphics) → color boundaries
  2. PORTRAIT — Human portrait photography → facial feature lines (normalized XDoG)
  3. LINE     — General images → uniform skeleton lines (centerline 1px) [default]
  4. CONTOUR  — Dark region perimeter tracing with optional centerline reduction
  5. RASTER   — Continuous tone area infill (zigzag / hatching / offset contours)
  6. EDGE     — High-precision Canny edge detection
  7. TEXT     — Direct text engraving (supports Unicode fonts) without requiring input images

FLAT COLOR (COLOR): Converts images to Lab color space, applies k-means color quantization,
and generates crisp 1px closed-loop boundary strokes between adjacent color clusters.

PORTRAIT (PORTRAIT): Employs Extended Difference of Gaussians (XDoG) normalized by standard
deviation to extract continuous hand-drawn sketch lines from continuous-tone portrait photos.

UNIFORM LINE (LINE): Skeletonizes dark regions into single 1px centerlines to ensure consistent
tool stroke width and eliminate duplicate perimeter passes.

CONTOUR (CONTOUR): Traces region boundaries with nearest-neighbor path optimization.
Supports centerline reduction to convert thick lines into single passes.

AREA INFILL (RASTER): High-efficiency area infill patterns designed to minimize Z-axis hops:
  - zigzag : continuous zigzag path connecting alternating raster rows (minimal pen-up hops)
  - hatch  : parallel directional shading lines
  - offset : concentric offset contours shrinking inward from the outer perimeter

TEXT ENGRAVING (TEXT): Renders system TrueType/OpenType fonts at exact physical millimeter
dimensions, skeletonized to single-stroke handwriting paths.

CIRCULAR ARCS (G2/G3): Fits curved point sequences into circular G2/G3 (I/J) arc commands,
reducing file size and preventing machine stuttering.

Usage:
    python image_to_gcode.py                          # Open GUI interface
    python image_to_gcode.py input.png                # CLI, default: LINE + Arcs
    python image_to_gcode.py cartoon.jpg color out.gcode
    python image_to_gcode.py portrait.jpg portrait out.gcode
    python image_to_gcode.py input.png line out.gcode
    python image_to_gcode.py input.png line --no-arcs      # Linear G1 only
    python image_to_gcode.py input.png line --no-uniform   # Outline contours
    python image_to_gcode.py "Hello World" text out.gcode  # Direct text engraving

OUTPUT FORMAT SPECIFICATION:
    N10 G90
    N20 G1 Z0 F800           ; Pen up
    N30 G1 X50 Y100 F1500    ; Rapid travel
    N40 G1 Z-10 F800         ; Pen down
    N50 G2 X50 Y100 I50 J0 F1000
    N60 G1 Z0 F800           ; Pen up
    N70 G1 X1 Y1 F2000       ; Return to park position
    N80 G1 Z0 F800           ; Resting Z height

Requirements:
    pip install opencv-python numpy Pillow
    (optional: opencv-contrib-python for accelerated skeletonization)
"""

import contextlib
import cv2
import math
import numpy as np
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk


# ============================================================
# MACHINE CONFIGURATION
# ============================================================
class MachineConfig:
    """Configuration parameters for 3-Axis Linear Motion Systems."""

    def __init__(self):
        # Work area dimensions (mm)
        self.work_area_x = 150.0
        self.work_area_y = 150.0

        # Z-axis heights (mm) — Higher Z = Pen UP, Lower Z = Pen DOWN
        self.z_pen_up = 0.0        # Pen retracted (rapid travel)
        self.z_pen_down = -10.0    # Pen engaged on drawing surface
        self.z_end = 0.0           # Resting Z position at program end

        # Feed rates (mm/min)
        self.feed_rate_draw = 1000
        self.feed_rate_travel = 1500
        self.feed_rate_z = 800
        self.feed_rate_return = 2000    # Feed rate for returning to park position

        # Output G-Code format
        self.line_numbers = True        # Prepend line numbers (N10, N20, N30...)
        self.line_number_start = 10
        self.line_number_step = 10
        self.emit_comments = False      # Include ';' comment lines
        self.use_g0 = False             # False = use G1 for rapid travels
        self.init_codes = ["G90"]       # Initialization commands
        self.end_codes = []             # Program end commands (e.g. ["M2"])
        self.park_x = 1.0               # Park position X (mm)
        self.park_y = 1.0               # Park position Y (mm)

        # General image processing
        self.threshold = 128
        self.invert = True
        self.blur_size = 3

        # Contour tracing
        self.min_contour_points = 5
        self.simplify_epsilon = 1.0
        self.contour_centerline = True  # Reduce thick contours to 1px centerline

        # Area infill (Raster)
        self.raster_resolution = 0.5   # Infill line spacing / pen stroke width (mm)
        self.raster_style = 'zigzag'   # 'zigzag', 'hatch', or 'offset'
        self.raster_angle = 45.0       # Raster line angle in degrees (0 = horizontal)
        self.raster_cross = False      # Cross-hatching (orthogonal second pass)
        self.raster_outline = True     # Trace boundary outline before infill
        self.raster_supersample = 2    # Internal supersampling multiplier
        self.raster_smooth = 1         # Post-raster polyline smoothing iterations

        # Edge detection (Canny)
        self.canny_low = 50
        self.canny_high = 150

        # Uniform Line (Skeletonization)
        self.uniform_stroke = True
        self.line_min_length = 8.0     # Discard stroke segments shorter than (px)
        self.line_simplify = 0.8       # Polyline simplification tolerance (px)
        self.line_smooth = 3           # Moving average anti-aliasing radius
        self.line_bridge_px = 2        # Bridge small gaps before skeletonization
        self.adaptive_threshold = False  # Adaptive thresholding for uneven lighting
        self.despeckle = True          # Morphological open for noise removal
        self.blob_outline = True       # Trace perimeters for solid fills

        # Flat Color boundaries (Color)
        self.color_levels = 8          # Number of color clusters (k-means)
        self.color_denoise = 5         # Median blur window before clustering
        self.color_min_area = 20       # Discard boundary fragments smaller than (px)

        # Portrait sketching (Portrait)
        self.portrait_denoise = 40.0   # Bilateral filter smoothing parameter
        self.portrait_detail = 1.3     # XDoG sigma — smaller = finer details
        self.portrait_sensitivity = 0.6 # XDoG threshold relative to standard deviation
        self.portrait_min_area = 12    # Discard speckles smaller than (px)
        self.portrait_phi = 3.0        # Tanh sharpness multiplier

        # Text engraving (Text)
        self.text_content = "Hello World"
        self.text_font = "arial"       # Font family name or file path
        self.text_height = 20.0        # Capital letter height (mm)
        self.text_line_spacing = 1.35  # Line spacing multiplier
        self.text_align = 'center'     # 'left', 'center', or 'right'
        self.text_margin = 10.0        # Margin around work area (mm)
        self.text_style = 'single'     # 'single' = single-stroke | 'outline' = hollow
        self.text_autofit = False      # Auto-scale text to fill work area
        self.text_render_scale = 8.0   # Rendering resolution (px per mm)

        # Circular arc fitting (G2/G3)
        self.use_arcs = True
        self.arc_tolerance = 0.3       # Maximum chord error for arc fitting (mm)
        self.arc_min_points = 5        # Minimum points required to fit an arc
        self.arc_max_radius = 500.0    # Maximum arc radius before treating as line (mm)
        self.arc_min_sweep_deg = 12.0  # Minimum arc sweep angle in degrees

        # Global coordinate offsets
        self.offset_x = 0.0
        self.offset_y = 0.0

        # Placement within work area
        self.place_mode = 'fit'        # 'fit' = centered full fit, 'manual' = custom
        self.place_x = 25.0            # Custom placement origin X (mm)
        self.place_y = 25.0            # Custom placement origin Y (mm)
        self.place_w = 100.0           # Custom placement width (mm)
        self.place_h = 100.0           # Custom placement height (mm)
        self.place_keep_ratio = True   # Preserve aspect ratio in manual mode


# ============================================================
# SHARED UTILITY FUNCTIONS
# ============================================================
def place_box(img_w, img_h, config):
    """Calculates placement bounding box (left_x, bottom_y, width, height) in mm."""
    if getattr(config, 'place_mode', 'fit') == 'manual':
        bx, by = config.place_x, config.place_y
        bw, bh = max(0.1, config.place_w), max(0.1, config.place_h)
    else:
        bx, by, bw, bh = 0.0, 0.0, config.work_area_x, config.work_area_y

    sx, sy = bw / img_w, bh / img_h
    if getattr(config, 'place_keep_ratio', True) or config.place_mode != 'manual':
        sx = sy = min(sx, sy)
    aw, ah = img_w * sx, img_h * sy
    return bx + (bw - aw) / 2, by + (bh - ah) / 2, aw, ah


def mm_per_px(img_w, img_h, config):
    """Calculates physical millimeter size per pixel based on placement box."""
    _, _, aw, ah = place_box(img_w, img_h, config)
    return min(aw / img_w, ah / img_h)


def px_to_mm(px_x, px_y, img_w, img_h, config):
    """Converts pixel coordinates to machine coordinates (inverts Y axis)."""
    ox, oy, aw, ah = place_box(img_w, img_h, config)
    mm_x = px_x * (aw / img_w) + ox + config.offset_x
    mm_y = (img_h - px_y) * (ah / img_h) + oy + config.offset_y
    return round(mm_x, 3), round(mm_y, 3)


def fmt(v):
    """Formats numeric coordinates cleanly: 50.0 -> '50', 94.7570 -> '94.757'."""
    s = f"{float(v):.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def cmd_pen_up(config):
    code = "G0" if config.use_g0 else "G1"
    return f"{code} Z{fmt(config.z_pen_up)} F{fmt(config.feed_rate_z)}"


def cmd_pen_down(config):
    return f"G1 Z{fmt(config.z_pen_down)} F{fmt(config.feed_rate_z)}"


def cmd_travel(config, x, y):
    code = "G0" if config.use_g0 else "G1"
    return f"{code} X{fmt(x)} Y{fmt(y)} F{fmt(config.feed_rate_travel)}"


def finalize_gcode(lines, config):
    """Filters comments and formats line numbers prior to writing G-Code."""
    out = []
    n = int(config.line_number_start)
    step = int(config.line_number_step)
    for ln in lines:
        s = ln.rstrip()
        is_comment = (not s) or s.lstrip().startswith(";")
        if is_comment and not config.emit_comments:
            continue
        if config.line_numbers and not is_comment:
            out.append(f"N{n} {s}")
            n += step
        else:
            out.append(s)
    return "\n".join(out)


def gcode_header(config, method_name, img_w, img_h, extra_info=""):
    ox, oy, aw, ah = place_box(img_w, img_h, config)
    scale = mm_per_px(img_w, img_h, config)
    lines = [
        "; =============================================",
        "; G-Code — Image to G-Code Converter",
        f"; Method: {method_name}",
        f"; Work area: {config.work_area_x} x {config.work_area_y} mm",
        f"; Scale: {scale:.4f} mm/px",
        f"; Drawing size: {aw:.1f} x {ah:.1f} mm",
        f"; Placed at: X {ox:.1f} -> {ox + aw:.1f} | Y {oy:.1f} -> {oy + ah:.1f} mm"
        + ("  (custom)" if getattr(config, 'place_mode', 'fit') == 'manual' else "  (centered)"),
        f"; Feed draw: {config.feed_rate_draw} | Feed travel: {config.feed_rate_travel}",
    ]
    if extra_info:
        lines.append(f"; {extra_info}")
    lines += [
        "; =============================================",
        ";  G1 = Linear move / draw",
        ";  G2 = Clockwise circular arc (I/J = center offset from start)",
        ";  G3 = Counter-clockwise circular arc (I/J = center offset from start)",
        "; =============================================",
        "",
        "; --- INITIALIZATION ---",
    ]
    lines += list(config.init_codes)
    lines.append("")
    return lines


def gcode_footer(config, stats_lines=None):
    code = "G0" if config.use_g0 else "G1"
    lines = [
        "; --- END ---",
        cmd_pen_up(config),
        f"{code} X{fmt(config.park_x)} Y{fmt(config.park_y)} "
        f"F{fmt(config.feed_rate_return)}",
        f"G1 Z{fmt(config.z_end)} F{fmt(config.feed_rate_z)}",
    ]
    lines += list(config.end_codes)
    lines.append("")
    if stats_lines:
        lines += stats_lines
    return lines


# ============================================================
# SKELETONIZATION (CENTERLINE EXTRACTION)
# ============================================================
_NB8 = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def _zhang_suen(binary):
    """Pure NumPy implementation of Zhang-Suen thinning algorithm."""
    skel = (binary > 0).astype(np.uint8)
    h, w = skel.shape
    for _ in range(200):
        removed_any = False
        for step in (0, 1):
            p = np.pad(skel, 1)
            P2 = p[0:h,   1:w+1]; P3 = p[0:h,   2:w+2]
            P4 = p[1:h+1, 2:w+2]; P5 = p[2:h+2, 2:w+2]
            P6 = p[2:h+2, 1:w+1]; P7 = p[2:h+2, 0:w]
            P8 = p[1:h+1, 0:w];   P9 = p[0:h,   0:w]

            B = (P2.astype(np.int16) + P3 + P4 + P5 + P6 + P7 + P8 + P9)

            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = np.zeros((h, w), np.int16)
            for k in range(8):
                A += ((seq[k] == 0) & (seq[k + 1] == 1)).astype(np.int16)

            if step == 0:
                c1 = (P2 * P4 * P6 == 0)
                c2 = (P4 * P6 * P8 == 0)
            else:
                c1 = (P2 * P4 * P8 == 0)
                c2 = (P2 * P6 * P8 == 0)

            rm = (skel == 1) & (B >= 2) & (B <= 6) & (A == 1) & c1 & c2
            if rm.any():
                skel[rm] = 0
                removed_any = True
        if not removed_any:
            break
    return skel


def skeletonize(binary):
    """Generates 1px binary skeleton (uses opencv-contrib if available)."""
    try:
        thin = cv2.ximgproc.thinning(binary, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
        return (thin > 0).astype(np.uint8)
    except AttributeError:
        return _zhang_suen(binary)


def trace_skeleton(skel, min_length=8.0):
    """Traces 1px skeleton pixels into ordered polyline coordinate arrays."""
    h, w = skel.shape
    on = skel > 0

    p = np.pad(on.astype(np.uint8), 1)
    ring = [p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy, dx in _NB8]
    ring.append(ring[0])
    deg = np.zeros((h, w), np.uint8)
    for k in range(8):
        deg += ((ring[k] == 0) & (ring[k + 1] == 1)).astype(np.uint8)
    lone = np.zeros((h, w), np.uint8)
    for r in ring[:8]:
        lone += r
    deg[(deg == 0) & (lone > 0)] = 2

    visited = np.zeros((h, w), bool)
    order = [(-1, 0), (0, 1), (1, 0), (0, -1), (-1, 1), (1, 1), (1, -1), (-1, -1)]

    def walk(sy, sx):
        path = [(sy, sx)]
        visited[sy, sx] = True
        cy, cx = sy, sx
        while True:
            nxt = None
            for dy, dx in order:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and on[ny, nx] and not visited[ny, nx]:
                    nxt = (ny, nx)
                    break
            if nxt is None:
                break
            visited[nxt] = True
            path.append(nxt)
            if deg[nxt] >= 3:
                break
            cy, cx = nxt
        return path

    paths = []
    ys, xs = np.nonzero(on & (deg == 1))
    for y, x in zip(ys, xs):
        if not visited[y, x]:
            paths.append(walk(int(y), int(x)))
    ys, xs = np.nonzero(on & ~visited)
    for y, x in zip(ys, xs):
        if not visited[y, x]:
            paths.append(walk(int(y), int(x)))

    out = []
    for pth in paths:
        if len(pth) < 2:
            continue
        arr = np.array([(x, y) for y, x in pth], np.int32)
        length = float(np.sum(np.linalg.norm(np.diff(arr, axis=0), axis=1)))
        if length < min_length:
            continue
        out.append(arr)
    return out


# ============================================================
# CIRCULAR ARC FITTING (G2/G3 WITH I/J)
# ============================================================
_ARC_CHECK_SAMPLES = 48


def _sample_idx(n):
    """Subsamples indices for long polylines to bound computational complexity."""
    if n <= _ARC_CHECK_SAMPLES:
        return range(n)
    return sorted(set(np.linspace(0, n - 1, _ARC_CHECK_SAMPLES).astype(int).tolist()))


def smooth_polyline(pts, radius):
    """Moving average smoothing to suppress pixel discretization artifacts."""
    p = np.asarray(pts, np.float32)
    n = len(p)
    r = int(radius)
    if r < 1 or n < 2 * r + 3:
        return p
    k = 2 * r + 1
    kernel = np.ones(k, np.float32) / k
    out = p.copy()
    for c in (0, 1):
        out[r:n - r, c] = np.convolve(p[:, c], kernel, mode='valid')
    return out


def _line_fits(pts, tol):
    """Tests if all points lie within tolerance of the chord between endpoints."""
    x0, y0 = pts[0]
    x1, y1 = pts[-1]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return all(math.hypot(x - x0, y - y0) <= tol for x, y in pts)
    for k in _sample_idx(len(pts)):
        x, y = pts[k]
        if abs(dy * (x - x0) - dx * (y - y0)) / length > tol:
            return False
    return True


def _fit_circle_lsq(pts):
    """Fits circle via least-squares (Kåsa method) over point sequence."""
    P = np.asarray(pts, np.float64)
    x = P[:, 0]
    y = P[:, 1]
    A = np.column_stack([x, y, np.ones(len(P))])
    b = x * x + y * y
    try:
        sol = np.linalg.lstsq(A, b, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    cx = sol[0] / 2.0
    cy = sol[1] / 2.0
    val = sol[2] + cx * cx + cy * cy
    if not np.isfinite(val) or val <= 0:
        return None
    return cx, cy, math.sqrt(val)


def _try_arc(pts, tol, max_radius, min_sweep_rad=0.0):
    """Attempts to fit a single circular arc. Returns ((cx,cy), r, sweep) or None."""
    n = len(pts)
    if n < 3:
        return None
    idx = _sample_idx(n)
    circ = _fit_circle_lsq([pts[k] for k in idx])
    if circ is None:
        return None
    cx, cy, r = circ
    if r < 1e-6 or r > max_radius:
        return None

    # Project center onto the chord perpendicular bisector to ensure r_start == r_end
    x0, y0 = pts[0]
    xe, ye = pts[-1]
    dx, dy = xe - x0, ye - y0
    chord = math.hypot(dx, dy)
    if chord > 1e-9:
        mx, my = (x0 + xe) / 2.0, (y0 + ye) / 2.0
        nx, ny = -dy / chord, dx / chord
        t = (cx - mx) * nx + (cy - my) * ny
        cx, cy = mx + t * nx, my + t * ny
        r = math.hypot(x0 - cx, y0 - cy)
        if r < 1e-6 or r > max_radius:
            return None

    for k in idx:
        x, y = pts[k]
        if abs(math.hypot(x - cx, y - cy) - r) > tol:
            return None

    sample = [pts[k] for k in idx]
    angles = [math.atan2(y - cy, x - cx) for (x, y) in sample]
    sweep = 0.0
    for k in range(1, len(sample)):
        d = angles[k] - angles[k - 1]
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        if abs(d) < 1e-12:
            continue
        if sweep != 0.0 and (d > 0) != (sweep > 0):
            return None
        sweep += d

    if abs(sweep) < max(1e-9, min_sweep_rad) or abs(sweep) > math.radians(300):
        return None
    return (cx, cy), r, sweep


def fit_arc_segments(pts, config):
    """Decomposes polyline into linear (G1) and circular arc (G2/G3) segments."""
    n = len(pts)
    segs = []
    i = 0
    tol = config.arc_tolerance
    min_pts = max(3, int(config.arc_min_points))
    min_sweep = math.radians(getattr(config, 'arc_min_sweep_deg', 0.0))
    while i < n - 1:
        j_line = i + 1
        j = i + 2
        while j < n and _line_fits(pts[i:j + 1], tol):
            j_line = j
            j += 1

        best_arc = None
        j = i + min_pts - 1
        while j < n:
            cand = _try_arc(pts[i:j + 1], tol, config.arc_max_radius)
            if cand is None:
                break
            if abs(cand[2]) >= min_sweep:
                best_arc = (j, cand)
            j += 1

        if best_arc is not None and best_arc[0] > j_line:
            j, (center, _r, sweep) = best_arc
            segs.append(('arc', pts[j], center, sweep))
            i = j
        else:
            segs.append(('line', pts[j_line]))
            i = j_line
    return segs


def _arc_in_bounds(sx, sy, ex, ey, ccx, ccy, sweep, config):
    """Verifies that circular arc trajectory remains entirely within machine bounds."""
    r = math.hypot(sx - ccx, sy - ccy)
    margin = 0.5
    x_lo = -margin
    y_lo = -margin
    x_hi = config.work_area_x + config.offset_x + margin
    y_hi = config.work_area_y + config.offset_y + margin

    if ccx - r >= x_lo and ccx + r <= x_hi and ccy - r >= y_lo and ccy + r <= y_hi:
        return True

    a0 = math.atan2(sy - ccy, sx - ccx)
    steps = max(12, int(abs(sweep) / 0.1))
    for k in range(steps + 1):
        a = a0 + sweep * k / steps
        px = ccx + r * math.cos(a)
        py = ccy + r * math.sin(a)
        if px < x_lo or px > x_hi or py < y_lo or py > y_hi:
            return False
    return True


def emit_polyline(pts, config, lines, close=False):
    """Emits G1/G2/G3 instructions for a polyline (in mm coordinates). Returns drawn distance (mm)."""
    pts = [tuple(p) for p in pts]
    if close and len(pts) > 2 and pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    if len(pts) < 2:
        return 0.0

    feed = config.feed_rate_draw
    dist = 0.0
    sx, sy = pts[0]

    if not config.use_arcs:
        for (x, y) in pts[1:]:
            lines.append(f"G1 X{fmt(x)} Y{fmt(y)} F{fmt(feed)}")
            dist += math.hypot(x - sx, y - sy)
            sx, sy = x, y
        return dist

    for seg in fit_arc_segments(pts, config):
        if seg[0] == 'line':
            x, y = seg[1]
            lines.append(f"G1 X{fmt(x)} Y{fmt(y)} F{fmt(feed)}")
            dist += math.hypot(x - sx, y - sy)
        else:
            _, (x, y), (ccx, ccy), sweep = seg
            i_off = ccx - sx
            j_off = ccy - sy

            qsx = round(sx, 3); qsy = round(sy, 3)
            qex = round(x, 3);  qey = round(y, 3)
            qi  = round(i_off, 3); qj = round(j_off, 3)
            best_ij = (qi, qj)
            best_err = abs(math.hypot(qsx - (qsx + qi), qsy - (qsy + qj))
                          - math.hypot(qex - (qsx + qi), qey - (qsy + qj)))
            if best_err > 0.0001:
                for di in (-0.001, 0, 0.001):
                    for dj in (-0.001, 0, 0.001):
                        ci = round(qi + di, 3)
                        cj = round(qj + dj, 3)
                        tcx, tcy = qsx + ci, qsy + cj
                        rs = math.hypot(qsx - tcx, qsy - tcy)
                        re_ = math.hypot(qex - tcx, qey - tcy)
                        err = abs(rs - re_)
                        if err < best_err:
                            best_err = err
                            best_ij = (ci, cj)
            qi, qj = best_ij
            arc_ok = best_err < 0.0005
            actual_cx = qsx + qi
            actual_cy = qsy + qj
            if arc_ok and _arc_in_bounds(sx, sy, x, y, actual_cx, actual_cy, sweep, config):
                code = "G3" if sweep > 0 else "G2"
                lines.append(f"{code} X{fmt(x)} Y{fmt(y)} "
                             f"I{fmt(qi)} J{fmt(qj)} F{fmt(feed)}")
                dist += math.hypot(qi, qj) * abs(sweep)
            else:
                r = math.hypot(i_off, j_off)
                a0 = math.atan2(sy - ccy, sx - ccx)
                n_segs = max(8, int(abs(sweep) / 0.05))
                for k in range(1, n_segs + 1):
                    a = a0 + sweep * k / n_segs
                    gx = ccx + r * math.cos(a)
                    gy = ccy + r * math.sin(a)
                    if k == n_segs:
                        gx, gy = x, y
                    lines.append(f"G1 X{fmt(gx)} Y{fmt(gy)} F{fmt(feed)}")
                    dist += math.hypot(gx - sx, gy - sy)
                    sx, sy = gx, gy
                continue
        sx, sy = x, y
    return dist


def polyline_to_mm(pts_px, w, h, config):
    """Converts Nx2 pixel coordinates to list of (x_mm, y_mm), removing consecutive duplicates."""
    out = []
    for px, py in np.asarray(pts_px).reshape(-1, 2):
        p = px_to_mm(float(px), float(py), w, h, config)
        if not out or p != out[-1]:
            out.append(p)
    return out


# ============================================================
# METHOD 1: CONTOUR — Boundary Tracing
# ============================================================
def process_contour(image_path, config):
    """Processes image into boundary contours and preview images."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        bs = config.blur_size | 1
        gray = cv2.GaussianBlur(gray, (bs, bs), 0)
    _, binary = cv2.threshold(gray, config.threshold, 255, cv2.THRESH_BINARY)
    if config.invert:
        binary = cv2.bitwise_not(binary)

    if getattr(config, 'contour_centerline', False):
        polylines, stroke_img = strokes_from_binary(binary, config)
        if (not config.use_arcs) and config.simplify_epsilon > 0:
            eps = float(config.simplify_epsilon)
            polylines = [
                cv2.approxPolyDP(np.round(p).reshape(-1, 1, 2).astype(np.int32),
                                 eps, False).reshape(-1, 2).astype(np.float32)
                if len(p) > 2 else p
                for p in polylines
            ]
            polylines = [p for p in polylines if len(p) >= 2]
        images = stroke_previews(img, polylines, stroke_img)
        total_pts = sum(len(p) for p in polylines)
        info = f"Contour [1px centerline]: {len(polylines)} strokes | Points: {total_pts}"
        return polylines, images, w, h, info

    contours_raw, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = []
    for cnt in contours_raw:
        if len(cnt) < config.min_contour_points:
            continue
        if config.simplify_epsilon > 0:
            eps = config.simplify_epsilon * cv2.arcLength(cnt, True) / 100
            cnt = cv2.approxPolyDP(cnt, eps, True)
        if len(cnt) >= 2:
            contours.append(cnt)

    images = {'original': img.copy()}
    conly = np.zeros((h, w, 3), np.uint8)
    cv2.drawContours(conly, contours, -1, (255, 255, 255), 1)
    for cnt in contours:
        cv2.circle(conly, tuple(cnt[0][0]), 3, (0, 255, 0), -1)
    images['preview'] = conly
    overlay = img.copy()
    cv2.drawContours(overlay, contours, -1, (0, 255, 0), 2)
    images['overlay'] = overlay

    total_pts = sum(len(c) for c in contours)
    info = f"Contour [outlines]: {len(contours)} | Points: {total_pts}"
    return contours, images, w, h, info


def optimize_contour_path(contours):
    """Nearest-neighbor path ordering to minimize rapid travel distance."""
    if len(contours) <= 1:
        return contours
    remaining = list(range(len(contours)))
    ordered = []
    pos = np.array([0.0, 0.0])
    while remaining:
        best_i, best_d, best_rev = None, float('inf'), False
        for i in remaining:
            s = contours[i][0][0].astype(float)
            e = contours[i][-1][0].astype(float)
            ds = np.linalg.norm(pos - s)
            de = np.linalg.norm(pos - e)
            if ds < best_d:
                best_d, best_i, best_rev = ds, i, False
            if de < best_d:
                best_d, best_i, best_rev = de, i, True
        remaining.remove(best_i)
        c = contours[best_i]
        if best_rev:
            c = c[::-1]
        ordered.append(c)
        pos = c[-1][0].astype(float)
    return ordered


def generate_gcode_contour(contours, w, h, config):
    """Generates G-Code from contour paths."""
    centerline = getattr(config, 'contour_centerline', False)
    contours = optimize_contour_path(
        [np.asarray(c).reshape(-1, 1, 2) for c in contours])
    mode = "G2/G3 arcs" if config.use_arcs else "G1 only"
    kind = "1px centerline" if centerline else "perimeter outline"
    lines = gcode_header(config, "CONTOUR (Perimeter Tracing)", w, h,
                         f"Contours: {len(contours)} | {kind} | Interpolation: {mode}")
    close_tol = 2.0 * mm_per_px(w, h, config)
    draw_d = travel_d = 0.0
    px, py = 0.0, 0.0
    for i, cnt in enumerate(contours):
        mm = polyline_to_mm(cnt, w, h, config)
        if len(mm) < 2:
            continue
        if centerline:
            closed = (len(mm) > 2 and
                      math.hypot(mm[0][0] - mm[-1][0], mm[0][1] - mm[-1][1]) <= close_tol)
        else:
            closed = len(mm) > 2
        lines.append(f"; Contour {i+1}/{len(contours)} ({len(mm)} points)")
        sx, sy = mm[0]
        travel_d += math.hypot(sx - px, sy - py)
        lines.append(cmd_pen_up(config))
        lines.append(cmd_travel(config, sx, sy))
        lines.append(cmd_pen_down(config))
        draw_d += emit_polyline(mm, config, lines, close=closed)
        px, py = (sx, sy) if closed else mm[-1]
        lines.append("")

    est = draw_d / config.feed_rate_draw + travel_d / config.feed_rate_travel
    stats = [
        f"; Draw distance: {draw_d:.1f} mm",
        f"; Rapid travel : {travel_d:.1f} mm",
        f"; Est. time    : ~{est:.1f} min",
    ]
    lines += gcode_footer(config, stats)
    return finalize_gcode(lines, config), {
        'contours': len(contours),
        'draw_dist': draw_d, 'travel_dist': travel_d, 'est_time': est
    }


# ============================================================
# METHOD 2: RASTER — Continuous Area Infill
# ============================================================
def _runs(row_bool):
    """Extracts continuous True runs on a row -> [(start, end), ...]."""
    if not row_bool.any():
        return []
    d = np.diff(row_bool.astype(np.int8))
    starts = (np.nonzero(d == 1)[0] + 1).tolist()
    ends = np.nonzero(d == -1)[0].tolist()
    if row_bool[0]:
        starts.insert(0, 0)
    if row_bool[-1]:
        ends.append(len(row_bool) - 1)
    return [(s, e) for s, e in zip(starts, ends) if e >= s]


def _connector_inside(mask, p0, p1, samples=8):
    """Tests if the line segment p0->p1 stays entirely within the fill region."""
    h, w = mask.shape
    for t in np.linspace(0.0, 1.0, samples):
        x = int(round(p0[0] + (p1[0] - p0[0]) * t))
        y = int(round(p0[1] + (p1[1] - p0[1]) * t))
        if not (0 <= x < w and 0 <= y < h) or mask[y, x] == 0:
            return False
    return True


def scanline_fill(binary, step_px, angle_deg, link=True):
    """Generates directional scanline infill strokes at specified angle."""
    h, w = binary.shape
    cx, cy = w / 2.0, h / 2.0
    M = cv2.getRotationMatrix2D((cx, cy), -float(angle_deg), 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw = int(h * sin + w * cos) + 2
    nh = int(h * cos + w * sin) + 2
    M[0, 2] += nw / 2.0 - cx
    M[1, 2] += nh / 2.0 - cy
    rot = cv2.warpAffine(binary, M, (nw, nh), flags=cv2.INTER_NEAREST,
                         borderValue=0)
    Minv = cv2.invertAffineTransform(M)

    step = max(1, int(step_px))
    link_r = max(2, step // 2 + 1)
    link_mask = cv2.dilate(rot, cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * link_r + 1, 2 * link_r + 1)))
    max_link = max(12.0, 6.0 * step)

    strokes = []
    cur = None
    for ri, y in enumerate(range(0, nh, step)):
        segs = _runs(rot[y] > 0)
        if not segs:
            cur = None
            continue
        if ri % 2:
            segs = [(e, s) for s, e in reversed(segs)]
        for a, b in segs:
            p_start, p_end = (float(a), float(y)), (float(b), float(y))
            if (link and cur is not None
                    and math.hypot(p_start[0] - cur[-1][0],
                                   p_start[1] - cur[-1][1]) <= max_link
                    and _connector_inside(link_mask, cur[-1], p_start)):
                cur.append(p_start)
            else:
                cur = []
                strokes.append(cur)
                cur.append(p_start)
            cur.append(p_end)

    out = []
    for s in strokes:
        if len(s) < 2:
            continue
        p = np.asarray(s, np.float32)
        ones = np.ones((len(p), 1), np.float32)
        back = (np.hstack([p, ones]) @ Minv.T).astype(np.float32)
        out.append(back)
    return out


def _mask_inside(mask, pt):
    h, w = mask.shape
    x = int(round(float(pt[0])))
    y = int(round(float(pt[1])))
    return 0 <= x < w and 0 <= y < h and mask[y, x] > 0


def clip_polylines_to_mask(polylines, mask, sample_step_px=0.35):
    """Clips polylines to remain strictly within boundary mask."""
    clipped = []
    sample_step_px = max(0.2, float(sample_step_px))

    for poly in polylines:
        pts = [tuple(map(float, p)) for p in poly]
        if len(pts) < 2:
            continue

        run = []

        def flush():
            nonlocal run
            if len(run) >= 2:
                cleaned = [run[0]]
                for p in run[1:]:
                    if math.hypot(p[0] - cleaned[-1][0], p[1] - cleaned[-1][1]) > 1e-6:
                        cleaned.append(p)
                if len(cleaned) >= 2:
                    clipped.append(np.asarray(cleaned, np.float32))
            run = []

        prev = pts[0]
        prev_inside = _mask_inside(mask, prev)
        if prev_inside:
            run.append(prev)

        for cur in pts[1:]:
            seg_len = math.hypot(cur[0] - prev[0], cur[1] - prev[1])
            steps = max(2, int(math.ceil(seg_len / sample_step_px)))
            for i in range(1, steps + 1):
                t = i / steps
                p = (prev[0] + (cur[0] - prev[0]) * t,
                     prev[1] + (cur[1] - prev[1]) * t)
                inside = _mask_inside(mask, p)
                if inside:
                    if not run:
                        run.append(prev if prev_inside else p)
                    if math.hypot(p[0] - run[-1][0], p[1] - run[-1][1]) > 1e-6:
                        run.append(p)
                elif run:
                    flush()
                prev_inside = inside
            prev = cur
            prev_inside = _mask_inside(mask, prev)

        flush()

    return clipped


def offset_fill(binary, step_px):
    """Generates concentric offset contours using Euclidean distance transform."""
    dist = cv2.distanceTransform((binary > 0).astype(np.uint8), cv2.DIST_L2, 5)
    max_d = float(dist.max())
    out = []
    level = step_px / 2.0
    while level <= max_d:
        band = (dist >= level).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(band, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for c in cnts:
            pts = c.reshape(-1, 2).astype(np.float32)
            if len(pts) < 8:
                continue
            pts = smooth_polyline(pts, 2)
            out.append(np.vstack([pts, pts[:1]]))
        level += step_px
    return out


def region_outlines(binary):
    """Extracts perimeter contours to draw sharp boundary edges prior to infill."""
    cnts, _ = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cnts:
        pts = c.reshape(-1, 2).astype(np.float32)
        if len(pts) < 8:
            continue
        pts = smooth_polyline(pts, 2)
        out.append(np.vstack([pts, pts[:1]]))
    return out


def process_raster_v2(image_path, config):
    """Raster infill pipeline with supersampling and boundary clipping."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    orig_h, orig_w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        bs = config.blur_size | 1
        gray = cv2.GaussianBlur(gray, (bs, bs), 0)

    _, binary0 = cv2.threshold(gray, config.threshold, 255, cv2.THRESH_BINARY)
    if config.invert:
        binary0 = cv2.bitwise_not(binary0)

    ss = max(1, int(round(getattr(config, 'raster_supersample', 1))))
    proc_binary = binary0
    if ss > 1:
        proc_binary = cv2.resize(binary0, (orig_w * ss, orig_h * ss),
                                 interpolation=cv2.INTER_LINEAR)
        _, proc_binary = cv2.threshold(proc_binary, 127, 255, cv2.THRESH_BINARY)

    proc_h, proc_w = proc_binary.shape[:2]
    proc_scale = mm_per_px(proc_w, proc_h, config)
    step_px = max(1, int(round(config.raster_resolution / proc_scale)))
    orig_scale = mm_per_px(orig_w, orig_h, config)
    orig_step_px = max(1, int(round(config.raster_resolution / orig_scale)))
    style = getattr(config, 'raster_style', 'zigzag')

    outline_polylines = []
    fill_mask0 = binary0
    if getattr(config, 'raster_outline', False):
        outline_polylines = region_outlines(proc_binary)
        r_proc = max(1, step_px // 2)
        fill_mask = cv2.erode(proc_binary, cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * r_proc + 1, 2 * r_proc + 1)))
        r_orig = max(1, orig_step_px // 2)
        fill_mask0 = cv2.erode(binary0, cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * r_orig + 1, 2 * r_orig + 1)))
    else:
        fill_mask = proc_binary

    fill_polylines = []
    if style == 'offset':
        fill_polylines = offset_fill(fill_mask, step_px)
    else:
        angle = float(getattr(config, 'raster_angle', 0.0))
        fill_polylines = scanline_fill(fill_mask, step_px, angle,
                                       link=(style == 'zigzag'))
        if getattr(config, 'raster_cross', False):
            fill_polylines += scanline_fill(fill_mask, step_px, angle + 90.0,
                                            link=(style == 'zigzag'))

    if ss > 1:
        inv = 1.0 / float(ss)
        outline_polylines = [p * inv for p in outline_polylines]
        fill_polylines = [p * inv for p in fill_polylines]

    fill_polylines = clip_polylines_to_mask(fill_polylines, fill_mask0)
    polylines = outline_polylines + fill_polylines

    smooth_n = max(0, int(getattr(config, 'raster_smooth', 0)))
    if smooth_n > 0:
        smoothed = []
        for p in polylines:
            if len(p) >= 5:
                smoothed.append(smooth_polyline(p, smooth_n))
            else:
                smoothed.append(p)
        polylines = smoothed
        if getattr(config, 'raster_outline', False):
            outline_len = len(outline_polylines)
            fill_polylines = clip_polylines_to_mask(polylines[outline_len:], fill_mask0)
            polylines = polylines[:outline_len] + fill_polylines

    polylines = [p for p in polylines if len(p) >= 2]

    images = {'original': img.copy()}
    images['binary'] = cv2.cvtColor(binary0, cv2.COLOR_GRAY2BGR)
    draw_pts = [np.round(p).astype(np.int32).reshape(-1, 1, 2) for p in polylines]

    preview = np.zeros((orig_h, orig_w, 3), np.uint8)
    cv2.polylines(preview, draw_pts, False, (255, 255, 255), 1)
    for p in polylines:
        cv2.circle(preview, (int(p[0][0]), int(p[0][1])), 2, (0, 255, 0), -1)
    images['preview'] = preview

    overlay = img.copy()
    cv2.polylines(overlay, draw_pts, False, (0, 255, 0), 1)
    images['overlay'] = overlay

    sim = np.zeros((orig_h, orig_w, 3), np.uint8)
    cv2.polylines(sim, draw_pts, False, (255, 255, 255), 1)
    prev = None
    for p in polylines:
        if prev is not None:
            cv2.line(sim, (int(prev[0]), int(prev[1])),
                     (int(p[0][0]), int(p[0][1])), (0, 0, 160), 1)
        prev = p[-1]
    images['raster'] = sim

    dp = cv2.countNonZero(binary0)
    total_pts = sum(len(p) for p in polylines)
    kind = {'zigzag': 'continuous zigzag', 'hatch': 'parallel hatching',
            'offset': 'offset contours'}.get(style, style)
    if style != 'offset':
        kind += f" {config.raster_angle:.0f}°"
    info = (f"Infill [{kind}]: {len(polylines)} strokes (= pen hops) | "
            f"Points: {total_pts} | Dark area {dp/(orig_w*orig_h)*100:.1f}% | "
            f"Spacing {config.raster_resolution}mm")
    return polylines, images, orig_w, orig_h, info


process_raster = process_raster_v2


def generate_gcode_raster(polylines, w, h, config):
    """Generates G-Code for area infill."""
    ordered = optimize_contour_path([np.asarray(p).reshape(-1, 1, 2)
                                     for p in polylines])
    style = getattr(config, 'raster_style', 'zigzag')
    kind = {'zigzag': 'continuous zigzag', 'hatch': 'parallel hatching',
            'offset': 'offset contours'}.get(style, style)
    if style != 'offset':
        kind += f" {config.raster_angle:.0f}°"
    mode = "G2/G3 arcs" if config.use_arcs else "G1 only"
    lines = gcode_header(config, "RASTER (Area Infill)", w, h,
                         f"Infill style: {kind} | "
                         f"Spacing: {config.raster_resolution}mm | Interpolation: {mode}")
    draw_d = travel_d = 0.0
    px, py = 0.0, 0.0
    for i, cnt in enumerate(ordered):
        mm = polyline_to_mm(cnt, w, h, config)
        if len(mm) < 2:
            continue
        lines.append(f"; Stroke {i+1}/{len(ordered)} ({len(mm)} points)")
        sx, sy = mm[0]
        travel_d += math.hypot(sx - px, sy - py)
        lines.append(cmd_pen_up(config))
        lines.append(cmd_travel(config, sx, sy))
        lines.append(cmd_pen_down(config))
        draw_d += emit_polyline(mm, config, lines)
        px, py = mm[-1]
        lines.append("")

    est = ((draw_d / config.feed_rate_draw + travel_d / config.feed_rate_travel)
           if config.feed_rate_draw else 0.0)
    stats = [
        f"; Strokes (pen down/up cycles): {len(ordered)}",
        f"; Draw distance: {draw_d:.1f} mm | Rapid travel: {travel_d:.1f} mm",
        f"; Est. time: ~{est:.1f} min",
    ]
    lines += gcode_footer(config, stats)
    return finalize_gcode(lines, config), {
        'strokes': len(ordered),
        'points': sum(len(p) for p in polylines),
        'draw_dist': draw_d, 'travel_dist': travel_d, 'est_time': est,
    }


# ============================================================
# METHOD 3: EDGE — Canny Edge Contours
# ============================================================
def process_edge(image_path, config):
    """Processes image into Canny edge contours and previews."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        bs = config.blur_size | 1
        gray = cv2.GaussianBlur(gray, (bs, bs), 0)

    edges = cv2.Canny(gray, config.canny_low, config.canny_high)
    contours_raw, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = []
    for cnt in contours_raw:
        if len(cnt) < 3:
            continue
        if config.simplify_epsilon > 0:
            eps = config.simplify_epsilon * cv2.arcLength(cnt, True) / 100
            cnt = cv2.approxPolyDP(cnt, eps, True)
        if len(cnt) >= 2:
            contours.append(cnt)

    images = {'original': img.copy()}

    edge_display = np.zeros((h, w, 3), np.uint8)
    cv2.drawContours(edge_display, contours, -1, (255, 255, 255), 1)
    for cnt in contours:
        cv2.circle(edge_display, tuple(cnt[0][0]), 2, (0, 255, 0), -1)
    images['preview'] = edge_display

    overlay = img.copy()
    cv2.drawContours(overlay, contours, -1, (0, 200, 255), 1)
    images['overlay'] = overlay

    edges_bgr = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
    images['canny_raw'] = edges_bgr

    total_pts = sum(len(c) for c in contours)
    info = f"Edges: {len(contours)} strokes | Points: {total_pts} | Canny [{config.canny_low}-{config.canny_high}]"
    return contours, images, w, h, info


def generate_gcode_edge(contours, w, h, config):
    """Generates G-Code from edge contours."""
    contours = optimize_contour_path(contours)
    mode = "G2/G3 arcs" if config.use_arcs else "G1 only"
    lines = gcode_header(config, "EDGE (Canny Contours)", w, h,
                         f"Strokes: {len(contours)} | Canny [{config.canny_low}-{config.canny_high}] "
                         f"| Interpolation: {mode}")
    draw_d = travel_d = 0.0
    px, py = 0.0, 0.0
    for i, cnt in enumerate(contours):
        mm = polyline_to_mm(cnt, w, h, config)
        if len(mm) < 2:
            continue
        lines.append(f"; Stroke {i+1}/{len(contours)} ({len(mm)} points)")
        sx, sy = mm[0]
        travel_d += math.hypot(sx - px, sy - py)
        lines.append(cmd_pen_up(config))
        lines.append(cmd_travel(config, sx, sy))
        lines.append(cmd_pen_down(config))
        draw_d += emit_polyline(mm, config, lines)
        px, py = mm[-1]
        lines.append("")

    est = draw_d / config.feed_rate_draw + travel_d / config.feed_rate_travel
    stats = [
        f"; Strokes: {len(contours)}",
        f"; Draw distance: {draw_d:.1f} mm | Rapid travel: {travel_d:.1f} mm",
        f"; Est. time: ~{est:.1f} min",
    ]
    lines += gcode_footer(config, stats)
    return finalize_gcode(lines, config), {
        'edges': len(contours),
        'draw_dist': draw_d, 'travel_dist': travel_d, 'est_time': est,
    }


# ============================================================
# SHARED UTILITIES FOR LINE, COLOR, AND PORTRAIT
# ============================================================
def strokes_from_binary(binary, config, despeckle=None):
    """Extracts ordered polyline strokes and preview image from binary mask."""
    if config.despeckle if despeckle is None else despeckle:
        k = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)

    if config.uniform_stroke:
        skel = skeletonize(binary)
        blob_raw = []
        if config.blob_outline:
            n, labels, stats, _ = cv2.connectedComponentsWithStats(
                (binary > 0).astype(np.uint8), connectivity=8)
            if n > 1:
                skel_len = np.bincount(labels[skel > 0].ravel(), minlength=n)
                for i in range(1, n):
                    area = stats[i, cv2.CC_STAT_AREA]
                    if skel_len[i] >= config.line_min_length or area < 8:
                        continue
                    comp = (labels == i).astype(np.uint8)
                    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_NONE)
                    for c in cnts:
                        pts = c.reshape(-1, 2)
                        if len(pts) >= 6:
                            blob_raw.append(np.vstack([pts, pts[:1]]))
                    skel[labels == i] = 0

        raw = trace_skeleton(skel, config.line_min_length) + blob_raw
        stroke_img = (skel * 255).astype(np.uint8)
    else:
        cnts, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        raw = []
        for c in cnts:
            pts = c.reshape(-1, 2)
            if len(pts) < 2:
                continue
            length = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
            if length >= config.line_min_length:
                raw.append(pts.astype(np.int32))
        stroke_img = binary

    polylines = []
    for pts in raw:
        if config.line_smooth > 0:
            pts = smooth_polyline(pts, config.line_smooth)
        if (not config.use_arcs) and config.line_simplify > 0 and len(pts) > 2:
            pts = cv2.approxPolyDP(
                np.round(pts).reshape(-1, 1, 2).astype(np.int32),
                float(config.line_simplify), False).reshape(-1, 2)
        if len(pts) >= 2:
            polylines.append(np.asarray(pts, np.float32))
    return polylines, stroke_img


def stroke_previews(img, polylines, stroke_img, extra=None):
    """Generates standard preview images: toolpaths / overlay / binary skeleton."""
    h, w = img.shape[:2]
    images = {'original': img.copy()}
    draw_pts = [np.round(p).astype(np.int32).reshape(-1, 1, 2) for p in polylines]

    preview = np.zeros((h, w, 3), np.uint8)
    cv2.polylines(preview, draw_pts, False, (255, 255, 255), 1)
    for pts in polylines:
        cv2.circle(preview, (int(pts[0][0]), int(pts[0][1])), 2, (0, 255, 0), -1)
    images['preview'] = preview

    overlay = img.copy()
    cv2.polylines(overlay, draw_pts, False, (0, 255, 0), 1)
    images['overlay'] = overlay
    images['stroke'] = cv2.cvtColor(stroke_img, cv2.COLOR_GRAY2BGR)
    if extra:
        images.update(extra)
    return images


def remove_small_blobs(binary, min_area):
    """Removes small connected components smaller than min_area (px)."""
    if min_area <= 1:
        return binary
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (binary > 0).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        keep[i] = stats[i, cv2.CC_STAT_AREA] >= min_area
    return np.where(keep[labels], 255, 0).astype(np.uint8)


# ============================================================
# METHOD 4: LINE — Uniform Stroke Line Art
# ============================================================
def process_line(image_path, config):
    """Processes image into 1px uniform centerline drawing paths."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        bs = int(config.blur_size) | 1
        gray = cv2.GaussianBlur(gray, (bs, bs), 0)

    if config.adaptive_threshold:
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 10)
    else:
        _, binary = cv2.threshold(gray, int(config.threshold), 255, cv2.THRESH_BINARY)
    if config.invert:
        binary = cv2.bitwise_not(binary)

    polylines, stroke_img = strokes_from_binary(binary, config)
    images = stroke_previews(img, polylines, stroke_img)

    total_pts = sum(len(p) for p in polylines)
    kind = "uniform stroke (skeleton)" if config.uniform_stroke else "outline"
    info = f"Line [{kind}]: {len(polylines)} strokes | Points: {total_pts}"
    return polylines, images, w, h, info


def generate_gcode_line(polylines, w, h, config):
    """Generates G-Code with G2/G3 arc optimization for line drawings."""
    ordered = optimize_contour_path([p.reshape(-1, 1, 2) for p in polylines])
    mode = "G2/G3 arcs" if config.use_arcs else "G1 only"
    kind = "uniform stroke (skeleton)" if config.uniform_stroke else "outline"
    lines = gcode_header(config, "LINE (Uniform Stroke)", w, h,
                         f"Strokes: {len(ordered)} | {kind} | Interpolation: {mode}")
    draw_d = travel_d = 0.0
    px, py = 0.0, 0.0
    n_arc = n_line = 0

    for i, cnt in enumerate(ordered):
        mm = polyline_to_mm(cnt, w, h, config)
        if len(mm) < 2:
            continue
        before = len(lines)
        lines.append(f"; Stroke {i+1}/{len(ordered)} ({len(mm)} points)")
        sx, sy = mm[0]
        travel_d += math.hypot(sx - px, sy - py)
        lines.append(cmd_pen_up(config))
        lines.append(cmd_travel(config, sx, sy))
        lines.append(cmd_pen_down(config))
        draw_d += emit_polyline(mm, config, lines)
        px, py = mm[-1]
        for ln in lines[before:]:
            if ln.startswith(("G2 ", "G3 ")):
                n_arc += 1
            elif ln.startswith("G1 X"):
                n_line += 1
        lines.append("")

    est = (draw_d / config.feed_rate_draw +
           travel_d / config.feed_rate_travel) if config.feed_rate_draw else 0.0
    stats = [
        f"; Strokes: {len(ordered)} | G2/G3 arcs: {n_arc} | G1 linear: {n_line}",
        f"; Draw distance: {draw_d:.1f} mm | Rapid travel: {travel_d:.1f} mm",
        f"; Est. time: ~{est:.1f} min",
    ]
    lines += gcode_footer(config, stats)
    return finalize_gcode(lines, config), {
        'lines_count': len(ordered), 'arcs': n_arc, 'segments': n_line,
        'draw_dist': draw_d, 'travel_dist': travel_d, 'est_time': est,
    }


# ============================================================
# METHOD 5: COLOR — Flat Color Boundaries
# ============================================================
def quantize_colors(img, k, seed=42):
    """Quantizes image colors into k clusters in Lab color space. Returns labels (h, w)."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    h, w = lab.shape[:2]
    Z = lab.reshape(-1, 3).astype(np.float32)

    cv2.setRNGSeed(seed)
    rng = np.random.default_rng(seed)
    sample = Z if len(Z) <= 40000 else Z[rng.choice(len(Z), 40000, replace=False)]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, _, centers = cv2.kmeans(sample, int(k), None, criteria, 3,
                               cv2.KMEANS_PP_CENTERS)

    best = np.zeros(len(Z), np.int32)
    best_d = None
    for i, c in enumerate(centers):
        d = ((Z - c) ** 2).sum(1)
        if best_d is None:
            best_d = d
        else:
            m = d < best_d
            best_d[m] = d[m]
            best[m] = i
    return best.reshape(h, w), centers


def process_color(image_path, config):
    """Processes flat-color artwork into boundary strokes between color regions."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    h, w = img.shape[:2]

    src = img
    if config.color_denoise > 0:
        ksz = int(config.color_denoise) | 1
        src = cv2.medianBlur(src, ksz)

    labels, centers = quantize_colors(src, config.color_levels)

    edge = np.zeros((h, w), bool)
    edge[:, :-1] |= labels[:, :-1] != labels[:, 1:]
    edge[:-1, :] |= labels[:-1, :] != labels[1:, :]
    binary = edge.astype(np.uint8) * 255

    binary = remove_small_blobs(binary, int(config.color_min_area))
    polylines, stroke_img = strokes_from_binary(binary, config, despeckle=False)

    quant = centers[labels].astype(np.uint8)
    quant = cv2.cvtColor(quant, cv2.COLOR_LAB2BGR)
    images = stroke_previews(img, polylines, stroke_img, extra={'quant': quant})

    total_pts = sum(len(p) for p in polylines)
    info = (f"Color: {len(polylines)} strokes | Points: {total_pts} | "
            f"{config.color_levels} color clusters")
    return polylines, images, w, h, info


def generate_gcode_color(polylines, w, h, config):
    """Generates G-Code from color boundary paths."""
    gcode, stats = generate_gcode_line(polylines, w, h, config)
    return gcode.replace("LINE (Uniform Stroke)", "COLOR (Color Boundaries)"), stats


# ============================================================
# METHOD 6: PORTRAIT — Portrait Sketching (XDoG)
# ============================================================
def xdog(gray, config):
    """Applies normalized Extended Difference of Gaussians (XDoG)."""
    f = gray.astype(np.float32) / 255.0
    s = max(0.3, float(config.portrait_detail))
    g1 = cv2.GaussianBlur(f, (0, 0), s)
    g2 = cv2.GaussianBlur(f, (0, 0), s * 1.6)

    d = g1 - g2
    sd = float(d.std())
    resp = d / sd if sd > 1e-9 else np.zeros_like(d)

    sens = float(config.portrait_sensitivity)
    mask = (resp < -sens).astype(np.uint8) * 255

    phi = float(config.portrait_phi)
    ink = np.clip(1.0 + np.tanh(phi * (resp + sens)), 0.0, 1.0)
    return (ink * 255).astype(np.uint8), mask


def process_portrait(image_path, config):
    """Processes portrait photo into sketch toolpaths via XDoG filter."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if config.portrait_denoise > 0:
        gray = cv2.bilateralFilter(gray, 9, float(config.portrait_denoise),
                                   float(config.portrait_denoise))

    ink, binary = xdog(gray, config)
    binary = remove_small_blobs(binary, int(config.portrait_min_area))
    polylines, stroke_img = strokes_from_binary(binary, config)

    images = stroke_previews(img, polylines, stroke_img,
                             extra={'ink': cv2.cvtColor(ink, cv2.COLOR_GRAY2BGR)})

    total_pts = sum(len(p) for p in polylines)
    info = (f"Portrait: {len(polylines)} strokes | Points: {total_pts} | "
            f"DoG σ={config.portrait_detail} threshold={config.portrait_sensitivity}σ")
    return polylines, images, w, h, info


def generate_gcode_portrait(polylines, w, h, config):
    """Generates G-Code for portrait sketches."""
    gcode, stats = generate_gcode_line(polylines, w, h, config)
    return gcode.replace("LINE (Uniform Stroke)", "PORTRAIT (Portrait Sketch)"), stats


# ============================================================
# METHOD 7: TEXT — Direct Text Engraving
# ============================================================
WINDOWS_FONT_DIRS = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
]


def list_system_fonts():
    """Returns dictionary of installed system TrueType / OpenType fonts."""
    found = {}
    for d in WINDOWS_FONT_DIRS:
        if not d or not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for fn in names:
            if fn.lower().endswith((".ttf", ".otf")):
                found.setdefault(os.path.splitext(fn)[0], os.path.join(d, fn))
    return dict(sorted(found.items(), key=lambda kv: kv[0].lower()))


def load_font(name, size_px):
    """Loads TrueType font by family name, file path, or default fallback."""
    size_px = max(4, int(size_px))
    candidates = []
    if name:
        installed = list_system_fonts()
        if name in installed:
            candidates.append(installed[name])
        candidates.append(name)
        if not name.lower().endswith((".ttf", ".otf")):
            candidates.append(name + ".ttf")
    candidates += ["arial.ttf", "segoeui.ttf", "tahoma.ttf", "DejaVuSans.ttf"]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size_px)
        except (OSError, IOError):
            continue
    raise RuntimeError("Could not load any TrueType font. Check the 'Font' setting.")


def _cap_height_px(font):
    """Measures capital letter 'H' height in pixels."""
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    _, y0, _, y1 = d.textbbox((0, 0), "H", font=font)
    return max(1, y1 - y0)


def _render_text_block(text, font, line_spacing, align):
    """Renders multiline text block tightly bound on a clean canvas."""
    lines = text.splitlines() or [""]
    ascent, descent = font.getmetrics()
    line_h = max(1, ascent + descent)
    step = max(1, int(round(line_h * max(0.5, line_spacing))))

    d0 = ImageDraw.Draw(Image.new("L", (1, 1)))
    widths = [float(d0.textlength(s, font=font)) for s in lines]
    pad = max(8, line_h // 4)
    W = int(math.ceil(max(widths) if widths else 1)) + 2 * pad
    H = step * (len(lines) - 1) + line_h + 2 * pad

    img = Image.new("L", (max(W, 1), max(H, 1)), 0)
    d = ImageDraw.Draw(img)
    for i, s in enumerate(lines):
        if not s.strip():
            continue
        if align == "center":
            x = (W - widths[i]) / 2
        elif align == "right":
            x = W - pad - widths[i]
        else:
            x = pad
        d.text((x, pad + i * step), s, font=font, fill=255)

    bb = img.getbbox()
    return img.crop(bb) if bb else img


def render_text_image(config):
    """Renders text string to binary mask matched to physical work area scale."""
    ppm = max(1.0, float(config.text_render_scale))
    W = max(64, int(round(config.work_area_x * ppm)))
    H = max(64, int(round(config.work_area_y * ppm)))
    margin = max(0.0, float(config.text_margin)) * ppm
    usable_w = max(8.0, W - 2 * margin)
    usable_h = max(8.0, H - 2 * margin)

    text = config.text_content if config.text_content.strip() else "Hello World"
    align = config.text_align if config.text_align in ("left", "center", "right") else "center"
    spacing = float(config.text_line_spacing)

    REF = 256
    cap_ref = _cap_height_px(load_font(config.text_font, REF))
    font_px = int(round(float(config.text_height) * ppm * REF / cap_ref))
    font_px = max(8, min(font_px, 6000))

    block = _render_text_block(text, load_font(config.text_font, font_px),
                               spacing, align)

    fit = min(usable_w / block.width, usable_h / block.height)
    if config.text_autofit or fit < 1.0:
        font_px = max(8, int(round(font_px * fit)))
        block = _render_text_block(text, load_font(config.text_font, font_px),
                                   spacing, align)
        fit2 = min(usable_w / block.width, usable_h / block.height)
        if fit2 < 1.0:
            block = block.resize((max(1, int(block.width * fit2)),
                                  max(1, int(block.height * fit2))), Image.LANCZOS)

    if align == "left":
        x = int(round(margin))
    elif align == "right":
        x = int(round(W - margin - block.width))
    else:
        x = int(round((W - block.width) / 2))
    y = int(round((H - block.height) / 2))

    canvas = Image.new("L", (W, H), 0)
    canvas.paste(block, (max(0, x), max(0, y)))

    binary = np.where(np.array(canvas, np.uint8) >= 128, 255, 0).astype(np.uint8)
    paper = np.full((H, W, 3), 255, np.uint8)
    paper[binary > 0] = (0, 0, 0)
    return binary, paper, (block.width / ppm, block.height / ppm)


@contextlib.contextmanager
def _text_stroke_mode(config):
    prev = (config.uniform_stroke, config.blob_outline)
    config.uniform_stroke = (config.text_style != 'outline')
    config.blob_outline = True
    try:
        yield
    finally:
        config.uniform_stroke, config.blob_outline = prev


def _text_outlines(binary, config):
    cnts, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cnts:
        pts = c.reshape(-1, 2).astype(np.float32)
        if len(pts) < 8:
            continue
        length = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
        if length < config.line_min_length:
            continue
        if config.line_smooth > 0:
            pts = smooth_polyline(pts, config.line_smooth)
        out.append(np.vstack([pts, pts[:1]]).astype(np.float32))
    return out


def process_text(config):
    """Processes text string directly into ordered polyline toolpaths."""
    binary, paper, (bw_mm, bh_mm) = render_text_image(config)
    h, w = binary.shape[:2]
    if config.text_style == 'outline':
        polylines = _text_outlines(binary, config)
        stroke_img = binary
    else:
        with _text_stroke_mode(config):
            polylines, stroke_img = strokes_from_binary(binary, config, despeckle=False)
    images = stroke_previews(paper, polylines, stroke_img, extra={'binary': binary})

    total_pts = sum(len(p) for p in polylines)
    kind = "outline" if config.text_style == 'outline' else "single-stroke"
    n_rows = len(config.text_content.splitlines()) or 1
    info = (f"Text [{kind}]: {len(polylines)} strokes | Points: {total_pts} | "
            f"{n_rows} lines | Dimensions {bw_mm:.1f} × {bh_mm:.1f} mm")
    return polylines, images, w, h, info


def generate_gcode_text(polylines, w, h, config):
    """Generates G-Code for text engraving."""
    with _text_stroke_mode(config):
        gcode, stats = generate_gcode_line(polylines, w, h, config)
    kind = "outline" if config.text_style == 'outline' else "single-stroke"
    return gcode.replace("LINE (Uniform Stroke)",
                         f"TEXT (Text Engraving — {kind})"), stats


# ============================================================
# GUI INTERFACE
# ============================================================
UI_SCALE = 0.78

BASE_W, BASE_H = 1180, 820
MIN_W, MIN_H = 900, 600
SCREEN_USE_W = 0.94
SCREEN_USE_H = 0.88
UI_SCALE_MIN = 0.55


def ui_px(v):
    return max(1, int(v * UI_SCALE))


def ui_font(size):
    return max(7, int(size * UI_SCALE + 0.5))


def fit_ui_scale(root):
    global UI_SCALE
    avail_w = root.winfo_screenwidth() * SCREEN_USE_W
    avail_h = root.winfo_screenheight() * SCREEN_USE_H
    fit = min(avail_w / BASE_W, avail_h / BASE_H, 1.0)
    UI_SCALE = max(UI_SCALE_MIN, min(UI_SCALE, fit))
    return UI_SCALE


def place_window(root, w, h):
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = min(w, int(sw * SCREEN_USE_W))
    h = min(h, int(sh * SCREEN_USE_H))
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 3)
    root.geometry(f"{w}x{h}+{x}+{y}")
    return w, h


# ============================================================
# CROP DIALOG
# ============================================================
class CropDialog:
    """Interactive image cropping dialog with boundary manipulation."""

    HANDLE_SIZE = 8
    MIN_CROP_PX = 20
    OVERLAY_STIPPLE = 'gray50'

    def __init__(self, parent, pil_img, initial_rect, callback):
        self.pil_img = pil_img
        self.img_w, self.img_h = pil_img.size
        self.callback = callback

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("Crop Image")
        self.dlg.configure(bg="#1e1e2e")
        self.dlg.transient(parent)
        self.dlg.grab_set()

        sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
        max_w = int(sw * 0.85)
        max_h = int(sh * 0.80) - 80
        self.scale = min(max_w / self.img_w, max_h / self.img_h, 1.0)
        self.cv_w = max(100, int(self.img_w * self.scale))
        self.cv_h = max(100, int(self.img_h * self.scale))

        win_w = self.cv_w + 20
        win_h = self.cv_h + 120
        x = max(0, (sw - win_w) // 2)
        y = max(0, (sh - win_h) // 3)
        self.dlg.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.dlg.resizable(False, False)

        hdr = ttk.Frame(self.dlg)
        hdr.pack(fill=tk.X, padx=10, pady=(8, 4))
        ttk.Label(hdr, text="Crop Image — Drag box handles to select crop region",
                  font=("Segoe UI", ui_font(11), "bold"),
                  foreground="#89b4fa", background="#1e1e2e").pack(side=tk.LEFT)
        self.size_label = ttk.Label(hdr, text="", foreground="#a6adc8",
                                    background="#1e1e2e")
        self.size_label.pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(self.dlg, width=self.cv_w, height=self.cv_h,
                                bg="#11111b", highlightthickness=1,
                                highlightbackground="#585b70")
        self.canvas.pack(padx=10, pady=4)

        display_img = pil_img.resize((self.cv_w, self.cv_h), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW, tags="bg")

        if initial_rect:
            self.crop_x, self.crop_y = initial_rect[0], initial_rect[1]
            self.crop_w, self.crop_h = initial_rect[2], initial_rect[3]
        else:
            self.crop_x, self.crop_y = 0.0, 0.0
            self.crop_w, self.crop_h = float(self.img_w), float(self.img_h)

        self._drag_mode = None
        self._drag_start = None
        self._drag_orig = None

        self._draw_crop()

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)

        btn_frame = ttk.Frame(self.dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=(6, 10))

        ttk.Button(btn_frame, text="Confirm Crop",
                   command=self._confirm).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Full Image",
                   command=self._reset).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Reset Crop",
                   command=self._remove_crop).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Cancel",
                   command=self.dlg.destroy).pack(side=tk.RIGHT)

    def _img_to_cv(self, ix, iy):
        return ix * self.scale, iy * self.scale

    def _cv_to_img(self, cx, cy):
        return cx / self.scale, cy / self.scale

    def _draw_crop(self):
        self.canvas.delete("crop")
        cx1, cy1 = self._img_to_cv(self.crop_x, self.crop_y)
        cx2, cy2 = self._img_to_cv(self.crop_x + self.crop_w,
                                     self.crop_y + self.crop_h)

        for coords in [(0, 0, self.cv_w, cy1), (0, cy2, self.cv_w, self.cv_h),
                        (0, cy1, cx1, cy2), (cx2, cy1, self.cv_w, cy2)]:
            self.canvas.create_rectangle(*coords, fill="black",
                                          stipple=self.OVERLAY_STIPPLE,
                                          outline="", tags="crop")

        self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                      outline="#89b4fa", width=2, tags="crop")

        for i in (1, 2):
            gx = cx1 + (cx2 - cx1) * i / 3
            gy = cy1 + (cy2 - cy1) * i / 3
            self.canvas.create_line(gx, cy1, gx, cy2,
                                     fill="#585b70", dash=(3, 3), tags="crop")
            self.canvas.create_line(cx1, gy, cx2, gy,
                                     fill="#585b70", dash=(3, 3), tags="crop")

        hs = self.HANDLE_SIZE
        handles = [
            (cx1, cy1), (cx2, cy1), (cx1, cy2), (cx2, cy2),
            ((cx1+cx2)/2, cy1), ((cx1+cx2)/2, cy2),
            (cx1, (cy1+cy2)/2), (cx2, (cy1+cy2)/2),
        ]
        for hx, hy in handles:
            self.canvas.create_rectangle(hx - hs, hy - hs, hx + hs, hy + hs,
                                          fill="#89b4fa", outline="#cdd6f4",
                                          width=1, tags="crop")

        w, h = int(round(self.crop_w)), int(round(self.crop_h))
        self.size_label.config(text=f"{w} × {h} px")

    def _hit_test(self, cx, cy):
        x1, y1 = self._img_to_cv(self.crop_x, self.crop_y)
        x2, y2 = self._img_to_cv(self.crop_x + self.crop_w,
                                   self.crop_y + self.crop_h)
        hs = self.HANDLE_SIZE + 4

        on_left = abs(cx - x1) <= hs
        on_right = abs(cx - x2) <= hs
        on_top = abs(cy - y1) <= hs
        on_bottom = abs(cy - y2) <= hs

        if on_left and on_top:     return "nw"
        if on_right and on_top:    return "ne"
        if on_left and on_bottom:  return "sw"
        if on_right and on_bottom: return "se"
        if on_top:                 return "n"
        if on_bottom:              return "s"
        if on_left:                return "e_left"
        if on_right:               return "e_right"
        if x1 < cx < x2 and y1 < cy < y2:
            return "move"
        return "new"

    def _on_hover(self, ev):
        mode = self._hit_test(ev.x, ev.y)
        cursors = {
            "nw": "top_left_corner", "ne": "top_right_corner",
            "sw": "bottom_left_corner", "se": "bottom_right_corner",
            "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
            "e_left": "sb_h_double_arrow", "e_right": "sb_h_double_arrow",
            "move": "fleur", "new": "crosshair",
        }
        self.canvas.config(cursor=cursors.get(mode, "crosshair"))

    def _on_press(self, ev):
        self._drag_mode = self._hit_test(ev.x, ev.y)
        self._drag_start = (ev.x, ev.y)
        self._drag_orig = (self.crop_x, self.crop_y, self.crop_w, self.crop_h)
        if self._drag_mode == "new":
            ix, iy = self._cv_to_img(ev.x, ev.y)
            self.crop_x = max(0, min(ix, self.img_w))
            self.crop_y = max(0, min(iy, self.img_h))
            self.crop_w = 1.0
            self.crop_h = 1.0

    def _on_drag(self, ev):
        if not self._drag_mode or not self._drag_start:
            return
        dx_cv = ev.x - self._drag_start[0]
        dy_cv = ev.y - self._drag_start[1]
        dx = dx_cv / self.scale
        dy = dy_cv / self.scale
        ox, oy, ow, oh = self._drag_orig

        mode = self._drag_mode
        if mode == "move":
            nx = max(0, min(self.img_w - ow, ox + dx))
            ny = max(0, min(self.img_h - oh, oy + dy))
            self.crop_x, self.crop_y = nx, ny
            self.crop_w, self.crop_h = ow, oh
        elif mode == "new":
            ix, iy = self._cv_to_img(ev.x, ev.y)
            ix = max(0, min(ix, self.img_w))
            iy = max(0, min(iy, self.img_h))
            self.crop_x = min(ox, ix)
            self.crop_y = min(oy, iy)
            self.crop_w = max(1, abs(ix - ox))
            self.crop_h = max(1, abs(iy - oy))
        else:
            nx, ny, nw, nh = ox, oy, ow, oh
            if mode in ("nw", "sw", "e_left"):
                nw = max(self.MIN_CROP_PX / self.scale, ow - dx)
                nx = ox + ow - nw
            if mode in ("ne", "se", "e_right"):
                nw = max(self.MIN_CROP_PX / self.scale, ow + dx)
            if mode in ("nw", "ne", "n"):
                nh = max(self.MIN_CROP_PX / self.scale, oh - dy)
                ny = oy + oh - nh
            if mode in ("sw", "se", "s"):
                nh = max(self.MIN_CROP_PX / self.scale, oh + dy)
            nx = max(0, nx)
            ny = max(0, ny)
            nw = min(nw, self.img_w - nx)
            nh = min(nh, self.img_h - ny)
            self.crop_x, self.crop_y = nx, ny
            self.crop_w, self.crop_h = max(1, nw), max(1, nh)

        self._draw_crop()

    def _on_release(self, ev):
        self._drag_mode = None
        self._drag_start = None

    def _confirm(self):
        cx, cy = int(round(self.crop_x)), int(round(self.crop_y))
        cw, ch = int(round(self.crop_w)), int(round(self.crop_h))
        if cx <= 0 and cy <= 0 and cw >= self.img_w and ch >= self.img_h:
            self.callback(None)
        else:
            self.callback((max(0, cx), max(0, cy),
                           min(cw, self.img_w - cx), min(ch, self.img_h - cy)))
        self.dlg.destroy()

    def _reset(self):
        self.crop_x, self.crop_y = 0.0, 0.0
        self.crop_w, self.crop_h = float(self.img_w), float(self.img_h)
        self._draw_crop()

    def _remove_crop(self):
        self.callback(None)
        self.dlg.destroy()


class ImageToGCodeApp:

    RASTER_STYLES = {
        'zigzag': 'Continuous Zigzag',
        'hatch':  'Parallel Hatching',
        'offset': 'Offset Contours',
    }

    METHODS = {
        'color':   'Color — Flat Color Boundaries',
        'portrait': 'Portrait — Facial Stippling/XDoG',
        'line':    'Line — Uniform Stroke',
        'contour': 'Contour — Perimeter Tracing',
        'raster':  'Raster — Area Infill',
        'edge':    'Edge — Canny Contours',
        'text':    'Text — Direct Text Engraving',
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Image to G-Code — 3-Axis Motion Pipeline")
        fit_ui_scale(self.root)
        win_w, win_h = place_window(self.root, ui_px(BASE_W), ui_px(BASE_H))
        self.root.minsize(min(ui_px(MIN_W), win_w), min(ui_px(MIN_H), win_h))
        self.root.configure(bg="#1e1e2e")

        self.config = MachineConfig()
        self.image_path = None
        self.original_image_path = None
        self.crop_rect = None
        self.processed_data = None
        self.gcode = None
        self.preview_images = {}
        self.current_view = 'original'
        self.current_method = 'line'

        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4",
                         font=("Segoe UI", ui_font(10)))
        style.configure("Header.TLabel", background="#1e1e2e", foreground="#89b4fa",
                         font=("Segoe UI", ui_font(13), "bold"))
        style.configure("Method.TLabel", background="#1e1e2e", foreground="#f9e2af",
                         font=("Segoe UI", ui_font(10), "bold"))
        style.configure("TButton", font=("Segoe UI", ui_font(10)))
        style.configure("TLabelframe", background="#1e1e2e", foreground="#89b4fa",
                         font=("Segoe UI", ui_font(10), "bold"))
        style.configure("TLabelframe.Label", background="#1e1e2e", foreground="#89b4fa")
        style.configure("Active.TButton", font=("Segoe UI", ui_font(10), "bold"))
        style.configure("TRadiobutton", background="#1e1e2e", foreground="#cdd6f4",
                        font=("Segoe UI", ui_font(10)))
        style.configure("TCheckbutton", background="#1e1e2e", foreground="#cdd6f4",
                        font=("Segoe UI", ui_font(10)))
        style.configure("Accent.TButton", font=("Segoe UI", ui_font(11), "bold"),
                        foreground="#1e1e2e", background="#89b4fa")
        style.map("Accent.TButton", background=[("active", "#b4befe")])

        ttk.Label(self.root, text="Image to G-Code Converter",
                  style="Header.TLabel").pack(pady=(8, 2))
        ttk.Label(self.root,
                  text="Converts drawings and photographs into standard CNC G-Code"
                  ).pack(pady=(0, 8))

        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        left = ttk.Frame(main, width=ui_px(350))
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left.pack_propagate(False)

        bottom = ttk.Frame(left)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        scroll_area = ttk.Frame(left)
        scroll_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        opt_canvas = tk.Canvas(scroll_area, bg="#1e1e2e", highlightthickness=0)
        vsb = ttk.Scrollbar(scroll_area, orient=tk.VERTICAL, command=opt_canvas.yview)
        opt_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        opt_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        opts = ttk.Frame(opt_canvas)
        opts_win = opt_canvas.create_window((0, 0), window=opts, anchor="nw")
        opts.bind("<Configure>",
                  lambda e: opt_canvas.configure(scrollregion=opt_canvas.bbox("all")))
        opt_canvas.bind("<Configure>",
                        lambda e: opt_canvas.itemconfigure(opts_win, width=e.width))

        def _on_wheel(event):
            opt_canvas.yview_scroll(int(-event.delta / 120), "units")
        opt_canvas.bind("<Enter>",
                        lambda e: opt_canvas.bind_all("<MouseWheel>", _on_wheel))
        opt_canvas.bind("<Leave>",
                        lambda e: opt_canvas.unbind_all("<MouseWheel>"))

        ff = ttk.LabelFrame(opts, text="Input Image")
        self.file_frame = ff
        ff.pack(fill=tk.X, pady=(0, 4))
        self.file_label = ttk.Label(ff, text="No file selected...", wraplength=ui_px(280))
        self.file_label.pack(padx=5, pady=4)
        btn_row = ttk.Frame(ff)
        btn_row.pack(fill=tk.X, padx=5, pady=(0, 4))
        ttk.Button(btn_row, text="Select Image...", command=self._browse).pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.crop_btn = ttk.Button(btn_row, text="Crop Image...",
                                    command=self._open_crop_dialog, state=tk.DISABLED)
        self.crop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))
        self.crop_info_label = ttk.Label(ff, text="", foreground="#a6adc8", wraplength=ui_px(280))
        self.crop_info_label.pack(padx=5, pady=(0, 2))

        mf = ttk.LabelFrame(opts, text="Drawing Algorithm")
        self.method_frame = mf
        mf.pack(fill=tk.X, pady=(0, 4))
        self.method_var = tk.StringVar(value='line')
        methods_info = [
            ('color',   'Color',   'Flat color artwork, cartoons, logos'),
            ('portrait','Portrait','Portrait photography → sketch lines'),
            ('line',    'Line',    'Uniform stroke width (centerline)'),
            ('contour', 'Contour', 'Perimeter tracing around dark regions'),
            ('raster',  'Raster',  'Area infill with continuous paths'),
            ('edge',    'Edge',    'Canny edge detection contours'),
            ('text',    'Text',    'Direct text engraving (no input image)'),
        ]
        for val, label, desc in methods_info:
            row = ttk.Frame(mf)
            row.pack(fill=tk.X, padx=5, pady=1)
            rb = ttk.Radiobutton(row, text=label, variable=self.method_var,
                                  value=val, command=self._on_method_change)
            rb.pack(side=tk.LEFT)
            ttk.Label(row, text=f"— {desc}", foreground="#a6adc8").pack(side=tk.LEFT)

        sf = ttk.LabelFrame(opts, text="Machine Configuration")
        sf.pack(fill=tk.X, pady=(0, 4))
        settings = [
            ("Work Area X (mm):", "work_area_x"),
            ("Work Area Y (mm):", "work_area_y"),
            ("Z Pen Up (mm):", "z_pen_up"),
            ("Z Pen Down (mm):", "z_pen_down"),
            ("Z End Position (mm):", "z_end"),
            ("Draw Feed Rate:", "feed_rate_draw"),
            ("Travel Feed Rate:", "feed_rate_travel"),
            ("Z-Axis Feed Rate:", "feed_rate_z"),
            ("Return Feed Rate:", "feed_rate_return"),
        ]
        self.setting_vars = {}
        for lbl, attr in settings:
            row = ttk.Frame(sf)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=lbl, width=18).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(getattr(self.config, attr)))
            self.setting_vars[attr] = var
            ttk.Entry(row, textvariable=var, width=8).pack(side=tk.RIGHT)

        self._build_place_panel(opts)

        of = ttk.LabelFrame(opts, text="Output Format")
        of.pack(fill=tk.X, pady=(0, 4))
        self.linenum_var = tk.BooleanVar(value=self.config.line_numbers)
        ttk.Checkbutton(of, text="Line numbering (N10, N20, ...)",
                        variable=self.linenum_var).pack(padx=5, pady=2, anchor=tk.W)
        self.comments_var = tk.BooleanVar(value=self.config.emit_comments)
        ttk.Checkbutton(of, text="Emit comments ';'",
                        variable=self.comments_var).pack(padx=5, pady=1, anchor=tk.W)
        self.useg0_var = tk.BooleanVar(value=self.config.use_g0)
        ttk.Checkbutton(of, text="Use G0 for rapid travels (unchecked = G1)",
                        variable=self.useg0_var).pack(padx=5, pady=(1, 4), anchor=tk.W)

        pf = ttk.LabelFrame(opts, text="Image Processing")
        self.proc_frame = pf
        pf.pack(fill=tk.X, pady=(0, 4))

        tr = ttk.Frame(pf)
        tr.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(tr, text="Threshold:").pack(side=tk.LEFT)
        self.threshold_var = tk.IntVar(value=self.config.threshold)
        self.thresh_lbl = ttk.Label(tr, text=str(self.config.threshold), width=4)
        self.thresh_lbl.pack(side=tk.RIGHT)
        ttk.Scale(tr, from_=0, to=255, variable=self.threshold_var,
                  orient=tk.HORIZONTAL,
                  command=lambda v: self.thresh_lbl.config(text=str(int(float(v))))
                  ).pack(side=tk.RIGHT, fill=tk.X, expand=True)

        self.simp_frame = ttk.Frame(pf)
        self.simp_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(self.simp_frame, text="Simplify:").pack(side=tk.LEFT)
        self.simplify_var = tk.DoubleVar(value=self.config.simplify_epsilon)
        ttk.Scale(self.simp_frame, from_=0, to=5, variable=self.simplify_var,
                  orient=tk.HORIZONTAL).pack(side=tk.RIGHT, fill=tk.X, expand=True)

        self.ctr_frame = ttk.Frame(pf)
        self.ctr_frame.pack(fill=tk.X, padx=5, pady=2)
        self.ctr_center_var = tk.BooleanVar(value=self.config.contour_centerline)
        ttk.Checkbutton(self.ctr_frame,
                        text="Reduce thick strokes to 1px centerline",
                        variable=self.ctr_center_var).pack(anchor=tk.W)
        ttk.Label(self.ctr_frame,
                  text="Unchecked = trace both perimeter edges.",
                  foreground="#a6adc8").pack(anchor=tk.W, padx=(18, 0))

        self.raster_frame = ttk.Frame(pf)
        self.raster_frame.pack(fill=tk.X, padx=5, pady=2)

        rr0 = ttk.Frame(self.raster_frame)
        rr0.pack(fill=tk.X, pady=1)
        ttk.Label(rr0, text="Infill style:", width=16).pack(side=tk.LEFT)
        self.raster_style_var = tk.StringVar(value=self.RASTER_STYLES[self.config.raster_style])
        ttk.Combobox(rr0, textvariable=self.raster_style_var, state="readonly",
                     values=list(self.RASTER_STYLES.values()), width=17
                     ).pack(side=tk.RIGHT)

        rr1 = ttk.Frame(self.raster_frame)
        rr1.pack(fill=tk.X, pady=1)
        ttk.Label(rr1, text="Spacing (mm):", width=16).pack(side=tk.LEFT)
        self.raster_res_var = tk.StringVar(value=str(self.config.raster_resolution))
        ttk.Entry(rr1, textvariable=self.raster_res_var, width=6).pack(side=tk.RIGHT)

        rr2 = ttk.Frame(self.raster_frame)
        rr2.pack(fill=tk.X, pady=1)
        ttk.Label(rr2, text="Angle (deg):", width=16).pack(side=tk.LEFT)
        self.raster_angle_var = tk.StringVar(value=str(self.config.raster_angle))
        ttk.Entry(rr2, textvariable=self.raster_angle_var, width=6).pack(side=tk.RIGHT)

        rr3 = ttk.Frame(self.raster_frame)
        rr3.pack(fill=tk.X, pady=1)
        ttk.Label(rr3, text="Supersample (x):", width=16).pack(side=tk.LEFT)
        self.raster_super_var = tk.StringVar(value=str(self.config.raster_supersample))
        ttk.Entry(rr3, textvariable=self.raster_super_var, width=6).pack(side=tk.RIGHT)

        rr4 = ttk.Frame(self.raster_frame)
        rr4.pack(fill=tk.X, pady=1)
        ttk.Label(rr4, text="Smoothing:", width=16).pack(side=tk.LEFT)
        self.raster_smooth_var = tk.StringVar(value=str(self.config.raster_smooth))
        ttk.Entry(rr4, textvariable=self.raster_smooth_var, width=6).pack(side=tk.RIGHT)

        self.raster_cross_var = tk.BooleanVar(value=self.config.raster_cross)
        ttk.Checkbutton(self.raster_frame, text="Cross-hatch (dual layer)",
                        variable=self.raster_cross_var).pack(anchor=tk.W, pady=1)
        self.raster_outline_var = tk.BooleanVar(value=self.config.raster_outline)
        ttk.Checkbutton(self.raster_frame, text="Trace boundary outline first",
                        variable=self.raster_outline_var).pack(anchor=tk.W, pady=1)
        ttk.Label(self.raster_frame,
                  text="Spacing = tool tip width. Increase if too dense;\n"
                       "decrease if gaps appear.",
                  foreground="#a6adc8", justify=tk.LEFT).pack(anchor=tk.W, pady=(1, 2))

        self.canny_frame = ttk.Frame(pf)
        self.canny_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(self.canny_frame, text="Canny thresholds:").pack(side=tk.LEFT)
        self.canny_low_var = tk.StringVar(value=str(self.config.canny_low))
        self.canny_high_var = tk.StringVar(value=str(self.config.canny_high))
        ttk.Entry(self.canny_frame, textvariable=self.canny_high_var, width=5).pack(side=tk.RIGHT)
        ttk.Label(self.canny_frame, text="—").pack(side=tk.RIGHT)
        ttk.Entry(self.canny_frame, textvariable=self.canny_low_var, width=5).pack(side=tk.RIGHT)

        self.invert_var = tk.BooleanVar(value=self.config.invert)
        ttk.Checkbutton(pf, text="Invert colors (draw dark regions)", variable=self.invert_var
                        ).pack(padx=5, pady=2, anchor=tk.W)

        self.proc_tail = ttk.Frame(opts)
        self.proc_tail.pack(fill=tk.X)

        self.line_frame = ttk.LabelFrame(opts, text="Stroke Settings")
        self.line_frame.pack(fill=tk.X, pady=(0, 4))
        self.uniform_var = tk.BooleanVar(value=self.config.uniform_stroke)
        ttk.Checkbutton(self.line_frame,
                        text="Uniform stroke (skeletonize 1px)",
                        variable=self.uniform_var).pack(padx=5, pady=2, anchor=tk.W)
        self.adaptive_var = tk.BooleanVar(value=self.config.adaptive_threshold)
        ttk.Checkbutton(self.line_frame, text="Adaptive thresholding",
                        variable=self.adaptive_var).pack(padx=5, pady=1, anchor=tk.W)
        self.despeckle_var = tk.BooleanVar(value=self.config.despeckle)
        ttk.Checkbutton(self.line_frame, text="Despeckle (remove noise)",
                        variable=self.despeckle_var).pack(padx=5, pady=1, anchor=tk.W)
        r1 = ttk.Frame(self.line_frame)
        r1.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(r1, text="Min stroke length (px):", width=21).pack(side=tk.LEFT)
        self.line_minlen_var = tk.StringVar(value=str(self.config.line_min_length))
        ttk.Entry(r1, textvariable=self.line_minlen_var, width=6).pack(side=tk.RIGHT)
        r2 = ttk.Frame(self.line_frame)
        r2.pack(fill=tk.X, padx=5, pady=(1, 4))
        ttk.Label(r2, text="Simplification tol (px):", width=21).pack(side=tk.LEFT)
        self.line_simp_var = tk.StringVar(value=str(self.config.line_simplify))
        ttk.Entry(r2, textvariable=self.line_simp_var, width=6).pack(side=tk.RIGHT)

        r3 = ttk.Frame(self.line_frame)
        r3.pack(fill=tk.X, padx=5, pady=(1, 4))
        ttk.Label(r3, text="Bridge gaps (px):", width=21).pack(side=tk.LEFT)
        self.line_bridge_var = tk.StringVar(value=str(self.config.line_bridge_px))
        ttk.Entry(r3, textvariable=self.line_bridge_var, width=6).pack(side=tk.RIGHT)

        self.color_frame = ttk.LabelFrame(opts, text="Color Boundary Settings")
        self.color_frame.pack(fill=tk.X, pady=(0, 4))
        for lbl, attr, var_name in [
                ("Color clusters:", "color_levels", "cl_levels_var"),
                ("Denoise (odd, 0=off):", "color_denoise", "cl_denoise_var"),
                ("Min region area (px):", "color_min_area", "cl_area_var")]:
            row = ttk.Frame(self.color_frame)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=lbl, width=21).pack(side=tk.LEFT)
            v = tk.StringVar(value=str(getattr(self.config, attr)))
            setattr(self, var_name, v)
            ttk.Entry(row, textvariable=v, width=6).pack(side=tk.RIGHT)
        ttk.Label(self.color_frame,
                  text="Missing lines → INCREASE clusters.\n"
                       "Too fragmented → DECREASE (4–6).",
                  foreground="#a6adc8", justify=tk.LEFT).pack(padx=5, pady=(2, 4),
                                                              anchor=tk.W)

        self.portrait_frame = ttk.LabelFrame(opts, text="Portrait Settings (XDoG)")
        self.portrait_frame.pack(fill=tk.X, pady=(0, 4))
        for lbl, attr, var_name in [
                ("Sensitivity (σ):", "portrait_sensitivity", "pt_thresh_var"),
                ("Detail σ (small=fine):", "portrait_detail", "pt_detail_var"),
                ("Skin smoothing:", "portrait_denoise", "pt_denoise_var"),
                ("Min blob area (px):", "portrait_min_area", "pt_area_var")]:
            row = ttk.Frame(self.portrait_frame)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=lbl, width=21).pack(side=tk.LEFT)
            v = tk.StringVar(value=str(getattr(self.config, attr)))
            setattr(self, var_name, v)
            ttk.Entry(row, textvariable=v, width=6).pack(side=tk.RIGHT)
        ttk.Label(self.portrait_frame,
                  text="Missing lines → DECREASE sensitivity (e.g. 0.4).\n"
                       "Too much noise → INCREASE sensitivity (e.g. 0.9)\n"
                       "or increase 'min blob area'.",
                  foreground="#a6adc8", justify=tk.LEFT).pack(padx=5, pady=(2, 4),
                                                              anchor=tk.W)

        self.text_frame = ttk.LabelFrame(opts, text="Text Content")
        self.text_frame.pack(fill=tk.X, pady=(0, 4))
        self.text_input = tk.Text(self.text_frame, height=4, bg="#313244",
                                  fg="#cdd6f4", insertbackground="#cdd6f4",
                                  relief=tk.FLAT, wrap=tk.WORD,
                                  font=("Segoe UI", ui_font(11)))
        self.text_input.insert("1.0", self.config.text_content)
        self.text_input.pack(fill=tk.X, padx=5, pady=(4, 2))
        ttk.Label(self.text_frame,
                  text="Enter = newline. Supports full Unicode characters.",
                  foreground="#a6adc8").pack(padx=5, anchor=tk.W)

        rowf = ttk.Frame(self.text_frame)
        rowf.pack(fill=tk.X, padx=5, pady=(4, 1))
        ttk.Label(rowf, text="Font:", width=13).pack(side=tk.LEFT)
        self.txt_font_var = tk.StringVar(value=self.config.text_font)
        ttk.Combobox(rowf, textvariable=self.txt_font_var,
                     values=list(list_system_fonts().keys()), width=15,
                     font=("Segoe UI", ui_font(9))).pack(side=tk.RIGHT)

        for lbl, attr, var_name in [
                ("Cap Height (mm):", "text_height", "txt_size_var"),
                ("Line spacing (x):", "text_line_spacing", "txt_spacing_var"),
                ("Margin (mm):", "text_margin", "txt_margin_var"),
                ("Resolution (px/mm):", "text_render_scale", "txt_scale_var")]:
            row = ttk.Frame(self.text_frame)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=lbl, width=21).pack(side=tk.LEFT)
            v = tk.StringVar(value=str(getattr(self.config, attr)))
            setattr(self, var_name, v)
            ttk.Entry(row, textvariable=v, width=6).pack(side=tk.RIGHT)

        rowa = ttk.Frame(self.text_frame)
        rowa.pack(fill=tk.X, padx=5, pady=(3, 1))
        ttk.Label(rowa, text="Alignment:", width=13).pack(side=tk.LEFT)
        self.txt_align_var = tk.StringVar(value=self.config.text_align)
        for val, lab in (("left", "Left"), ("center", "Center"), ("right", "Right")):
            ttk.Radiobutton(rowa, text=lab, value=val,
                            variable=self.txt_align_var).pack(side=tk.LEFT, padx=2)

        rows = ttk.Frame(self.text_frame)
        rows.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(rows, text="Stroke style:", width=13).pack(side=tk.LEFT)
        self.txt_style_var = tk.StringVar(value=self.config.text_style)
        ttk.Radiobutton(rows, text="Single-stroke", value="single",
                        variable=self.txt_style_var).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(rows, text="Outline", value="outline",
                        variable=self.txt_style_var).pack(side=tk.LEFT, padx=2)

        self.txt_autofit_var = tk.BooleanVar(value=self.config.text_autofit)
        ttk.Checkbutton(self.text_frame, text="Auto-scale text to fill work area",
                        variable=self.txt_autofit_var).pack(padx=5, pady=1, anchor=tk.W)

        rowm = ttk.Frame(self.text_frame)
        rowm.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(rowm, text="Min stroke length (px):", width=21).pack(side=tk.LEFT)
        ttk.Entry(rowm, textvariable=self.line_minlen_var, width=6).pack(side=tk.RIGHT)

        ttk.Label(self.text_frame,
                  text="Single-stroke = single centerline handwriting path.\n"
                       "Outline = hollow contour boundary path.",
                  foreground="#a6adc8", justify=tk.LEFT).pack(padx=5, pady=(2, 4),
                                                              anchor=tk.W)

        self.arc_frame = ttk.LabelFrame(opts, text="Circular Arc Fitting (G2/G3)")
        self.arc_frame.pack(fill=tk.X, pady=(0, 4))
        self.arcs_var = tk.BooleanVar(value=self.config.use_arcs)
        ttk.Checkbutton(self.arc_frame,
                        text="Use G2/G3 arcs instead of linear G1 segments",
                        variable=self.arcs_var).pack(padx=5, pady=2, anchor=tk.W)
        r3 = ttk.Frame(self.arc_frame)
        r3.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(r3, text="Arc fitting tolerance (mm):", width=21).pack(side=tk.LEFT)
        self.arc_tol_var = tk.StringVar(value=str(self.config.arc_tolerance))
        ttk.Entry(r3, textvariable=self.arc_tol_var, width=6).pack(side=tk.RIGHT)
        r4 = ttk.Frame(self.arc_frame)
        r4.pack(fill=tk.X, padx=5, pady=(1, 4))
        ttk.Label(r4, text="Minimum points per arc:", width=21).pack(side=tk.LEFT)
        self.arc_minpts_var = tk.StringVar(value=str(self.config.arc_min_points))
        ttk.Entry(r4, textvariable=self.arc_minpts_var, width=6).pack(side=tk.RIGHT)

        self.opts_tail = ttk.Frame(opts)
        self.opts_tail.pack(fill=tk.X)

        bf = ttk.LabelFrame(bottom, text="Actions")
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="1. Preview Toolpaths",
                   command=self._preview).pack(fill=tk.X, padx=5, pady=(4, 2))
        ttk.Button(bf, text="2. GENERATE G-CODE",
                   style="Accent.TButton",
                   command=self._generate).pack(fill=tk.X, padx=5, pady=2)
        self.save_btn = ttk.Button(bf, text="3. Save .gcode File",
                                   command=self._save, state=tk.DISABLED)
        self.save_btn.pack(fill=tk.X, padx=5, pady=(2, 5))

        self.status_label = ttk.Label(bottom, text="Ready — select an image to start.",
                                      foreground="#a6e3a1", wraplength=ui_px(330))
        self.status_label.pack(pady=3)

        self.info_text = tk.Text(bottom, height=7, bg="#313244", fg="#cdd6f4",
                                  font=("Consolas", ui_font(9)), relief=tk.FLAT, wrap=tk.WORD)
        self.info_text.pack(fill=tk.X)

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        vf = ttk.Frame(right)
        vf.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(vf, text="View:", style="Header.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.view_btn_frame = vf

        self.method_desc = ttk.Label(right, text="", style="Method.TLabel")
        self.method_desc.pack(pady=(0, 2))
        self.view_desc = ttk.Label(right, text="", foreground="#a6adc8")
        self.view_desc.pack(pady=(0, 3))

        self.canvas = tk.Canvas(right, bg="#313244", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.legend_frame = ttk.Frame(right)
        self.legend_frame.pack(fill=tk.X, pady=(3, 0))
        self.legend_frame.pack_forget()

        self._on_method_change()

    # ========================================================
    # PLACEMENT PREVIEW PANEL
    # ========================================================
    PLACE_PAD = 14
    PLACE_GRIP = 11

    def _build_place_panel(self, parent):
        self._place_drag_mode = None
        self._place_syncing = False
        self._img_aspect_cache = {}

        pf = ttk.LabelFrame(parent, text="Work Area Placement")
        pf.pack(fill=tk.X, pady=(0, 4))

        self.place_manual_var = tk.BooleanVar(value=self.config.place_mode == 'manual')
        ttk.Checkbutton(pf, text="Manual positioning (custom bounding box)",
                        variable=self.place_manual_var,
                        command=self._place_mode_changed).pack(padx=5, pady=(3, 0), anchor=tk.W)
        self.place_ratio_var = tk.BooleanVar(value=self.config.place_keep_ratio)
        ttk.Checkbutton(pf, text="Preserve aspect ratio",
                        variable=self.place_ratio_var,
                        command=self._place_ratio_changed).pack(padx=5, pady=(0, 3), anchor=tk.W)

        side = ui_px(226)
        self.place_canvas = tk.Canvas(pf, width=side, height=side, bg="#181825",
                                      highlightthickness=0, cursor="hand2")
        self.place_canvas.pack(padx=5, pady=3)
        self.place_canvas.bind("<Button-1>", self._place_press)
        self.place_canvas.bind("<B1-Motion>", self._place_drag)
        self.place_canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_place_drag_mode", None))

        self.place_vars = {}
        grid = ttk.Frame(pf)
        grid.pack(fill=tk.X, padx=5, pady=(0, 4))
        for col, (attr, lbl) in enumerate([("place_x", "X"), ("place_y", "Y"),
                                           ("place_w", "Width"), ("place_h", "Height")]):
            cell = ttk.Frame(grid)
            cell.grid(row=col // 2, column=col % 2, sticky="ew", padx=(0, 4), pady=1)
            grid.columnconfigure(col % 2, weight=1)
            ttk.Label(cell, text=f"{lbl}:", width=6).pack(side=tk.LEFT)
            var = tk.StringVar(value=f"{getattr(self.config, attr):g}")
            var.trace_add("write", lambda *_: self._place_from_entries())
            self.place_vars[attr] = var
            ttk.Entry(cell, textvariable=var, width=6).pack(side=tk.LEFT)

        btns = ttk.Frame(pf)
        btns.pack(fill=tk.X, padx=5, pady=(0, 5))
        ttk.Button(btns, text="Fit Work Area",
                   command=lambda: self._place_preset("full")).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(btns, text="Center",
                   command=lambda: self._place_preset("center")).pack(side=tk.LEFT, expand=True,
                                                                      fill=tk.X, padx=(4, 0))

        self.place_hint = ttk.Label(pf, text="", foreground="#a6adc8", wraplength=ui_px(215))
        self.place_hint.pack(padx=5, pady=(0, 4), anchor="w")

        self.place_canvas.after(60, self._place_redraw)

    def _place_scale(self):
        side = int(self.place_canvas.cget("width"))
        span = max(self.config.work_area_x, self.config.work_area_y, 1.0)
        return (side - 2 * self.PLACE_PAD) / span, side

    def _mm_to_cv(self, mx, my):
        s, side = self._place_scale()
        return self.PLACE_PAD + mx * s, side - self.PLACE_PAD - my * s

    def _cv_to_mm(self, cx, cy):
        s, side = self._place_scale()
        return (cx - self.PLACE_PAD) / s, (side - self.PLACE_PAD - cy) / s

    def _img_aspect(self):
        if not self.image_path:
            return None
        if self.image_path not in self._img_aspect_cache:
            try:
                with Image.open(self.image_path) as im:
                    self._img_aspect_cache[self.image_path] = im.width / im.height
            except Exception:
                self._img_aspect_cache[self.image_path] = None
        return self._img_aspect_cache[self.image_path]

    def _place_redraw(self):
        c = getattr(self, "place_canvas", None)
        if c is None:
            return
        c.delete("all")
        cfg = self.config
        x0, y0 = self._mm_to_cv(0, 0)
        x1, y1 = self._mm_to_cv(cfg.work_area_x, cfg.work_area_y)

        c.create_rectangle(x0, y1, x1, y0, fill="#11111b", outline="#585b70")
        step = 10.0
        while (step / max(cfg.work_area_x, 1.0)) * (x1 - x0) < 12:
            step *= 2
        g = step
        while g < cfg.work_area_x:
            gx, _ = self._mm_to_cv(g, 0)
            c.create_line(gx, y1, gx, y0, fill="#282839")
            g += step
        g = step
        while g < cfg.work_area_y:
            _, gy = self._mm_to_cv(0, g)
            c.create_line(x0, gy, x1, gy, fill="#282839")
            g += step

        manual = self.place_manual_var.get()
        aspect = self._img_aspect()
        iw, ih = (aspect or 1.0), 1.0
        bx, by, bw, bh = place_box(iw * 1000, ih * 1000, cfg)

        px0, py0 = self._mm_to_cv(bx, by)
        px1, py1 = self._mm_to_cv(bx + bw, by + bh)
        col = "#89b4fa" if manual else "#585b70"
        c.create_rectangle(px0, py1, px1, py0, fill="#1e2030", outline=col, width=2)
        c.create_text((px0 + px1) / 2, (py0 + py1) / 2,
                      text=f"{bw:.0f}×{bh:.0f}", fill=col, font=("Segoe UI", ui_font(9), "bold"))

        if manual:
            gs = self.PLACE_GRIP
            c.create_rectangle(px1 - gs, py0 - gs, px1, py0, fill=col, outline="")

        c.create_oval(x0 - 3, y0 - 3, x0 + 3, y0 + 3, fill="#f38ba8", outline="")
        c.create_text(x0 + 4, y0 - 8, text="0,0", anchor="sw", fill="#f38ba8",
                      font=("Segoe UI", ui_font(8)))

        if manual:
            self.place_hint.config(
                text=f"Drag box to move, drag bottom-right corner to resize. "
                     f"Drawing fits inside {bw:.0f}×{bh:.0f} mm at X{bx:.0f} Y{by:.0f}.")
        else:
            self.place_hint.config(text="Auto-fitted and centered in work area. "
                                        "Check 'Manual positioning' to customize.")

    def _place_press(self, ev):
        if not self.place_manual_var.get():
            return
        cfg = self.config
        px1, py0 = self._mm_to_cv(cfg.place_x + cfg.place_w, cfg.place_y)
        gs = self.PLACE_GRIP + 3
        if abs(ev.x - px1) <= gs and abs(ev.y - py0) <= gs:
            self._place_drag_mode = "size"
        else:
            self._place_drag_mode = "move"
            mx, my = self._cv_to_mm(ev.x, ev.y)
            self._place_grab = (mx - cfg.place_x, my - cfg.place_y)

    def _place_drag(self, ev):
        if not self._place_drag_mode:
            return
        cfg = self.config
        mx, my = self._cv_to_mm(ev.x, ev.y)

        if self._place_drag_mode == "move":
            gx, gy = self._place_grab
            cfg.place_x = max(0.0, min(cfg.work_area_x - cfg.place_w, mx - gx))
            cfg.place_y = max(0.0, min(cfg.work_area_y - cfg.place_h, my - gy))
        else:
            top = cfg.place_y + cfg.place_h
            w = max(5.0, min(cfg.work_area_x - cfg.place_x, mx - cfg.place_x))
            h = max(5.0, min(top, top - my))
            aspect = self._img_aspect()
            if self.place_ratio_var.get() and aspect:
                h = w / aspect
                if h > top:
                    h = top
                    w = h * aspect
                if cfg.place_x + w > cfg.work_area_x:
                    w = cfg.work_area_x - cfg.place_x
                    h = w / aspect
            cfg.place_w, cfg.place_h = w, h
            cfg.place_y = top - h

        self._place_to_entries()
        self._place_redraw()

    def _place_to_entries(self):
        self._place_syncing = True
        for attr, var in self.place_vars.items():
            var.set(f"{getattr(self.config, attr):.1f}")
        self._place_syncing = False

    def _place_from_entries(self):
        if self._place_syncing:
            return
        for attr, var in self.place_vars.items():
            try:
                setattr(self.config, attr, float(var.get()))
            except ValueError:
                pass
        self._place_redraw()

    def _place_mode_changed(self):
        self.config.place_mode = 'manual' if self.place_manual_var.get() else 'fit'
        self._place_redraw()

    def _place_ratio_changed(self):
        self.config.place_keep_ratio = self.place_ratio_var.get()
        self._place_redraw()

    def _place_preset(self, kind):
        cfg = self.config
        if kind == "full":
            cfg.place_x = cfg.place_y = 0.0
            cfg.place_w, cfg.place_h = cfg.work_area_x, cfg.work_area_y
        else:
            cfg.place_x = (cfg.work_area_x - cfg.place_w) / 2
            cfg.place_y = (cfg.work_area_y - cfg.place_h) / 2
        self._place_to_entries()
        self._place_redraw()

    def _on_method_change(self):
        m = self.method_var.get()
        self.current_method = m

        if m == 'text':
            self.file_frame.pack_forget()
            self.proc_frame.pack_forget()
            self.text_frame.pack(fill=tk.X, pady=(0, 4), before=self.opts_tail)
        else:
            self.file_frame.pack(fill=tk.X, pady=(0, 4), before=self.method_frame)
            self.proc_frame.pack(fill=tk.X, pady=(0, 4), before=self.proc_tail)
            self.text_frame.pack_forget()

        if m in ('line', 'portrait', 'color'):
            self.simp_frame.pack_forget()
            self.raster_frame.pack_forget()
            self.canny_frame.pack_forget()
        elif m == 'contour':
            self.simp_frame.pack(fill=tk.X, padx=5, pady=2)
            self.raster_frame.pack_forget()
            self.canny_frame.pack_forget()
        elif m == 'raster':
            self.simp_frame.pack_forget()
            self.raster_frame.pack(fill=tk.X, padx=5, pady=2)
            self.canny_frame.pack_forget()
        elif m == 'edge':
            self.simp_frame.pack(fill=tk.X, padx=5, pady=2)
            self.raster_frame.pack_forget()
            self.canny_frame.pack(fill=tk.X, padx=5, pady=2)

        if m == 'contour':
            self.ctr_frame.pack(fill=tk.X, padx=5, pady=2)
        else:
            self.ctr_frame.pack_forget()

        if m in ('line', 'portrait', 'color'):
            self.line_frame.pack(fill=tk.X, pady=(0, 4), before=self.opts_tail)
        else:
            self.line_frame.pack_forget()
        if m == 'color':
            self.color_frame.pack(fill=tk.X, pady=(0, 4), before=self.opts_tail)
        else:
            self.color_frame.pack_forget()
        if m == 'portrait':
            self.portrait_frame.pack(fill=tk.X, pady=(0, 4), before=self.opts_tail)
        else:
            self.portrait_frame.pack_forget()
        self.arc_frame.pack(fill=tk.X, pady=(0, 4), before=self.opts_tail)

        descriptions = {
            'color': ' COLOR — Flat color region boundaries (cartoons, logos, vector art)',
            'portrait': ' PORTRAIT — Facial sketch feature lines (XDoG) with G2/G3 arcs',
            'line': ' LINE — Uniform centerline drawing paths (skeleton) with G2/G3 arcs',
            'contour': ' CONTOUR — Perimeter tracing around dark regions (with optional centerline)',
            'raster': ' RASTER — Continuous area infill with minimal Z-hops (zigzag / hatching / offset)',
            'edge': ' EDGE — High-precision Canny edge contour detection',
            'text': ' TEXT — Direct Unicode text engraving (no input image required)',
        }
        if hasattr(self, 'method_desc'):
            self.method_desc.config(text=descriptions.get(m, ''))

    def _update_view_buttons(self, view_modes):
        for w in self.view_btn_frame.winfo_children()[1:]:
            w.destroy()
        for mode, label in view_modes:
            btn = ttk.Button(self.view_btn_frame, text=label,
                             command=lambda m=mode: self._switch_view(m))
            btn.pack(side=tk.LEFT, padx=2)

    def _switch_view(self, mode):
        if mode not in self.preview_images:
            messagebox.showinfo("Notice", "Click 'Preview Toolpaths' first!")
            return
        self.current_view = mode
        self._display_view()

    def _display_view(self):
        if self.current_view not in self.preview_images:
            return
        img_pil = self.preview_images[self.current_view]
        cw = self.canvas.winfo_width() or 700
        ch = self.canvas.winfo_height() or 500
        ratio = min(cw / img_pil.width, ch / img_pil.height, 1.0)
        ns = (max(1, int(img_pil.width * ratio)), max(1, int(img_pil.height * ratio)))
        resized = img_pil.resize(ns, Image.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized)
        self.canvas.delete("all")
        self.canvas.create_image(cw//2, ch//2, image=self.tk_image, anchor=tk.CENTER)

        descs = {
            'original': ' Original input image',
            'preview': {
                'contour': 'Contour: white = toolpath | Green = start points',
                'raster': ' Infill: white = toolpath | Green = pen down points',
                'edge': 'Edge: white = toolpath | Green = start points',
            }.get(self.current_method, ''),
            'overlay': ' Toolpaths overlaid onto input image',
            'binary': ' Binary mask: WHITE = infill area | BLACK = ignored',
            'raster': ' Toolpath simulation: white = draw | red = rapid travel (pen up)',
            'canny_raw': ' Raw Canny edge output',
        }
        self.view_desc.config(text=descs.get(self.current_view, ''))

        self.legend_frame.pack_forget()
        for w in self.legend_frame.winfo_children():
            w.destroy()
        if self.current_view in ('preview', 'raster'):
            items = [
                (" White = Draw path (pen down)", "#ffffff"),
                (" Red = Rapid travel (pen up)", "#f38ba8"),
                (" Green = Start point", "#a6e3a1"),
            ]
            for txt, clr in items:
                ttk.Label(self.legend_frame, text=txt, foreground=clr).pack(side=tk.LEFT, padx=6)
            self.legend_frame.pack(fill=tk.X, pady=(3, 0))

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select Input Image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"), ("All files", "*.*")]
        )
        if path:
            self.image_path = path
            self.original_image_path = path
            self.crop_rect = None
            self.crop_info_label.config(text="")
            self.gcode = None
            self.save_btn.config(state=tk.DISABLED)
            self.crop_btn.config(state=tk.NORMAL)
            self.file_label.config(text=os.path.basename(path))
            self._place_redraw()
            try:
                img = Image.open(path)
                self.preview_images = {'original': img}
                self.current_view = 'original'
                self._update_view_buttons([('original', 'Original')])
                self._display_view()
            except Exception:
                pass
            self.status_label.config(text=f"Selected: {os.path.basename(path)}", foreground="#a6e3a1")

    def _get_effective_image_path(self):
        if self.crop_rect is None or self.original_image_path is None:
            return self.image_path
        cx, cy, cw, ch = self.crop_rect
        img = cv2.imread(self.original_image_path)
        if img is None:
            return self.image_path
        ih, iw = img.shape[:2]
        x1 = max(0, int(cx))
        y1 = max(0, int(cy))
        x2 = min(iw, int(cx + cw))
        y2 = min(ih, int(cy + ch))
        if x2 <= x1 or y2 <= y1:
            return self.image_path
        cropped = img[y1:y2, x1:x2]
        base, ext = os.path.splitext(self.original_image_path)
        crop_path = base + "_crop" + (ext if ext else ".png")
        cv2.imwrite(crop_path, cropped)
        self.image_path = crop_path
        return crop_path

    def _open_crop_dialog(self):
        src_path = self.original_image_path or self.image_path
        if not src_path:
            messagebox.showwarning("Warning", "Select an image first!")
            return
        try:
            pil_img = Image.open(src_path)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open image: {e}")
            return

        CropDialog(self.root, pil_img, self.crop_rect, self._on_crop_done)

    def _on_crop_done(self, rect):
        self.crop_rect = rect
        if rect is None:
            self.crop_info_label.config(text="")
            if self.original_image_path:
                self.image_path = self.original_image_path
            self.status_label.config(text="Crop reset — using full image.", foreground="#a6e3a1")
        else:
            cx, cy, cw, ch = rect
            self.crop_info_label.config(
                text=f" Cropped: {int(cw)}×{int(ch)} px at ({int(cx)}, {int(cy)})")
            self._get_effective_image_path()
            self.status_label.config(
                text=f" Cropped: {int(cw)}×{int(ch)} px", foreground="#a6e3a1")
        self.gcode = None
        self.save_btn.config(state=tk.DISABLED)
        self._img_aspect_cache.clear()
        self._place_redraw()
        try:
            img = Image.open(self.image_path)
            self.preview_images = {'original': img}
            self.current_view = 'original'
            self._update_view_buttons([('original', 'Original')])
            self._display_view()
        except Exception:
            pass

    def _apply(self):
        for attr, var in self.setting_vars.items():
            try:
                setattr(self.config, attr, float(var.get()))
            except ValueError:
                pass
        self.config.threshold = self.threshold_var.get()
        self.config.invert = self.invert_var.get()
        self.config.line_numbers = self.linenum_var.get()
        self.config.emit_comments = self.comments_var.get()
        self.config.use_g0 = self.useg0_var.get()
        self.config.simplify_epsilon = self.simplify_var.get()
        self.config.contour_centerline = self.ctr_center_var.get()
        try:
            self.config.raster_resolution = float(self.raster_res_var.get())
        except ValueError:
            pass
        try:
            self.config.raster_angle = float(self.raster_angle_var.get())
        except ValueError:
            pass
        try:
            self.config.raster_supersample = int(float(self.raster_super_var.get()))
        except ValueError:
            pass
        try:
            self.config.raster_smooth = int(float(self.raster_smooth_var.get()))
        except ValueError:
            pass
        label = self.raster_style_var.get()
        for key, txt in self.RASTER_STYLES.items():
            if txt == label:
                self.config.raster_style = key
                break
        self.config.raster_cross = self.raster_cross_var.get()
        self.config.raster_outline = self.raster_outline_var.get()
        try:
            self.config.canny_low = int(self.canny_low_var.get())
            self.config.canny_high = int(self.canny_high_var.get())
        except ValueError:
            pass
        self.config.uniform_stroke = self.uniform_var.get()
        self.config.adaptive_threshold = self.adaptive_var.get()
        self.config.despeckle = self.despeckle_var.get()
        try:
            self.config.line_min_length = float(self.line_minlen_var.get())
            self.config.line_simplify = float(self.line_simp_var.get())
        except ValueError:
            pass
        try:
            self.config.line_bridge_px = float(self.line_bridge_var.get())
        except ValueError:
            pass
        for attr, var_name, cast in [
                ("color_levels", "cl_levels_var", int),
                ("color_denoise", "cl_denoise_var", int),
                ("color_min_area", "cl_area_var", int)]:
            try:
                setattr(self.config, attr, cast(getattr(self, var_name).get()))
            except ValueError:
                pass
        for attr, var_name, cast in [
                ("portrait_sensitivity", "pt_thresh_var", float),
                ("portrait_detail", "pt_detail_var", float),
                ("portrait_denoise", "pt_denoise_var", float),
                ("portrait_min_area", "pt_area_var", int)]:
            try:
                setattr(self.config, attr, cast(getattr(self, var_name).get()))
            except ValueError:
                pass
        self.config.text_content = self.text_input.get("1.0", "end-1c")
        self.config.text_font = self.txt_font_var.get().strip()
        self.config.text_align = self.txt_align_var.get()
        self.config.text_style = self.txt_style_var.get()
        self.config.text_autofit = self.txt_autofit_var.get()
        for attr, var_name in [("text_height", "txt_size_var"),
                               ("text_line_spacing", "txt_spacing_var"),
                               ("text_margin", "txt_margin_var"),
                               ("text_render_scale", "txt_scale_var")]:
            try:
                setattr(self.config, attr, float(getattr(self, var_name).get()))
            except ValueError:
                pass
        self.config.use_arcs = self.arcs_var.get()
        try:
            self.config.arc_tolerance = float(self.arc_tol_var.get())
            self.config.arc_min_points = int(self.arc_minpts_var.get())
        except ValueError:
            pass
        self.config.place_mode = 'manual' if self.place_manual_var.get() else 'fit'
        self.config.place_keep_ratio = self.place_ratio_var.get()
        self._place_from_entries()
        if self.crop_rect is not None:
            self._get_effective_image_path()

    def _preview(self):
        m = self.current_method
        if m != 'text' and not self.image_path:
            messagebox.showwarning("Warning", "Select an image first!")
            return
        self._apply()
        self.status_label.config(text="Processing...", foreground="#f9e2af")
        self.root.update()

        try:
            if m == 'color':
                data, imgs_cv, w, h, info = process_color(self.image_path, self.config)
                views = [('original','Original'), ('preview','Strokes'),
                         ('quant','Quantized'), ('overlay','Overlay')]
            elif m == 'portrait':
                data, imgs_cv, w, h, info = process_portrait(self.image_path, self.config)
                views = [('original','Original'), ('preview','Portrait Strokes'),
                         ('ink','XDoG'), ('stroke','Skeleton'),
                         ('overlay','Overlay')]
            elif m == 'line':
                data, imgs_cv, w, h, info = process_line(self.image_path, self.config)
                views = [('original','Original'), ('preview','Strokes'),
                         ('stroke','Binary/Skeleton'), ('overlay','Overlay')]
            elif m == 'contour':
                data, imgs_cv, w, h, info = process_contour(self.image_path, self.config)
                views = [('original','Original'), ('preview','Contour'), ('overlay','Overlay')]
                if 'stroke' in imgs_cv:
                    views.append(('stroke', '1px Centerline'))
            elif m == 'raster':
                data, imgs_cv, w, h, info = process_raster(self.image_path, self.config)
                views = [('original','Original'), ('preview','Infill'),
                         ('raster','Simulation'), ('binary','Binary'),
                         ('overlay','Overlay')]
            elif m == 'edge':
                data, imgs_cv, w, h, info = process_edge(self.image_path, self.config)
                views = [('original','Original'), ('preview','Edges'),
                         ('overlay','Overlay'), ('canny_raw','Canny Raw')]
            elif m == 'text':
                data, imgs_cv, w, h, info = process_text(self.config)
                views = [('original','Text'), ('preview','Toolpaths'),
                         ('stroke','Skeleton/Binary'), ('overlay','Overlay')]

            self.processed_data = data
            self.preview_images = {}
            for key, cv_img in imgs_cv.items():
                if len(cv_img.shape) == 2:
                    rgb = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2RGB)
                else:
                    rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                self.preview_images[key] = Image.fromarray(rgb)

            self._update_view_buttons(views)
            self.current_view = 'preview'
            self._display_view()

            self.status_label.config(text=f" {info}", foreground="#a6e3a1")
            self.info_text.delete("1.0", tk.END)
            self.info_text.insert(tk.END, f"Method: {self.METHODS[m]}\n")
            self.info_text.insert(tk.END, f"Image: {w} x {h} px\n")
            self.info_text.insert(tk.END, f"{info}\n")
            self.info_text.insert(tk.END, f"\nUse view buttons above to inspect different layers.\n")

        except Exception as e:
            self.status_label.config(text=f" {e}", foreground="#f38ba8")
            messagebox.showerror("Error", str(e))

    def _generate(self):
        m = self.current_method
        if m != 'text' and not self.image_path:
            messagebox.showwarning("Warning", "Select an image first!")
            return
        self._apply()
        self.status_label.config(text="Generating G-Code...", foreground="#f9e2af")
        self.root.update()

        try:
            if m == 'color':
                data, imgs_cv, w, h, info = process_color(self.image_path, self.config)
                self.gcode, stats = generate_gcode_color(data, w, h, self.config)
                stat_text = (f"Strokes: {stats['lines_count']}\n"
                             f"G2/G3 arcs: {stats['arcs']} | G1 linear: {stats['segments']}\n"
                             f"Draw distance: {stats['draw_dist']:.1f}mm\n"
                             f"Rapid travel: {stats['travel_dist']:.1f}mm\n"
                             f"Est. time: ~{stats['est_time']:.1f} min")
                views = [('original','Original'), ('preview','Strokes'),
                         ('quant','Quantized'), ('overlay','Overlay')]

            elif m == 'portrait':
                data, imgs_cv, w, h, info = process_portrait(self.image_path, self.config)
                self.gcode, stats = generate_gcode_portrait(data, w, h, self.config)
                stat_text = (f"Strokes: {stats['lines_count']}\n"
                             f"G2/G3 arcs: {stats['arcs']} | G1 linear: {stats['segments']}\n"
                             f"Draw distance: {stats['draw_dist']:.1f}mm\n"
                             f"Rapid travel: {stats['travel_dist']:.1f}mm\n"
                             f"Est. time: ~{stats['est_time']:.1f} min")
                views = [('original','Original'), ('preview','Portrait Strokes'),
                         ('ink','XDoG'), ('stroke','Skeleton'),
                         ('overlay','Overlay')]

            elif m == 'line':
                data, imgs_cv, w, h, info = process_line(self.image_path, self.config)
                self.gcode, stats = generate_gcode_line(data, w, h, self.config)
                stat_text = (f"Strokes: {stats['lines_count']}\n"
                             f"G2/G3 arcs: {stats['arcs']} | G1 linear: {stats['segments']}\n"
                             f"Draw distance: {stats['draw_dist']:.1f}mm\n"
                             f"Rapid travel: {stats['travel_dist']:.1f}mm\n"
                             f"Est. time: ~{stats['est_time']:.1f} min")
                views = [('original','Original'), ('preview','Strokes'),
                         ('stroke','Binary/Skeleton'), ('overlay','Overlay')]

            elif m == 'contour':
                data, imgs_cv, w, h, info = process_contour(self.image_path, self.config)
                self.gcode, stats = generate_gcode_contour(data, w, h, self.config)
                stat_text = (f"Contours: {stats['contours']}\n"
                             f"Draw distance: {stats['draw_dist']:.1f}mm\n"
                             f"Rapid travel: {stats['travel_dist']:.1f}mm\n"
                             f"Est. time: ~{stats['est_time']:.1f} min")
                views = [('original','Original'), ('preview','Contour'), ('overlay','Overlay')]
                if 'stroke' in imgs_cv:
                    views.append(('stroke', '1px Centerline'))

            elif m == 'raster':
                data, imgs_cv, w, h, info = process_raster(self.image_path, self.config)
                self.gcode, stats = generate_gcode_raster(data, w, h, self.config)
                stat_text = (f"Strokes: {stats['strokes']} (= pen hops)\n"
                             f"Points: {stats['points']}\n"
                             f"Draw distance: {stats['draw_dist']:.1f}mm\n"
                             f"Rapid travel: {stats['travel_dist']:.1f}mm\n"
                             f"Est. time: ~{stats['est_time']:.1f} min")
                views = [('original','Original'), ('preview','Infill'),
                         ('raster','Simulation'), ('binary','Binary'),
                         ('overlay','Overlay')]

            elif m == 'edge':
                data, imgs_cv, w, h, info = process_edge(self.image_path, self.config)
                self.gcode, stats = generate_gcode_edge(data, w, h, self.config)
                stat_text = (f"Strokes: {stats['edges']}\n"
                             f"Draw distance: {stats['draw_dist']:.1f}mm\n"
                             f"Rapid travel: {stats['travel_dist']:.1f}mm\n"
                             f"Est. time: ~{stats['est_time']:.1f} min")
                views = [('original','Original'), ('preview','Edges'),
                         ('overlay','Overlay'), ('canny_raw','Canny Raw')]

            elif m == 'text':
                data, imgs_cv, w, h, info = process_text(self.config)
                self.gcode, stats = generate_gcode_text(data, w, h, self.config)
                stat_text = (f"Strokes: {stats['lines_count']}\n"
                             f"G2/G3 arcs: {stats['arcs']} | G1 linear: {stats['segments']}\n"
                             f"Draw distance: {stats['draw_dist']:.1f}mm\n"
                             f"Rapid travel: {stats['travel_dist']:.1f}mm\n"
                             f"Est. time: ~{stats['est_time']:.1f} min")
                views = [('original','Text'), ('preview','Toolpaths'),
                         ('stroke','Skeleton/Binary'), ('overlay','Overlay')]

            self.preview_images = {}
            for key, cv_img in imgs_cv.items():
                if len(cv_img.shape) == 2:
                    rgb = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2RGB)
                else:
                    rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                self.preview_images[key] = Image.fromarray(rgb)

            self._update_view_buttons(views)
            self.current_view = 'preview'
            self._display_view()

            num_lines = self.gcode.count("\n") + 1
            self.save_btn.config(state=tk.NORMAL)
            self.status_label.config(
                text=f" G-Code generated: {num_lines} lines | ~{stats['est_time']:.1f} min"
                     " — click '3. Save .gcode File'",
                foreground="#a6e3a1"
            )

            self.info_text.delete("1.0", tk.END)
            self.info_text.insert(tk.END, f"Method: {self.METHODS[m]}\n")
            self.info_text.insert(tk.END, f"Image: {w} x {h} px\n")
            self.info_text.insert(tk.END, f"G-Code: {num_lines} lines\n\n")
            self.info_text.insert(tk.END, stat_text + "\n")
            self.info_text.insert(tk.END, "\n--- G-Code Preview ---\n")
            self.info_text.insert(tk.END, "\n".join(self.gcode.split("\n")[:12]))

        except Exception as e:
            self.status_label.config(text=f" {e}", foreground="#f38ba8")
            messagebox.showerror("Error", str(e))

    def _save(self):
        if not self.gcode:
            messagebox.showwarning("Warning", "Generate G-Code first!")
            return
        default = os.path.splitext(os.path.basename(self.image_path))[0] + ".gcode" if self.image_path else "output.gcode"
        path = filedialog.asksaveasfilename(
            title="Save G-Code File", defaultextension=".gcode", initialfile=default,
            filetypes=[("G-Code files", "*.gcode *.nc *.ngc"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.gcode)
            self.status_label.config(text=f"Saved: {os.path.basename(path)}", foreground="#a6e3a1")
            messagebox.showinfo("Success", f"Saved:\n{path}")


# ============================================================
# CLI ENTRY POINT
# ============================================================
def run_cli(image_path, method='line', output_path=None, no_arcs=False,
            no_uniform=False, contour_outline=False, text=None):
    config = MachineConfig()
    if no_arcs:
        config.use_arcs = False
    if no_uniform:
        config.uniform_stroke = False
    if contour_outline:
        config.contour_centerline = False

    if method == 'text':
        if text:
            config.text_content = text.replace("\\n", "\n")
        print(f"Text: {config.text_content!r} | Font: {config.text_font} | "
              f"Size: {config.text_height}mm")
        data, _, w, h, info = process_text(config)
        gcode, stats = generate_gcode_text(data, w, h, config)
        print(f"{info}")
        if output_path is None:
            output_path = "text.gcode"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(gcode)
        print(f"Saved: {output_path} ({gcode.count(chr(10)) + 1} lines)")
        print(f"Est. time: ~{stats['est_time']:.1f} min")
        return

    print(f"Image: {image_path} | Method: {method} | "
          f"G2/G3 arcs: {'yes' if config.use_arcs else 'no'}")

    if method == 'color':
        data, _, w, h, info = process_color(image_path, config)
        gcode, stats = generate_gcode_color(data, w, h, config)
    elif method == 'portrait':
        data, _, w, h, info = process_portrait(image_path, config)
        gcode, stats = generate_gcode_portrait(data, w, h, config)
    elif method == 'line':
        data, _, w, h, info = process_line(image_path, config)
        gcode, stats = generate_gcode_line(data, w, h, config)
    elif method == 'contour':
        data, _, w, h, info = process_contour(image_path, config)
        gcode, stats = generate_gcode_contour(data, w, h, config)
    elif method == 'raster':
        data, _, w, h, info = process_raster(image_path, config)
        gcode, stats = generate_gcode_raster(data, w, h, config)
    elif method == 'edge':
        data, _, w, h, info = process_edge(image_path, config)
        gcode, stats = generate_gcode_edge(data, w, h, config)
    else:
        print(f"Invalid method: {method}")
        return

    print(f"{info}")
    if output_path is None:
        output_path = os.path.splitext(image_path)[0] + f"_{method}.gcode"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(gcode)
    num = gcode.count("\n") + 1
    print(f"Saved: {output_path} ({num} lines)")
    print(f"Est. time: ~{stats['est_time']:.1f} min")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        flags = {a for a in sys.argv[1:] if a.startswith("--")}
        method = args[1] if len(args) > 1 else 'line'
        out = args[2] if len(args) > 2 else None
        run_cli(None if method == 'text' else args[0], method, out,
                no_arcs="--no-arcs" in flags,
                no_uniform="--no-uniform" in flags,
                contour_outline="--contour-outline" in flags,
                text=args[0] if method == 'text' else None)
    else:
        root = tk.Tk()
        app = ImageToGCodeApp(root)
        root.mainloop()
