# -*- coding: utf-8 -*-
"""
3D to 2D Image Converter — Preprocessor for image_to_gcode.py
============================================================
3D photographs (real-world photos with smooth shading, cast shadows, and depth)
are challenging to convert into clean G-Code: simple luminance thresholding
picks up shadows, edge detectors fragment across textures, and smooth gradients
generate hundreds of tiny disconnected strokes.

This module converts 3D photographs into flat 2D artwork (clean line art,
flat color regions, or crisp binary drawings). Passing this processed output
into image_to_gcode.py produces significantly cleaner toolpaths.

6 CONVERSION METHODS:
  1. LINE ART     — Crisp black contours on white background (optimal for
                     LINE / CONTOUR modes in image_to_gcode)
  2. CARTOON      — Flat color regions + boundary outlines (optimal for COLOR)
  3. THRESHOLD    — Adaptive binary black & white with noise cleanup
  4. POSTERIZE    — Quantizes luminance into 4–8 discrete levels without gradients
  5. EDGE DRAWING — Canny edge detection with morphological gap bridging
  6. STIPPLE      — Dot / hatch patterns simulating continuous tones (for RASTER)

Usage:
    python convert_3d_to_2d.py                   # Open GUI
    python convert_3d_to_2d.py input.jpg          # CLI, default: lineart
    python convert_3d_to_2d.py input.jpg cartoon   # CLI, select method
    python convert_3d_to_2d.py input.jpg all       # Export ALL methods

Requirements:
    pip install opencv-python numpy Pillow
"""

import cv2
import math
import numpy as np
import os
import sys
import tkinter as tk

# Configure UTF-8 stdout on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFilter, ImageTk

# ============================================================
# CONFIGURATION
# ============================================================
class ConvertConfig:
    """Parameters for 3D → 2D image conversion."""

    def __init__(self):
        # ---- GENERAL ----
        self.denoise_strength = 10      # Denoise strength (0 = disabled)
        self.sharpen = True             # Sharpen before conversion

        # ---- LINE ART (Outlines) ----
        self.lineart_levels = 8         # Color clusters for palette grouping
        self.lineart_smooth = 3         # Bilateral filter iterations
        self.lineart_clean = 9          # Median filter window for speckle removal (odd integer)
        self.lineart_min_area = 60      # Discard fragments smaller than (px)
        self.lineart_thickness = 1      # Stroke thickness (px)

        # ---- CARTOON ----
        self.cartoon_levels = 6         # Number of discrete color levels
        self.cartoon_smooth = 2         # Bilateral filter iterations
        self.cartoon_clean = 9          # Median filter window for speckle removal
        self.cartoon_min_area = 60      # Discard small color fragments
        self.cartoon_edge_thick = 1     # Boundary outline thickness

        # ---- THRESHOLD (Binary) ----
        self.thresh_method = 'adaptive' # adaptive / otsu / manual
        self.thresh_value = 128         # Fixed threshold when method=manual
        self.thresh_block = 25          # Window block size for adaptive threshold
        self.thresh_c = 10              # Constant C subtracted in adaptive threshold
        self.thresh_invert = True       # True = Black strokes on white background
        self.thresh_clean = True        # Morphological noise cleanup

        # ---- POSTERIZE (Quantized Luminance) ----
        self.poster_levels = 5          # Number of luminance levels (2–16)
        self.poster_smooth = True       # Bilateral smoothing before quantization
        self.poster_edge = True         # Overlay edge outlines

        # ---- EDGE DRAWING (Canny) ----
        self.edge_low = 50              # Canny lower threshold
        self.edge_high = 150            # Canny upper threshold
        self.edge_blur = 3              # Gaussian blur kernel size before Canny
        self.edge_dilate = 0            # Edge dilation (0 = none)
        self.edge_close = True          # Morphological gap closing

        # ---- STIPPLE (Dots / Hatching) ----
        self.stipple_style = 'dots'     # dots / crosshatch / lines
        self.stipple_spacing = 4        # Dot / stroke spacing (px)
        self.stipple_min_dot = 1        # Minimum dot diameter (px)
        self.stipple_max_dot = 4        # Maximum dot diameter (px)

        # ---- BACKGROUND & SHADOW REMOVAL ----
        self.remove_bg = False          # Isolate object onto white background
        self.bg_method = 'auto'         # auto / white / chroma
        self.remove_shadow = True       # Enable shadow border elimination
        self.shadow_erode = 4           # Erode shadow border (px): 0-15
        self.shadow_thresh = 180        # Whitening threshold for faint shadows (120-240)


# ============================================================
# SHARED UTILITIES
# ============================================================
def _load_image(path):
    """Loads image safely supporting Unicode file paths."""
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return img


def _save_image(path, img):
    """Saves image safely supporting Unicode file paths."""
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(path)
    return ok


def _denoise(img, strength):
    """Edge-preserving bilateral filter."""
    if strength <= 0:
        return img
    return cv2.bilateralFilter(img, 9, float(strength) * 5, float(strength) * 5)


def remove_shadows(img_bgr, config):
    """Removes cast shadow borders around 3D physical objects."""
    if not config.remove_shadow and config.shadow_erode <= 0:
        return img_bgr

    h, w = img_bgr.shape[:2]
    out = img_bgr.copy()

    # 1. Whitening faint shadow / bright background areas to pure white (255, 255, 255)
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
    L = lab[:, :, 0]
    A = lab[:, :, 1]
    B = lab[:, :, 2]
    S = hsv[:, :, 1]

    band = max(4, int(min(h, w) * 0.05))
    border = np.zeros((h, w), bool)
    border[:band, :] = True
    border[-band:, :] = True
    border[:, :band] = True
    border[:, -band:] = True
    a_bg = float(np.median(A[border]))
    b_bg = float(np.median(B[border]))
    chroma = np.hypot(A.astype(np.float32) - a_bg, B.astype(np.float32) - b_bg)

    if config.remove_shadow:
        thresh_val = config.shadow_thresh
        is_light_shadow = (L > thresh_val) & (chroma < 20) & (S < 70)
        out[is_light_shadow] = [255, 255, 255]

    # 2. Morphological Mask Erosion on shadow borders
    if config.shadow_erode > 0:
        gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
        fg_mask = (gray < 248).astype(np.uint8) * 255
        k_close = np.ones((5, 5), np.uint8)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, k_close)

        e_sz = config.shadow_erode * 2 + 1
        k_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (e_sz, e_sz))
        eroded = cv2.erode(fg_mask, k_erode)

        trimmed = (fg_mask > 0) & (eroded == 0)
        out[trimmed] = [255, 255, 255]

    return out


def _enhance(img, config):
    """General preprocessing: denoise + sharpen + remove shadow borders."""
    out = img.copy()
    if config.denoise_strength > 0:
        out = _denoise(out, config.denoise_strength)
    if config.sharpen:
        blur = cv2.GaussianBlur(out, (0, 0), 1.0)
        out = cv2.addWeighted(out, 1.5, blur, -0.5, 0)
    out = remove_shadows(out, config)
    return out


# ============================================================
# METHOD 1: LINE ART — Black outlines on white background
# ============================================================
def _palette_kmeans(img_bgr, k, seed=42):
    """Clusters image into k color groups using k-means in Lab color space."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    h, w = lab.shape[:2]
    Z = lab.reshape(-1, 3).astype(np.float32)
    rng = np.random.default_rng(seed)
    sample = Z if len(Z) <= 40000 else Z[rng.choice(len(Z), 40000, replace=False)]
    cv2.setRNGSeed(seed)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, _, centers = cv2.kmeans(sample, int(k), None, crit, 3, cv2.KMEANS_PP_CENTERS)

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


def _merge_small_regions(lbl, min_area):
    """Merges small color fragments into surrounding regions."""
    if min_area <= 0:
        return lbl
    out = lbl.copy()
    for i in np.unique(lbl):
        m = (out == i).astype(np.uint8)
        n, comp, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        if n <= 1:
            continue
        tiny = np.zeros(n, bool)
        for j in range(1, n):
            tiny[j] = stats[j, cv2.CC_STAT_AREA] < min_area
        if not tiny.any():
            continue
        holes = tiny[comp]
        grown = cv2.dilate(np.where(holes, 0, out + 1).astype(np.uint8),
                           np.ones((5, 5), np.uint8))
        out[holes] = np.maximum(grown[holes].astype(np.int16) - 1, 0).astype(np.uint8)
    return out


def convert_lineart(img_bgr, config):
    """3D photo → crisp black outlines on pure white background."""
    h, w = img_bgr.shape[:2]
    work_size = 1000
    s = min(1.0, float(work_size) / max(h, w))
    if s < 1.0:
        small = cv2.resize(img_bgr, (max(1, int(w * s)), max(1, int(h * s))),
                           interpolation=cv2.INTER_AREA)
    else:
        small = img_bgr

    for _ in range(max(1, config.lineart_smooth)):
        small = cv2.bilateralFilter(small, 9, 75, 75)

    centers = _palette_kmeans(small, config.lineart_levels)[1]
    base = cv2.bilateralFilter(img_bgr, 9, 60, 60) if s < 1.0 else small
    lbl = _palette_kmeans(base, config.lineart_levels)[0]

    if config.lineart_clean >= 3:
        lbl = cv2.medianBlur(lbl.astype(np.uint8), config.lineart_clean | 1)
    lbl = _merge_small_regions(lbl, config.lineart_min_area)

    ink = (cv2.morphologyEx(lbl, cv2.MORPH_GRADIENT,
                            np.ones((3, 3), np.uint8)) > 0).astype(np.uint8) * 255
    if config.lineart_thickness > 1:
        ink = cv2.dilate(ink, np.ones((config.lineart_thickness,) * 2, np.uint8))

    out = np.full((h, w, 3), 255, np.uint8)
    out[ink > 0] = (0, 0, 0)
    return out


# ============================================================
# METHOD 2: CARTOON — Flat color regions + dark outlines
# ============================================================
def convert_cartoon(img_bgr, config):
    """3D photo → cartoon art: flat color regions + dark boundary outlines."""
    h, w = img_bgr.shape[:2]
    work_size = 1000
    s = min(1.0, float(work_size) / max(h, w))
    if s < 1.0:
        small = cv2.resize(img_bgr, (max(1, int(w * s)), max(1, int(h * s))),
                           interpolation=cv2.INTER_AREA)
    else:
        small = img_bgr

    for _ in range(max(1, config.cartoon_smooth)):
        small = cv2.bilateralFilter(small, 9, 75, 75)

    _, centers = _palette_kmeans(small, config.cartoon_levels)
    base = cv2.bilateralFilter(img_bgr, 9, 60, 60) if s < 1.0 else small
    lbl, _ = _palette_kmeans(base, config.cartoon_levels)

    if config.cartoon_clean >= 3:
        lbl = cv2.medianBlur(lbl.astype(np.uint8), config.cartoon_clean | 1)
    lbl = _merge_small_regions(lbl, config.cartoon_min_area)

    _, centers2 = _palette_kmeans(base, config.cartoon_levels)
    lab_flat = np.zeros((h, w, 3), np.uint8)
    for c_idx in range(len(centers2)):
        mask = (lbl == c_idx)
        lab_flat[mask] = centers2[c_idx].astype(np.uint8)
    flat = cv2.cvtColor(lab_flat, cv2.COLOR_LAB2BGR)

    ink = (cv2.morphologyEx(lbl, cv2.MORPH_GRADIENT,
                            np.ones((3, 3), np.uint8)) > 0).astype(np.uint8) * 255
    if config.cartoon_edge_thick > 1:
        ink = cv2.dilate(ink, np.ones((config.cartoon_edge_thick,) * 2, np.uint8))

    flat[ink > 0] = (0, 0, 0)
    return flat


# ============================================================
# METHOD 3: THRESHOLD — Binary black & white
# ============================================================
def convert_threshold(img_bgr, config):
    """3D photo → clean binary black and white."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    method = config.thresh_method
    if method == 'adaptive':
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, config.thresh_block | 1, config.thresh_c)
    elif method == 'otsu':
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        _, binary = cv2.threshold(gray, config.thresh_value, 255, cv2.THRESH_BINARY)

    if config.thresh_invert:
        white_ratio = np.count_nonzero(binary) / binary.size
        if white_ratio < 0.3:
            binary = cv2.bitwise_not(binary)

    if config.thresh_clean:
        k = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)

    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


# ============================================================
# METHOD 4: POSTERIZE — Quantized luminance
# ============================================================
def convert_posterize(img_bgr, config):
    """3D photo → posterized image (discrete luminance levels, removes gradients)."""
    n = max(2, min(16, config.poster_levels))

    if config.poster_smooth:
        img = cv2.bilateralFilter(img_bgr, 9, 75, 75)
        img = cv2.bilateralFilter(img, 9, 75, 75)
    else:
        img = img_bgr.copy()

    step = 256.0 / n
    out = (np.floor(img.astype(np.float32) / step) * step + step / 2)
    out = np.clip(out, 0, 255).astype(np.uint8)

    if config.poster_edge:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 160)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8))
        out[edges > 0] = (0, 0, 0)

    return out


# ============================================================
# METHOD 5: EDGE DRAWING — Canny edge contours
# ============================================================
def convert_edge(img_bgr, config):
    """3D photo → Canny edge contours with morphological bridging."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    if config.edge_blur > 0:
        ks = config.edge_blur | 1
        gray = cv2.GaussianBlur(gray, (ks, ks), 0)

    edges = cv2.Canny(gray, config.edge_low, config.edge_high)

    if config.edge_close:
        k = np.ones((3, 3), np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k)

    if config.edge_dilate > 0:
        k = np.ones((config.edge_dilate * 2 + 1,) * 2, np.uint8)
        edges = cv2.dilate(edges, k)

    out = np.full(img_bgr.shape, 255, np.uint8)
    out[edges > 0] = (0, 0, 0)
    return out


# ============================================================
# METHOD 6: STIPPLE — Dots / Hatching
# ============================================================
def convert_stipple(img_bgr, config):
    """3D photo → stippled dot or hatch pattern simulating shading."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    h, w = gray.shape

    inv = 255 - gray

    out = np.full((h, w), 255, np.uint8)
    spacing = max(2, config.stipple_spacing)
    min_d = max(1, config.stipple_min_dot)
    max_d = max(min_d, config.stipple_max_dot)

    style = config.stipple_style

    if style == 'dots':
        for y in range(spacing // 2, h, spacing):
            for x in range(spacing // 2, w, spacing):
                val = float(inv[y, x]) / 255.0
                if val < 0.05:
                    continue
                r = int(min_d + val * (max_d - min_d))
                cv2.circle(out, (x, y), max(1, r), 0, -1)

    elif style == 'lines':
        for y in range(spacing // 2, h, spacing):
            x = 0
            while x < w:
                val = float(inv[y, min(x, w - 1)]) / 255.0
                if val < 0.05:
                    x += spacing
                    continue
                thick = max(1, int(min_d + val * (max_d - min_d)))
                x_end = x
                while x_end < w and float(inv[y, x_end]) / 255.0 >= 0.05:
                    x_end += 1
                cv2.line(out, (x, y), (x_end, y), 0, thick)
                x = x_end + spacing

    elif style == 'crosshatch':
        for angle_deg, thresh_frac in [(45, 0.15), (-45, 0.40), (0, 0.70)]:
            angle_rad = math.radians(angle_deg)
            dx = math.cos(angle_rad)
            dy = math.sin(angle_rad)
            step = spacing
            perp_dx = -dy
            perp_dy = dx
            diag = int(math.hypot(h, w))
            for offset in range(-diag, diag, step):
                cx = w / 2.0 + offset * perp_dx
                cy = h / 2.0 + offset * perp_dy
                x0 = int(cx - diag * dx)
                y0 = int(cy - diag * dy)
                x1 = int(cx + diag * dx)
                y1 = int(cy + diag * dy)
                n_steps = max(2, int(math.hypot(x1 - x0, y1 - y0)))
                drawn = False
                for t in range(n_steps):
                    frac = t / float(n_steps)
                    sx = int(x0 + (x1 - x0) * frac)
                    sy = int(y0 + (y1 - y0) * frac)
                    if 0 <= sx < w and 0 <= sy < h:
                        if float(inv[sy, sx]) / 255.0 >= thresh_frac:
                            if not drawn:
                                prev = (sx, sy)
                                drawn = True
                            else:
                                cv2.line(out, prev, (sx, sy), 0, 1)
                                prev = (sx, sy)
                        else:
                            drawn = False

    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


# ============================================================
# BACKGROUND REMOVAL (OPTIONAL)
# ============================================================
def remove_background(img_bgr, config):
    """Isolates object and composites onto a pure white background."""
    h, w = img_bgr.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(img_bgr, (0, 0), 1.2), cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    band = max(4, int(min(h, w) * 0.04))
    border = np.zeros((h, w), bool)
    border[:band, :] = True
    border[-band:, :] = True
    border[:, :band] = True
    border[:, -band:] = True

    a_bg = float(np.median(A[border]))
    b_bg = float(np.median(B[border]))
    chroma = np.hypot(A.astype(np.float32) - a_bg, B.astype(np.float32) - b_bg)

    l_bg = float(np.median(L[border]))
    dark_ratio = L.astype(np.float32) / max(1.0, l_bg)

    mask = ((chroma > 10) | (dark_ratio < 0.72)).astype(np.uint8) * 255

    k3 = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k3, iterations=3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k3, iterations=2)

    flood = mask.copy()
    tmp = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, tmp, (0, 0), 255)
    mask = cv2.bitwise_or(mask, cv2.bitwise_not(flood))

    alpha = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), 1.5)
    alpha3 = cv2.merge([alpha, alpha, alpha])
    out = (img_bgr.astype(np.float32) * alpha3 + 255.0 * (1.0 - alpha3))
    return np.clip(out, 0, 255).astype(np.uint8)


# ============================================================
# MAIN CONVERSION DISPATCHER
# ============================================================
METHODS = {
    'lineart':   ('Line Art',    'Black outlines on white background',       convert_lineart),
    'cartoon':   ('Cartoon',     'Flat color regions + outlines',            convert_cartoon),
    'threshold': ('Threshold',   'Binary black & white',                     convert_threshold),
    'posterize': ('Posterize',   'Quantize luminance, strip gradients',      convert_posterize),
    'edge':      ('Edge',        'Canny edge contours only',                 convert_edge),
    'stipple':   ('Stipple',     'Dots / hatching simulating tones',         convert_stipple),
}


def convert(img_path, method, config, output_path=None):
    """Converts 3D image into 2D flat artwork. Returns (result_img, saved_path)."""
    img = _load_image(img_path)
    img = _enhance(img, config)

    if config.remove_bg:
        img = remove_background(img, config)

    if method not in METHODS:
        raise ValueError(f"Unknown method '{method}'. Available: {', '.join(METHODS.keys())}")

    _, _, func = METHODS[method]
    result = func(img, config)

    if output_path is None:
        base, ext = os.path.splitext(img_path)
        output_path = f"{base}_{method}.png"

    _save_image(output_path, result)
    return result, output_path


# ============================================================
# GUI INTERFACE
# ============================================================
UI_SCALE = 0.85
BASE_W, BASE_H = 1200, 750
SCREEN_USE = 0.92


def _ui_px(v):
    return max(1, int(v * UI_SCALE))


def _ui_font(size):
    return max(7, int(size * UI_SCALE + 0.5))


def _fit_scale(root):
    global UI_SCALE
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    fit = min(sw * SCREEN_USE / BASE_W, sh * SCREEN_USE / BASE_H, 1.0)
    UI_SCALE = max(0.55, min(UI_SCALE, fit))


# ============================================================
# CROP DIALOG — Interactive Crop Window
# ============================================================
class CropDialog:
    """Interactive image cropping dialog with resizable boundary frame."""

    HANDLE_SIZE = 8
    MIN_CROP_PX = 20
    OVERLAY_STIPPLE = 'gray50'

    def __init__(self, parent, pil_img, initial_rect, callback):
        self.pil_img = pil_img
        self.img_w, self.img_h = pil_img.size
        self.callback = callback

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("Crop Image")
        self.dlg.configure(bg="#1a1b26")
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
        ttk.Label(hdr, text="Crop Image — Drag boundary handles to adjust crop region",
                  font=("Segoe UI", _ui_font(11), "bold"),
                  foreground="#7aa2f7", background="#1a1b26").pack(side=tk.LEFT)
        self.size_label = ttk.Label(hdr, text="", foreground="#565f89",
                                    background="#1a1b26")
        self.size_label.pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(self.dlg, width=self.cv_w, height=self.cv_h,
                                bg="#11111b", highlightthickness=1,
                                highlightbackground="#414868")
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
                                      outline="#7aa2f7", width=2, tags="crop")

        for i in (1, 2):
            gx = cx1 + (cx2 - cx1) * i / 3
            gy = cy1 + (cy2 - cy1) * i / 3
            self.canvas.create_line(gx, cy1, gx, cy2,
                                     fill="#414868", dash=(3, 3), tags="crop")
            self.canvas.create_line(cx1, gy, cx2, gy,
                                     fill="#414868", dash=(3, 3), tags="crop")

        hs = self.HANDLE_SIZE
        for hx, hy in [(cx1, cy1), (cx2, cy1), (cx1, cy2), (cx2, cy2),
                        ((cx1+cx2)/2, cy1), ((cx1+cx2)/2, cy2),
                        (cx1, (cy1+cy2)/2), (cx2, (cy1+cy2)/2)]:
            self.canvas.create_rectangle(hx-hs, hy-hs, hx+hs, hy+hs,
                                          fill="#7aa2f7", outline="#c0caf5",
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
        dx = (ev.x - self._drag_start[0]) / self.scale
        dy = (ev.y - self._drag_start[1]) / self.scale
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


class ConvertApp:
    """GUI for 3D to 2D Image Conversion."""

    def __init__(self, root):
        self.root = root
        self.root.title("3D → 2D Image Converter — Preprocessor for G-Code")
        _fit_scale(root)

        w, h = _ui_px(BASE_W), _ui_px(BASE_H)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.minsize(_ui_px(900), _ui_px(550))
        root.configure(bg="#1a1b26")

        self.config = ConvertConfig()
        self.image_path = None
        self.result_image = None
        self.original_img = None
        self.cropped_img = None
        self.crop_rect = None
        self.current_method = 'lineart'

        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        bg = "#1a1b26"
        fg = "#c0caf5"
        accent = "#7aa2f7"
        accent2 = "#bb9af7"
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg,
                         font=("Segoe UI", _ui_font(10)))
        style.configure("Header.TLabel", background=bg, foreground=accent,
                         font=("Segoe UI", _ui_font(14), "bold"))
        style.configure("Sub.TLabel", background=bg, foreground="#565f89",
                         font=("Segoe UI", _ui_font(9)))
        style.configure("Method.TLabel", background=bg, foreground="#e0af68",
                         font=("Segoe UI", _ui_font(10), "bold"))
        style.configure("TButton", font=("Segoe UI", _ui_font(10)))
        style.configure("Accent.TButton", font=("Segoe UI", _ui_font(11), "bold"),
                         foreground=bg, background=accent)
        style.map("Accent.TButton", background=[("active", accent2)])
        style.configure("TLabelframe", background=bg, foreground=accent,
                         font=("Segoe UI", _ui_font(10), "bold"))
        style.configure("TLabelframe.Label", background=bg, foreground=accent)
        style.configure("TRadiobutton", background=bg, foreground=fg,
                         font=("Segoe UI", _ui_font(10)))
        style.configure("TCheckbutton", background=bg, foreground=fg,
                         font=("Segoe UI", _ui_font(10)))

        hdr_fr = ttk.Frame(self.root)
        hdr_fr.pack(fill=tk.X, padx=12, pady=(8, 0))
        ttk.Label(hdr_fr, text="3D → 2D Image Converter",
                  style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(hdr_fr, text="Preprocessing continuous-tone photos into flat 2D vector art for G-Code",
                  style="Sub.TLabel").pack(side=tk.LEFT, padx=(12, 0))

        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        left = ttk.Frame(main, width=_ui_px(340))
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        left.pack_propagate(False)

        bottom = ttk.Frame(left)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        ttk.Button(bottom, text="Convert", style="Accent.TButton",
                   command=self._do_convert).pack(fill=tk.X, pady=(0, 4))

        btn_row = ttk.Frame(bottom)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="Save Result",
                   command=self._save_result).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(btn_row, text="Export All",
                   command=self._export_all).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        scroll_area = ttk.Frame(left)
        scroll_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(scroll_area, bg=bg, highlightthickness=0)
        vsb = ttk.Scrollbar(scroll_area, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        opts = ttk.Frame(canvas)
        opts_win = canvas.create_window((0, 0), window=opts, anchor="nw")
        opts.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(opts_win, width=e.width))

        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<Enter>",
                    lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>",
                    lambda e: canvas.unbind_all("<MouseWheel>"))

        ff = ttk.LabelFrame(opts, text="Input Image")
        ff.pack(fill=tk.X, pady=(0, 4))
        self.file_label = ttk.Label(ff, text="No image selected", foreground="#565f89")
        self.file_label.pack(fill=tk.X, padx=6, pady=2)
        self.crop_label = ttk.Label(ff, text="", foreground="#565f89",
                                     font=("Segoe UI", _ui_font(9)))
        self.crop_label.pack(fill=tk.X, padx=6)
        file_btns = ttk.Frame(ff)
        file_btns.pack(fill=tk.X, padx=6, pady=(0, 4))
        ttk.Button(file_btns, text="Select Image...",
                   command=self._open_file).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(file_btns, text="Crop",
                   command=self._open_crop).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        mf = ttk.LabelFrame(opts, text="Conversion Method")
        mf.pack(fill=tk.X, pady=(0, 4))

        self.method_var = tk.StringVar(value='lineart')
        for key, (icon, desc, _) in METHODS.items():
            fr = ttk.Frame(mf)
            fr.pack(fill=tk.X, padx=4, pady=1)
            ttk.Radiobutton(fr, text=f"{icon}", variable=self.method_var,
                            value=key, command=self._on_method_change).pack(side=tk.LEFT)
            ttk.Label(fr, text=desc, foreground="#565f89",
                      font=("Segoe UI", _ui_font(9))).pack(side=tk.LEFT, padx=(4, 0))

        self.opt_frames = {}
        self._build_lineart_opts(opts)
        self._build_cartoon_opts(opts)
        self._build_threshold_opts(opts)
        self._build_posterize_opts(opts)
        self._build_edge_opts(opts)
        self._build_stipple_opts(opts)

        cf = ttk.LabelFrame(opts, text="General Options")
        cf.pack(fill=tk.X, pady=(0, 4))

        self.denoise_var = tk.IntVar(value=self.config.denoise_strength)
        r = ttk.Frame(cf)
        r.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(r, text="Denoise:", width=14).pack(side=tk.LEFT)
        ttk.Scale(r, from_=0, to=30, variable=self.denoise_var,
                  orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.sharpen_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(cf, text="Sharpen before conversion",
                        variable=self.sharpen_var).pack(fill=tk.X, padx=6, pady=2)

        self.remove_shadow_var = tk.BooleanVar(value=self.config.remove_shadow)
        ttk.Checkbutton(cf, text="Remove shadow borders",
                        variable=self.remove_shadow_var).pack(fill=tk.X, padx=6, pady=2)

        self.shadow_erode_var = tk.IntVar(value=self.config.shadow_erode)
        self._make_slider(cf, "Shadow erode (px):", self.shadow_erode_var, 0, 15)

        self.shadow_thresh_var = tk.IntVar(value=self.config.shadow_thresh)
        self._make_slider(cf, "Shadow threshold:", self.shadow_thresh_var, 120, 240)

        self.remove_bg_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cf, text="Extract object (paste onto white bg)",
                        variable=self.remove_bg_var).pack(fill=tk.X, padx=6, pady=2)

        self._on_method_change()

        right = ttk.Frame(main)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vf = ttk.Frame(right)
        vf.pack(fill=tk.X, pady=(0, 4))
        self.view_var = tk.StringVar(value='original')
        for val, label in [('original', 'Original'), ('result', 'Result'),
                           ('compare', '↔ Compare')]:
            ttk.Radiobutton(vf, text=label, variable=self.view_var,
                            value=val, command=self._update_preview).pack(side=tk.LEFT, padx=4)

        self.info_label = ttk.Label(right, text="", foreground="#e0af68",
                                     font=("Segoe UI", _ui_font(9)))
        self.info_label.pack(fill=tk.X)

        self.preview_canvas = tk.Canvas(right, bg="#11111b", highlightthickness=1,
                                         highlightbackground="#414868")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self._preview_photo = None

    def _make_slider(self, parent, label, var, from_, to_, row=None):
        r = ttk.Frame(parent)
        r.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(r, text=label, width=16).pack(side=tk.LEFT)
        ttk.Scale(r, from_=from_, to=to_, variable=var,
                  orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True)
        return r

    def _build_lineart_opts(self, parent):
        f = ttk.LabelFrame(parent, text="Line Art")
        self.opt_frames['lineart'] = f

        self.la_levels = tk.IntVar(value=8)
        self._make_slider(f, "Color groups:", self.la_levels, 3, 16)
        self.la_smooth = tk.IntVar(value=3)
        self._make_slider(f, "Smoothing:", self.la_smooth, 1, 8)
        self.la_clean = tk.IntVar(value=9)
        self._make_slider(f, "Clean spots:", self.la_clean, 3, 21)
        self.la_min_area = tk.IntVar(value=60)
        self._make_slider(f, "Min region area <", self.la_min_area, 0, 200)
        self.la_thick = tk.IntVar(value=1)
        self._make_slider(f, "Line thickness:", self.la_thick, 1, 5)

    def _build_cartoon_opts(self, parent):
        f = ttk.LabelFrame(parent, text="Cartoon")
        self.opt_frames['cartoon'] = f

        self.ct_levels = tk.IntVar(value=6)
        self._make_slider(f, "Color levels:", self.ct_levels, 3, 12)
        self.ct_smooth = tk.IntVar(value=2)
        self._make_slider(f, "Smoothing:", self.ct_smooth, 1, 8)
        self.ct_clean = tk.IntVar(value=9)
        self._make_slider(f, "Clean spots:", self.ct_clean, 3, 21)
        self.ct_min_area = tk.IntVar(value=60)
        self._make_slider(f, "Min region area <", self.ct_min_area, 0, 200)
        self.ct_edge = tk.IntVar(value=1)
        self._make_slider(f, "Outline width:", self.ct_edge, 1, 5)

    def _build_threshold_opts(self, parent):
        f = ttk.LabelFrame(parent, text="Threshold")
        self.opt_frames['threshold'] = f

        r = ttk.Frame(f)
        r.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(r, text="Method:", width=14).pack(side=tk.LEFT)
        self.th_method = tk.StringVar(value='adaptive')
        for v, t in [('adaptive', 'Adaptive'), ('otsu', 'Otsu'), ('manual', 'Manual')]:
            ttk.Radiobutton(r, text=t, variable=self.th_method, value=v).pack(side=tk.LEFT)

        self.th_value = tk.IntVar(value=128)
        self._make_slider(f, "Threshold (manual):", self.th_value, 0, 255)
        self.th_block = tk.IntVar(value=25)
        self._make_slider(f, "Block size:", self.th_block, 3, 51)
        self.th_c = tk.IntVar(value=10)
        self._make_slider(f, "Constant C:", self.th_c, 0, 30)
        self.th_clean = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Clean noise (morphology)",
                        variable=self.th_clean).pack(fill=tk.X, padx=6, pady=2)

    def _build_posterize_opts(self, parent):
        f = ttk.LabelFrame(parent, text="Posterize")
        self.opt_frames['posterize'] = f

        self.pt_levels = tk.IntVar(value=5)
        self._make_slider(f, "Luminance levels:", self.pt_levels, 2, 16)
        self.pt_smooth = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Smooth before quantization",
                        variable=self.pt_smooth).pack(fill=tk.X, padx=6, pady=2)
        self.pt_edge = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Add outline strokes",
                        variable=self.pt_edge).pack(fill=tk.X, padx=6, pady=2)

    def _build_edge_opts(self, parent):
        f = ttk.LabelFrame(parent, text="Edge Drawing")
        self.opt_frames['edge'] = f

        self.ed_low = tk.IntVar(value=50)
        self._make_slider(f, "Canny low:", self.ed_low, 10, 200)
        self.ed_high = tk.IntVar(value=150)
        self._make_slider(f, "Canny high:", self.ed_high, 50, 300)
        self.ed_blur = tk.IntVar(value=3)
        self._make_slider(f, "Blur radius:", self.ed_blur, 1, 15)
        self.ed_dilate = tk.IntVar(value=0)
        self._make_slider(f, "Dilate:", self.ed_dilate, 0, 5)
        self.ed_close = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Bridge gaps (morphology)",
                        variable=self.ed_close).pack(fill=tk.X, padx=6, pady=2)

    def _build_stipple_opts(self, parent):
        f = ttk.LabelFrame(parent, text="Stipple")
        self.opt_frames['stipple'] = f

        r = ttk.Frame(f)
        r.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(r, text="Style:", width=14).pack(side=tk.LEFT)
        self.st_style = tk.StringVar(value='dots')
        for v, t in [('dots', 'Dots'), ('lines', 'Lines'), ('crosshatch', 'Crosshatch')]:
            ttk.Radiobutton(r, text=t, variable=self.st_style, value=v).pack(side=tk.LEFT)

        self.st_spacing = tk.IntVar(value=4)
        self._make_slider(f, "Spacing:", self.st_spacing, 2, 12)
        self.st_min = tk.IntVar(value=1)
        self._make_slider(f, "Min dot:", self.st_min, 1, 4)
        self.st_max = tk.IntVar(value=4)
        self._make_slider(f, "Max dot:", self.st_max, 1, 8)

    def _on_method_change(self):
        method = self.method_var.get()
        for key, frame in self.opt_frames.items():
            if key == method:
                frame.pack(fill=tk.X, pady=(0, 4))
            else:
                frame.pack_forget()
        self.current_method = method

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Select 3D Photo",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                       ("All files", "*.*")])
        if not path:
            return
        self.image_path = path
        self.file_label.config(text=os.path.basename(path), foreground="#c0caf5")

        self.original_img = _load_image(path)
        self.crop_rect = None
        self.cropped_img = None
        self.result_image = None
        self._update_crop_label()
        self.view_var.set('original')
        self._update_preview()

    def _open_crop(self):
        if self.original_img is None:
            messagebox.showwarning("No Image", "Please select an input image first!")
            return
        rgb = cv2.cvtColor(self.original_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        CropDialog(self.root, pil_img, self.crop_rect, self._apply_crop)

    def _apply_crop(self, rect):
        self.crop_rect = rect
        if rect is not None:
            x, y, w, h = rect
            self.cropped_img = self.original_img[y:y+h, x:x+w].copy()
        else:
            self.cropped_img = None
        self.result_image = None
        self._update_crop_label()
        self.view_var.set('original')
        self._update_preview()

    def _update_crop_label(self):
        if self.crop_rect:
            x, y, w, h = self.crop_rect
            self.crop_label.config(
                text=f" Cropped: {w}×{h} px (from {x},{y})",
                foreground="#9ece6a")
        else:
            self.crop_label.config(text="", foreground="#565f89")

    def _get_working_img(self):
        if self.cropped_img is not None:
            return self.cropped_img.copy()
        if self.original_img is not None:
            return self.original_img.copy()
        return None

    def _sync_config(self):
        c = self.config
        c.denoise_strength = self.denoise_var.get()
        c.sharpen = self.sharpen_var.get()
        c.remove_shadow = self.remove_shadow_var.get()
        c.shadow_erode = self.shadow_erode_var.get()
        c.shadow_thresh = self.shadow_thresh_var.get()
        c.remove_bg = self.remove_bg_var.get()

        c.lineart_levels = self.la_levels.get()
        c.lineart_smooth = self.la_smooth.get()
        c.lineart_clean = self.la_clean.get()
        c.lineart_min_area = self.la_min_area.get()
        c.lineart_thickness = self.la_thick.get()

        c.cartoon_levels = self.ct_levels.get()
        c.cartoon_smooth = self.ct_smooth.get()
        c.cartoon_clean = self.ct_clean.get()
        c.cartoon_min_area = self.ct_min_area.get()
        c.cartoon_edge_thick = self.ct_edge.get()

        c.thresh_method = self.th_method.get()
        c.thresh_value = self.th_value.get()
        c.thresh_block = self.th_block.get()
        c.thresh_c = self.th_c.get()
        c.thresh_clean = self.th_clean.get()

        c.poster_levels = self.pt_levels.get()
        c.poster_smooth = self.pt_smooth.get()
        c.poster_edge = self.pt_edge.get()

        c.edge_low = self.ed_low.get()
        c.edge_high = self.ed_high.get()
        c.edge_blur = self.ed_blur.get()
        c.edge_dilate = self.ed_dilate.get()
        c.edge_close = self.ed_close.get()

        c.stipple_style = self.st_style.get()
        c.stipple_spacing = self.st_spacing.get()
        c.stipple_min_dot = self.st_min.get()
        c.stipple_max_dot = self.st_max.get()

    def _do_convert(self):
        if self.original_img is None:
            messagebox.showwarning("No Image", "Please select an input image first!")
            return

        self._sync_config()
        method = self.method_var.get()

        self.info_label.config(text="Converting...", foreground="#e0af68")
        self.root.update()

        try:
            src = self._get_working_img()
            img = _enhance(src, self.config)
            if self.config.remove_bg:
                img = remove_background(img, self.config)
            _, _, func = METHODS[method]
            self.result_image = func(img, self.config)

            h, w = self.result_image.shape[:2]
            name, desc, _ = METHODS[method]
            crop_info = ""
            if self.crop_rect:
                crop_info = " (cropped)"
            self.info_label.config(
                text=f" {name} — {w}×{h} px | {desc}{crop_info}",
                foreground="#9ece6a")
            self.view_var.set('result')
            self._update_preview()

        except Exception as e:
            self.info_label.config(text=f"Error: {e}", foreground="#f7768e")

    def _update_preview(self):
        cw = self.preview_canvas.winfo_width()
        ch = self.preview_canvas.winfo_height()
        if cw < 10 or ch < 10:
            self.root.after(100, self._update_preview)
            return

        view = self.view_var.get()

        if view == 'original' and self.original_img is not None:
            img = self.cropped_img if self.cropped_img is not None else self.original_img
        elif view == 'result' and self.result_image is not None:
            img = self.result_image
        elif view == 'compare' and self.original_img is not None and self.result_image is not None:
            orig = self.cropped_img if self.cropped_img is not None else self.original_img
            h1, w1 = orig.shape[:2]
            h2, w2 = self.result_image.shape[:2]
            target_h = max(h1, h2)
            img1 = cv2.resize(orig,
                              (int(w1 * target_h / h1), target_h))
            img2 = cv2.resize(self.result_image,
                              (int(w2 * target_h / h2), target_h))
            sep = np.full((target_h, 4, 3), (65, 72, 126), np.uint8)
            img = np.hstack([img1, sep, img2])
        else:
            self.preview_canvas.delete("all")
            self.preview_canvas.create_text(
                cw // 2, ch // 2,
                text="Select an input image to begin\n\n"
                     " Click 'Select Image...' on the left\n"
                     " Choose a conversion method\n"
                     " Click 'Convert'",
                fill="#565f89", font=("Segoe UI", _ui_font(12)),
                justify=tk.CENTER)
            return

        ih, iw = img.shape[:2]
        scale = min(cw / iw, ch / ih, 1.0)
        if scale < 1.0:
            img = cv2.resize(img, (max(1, int(iw * scale)), max(1, int(ih * scale))),
                             interpolation=cv2.INTER_AREA)

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        self._preview_photo = ImageTk.PhotoImage(pil)

        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(cw // 2, ch // 2,
                                          image=self._preview_photo, anchor=tk.CENTER)

    def _save_result(self):
        if self.result_image is None:
            messagebox.showwarning("No Result", "Please convert the image first!")
            return

        method = self.method_var.get()
        default_name = ""
        if self.image_path:
            base = os.path.splitext(os.path.basename(self.image_path))[0]
            default_name = f"{base}_{method}.png"

        path = filedialog.asksaveasfilename(
            title="Save 2D Image",
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("BMP Image", "*.bmp")])
        if not path:
            return

        _save_image(path, self.result_image)
        self.info_label.config(text=f"Saved: {os.path.basename(path)}",
                                foreground="#9ece6a")

    def _export_all(self):
        if self.original_img is None:
            messagebox.showwarning("No Image", "Please select an input image first!")
            return

        folder = filedialog.askdirectory(title="Select Export Directory")
        if not folder:
            return

        self._sync_config()
        self.info_label.config(text="Exporting all methods...",
                                foreground="#e0af68")
        self.root.update()

        base = os.path.splitext(os.path.basename(self.image_path))[0]
        src = self._get_working_img()
        img = _enhance(src, self.config)
        if self.config.remove_bg:
            img = remove_background(img, self.config)

        count = 0
        for key, (name, desc, func) in METHODS.items():
            try:
                result = func(img, self.config)
                out_path = os.path.join(folder, f"{base}_{key}.png")
                _save_image(out_path, result)
                count += 1
            except Exception as e:
                print(f"[ERROR] {key}: {e}")

        self.info_label.config(
            text=f" Exported {count}/{len(METHODS)} methods → {folder}",
            foreground="#9ece6a")


# ============================================================
# CLI ENTRY POINT
# ============================================================
def main_cli():
    """Command-line interface entry point."""
    if len(sys.argv) < 2:
        root = tk.Tk()
        app = ConvertApp(root)
        root.mainloop()
        return

    img_path = sys.argv[1]
    method = sys.argv[2] if len(sys.argv) > 2 else 'lineart'
    output = sys.argv[3] if len(sys.argv) > 3 else None

    config = ConvertConfig()

    if method == 'all':
        base, _ = os.path.splitext(img_path)
        img = _load_image(img_path)
        img = _enhance(img, config)
        for key, (name, desc, func) in METHODS.items():
            out_path = f"{base}_{key}.png"
            result = func(img, config)
            _save_image(out_path, result)
            print(f"{name}: {out_path}")
        print(f"\nExported {len(METHODS)} files.")
    else:
        result, out_path = convert(img_path, method, config, output)
        h, w = result.shape[:2]
        print(f"Converted: {out_path} ({w}×{h} px)")
        print(f"→ Pass this file into image_to_gcode.py to generate G-Code.")


if __name__ == "__main__":
    main_cli()
