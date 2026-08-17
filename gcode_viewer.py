"""
G-Code Viewer — Open .gcode files and preview CNC / plotter toolpaths.

Reconstructs drawing paths from standard CNC G-Code instructions:
  - G90/G91 (Absolute / Incremental positioning)
  - G0/G1 (Rapid travel / Linear interpolation)
  - G2/G3 (Clockwise / Counter-clockwise circular arcs with I/J or R parameters)
  - Line numbers N10..., comments ';' and '(...)', modal F feed rates, skipped M-codes.

Distinguishes Pen-Down (drawing) vs Pen-Up (rapid travel) via Z-axis height:
  Z <= threshold = DRAWING, Z > threshold = RAPID TRAVEL.
Threshold is auto-calculated as the midpoint between min and max Z in the file.

Usage:
    python gcode_viewer.py                    # Open GUI and click "Open File"
    python gcode_viewer.py output.gcode
    python gcode_viewer.py output.gcode --stats   # Print statistics only, no GUI

Controls:
    Mouse: Scroll = Zoom at cursor · Drag = Pan · Double-click = Fit to View.
    Keys:  Space = Play/Pause · F = Fit to View · R = Replay from start.
"""

import colorsys
import math
import os
import re
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# ============================================================
# G-CODE PARSER
# ============================================================
WORD_RE = re.compile(r'([A-Za-z])\s*([-+]?\d*\.?\d+)')
NUM_RE = re.compile(r'^\s*[Nn]\d+')
PAREN_RE = re.compile(r'\([^)]*\)')

# Maximum chord error when interpolating circular arcs to linear segments (mm)
ARC_TOLERANCE = 0.02
ARC_MAX_SEGMENTS = 720


class Move:
    """A linear segment of the toolpath after arc interpolation."""
    __slots__ = ('x0', 'y0', 'x1', 'y1', 'z', 'rapid', 'feed', 'line', 'draw')

    def __init__(self, x0, y0, x1, y1, z, rapid, feed, line):
        self.x0, self.y0 = x0, y0
        self.x1, self.y1 = x1, y1
        self.z = z
        self.rapid = rapid
        self.feed = feed
        self.line = line
        self.draw = False

    @property
    def length(self):
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


def arc_points(x0, y0, x1, y1, cx, cy, clockwise):
    """Interpolates circular arc into discrete point sequence."""
    r = math.hypot(x0 - cx, y0 - cy)
    if r < 1e-9:
        return [(x1, y1)]

    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    sweep = a1 - a0
    if clockwise:
        while sweep >= -1e-9:
            sweep -= 2 * math.pi
    else:
        while sweep <= 1e-9:
            sweep += 2 * math.pi

    if r > ARC_TOLERANCE:
        step_max = 2 * math.acos(max(-1.0, 1.0 - ARC_TOLERANCE / r))
    else:
        step_max = math.pi / 4
    n = max(2, int(math.ceil(abs(sweep) / max(step_max, 1e-6))))
    n = min(n, ARC_MAX_SEGMENTS)

    pts = []
    for k in range(1, n + 1):
        a = a0 + sweep * k / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts[-1] = (x1, y1)
    return pts


def parse_gcode(text):
    """Parses G-code text into moves and metadata."""
    x = y = z = 0.0
    feed = 0.0
    absolute = True
    mode = None
    moves = []
    z_values = set()
    n_arcs = 0
    bad_lines = []

    for lineno, raw in enumerate(text.splitlines(), 1):
        s = raw.split(';', 1)[0]
        s = PAREN_RE.sub(' ', s)
        s = NUM_RE.sub(' ', s)
        if not s.strip():
            continue

        params = {}
        gcodes = []
        for letter, val in WORD_RE.findall(s):
            L = letter.upper()
            if L == 'G':
                gcodes.append(int(round(float(val))))
            elif L == 'M':
                pass
            else:
                params[L] = float(val)

        for g in gcodes:
            if g == 90:
                absolute = True
            elif g == 91:
                absolute = False
            elif g in (0, 1, 2, 3):
                mode = g

        if 'F' in params:
            feed = params['F']

        if not any(k in params for k in ('X', 'Y', 'Z')):
            continue
        if mode is None:
            bad_lines.append(lineno)
            continue

        def target(letter, cur):
            if letter not in params:
                return cur
            return params[letter] if absolute else cur + params[letter]

        nx, ny, nz = target('X', x), target('Y', y), target('Z', z)
        rapid = (mode == 0)

        if mode in (0, 1):
            moves.append(Move(x, y, nx, ny, nz, rapid, feed, lineno))
        else:
            if 'I' in params or 'J' in params:
                cx = x + params.get('I', 0.0)
                cy = y + params.get('J', 0.0)
            elif 'R' in params:
                cx, cy = _center_from_radius(x, y, nx, ny, params['R'], mode == 2)
                if cx is None:
                    bad_lines.append(lineno)
                    moves.append(Move(x, y, nx, ny, nz, rapid, feed, lineno))
                    x, y, z = nx, ny, nz
                    continue
            else:
                bad_lines.append(lineno)
                moves.append(Move(x, y, nx, ny, nz, rapid, feed, lineno))
                x, y, z = nx, ny, nz
                continue

            n_arcs += 1
            px, py = x, y
            pts = arc_points(x, y, nx, ny, cx, cy, clockwise=(mode == 2))
            for k, (ax, ay) in enumerate(pts, 1):
                az = z + (nz - z) * k / len(pts)
                moves.append(Move(px, py, ax, ay, az, rapid, feed, lineno))
                px, py = ax, ay

        if nz != z:
            z_values.add(round(nz, 4))
        x, y, z = nx, ny, nz

    z_values.add(0.0)
    meta = {
        'z_values': sorted(z_values),
        'n_arcs': n_arcs,
        'bad_lines': bad_lines,
    }
    return moves, meta


def _center_from_radius(x0, y0, x1, y1, r, clockwise):
    """Calculates arc center when radius R is specified."""
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy)
    if d < 1e-9 or abs(r) < d / 2 - 1e-6:
        return None, None
    h = math.sqrt(max(0.0, r * r - (d / 2) ** 2))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    ux, uy = -dy / d, dx / d
    sign = 1.0 if (clockwise == (r < 0)) else -1.0
    return mx + sign * h * ux, my + sign * h * uy


def auto_pen_threshold(z_values):
    """Estimates pen-down threshold from distinct Z values."""
    if not z_values:
        return 0.0
    lo, hi = min(z_values), max(z_values)
    if hi - lo < 1e-6:
        return hi
    return (lo + hi) / 2.0


def apply_pen_threshold(moves, threshold):
    """Assigns draw flag: pen down (Z <= threshold) and not rapid motion (G0)."""
    for m in moves:
        m.draw = (m.z <= threshold + 1e-9) and not m.rapid


def build_strokes(moves):
    """Groups consecutive motion segments with identical pen state into strokes."""
    strokes = []
    cur = None
    seg_moves = []
    for m in moves:
        if m.length < 1e-9:
            continue
        if cur is None or cur['draw'] != m.draw:
            cur = {'pts': [(m.x0, m.y0)], 'draw': m.draw, 'item': None, 'off': 0}
            strokes.append(cur)
        cur['pts'].append((m.x1, m.y1))
        seg_moves.append(m)

    off = 0
    for st in strokes:
        st['nseg'] = len(st['pts']) - 1
        st['off'] = off
        off += st['nseg']
    return strokes, off, seg_moves


def compute_stats(moves, strokes, total_seg):
    draw_d = travel_d = z_d = 0.0
    minutes = 0.0
    xs, ys = [], []
    dxs, dys = [], []
    for m in moves:
        d = m.length
        if m.draw:
            draw_d += d
            dxs.extend((m.x0, m.x1))
            dys.extend((m.y0, m.y1))
        else:
            travel_d += d
        if m.feed > 0:
            minutes += d / m.feed
        xs.extend((m.x0, m.x1))
        ys.extend((m.y0, m.y1))
    if not dxs:
        dxs, dys = xs, ys

    prev_z = 0.0
    for m in moves:
        z_d += abs(m.z - prev_z)
        prev_z = m.z

    n_draw = sum(1 for s in strokes if s['draw'])
    return {
        'n_moves': len(moves),
        'n_strokes': n_draw,
        'n_travel': len(strokes) - n_draw,
        'total_seg': total_seg,
        'draw_dist': draw_d,
        'travel_dist': travel_d,
        'z_dist': z_d,
        'minutes': minutes,
        'xmin': min(xs) if xs else 0.0, 'xmax': max(xs) if xs else 0.0,
        'ymin': min(ys) if ys else 0.0, 'ymax': max(ys) if ys else 0.0,
        'dxmin': min(dxs) if dxs else 0.0, 'dxmax': max(dxs) if dxs else 0.0,
        'dymin': min(dys) if dys else 0.0, 'dymax': max(dys) if dys else 0.0,
    }


# ============================================================
# GUI INTERFACE
# ============================================================
UI_SCALE = 0.78

BASE_W, BASE_H = 1200, 820
MIN_W, MIN_H = 880, 560
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


BG = "#1e1e2e"
CANVAS_BG = "#11111b"
GRID = "#282839"
GRID_MAJOR = "#3c3c55"
AREA = "#585b70"
TEXT = "#cdd6f4"
BLUE = "#89b4fa"
GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
RED = "#f38ba8"
MAUVE = "#cba6f7"
TRAVEL = "#45475a"


def order_color(t):
    """Generates color gradient by draw order: Blue -> Green -> Yellow -> Red."""
    r, g, b = colorsys.hsv_to_rgb(0.62 * (1.0 - t), 0.62, 1.0)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


class GCodeViewer:

    def __init__(self, root, path=None):
        self.root = root
        self.root.title("G-Code Viewer — Toolpath Visualizer")
        fit_ui_scale(self.root)
        win_w, win_h = place_window(self.root, ui_px(BASE_W), ui_px(BASE_H))
        self.root.minsize(min(ui_px(MIN_W), win_w), min(ui_px(MIN_H), win_h))
        self.root.configure(bg=BG)

        self.path = None
        self.moves = []
        self.meta = {}
        self.strokes = []
        self.total_seg = 0
        self.seg_moves = []
        self.stats = None

        self.scale = 3.0
        self.tx = 40.0
        self.ty = 40.0
        self._drag = None

        self.playing = False
        self._after_id = None
        self._last_tick_time = None
        self._residual_mm = 0.0
        self.pen_marker = None

        self._build_ui()
        if path:
            self.load(path)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT,
                        font=("Segoe UI", ui_font(10)))
        style.configure("Header.TLabel", background=BG, foreground=BLUE,
                        font=("Segoe UI", ui_font(13), "bold"))
        style.configure("TButton", font=("Segoe UI", ui_font(10)))
        style.configure("Accent.TButton", font=("Segoe UI", ui_font(11), "bold"),
                        foreground=BG, background=BLUE)
        style.map("Accent.TButton", background=[("active", MAUVE)])
        style.configure("TLabelframe", background=BG, foreground=BLUE,
                        font=("Segoe UI", ui_font(10), "bold"))
        style.configure("TLabelframe.Label", background=BG, foreground=BLUE)
        style.configure("TCheckbutton", background=BG, foreground=TEXT,
                        font=("Segoe UI", ui_font(10)))
        style.configure("TScale", background=BG)

        main = ttk.Frame(self.root, padding=ui_px(8))
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main, width=ui_px(320))
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, ui_px(8)))
        left.pack_propagate(False)

        ttk.Label(left, text="G-Code Viewer", style="Header.TLabel").pack(anchor="w")
        ttk.Label(left, text="Open a .gcode file to preview toolpaths",
                  wraplength=ui_px(300)).pack(anchor="w", pady=(0, ui_px(6)))

        ttk.Button(left, text="Open .gcode File", style="Accent.TButton",
                   command=self._open).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Reload File",
                   command=self._reload).pack(fill=tk.X, pady=2)

        self.file_label = ttk.Label(left, text="(no file loaded)", foreground=YELLOW,
                                    wraplength=ui_px(300))
        self.file_label.pack(anchor="w", pady=(ui_px(4), ui_px(6)))

        # Information frame
        inf = ttk.LabelFrame(left, text="Information", padding=ui_px(6))
        inf.pack(fill=tk.X, pady=ui_px(4))
        self.info = tk.Text(inf, height=13, bg="#181825", fg=TEXT, bd=0,
                            font=("Consolas", ui_font(9)), wrap=tk.WORD,
                            highlightthickness=0)
        self.info.pack(fill=tk.X)
        self.info.insert("1.0", "No file loaded.")
        self.info.config(state=tk.DISABLED)

        # Display options frame
        disp = ttk.LabelFrame(left, text="Display", padding=ui_px(6))
        disp.pack(fill=tk.X, pady=ui_px(4))

        self.v_travel = tk.BooleanVar(value=True)
        self.v_order = tk.BooleanVar(value=True)
        self.v_starts = tk.BooleanVar(value=False)
        self.v_grid = tk.BooleanVar(value=True)
        self.v_area = tk.BooleanVar(value=True)
        for txt, var in (("Rapid moves (pen up)", self.v_travel),
                         ("Color by draw order", self.v_order),
                         ("Start point markers", self.v_starts),
                         ("10 mm grid", self.v_grid),
                         ("Work area boundary", self.v_area)):
            ttk.Checkbutton(disp, text=txt, variable=var,
                            command=self._rebuild).pack(anchor="w")

        row = ttk.Frame(disp)
        row.pack(fill=tk.X, pady=(ui_px(4), 0))
        ttk.Label(row, text="Work area (mm):").pack(side=tk.LEFT)
        self.e_area_w = self._entry(row, "150", 5)
        ttk.Label(row, text="×").pack(side=tk.LEFT)
        self.e_area_h = self._entry(row, "150", 5)

        row = ttk.Frame(disp)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Z threshold (pen down ≤):").pack(side=tk.LEFT)
        self.e_thr = self._entry(row, "-5", 6)
        ttk.Button(row, text="Apply", width=8,
                   command=self._reapply_threshold).pack(side=tk.LEFT, padx=2)

        # Toolpath replay frame
        play = ttk.LabelFrame(left, text="Replay Toolpath", padding=ui_px(6))
        play.pack(fill=tk.X, pady=ui_px(4))

        self.progress = tk.IntVar(value=0)
        self.slider = ttk.Scale(play, from_=0, to=1, orient=tk.HORIZONTAL,
                                command=self._on_slider)
        self.slider.pack(fill=tk.X)

        row = ttk.Frame(play)
        row.pack(fill=tk.X, pady=ui_px(4))
        self.play_btn = ttk.Button(row, text="Play", command=self._toggle_play)
        self.play_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(row, text="|<", width=4, command=self._restart).pack(side=tk.LEFT, padx=1)
        ttk.Button(row, text=">|", width=4, command=self._to_end).pack(side=tk.LEFT, padx=1)

        row = ttk.Frame(play)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Speed:").pack(side=tk.LEFT)
        self.speed = tk.DoubleVar(value=1.0)
        ttk.Scale(row, from_=1, to=50, orient=tk.HORIZONTAL,
                  variable=self.speed).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.speed_label = ttk.Label(row, text="1×", width=4)
        self.speed_label.pack(side=tk.LEFT, padx=2)

        ttk.Button(left, text="Fit to View (F)",
                   command=self._fit).pack(fill=tk.X, pady=ui_px(4))

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(right, bg=CANVAS_BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.status = ttk.Label(right, text="Scroll = Zoom · Drag = Pan · Double-click = Fit to View",
                                foreground=GREEN)
        self.status.pack(anchor="w", pady=(ui_px(4), 0))

        self.canvas.bind("<Configure>", lambda e: self._rebuild())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.canvas.bind("<Double-Button-1>", lambda e: self._fit())
        self.canvas.bind("<Motion>", self._on_move)

        self.root.bind("<space>", lambda e: self._toggle_play())
        self.root.bind("f", lambda e: self._fit())
        self.root.bind("r", lambda e: self._restart())

    def _entry(self, parent, default, width):
        e = ttk.Entry(parent, width=width, font=("Segoe UI", ui_font(9)))
        e.insert(0, default)
        e.pack(side=tk.LEFT, padx=2)
        return e

    def _open(self):
        path = filedialog.askopenfilename(
            title="Select G-Code File",
            initialdir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "gcode"),
            filetypes=[("G-Code files", "*.gcode *.nc *.ngc *.tap"),
                       ("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self.load(path)

    def _reload(self):
        if self.path:
            self.load(self.path)

    def load(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            messagebox.showerror("Error", f"Could not read file:\n{e}")
            return

        self._stop()
        self.path = path
        self.moves, self.meta = parse_gcode(text)
        if not self.moves:
            messagebox.showwarning("Empty",
                                   "No motion commands found in file.")
            return

        thr = auto_pen_threshold(self.meta['z_values'])
        self.e_thr.delete(0, tk.END)
        self.e_thr.insert(0, f"{thr:g}")
        self._apply(thr)

        self.file_label.config(text=os.path.basename(path))
        self._fit()

    def _reapply_threshold(self):
        try:
            thr = float(self.e_thr.get())
        except ValueError:
            messagebox.showerror("Error", "Z threshold must be a valid number.")
            return
        if self.moves:
            self._apply(thr)
            self._rebuild()

    def _apply(self, threshold):
        apply_pen_threshold(self.moves, threshold)
        self.strokes, self.total_seg, self.seg_moves = build_strokes(self.moves)
        self.stats = compute_stats(self.moves, self.strokes, self.total_seg)
        self.slider.config(to=max(1, self.total_seg))
        self.progress.set(self.total_seg)
        self.slider.set(self.total_seg)
        self._show_info(threshold)

    def _show_info(self, threshold):
        s = self.stats
        zs = ", ".join(f"{z:g}" for z in self.meta['z_values'][:8])
        w = s['dxmax'] - s['dxmin']
        h = s['dymax'] - s['dymin']
        txt = (
            f"Linear moves : {s['n_moves']}\n"
            f"Draw strokes : {s['n_strokes']}\n"
            f"Pen hops (G0): {s['n_travel']}\n"
            f"Arcs G2/G3   : {self.meta['n_arcs']}\n"
            f"\n"
            f"Drawing size : {w:.1f} × {h:.1f} mm\n"
            f"X (draw)     : {s['dxmin']:.1f} … {s['dxmax']:.1f}\n"
            f"Y (draw)     : {s['dymin']:.1f} … {s['dymax']:.1f}\n"
            f"Total travel : X {s['xmin']:.1f}…{s['xmax']:.1f}"
            f"  Y {s['ymin']:.1f}…{s['ymax']:.1f}\n"
            f"Z levels     : {zs}\n"
            f"Pen-down thr : Z ≤ {threshold:g}\n"
            f"\n"
            f"Draw distance: {s['draw_dist']:.1f} mm\n"
            f"Rapid travel : {s['travel_dist']:.1f} mm\n"
            f"Z travel     : {s['z_dist']:.1f} mm\n"
            f"Est. time    : {s['minutes']:.1f} min"
        )
        if self.meta['bad_lines']:
            n = len(self.meta['bad_lines'])
            first = ", ".join(str(x) for x in self.meta['bad_lines'][:5])
            txt += f"\n\n[!] {n} unparsed lines (lines {first}…)"

        self.info.config(state=tk.NORMAL)
        self.info.delete("1.0", tk.END)
        self.info.insert("1.0", txt)
        self.info.config(state=tk.DISABLED)

    def _to_screen(self, x, y):
        return x * self.scale + self.tx, -y * self.scale + self.ty

    def _to_mm(self, sx, sy):
        return (sx - self.tx) / self.scale, -(sy - self.ty) / self.scale

    def _fit(self):
        if not self.stats:
            return
        cw = max(self.canvas.winfo_width(), 50)
        ch = max(self.canvas.winfo_height(), 50)
        pad = ui_px(30)

        try:
            aw, ah = float(self.e_area_w.get()), float(self.e_area_h.get())
        except ValueError:
            aw = ah = 0.0
        s = self.stats
        xmin, xmax = min(s['xmin'], 0.0), max(s['xmax'], aw if self.v_area.get() else 0.0)
        ymin, ymax = min(s['ymin'], 0.0), max(s['ymax'], ah if self.v_area.get() else 0.0)
        w = max(xmax - xmin, 1e-6)
        h = max(ymax - ymin, 1e-6)

        avail_w = max(cw - 2 * pad, ui_px(20))
        avail_h = max(ch - 2 * pad, ui_px(20))
        self.scale = max(min(avail_w / w, avail_h / h), 1e-3)
        self.tx = pad - xmin * self.scale
        self.ty = ch - pad + ymin * self.scale
        self._rebuild()

    def _rebuild(self):
        self.canvas.delete("all")
        for st in self.strokes:
            st['item'] = None
        self._draw_background()
        self._draw_strokes()
        self._apply_progress()

    def _draw_background(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        try:
            aw, ah = float(self.e_area_w.get()), float(self.e_area_h.get())
        except ValueError:
            aw = ah = 150.0

        if self.v_grid.get():
            x0, y0 = self._to_mm(0, ch)
            x1, y1 = self._to_mm(cw, 0)
            step = 10.0
            while (step * self.scale) < ui_px(8):
                step *= 5
            gx = math.floor(x0 / step) * step
            while gx <= x1:
                sx, _ = self._to_screen(gx, 0)
                self.canvas.create_line(sx, 0, sx, ch,
                                        fill=GRID_MAJOR if abs(gx) < 1e-9 else GRID)
                gx += step
            gy = math.floor(y0 / step) * step
            while gy <= y1:
                _, sy = self._to_screen(0, gy)
                self.canvas.create_line(0, sy, cw, sy,
                                        fill=GRID_MAJOR if abs(gy) < 1e-9 else GRID)
                gy += step

        if self.v_area.get() and aw > 0 and ah > 0:
            ax0, ay0 = self._to_screen(0, 0)
            ax1, ay1 = self._to_screen(aw, ah)
            self.canvas.create_rectangle(ax0, ay0, ax1, ay1, outline=AREA, dash=(4, 3))
            self.canvas.create_text(ax0 + 4, ay0 - 4, anchor="sw",
                                    text=f"{aw:g} × {ah:g} mm", fill=AREA,
                                    font=("Segoe UI", ui_font(8)))

        # Origin point (0, 0)
        ox, oy = self._to_screen(0, 0)
        self.canvas.create_line(ox - 7, oy, ox + 7, oy, fill=RED)
        self.canvas.create_line(ox, oy - 7, ox, oy + 7, fill=RED)

    def _draw_strokes(self):
        n_draw = max(1, sum(1 for s in self.strokes if s['draw']))
        idx = 0
        show_travel = self.v_travel.get()
        use_order = self.v_order.get()

        for st in self.strokes:
            if not st['draw']:
                if not show_travel:
                    continue
                color, width, dash = TRAVEL, 1, (3, 3)
            else:
                color = order_color(idx / n_draw) if use_order else GREEN
                width, dash = 2, None
                idx += 1

            flat = []
            for x, y in st['pts']:
                sx, sy = self._to_screen(x, y)
                flat.extend((sx, sy))
            kw = {'fill': color, 'width': width, 'capstyle': tk.ROUND,
                  'joinstyle': tk.ROUND}
            if dash:
                kw['dash'] = dash
            st['item'] = self.canvas.create_line(*flat, **kw)

        if self.v_starts.get():
            for st in self.strokes:
                if st['draw']:
                    sx, sy = self._to_screen(*st['pts'][0])
                    self.canvas.create_oval(sx - 2, sy - 2, sx + 2, sy + 2,
                                            outline=YELLOW)

        self.pen_marker = self.canvas.create_oval(0, 0, 0, 0, outline=RED,
                                                  width=2, state="hidden")

    def _apply_progress(self):
        """Displays toolpath up to current slider progress."""
        p = self.progress.get()
        pen_xy = None
        for st in self.strokes:
            item = st['item']
            if item is None:
                continue
            vis = p - st['off']
            if vis <= 0:
                self.canvas.itemconfigure(item, state="hidden")
                continue
            if vis >= st['nseg']:
                pts = st['pts']
            else:
                pts = st['pts'][:vis + 1]
                pen_xy = pts[-1]
            flat = []
            for x, y in pts:
                sx, sy = self._to_screen(x, y)
                flat.extend((sx, sy))
            self.canvas.coords(item, *flat)
            self.canvas.itemconfigure(item, state="normal")
            if pen_xy is None and vis >= st['nseg'] and p <= st['off'] + st['nseg']:
                pen_xy = st['pts'][-1]

        if self.pen_marker is None:
            return
        if pen_xy and p < self.total_seg:
            sx, sy = self._to_screen(*pen_xy)
            self.canvas.coords(self.pen_marker, sx - 5, sy - 5, sx + 5, sy + 5)
            self.canvas.itemconfigure(self.pen_marker, state="normal")
            self.canvas.tag_raise(self.pen_marker)
        else:
            self.canvas.itemconfigure(self.pen_marker, state="hidden")

    def _on_slider(self, _val):
        if not self.strokes:
            return
        self.progress.set(int(float(self.slider.get())))
        self._apply_progress()

    def _toggle_play(self):
        if not self.strokes:
            return
        if self.playing:
            self._stop()
        else:
            if self.progress.get() >= self.total_seg:
                self.progress.set(0)
                self.slider.set(0)
            self.playing = True
            self._last_tick_time = None
            self._residual_mm = 0.0
            self.play_btn.config(text="Pause")
            self._tick()

    def _stop(self):
        self.playing = False
        self._last_tick_time = None
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.play_btn.config(text="Play")

    def _tick(self):
        if not self.playing:
            return

        now = time.perf_counter()
        if self._last_tick_time is None:
            self._last_tick_time = now
            self._after_id = self.root.after(16, self._tick)
            return

        dt = now - self._last_tick_time
        self._last_tick_time = now
        dt = min(dt, 0.1)

        multiplier = max(1.0, self.speed.get())
        self.speed_label.config(text=f"{multiplier:.0f}×")

        p = self.progress.get()
        budget_mm = self._residual_mm

        while p < self.total_seg:
            if p < len(self.seg_moves):
                mv = self.seg_moves[p]
                seg_len = mv.length
                feed = max(800.0, mv.feed) if mv.feed > 0 else 800.0
            else:
                seg_len = 0.001
                feed = 800.0

            mm_this_tick = feed / 60.0 * dt * multiplier
            budget_mm += mm_this_tick

            if budget_mm >= seg_len:
                budget_mm -= seg_len
                p += 1
                dt = 0
            else:
                break

        self._residual_mm = budget_mm
        self.progress.set(p)
        self.slider.set(p)
        self._apply_progress()
        if p >= self.total_seg:
            self._stop()
            return
        self._after_id = self.root.after(16, self._tick)

    def _restart(self):
        self._stop()
        self.progress.set(0)
        self.slider.set(0)
        self._apply_progress()

    def _to_end(self):
        self._stop()
        self.progress.set(self.total_seg)
        self.slider.set(self.total_seg)
        self._apply_progress()

    def _on_wheel(self, e):
        if e.num == 5 or getattr(e, 'delta', 0) < 0:
            f = 1 / 1.15
        else:
            f = 1.15
        self.tx = e.x - (e.x - self.tx) * f
        self.ty = e.y - (e.y - self.ty) * f
        self.scale *= f
        self._rebuild()

    def _on_press(self, e):
        self._drag = (e.x, e.y, self.tx, self.ty)

    def _on_drag(self, e):
        if not self._drag:
            return
        x0, y0, tx0, ty0 = self._drag
        self.tx = tx0 + (e.x - x0)
        self.ty = ty0 + (e.y - y0)
        self._rebuild()

    def _on_move(self, e):
        mx, my = self._to_mm(e.x, e.y)
        extra = ""
        if self.total_seg:
            extra = f"   |   segment {self.progress.get()}/{self.total_seg}"
        self.status.config(text=f"X = {mx:7.2f} mm    Y = {my:7.2f} mm"
                                f"    (zoom {self.scale:.2f}×){extra}")


# ============================================================
# CLI ENTRY POINT
# ============================================================
def print_stats(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        moves, meta = parse_gcode(f.read())
    if not moves:
        print("No motion commands found in file.")
        return
    thr = auto_pen_threshold(meta['z_values'])
    apply_pen_threshold(moves, thr)
    strokes, total, _seg_moves = build_strokes(moves)
    s = compute_stats(moves, strokes, total)
    print(f"File          : {path}")
    print(f"Linear moves  : {s['n_moves']}  (G2/G3 arcs: {meta['n_arcs']})")
    print(f"Draw strokes  : {s['n_strokes']}   | Pen hops: {s['n_travel']}")
    print(f"Z levels      : {', '.join(f'{z:g}' for z in meta['z_values'])}"
          f"  -> Pen-down threshold Z <= {thr:g}")
    print(f"Drawing size  : {s['dxmax'] - s['dxmin']:.1f} x {s['dymax'] - s['dymin']:.1f} mm"
          f"   X {s['dxmin']:.1f}..{s['dxmax']:.1f}   Y {s['dymin']:.1f}..{s['dymax']:.1f}")
    print(f"Total travel  : X {s['xmin']:.1f}..{s['xmax']:.1f}"
          f"   Y {s['ymin']:.1f}..{s['ymax']:.1f}")
    print(f"Draw distance : {s['draw_dist']:.1f} mm | Rapid travel: {s['travel_dist']:.1f} mm"
          f" | Z travel: {s['z_dist']:.1f} mm")
    print(f"Est. time     : {s['minutes']:.1f} min")
    if meta['bad_lines']:
        print(f"[!] Unparsed lines: {meta['bad_lines'][:10]}")


def main():
    args = [a for a in sys.argv[1:]]
    stats_only = "--stats" in args
    if stats_only:
        args.remove("--stats")
    path = args[0] if args else None

    if stats_only:
        if not path:
            print("File path required: python gcode_viewer.py file.gcode --stats")
            return
        print_stats(path)
        return

    root = tk.Tk()
    GCodeViewer(root, path)
    root.mainloop()


if __name__ == "__main__":
    main()
