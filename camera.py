# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os
import sys
import time
from datetime import datetime

# Thiết lập UTF-8 stdout trên Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Biến toàn cục lưu cài đặt
UI_SCALE = 0.5             # TỶ LỆ KHUNG HIỂN THỊ UI (Thay đổi ở đây: 0.3 = 30%, 0.5 = 50%, 0.7 = 70%)
                           # Đây là mức TỐI ĐA — fit_display() tự thu nhỏ thêm
                           # nếu cửa sổ vượt ra ngoài màn hình.
SCREEN_USE = 0.85          # cửa sổ chỉ chiếm tối đa 85% màn hình
TRACKBAR_H = 190           # chiều cao 4 thanh trượt + thanh tiêu đề (px), phải trừ ra
current_exposure_ms = 42   # 42ms phơi sáng thủ công (thanh trượt tối đa 100)
current_gain = 10          # Gain (dB) (thanh trượt tối đa 24)
auto_exposure_enabled = 0  # 0 = TẮT TỰ ĐỘNG PHƠI SÁNG
color_mode_idx = 3         # Mặc định = 3 (BayerGR2BGR)
live_sharpen_level = 2     # Nấc làm nét bằng phần mềm trên luồng Live (0 = Tắt, 1-5 = Tăng độ nét kỹ thuật số)

# ===== CẤU HÌNH CHỤP ẢNH (CAPTURE) =====
CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
CAPTURE_AVG_FRAMES = 3     # Số khung hình gộp trung bình để khử nhiễu khi chụp (đặt = 1 để tắt)
CLAHE_CLIP = 2.0           # Độ mạnh tăng tương phản cục bộ
UNSHARP_SIGMA = 1.2        # Bán kính mặt nạ làm nét (px)

# ===== CẤU HÌNH TÁCH VẬT KHỎI NỀN (để cắt G-Code cho sạch) =====
# Vấn đề: chụp trên giấy trắng thì BÓNG ĐỔ quanh vật cũng tối, image_to_gcode
# cắt ngưỡng độ sáng sẽ vẽ luôn cả bóng; còn tăng đèn cho hết bóng thì vật bị
# cháy sáng, mất nét. Cách xử lý: dựa vào MÀU (bóng đổ gần như không đổi màu,
# chỉ đổi độ sáng) cộng với việc san phẳng ánh sáng nền, rồi dán vật lên nền
# TRẮNG TINH -> ảnh vào G-Code chỉ còn đúng vật.
EXTRACT_OBJECT = True      # False = tắt, chỉ lưu ảnh làm nét
OBJ_CHROMA_THR = 10.0      # Lệch màu so với nền (LAB a/b) > ngưỡng = VẬT.
                           #   Vật màu nhạt không bắt được -> GIẢM (6–8)
                           #   Bắt nhầm nền ngả vàng          -> TĂNG (14–18)
OBJ_DARK_RATIO = 0.72      # Tối hơn nền còn < 72% = VẬT (bắt vật đen/xám).
                           #   Bóng đổ bị vẽ theo -> GIẢM (0.6)
                           #   Vật tối bị bỏ sót  -> TĂNG (0.8)
OBJ_MIN_AREA_RATIO = 0.001  # Bỏ mảng nhỏ hơn 0.1% diện tích ảnh (nhiễu, vết bẩn)
OBJ_USE_GRABCUT = True     # Tinh chỉnh biên bằng GrabCut (chậm thêm ~0.5s)
OBJ_FEATHER = 1.0          # Làm mềm biên khi dán (px), 0 = cắt sắc cạnh
OBJ_CROP_MARGIN = 20       # Cắt sát vật, chừa lề (px). Đặt -1 để giữ nguyên khung

# ===== KHỬ BÓNG ĐỔ QUANH VẬT =====
# Bóng đổ là nền BỊ MỜ ĐI chứ không phải vật: nó chỉ hạ độ sáng, gần như không
# đổi sắc độ. Cách khử: dựng "trường ánh sáng" của riêng tấm ảnh đó — che vùng
# vật lại, trám chỗ che bằng nội suy từ xung quanh rồi làm mượt. Bóng biến thiên
# trơn nên nằm gọn trong trường này; đem ảnh chia cho trường thì bóng biến mất,
# chỉ còn thứ thật sự tối hơn môi trường ngay quanh nó = vật.
# Vùng vật để che lấy từ dấu hiệu MÀU (bóng không đổi màu nên không bao giờ lọt
# vào mồi) cộng với vùng tối đậm chắc chắn không phải bóng.
REMOVE_SHADOW = True       # False = tắt, quay về cách cũ
SHADOW_SEED_RATIO = 0.45   # Tối hơn 45% so với nền = chắc chắn VẬT, dùng làm mồi.
                           #   Bóng quá đậm vẫn bị vẽ -> GIẢM (0.3–0.4)
                           #   Vật xám đậm bị ăn mất  -> TĂNG (0.55–0.6)
SHADOW_SMOOTH = 9.0        # Độ mượt của trường sáng (px, đo trên ảnh thu nhỏ 512).
                           #   Bóng viền còn sót     -> TĂNG chậm (11–14)
                           #   Vật to bị coi là nền  -> GIẢM (6–7)

# ===== HOẠT HÌNH HOÁ (CARTOON) =====
# Ảnh chụp thật có chuyển sắc mượt + vân bề mặt + nhiễu cảm biến. image_to_gcode
# cắt theo ngưỡng độ sáng nên chỗ chuyển sắc từ từ biến thành hàng trăm nét vụn,
# bút nhấc lên hạ xuống liên tục mà hình vẫn rối. Hoạt hình hoá gom ảnh về vài
# MẢNG MÀU PHẲNG + NÉT VIỀN rõ ràng — đúng thứ máy vẽ nét cần.
# Nét viền lấy từ RANH GIỚI các mảng màu, KHÔNG dùng ngưỡng thích nghi trên ảnh
# xám: cách đó rắc đầy đốm nhiễu lên vùng phẳng, đo ra còn nhiều nét vụn hơn cả
# ảnh gốc. Ranh giới mảng màu thì kín và sạch sẵn.
CARTOON = True             # Tạo thêm file *_cartoon.png sau mỗi lần chụp
CARTOON_LEVELS = 6         # Số mức màu sau khi gom. Ít = phẳng/đơn giản, nhiều = giữ chi tiết
CARTOON_SMOOTH = 2         # Số lần lọc song phương (xoá vân nhưng giữ nguyên biên)
CARTOON_CLEAN = 9          # Cỡ cửa sổ dọn đốm trên bản đồ màu (số LẺ).
                           #   Còn nhiều nét vụn -> TĂNG (11–15)
                           #   Mất chi tiết nhỏ  -> GIẢM (5–7)
CARTOON_MIN_AREA = 60      # Xoá hẳn mảng màu nhỏ hơn ngần này px
CARTOON_EDGE_THICK = 1     # Độ dày nét viền (px)
CARTOON_WORK = 1000        # Cỡ ảnh khi xử lý nặng (px cạnh dài) — lớn hơn = chậm hơn

# ===== SAN PHẲNG ÁNH SÁNG NỀN (FLAT-FIELD) =====
# Vấn đề: đèn chiếu lệch + ống kính tối 4 góc (vignetting) làm tấm nền trắng chỗ
# sáng chỗ xám. image_to_gcode cắt theo ĐỘ SÁNG nên góc tối bị vẽ thành nét, còn
# vật ở vùng sáng thì mất nét.
# Cách chuẩn: chụp MỘT lần tấm nền trắng TRỐNG (phím 'f') làm bản đồ sáng, mọi
# ảnh sau đều được chia cho bản đồ đó -> nền phẳng đều, đúng cả sai lệch màu đèn.
FLATTEN_ILLUM = True       # False = tắt hẳn phần san phẳng
FLATFIELD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flatfield.png")
FLATFIELD_BLUR = 21        # Làm mượt bản đồ sáng (px) để không in nhiễu/bụi vào ảnh
FLATFIELD_MAX_GAIN = 4.0   # Chặn hệ số nhân, tránh khuếch đại nhiễu ở góc quá tối
AUTO_FLATTEN = True        # Chưa có file tham chiếu thì tự ước lượng nền từ chính ảnh
AUTO_MAX_GAIN = 2.2        # Chặn hệ số khi tự ước lượng (thấp hơn vì kém chắc chắn)
WHITEN_BG = True           # Kéo nền về trắng tinh sau khi đã san phẳng
WHITEN_PCT = 92            # Phân vị độ sáng coi là "nền" (92% ảnh là nền trắng)
WHITEN_MAX_GAIN = 1.6      # Chặn mức kéo sáng, tránh cháy mất chi tiết vật

# Danh sách các chế độ giải mã màu Bayer trong OpenCV
BAYER_MODES = [
    ("BayerBG2BGR", cv2.COLOR_BayerBG2BGR),
    ("BayerGB2BGR", cv2.COLOR_BayerGB2BGR),
    ("BayerRG2BGR", cv2.COLOR_BayerRG2BGR),
    ("BayerGR2BGR", cv2.COLOR_BayerGR2BGR),  # MODE 3 CHUẨN MẶC ĐỊNH
    ("BayerBG2RGB", cv2.COLOR_BayerBG2RGB),
    ("BayerGB2RGB", cv2.COLOR_BayerGB2RGB),
    ("BayerRG2RGB", cv2.COLOR_BayerRG2RGB),
    ("BayerGR2RGB", cv2.COLOR_BayerGR2RGB),
]

_screen_cache = None


def screen_size():
    """Cỡ màn hình (px). Không hỏi được thì tạm coi là 1920x1080."""
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
    """Thu nhỏ ảnh để cửa sổ hiển thị KHÔNG tràn ra ngoài màn hình.

    Cảm biến của Basler lớn (vài nghìn px), nhân UI_SCALE cố định vẫn có thể cao
    hơn màn hình — cộng thêm mấy thanh trượt nữa là mất luôn mép dưới. Ở đây lấy
    tỷ lệ nhỏ nhất giữa UI_SCALE và tỷ lệ vừa-màn-hình.
    """
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
    """Ghi ảnh an toàn kể cả khi đường dẫn có ký tự tiếng Việt (cv2.imwrite bị lỗi trên Windows)."""
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(path)
    return ok


def raw_to_bgr(img, cv2_bayer_code):
    """Chuyển mảng ảnh thô từ camera (mono/Bayer, 8 hoặc 12/16-bit) sang ảnh BGR 8-bit."""
    if img.dtype != np.uint8:
        img_8u = (img >> 4).astype(np.uint8) if img.dtype == np.uint16 else img.astype(np.uint8)
    else:
        img_8u = img

    if len(img_8u.shape) == 2:
        return cv2.cvtColor(img_8u, cv2_bayer_code)
    return img_8u.copy()


def sharpness_score(img_bgr):
    """Điểm độ nét (phương sai Laplacian) - càng cao càng nét."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def enhance_image(img_bgr):
    """
    Tự động làm rõ nét ảnh sau khi chụp:
      1. Lọc song phương (bilateral) khử nhiễu nhưng giữ nguyên cạnh.
      2. CLAHE trên kênh L (LAB) tăng tương phản cục bộ, làm nổi đường nét.
      3. Unsharp mask với cường độ TỰ ĐỘNG theo độ nét gốc của ảnh.
    """
    score = sharpness_score(img_bgr)

    # Ảnh càng mờ thì đẩy cường độ làm nét càng mạnh
    if score < 50:
        amount = 1.6
    elif score < 150:
        amount = 1.1
    elif score < 400:
        amount = 0.8
    else:
        amount = 0.5

    # 1. Khử nhiễu giữ cạnh
    den = cv2.bilateralFilter(img_bgr, 7, 50, 50)

    # 2. Tăng tương phản cục bộ trên kênh sáng
    lab = cv2.cvtColor(den, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(8, 8)).apply(l)
    den = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    # 3. Unsharp mask: ảnh gốc + (ảnh gốc - ảnh mờ) * amount
    blur = cv2.GaussianBlur(den, (0, 0), UNSHARP_SIGMA)
    sharp = cv2.addWeighted(den, 1.0 + amount, blur, -amount, 0)

    return sharp, score, amount


# ============================================================
# SAN PHẲNG ÁNH SÁNG NỀN
# ============================================================
_ff_gain = None            # bản đồ hệ số nhân từ file tham chiếu (float32, BGR)
_ff_tried = False          # đã thử đọc file chưa (khỏi đọc lại mỗi khung hình)
_ff_resized = {}           # (h, w) -> bản đồ đã co về cỡ đó


def _gain_from_reference(ref_bgr):
    """Từ ảnh nền trắng trống -> bản đồ hệ số nhân đưa mọi điểm về cùng độ sáng.

    Chia theo TỪNG KÊNH màu nên sửa luôn được ánh đèn ngả vàng/xanh.
    """
    ref = cv2.GaussianBlur(ref_bgr.astype(np.float32), (0, 0), FLATFIELD_BLUR)
    ref = np.maximum(ref, 1.0)
    target = float(np.percentile(ref, 98))     # chỗ sáng nhất của nền = mốc trắng
    return np.clip(target / ref, 0.2, FLATFIELD_MAX_GAIN).astype(np.float32)


def load_flatfield():
    """Nạp bản đồ sáng từ file (nạp một lần rồi nhớ luôn). None = chưa có file."""
    global _ff_gain, _ff_tried
    if not _ff_tried:
        _ff_tried = True
        if os.path.exists(FLATFIELD_PATH):
            try:
                ref = cv2.imdecode(np.fromfile(FLATFIELD_PATH, np.uint8), cv2.IMREAD_COLOR)
                if ref is not None:
                    _ff_gain = _gain_from_reference(ref)
            except Exception as e:
                print(f"[Lưu ý] Không đọc được {FLATFIELD_PATH}: {e}")
    return _ff_gain


def _reset_flatfield_cache():
    global _ff_gain, _ff_tried, _ff_resized
    _ff_gain, _ff_tried, _ff_resized = None, False, {}


def apply_flatfield(img_bgr):
    """Nhân ảnh với bản đồ sáng. None = chưa có file tham chiếu."""
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
    """Ước lượng ảnh NỀN: xoá vật đi, chỉ giữ lại độ dốc ánh sáng.

    Phép ĐÓNG cửa sổ lớn nuốt trọn mọi thứ nhỏ hơn cửa sổ (tức là vật), chừa lại
    nền. Tính trên ảnh thu nhỏ cho nhanh rồi phóng bản đồ lên — nền vốn biến
    thiên rất thoai thoải nên không mất gì. Nhận cả ảnh xám lẫn ảnh màu.

    frac: cửa sổ = cạnh ngắn / frac. Số càng NHỎ thì cửa sổ càng to, xoá được
    vật càng lớn nhưng bám độ dốc ánh sáng càng thô.
    """
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
    """Chưa có file tham chiếu: ước lượng nền ngay từ ảnh đang chụp rồi chia."""
    bg = _estimate_background(img_bgr)
    target = float(np.percentile(bg, 98))
    gain = np.clip(target / np.maximum(bg, 1.0), 0.2, AUTO_MAX_GAIN)
    return np.clip(img_bgr.astype(np.float32) * gain, 0, 255).astype(np.uint8)


def whiten_background(img_bgr):
    """Kéo nền lên TRẮNG TINH: lấy độ sáng của nền làm mốc 255.

    Sau khi san phẳng, nền đều nhưng thường còn xám (~230). image_to_gcode cắt
    ngưỡng sáng nên nền càng sát trắng thì càng ít bị vẽ nhầm.
    """
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
    """San phẳng ánh sáng nền. Trả về (ảnh, tên cách đã dùng)."""
    if not FLATTEN_ILLUM:
        return img_bgr, "tắt"
    out = apply_flatfield(img_bgr)
    mode = "file tham chiếu"
    if out is None:
        if not AUTO_FLATTEN:
            return img_bgr, "tắt"
        out = auto_flatten(img_bgr)
        mode = "tự ước lượng"
    return whiten_background(out), mode


def illumination_spread(img_bgr):
    """Mức lệch sáng của NỀN (%): 0 = phẳng lì. Dùng để báo chất lượng đèn.

    Đo trên ảnh nền đã ước lượng chứ không đo thẳng ảnh gốc — nếu không, đặt một
    vật màu đen vào khung là con số vọt lên 80% dù đèn hoàn toàn đều.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    bg = _estimate_background(gray, work=384, frac=2)   # cửa sổ to cho hết vật
    lo, hi = float(np.percentile(bg, 2)), float(np.percentile(bg, 98))
    if hi < 1.0:
        return 100.0
    return (hi - lo) / hi * 100.0


def capture_flatfield(camera, pylon, base_img, cv2_bayer_code, n_frames=8):
    """Chụp tấm NỀN TRẮNG TRỐNG (không có vật) làm bản đồ sáng tham chiếu."""
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
        print("[LỖI] Không ghi được file nền tham chiếu.")
        return False

    _reset_flatfield_cache()
    after = illumination_spread(flatten_illumination(ref)[0])

    print("--------------------------------------------------")
    print(f"[NỀN TRẮNG] Đã gộp {len(frames)} khung, lưu: {FLATFIELD_PATH}")
    print(f" -> Lệch sáng nền: {before:.1f}%  =>  {after:.1f}% sau khi san phẳng")
    if before > 25:
        print("(nền lệch hơn 25% — chỉnh đèn cho đều thì ảnh sẽ còn sạch hơn)")
    print(" -> Từ giờ mọi ảnh chụp đều được san phẳng theo tấm nền này.")
    print("--------------------------------------------------")
    return True


# ============================================================
# HOẠT HÌNH HOÁ
# ============================================================
def _palette(img_bgr, k):
    """Tìm k màu đại diện bằng k-means (chạy trên ảnh nhỏ cho nhanh)."""
    Z = img_bgr.reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, _, centers = cv2.kmeans(Z, max(2, k), None, crit, 3, cv2.KMEANS_PP_CENTERS)
    return centers


def _snap_to_palette(img_bgr, centers):
    """Ép mọi điểm ảnh về màu gần nhất trong bảng màu -> mảng màu phẳng lì."""
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
    """Chỉ số màu gần nhất cho từng điểm ảnh (bản đồ mảng màu)."""
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
    """Nuốt các mảng màu vụn vào mảng bao quanh nó.

    Mảng vài chục pixel không vẽ được bằng bút mà chỉ sinh ra nét rác, nên gán
    chúng theo nhãn của vùng lân cận đã giãn ra.
    """
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
        # Lấy nhãn lân cận: giãn ảnh nhãn đã xoá vùng vụn rồi lấp vào chỗ trống
        filled = out.copy()
        filled[holes] = 255
        grown = cv2.dilate(np.where(holes, 0, out + 1).astype(np.uint8),
                           np.ones((5, 5), np.uint8))
        out[holes] = np.maximum(grown[holes].astype(np.int16) - 1, 0).astype(np.uint8)
    return out


def _cartoon_parts(img_bgr):
    """Lõi hoạt hình hoá -> (bảng màu, bản đồ mảng màu, mặt nạ nét viền).

    Ba bước: (1) lọc song phương xoá vân bề mặt nhưng giữ nguyên biên, (2) gom
    về vài mức màu bằng k-means, (3) dọn mảng vụn rồi lấy ranh giới làm nét.
    Việc nặng làm trên ảnh thu nhỏ, bản đồ màu thì dựng ở cỡ gốc cho sắc nét.
    """
    h, w = img_bgr.shape[:2]
    s = min(1.0, float(CARTOON_WORK) / max(h, w))
    small = (cv2.resize(img_bgr, (max(1, int(w * s)), max(1, int(h * s))),
                        interpolation=cv2.INTER_AREA) if s < 1.0 else img_bgr)

    # 1) Làm phẳng mà vẫn giữ biên
    for _ in range(max(1, CARTOON_SMOOTH)):
        small = cv2.bilateralFilter(small, 9, 75, 75)

    # 2) Gom màu: lấy bảng màu ở ảnh nhỏ rồi ép cả ảnh gốc theo bảng đó, nhờ vậy
    #    mảng màu phẳng ở đúng độ phân giải gốc chứ không bị răng cưa khi phóng.
    centers = _palette(small, CARTOON_LEVELS)
    base = cv2.bilateralFilter(img_bgr, 9, 60, 60) if s < 1.0 else small
    lbl = _label_map(base, centers)

    # 3) Dọn bản đồ mảng màu: lọc trung vị xoá đốm + làm mượt biên, rồi nuốt nốt
    #    các mảng còn quá nhỏ. Đây mới là chỗ quyết định nét ra ít hay nhiều.
    if CARTOON_CLEAN >= 3:
        lbl = cv2.medianBlur(lbl, CARTOON_CLEAN | 1)
    lbl = _merge_small_regions(lbl, CARTOON_MIN_AREA)

    # 4) Nét viền = RANH GIỚI giữa các mảng màu (kín sẵn, không có đốm rác)
    ink = (cv2.morphologyEx(lbl, cv2.MORPH_GRADIENT,
                            np.ones((3, 3), np.uint8)) > 0).astype(np.uint8) * 255
    if CARTOON_EDGE_THICK > 1:
        ink = cv2.dilate(ink, np.ones((CARTOON_EDGE_THICK,) * 2, np.uint8))
    return centers, lbl, ink


def cartoonize(img_bgr):
    """Tranh hoạt hình CÓ MÀU: mảng màu phẳng + nét viền đen. Để xem/đối chiếu."""
    centers, lbl, ink = _cartoon_parts(img_bgr)
    out = centers[lbl].astype(np.uint8)
    out[ink > 0] = (0, 0, 0)
    return out


def line_art(img_bgr):
    """CHỈ CÒN NÉT: nền trắng, viền đen — đúng thứ máy vẽ một bút cần.

    Bản có màu không dùng thẳng được: image_to_gcode cắt theo ĐỘ SÁNG nên nó tô
    cả mảng màu đậm chứ không đi theo viền. Tách riêng lớp nét ra thì phương
    pháp 'line'/'contour' bám đúng từng đường một.
    """
    _, _, ink = _cartoon_parts(img_bgr)
    out = np.full(img_bgr.shape, 255, np.uint8)
    out[ink > 0] = (0, 0, 0)
    return out


def _fill_holes(mask):
    """Lấp lỗ bên trong mảng trắng (mắt, chi tiết sáng giữa vật)."""
    h, w = mask.shape
    flood = mask.copy()
    tmp = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, tmp, (0, 0), 255)      # tô nền ngoài thành trắng
    return cv2.bitwise_or(mask, cv2.bitwise_not(flood))


def _keep_main_blobs(mask, min_area):
    """Giữ các mảng đủ lớn; ưu tiên mảng KHÔNG chạm mép ảnh (vật nằm giữa khung)."""
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
    """Bám sát biên thật của vật bằng GrabCut, khởi tạo từ mặt nạ thô."""
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
    gc[:2, :] = gc[-2:, :] = cv2.GC_BGD      # viền ảnh chắc chắn là nền
    gc[:, :2] = gc[:, -2:] = cv2.GC_BGD

    if not (gc == cv2.GC_FGD).any():
        return mask                           # không đủ dữ liệu -> giữ mặt nạ cũ
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
    """Trường ánh sáng của tấm ảnh — CÓ TÍNH CẢ BÓNG ĐỔ, đã bỏ vùng vật ra.

    seed: mặt nạ vùng chắc chắn là VẬT. Chỗ đó bị che đi rồi trám lại bằng nội
    suy từ nền xung quanh, nên vật không kéo trường sáng xuống theo. Làm mượt
    vừa phải: đủ để xoá vân bề mặt nhưng vẫn bám được độ dốc của vùng nửa tối.
    """
    h, w = L.shape[:2]
    s = min(1.0, float(work) / max(h, w))
    if s < 1.0:
        nw, nh = max(1, int(w * s)), max(1, int(h * s))
        Ls = cv2.resize(L, (nw, nh), interpolation=cv2.INTER_AREA)
        ms = cv2.resize(seed, (nw, nh), interpolation=cv2.INTER_NEAREST)
    else:
        Ls, ms = L, seed

    ms = cv2.dilate(ms, np.ones((7, 7), np.uint8))   # nới ra cho hết mép vật
    if cv2.countNonZero(ms) and cv2.countNonZero(255 - ms):
        Ls = cv2.inpaint(Ls, ms, 7, cv2.INPAINT_TELEA)
    field = cv2.GaussianBlur(Ls.astype(np.float32), (0, 0), SHADOW_SMOOTH)
    if s < 1.0:
        field = cv2.resize(field, (w, h), interpolation=cv2.INTER_LINEAR)
    return field


def object_mask(img_bgr):
    """Mặt nạ VẬT (255) / nền (0), bỏ qua bóng đổ.

    Hai dấu hiệu độc lập, lấy hợp của cả hai:
      1. LỆCH MÀU so với nền — bóng đổ chỉ làm TỐI chứ gần như không đổi màu,
         nên vật có màu (dù nhạt) vẫn tách được kể cả khi đèn rọi mạnh.
      2. TỐI HƠN HẲN nền SAU KHI đã san phẳng ánh sáng — bắt vật đen/xám không
         có màu. San phẳng bằng cách chia cho ảnh nền ước lượng (phép ĐÓNG cửa
         sổ lớn), nhờ vậy vùng sáng không đều và bóng đổ thoai thoải bị triệt
         tiêu, chỉ còn thứ thật sự tối hơn môi trường quanh nó.
    """
    h, w = img_bgr.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(img_bgr, (0, 0), 1.2), cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    # --- 1) Lệch màu so với nền (lấy mẫu nền ở VIỀN ảnh) ---
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

    # --- 2) Tối hơn nền sau khi san phẳng ánh sáng ---
    k = max(31, (min(h, w) // 6) | 1)
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bg = cv2.morphologyEx(L, cv2.MORPH_CLOSE, se)      # xoá vật, giữ nền + bóng
    bg = cv2.GaussianBlur(bg, (0, 0), k / 6.0)
    ratio = L.astype(np.float32) / np.maximum(bg.astype(np.float32), 1.0)

    if REMOVE_SHADOW:
        # Dựng lại trường sáng có tính cả bóng, lấy mồi là vùng CHẮC CHẮN là vật:
        # chỗ lệch màu (bóng không đổi màu nên không lọt vào) cộng chỗ tối đậm
        # quá mức một cái bóng khuếch tán có thể gây ra.
        seed = ((mask_color | (ratio < SHADOW_SEED_RATIO)).astype(np.uint8)) * 255
        seed = cv2.morphologyEx(seed, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        field = illum_field(L, seed)
        ratio = L.astype(np.float32) / np.maximum(field, 1.0)

    mask_dark = ratio < OBJ_DARK_RATIO
    mask = ((mask_color | mask_dark).astype(np.uint8)) * 255

    # --- 3) Dọn dẹp: nối nét đứt, xoá đốm, lấp lỗ, giữ mảng chính ---
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
    """Cắt vật ra khỏi nền rồi dán lên nền TRẮNG TINH.

    mask_src: ảnh dùng để TÌM vật (nên đưa ảnh gộp khung chưa làm nét — sạch
    nhiễu hơn); vật thì vẫn được cắt từ img_bgr (ảnh đã làm nét).
    Trả về (ảnh_nền_trắng, mặt_nạ, tỉ_lệ_diện_tích) hoặc (None, mask, tỉ lệ)
    nếu không tách được.
    """
    h, w = img_bgr.shape[:2]
    src = img_bgr if mask_src is None else mask_src
    if src.shape[:2] != (h, w):
        src = cv2.resize(src, (w, h), interpolation=cv2.INTER_AREA)

    mask = object_mask(src)
    coverage = cv2.countNonZero(mask) / float(h * w)

    # Quá ít = không thấy vật; quá nhiều = bắt nhầm cả nền -> báo để chỉnh ngưỡng
    if coverage < 0.0005 or coverage > 0.9:
        return None, mask, coverage

    alpha = mask.astype(np.float32) / 255.0
    if OBJ_FEATHER > 0:
        alpha = cv2.GaussianBlur(alpha, (0, 0), OBJ_FEATHER)
    alpha3 = cv2.merge([alpha, alpha, alpha])
    out = (img_bgr.astype(np.float32) * alpha3 + 255.0 * (1.0 - alpha3))
    out = np.clip(out, 0, 255).astype(np.uint8)

    # Cắt sát vật (chừa lề) -> image_to_gcode phóng vật ra kín vùng vẽ
    if OBJ_CROP_MARGIN >= 0:
        ys, xs = np.nonzero(mask)
        m = int(OBJ_CROP_MARGIN)
        x0, x1 = max(0, xs.min() - m), min(w, xs.max() + 1 + m)
        y0, y1 = max(0, ys.min() - m), min(h, ys.max() + 1 + m)
        out = out[y0:y1, x0:x1]

    return out, mask, coverage


def capture_and_save(camera, pylon, base_img, cv2_bayer_code):
    """
    Chụp ảnh sạch (không có chữ overlay), gộp nhiều khung để khử nhiễu,
    làm nét tự động, rồi TÁCH VẬT DÁN LÊN NỀN TRẮNG để cắt G-Code cho sạch.
    Lưu 3 file: _raw (gốc), _sharp (đã làm nét), _object (vật trên nền trắng).
    """
    os.makedirs(CAPTURE_DIR, exist_ok=True)

    # Gộp trung bình nhiều khung liên tiếp -> giảm nhiễu cảm biến (cảnh phải đứng yên)
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

    # SAN PHẲNG ÁNH SÁNG trước mọi bước khác: mọi xử lý sau đều so theo độ sáng,
    # nên nền phải đều trước thì tìm vật và cắt ngưỡng mới chuẩn.
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
    print(f"[CHỤP ẢNH] Gộp {len(frames)} khung hình để khử nhiễu.")
    print(f" -> San phẳng nền ({flat_mode}): lệch sáng "
          f"{spread_before:.1f}% => {spread_after:.1f}%")
    if flat_mode == "tự ước lượng":
        print("(nhấn 'f'khi khung hình chỉ có NỀN TRẮNG TRỐNG để chuẩn cho chính xác)")
    print(f" -> Độ nét: {score_before:.1f}  =>  {score_after:.1f} (cường độ làm nét: {amount:.1f})")
    print(f" -> Ảnh gốc   : {raw_path}")
    print(f" -> Ảnh đã nét: {sharp_path}")

    # --- Tách vật khỏi nền, dán lên nền trắng (ảnh dùng để cắt G-Code) ---
    # Tìm vật trên ảnh CHƯA làm nét: CLAHE + unsharp đẩy cả nhiễu nền lên,
    # dò trên ảnh sạch cho biên chuẩn hơn. Vật thì vẫn cắt từ ảnh đã làm nét.
    result_path = sharp_path
    show_img = sharp_img
    if EXTRACT_OBJECT:
        obj_img, mask, coverage = extract_object_on_white(sharp_img, mask_src=flat_img)
        if obj_img is None:
            print(f" -> [!] KHÔNG tách được vật (chiếm {coverage*100:.2f}% khung hình).")
            print("Vật nhạt màu quá thì GIẢM OBJ_CHROMA_THR; "
                  "bắt nhầm nền thì TĂNG.")
        else:
            obj_path = os.path.join(CAPTURE_DIR, f"capture_{stamp}_object.png")
            imwrite_unicode(obj_path, obj_img)
            oh, ow = obj_img.shape[:2]
            print(f" -> Vật/nền trắng: {obj_path}")
            print(f"(vật chiếm {coverage*100:.1f}% khung, ảnh cắt ra {ow}x{oh} px)")
            result_path = obj_path
            show_img = obj_img

    print(f" -> Dùng convert_3d_to_2d.py để chuyển ảnh 3D → 2D trước khi đưa")
    print(f"vào image_to_gcode.py tạo G-Code.")
    print("--------------------------------------------------")

    # Xem trước kết quả trong cửa sổ riêng
    h, w = show_img.shape[:2]
    scale = UI_SCALE if max(h, w) * UI_SCALE > 240 else min(1.0, 480.0 / max(h, w))
    cv2.imshow("Anh da chup (vat tren nen trang)",
               fit_display(show_img, scale, chrome_h=60))

    return result_path


def main():
    global current_exposure_ms, current_gain, auto_exposure_enabled, color_mode_idx
    print("==================================================")
    print("BASLER GIGE CAMERA - STREAMING & KẾT NỐI CTRLX")
    print("==================================================")

    try:
        from pypylon import pylon
    except ImportError:
        print("[LỖI] Thư viện 'pypylon'chưa được cài đặt. Vui lòng chạy: pip install pypylon")
        return

    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()

    if not devices:
        print("[LỖI] Không tìm thấy camera Basler GigE nào trên dải mạng!")
        return

    dev_info = devices[0]
    print(f"[KẾT NỐI] Đã tìm thấy camera: {dev_info.GetFriendlyName()} ({dev_info.GetIpAddress()})\n")

    try:
        camera = pylon.InstantCamera(tl_factory.CreateDevice(dev_info))
        camera.Open()
        
        # Cấu hình gói tin mạng GigE tối ưu
        try:
            if hasattr(camera, 'GevSCPSPacketSize'):
                camera.GevSCPSPacketSize.SetValue(1440)
        except Exception:
            pass

        # TẮT TỰ ĐỘNG PHƠI SÁNG ĐỂ ÁNH SÁNG VẬT LÝ VÀ ĐÈN CHIẾU NGOÀI ĐỜI HOẠT ĐỘNG CHUẨN
        try:
            if hasattr(camera, 'ExposureAuto'):
                camera.ExposureAuto.SetValue("Off")
            if hasattr(camera, 'GainAuto'):
                camera.GainAuto.SetValue("Off")
            print(" -> [CHẾ ĐỘ THỦ CÔNG] Đã tắt Auto Exposure & Gain (Tùy chỉnh ánh sáng vật lý trực tiếp).")
        except Exception as e:
            print(f" [Lưu ý phơi sáng]: {e}")

        # Cân bằng trắng an toàn
        try:
            if hasattr(camera, 'BalanceWhiteAuto'):
                camera.BalanceWhiteAuto.SetValue("Once")
        except Exception:
            pass

        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        
        window_name = "Basler GigE Camera Stream"
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

        # Thanh trượt tinh chỉnh tinh gọn — vị trí ban đầu lấy thẳng từ các biến
        # mặc định ở đầu file, khỏi phải sửa hai nơi mà lệch nhau.
        cv2.createTrackbar("Auto Exposure (1=ON, 0=OFF)", window_name,
                           auto_exposure_enabled, 1, on_auto_exposure_change)
        cv2.createTrackbar("Exposure (ms)", window_name,
                           current_exposure_ms, 100, on_exposure_change)
        cv2.createTrackbar("Gain (dB)", window_name,
                           current_gain, 24, on_gain_change)
        cv2.createTrackbar("Color Mode (0-7)", window_name,
                           color_mode_idx, 7, on_color_mode_change)

        # Neo cửa sổ vào góc trên trái để không mở lệch ra ngoài màn hình
        try:
            cv2.moveWindow(window_name, 0, 0)
        except Exception:
            pass

        print("[HƯỚNG DẪN]:")
        print(" - Giao diện tự động thu gọn cho vừa màn hình.")
        print(" - LÀM MỘT LẦN: để khung hình chỉ có NỀN TRẮNG TRỐNG rồi nhấn 'f'")
        print("để chuẩn độ sáng nền. Chỉ cần chuẩn lại khi đổi đèn/ống kính/khoảng cách.")
        print(" - Nhấn 'n'để xem thử khung hình sau khi san phẳng.")
        print(" - Kéo thanh 'Color Mode (0-7)'hoặc nhấn 'c'để chuyển màu sắc.")
        print(" - Nhấn 's'hoặc PHÍM CÁCH để CHỤP ẢNH.")
        print("Sau khi chụp: gộp khung khử nhiễu -> làm rõ nét -> TÁCH VẬT")
        print("dán lên NỀN TRẮNG (file *_object.png) để cắt G-Code không dính bóng.")
        print(f"Ảnh được lưu vào thư mục: {CAPTURE_DIR}")
        print(" - Nhấn 'q'hoặc 'ESC'để thoát.\n")

        last_auto_state = -1
        last_capture_time = 0.0
        last_flat_time = 0.0       # lần chuẩn nền gần nhất (để nhấp nháy báo)
        preview_flat = load_flatfield() is not None   # có file chuẩn thì xem luôn
        last_exposure_ms = None    # giá trị đã ghi xuống camera lần gần nhất
        last_gain = None
        exp_readback = None        # số phơi sáng đọc về (None = cần đọc lại)
        last_exp_read = 0.0        # lần đọc gần nhất (dùng ở chế độ Auto)
        timeout_count = 0          # đếm số lần liên tiếp không nhận được frame

        while camera.IsGrabbing():
            # XỬ LÝ SỰ KIỆN CỬA SỔ TRƯỚC — tránh "Not Responding"
            # cv2.waitKey phải luôn được gọi ở mỗi vòng lặp, kể cả khi
            # camera chưa gửi frame. Không gọi → Windows coi cửa sổ đã treo.
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:   # 'q' hoặc ESC
                break
            elif key == ord('n'):
                preview_flat = not preview_flat
                print(f"[XEM THỬ] San phẳng trên khung hình live: "
                      f"{'BẬT' if preview_flat else 'TẮT'}")

            # Xử lý bật/tắt Auto Exposure linh hoạt
            if auto_exposure_enabled != last_auto_state:
                last_auto_state = auto_exposure_enabled
                # Auto vừa chỉnh lại phơi sáng/gain trong camera, nên khi quay về
                # thủ công phải GHI LẠI giá trị thanh trượt dù nó không đổi.
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

            # Nếu tắt Auto, cập nhật thông số thủ công từ thanh trượt.
            # CHỈ ghi khi giá trị THAY ĐỔI: mỗi lệnh SetValue là một lượt hỏi/đáp
            # qua mạng GigE, ghi lại mỗi khung hình sẽ làm stream giật và tụt FPS.
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
                    exp_readback = None      # buộc đọc lại số hiển thị

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
                # Chế độ Auto: camera tự đổi phơi sáng -> đọc lại số hiển thị,
                # nhưng giãn ra 0.5s một lần cho đỡ nghẽn đường truyền.
                if time.time() - last_exp_read > 0.5:
                    last_exp_read = time.time()
                    exp_readback = None

            # TIMEOUT NGẮN + KHÔNG THROW — cửa sổ không bao giờ bị treo.
            # Thay vì chờ 5 giây rồi throw exception (cửa sổ đông cứng suốt
            # thời gian chờ), dùng timeout 500ms + Return: nếu không có frame
            # thì quay lại đầu vòng lặp gọi waitKey cho cửa sổ vẫn responsive.
            try:
                grabResult = camera.RetrieveResult(500, pylon.TimeoutHandling_Return)
            except Exception as e:
                print(f"[LỖI GRAB]: {e}")
                timeout_count += 1
                if timeout_count > 20:
                    print("[LỖI] Mất kết nối camera — đang thử kết nối lại...")
                    try:
                        camera.StopGrabbing()
                        time.sleep(1)
                        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                        timeout_count = 0
                        print("[OK] Đã kết nối lại camera.")
                    except Exception as e2:
                        print(f"[LỖI] Không thể kết nối lại: {e2}")
                        break
                continue

            if not grabResult.IsValid() or not grabResult.GrabSucceeded():
                # Không nhận được frame — hiển thị thông báo chờ
                timeout_count += 1
                if grabResult.IsValid():
                    grabResult.Release()
                if timeout_count == 1 or timeout_count % 10 == 0:
                    print(f"[CHỜ] Chưa nhận được frame từ camera... "
                          f"(lần {timeout_count})")
                # Nếu timeout quá lâu (>10 giây liên tục): thử reset stream
                if timeout_count > 20:
                    print("[CẢNH BÁO] Camera không gửi frame — đang thử kết nối lại...")
                    try:
                        camera.StopGrabbing()
                        time.sleep(1)
                        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                        timeout_count = 0
                        print("[OK] Đã khởi động lại stream.")
                    except Exception as e:
                        print(f"[LỖI] Reset stream thất bại: {e}")
                        break
                continue

            # Nhận được frame thành công
            timeout_count = 0

            try:
                # Lấy chế độ giải mã màu hiện tại
                mode_name, cv2_bayer_code = BAYER_MODES[color_mode_idx]

                # Ảnh SẠCH (không chữ overlay) - dùng để chụp và lưu
                img_bgr = raw_to_bgr(grabResult.Array, cv2_bayer_code)

                # Ảnh để hiển thị: THU NHỎ TRƯỚC rồi mới vẽ chữ lên. Vẽ ở cỡ gốc
                # rồi mới thu nhỏ thì chữ bị co lại còn vài pixel, không đọc nổi.
                view = fit_display(img_bgr)
                if preview_flat:
                    view = flatten_illumination(view)[0]

                # Hiển thị thông số trên góc hình ảnh.
                # Đọc lại từ camera là một lượt hỏi/đáp qua mạng nữa -> chỉ đọc
                # khi vừa đổi thông số, còn lại dùng số đã nhớ.
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

                # Trạng thái nền: có file chuẩn hay đang phải tự đoán
                if load_flatfield() is not None:
                    flat_txt = "FLAT: da chuan" + (" [xem thu]" if preview_flat else "")
                    flat_col = (0, 255, 0)
                else:
                    flat_txt = "FLAT: chua chuan - nhan 'f' khi nen TRONG"
                    flat_col = (0, 200, 255)

                status_text = f"Exp: {exp_val:.1f}ms | Gain: {current_gain} | Mode [{color_mode_idx}]: {mode_name}"

                cv2.putText(view, status_text, (10, 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
                cv2.putText(view, flat_txt, (10, 44),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, flat_col, 1, cv2.LINE_AA)

                # Thông báo nhấp nháy 2 giây sau khi chụp xong
                if time.time() - last_capture_time < 2.0:
                    cv2.putText(view, "DA CHUP + LAM NET!", (10, 70),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
                if time.time() - last_flat_time < 2.0:
                    cv2.putText(view, "DA CHUAN NEN TRANG!", (10, 70),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

                cv2.imshow(window_name, view)

                # Phím tắt chụp ảnh và chuẩn nền (phải có frame mới xử lý được)
                if key == ord('c'):
                    color_mode_idx = (color_mode_idx + 1) % len(BAYER_MODES)
                    cv2.setTrackbarPos("Color Mode (0-7)", window_name, color_mode_idx)
                elif key == ord('s') or key == 32:  # 's' hoặc PHÍM CÁCH = chụp ảnh
                    grabResult.Release()
                    grabResult = None
                    try:
                        capture_and_save(camera, pylon, img_bgr, cv2_bayer_code)
                        last_capture_time = time.time()
                    except Exception as e:
                        print(f"[LỖI CHỤP ẢNH]: {e}")
                elif key == ord('f'):   # chuẩn nền trắng (khung hình phải TRỐNG)
                    grabResult.Release()
                    grabResult = None
                    try:
                        if capture_flatfield(camera, pylon, img_bgr, cv2_bayer_code):
                            last_flat_time = time.time()
                            preview_flat = True   # bật xem thử để thấy ngay kết quả
                    except Exception as e:
                        print(f"[LỖI CHUẨN NỀN]: {e}")

            except Exception as e:
                print(f"[LỖI XỬ LÝ FRAME]: {e}")

            if grabResult is not None:
                grabResult.Release()

        camera.Close()
        cv2.destroyAllWindows()
        print("Đã đóng kết nối camera an toàn.")

    except Exception as e:
        print(f"[LỖI]: {e}")

if __name__ == "__main__":
    main()
