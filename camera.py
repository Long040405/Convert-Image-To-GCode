# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os
import sys
import time
from datetime import datetime

# Set UTF-8 stdout on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Global UI and Camera settings
UI_SCALE = 0.5             # UI display scale factor (0.3 = 30%, 0.5 = 50%, 0.7 = 70%)
                           # Maximum upper bound — fit_display() auto-downscales further
                           # if the window exceeds screen dimensions.
SCREEN_USE = 0.85          # Window occupies at most 85% of screen
TRACKBAR_H = 190           # Height of 4 trackbars + title bar (px)
current_exposure_ms = 42   # 42ms manual exposure (slider max: 100)
current_gain = 10          # Gain (dB) (slider max: 24)
auto_exposure_enabled = 0  # 0 = Auto Exposure Disabled
color_mode_idx = 3         # Default = 3 (BayerGR2BGR)
live_sharpen_level = 2     # Software sharpening level on Live stream (0 = Off, 1-5 = Digital sharpness level)

# ===== CAPTURE CONFIGURATION =====
CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
CAPTURE_AVG_FRAMES = 3     # Number of frames averaged for temporal noise reduction (set 1 to disable)
CLAHE_CLIP = 2.0           # Local contrast enhancement clip limit
UNSHARP_SIGMA = 1.2        # Sharpening mask radius (px)

# ===== OBJECT SEGMENTATION CONFIGURATION (Clean background for G-Code) =====
# Problem: On white paper, cast shadows around physical objects are dark. If thresholded
# directly by luminance, G-Code will draw the shadows too. Increasing lighting burns highlights.
# Solution: Separate using chrominance (shadows change brightness, not hue), level background
# illumination, and paste object onto pure white background.
EXTRACT_OBJECT = True      # False = Disable object isolation, save sharpened frame only
OBJ_CHROMA_THR = 10.0      # Color divergence from background (LAB a/b) > threshold = OBJECT
                           #   Pale objects missed    -> DECREASE (6–8)
                           #   Yellowish background captured -> INCREASE (14–18)
OBJ_DARK_RATIO = 0.72      # Darker than background < 72% = OBJECT (catches black/gray objects)
                           #   Cast shadows captured  -> DECREASE (0.6)
                           #   Dark objects missed    -> INCREASE (0.8)
OBJ_MIN_AREA_RATIO = 0.001  # Discard blobs smaller than 0.1% of image area (noise, dust)
OBJ_USE_GRABCUT = True     # Refine contours with GrabCut (~0.5s additional processing)
OBJ_FEATHER = 1.0          # Alpha feather radius at boundary (px), 0 = sharp cut
OBJ_CROP_MARGIN = 20       # Tight crop margin around object (px). Set -1 to keep original frame

# ===== CAST SHADOW ELIMINATION =====
# Shadows are dimmed background rather than physical objects (lower luminance, unchanged chrominance).
# Solution: Construct an illumination field — mask the object seed, interpolate background, and smooth.
# Dividing the image by this field eliminates diffuse shadows while retaining true object boundaries.
REMOVE_SHADOW = True       # False = Disable shadow removal
SHADOW_SEED_RATIO = 0.45   # Darker than 45% of background = definite OBJECT seed
                           #   Dark shadows captured -> DECREASE (0.3–0.4)
                           #   Dark gray objects eroded -> INCREASE (0.55–0.6)
SHADOW_SMOOTH = 9.0        # Smoothness of light field (px, evaluated on 512px downscaled image)
                           #   Residual shadow edges -> INCREASE slowly (11–14)
                           #   Large objects treated as bg -> DECREASE (6–7)

# ===== CARTOONIZATION CONFIGURATION =====
# Raw photos contain continuous gradients and sensor noise that generate fragmented toolpaths.
# Cartoonization quantizes images into discrete flat color regions with crisp boundary strokes.
CARTOON = True             # Generate *_cartoon.png after capture
CARTOON_LEVELS = 6         # Number of quantized color clusters (fewer = simpler, more = retains detail)
CARTOON_SMOOTH = 2         # Bilateral filter iterations (removes surface texture while keeping edges)
CARTOON_CLEAN = 9          # Median filter window for speckle removal on color map (odd integer)
                           #   Fragmented lines remain -> INCREASE (11–15)
                           #   Fine details lost       -> DECREASE (5–7)
CARTOON_MIN_AREA = 60      # Discard color patches smaller than this area (px)
CARTOON_EDGE_THICK = 1     # Edge outline thickness (px)
CARTOON_WORK = 1000        # Processing resolution (px long edge)

# ===== FLAT-FIELD ILLUMINATION LEVELING =====
# Uneven lighting and lens vignetting cause false contours on white backgrounds.
# Flat-field calibration divides subsequent frames by an empty white reference image.
FLATTEN_ILLUM = True       # False = Disable illumination leveling
FLATFIELD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flatfield.png")
FLATFIELD_BLUR = 21        # Smoothing radius for light map (px) to prevent dust transfer
FLATFIELD_MAX_GAIN = 4.0   # Maximum gain clamp to prevent noise amplification in corners
AUTO_FLATTEN = True        # Auto-estimate background if reference file is absent
AUTO_MAX_GAIN = 2.2        # Gain clamp for automatic estimation
WHITEN_BG = True           # Pull leveled background to pure white (255)
WHITEN_PCT = 92            # Luminance percentile treated as background
WHITEN_MAX_GAIN = 1.6      # Gain clamp for background whitening

# List of Bayer color demosaicing modes in OpenCV
BAYER_MODES = [
    ("BayerBG2BGR", cv2.COLOR_BayerBG2BGR),
    ("BayerGB2BGR", cv2.COLOR_BayerGB2BGR),
    ("BayerRG2BGR", cv2.COLOR_BayerRG2BGR),
    ("BayerGR2BGR", cv2.COLOR_BayerGR2BGR),  # MODE 3 DEFAULT STANDARD
    ("BayerBG2RGB", cv2.COLOR_BayerBG2RGB),
    ("BayerGB2RGB", cv2.COLOR_BayerGB2RGB),
    ("BayerRG2RGB", cv2.COLOR_BayerRG2RGB),
    ("BayerGR2RGB", cv2.COLOR_BayerGR2RGB),
]

_screen_cache = None


def screen_size():
    """Returns screen resolution (px). Falls back to 1920x1080 if unavailable."""
    global _screen_cache
    if _screen_cache is None:
        _screen_cache = (1920, 1080)
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
                if w > 0 and h > 0:
                    _screen_cache = (w, h)
            except Exception:
                pass
    return _screen_cache


def fit_display(img, scale=None, chrome_h=TRACKBAR_H):
    """Downscales image to ensure the window fits comfortably on screen."""
    h, w = img.shape[:2]
    sw, sh = screen_size()
    s = min(scale if scale is not None else UI_SCALE,
            sw * SCREEN_USE / max(1, w),
            (sh * SCREEN_USE - chrome_h) / max(1, h))
    s = max(0.05, min(s, 1.0))
    if s >= 0.999:
        return img
    return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))),
                      interpolation=cv2.INTER_AREA)


def on_exposure_change(val):
    global current_exposure_ms
    current_exposure_ms = max(1, val)


def on_gain_change(val):
    global current_gain
    current_gain = val


def on_auto_exposure_change(val):
    global auto_exposure_enabled
    auto_exposure_enabled = val


def on_color_mode_change(val):
    global color_mode_idx
    color_mode_idx = val % len(BAYER_MODES)


def on_sharpen_change(val):
    global live_sharpen_level
    live_sharpen_level = val


def imwrite_unicode(path, img):
    """Safe image write supporting Unicode/special characters in file paths on Windows."""
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(path)
    return ok


def raw_to_bgr(img, cv2_bayer_code):
    """Converts raw camera buffer (mono/Bayer, 8 or 12/16-bit) to 8-bit BGR image."""
    if img.dtype != np.uint8:
        img_8u = (img >> 4).astype(np.uint8) if img.dtype == np.uint16 else img.astype(np.uint8)
    else:
        img_8u = img

    if len(img_8u.shape) == 2:
        return cv2.cvtColor(img_8u, cv2_bayer_code)
    return img_8u.copy()


def sharpness_score(img_bgr):
    """Laplacian variance score — higher value indicates sharper focus."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def enhance_image(img_bgr):
    """
    Automated post-capture enhancement pipeline:
      1. Bilateral filtering for edge-preserving denoising.
      2. CLAHE on L channel (LAB) for local contrast enhancement.
      3. Adaptive unsharp masking proportional to initial sharpness.
    """
    score = sharpness_score(img_bgr)

    # Blurrier images receive stronger sharpening compensation
    if score < 50:
        amount = 1.6
    elif score < 150:
        amount = 1.1
    elif score < 400:
        amount = 0.8
    else:
        amount = 0.5

    # 1. Edge-preserving denoising
    den = cv2.bilateralFilter(img_bgr, 7, 50, 50)

    # 2. Local contrast enhancement on luminance channel
    lab = cv2.cvtColor(den, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(8, 8)).apply(l)
    den = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    # 3. Unsharp masking: original + (original - blurred) * amount
    blur = cv2.GaussianBlur(den, (0, 0), UNSHARP_SIGMA)
    sharp = cv2.addWeighted(den, 1.0 + amount, blur, -amount, 0)

    return sharp, score, amount


# ============================================================
# FLAT-FIELD ILLUMINATION CORRECTION
# ============================================================
_ff_gain = None            # Gain map from reference file (float32, BGR)
_ff_tried = False          # File read flag (avoids redundant disk I/O)
_ff_resized = {}           # (h, w) -> Resized gain map cache


def _gain_from_reference(ref_bgr):
    """Generates per-channel gain map from an empty white reference image."""
    ref = cv2.GaussianBlur(ref_bgr.astype(np.float32), (0, 0), FLATFIELD_BLUR)
    ref = np.maximum(ref, 1.0)
    target = float(np.percentile(ref, 98))     # Brightest region of background = white reference
    return np.clip(target / ref, 0.2, FLATFIELD_MAX_GAIN).astype(np.float32)


def load_flatfield():
    """Loads gain map from reference file (cached in memory). Returns None if absent."""
    global _ff_gain, _ff_tried
    if not _ff_tried:
        _ff_tried = True
        if os.path.exists(FLATFIELD_PATH):
            try:
                ref = cv2.imdecode(np.fromfile(FLATFIELD_PATH, np.uint8), cv2.IMREAD_COLOR)
                if ref is not None:
                    _ff_gain = _gain_from_reference(ref)
            except Exception as e:
                print(f"[Notice] Could not read {FLATFIELD_PATH}: {e}")
    return _ff_gain


def _reset_flatfield_cache():
    global _ff_gain, _ff_tried, _ff_resized
    _ff_gain, _ff_tried, _ff_resized = None, False, {}


def apply_flatfield(img_bgr):
    """Applies reference flat-field gain map. Returns None if reference is missing."""
    gain = load_flatfield()
    if gain is None:
        return None
    h, w = img_bgr.shape[:2]
    if gain.shape[:2] != (h, w):
        g = _ff_resized.get((h, w))
        if g is None:
            g = cv2.resize(gain, (w, h), interpolation=cv2.INTER_LINEAR)
            _ff_resized[(h, w)] = g
        gain = g
    return np.clip(img_bgr.astype(np.float32) * gain, 0, 255).astype(np.uint8)


def _estimate_background(img, work=512, frac=3):
    """Estimates background illumination by morphological closing over objects."""
    h, w = img.shape[:2]
    s = min(1.0, float(work) / max(h, w))
    small = (cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))),
                        interpolation=cv2.INTER_AREA) if s < 1.0 else img)

    k = max(15, (min(small.shape[:2]) // max(1, frac)) | 1)
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, se)
    bg = cv2.GaussianBlur(bg.astype(np.float32), (0, 0), k / 3.0)
    return cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)


def auto_flatten(img_bgr):
    """Estimates background directly from current frame and applies leveling."""
    bg = _estimate_background(img_bgr)
    target = float(np.percentile(bg, 98))
    gain = np.clip(target / np.maximum(bg, 1.0), 0.2, AUTO_MAX_GAIN)
    return np.clip(img_bgr.astype(np.float32) * gain, 0, 255).astype(np.uint8)


def whiten_background(img_bgr):
    """Scales background level to pure white (255)."""
    if not WHITEN_BG:
        return img_bgr
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    p = float(np.percentile(gray, WHITEN_PCT))
    if p < 1.0:
        return img_bgr
    s = min(WHITEN_MAX_GAIN, 250.0 / p)
    if s <= 1.01:
        return img_bgr
    return np.clip(img_bgr.astype(np.float32) * s, 0, 255).astype(np.uint8)


def flatten_illumination(img_bgr):
    """Levels background illumination. Returns (image, method_name)."""
    if not FLATTEN_ILLUM:
        return img_bgr, "disabled"
    out = apply_flatfield(img_bgr)
    mode = "reference file"
    if out is None:
        if not AUTO_FLATTEN:
            return img_bgr, "disabled"
        out = auto_flatten(img_bgr)
        mode = "auto estimation"
    return whiten_background(out), mode


def illumination_spread(img_bgr):
    """Background illumination variance (%): 0 = perfectly uniform."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    bg = _estimate_background(gray, work=384, frac=2)
    lo, hi = float(np.percentile(bg, 2)), float(np.percentile(bg, 98))
    if hi < 1.0:
        return 100.0
    return (hi - lo) / hi * 100.0


def capture_flatfield(camera, pylon, base_img, cv2_bayer_code, n_frames=8):
    """Captures an EMPTY WHITE BACKGROUND (without objects) as illumination reference."""
    frames = [base_img.astype(np.float32)]
    for _ in range(max(0, n_frames - 1)):
        try:
            grab = camera.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
        except Exception:
            break
        try:
            if grab.GrabSucceeded():
                f = raw_to_bgr(grab.Array, cv2_bayer_code)
                if f.shape == base_img.shape:
                    frames.append(f.astype(np.float32))
        finally:
            grab.Release()

    ref = np.clip(np.mean(frames, axis=0), 0, 255).astype(np.uint8)
    before = illumination_spread(ref)

    if not imwrite_unicode(FLATFIELD_PATH, ref):
        print("[ERROR] Failed to save flat-field reference image.")
        return False

    _reset_flatfield_cache()
    after = illumination_spread(flatten_illumination(ref)[0])

    print("--------------------------------------------------")
    print(f"[WHITE BACKGROUND] Merged {len(frames)} frames, saved: {FLATFIELD_PATH}")
    print(f" -> Background illumination variance: {before:.1f}%  =>  {after:.1f}% after leveling")
    if before > 25:
        print("(variance > 25% — adjust physical lights for better uniformity)")
    print(" -> All future captures will be leveled using this reference background.")
    print("--------------------------------------------------")
    return True


# ============================================================
# CARTOONIZATION
# ============================================================
def _palette(img_bgr, k):
    """Finds k representative color centers using k-means."""
    Z = img_bgr.reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, _, centers = cv2.kmeans(Z, max(2, k), None, crit, 3, cv2.KMEANS_PP_CENTERS)
    return centers


def _snap_to_palette(img_bgr, centers):
    """Maps every pixel to the nearest palette color."""
    f = img_bgr.astype(np.float32)
    best_d = None
    best_i = np.zeros(f.shape[:2], np.uint8)
    for i, c in enumerate(centers):
        d = ((f - c) ** 2).sum(axis=2)
        if best_d is None:
            best_d = d
        else:
            m = d < best_d
            best_d[m] = d[m]
            best_i[m] = i
    return centers[best_i].astype(np.uint8)


def _label_map(img_bgr, centers):
    """Generates discrete label map indexing the closest palette center."""
    f = img_bgr.astype(np.float32)
    best_d = None
    lbl = np.zeros(f.shape[:2], np.uint8)
    for i, c in enumerate(centers):
        d = ((f - c) ** 2).sum(axis=2)
        if best_d is None:
            best_d = d
        else:
            m = d < best_d
            best_d[m] = d[m]
            lbl[m] = i
    return lbl


def _merge_small_regions(lbl, min_area):
    """Merges tiny color fragments into surrounding major regions."""
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
        filled = out.copy()
        filled[holes] = 255
        grown = cv2.dilate(np.where(holes, 0, out + 1).astype(np.uint8),
                           np.ones((5, 5), np.uint8))
        out[holes] = np.maximum(grown[holes].astype(np.int16) - 1, 0).astype(np.uint8)
    return out


def _cartoon_parts(img_bgr):
    """Core cartoonization -> (palette, label_map, edge_mask)."""
    h, w = img_bgr.shape[:2]
    s = min(1.0, float(CARTOON_WORK) / max(h, w))
    small = (cv2.resize(img_bgr, (max(1, int(w * s)), max(1, int(h * s))),
                        interpolation=cv2.INTER_AREA) if s < 1.0 else img_bgr)

    # 1) Edge-preserving smoothing
    for _ in range(max(1, CARTOON_SMOOTH)):
        small = cv2.bilateralFilter(small, 9, 75, 75)

    # 2) Color clustering
    centers = _palette(small, CARTOON_LEVELS)
    base = cv2.bilateralFilter(img_bgr, 9, 60, 60) if s < 1.0 else small
    lbl = _label_map(base, centers)

    # 3) Clean label map
    if CARTOON_CLEAN >= 3:
        lbl = cv2.medianBlur(lbl, CARTOON_CLEAN | 1)
    lbl = _merge_small_regions(lbl, CARTOON_MIN_AREA)

    # 4) Boundary edges between color clusters
    ink = (cv2.morphologyEx(lbl, cv2.MORPH_GRADIENT,
                            np.ones((3, 3), np.uint8)) > 0).astype(np.uint8) * 255
    if CARTOON_EDGE_THICK > 1:
        ink = cv2.dilate(ink, np.ones((CARTOON_EDGE_THICK,) * 2, np.uint8))
    return centers, lbl, ink


def cartoonize(img_bgr):
    """Color cartoon: flat color regions + dark boundary outlines."""
    centers, lbl, ink = _cartoon_parts(img_bgr)
    out = centers[lbl].astype(np.uint8)
    out[ink > 0] = (0, 0, 0)
    return out


def line_art(img_bgr):
    """Line art only: white background with crisp black outlines for pen plotters."""
    _, _, ink = _cartoon_parts(img_bgr)
    out = np.full(img_bgr.shape, 255, np.uint8)
    out[ink > 0] = (0, 0, 0)
    return out


def _fill_holes(mask):
    """Fills internal holes inside white regions."""
    h, w = mask.shape
    flood = mask.copy()
    tmp = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, tmp, (0, 0), 255)
    return cv2.bitwise_or(mask, cv2.bitwise_not(flood))


def _keep_main_blobs(mask, min_area):
    """Retains major blobs, prioritizing objects centered within the frame."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (mask > 0).astype(np.uint8), connectivity=8)
    if n <= 1:
        return mask
    h, w = mask.shape
    big, inner = [], []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_area:
            continue
        big.append(i)
        x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if x > 0 and y > 0 and x + bw < w and y + bh < h:
            inner.append(i)
    keep = inner if inner else big
    if not keep:
        return np.zeros_like(mask)
    return np.where(np.isin(labels, keep), 255, 0).astype(np.uint8)


def _refine_grabcut(img_bgr, mask, iters=3, max_dim=480):
    """Refines object boundaries using GrabCut initialized from initial mask."""
    h, w = mask.shape
    scale = min(1.0, float(max_dim) / max(h, w))
    if scale < 1.0:
        small = cv2.resize(img_bgr, (max(1, int(w * scale)), max(1, int(h * scale))),
                           interpolation=cv2.INTER_AREA)
        m = cv2.resize(mask, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    else:
        small, m = img_bgr, mask

    gc = np.full(m.shape, cv2.GC_PR_BGD, np.uint8)
    gc[m > 0] = cv2.GC_PR_FGD
    sure = cv2.erode(m, np.ones((5, 5), np.uint8))
    gc[sure > 0] = cv2.GC_FGD
    gc[:2, :] = gc[-2:, :] = cv2.GC_BGD      # Frame borders are guaranteed background
    gc[:, :2] = gc[:, -2:] = cv2.GC_BGD

    if not (gc == cv2.GC_FGD).any():
        return mask
    try:
        cv2.grabCut(small, gc, None, np.zeros((1, 65), np.float64),
                    np.zeros((1, 65), np.float64), iters, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return mask
    out = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    if cv2.countNonZero(out) == 0:
        return mask
    if scale < 1.0:
        out = cv2.resize(out, (w, h), interpolation=cv2.INTER_NEAREST)
    return out


def illum_field(L, seed, work=512):
    """Constructs light field including cast shadows while masking object regions."""
    h, w = L.shape[:2]
    s = min(1.0, float(work) / max(h, w))
    if s < 1.0:
        nw, nh = max(1, int(w * s)), max(1, int(h * s))
        Ls = cv2.resize(L, (nw, nh), interpolation=cv2.INTER_AREA)
        ms = cv2.resize(seed, (nw, nh), interpolation=cv2.INTER_NEAREST)
    else:
        Ls, ms = L, seed

    ms = cv2.dilate(ms, np.ones((7, 7), np.uint8))
    if cv2.countNonZero(ms) and cv2.countNonZero(255 - ms):
        Ls = cv2.inpaint(Ls, ms, 7, cv2.INPAINT_TELEA)
    field = cv2.GaussianBlur(Ls.astype(np.float32), (0, 0), SHADOW_SMOOTH)
    if s < 1.0:
        field = cv2.resize(field, (w, h), interpolation=cv2.INTER_LINEAR)
    return field


def object_mask(img_bgr):
    """Generates binary mask for OBJECT (255) / background (0), suppressing cast shadows."""
    h, w = img_bgr.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(img_bgr, (0, 0), 1.2), cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    # 1. Color divergence from background sampled at image borders
    band = max(4, int(min(h, w) * 0.04))
    border = np.zeros((h, w), bool)
    border[:band, :] = True
    border[-band:, :] = True
    border[:, :band] = True
    border[:, -band:] = True
    a_bg = float(np.median(A[border]))
    b_bg = float(np.median(B[border]))
    chroma = np.hypot(A.astype(np.float32) - a_bg, B.astype(np.float32) - b_bg)
    mask_color = chroma > OBJ_CHROMA_THR

    # 2. Luminance deficit relative to background after leveling
    k = max(31, (min(h, w) // 6) | 1)
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bg = cv2.morphologyEx(L, cv2.MORPH_CLOSE, se)
    bg = cv2.GaussianBlur(bg, (0, 0), k / 6.0)
    ratio = L.astype(np.float32) / np.maximum(bg.astype(np.float32), 1.0)

    if REMOVE_SHADOW:
        seed = ((mask_color | (ratio < SHADOW_SEED_RATIO)).astype(np.uint8)) * 255
        seed = cv2.morphologyEx(seed, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        field = illum_field(L, seed)
        ratio = L.astype(np.float32) / np.maximum(field, 1.0)

    mask_dark = ratio < OBJ_DARK_RATIO
    mask = ((mask_color | mask_dark).astype(np.uint8)) * 255

    # 3. Cleanup: bridge gaps, remove speckles, fill holes, retain main blob
    k3 = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k3, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k3, iterations=1)
    mask = _keep_main_blobs(mask, OBJ_MIN_AREA_RATIO * h * w)
    mask = _fill_holes(mask)

    if OBJ_USE_GRABCUT and cv2.countNonZero(mask) > 0:
        mask = _refine_grabcut(img_bgr, mask)
        mask = _fill_holes(_keep_main_blobs(mask, OBJ_MIN_AREA_RATIO * h * w))
    return mask


def extract_object_on_white(img_bgr, mask_src=None):
    """Isolates object and pastes it onto a pure WHITE background."""
    h, w = img_bgr.shape[:2]
    src = img_bgr if mask_src is None else mask_src
    if src.shape[:2] != (h, w):
        src = cv2.resize(src, (w, h), interpolation=cv2.INTER_AREA)

    mask = object_mask(src)
    coverage = cv2.countNonZero(mask) / float(h * w)

    if coverage < 0.0005 or coverage > 0.9:
        return None, mask, coverage

    alpha = mask.astype(np.float32) / 255.0
    if OBJ_FEATHER > 0:
        alpha = cv2.GaussianBlur(alpha, (0, 0), OBJ_FEATHER)
    alpha3 = cv2.merge([alpha, alpha, alpha])
    out = (img_bgr.astype(np.float32) * alpha3 + 255.0 * (1.0 - alpha3))
    out = np.clip(out, 0, 255).astype(np.uint8)

    if OBJ_CROP_MARGIN >= 0:
        ys, xs = np.nonzero(mask)
        m = int(OBJ_CROP_MARGIN)
        x0, x1 = max(0, xs.min() - m), min(w, xs.max() + 1 + m)
        y0, y1 = max(0, ys.min() - m), min(h, ys.max() + 1 + m)
        out = out[y0:y1, x0:x1]

    return out, mask, coverage


def capture_and_save(camera, pylon, base_img, cv2_bayer_code):
    """
    Captures clean image (without overlay), averages frames for denoising,
    sharpens automatically, and isolates object onto pure white background.
    Saves: _raw (original), _sharp (enhanced), _object (object on white).
    """
    os.makedirs(CAPTURE_DIR, exist_ok=True)

    frames = [base_img.astype(np.float32)]
    for _ in range(max(0, CAPTURE_AVG_FRAMES - 1)):
        try:
            grab = camera.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
        except Exception:
            break
        try:
            if grab.GrabSucceeded():
                f = raw_to_bgr(grab.Array, cv2_bayer_code)
                if f.shape == base_img.shape:
                    frames.append(f.astype(np.float32))
        finally:
            grab.Release()

    raw_img = np.clip(np.mean(frames, axis=0), 0, 255).astype(np.uint8)

    spread_before = illumination_spread(raw_img)
    flat_img, flat_mode = flatten_illumination(raw_img)
    spread_after = illumination_spread(flat_img)

    sharp_img, score_before, amount = enhance_image(flat_img)
    score_after = sharpness_score(sharp_img)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = os.path.join(CAPTURE_DIR, f"capture_{stamp}_raw.png")
    sharp_path = os.path.join(CAPTURE_DIR, f"capture_{stamp}_sharp.png")

    imwrite_unicode(raw_path, raw_img)
    imwrite_unicode(sharp_path, sharp_img)

    print("--------------------------------------------------")
    print(f"[CAPTURE] Merged {len(frames)} frames for noise reduction.")
    print(f" -> Background leveling ({flat_mode}): variance "
          f"{spread_before:.1f}% => {spread_after:.1f}%")
    if flat_mode == "auto estimation":
        print("(press 'f' when frame has EMPTY WHITE BACKGROUND for accurate calibration)")
    print(f" -> Sharpness: {score_before:.1f} => {score_after:.1f} (sharpen strength: {amount:.1f})")
    print(f" -> Raw image  : {raw_path}")
    print(f" -> Sharp image: {sharp_path}")

    result_path = sharp_path
    show_img = sharp_img
    if EXTRACT_OBJECT:
        obj_img, mask, coverage = extract_object_on_white(sharp_img, mask_src=flat_img)
        if obj_img is None:
            print(f" -> [!] FAILED to extract object ({coverage*100:.2f}% of frame).")
            print("If object is too pale, DECREASE OBJ_CHROMA_THR; if background is captured, INCREASE.")
        else:
            obj_path = os.path.join(CAPTURE_DIR, f"capture_{stamp}_object.png")
            imwrite_unicode(obj_path, obj_img)
            oh, ow = obj_img.shape[:2]
            print(f" -> Object/white bg: {obj_path}")
            print(f"(object covers {coverage*100:.1f}% of frame, cropped to {ow}x{oh} px)")
            result_path = obj_path
            show_img = obj_img

    print(f" -> Use convert_3d_to_2d.py to convert 3D → 2D before")
    print(f"generating G-Code in image_to_gcode.py.")
    print("--------------------------------------------------")

    h, w = show_img.shape[:2]
    scale = UI_SCALE if max(h, w) * UI_SCALE > 240 else min(1.0, 480.0 / max(h, w))
    cv2.imshow("Captured Image (Object on White Background)",
               fit_display(show_img, scale, chrome_h=60))

    return result_path


def main():
    global current_exposure_ms, current_gain, auto_exposure_enabled, color_mode_idx
    print("==================================================")
    print("BASLER GIGE CAMERA - STREAMING & CTRLX PIPELINE")
    print("==================================================")

    try:
        from pypylon import pylon
    except ImportError:
        print("[ERROR] 'pypylon' library is not installed. Please run: pip install pypylon")
        return

    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()

    if not devices:
        print("[ERROR] No Basler GigE camera found on the network!")
        return

    dev_info = devices[0]
    print(f"[CONNECT] Camera found: {dev_info.GetFriendlyName()} ({dev_info.GetIpAddress()})\n")

    try:
        camera = pylon.InstantCamera(tl_factory.CreateDevice(dev_info))
        camera.Open()

        # Optimize GigE network packet size
        try:
            if hasattr(camera, 'GevSCPSPacketSize'):
                camera.GevSCPSPacketSize.SetValue(1440)
        except Exception:
            pass

        # Disable auto exposure for consistent physical lighting
        try:
            if hasattr(camera, 'ExposureAuto'):
                camera.ExposureAuto.SetValue("Off")
            if hasattr(camera, 'GainAuto'):
                camera.GainAuto.SetValue("Off")
            print(" -> [MANUAL MODE] Auto Exposure & Gain disabled (direct physical lighting adjustment).")
        except Exception as e:
            print(f" [Exposure notice]: {e}")

        # Safe white balance
        try:
            if hasattr(camera, 'BalanceWhiteAuto'):
                camera.BalanceWhiteAuto.SetValue("Once")
        except Exception:
            pass

        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

        window_name = "Basler GigE Camera Stream"
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

        cv2.createTrackbar("Auto Exposure (1=ON, 0=OFF)", window_name,
                           auto_exposure_enabled, 1, on_auto_exposure_change)
        cv2.createTrackbar("Exposure (ms)", window_name,
                           current_exposure_ms, 100, on_exposure_change)
        cv2.createTrackbar("Gain (dB)", window_name,
                           current_gain, 24, on_gain_change)
        cv2.createTrackbar("Color Mode (0-7)", window_name,
                           color_mode_idx, 7, on_color_mode_change)

        try:
            cv2.moveWindow(window_name, 0, 0)
        except Exception:
            pass

        print("[INSTRUCTIONS]:")
        print(" - UI automatically scales to fit screen.")
        print(" - RUN ONCE: place an EMPTY WHITE BACKGROUND in frame, then press 'f'")
        print("   to calibrate background illumination. Only recalibrate when changing lights/lens/distance.")
        print(" - Press 'n' to toggle flat-field preview on live stream.")
        print(" - Adjust 'Color Mode (0-7)' slider or press 'c' to cycle color modes.")
        print(" - Press 's' or SPACEBAR to CAPTURE IMAGE.")
        print("   Post-capture: average frames -> sharpen -> EXTRACT OBJECT")
        print("   onto WHITE BACKGROUND (*_object.png) to eliminate shadows for G-Code.")
        print(f"   Images saved to directory: {CAPTURE_DIR}")
        print(" - Press 'q' or 'ESC' to exit.\n")

        last_auto_state = -1
        last_capture_time = 0.0
        last_flat_time = 0.0
        preview_flat = load_flatfield() is not None
        last_exposure_ms = None
        last_gain = None
        exp_readback = None
        last_exp_read = 0.0
        timeout_count = 0

        while camera.IsGrabbing():
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:   # 'q' or ESC
                break
            elif key == ord('n'):
                preview_flat = not preview_flat
                print(f"[PREVIEW] Flat-field correction on live frame: "
                      f"{'ON' if preview_flat else 'OFF'}")

            if auto_exposure_enabled != last_auto_state:
                last_auto_state = auto_exposure_enabled
                last_exposure_ms = None
                last_gain = None
                exp_readback = None
                if auto_exposure_enabled == 1:
                    try:
                        camera.ExposureAuto.SetValue("Continuous")
                        camera.GainAuto.SetValue("Continuous")
                    except Exception:
                        pass
                else:
                    try:
                        camera.ExposureAuto.SetValue("Off")
                        camera.GainAuto.SetValue("Off")
                    except Exception:
                        pass

            if auto_exposure_enabled == 0:
                if current_exposure_ms != last_exposure_ms:
                    last_exposure_ms = current_exposure_ms
                    try:
                        us_val = int(current_exposure_ms * 1000)
                        if hasattr(camera, 'ExposureTimeAbs'):
                            camera.ExposureTimeAbs.SetValue(float(us_val))
                        elif hasattr(camera, 'ExposureTimeRaw'):
                            camera.ExposureTimeRaw.SetValue(us_val)
                        elif hasattr(camera, 'ExposureTime'):
                            camera.ExposureTime.SetValue(float(us_val))
                    except Exception:
                        pass
                    exp_readback = None

                if current_gain != last_gain:
                    last_gain = current_gain
                    try:
                        if hasattr(camera, 'GainRaw'):
                            camera.GainRaw.SetValue(int(current_gain))
                        elif hasattr(camera, 'Gain'):
                            camera.Gain.SetValue(float(current_gain))
                    except Exception:
                        pass
            else:
                if time.time() - last_exp_read > 0.5:
                    last_exp_read = time.time()
                    exp_readback = None

            try:
                grabResult = camera.RetrieveResult(500, pylon.TimeoutHandling_Return)
            except Exception as e:
                print(f"[GRAB ERROR]: {e}")
                timeout_count += 1
                if timeout_count > 20:
                    print("[ERROR] Camera connection lost — attempting to reconnect...")
                    try:
                        camera.StopGrabbing()
                        time.sleep(1)
                        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                        timeout_count = 0
                        print("[OK] Camera reconnected.")
                    except Exception as e2:
                        print(f"[ERROR] Could not reconnect: {e2}")
                        break
                continue

            if not grabResult.IsValid() or not grabResult.GrabSucceeded():
                timeout_count += 1
                if grabResult.IsValid():
                    grabResult.Release()
                if timeout_count == 1 or timeout_count % 10 == 0:
                    print(f"[WAIT] Waiting for camera frame... (attempt {timeout_count})")
                if timeout_count > 20:
                    print("[WARNING] Camera not sending frames — attempting to reconnect...")
                    try:
                        camera.StopGrabbing()
                        time.sleep(1)
                        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                        timeout_count = 0
                        print("[OK] Stream restarted.")
                    except Exception as e:
                        print(f"[ERROR] Stream reset failed: {e}")
                        break
                continue

            timeout_count = 0

            try:
                mode_name, cv2_bayer_code = BAYER_MODES[color_mode_idx]
                img_bgr = raw_to_bgr(grabResult.Array, cv2_bayer_code)

                view = fit_display(img_bgr)
                if preview_flat:
                    view = flatten_illumination(view)[0]

                if exp_readback is None:
                    exp_readback = float(current_exposure_ms)
                    try:
                        if hasattr(camera, 'ExposureTimeAbs'):
                            exp_readback = camera.ExposureTimeAbs.GetValue() / 1000.0
                        elif hasattr(camera, 'ExposureTime'):
                            exp_readback = camera.ExposureTime.GetValue() / 1000.0
                    except Exception:
                        pass
                exp_val = exp_readback

                if load_flatfield() is not None:
                    flat_txt = "FLAT: calibrated" + (" [preview]" if preview_flat else "")
                    flat_col = (0, 255, 0)
                else:
                    flat_txt = "FLAT: not calibrated - press 'f' on EMPTY background"
                    flat_col = (0, 200, 255)

                status_text = f"Exp: {exp_val:.1f}ms | Gain: {current_gain} | Mode [{color_mode_idx}]: {mode_name}"

                cv2.putText(view, status_text, (10, 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
                cv2.putText(view, flat_txt, (10, 44),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, flat_col, 1, cv2.LINE_AA)

                if time.time() - last_capture_time < 2.0:
                    cv2.putText(view, "CAPTURED + SHARPENED!", (10, 70),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
                if time.time() - last_flat_time < 2.0:
                    cv2.putText(view, "CALIBRATED WHITE BACKGROUND!", (10, 70),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

                cv2.imshow(window_name, view)

                if key == ord('c'):
                    color_mode_idx = (color_mode_idx + 1) % len(BAYER_MODES)
                    cv2.setTrackbarPos("Color Mode (0-7)", window_name, color_mode_idx)
                elif key == ord('s') or key == 32:  # 's' or SPACE = capture
                    grabResult.Release()
                    grabResult = None
                    try:
                        capture_and_save(camera, pylon, img_bgr, cv2_bayer_code)
                        last_capture_time = time.time()
                    except Exception as e:
                        print(f"[CAPTURE ERROR]: {e}")
                elif key == ord('f'):   # Calibrate background (frame must be EMPTY)
                    grabResult.Release()
                    grabResult = None
                    try:
                        if capture_flatfield(camera, pylon, img_bgr, cv2_bayer_code):
                            last_flat_time = time.time()
                            preview_flat = True
                    except Exception as e:
                        print(f"[CALIBRATION ERROR]: {e}")

            except Exception as e:
                print(f"[FRAME PROCESSING ERROR]: {e}")

            if grabResult is not None:
                grabResult.Release()

        camera.Close()
        cv2.destroyAllWindows()
        print("Closed camera connection safely.")

    except Exception as e:
        print(f"[ERROR]: {e}")


if __name__ == "__main__":
    main()
