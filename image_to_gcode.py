"""
Image to G-Code Converter — 3 Phương Pháp
==========================================
Chuyển đổi ảnh thành file G-Code cho máy Linear System 3 trục (X, Y, Z).

7 PHƯƠNG PHÁP VẼ:
  1. COLOR    — Tranh MÀU PHẲNG (hoạt hình, logo, vector) → ranh giới vùng màu
  2. PORTRAIT — Ảnh CHỤP NGƯỜI → nét vẽ chân dung (DoG chuẩn hoá)
  3. LINE     — Ảnh → nét đen trắng, độ dày ĐỀU (skeleton/centerline)   mặc định
  4. CONTOUR  — Đi theo đường viền vùng tối, nét dày gom về 1 đường tâm
  5. RASTER   — Tô đặc vùng tối bằng nét liên tục (zigzag / gạch / đồng mức)
  6. EDGE     — Phát hiện cạnh (Canny), vẽ theo các đường nét mảnh
  7. TEXT     — Gõ CHỮ (có dấu tiếng Việt) → nét viết tay. KHÔNG cần ảnh đầu vào

TRANH MÀU PHẲNG (COLOR): ảnh hoạt hình chuyển sang xám hay mất ranh giới —
vàng (255,255,0) ra ~226 còn nền trắng ra 255, nên mọi ngưỡng tách được nền
đều nuốt luôn viền thân; đỏ lại tối gần bằng nét đen. COLOR gom ảnh về N nhóm
màu (k-means trong không gian Lab) rồi vẽ nét ở chỗ hai pixel kề nhau thuộc
hai nhóm khác nhau — viền luôn rộng 1 px và khép kín.
Chỉnh chính: "Số nhóm màu" — thiếu nét thì tăng, rối thì giảm (4–6).

CHÂN DUNG (PORTRAIT): ảnh chụp là tông liên tục — da, tóc, nền chuyển dần chứ
không có ranh giới đen/trắng. Cắt ngưỡng thẳng ra mảng loang, Canny ra nét đứt
vụn. PORTRAIT dùng hiệu hai ảnh làm mờ (DoG) chuẩn hoá theo độ lệch chuẩn, chỉ
lấy phía TỐI của mỗi cạnh nên mỗi đường nét chỉ vẽ MỘT lần. Mảng đặc (con
ngươi, lỗ mũi) được vẽ bằng ĐƯỜNG BAO vì bút không tô đặc được.
Chỉnh chính: "Ngưỡng nét (σ)" — thiếu nét thì giảm (0.4), rối thì tăng (0.9).

NÉT ĐỀU (LINE): findContours đi VÒNG QUANH vùng tối nên nét bút dày sẽ thành 2
đường bao, nét dày/mỏng ra hình khác nhau. LINE rút mọi nét về đúng 1 pixel ở
giữa (skeleton) → bút vẽ MỘT đường, độ dày đồng nhất. Tắt bằng --no-uniform.

ĐƯỜNG VIỀN (CONTOUR): mặc định cũng rút nét dày về ĐƯỜNG TÂM 1 px trước khi
vẽ, nên một nét bút dày chỉ ra MỘT đường chứ không phải 2 đường bao chạy song
song. Vòng kín (chữ O, hình tròn) vẫn được đóng lại; nét hở thì không bị kéo
một đường thẳng từ đuôi về đầu. Muốn quay lại kiểu đi theo rìa: bỏ chọn
"Gom nét dày về 1 đường" trong GUI, hoặc dùng cờ --contour-outline.

TÔ VÙNG (RASTER): quét hàng ngang rồi nhấc bút ở cuối mỗi hàng là cách tô tệ
nhất cho máy vẽ — mỗi hàng tốn 1 lần nhấc + 1 lần hạ bút, ảnh 300 hàng mất 600
lượt chạy trục Z, lâu hơn cả thời gian vẽ và để lại chấm đậm ở mỗi chỗ hạ bút.
Ba kiểu tô ở đây đều nhắm vào việc giảm số lần nhấc bút:
  zigzag — nối cuối hàng này với đầu hàng kia thành MỘT nét liên tục, chỉ nhấc
           bút khi nhảy sang mảng rời khác (mặc định, ít nhấc bút nhất)
  hatch  — nét song song rời nhau kiểu gạch bóng bản khắc
  offset — nét chạy song song với ĐƯỜNG BAO rồi thu dần vào trong, bám hình
Thêm "Góc nét" (45° đẹp và đỡ lộ vệt hơn 0°), tô chéo 2 lớp, và vẽ đường bao
trước để cạnh mảng tô sắc thay vì lởm chởm đầu nét.

VIẾT CHỮ (TEXT): phương pháp duy nhất không có ảnh đầu vào. Chữ được dựng bằng
font TrueType của Windows (nên gõ tiếng Việt có dấu bình thường) ra một khung
ảnh có ĐÚNG tỉ lệ vùng vẽ — nhờ vậy cỡ chữ và lề khai bằng mm là ra đúng bấy
nhiêu mm trên giấy. Font TrueType là chữ ĐẶC, đi theo đường bao sẽ ra chữ rỗng
hai nét, nên mặc định chữ được skeleton hoá về đường tâm 1 px để bút đi MỘT
đường như viết tay; chọn "Viền chữ" nếu muốn chữ rỗng kiểu tiêu đề.
Dấu tiếng Việt và chấm chữ "i" là mảng đặc tí hon nên luôn được vẽ bằng đường
bao — mất dấu thì giảm "Bỏ nét ngắn hơn" hoặc tăng cỡ chữ / độ mịn.

CUNG TRÒN G2/G3: thay vì băm đường cong thành hàng trăm G1 ngắn, chương trình
khớp cung tròn qua chuỗi điểm rồi xuất một lệnh G2/G3 với I/J (I/J = vector từ
điểm đầu tới tâm cung). Máy chạy mượt, file nhỏ hơn nhiều. Tắt bằng --no-arcs.
Áp dụng cho LINE / CONTOUR / EDGE (RASTER quét hàng ngang nên không dùng).

Sử dụng:
    python image_to_gcode.py                          # Mở giao diện GUI
    python image_to_gcode.py input.png                # CLI, mặc định LINE + cung
    python image_to_gcode.py hoat_hinh.jpg color hoathinh.gcode
    python image_to_gcode.py anh_chan_dung.jpg portrait chandung.gcode
    python image_to_gcode.py input.png line out.gcode
    python image_to_gcode.py input.png line --no-arcs      # chỉ G1
    python image_to_gcode.py input.png line --no-uniform   # vẽ đường bao
    python image_to_gcode.py input.png contour --contour-outline  # contour kiểu cũ
    python image_to_gcode.py "Xin chào" text chao.gcode     # viết chữ (\n = xuống dòng)

ĐỊNH DẠNG FILE XUẤT (khớp máy đang dùng):
    N10 G90
    N20 G1 Z0 F800           ; nâng bút
    N30 G1 X50 Y100 F1500    ; di chuyển
    N40 G1 Z-10 F800         ; hạ bút
    N50 G2 X50 Y100 I50 J0 F1000
    N60 G1 Z0 F800           ; nâng bút
    N70 G1 X1 Y1 F2000       ; về vị trí đỗ
    N80 G1 Z0 F800           ; Z nghỉ khi kết thúc
  Vùng vẽ 150x150 mm · nâng bút Z0 · hạ bút Z-10 · kết thúc Z0.
  Không chú thích, không G0. Đổi ở MachineConfig hoặc trong GUI
  (" Cấu hình máy" cho Z/tốc độ, " Định dạng file" cho số dòng).

Yêu cầu:
    pip install opencv-python numpy Pillow
    (tuỳ chọn: opencv-contrib-python → skeleton hoá nhanh hơn nhiều)
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
# CẤU HÌNH MÁY
# ============================================================
class MachineConfig:
    """Cấu hình tham số máy Linear System"""

    def __init__(self):
        # Kích thước vùng làm việc (mm)
        self.work_area_x = 150.0
        self.work_area_y = 150.0

        # Chiều cao trục Z (mm) — Z LỚN = bút NÂNG, Z NHỎ = bút HẠ
        self.z_pen_up = 0.0        # nhấc bút
        self.z_pen_down = -10.0    # hạ bút xuống mặt giấy
        self.z_end = 0.0           # vị trí Z khi kết thúc chương trình

        # Tốc độ (mm/phút)
        self.feed_rate_draw = 1000
        self.feed_rate_travel = 1500
        self.feed_rate_z = 800
        self.feed_rate_return = 2000    # tốc độ về vị trí đỗ cuối chương trình

        # ---- ĐỊNH DẠNG FILE XUẤT ----
        self.line_numbers = True        # đánh số N10, N20, N30...
        self.line_number_start = 10
        self.line_number_step = 10
        self.emit_comments = False      # xuất dòng chú thích ';'
        self.use_g0 = False             # False = dùng G1 cho cả di chuyển nhanh
        self.init_codes = ["G90"]       # lệnh khởi tạo, mỗi lệnh một dòng
        self.end_codes = []             # lệnh kết thúc (vd ["M2"])
        self.park_x = 1.0               # vị trí đỗ cuối chương trình
        self.park_y = 1.0

        # Xử lý ảnh chung
        self.threshold = 128
        self.invert = True
        self.blur_size = 3

        # Contour
        self.min_contour_points = 5
        self.simplify_epsilon = 1.0
        # findContours đi VÒNG QUANH vùng tối: một nét bút dày cho ra 2 đường
        # bao (ngoài + trong) -> bút tô lại 2 lần, nét ra dày gấp đôi.
        # Bật = rút nét về ĐƯỜNG TÂM 1 px trước, mỗi nét chỉ vẽ MỘT lần.
        self.contour_centerline = True

        # ---- RASTER / TÔ VÙNG ----
        # Quét hàng ngang rồi nhấc bút cuối mỗi hàng là cách TỆ NHẤT cho máy vẽ:
        # mỗi hàng tốn 1 lần nhấc + 1 lần hạ bút, ảnh 300 hàng = 600 lần lên xuống
        # trục Z, chạy rất lâu và bút hay bị đầu/cuối nét đậm nhạt không đều.
        #   zigzag = quét rồi NỐI đầu hàng này với cuối hàng kia thành MỘT nét
        #            liên tục (bút gần như không nhấc)       mặc định
        #   hatch  = các nét song song rời nhau, kiểu gạch bóng khắc bản
        #   offset = nét chạy SONG SONG VỚI ĐƯỜNG BAO, thu dần vào trong
        #            (bám hình, đẹp nhất cho logo/mảng đặc)
        self.raster_resolution = 0.5   # mm — khoảng cách 2 nét tô = bề rộng nét bút
        self.raster_style = 'zigzag'
        self.raster_angle = 45.0       # độ — hướng nét tô (0 = ngang, 90 = dọc)
        self.raster_cross = False      # tô thêm lớp vuông góc (cross-hatch)
        self.raster_outline = True     # vẽ đường bao vùng trước khi tô cho cạnh sắc
        self.raster_supersample = 2    # phóng nội bộ raster để nét mượt hơn
        self.raster_smooth = 1         # số lượt làm mượt nhẹ polyline raster

        # Edge (Canny)
        self.canny_low = 50
        self.canny_high = 150

        # ---- LINE (nét vẽ đen trắng) ----
        # Skeleton hoá: mọi nét dày mỏng khác nhau đều rút về nét 1 px ở giữa
        # -> bút vẽ MỘT đường duy nhất, không còn "nét lớn nét nhỏ".
        # Tắt = vẽ theo đường viền (nét dày sẽ thành 2 đường bao).
        self.uniform_stroke = True
        self.line_min_length = 8.0     # px — bỏ nét vụn ngắn hơn ngưỡng này
        self.line_simplify = 0.8       # px — sai số làm gọn polyline (khi tắt cung)
        self.line_smooth = 3           # bán kính trung bình trượt khử răng cưa
        self.line_bridge_px = 2        # px — khép khe hở nhỏ trước skeleton
        self.adaptive_threshold = False  # ngưỡng thích ứng (ảnh sáng không đều)
        self.despeckle = True          # morphology OPEN xoá đốm nhiễu
        self.blob_outline = True       # mảng đặc -> vẽ đường bao thay vì skeleton

        # ---- COLOR (tranh màu phẳng: hoạt hình, logo, vector) ----
        # Gom màu về N nhóm rồi vẽ nét ở chỗ 2 pixel kề nhau thuộc 2 nhóm khác
        # nhau. Ảnh màu phẳng chuyển sang xám hay mất ranh giới (vàng ~226 và
        # trắng 255 gần nhau) -> ngưỡng độ sáng làm mất viền; so theo MÀU thì
        # ranh giới nào cũng bắt được.
        self.color_levels = 8          # số nhóm màu (k-means)
        self.color_denoise = 5         # lọc trung vị trước khi gom (0 = tắt)
        self.color_min_area = 20       # px — bỏ mảnh ranh giới vụn

        # ---- PORTRAIT (ảnh chụp người → nét vẽ) ----
        self.portrait_denoise = 40.0    # lọc song phương: làm phẳng da, giữ cạnh
        self.portrait_detail = 1.3      # σ của DoG — NHỎ = nhiều chi tiết vụn
        # Ngưỡng tính theo ĐỘ LỆCH CHUẨN của đáp ứng DoG (không phải 0..255),
        # nhờ vậy một giá trị dùng được cho mọi ảnh. THẤP = nhiều nét hơn.
        self.portrait_sensitivity = 0.6
        self.portrait_min_area = 12     # px — bỏ mảng nhiễu nhỏ hơn
        self.portrait_phi = 3.0         # độ dứt khoát của nét (chỉ ảnh xem trước)

        # ---- TEXT (viết chữ) ----
        # Phương pháp duy nhất KHÔNG cần ảnh đầu vào. Chữ được dựng ra một khung
        # có ĐÚNG tỉ lệ vùng vẽ nên px_to_mm ánh xạ 1-1: khai cỡ chữ và lề bằng
        # mm là ra đúng bấy nhiêu mm trên giấy.
        self.text_content = "Xin chào"
        self.text_font = "arial"        # tên file font trong C:\Windows\Fonts
        self.text_height = 20.0         # mm — chiều cao chữ HOA
        self.text_line_spacing = 1.35   # giãn dòng (lần chiều cao dòng của font)
        self.text_align = 'center'      # left | center | right
        self.text_margin = 10.0         # mm — lề chừa quanh vùng vẽ
        self.text_style = 'single'      # single = nét đơn (viết) | outline = viền chữ
        self.text_autofit = False       # phóng/thu chữ cho kín vùng vẽ
        self.text_render_scale = 8.0    # px mỗi mm khi dựng ảnh (cao = mượt, chậm)

        # ---- CUNG TRÒN G2/G3 (I/J) ----
        # Khớp cung tròn vào chuỗi điểm rồi xuất G2/G3 thay vì hàng loạt G1 ngắn.
        self.use_arcs = True
        self.arc_tolerance = 0.3       # mm — sai lệch tối đa cho phép khi khớp cung
        self.arc_min_points = 5        # ít điểm hơn thì để nguyên G1
        self.arc_max_radius = 500.0    # mm — bán kính lớn hơn coi như đường thẳng
        # Cung quét góc quá nhỏ thì nhiễu lấn át -> tâm/bán kính vô nghĩa.
        # Những đoạn đó để G1 thẳng cho chắc.
        self.arc_min_sweep_deg = 12.0

        # Offset
        self.offset_x = 0.0
        self.offset_y = 0.0

        # ---- ĐẶT ẢNH TRONG VÙNG VẼ ----
        # 'fit'    = phóng ảnh kín vùng vẽ rồi canh GIỮA (cách cũ, luôn ở tâm)
        # 'manual' = tự khai khung: to nhỏ và nằm đâu là do người dùng đặt
        self.place_mode = 'fit'
        self.place_x = 25.0        # mm — mép TRÁI của khung đặt ảnh
        self.place_y = 25.0        # mm — mép DƯỚI của khung (gốc 0,0 ở góc dưới-trái)
        self.place_w = 100.0       # mm — bề rộng khung
        self.place_h = 100.0       # mm — chiều cao khung
        self.place_keep_ratio = True   # giữ tỉ lệ ảnh, không kéo méo


# ============================================================
# HÀM DÙNG CHUNG
# ============================================================
def place_box(img_w, img_h, config):
    """Khung ảnh sẽ nằm trong vùng vẽ: (x_trái, y_dưới, rộng, cao) tính bằng mm.

    'fit'    — phóng kín vùng vẽ rồi canh giữa (cách cũ).
    'manual' — đúng khung người dùng đã đặt; nếu giữ tỉ lệ thì ảnh được thu vào
               cho vừa khung rồi canh giữa TRONG khung đó.
    """
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
    """Một pixel ảnh dài bao nhiêu mm trên giấy — theo khung đã đặt.

    Dùng cho mọi chỗ cần quy đổi mm ↔ px (bước nét tô, dung sai khép vòng).
    Khi kéo méo ảnh thì hai trục có tỉ lệ khác nhau; lấy cạnh NHỎ hơn để nét tô
    dày hơn yêu cầu một chút chứ không thưa ra.
    """
    _, _, aw, ah = place_box(img_w, img_h, config)
    return min(aw / img_w, ah / img_h)


def px_to_mm(px_x, px_y, img_w, img_h, config):
    """Chuyển pixel → mm, lật Y (ảnh tính từ trên xuống, máy tính từ dưới lên)."""
    ox, oy, aw, ah = place_box(img_w, img_h, config)
    mm_x = px_x * (aw / img_w) + ox + config.offset_x
    mm_y = (img_h - px_y) * (ah / img_h) + oy + config.offset_y
    return round(mm_x, 3), round(mm_y, 3)


def fmt(v):
    """Số toạ độ gọn: 50.0 -> '50', 94.7570 -> '94.757'."""
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
    """Lọc chú thích và đánh số dòng N — bước cuối cùng trước khi ghi file."""
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
        f"; Phương pháp: {method_name}",
        f"; Vùng vẽ: {config.work_area_x} x {config.work_area_y} mm",
        f"; Scale: {scale:.4f} mm/px",
        f"; Kích thước bản vẽ: {aw:.1f} x {ah:.1f} mm",
        f"; Đặt tại: X {ox:.1f} -> {ox + aw:.1f} | Y {oy:.1f} -> {oy + ah:.1f} mm"
        + ("  (tự đặt)" if getattr(config, 'place_mode', 'fit') == 'manual' else "  (canh giữa)"),
        f"; Feed vẽ: {config.feed_rate_draw} | Feed di chuyển: {config.feed_rate_travel}",
    ]
    if extra_info:
        lines.append(f"; {extra_info}")
    lines += [
        "; =============================================",
        ";  G1 = di chuyển / vẽ đường thẳng",
        ";  G2 = cung tròn THUẬN kim đồng hồ  (I/J = tâm so với điểm đầu)",
        ";  G3 = cung tròn NGƯỢC kim đồng hồ  (I/J = tâm so với điểm đầu)",
        "; =============================================",
        "",
        "; --- KHỞI TẠO ---",
    ]
    lines += list(config.init_codes)
    lines.append("")
    return lines


def gcode_footer(config, stats_lines=None):
    code = "G0" if config.use_g0 else "G1"
    lines = [
        "; --- KẾT THÚC ---",
        cmd_pen_up(config),                              # nhấc bút khỏi giấy
        f"{code} X{fmt(config.park_x)} Y{fmt(config.park_y)} "
        f"F{fmt(config.feed_rate_return)}",              # về vị trí đỗ
        f"G1 Z{fmt(config.z_end)} F{fmt(config.feed_rate_z)}",   # Z nghỉ
    ]
    lines += list(config.end_codes)
    lines.append("")
    if stats_lines:
        lines += stats_lines
    return lines


# ============================================================
# NÉT ĐỀU — SKELETON HOÁ (centerline)
# ============================================================
# Vấn đề: findContours đi VÒNG QUANH vùng tối, nên một nét bút dày sẽ thành
# 2 đường bao (ngoài + trong) và nét dày/mỏng khác nhau cho ra hình khác nhau.
# Skeleton hoá rút mọi nét về đúng 1 pixel ở giữa -> bút vẽ 1 đường, nét đều.

_NB8 = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def _zhang_suen(binary):
    """Làm mảnh Zhang-Suen thuần numpy (dự phòng khi không có opencv-contrib).

    binary: ảnh 0/255 -> trả về skeleton 0/1 (uint8).
    """
    skel = (binary > 0).astype(np.uint8)
    h, w = skel.shape
    for _ in range(200):                       # chặn trên, thực tế hội tụ sớm
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
    """Skeleton 0/1. Ưu tiên opencv-contrib (nhanh hơn nhiều), fallback numpy."""
    try:
        thin = cv2.ximgproc.thinning(binary, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
        return (thin > 0).astype(np.uint8)
    except AttributeError:
        return _zhang_suen(binary)


def trace_skeleton(skel, min_length=8.0):
    """Đi dọc skeleton 1 px -> danh sách polyline (mảng Nx2 toạ độ px (x, y)).

    Cắt nét tại điểm giao (>=3 láng giềng) để mỗi nhánh là một nét riêng.
    """
    h, w = skel.shape
    on = skel > 0

    p = np.pad(on.astype(np.uint8), 1)
    # Phân loại pixel bằng SỐ LẦN CHUYỂN 0->1 quanh vòng 8 láng giềng, KHÔNG
    # phải đếm láng giềng thô. Nét chéo dạng bậc thang có pixel 3 láng giềng
    # nhưng vẫn là điểm giữa nét — đếm thô sẽ cắt nét thành hàng chục mảnh vụn.
    #   1 = đầu mút | 2 = điểm giữa | >=3 = ngã ba thật
    ring = [p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy, dx in _NB8]
    ring.append(ring[0])
    deg = np.zeros((h, w), np.uint8)
    for k in range(8):
        deg += ((ring[k] == 0) & (ring[k + 1] == 1)).astype(np.uint8)
    # Pixel đơn độc: không có chuyển tiếp nào nhưng vẫn có thể có láng giềng
    lone = np.zeros((h, w), np.uint8)
    for r in ring[:8]:
        lone += r
    deg[(deg == 0) & (lone > 0)] = 2

    visited = np.zeros((h, w), bool)
    # Ưu tiên láng giềng 4-liên thông để đường đi bám sát nét, ít răng cưa
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
            if deg[nxt] >= 3:          # tới ngã ba -> kết thúc nét này
                break
            cy, cx = nxt
        return path

    paths = []
    # 1) xuất phát từ các đầu mút (nét hở)
    ys, xs = np.nonzero(on & (deg == 1))
    for y, x in zip(ys, xs):
        if not visited[y, x]:
            paths.append(walk(int(y), int(x)))
    # 2) phần còn lại là các vòng kín
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
# KHỚP CUNG TRÒN — xuất G2/G3 với I/J
# ============================================================
# Thay vì băm đường cong thành hàng trăm G1 ngắn ("chấm nhiều lần"), ta khớp
# cung tròn qua chuỗi điểm rồi xuất MỘT lệnh G2/G3. Máy chạy mượt hơn nhiều.

_ARC_CHECK_SAMPLES = 48   # số điểm lấy mẫu khi kiểm tra một cung/đoạn dài


def _sample_idx(n):
    """Chỉ số điểm dùng để kiểm tra — cắt chi phí O(n²) trên nét dài."""
    if n <= _ARC_CHECK_SAMPLES:
        return range(n)
    return sorted(set(np.linspace(0, n - 1, _ARC_CHECK_SAMPLES).astype(int).tolist()))


def smooth_polyline(pts, radius):
    """Trung bình trượt khử RĂNG CƯA PIXEL, giữ nguyên 2 đầu mút.

    Điểm skeleton nằm đúng tâm pixel nên lệch khỏi đường cong thật tới ~0.5 px.
    Ở tỉ lệ 0.5 mm/px thì đã là 0.25 mm — lớn hơn sai số khớp cung, khiến không
    cung nào khớp được. Làm mượt trước rồi mới khớp cung.
    """
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
    """Mọi điểm có nằm trong dải tol quanh dây cung p0->pe không?"""
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
    """Khớp đường tròn bình phương tối thiểu (Kåsa) qua TẤT CẢ điểm.

    Khớp qua đúng 3 điểm rất nhạy với nhiễu pixel: chỉ một điểm lệch là bán
    kính nhảy loạn, đường tròn bị băm thành nhiều cung khác bán kính. Khớp
    toàn bộ điểm cho tâm/bán kính ổn định hơn hẳn.

    Điểm gần thẳng hàng -> hệ suy biến -> bán kính rất lớn, sẽ bị chặn bởi
    arc_max_radius và tự động rơi về đoạn thẳng.
    """
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
    """Thử khớp 1 cung qua toàn bộ pts. Trả về ((cx,cy), r, sweep) hoặc None.

    sweep > 0 = ngược kim đồng hồ (G3), sweep < 0 = thuận kim đồng hồ (G2).
    """
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

    #  ÉP TÂM NẰM TRÊN TRUNG TRỰC DÂY CUNG.
    # G2/G3 với I/J là "thừa dữ liệu": bộ nội suy tính bán kính từ điểm ĐẦU và
    # từ điểm CUỐI rồi so sánh; lệch quá dung sai là báo lỗi arc radius
    # mismatch và dừng chương trình. Tâm khớp bình phương tối thiểu KHÔNG bảo
    # đảm hai bán kính bằng nhau, nên phải chiếu tâm lên trung trực dây cung —
    # khi đó |đầu-tâm| == |cuối-tâm| chính xác.
    x0, y0 = pts[0]
    xe, ye = pts[-1]
    dx, dy = xe - x0, ye - y0
    chord = math.hypot(dx, dy)
    if chord > 1e-9:
        mx, my = (x0 + xe) / 2.0, (y0 + ye) / 2.0
        nx, ny = -dy / chord, dx / chord          # pháp tuyến đơn vị của dây cung
        t = (cx - mx) * nx + (cy - my) * ny
        cx, cy = mx + t * nx, my + t * ny
        r = math.hypot(x0 - cx, y0 - cy)
        if r < 1e-6 or r > max_radius:
            return None

    # Mọi điểm phải nằm trên đường tròn trong sai số tol
    # (kiểm tra SAU khi chiếu tâm, để cung xuất ra chắc chắn đạt dung sai)
    for k in idx:
        x, y = pts[k]
        if abs(math.hypot(x - cx, y - cy) - r) > tol:
            return None

    # Góc phải tiến ĐỀU MỘT CHIỀU — nếu quay ngược thì đó không phải 1 cung
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
    """Chia polyline thành các đoạn thẳng / cung tròn.

    Trả về list các tuple:
        ('line', (x, y))
        ('arc',  (x, y), (cx, cy), sweep)
    """
    n = len(pts)
    segs = []
    i = 0
    tol = config.arc_tolerance
    min_pts = max(3, int(config.arc_min_points))
    min_sweep = math.radians(getattr(config, 'arc_min_sweep_deg', 0.0))
    while i < n - 1:
        # 1) Kéo dài ĐOẠN THẲNG xa nhất có thể — nếu không làm bước này thì
        #    mỗi điểm trên một nét thẳng sẽ thành một lệnh G1 riêng.
        j_line = i + 1
        j = i + 2
        while j < n and _line_fits(pts[i:j + 1], tol):
            j_line = j
            j += 1

        # 2) Kéo dài CUNG TRÒN xa nhất có thể.
        #    Cung ngắn chưa đạt góc quét tối thiểu vẫn cho đi tiếp (chưa đủ dữ
        #    liệu để kết luận), chỉ không được chọn làm kết quả.
        best_arc = None
        j = i + min_pts - 1
        while j < n:
            cand = _try_arc(pts[i:j + 1], tol, config.arc_max_radius)
            if cand is None:
                break
            if abs(cand[2]) >= min_sweep:
                best_arc = (j, cand)
            j += 1

        # 3) Chọn cái đi được xa hơn
        if best_arc is not None and best_arc[0] > j_line:
            j, (center, _r, sweep) = best_arc
            segs.append(('arc', pts[j], center, sweep))
            i = j
        else:
            segs.append(('line', pts[j_line]))
            i = j_line
    return segs


def _arc_in_bounds(sx, sy, ex, ey, ccx, ccy, sweep, config):
    """Kiểm tra cung tròn có nằm gọn trong vùng vẽ không.

    Quỹ đạo cong G2/G3 có thể vượt ra ngoài giới hạn trục dù điểm đầu và cuối
    đều nằm trong vùng vẽ. Bộ điều khiển sẽ báo lỗi 'Axis position limit
    exceeded' và dừng chương trình. Kiểm tra bằng cách lấy mẫu trên quỹ đạo
    cung: nếu có điểm nào nằm ngoài thì trả False → emit_polyline sẽ chuyển
    sang G1 cho đoạn cung này.
    """
    r = math.hypot(sx - ccx, sy - ccy)
    # Kiểm tra nhanh: hình chữ nhật bao quanh tâm ± bán kính
    # Chừa lề 0.5mm phòng sai số nội suy và quán tính
    margin = 0.5
    x_lo = -margin
    y_lo = -margin
    x_hi = config.work_area_x + config.offset_x + margin
    y_hi = config.work_area_y + config.offset_y + margin

    # Nếu hình tròn trọn vẹn nằm trong vùng thì chắc chắn cung cũng nằm trong
    if ccx - r >= x_lo and ccx + r <= x_hi and ccy - r >= y_lo and ccy + r <= y_hi:
        return True

    # Lấy mẫu dọc cung để kiểm tra sát hơn
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
    """Sinh G1/G2/G3 cho một polyline (toạ độ mm). Trả về quãng đường vẽ (mm)."""
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
            i_off = ccx - sx      # I/J = vector từ ĐIỂM ĐẦU tới TÂM cung
            j_off = ccy - sy
            #  SỬA LỖI BÁN KÍNH LỆCH SAU KHI QUANTIZE.
            # Bộ điều khiển Rexroth kiểm tra r_start == r_end từ toạ độ ĐÃ LÀM
            # TRÒN trong file G-code. fmt() làm tròn 3 chữ số nên bán kính có
            # thể lệch → lỗi "invalid center point". Tìm I/J tốt nhất trong
            # vùng ±0.001 sao cho mismatch nhỏ nhất.
            qsx = round(sx, 3); qsy = round(sy, 3)
            qex = round(x, 3);  qey = round(y, 3)
            qi  = round(i_off, 3); qj = round(j_off, 3)
            best_ij = (qi, qj)
            best_err = abs(math.hypot(qsx - (qsx + qi), qsy - (qsy + qj))
                          - math.hypot(qex - (qsx + qi), qey - (qsy + qj)))
            if best_err > 0.0001:
                # Duyệt lưới 3x3 quanh (qi, qj) với bước 0.001
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
            arc_ok = best_err < 0.0005  # dung sai Rexroth
            #  KIỂM TRA GIỚI HẠN: cung có thể vượt ra ngoài vùng vẽ dù
            # điểm đầu/cuối đều nằm trong. Nếu vượt → dùng G1 thay thế.
            actual_cx = qsx + qi
            actual_cy = qsy + qj
            if arc_ok and _arc_in_bounds(sx, sy, x, y, actual_cx, actual_cy, sweep, config):
                code = "G3" if sweep > 0 else "G2"
                lines.append(f"{code} X{fmt(x)} Y{fmt(y)} "
                             f"I{fmt(qi)} J{fmt(qj)} F{fmt(feed)}")
                dist += math.hypot(qi, qj) * abs(sweep)
            else:
                # Fallback: chia cung thành các đoạn G1 ngắn
                r = math.hypot(i_off, j_off)
                a0 = math.atan2(sy - ccy, sx - ccx)
                n_segs = max(8, int(abs(sweep) / 0.05))
                for k in range(1, n_segs + 1):
                    a = a0 + sweep * k / n_segs
                    gx = ccx + r * math.cos(a)
                    gy = ccy + r * math.sin(a)
                    if k == n_segs:
                        gx, gy = x, y   # điểm cuối chính xác
                    lines.append(f"G1 X{fmt(gx)} Y{fmt(gy)} F{fmt(feed)}")
                    dist += math.hypot(gx - sx, gy - sy)
                    sx, sy = gx, gy
                continue
        sx, sy = x, y
    return dist


def polyline_to_mm(pts_px, w, h, config):
    """Đổi mảng điểm pixel Nx2 -> list[(x_mm, y_mm)], bỏ điểm trùng liên tiếp."""
    out = []
    for px, py in np.asarray(pts_px).reshape(-1, 2):
        p = px_to_mm(float(px), float(py), w, h, config)
        if not out or p != out[-1]:
            out.append(p)
    return out


# ============================================================
# 1) CONTOUR — Đi theo đường viền
# ============================================================
def process_contour(image_path, config):
    """Xử lý ảnh → contours + preview images."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        bs = config.blur_size | 1
        gray = cv2.GaussianBlur(gray, (bs, bs), 0)
    _, binary = cv2.threshold(gray, config.threshold, 255, cv2.THRESH_BINARY)
    if config.invert:
        binary = cv2.bitwise_not(binary)

    #  GOM NÉT DÀY VỀ MỘT ĐƯỜNG.
    # findContours bám theo RÌA vùng tối, nên một nét bút dày sẽ ra 2 đường bao
    # (đi hết mép ngoài rồi vòng ngược mép trong) — máy tô lại 2 lần, nét ra
    # dày gấp đôi và hai mép hở ra. Rút về đường tâm 1 px thì mỗi nét chỉ còn
    # MỘT đường duy nhất. Mảng ĐẶC (chấm, con ngươi) vẫn lấy đường bao vì bút
    # không tô đặc được — phần này strokes_from_binary đã lo (blob_outline).
    if getattr(config, 'contour_centerline', False):
        polylines, stroke_img = strokes_from_binary(binary, config)
        # Làm gọn số điểm theo thanh "Đơn giản hóa" của CONTOUR (khi tắt cung).
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
        info = f"Contour [đường tâm 1 nét]: {len(polylines)} nét | Điểm: {total_pts}"
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

    # Preview images
    images = {'original': img.copy()}
    # Contour only
    conly = np.zeros((h, w, 3), np.uint8)
    cv2.drawContours(conly, contours, -1, (255, 255, 255), 1)
    for cnt in contours:
        cv2.circle(conly, tuple(cnt[0][0]), 3, (0, 255, 0), -1)
    images['preview'] = conly
    # Overlay
    overlay = img.copy()
    cv2.drawContours(overlay, contours, -1, (0, 255, 0), 2)
    images['overlay'] = overlay

    total_pts = sum(len(c) for c in contours)
    info = f"Contour [đường bao]: {len(contours)} | Điểm: {total_pts}"
    return contours, images, w, h, info


def optimize_contour_path(contours):
    """Nearest-neighbor sắp xếp thứ tự contour."""
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
    """Sinh G-Code từ contours (hoặc từ nét đường tâm khi bật gom 1 nét)."""
    centerline = getattr(config, 'contour_centerline', False)
    contours = optimize_contour_path(
        [np.asarray(c).reshape(-1, 1, 2) for c in contours])
    mode = "cung G2/G3" if config.use_arcs else "chỉ G1"
    kind = "đường tâm 1 nét" if centerline else "đường bao"
    lines = gcode_header(config, "CONTOUR (đường viền)", w, h,
                         f"Contours: {len(contours)} | {kind} | Nội suy: {mode}")
    # Nét đường tâm có cả vòng KÍN lẫn nét HỞ. Đóng vòng vô điều kiện sẽ kéo một
    # đường thẳng từ đuôi về đầu ở mọi nét hở -> thừa nét. Chỉ đóng khi hai đầu
    # đã sát nhau (trong 2 px quy đổi ra mm) thì đó mới thật sự là vòng kín.
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
        lines.append(f"; Contour {i+1}/{len(contours)} ({len(mm)} điểm)")
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
        f"; Quãng đường vẽ: {draw_d:.1f} mm",
        f"; Quãng đường di chuyển: {travel_d:.1f} mm",
        f"; Thời gian: ~{est:.1f} phút",
    ]
    lines += gcode_footer(config, stats)
    return finalize_gcode(lines, config), {
        'contours': len(contours),
        'draw_dist': draw_d, 'travel_dist': travel_d, 'est_time': est
    }


# ============================================================
# 2) RASTER — Tô vùng tối bằng nét liên tục
# ============================================================
# Quét hàng ngang kiểu máy in là cách tô TỆ NHẤT cho máy vẽ bút: mỗi hàng một
# lần nhấc + một lần hạ bút. Ảnh 300 hàng = 600 lần lên xuống trục Z, thời gian
# chạy Z còn lâu hơn thời gian vẽ, và mỗi lần hạ bút lại để một chấm đậm.
#
# Ba kiểu tô ở đây đều nhắm vào việc GIẢM SỐ LẦN NHẤC BÚT:
#   zigzag — quét xong một hàng thì đi thẳng xuống hàng kế (đầu hàng này nối
#            với cuối hàng kia) tạo MỘT nét liên tục hình ruy băng. Chỉ nhấc
#            bút khi phải nhảy sang mảng rời khác.
#   hatch  — nét song song rời nhau một chiều, kiểu gạch bóng bản khắc.
#   offset — nét chạy song song với ĐƯỜNG BAO rồi thu dần vào trong, bám theo
#            hình dạng vật nên nhìn "có hồn" hơn hẳn các đường ngang cứng đờ.


def _runs(row_bool):
    """Các đoạn liên tiếp True trên một hàng -> [(đầu, cuối), ...]."""
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
    """Đoạn nối p0->p1 có nằm gọn trong vùng cần tô không?

    Dùng để quyết định có được HẠ BÚT đi thẳng từ cuối hàng này sang đầu hàng
    kia hay không — nếu đoạn nối chạy ra ngoài hình thì phải nhấc bút, nếu không
    sẽ có vệt mực cắt ngang chỗ đáng lẽ để trắng.
    """
    h, w = mask.shape
    for t in np.linspace(0.0, 1.0, samples):
        x = int(round(p0[0] + (p1[0] - p0[0]) * t))
        y = int(round(p0[1] + (p1[1] - p0[1]) * t))
        if not (0 <= x < w and 0 <= y < h) or mask[y, x] == 0:
            return False
    return True


def scanline_fill(binary, step_px, angle_deg, link=True):
    """Tô vùng trắng bằng các nét song song nghiêng góc `angle_deg`.

    Cách làm: XOAY mặt nạ về phương ngang rồi quét theo hàng (đơn giản và chắc
    hơn nhiều so với cắt đường thẳng nghiêng qua đa giác), sau đó đưa các điểm
    ngược về hệ toạ độ ảnh gốc.

    link=True: nối các hàng liền kề thành một nét zigzag liên tục khi đoạn nối
    còn nằm trong hình -> số lần nhấc bút giảm hàng chục lần.
    """
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
    # Đoạn nối giữa 2 hàng chạy DỌC MÉP hình, mà mép hình thì răng cưa từng
    # pixel — kiểm tra trên mặt nạ gốc sẽ trượt ra ngoài liên tục và hầu như
    # không nối được hàng nào. Nới mặt nạ ra nửa khoảng cách nét: bút có lấn thì
    # cũng chỉ trong phạm vi độ phân giải đang chấp nhận.
    link_r = max(2, step // 2 + 1)
    link_mask = cv2.dilate(rot, cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * link_r + 1, 2 * link_r + 1)))
    # Chặn độ dài đoạn nối chỉ để phòng ca bệnh lý; việc "có được nối không"
    # do phép kiểm tra nằm-trong-hình quyết định. Chặn chặt quá thì cạnh hình
    # hơi thoai thoải là đứt nét, mà đứt ở đó thì phải nhấc bút vô ích.
    max_link = max(12.0, 6.0 * step)

    strokes = []          # danh sách nét trong hệ toạ độ ĐÃ XOAY
    cur = None
    for ri, y in enumerate(range(0, nh, step)):
        segs = _runs(rot[y] > 0)
        if not segs:
            cur = None    # hàng trống -> cắt nét, tránh nối vắt qua chỗ trắng
            continue
        if ri % 2:                                   # hàng lẻ đi ngược lại
            segs = [(e, s) for s, e in reversed(segs)]
        for a, b in segs:
            p_start, p_end = (float(a), float(y)), (float(b), float(y))
            if (link and cur is not None
                    and math.hypot(p_start[0] - cur[-1][0],
                                   p_start[1] - cur[-1][1]) <= max_link
                    and _connector_inside(link_mask, cur[-1], p_start)):
                cur.append(p_start)                  # hạ bút đi thẳng sang
            else:
                cur = []
                strokes.append(cur)
                cur.append(p_start)
            cur.append(p_end)

    # Đưa toàn bộ điểm về hệ toạ độ ảnh gốc
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
    """Điểm `pt` có nằm trong mask không?"""
    h, w = mask.shape
    x = int(round(float(pt[0])))
    y = int(round(float(pt[1])))
    return 0 <= x < w and 0 <= y < h and mask[y, x] > 0


def clip_polylines_to_mask(polylines, mask, sample_step_px=0.35):
    """Cắt các polyline về phần nằm trong mask.

    Dùng cho raster fill để chặn các đoạn quét/đường nối vô tình vượt ra khỏi biên.
    """
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
    """Tô theo ĐƯỜNG ĐỒNG MỨC: nét song song với đường bao, thu dần vào trong.

    Dùng biến đổi khoảng cách (distance transform): mỗi pixel biết nó cách mép
    hình bao xa, nên tập các pixel "cách mép đúng d" chính là một đường bao thu
    nhỏ d. Cắt ở d = step/2, 3·step/2, ... là được các vòng cách đều nhau —
    tương đương phép offset đa giác nhưng không phải xử lý các ca tự cắt.
    """
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
            out.append(np.vstack([pts, pts[:1]]))     # khép kín vòng
        level += step_px
    return out


def region_outlines(binary):
    """Đường bao ngoài + bao lỗ của các vùng cần tô (vẽ trước để cạnh sắc nét)."""
    cnts, _ = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cnts:
        pts = c.reshape(-1, 2).astype(np.float32)
        if len(pts) < 8:
            continue
        pts = smooth_polyline(pts, 2)
        out.append(np.vstack([pts, pts[:1]]))
    return out


def process_raster(image_path, config):
    """Ảnh → các nét tô (polyline pixel) + ảnh xem trước."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        bs = config.blur_size | 1
        gray = cv2.GaussianBlur(gray, (bs, bs), 0)
    _, binary = cv2.threshold(gray, config.threshold, 255, cv2.THRESH_BINARY)
    if config.invert:
        binary = cv2.bitwise_not(binary)

    ss = max(1, int(round(getattr(config, 'raster_supersample', 1))))
    if ss > 1:
        binary = cv2.resize(binary, (w * ss, h * ss), interpolation=cv2.INTER_LINEAR)
        _, binary = cv2.threshold(binary, 127, 255, cv2.THRESH_BINARY)
        h, w = binary.shape[:2]

    # Bước nét tính theo khung ĐÃ ĐẶT: đặt ảnh nhỏ lại thì bước px cũng phải nhỏ
    # theo, không thì nét tô trên giấy thưa ra so với con số đã khai.
    scale = mm_per_px(w, h, config)
    step_px = max(1, int(round(config.raster_resolution / scale)))
    style = getattr(config, 'raster_style', 'zigzag')

    outline_polylines = []
    if getattr(config, 'raster_outline', False):
        outline_polylines = region_outlines(binary)
        # Thụt phần tô vào trong kỹ hơn một chút để bút không lấn qua viền.
        # Nếu chỉ lùi nửa bước thì một số đoạn chéo/đường nối vẫn có thể cọ ra ngoài
        # khi ảnh có biên cong gắt hoặc mép răng cưa.
        r = max(1, step_px // 2)
        fill_mask = cv2.erode(binary, cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    else:
        fill_mask = binary

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

    # Chốt an toàn cuối cùng: mọi nét tô phải nằm trong vùng đã co vào trong.
    fill_polylines = clip_polylines_to_mask(fill_polylines, fill_mask)
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
            fill_polylines = clip_polylines_to_mask(polylines[outline_len:], fill_mask)
            polylines = polylines[:outline_len] + fill_polylines

    polylines = [p for p in polylines if len(p) >= 2]

    # --- Ảnh xem trước ---
    images = {'original': img.copy()}
    images['binary'] = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    draw_pts = [np.round(p).astype(np.int32).reshape(-1, 1, 2) for p in polylines]

    preview = np.zeros((h, w, 3), np.uint8)
    cv2.polylines(preview, draw_pts, False, (255, 255, 255), 1)
    for p in polylines:
        cv2.circle(preview, (int(p[0][0]), int(p[0][1])), 2, (0, 255, 0), -1)
    images['preview'] = preview

    overlay = img.copy()
    cv2.polylines(overlay, draw_pts, False, (0, 255, 0), 1)
    images['overlay'] = overlay

    # Mô phỏng đường chạy: trắng = vẽ, đỏ = di chuyển khi NHẤC BÚT
    sim = np.zeros((h, w, 3), np.uint8)
    cv2.polylines(sim, draw_pts, False, (255, 255, 255), 1)
    prev = None
    for p in polylines:
        if prev is not None:
            cv2.line(sim, (int(prev[0]), int(prev[1])),
                     (int(p[0][0]), int(p[0][1])), (0, 0, 160), 1)
        prev = p[-1]
    images['raster'] = sim

    dp = cv2.countNonZero(binary)
    total_pts = sum(len(p) for p in polylines)
    kind = {'zigzag': 'zigzag liên tục', 'hatch': 'gạch song song',
            'offset': 'đường đồng mức'}.get(style, style)
    if style != 'offset':                      # góc chỉ có nghĩa với nét thẳng
        kind += f" {config.raster_angle:.0f}°"
    info = (f"Tô [{kind}]: {len(polylines)} nét (= số lần nhấc bút) | "
            f"Điểm: {total_pts} | Vùng tối {dp/(w*h)*100:.1f}% | "
            f"Cách nét {config.raster_resolution}mm")
    return polylines, images, w, h, info


def process_raster_v2(image_path, config):
    """Raster pipeline with optional supersampling and gentle smoothing."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được: {image_path}")

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
    kind = {'zigzag': 'zigzag liên tục', 'hatch': 'gạch song song',
            'offset': 'đường đồng mức'}.get(style, style)
    if style != 'offset':
        kind += f" {config.raster_angle:.0f}°"
    info = (f"Tô [{kind}]: {len(polylines)} nét (= số lần nhấc bút) | "
            f"Điểm: {total_pts} | Vùng tối {dp/(orig_w*orig_h)*100:.1f}% | "
            f"Cách nét {config.raster_resolution}mm")
    return polylines, images, orig_w, orig_h, info


process_raster = process_raster_v2


def generate_gcode_raster(polylines, w, h, config):
    """Sinh G-Code tô vùng: mỗi polyline = MỘT lần hạ bút."""
    ordered = optimize_contour_path([np.asarray(p).reshape(-1, 1, 2)
                                     for p in polylines])
    style = getattr(config, 'raster_style', 'zigzag')
    kind = {'zigzag': 'zigzag liên tục', 'hatch': 'gạch song song',
            'offset': 'đường đồng mức'}.get(style, style)
    if style != 'offset':
        kind += f" {config.raster_angle:.0f}°"
    mode = "cung G2/G3" if config.use_arcs else "chỉ G1"
    lines = gcode_header(config, "RASTER (tô vùng)", w, h,
                         f"Kiểu tô: {kind} | "
                         f"Cách nét: {config.raster_resolution}mm | Nội suy: {mode}")
    draw_d = travel_d = 0.0
    px, py = 0.0, 0.0
    for i, cnt in enumerate(ordered):
        mm = polyline_to_mm(cnt, w, h, config)
        if len(mm) < 2:
            continue
        lines.append(f"; Nét {i+1}/{len(ordered)} ({len(mm)} điểm)")
        sx, sy = mm[0]
        travel_d += math.hypot(sx - px, sy - py)
        lines.append(cmd_pen_up(config))          # 1 lần nhấc bút cho CẢ nét
        lines.append(cmd_travel(config, sx, sy))
        lines.append(cmd_pen_down(config))
        draw_d += emit_polyline(mm, config, lines)
        px, py = mm[-1]
        lines.append("")

    est = ((draw_d / config.feed_rate_draw + travel_d / config.feed_rate_travel)
           if config.feed_rate_draw else 0.0)
    stats = [
        f"; Số nét (= số lần nhấc/hạ bút): {len(ordered)}",
        f"; Vẽ: {draw_d:.1f}mm | Di chuyển: {travel_d:.1f}mm",
        f"; Thời gian: ~{est:.1f} phút",
    ]
    lines += gcode_footer(config, stats)
    return finalize_gcode(lines, config), {
        'strokes': len(ordered),
        'points': sum(len(p) for p in polylines),
        'draw_dist': draw_d, 'travel_dist': travel_d, 'est_time': est,
    }


# ============================================================
# 3) EDGE — Phát hiện cạnh (Canny), vẽ theo nét
# ============================================================
def process_edge(image_path, config):
    """Xử lý ảnh → edge contours + preview."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        bs = config.blur_size | 1
        gray = cv2.GaussianBlur(gray, (bs, bs), 0)

    # Canny edge detection
    edges = cv2.Canny(gray, config.canny_low, config.canny_high)

    # Tìm contour từ ảnh edge
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

    # Edge preview (trắng trên đen)
    edge_display = np.zeros((h, w, 3), np.uint8)
    cv2.drawContours(edge_display, contours, -1, (255, 255, 255), 1)
    for cnt in contours:
        cv2.circle(edge_display, tuple(cnt[0][0]), 2, (0, 255, 0), -1)
    images['preview'] = edge_display

    # Overlay
    overlay = img.copy()
    cv2.drawContours(overlay, contours, -1, (0, 200, 255), 1)
    images['overlay'] = overlay

    # Canny raw
    edges_bgr = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
    images['canny_raw'] = edges_bgr

    total_pts = sum(len(c) for c in contours)
    info = f"Edges: {len(contours)} nét | Điểm: {total_pts} | Canny [{config.canny_low}-{config.canny_high}]"
    return contours, images, w, h, info


def generate_gcode_edge(contours, w, h, config):
    """Sinh G-Code từ edge contours (giống contour nhưng KHÔNG đóng loop)."""
    contours = optimize_contour_path(contours)
    mode = "cung G2/G3" if config.use_arcs else "chỉ G1"
    lines = gcode_header(config, "EDGE (phát hiện cạnh/nét)", w, h,
                         f"Nét: {len(contours)} | Canny [{config.canny_low}-{config.canny_high}] "
                         f"| Nội suy: {mode}")
    draw_d = travel_d = 0.0
    px, py = 0.0, 0.0
    for i, cnt in enumerate(contours):
        mm = polyline_to_mm(cnt, w, h, config)
        if len(mm) < 2:
            continue
        lines.append(f"; Nét {i+1}/{len(contours)} ({len(mm)} điểm)")
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
        f"; Nét: {len(contours)}",
        f"; Vẽ: {draw_d:.1f}mm | Di chuyển: {travel_d:.1f}mm",
        f"; Thời gian: ~{est:.1f} phút",
    ]
    lines += gcode_footer(config, stats)
    return finalize_gcode(lines, config), {
        'edges': len(contours),
        'draw_dist': draw_d, 'travel_dist': travel_d, 'est_time': est,
    }


# ============================================================
# DÙNG CHUNG cho LINE và PORTRAIT
# ============================================================
def strokes_from_binary(binary, config, despeckle=None):
    """Ảnh nhị phân (nét = TRẮNG) -> (danh sách polyline, ảnh nét để xem trước).

    despeckle=False khi ảnh vào ĐÃ mỏng 1 px (ranh giới màu): phép OPEN là co
    rồi giãn, nét 1 px sẽ bị co mất hẳn và không giãn lại được.
    """
    if config.despeckle if despeckle is None else despeckle:
        k = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)

    # --- Rút về nét đều hoặc lấy đường bao ---
    if config.uniform_stroke:
        skel = skeletonize(binary)

        # Mảng ĐẶC (con ngươi, lỗ mũi, dấu chấm) có skeleton co lại thành một
        # chấm vài pixel -> bị bộ lọc độ dài loại sạch, hình mất hẳn chi tiết.
        # Bút thì không tô được mảng đặc, nên vẽ ĐƯỜNG BAO của chúng.
        blob_raw = []
        if config.blob_outline:
            n, labels, stats, _ = cv2.connectedComponentsWithStats(
                (binary > 0).astype(np.uint8), connectivity=8)
            if n > 1:
                skel_len = np.bincount(labels[skel > 0].ravel(), minlength=n)
                for i in range(1, n):
                    area = stats[i, cv2.CC_STAT_AREA]
                    if skel_len[i] >= config.line_min_length or area < 8:
                        continue          # nét dài bình thường -> để skeleton lo
                    comp = (labels == i).astype(np.uint8)
                    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_NONE)
                    for c in cnts:
                        pts = c.reshape(-1, 2)
                        if len(pts) >= 6:
                            blob_raw.append(np.vstack([pts, pts[:1]]))  # khép kín
                    skel[labels == i] = 0  # đã xử lý -> đừng dò lại ở bước sau

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

    # --- Làm mượt + làm gọn số điểm ---
    # Làm gọn CHỈ khi KHÔNG dùng cung: approxPolyDP biến đường tròn thành đa
    # giác thô, sau đó không còn khớp được cung nào. Khi bật G2/G3 thì chính
    # bộ khớp cung đã nén dữ liệu, giữ điểm dày để cung bám đúng hình.
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
    """Bộ ảnh xem trước dùng chung: nét vẽ / chồng lớp / ảnh nhị phân."""
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
    """Xoá các mảng trắng nhỏ hơn min_area px (nhiễu hạt của ảnh chụp)."""
    if min_area <= 1:
        return binary
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (binary > 0).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        keep[i] = stats[i, cv2.CC_STAT_AREA] >= min_area
    return np.where(keep[labels], 255, 0).astype(np.uint8)


# ============================================================
# 4) LINE — Nét vẽ đen trắng, độ dày ĐỀU
# ============================================================
def process_line(image_path, config):
    """Ảnh -> nét đen trắng 1 px (skeleton) -> danh sách polyline."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        bs = int(config.blur_size) | 1
        gray = cv2.GaussianBlur(gray, (bs, bs), 0)

    # --- Nhị phân hoá: nét = trắng (255), nền = đen ---
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
    kind = "nét đều (skeleton)" if config.uniform_stroke else "đường bao"
    info = f"Line [{kind}]: {len(polylines)} nét | Điểm: {total_pts}"
    return polylines, images, w, h, info


def generate_gcode_line(polylines, w, h, config):
    """Sinh G-Code từ các nét, ưu tiên cung tròn G2/G3."""
    ordered = optimize_contour_path([p.reshape(-1, 1, 2) for p in polylines])
    mode = "cung G2/G3" if config.use_arcs else "chỉ G1"
    kind = "nét đều (skeleton)" if config.uniform_stroke else "đường bao"
    lines = gcode_header(config, "LINE (nét vẽ đen trắng)", w, h,
                         f"Nét: {len(ordered)} | {kind} | Nội suy: {mode}")
    draw_d = travel_d = 0.0
    px, py = 0.0, 0.0
    n_arc = n_line = 0

    for i, cnt in enumerate(ordered):
        mm = polyline_to_mm(cnt, w, h, config)
        if len(mm) < 2:
            continue
        before = len(lines)
        lines.append(f"; Nét {i+1}/{len(ordered)} ({len(mm)} điểm)")
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
        f"; Nét: {len(ordered)} | Cung G2/G3: {n_arc} | Đoạn thẳng G1: {n_line}",
        f"; Vẽ: {draw_d:.1f}mm | Di chuyển: {travel_d:.1f}mm",
        f"; Thời gian: ~{est:.1f} phút",
    ]
    lines += gcode_footer(config, stats)
    return finalize_gcode(lines, config), {
        'lines_count': len(ordered), 'arcs': n_arc, 'segments': n_line,
        'draw_dist': draw_d, 'travel_dist': travel_d, 'est_time': est,
    }


# ============================================================
# 6) COLOR — Ranh giới giữa các vùng MÀU
# ============================================================
# Dành cho tranh màu phẳng: hoạt hình, logo, ảnh vector, clip-art.
#
# Vì sao ngưỡng độ sáng KHÔNG dùng được cho loại ảnh này: đổi sang ảnh xám thì
# vàng (255,255,0) ra ~226 còn trắng ra 255 — sát nhau, nên mọi ngưỡng tách
# được nền trắng đều nuốt luôn viền thân màu vàng. Đỏ (~84) lại tối gần bằng
# nét đen. Thông tin phân biệt nằm ở MÀU chứ không ở độ sáng.
#
# Cách làm: gom toàn ảnh về N nhóm màu (k-means trong không gian Lab, gần với
# cảm nhận mắt người), rồi đánh dấu pixel nào có hàng xóm PHẢI hoặc DƯỚI thuộc
# nhóm khác. Đó chính là "2 pixel kề nhau khác nhau thì tạo 1 nét", và vì so
# theo nhãn nhóm nên viền luôn rộng đúng 1 px và khép kín.

def quantize_colors(img, k, seed=42):
    """Gom màu ảnh về k nhóm trong không gian Lab. Trả về nhãn (h, w)."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    h, w = lab.shape[:2]
    Z = lab.reshape(-1, 3).astype(np.float32)

    # Lấy mẫu để chạy k-means cho nhanh trên ảnh lớn, rồi gán lại toàn bộ
    cv2.setRNGSeed(seed)               # cùng ảnh -> cùng kết quả mỗi lần chạy
    rng = np.random.default_rng(seed)
    sample = Z if len(Z) <= 40000 else Z[rng.choice(len(Z), 40000, replace=False)]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, _, centers = cv2.kmeans(sample, int(k), None, criteria, 3,
                               cv2.KMEANS_PP_CENTERS)

    # Gán từng pixel về tâm gần nhất — lặp theo tâm để không ngốn bộ nhớ
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
    """Tranh màu phẳng -> nét ở ranh giới các vùng màu."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được: {image_path}")
    h, w = img.shape[:2]

    # 1) Khử nhiễu/răng cưa JPEG — trung vị giữ cạnh sắc, không bôi nhoè
    src = img
    if config.color_denoise > 0:
        ksz = int(config.color_denoise) | 1
        src = cv2.medianBlur(src, ksz)

    # 2) Gom màu
    labels, centers = quantize_colors(src, config.color_levels)

    # 3)  Nét = chỗ pixel kề nhau thuộc HAI nhóm màu khác nhau
    edge = np.zeros((h, w), bool)
    edge[:, :-1] |= labels[:, :-1] != labels[:, 1:]     # so với hàng xóm PHẢI
    edge[:-1, :] |= labels[:-1, :] != labels[1:, :]     # so với hàng xóm DƯỚI
    binary = edge.astype(np.uint8) * 255

    # 4) Bỏ mảnh vụn
    binary = remove_small_blobs(binary, int(config.color_min_area))

    # 5) Rút nét + làm mượt. despeckle=False vì ranh giới đã mỏng đúng 1 px.
    polylines, stroke_img = strokes_from_binary(binary, config, despeckle=False)

    quant = centers[labels].astype(np.uint8)
    quant = cv2.cvtColor(quant, cv2.COLOR_LAB2BGR)
    images = stroke_previews(img, polylines, stroke_img, extra={'quant': quant})

    total_pts = sum(len(p) for p in polylines)
    info = (f"Color: {len(polylines)} nét | Điểm: {total_pts} | "
            f"{config.color_levels} nhóm màu")
    return polylines, images, w, h, info


def generate_gcode_color(polylines, w, h, config):
    """Sinh G-Code từ ranh giới màu (dùng chung bộ sinh của LINE)."""
    gcode, stats = generate_gcode_line(polylines, w, h, config)
    return gcode.replace("LINE (nét vẽ đen trắng)", "COLOR (ranh giới màu)"), stats


# ============================================================
# 5) PORTRAIT — Ảnh chụp người → nét vẽ chân dung
# ============================================================
# Ảnh chụp là TÔNG LIÊN TỤC: da, tóc, nền chuyển dần chứ không có ranh giới
# đen/trắng rõ. Cắt ngưỡng thẳng sẽ ra mảng loang; Canny thì ra nét đứt vụn
# vì nhạy với hạt nhiễu và lỗ chân lông.
#
# XDoG (eXtended Difference of Gaussians) là kỹ thuật chuẩn cho việc này:
# hiệu hai ảnh làm mờ ở hai mức sigma khác nhau làm nổi ĐƯỜNG BIÊN ở đúng cỡ
# chi tiết mong muốn, rồi hàm tanh ép đáp ứng thành nét dứt khoát. Kết quả là
# nét liền mạch kiểu vẽ tay, không phải rìa răng cưa.

def xdog(gray, config):
    """Ảnh xám -> (ảnh 'mực' để xem trước, mặt nạ nét nhị phân).

    Đáp ứng DoG được CHUẨN HOÁ theo độ lệch chuẩn của chính nó, nên một ngưỡng
    duy nhất dùng được cho mọi ảnh bất kể sáng tối / tương phản. Nếu so sánh
    trực tiếp với hằng số tuyệt đối thì ảnh này ra đặc kín, ảnh kia ra trắng
    trơn — đúng lỗi gặp phải với dạng XDoG nguyên bản.
    """
    f = gray.astype(np.float32) / 255.0
    s = max(0.3, float(config.portrait_detail))
    g1 = cv2.GaussianBlur(f, (0, 0), s)
    g2 = cv2.GaussianBlur(f, (0, 0), s * 1.6)   # 1.6 = xấp xỉ Laplace-of-Gaussian

    d = g1 - g2          # dương ở phía SÁNG của cạnh, âm ở phía TỐI
    sd = float(d.std())
    resp = d / sd if sd > 1e-9 else np.zeros_like(d)

    # Chỉ lấy phía TỐI của cạnh -> MỖI cạnh cho ĐÚNG MỘT nét (không bị nét đôi)
    sens = float(config.portrait_sensitivity)
    mask = (resp < -sens).astype(np.uint8) * 255

    phi = float(config.portrait_phi)
    ink = np.clip(1.0 + np.tanh(phi * (resp + sens)), 0.0, 1.0)
    return (ink * 255).astype(np.uint8), mask


def process_portrait(image_path, config):
    """Ảnh chụp người -> nét vẽ chân dung -> danh sách polyline."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Không đọc được: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1) Làm phẳng da/nhiễu nhưng GIỮ cạnh (mắt, mũi, viền tóc).
    #    Gaussian thường sẽ bôi nhoè luôn cả cạnh -> mất nét khuôn mặt.
    if config.portrait_denoise > 0:
        gray = cv2.bilateralFilter(gray, 9, float(config.portrait_denoise),
                                   float(config.portrait_denoise))

    # 2) XDoG -> ảnh mực + mặt nạ nét (nét = TRẮNG, khớp strokes_from_binary)
    ink, binary = xdog(gray, config)

    # 3) Bỏ hạt nhiễu nhỏ (ảnh chụp luôn có)
    binary = remove_small_blobs(binary, int(config.portrait_min_area))

    # 5) Rút nét đều + làm mượt (dùng chung với LINE)
    polylines, stroke_img = strokes_from_binary(binary, config)

    images = stroke_previews(img, polylines, stroke_img,
                             extra={'ink': cv2.cvtColor(ink, cv2.COLOR_GRAY2BGR)})

    total_pts = sum(len(p) for p in polylines)
    info = (f"Portrait: {len(polylines)} nét | Điểm: {total_pts} | "
            f"DoG σ={config.portrait_detail} ngưỡng={config.portrait_sensitivity}σ")
    return polylines, images, w, h, info


def generate_gcode_portrait(polylines, w, h, config):
    """Sinh G-Code chân dung (dùng chung bộ sinh của LINE)."""
    gcode, stats = generate_gcode_line(polylines, w, h, config)
    return gcode.replace("LINE (nét vẽ đen trắng)", "PORTRAIT (chân dung)"), stats


# ============================================================
# 8) TEXT — Viết chữ
# ============================================================
# Khác mọi phương pháp trên: đầu vào là CHỮ chứ không phải ảnh.
#
# Cách làm: dựng chữ ra một khung ảnh có ĐÚNG tỉ lệ vùng vẽ. Khi đó px_to_mm
# (vốn co ảnh vừa khung rồi canh giữa) trở thành ánh xạ 1-1 không méo — đặt chữ
# ở đâu trên khung là ra đúng chỗ đó trên giấy, cỡ chữ khai bằng mm là ra đúng mm.
# Sau đó dùng lại nguyên bộ skeleton + khớp cung G2/G3 của LINE.
#
# Vì sao phải skeleton: font TrueType là chữ ĐẶC (nét có bề dày). Đi theo đường
# bao chữ đặc sẽ ra chữ RỖNG hai nét viền. Skeleton rút mỗi nét chữ về đường tâm
# 1 px -> bút đi đúng MỘT đường như người viết tay. Muốn chữ rỗng kiểu tiêu đề
# thì chọn kiểu "viền chữ".

WINDOWS_FONT_DIRS = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
]


def list_system_fonts():
    """{tên font: đường dẫn} — các file TrueType/OpenType có trong máy."""
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
    """Nạp font theo đường dẫn / tên file / tên hiển thị; hỏng thì lùi về font sẵn có."""
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
    raise RuntimeError("Không nạp được font TrueType nào — kiểm tra lại ô 'Font'.")


def _cap_height_px(font):
    """Chiều cao chữ 'H' (px) — cầu nối để quy 'cỡ chữ mm' ra cỡ font px."""
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    _, y0, _, y1 = d.textbbox((0, 0), "H", font=font)
    return max(1, y1 - y0)


def _render_text_block(text, font, line_spacing, align):
    """Khối chữ nhiều dòng (ảnh 'L', nét = 255), bó sát, baseline các dòng đều nhau.

    Tự đặt từng dòng thay vì dùng multiline_text vì cách tính 'spacing' của
    Pillow đổi theo phiên bản, còn giãn dòng ở đây phải ra đúng số mm đã khai.
    """
    lines = text.splitlines() or [""]
    ascent, descent = font.getmetrics()
    line_h = max(1, ascent + descent)
    step = max(1, int(round(line_h * max(0.5, line_spacing))))

    d0 = ImageDraw.Draw(Image.new("L", (1, 1)))
    widths = [float(d0.textlength(s, font=font)) for s in lines]
    # lề tạm: dấu tiếng Việt (Ẫ, Ổ) vượt lên trên ascent, chữ nghiêng tràn ngang
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

    bb = img.getbbox()          # bó sát vào đúng phần có nét
    return img.crop(bb) if bb else img


def render_text_image(config):
    """Chữ -> (ảnh nhị phân nét=trắng, ảnh 'giấy' xem trước, cỡ khối chữ tính mm)."""
    ppm = max(1.0, float(config.text_render_scale))       # px trên mỗi mm
    W = max(64, int(round(config.work_area_x * ppm)))
    H = max(64, int(round(config.work_area_y * ppm)))
    margin = max(0.0, float(config.text_margin)) * ppm
    usable_w = max(8.0, W - 2 * margin)
    usable_h = max(8.0, H - 2 * margin)

    text = config.text_content if config.text_content.strip() else "Xin chào"
    align = config.text_align if config.text_align in ("left", "center", "right") else "center"
    spacing = float(config.text_line_spacing)

    # Cỡ font px sao cho chữ HOA cao đúng text_height mm: đo chữ 'H' ở cỡ tham
    # chiếu rồi suy ra tỉ lệ (em-size của font không bằng chiều cao chữ hoa).
    REF = 256
    cap_ref = _cap_height_px(load_font(config.text_font, REF))
    font_px = int(round(float(config.text_height) * ppm * REF / cap_ref))
    font_px = max(8, min(font_px, 6000))

    block = _render_text_block(text, load_font(config.text_font, font_px),
                               spacing, align)

    # Tràn khung -> thu nhỏ cho vừa. Bật "tự phóng" -> ép kín khung luôn.
    fit = min(usable_w / block.width, usable_h / block.height)
    if config.text_autofit or fit < 1.0:
        font_px = max(8, int(round(font_px * fit)))
        block = _render_text_block(text, load_font(config.text_font, font_px),
                                   spacing, align)
        fit2 = min(usable_w / block.width, usable_h / block.height)
        if fit2 < 1.0:      # còn dư vài px do làm tròn cỡ font -> co ảnh cho chắc
            block = block.resize((max(1, int(block.width * fit2)),
                                  max(1, int(block.height * fit2))), Image.LANCZOS)

    if align == "left":
        x = int(round(margin))
    elif align == "right":
        x = int(round(W - margin - block.width))
    else:
        x = int(round((W - block.width) / 2))
    y = int(round((H - block.height) / 2))       # luôn canh giữa theo chiều dọc

    canvas = Image.new("L", (W, H), 0)
    canvas.paste(block, (max(0, x), max(0, y)))

    binary = np.where(np.array(canvas, np.uint8) >= 128, 255, 0).astype(np.uint8)
    paper = np.full((H, W, 3), 255, np.uint8)    # xem trước: chữ đen trên nền trắng
    paper[binary > 0] = (0, 0, 0)
    return binary, paper, (block.width / ppm, block.height / ppm)


@contextlib.contextmanager
def _text_stroke_mode(config):
    """TEXT tự quyết nét đơn / viền chữ, không nghe ô 'Nét ĐỀU' của LINE.

    blob_outline luôn bật: dấu tiếng Việt và chấm chữ 'i' là mảng đặc tí hon,
    skeleton của chúng co thành vài pixel rồi bị lọc độ dài xoá mất — mất dấu là
    sai chữ, nên phải vẽ đường bao của chúng.
    """
    prev = (config.uniform_stroke, config.blob_outline)
    config.uniform_stroke = (config.text_style != 'outline')
    config.blob_outline = True
    try:
        yield
    finally:
        config.uniform_stroke, config.blob_outline = prev


def _text_outlines(binary, config):
    """Đường bao chữ cho kiểu 'viền chữ' — khép kín và giữ đủ điểm.

    Không dùng nhánh đường bao của strokes_from_binary vì nó lấy contour kiểu
    CHAIN_APPROX_SIMPLE: cạnh thẳng của chữ bị rút còn 2 điểm, bộ khớp cung
    G2/G3 lại bẻ mấy điểm góc đó thành cung -> chữ méo. Ngoài ra contour là
    vòng KÍN, phải nối điểm cuối về điểm đầu, không thì hở mất một cạnh.
    """
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
        out.append(np.vstack([pts, pts[:1]]).astype(np.float32))   # khép kín vòng
    return out


def process_text(config):
    """Chữ -> danh sách polyline. Không cần ảnh đầu vào."""
    binary, paper, (bw_mm, bh_mm) = render_text_image(config)
    h, w = binary.shape[:2]
    if config.text_style == 'outline':
        polylines = _text_outlines(binary, config)
        stroke_img = binary
    else:
        with _text_stroke_mode(config):
            # despeckle=False: nét chữ và dấu tiếng Việt rất mảnh, phép OPEN ăn mất
            polylines, stroke_img = strokes_from_binary(binary, config, despeckle=False)
    images = stroke_previews(paper, polylines, stroke_img, extra={'binary': binary})

    total_pts = sum(len(p) for p in polylines)
    kind = "viền chữ" if config.text_style == 'outline' else "nét đơn"
    n_rows = len(config.text_content.splitlines()) or 1
    info = (f"Text [{kind}]: {len(polylines)} nét | Điểm: {total_pts} | "
            f"{n_rows} dòng | Khối chữ {bw_mm:.1f} × {bh_mm:.1f} mm")
    return polylines, images, w, h, info


def generate_gcode_text(polylines, w, h, config):
    """Sinh G-Code cho chữ (dùng lại bộ sinh của LINE)."""
    with _text_stroke_mode(config):
        gcode, stats = generate_gcode_line(polylines, w, h, config)
    kind = "viền chữ" if config.text_style == 'outline' else "nét đơn"
    return gcode.replace("LINE (nét vẽ đen trắng)",
                         f"TEXT (viết chữ — {kind})"), stats


# ============================================================
# GIAO DIỆN
# ============================================================
# TỶ LỆ KHUNG GIAO DIỆN — chỉnh MỘT chỗ này là cả cửa sổ, bảng tuỳ chọn và cỡ
# chữ cùng thu/phóng theo. 1.0 = cỡ gốc, 0.85 = nhỏ lại 15%, 0.7 = nhỏ hẳn.
# Đây chỉ là mức TỐI ĐA: fit_ui_scale() sẽ tự hạ thêm nếu màn hình không đủ chỗ.
UI_SCALE = 0.78

BASE_W, BASE_H = 1180, 820      # cỡ cửa sổ ở tỷ lệ 1.0
MIN_W, MIN_H = 900, 600         # cỡ nhỏ nhất còn dùng được (ở tỷ lệ 1.0)
SCREEN_USE_W = 0.94             # chỉ chiếm ngần này bề ngang màn hình
SCREEN_USE_H = 0.88             # chừa chỗ cho taskbar + thanh tiêu đề
UI_SCALE_MIN = 0.55             # nhỏ hơn nữa thì chữ không đọc nổi


def ui_px(v):
    """Kích thước tính bằng pixel, đã nhân UI_SCALE."""
    return max(1, int(v * UI_SCALE))


def ui_font(size):
    """Cỡ chữ đã nhân UI_SCALE (chặn dưới 7pt để còn đọc được)."""
    return max(7, int(size * UI_SCALE + 0.5))


def fit_ui_scale(root):
    """Hạ UI_SCALE cho cửa sổ vừa màn hình thật.

    Cửa sổ cỡ cố định bị tràn khỏi mép dưới trên màn nhỏ, hoặc khi Windows đang
    phóng to hiển thị (125% / 150%) — lúc đó hàng nút dưới cùng lọt ra ngoài,
    không bấm được. Đo màn hình trước rồi co giao diện lại cho lọt.
    """
    global UI_SCALE
    avail_w = root.winfo_screenwidth() * SCREEN_USE_W
    avail_h = root.winfo_screenheight() * SCREEN_USE_H
    fit = min(avail_w / BASE_W, avail_h / BASE_H, 1.0)
    UI_SCALE = max(UI_SCALE_MIN, min(UI_SCALE, fit))
    return UI_SCALE


def place_window(root, w, h):
    """Đặt cửa sổ cỡ w×h vào giữa màn hình, cắt bớt nếu vẫn còn quá khổ."""
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = min(w, int(sw * SCREEN_USE_W))
    h = min(h, int(sh * SCREEN_USE_H))
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 3)      # nhích lên trên chút cho thoáng taskbar
    root.geometry(f"{w}x{h}+{x}+{y}")
    return w, h


# ============================================================
# CROP DIALOG — Cửa sổ crop ảnh tương tác
# ============================================================
class CropDialog:
    """Cửa sổ crop ảnh với khung kéo thả tương tác.

    Hiển thị ảnh gốc với vùng crop có thể kéo để di chuyển, kéo cạnh/góc để
    thay đổi kích thước. Vùng ngoài crop được phủ tối bán trong suốt.
    """

    HANDLE_SIZE = 8           # kích thước tay nắm kéo (px)
    MIN_CROP_PX = 20          # kích thước crop tối thiểu (px trên canvas)
    OVERLAY_STIPPLE = 'gray50'  # pattern tối phủ vùng ngoài crop

    def __init__(self, parent, pil_img, initial_rect, callback):
        """
        parent:        widget cha (root)
        pil_img:       ảnh PIL gốc
        initial_rect:  (x, y, w, h) crop hiện tại hoặc None
        callback:      hàm gọi khi xác nhận, nhận (x, y, w, h) hoặc None
        """
        self.pil_img = pil_img
        self.img_w, self.img_h = pil_img.size
        self.callback = callback

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("Crop ảnh")
        self.dlg.configure(bg="#1e1e2e")
        self.dlg.transient(parent)
        self.dlg.grab_set()

        # Cỡ cửa sổ: vừa màn hình, chừa chỗ cho nút
        sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
        max_w = int(sw * 0.85)
        max_h = int(sh * 0.80) - 80   # chừa chỗ nút + tiêu đề
        self.scale = min(max_w / self.img_w, max_h / self.img_h, 1.0)
        self.cv_w = max(100, int(self.img_w * self.scale))
        self.cv_h = max(100, int(self.img_h * self.scale))

        # Đặt cửa sổ giữa màn hình
        win_w = self.cv_w + 20
        win_h = self.cv_h + 120
        x = max(0, (sw - win_w) // 2)
        y = max(0, (sh - win_h) // 3)
        self.dlg.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.dlg.resizable(False, False)

        # Header
        hdr = ttk.Frame(self.dlg)
        hdr.pack(fill=tk.X, padx=10, pady=(8, 4))
        ttk.Label(hdr, text="Crop ảnh — kéo khung để chọn vùng cắt",
                  font=("Segoe UI", ui_font(11), "bold"),
                  foreground="#89b4fa", background="#1e1e2e").pack(side=tk.LEFT)
        self.size_label = ttk.Label(hdr, text="", foreground="#a6adc8",
                                    background="#1e1e2e")
        self.size_label.pack(side=tk.RIGHT)

        # Canvas
        self.canvas = tk.Canvas(self.dlg, width=self.cv_w, height=self.cv_h,
                                bg="#11111b", highlightthickness=1,
                                highlightbackground="#585b70")
        self.canvas.pack(padx=10, pady=4)

        # Hiển thị ảnh
        display_img = pil_img.resize((self.cv_w, self.cv_h), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW, tags="bg")

        # Crop rect ban đầu (pixel ảnh gốc)
        if initial_rect:
            self.crop_x, self.crop_y = initial_rect[0], initial_rect[1]
            self.crop_w, self.crop_h = initial_rect[2], initial_rect[3]
        else:
            # Mặc định: toàn bộ ảnh
            self.crop_x, self.crop_y = 0.0, 0.0
            self.crop_w, self.crop_h = float(self.img_w), float(self.img_h)

        self._drag_mode = None
        self._drag_start = None
        self._drag_orig = None

        # Vẽ ban đầu
        self._draw_crop()

        # Sự kiện chuột
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)

        # Nút bấm
        btn_frame = ttk.Frame(self.dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=(6, 10))

        ttk.Button(btn_frame, text="Xác nhận crop",
                   command=self._confirm).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Toàn bộ ảnh",
                   command=self._reset).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Bỏ crop (dùng ảnh gốc)",
                   command=self._remove_crop).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Huỷ",
                   command=self.dlg.destroy).pack(side=tk.RIGHT)

    # ---- Quy đổi pixel ảnh <-> pixel canvas ----
    def _img_to_cv(self, ix, iy):
        return ix * self.scale, iy * self.scale

    def _cv_to_img(self, cx, cy):
        return cx / self.scale, cy / self.scale

    # ---- Vẽ vùng crop ----
    def _draw_crop(self):
        self.canvas.delete("crop")
        cx1, cy1 = self._img_to_cv(self.crop_x, self.crop_y)
        cx2, cy2 = self._img_to_cv(self.crop_x + self.crop_w,
                                     self.crop_y + self.crop_h)

        # Phủ tối 4 vùng ngoài crop bằng hình chữ nhật bán trong suốt
        # Trên
        self.canvas.create_rectangle(0, 0, self.cv_w, cy1,
                                      fill="black", stipple=self.OVERLAY_STIPPLE,
                                      outline="", tags="crop")
        # Dưới
        self.canvas.create_rectangle(0, cy2, self.cv_w, self.cv_h,
                                      fill="black", stipple=self.OVERLAY_STIPPLE,
                                      outline="", tags="crop")
        # Trái
        self.canvas.create_rectangle(0, cy1, cx1, cy2,
                                      fill="black", stipple=self.OVERLAY_STIPPLE,
                                      outline="", tags="crop")
        # Phải
        self.canvas.create_rectangle(cx2, cy1, self.cv_w, cy2,
                                      fill="black", stipple=self.OVERLAY_STIPPLE,
                                      outline="", tags="crop")

        # Khung crop
        self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                      outline="#89b4fa", width=2, tags="crop")

        # Đường lưới 3x3 (rule of thirds)
        for i in (1, 2):
            gx = cx1 + (cx2 - cx1) * i / 3
            gy = cy1 + (cy2 - cy1) * i / 3
            self.canvas.create_line(gx, cy1, gx, cy2,
                                     fill="#585b70", dash=(3, 3), tags="crop")
            self.canvas.create_line(cx1, gy, cx2, gy,
                                     fill="#585b70", dash=(3, 3), tags="crop")

        # Tay nắm kéo ở 4 góc + 4 cạnh
        hs = self.HANDLE_SIZE
        handles = [
            (cx1, cy1), (cx2, cy1), (cx1, cy2), (cx2, cy2),   # 4 góc
            ((cx1+cx2)/2, cy1), ((cx1+cx2)/2, cy2),           # giữa trên/dưới
            (cx1, (cy1+cy2)/2), (cx2, (cy1+cy2)/2),           # giữa trái/phải
        ]
        for hx, hy in handles:
            self.canvas.create_rectangle(hx - hs, hy - hs, hx + hs, hy + hs,
                                          fill="#89b4fa", outline="#cdd6f4",
                                          width=1, tags="crop")

        # Cập nhật label kích thước
        w, h = int(round(self.crop_w)), int(round(self.crop_h))
        self.size_label.config(text=f"{w} × {h} px")

    # ---- Xác định vùng chuột đang trỏ ----
    def _hit_test(self, cx, cy):
        """Trả về chế độ kéo dựa vào vị trí chuột."""
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
        return "new"    # bấm ngoài -> vẽ crop mới

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
            # Vẽ crop mới từ điểm bấm
            ix, iy = self._cv_to_img(ev.x, ev.y)
            ix = max(0, min(ix, self.img_w))
            iy = max(0, min(iy, self.img_h))
            self.crop_x = min(ox, ix)
            self.crop_y = min(oy, iy)
            self.crop_w = max(1, abs(ix - ox))
            self.crop_h = max(1, abs(iy - oy))
        else:
            # Kéo cạnh/góc
            nx, ny, nw, nh = ox, oy, ow, oh
            # Cạnh TRÁI: nw, sw, e_left
            if mode in ("nw", "sw", "e_left"):
                nw = max(self.MIN_CROP_PX / self.scale, ow - dx)
                nx = ox + ow - nw
            # Cạnh PHẢI: ne, se, e_right
            if mode in ("ne", "se", "e_right"):
                nw = max(self.MIN_CROP_PX / self.scale, ow + dx)
            # Cạnh TRÊN: nw, ne, n
            if mode in ("nw", "ne", "n"):
                nh = max(self.MIN_CROP_PX / self.scale, oh - dy)
                ny = oy + oh - nh
            # Cạnh DƯỚI: sw, se, s
            if mode in ("sw", "se", "s"):
                nh = max(self.MIN_CROP_PX / self.scale, oh + dy)
            # Clamp
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

    # ---- Nút bấm ----
    def _confirm(self):
        # Chỉ crop nếu không phải toàn bộ ảnh
        cx, cy = int(round(self.crop_x)), int(round(self.crop_y))
        cw, ch = int(round(self.crop_w)), int(round(self.crop_h))
        if cx <= 0 and cy <= 0 and cw >= self.img_w and ch >= self.img_h:
            self.callback(None)   # toàn bộ ảnh = không crop
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

    # Kiểu tô của RASTER: khoá config -> nhãn hiển thị
    RASTER_STYLES = {
        'zigzag': 'Zigzag liên tục',
        'hatch':  'Gạch song song',
        'offset': 'Đường đồng mức',
    }

    METHODS = {
        'color':   'Color — Ranh giới màu',
        'portrait': 'Portrait — Chân dung',
        'line':    'Line — Nét đều',
        'contour': 'Contour — Đường viền',
        'raster':  'Raster — Tô vùng',
        'edge':    'Edge — Nét cạnh',
        'text':    'Text — Viết chữ',
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Image to G-Code — Linear System 3 Trục")
        # Co giao diện theo màn hình TRƯỚC khi dựng UI (ui_px/ui_font đọc UI_SCALE)
        fit_ui_scale(self.root)
        win_w, win_h = place_window(self.root, ui_px(BASE_W), ui_px(BASE_H))
        self.root.minsize(min(ui_px(MIN_W), win_w), min(ui_px(MIN_H), win_h))
        self.root.configure(bg="#1e1e2e")

        self.config = MachineConfig()
        self.image_path = None
        self.original_image_path = None   # đường dẫn ảnh GỐC (trước crop)
        self.crop_rect = None             # (x, y, w, h) vùng crop hoặc None
        self.processed_data = None   # contours or binary
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
        # Nút chính — tô đậm để không lẫn vào danh sách nút
        style.configure("Accent.TButton", font=("Segoe UI", ui_font(11), "bold"),
                        foreground="#1e1e2e", background="#89b4fa")
        style.map("Accent.TButton", background=[("active", "#b4befe")])

        # Header
        ttk.Label(self.root, text="Image to G-Code Converter",
                  style="Header.TLabel").pack(pady=(8, 2))
        ttk.Label(self.root,
                  text="Chuyển ảnh → G-Code cho máy Linear System 3 trục X/Y/Z"
                  ).pack(pady=(0, 8))

        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # === LEFT PANEL ===
        left = ttk.Frame(main, width=ui_px(350))
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left.pack_propagate(False)

        # Vùng NÚT — neo ĐÁY và tạo TRƯỚC nên luôn nhìn thấy, dù danh sách tuỳ
        # chọn có dài đến đâu. (Trước đây nút nằm cuối dòng pack nên bị các
        # khung tuỳ chọn đẩy ra ngoài màn hình, không bấm được.)
        bottom = ttk.Frame(left)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        # Vùng TUỲ CHỌN — cuộn được
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

        # File
        ff = ttk.LabelFrame(opts, text="Ảnh đầu vào")
        self.file_frame = ff          # TEXT không cần ảnh -> giấu khung này đi
        ff.pack(fill=tk.X, pady=(0, 4))
        self.file_label = ttk.Label(ff, text="Chưa chọn file...", wraplength=ui_px(280))
        self.file_label.pack(padx=5, pady=4)
        btn_row = ttk.Frame(ff)
        btn_row.pack(fill=tk.X, padx=5, pady=(0, 4))
        ttk.Button(btn_row, text="Chọn ảnh...", command=self._browse).pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.crop_btn = ttk.Button(btn_row, text="Crop ảnh...",
                                    command=self._open_crop_dialog, state=tk.DISABLED)
        self.crop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))
        self.crop_info_label = ttk.Label(ff, text="", foreground="#a6adc8", wraplength=ui_px(280))
        self.crop_info_label.pack(padx=5, pady=(0, 2))

        # Method selection
        mf = ttk.LabelFrame(opts, text="Phương pháp vẽ")
        self.method_frame = mf        # neo để pack lại khung ảnh đúng chỗ
        mf.pack(fill=tk.X, pady=(0, 4))
        self.method_var = tk.StringVar(value='line')
        methods_info = [
            ('color',   'Color',   'Tranh màu phẳng, hoạt hình'),
            ('portrait','Portrait','Ảnh chụp người → nét vẽ'),
            ('line',    'Line',    'Nét đen trắng, độ dày ĐỀU'),
            ('contour', 'Contour', 'Đi theo đường viền vùng tối'),
            ('raster',  'Raster',  'Tô đặc vùng tối bằng nét liên tục'),
            ('edge',    'Edge',    'Phát hiện cạnh, vẽ nét mảnh'),
            ('text',    'Text',    'Gõ chữ → nét viết (không cần ảnh)'),
        ]
        for val, label, desc in methods_info:
            row = ttk.Frame(mf)
            row.pack(fill=tk.X, padx=5, pady=1)
            rb = ttk.Radiobutton(row, text=label, variable=self.method_var,
                                  value=val, command=self._on_method_change)
            rb.pack(side=tk.LEFT)
            ttk.Label(row, text=f"— {desc}", foreground="#a6adc8").pack(side=tk.LEFT)

        # Machine settings
        sf = ttk.LabelFrame(opts, text="Cấu hình máy")
        sf.pack(fill=tk.X, pady=(0, 4))
        settings = [
            ("Vùng vẽ X (mm):", "work_area_x"),
            ("Vùng vẽ Y (mm):", "work_area_y"),
            ("Z nâng bút:", "z_pen_up"),
            ("Z hạ bút:", "z_pen_down"),
            ("Z kết thúc:", "z_end"),
            ("Tốc độ vẽ:", "feed_rate_draw"),
            ("Tốc độ di chuyển:", "feed_rate_travel"),
            ("Tốc độ trục Z:", "feed_rate_z"),
            ("Tốc độ về đỗ:", "feed_rate_return"),
        ]
        self.setting_vars = {}
        for lbl, attr in settings:
            row = ttk.Frame(sf)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=lbl, width=18).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(getattr(self.config, attr)))
            self.setting_vars[attr] = var
            ttk.Entry(row, textvariable=var, width=8).pack(side=tk.RIGHT)

        # --- Đặt ảnh trong vùng vẽ ---
        self._build_place_panel(opts)

        # Định dạng file xuất
        of = ttk.LabelFrame(opts, text="Định dạng file")
        of.pack(fill=tk.X, pady=(0, 4))
        self.linenum_var = tk.BooleanVar(value=self.config.line_numbers)
        ttk.Checkbutton(of, text="Đánh số dòng (N10, N20, ...)",
                        variable=self.linenum_var).pack(padx=5, pady=2, anchor=tk.W)
        self.comments_var = tk.BooleanVar(value=self.config.emit_comments)
        ttk.Checkbutton(of, text="Xuất chú thích ';'",
                        variable=self.comments_var).pack(padx=5, pady=1, anchor=tk.W)
        self.useg0_var = tk.BooleanVar(value=self.config.use_g0)
        ttk.Checkbutton(of, text="Dùng G0 cho di chuyển (tắt = G1)",
                        variable=self.useg0_var).pack(padx=5, pady=(1, 4), anchor=tk.W)

        # Image processing
        pf = ttk.LabelFrame(opts, text="Xử lý ảnh")
        self.proc_frame = pf          # TEXT không xử lý ảnh -> giấu khung này đi
        pf.pack(fill=tk.X, pady=(0, 4))

        # Threshold
        tr = ttk.Frame(pf)
        tr.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(tr, text="Ngưỡng:").pack(side=tk.LEFT)
        self.threshold_var = tk.IntVar(value=self.config.threshold)
        self.thresh_lbl = ttk.Label(tr, text=str(self.config.threshold), width=4)
        self.thresh_lbl.pack(side=tk.RIGHT)
        ttk.Scale(tr, from_=0, to=255, variable=self.threshold_var,
                  orient=tk.HORIZONTAL,
                  command=lambda v: self.thresh_lbl.config(text=str(int(float(v))))
                  ).pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # Simplify (contour/edge)
        self.simp_frame = ttk.Frame(pf)
        self.simp_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(self.simp_frame, text="Đơn giản hóa:").pack(side=tk.LEFT)
        self.simplify_var = tk.DoubleVar(value=self.config.simplify_epsilon)
        ttk.Scale(self.simp_frame, from_=0, to=5, variable=self.simplify_var,
                  orient=tk.HORIZONTAL).pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # Gom nét dày về 1 đường (contour)
        self.ctr_frame = ttk.Frame(pf)
        self.ctr_frame.pack(fill=tk.X, padx=5, pady=2)
        self.ctr_center_var = tk.BooleanVar(value=self.config.contour_centerline)
        ttk.Checkbutton(self.ctr_frame,
                        text="Gom nét dày về 1 đường (đường tâm)",
                        variable=self.ctr_center_var).pack(anchor=tk.W)
        ttk.Label(self.ctr_frame,
                  text="Tắt = đi theo đường bao (nét dày ra 2 đường).",
                  foreground="#a6adc8").pack(anchor=tk.W, padx=(18, 0))

        # Tô vùng (raster)
        self.raster_frame = ttk.Frame(pf)
        self.raster_frame.pack(fill=tk.X, padx=5, pady=2)

        rr0 = ttk.Frame(self.raster_frame)
        rr0.pack(fill=tk.X, pady=1)
        ttk.Label(rr0, text="Kiểu tô:", width=16).pack(side=tk.LEFT)
        self.raster_style_var = tk.StringVar(value=self.RASTER_STYLES[self.config.raster_style])
        ttk.Combobox(rr0, textvariable=self.raster_style_var, state="readonly",
                     values=list(self.RASTER_STYLES.values()), width=17
                     ).pack(side=tk.RIGHT)

        rr1 = ttk.Frame(self.raster_frame)
        rr1.pack(fill=tk.X, pady=1)
        ttk.Label(rr1, text="Cách nét (mm):", width=16).pack(side=tk.LEFT)
        self.raster_res_var = tk.StringVar(value=str(self.config.raster_resolution))
        ttk.Entry(rr1, textvariable=self.raster_res_var, width=6).pack(side=tk.RIGHT)

        rr2 = ttk.Frame(self.raster_frame)
        rr2.pack(fill=tk.X, pady=1)
        ttk.Label(rr2, text="Góc nét (độ):", width=16).pack(side=tk.LEFT)
        self.raster_angle_var = tk.StringVar(value=str(self.config.raster_angle))
        ttk.Entry(rr2, textvariable=self.raster_angle_var, width=6).pack(side=tk.RIGHT)

        rr3 = ttk.Frame(self.raster_frame)
        rr3.pack(fill=tk.X, pady=1)
        ttk.Label(rr3, text="Mịn nội bộ (x):", width=16).pack(side=tk.LEFT)
        self.raster_super_var = tk.StringVar(value=str(self.config.raster_supersample))
        ttk.Entry(rr3, textvariable=self.raster_super_var, width=6).pack(side=tk.RIGHT)

        rr4 = ttk.Frame(self.raster_frame)
        rr4.pack(fill=tk.X, pady=1)
        ttk.Label(rr4, text="Làm mượt:", width=16).pack(side=tk.LEFT)
        self.raster_smooth_var = tk.StringVar(value=str(self.config.raster_smooth))
        ttk.Entry(rr4, textvariable=self.raster_smooth_var, width=6).pack(side=tk.RIGHT)

        self.raster_cross_var = tk.BooleanVar(value=self.config.raster_cross)
        ttk.Checkbutton(self.raster_frame, text="Tô chéo 2 lớp (đậm hơn)",
                        variable=self.raster_cross_var).pack(anchor=tk.W, pady=1)
        self.raster_outline_var = tk.BooleanVar(value=self.config.raster_outline)
        ttk.Checkbutton(self.raster_frame, text="Vẽ đường bao trước (cạnh sắc)",
                        variable=self.raster_outline_var).pack(anchor=tk.W, pady=1)
        ttk.Label(self.raster_frame,
                  text="Cách nét = bề rộng nét bút. Nhiều nét quá\n"
                       "→ TĂNG; hở kẽ trắng → GIẢM.",
                  foreground="#a6adc8", justify=tk.LEFT).pack(anchor=tk.W, pady=(1, 2))

        # Canny thresholds (edge)
        self.canny_frame = ttk.Frame(pf)
        self.canny_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(self.canny_frame, text="Canny:").pack(side=tk.LEFT)
        self.canny_low_var = tk.StringVar(value=str(self.config.canny_low))
        self.canny_high_var = tk.StringVar(value=str(self.config.canny_high))
        ttk.Entry(self.canny_frame, textvariable=self.canny_high_var, width=5).pack(side=tk.RIGHT)
        ttk.Label(self.canny_frame, text="—").pack(side=tk.RIGHT)
        ttk.Entry(self.canny_frame, textvariable=self.canny_low_var, width=5).pack(side=tk.RIGHT)

        # Invert
        self.invert_var = tk.BooleanVar(value=self.config.invert)
        ttk.Checkbutton(pf, text="Đảo màu (vẽ phần tối)", variable=self.invert_var
                        ).pack(padx=5, pady=2, anchor=tk.W)

        # Neo TĨNH ngay sau khung "Xử lý ảnh" — pack(before=...) cần một widget
        # luôn hiển thị, mà chính khung đó lại bị giấu khi chọn TEXT.
        self.proc_tail = ttk.Frame(opts)
        self.proc_tail.pack(fill=tk.X)

        # --- Nét đều (phương pháp LINE) ---
        self.line_frame = ttk.LabelFrame(opts, text="Nét vẽ")
        self.line_frame.pack(fill=tk.X, pady=(0, 4))
        self.uniform_var = tk.BooleanVar(value=self.config.uniform_stroke)
        ttk.Checkbutton(self.line_frame,
                        text="Nét ĐỀU (skeleton) — bỏ nét lớn/nhỏ",
                        variable=self.uniform_var).pack(padx=5, pady=2, anchor=tk.W)
        self.adaptive_var = tk.BooleanVar(value=self.config.adaptive_threshold)
        ttk.Checkbutton(self.line_frame, text="Ngưỡng thích ứng (ảnh sáng lệch)",
                        variable=self.adaptive_var).pack(padx=5, pady=1, anchor=tk.W)
        self.despeckle_var = tk.BooleanVar(value=self.config.despeckle)
        ttk.Checkbutton(self.line_frame, text="Xoá đốm nhiễu",
                        variable=self.despeckle_var).pack(padx=5, pady=1, anchor=tk.W)
        r1 = ttk.Frame(self.line_frame)
        r1.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(r1, text="Bỏ nét ngắn hơn (px):", width=21).pack(side=tk.LEFT)
        self.line_minlen_var = tk.StringVar(value=str(self.config.line_min_length))
        ttk.Entry(r1, textvariable=self.line_minlen_var, width=6).pack(side=tk.RIGHT)
        r2 = ttk.Frame(self.line_frame)
        r2.pack(fill=tk.X, padx=5, pady=(1, 4))
        ttk.Label(r2, text="Làm gọn điểm (px):", width=21).pack(side=tk.LEFT)
        self.line_simp_var = tk.StringVar(value=str(self.config.line_simplify))
        ttk.Entry(r2, textvariable=self.line_simp_var, width=6).pack(side=tk.RIGHT)

        r3 = ttk.Frame(self.line_frame)
        r3.pack(fill=tk.X, padx=5, pady=(1, 4))
        ttk.Label(r3, text="Khép khe (px):", width=21).pack(side=tk.LEFT)
        self.line_bridge_var = tk.StringVar(value=str(self.config.line_bridge_px))
        ttk.Entry(r3, textvariable=self.line_bridge_var, width=6).pack(side=tk.RIGHT)

        # --- Ranh giới màu (phương pháp COLOR) ---
        self.color_frame = ttk.LabelFrame(opts, text="Ranh giới màu")
        self.color_frame.pack(fill=tk.X, pady=(0, 4))
        for lbl, attr, var_name in [
                ("Số nhóm màu:", "color_levels", "cl_levels_var"),
                ("Khử nhiễu (lẻ, 0=tắt):", "color_denoise", "cl_denoise_var"),
                ("Bỏ mảnh nhỏ hơn (px):", "color_min_area", "cl_area_var")]:
            row = ttk.Frame(self.color_frame)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=lbl, width=21).pack(side=tk.LEFT)
            v = tk.StringVar(value=str(getattr(self.config, attr)))
            setattr(self, var_name, v)
            ttk.Entry(row, textvariable=v, width=6).pack(side=tk.RIGHT)
        ttk.Label(self.color_frame,
                  text="Thiếu nét → TĂNG số nhóm màu.\n"
                       "Rối/nhiều nét thừa → GIẢM (4–6).",
                  foreground="#a6adc8", justify=tk.LEFT).pack(padx=5, pady=(2, 4),
                                                              anchor=tk.W)

        # --- Chân dung (phương pháp PORTRAIT) ---
        self.portrait_frame = ttk.LabelFrame(opts, text="Chân dung (XDoG)")
        self.portrait_frame.pack(fill=tk.X, pady=(0, 4))
        for lbl, attr, var_name in [
                ("Ngưỡng nét (σ):", "portrait_sensitivity", "pt_thresh_var"),
                ("Chi tiết σ (nhỏ=vụn):", "portrait_detail", "pt_detail_var"),
                ("Khử nhiễu da:", "portrait_denoise", "pt_denoise_var"),
                ("Bỏ đốm nhỏ hơn (px):", "portrait_min_area", "pt_area_var")]:
            row = ttk.Frame(self.portrait_frame)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=lbl, width=21).pack(side=tk.LEFT)
            v = tk.StringVar(value=str(getattr(self.config, attr)))
            setattr(self, var_name, v)
            ttk.Entry(row, textvariable=v, width=6).pack(side=tk.RIGHT)
        ttk.Label(self.portrait_frame,
                  text="Thiếu nét → GIẢM ngưỡng (vd 0.4).\n"
                       "Rối/nhiều rác → TĂNG ngưỡng (vd 0.9)\n"
                       "hoặc tăng 'bỏ đốm nhỏ'.",
                  foreground="#a6adc8", justify=tk.LEFT).pack(padx=5, pady=(2, 4),
                                                              anchor=tk.W)

        # --- Viết chữ (phương pháp TEXT) ---
        self.text_frame = ttk.LabelFrame(opts, text="Nội dung chữ")
        self.text_frame.pack(fill=tk.X, pady=(0, 4))
        self.text_input = tk.Text(self.text_frame, height=4, bg="#313244",
                                  fg="#cdd6f4", insertbackground="#cdd6f4",
                                  relief=tk.FLAT, wrap=tk.WORD,
                                  font=("Segoe UI", ui_font(11)))
        self.text_input.insert("1.0", self.config.text_content)
        self.text_input.pack(fill=tk.X, padx=5, pady=(4, 2))
        ttk.Label(self.text_frame,
                  text="Enter = xuống dòng. Gõ tiếng Việt có dấu bình thường.",
                  foreground="#a6adc8").pack(padx=5, anchor=tk.W)

        rowf = ttk.Frame(self.text_frame)
        rowf.pack(fill=tk.X, padx=5, pady=(4, 1))
        ttk.Label(rowf, text="Font:", width=13).pack(side=tk.LEFT)
        self.txt_font_var = tk.StringVar(value=self.config.text_font)
        ttk.Combobox(rowf, textvariable=self.txt_font_var,
                     values=list(list_system_fonts().keys()), width=15,
                     font=("Segoe UI", ui_font(9))).pack(side=tk.RIGHT)

        for lbl, attr, var_name in [
                ("Cỡ chữ HOA (mm):", "text_height", "txt_size_var"),
                ("Giãn dòng (lần):", "text_line_spacing", "txt_spacing_var"),
                ("Lề (mm):", "text_margin", "txt_margin_var"),
                ("Độ mịn (px/mm):", "text_render_scale", "txt_scale_var")]:
            row = ttk.Frame(self.text_frame)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=lbl, width=21).pack(side=tk.LEFT)
            v = tk.StringVar(value=str(getattr(self.config, attr)))
            setattr(self, var_name, v)
            ttk.Entry(row, textvariable=v, width=6).pack(side=tk.RIGHT)

        rowa = ttk.Frame(self.text_frame)
        rowa.pack(fill=tk.X, padx=5, pady=(3, 1))
        ttk.Label(rowa, text="Canh lề:", width=13).pack(side=tk.LEFT)
        self.txt_align_var = tk.StringVar(value=self.config.text_align)
        for val, lab in (("left", "Trái"), ("center", "Giữa"), ("right", "Phải")):
            ttk.Radiobutton(rowa, text=lab, value=val,
                            variable=self.txt_align_var).pack(side=tk.LEFT, padx=2)

        rows = ttk.Frame(self.text_frame)
        rows.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(rows, text="Kiểu chữ:", width=13).pack(side=tk.LEFT)
        self.txt_style_var = tk.StringVar(value=self.config.text_style)
        ttk.Radiobutton(rows, text="Nét đơn", value="single",
                        variable=self.txt_style_var).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(rows, text="Viền chữ", value="outline",
                        variable=self.txt_style_var).pack(side=tk.LEFT, padx=2)

        self.txt_autofit_var = tk.BooleanVar(value=self.config.text_autofit)
        ttk.Checkbutton(self.text_frame, text="Tự phóng chữ cho kín vùng vẽ",
                        variable=self.txt_autofit_var).pack(padx=5, pady=1, anchor=tk.W)

        rowm = ttk.Frame(self.text_frame)
        rowm.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(rowm, text="Bỏ nét ngắn hơn (px):", width=21).pack(side=tk.LEFT)
        ttk.Entry(rowm, textvariable=self.line_minlen_var, width=6).pack(side=tk.RIGHT)

        ttk.Label(self.text_frame,
                  text="Nét đơn = bút đi MỘT đường như viết tay.\n"
                       "Viền chữ = chữ rỗng, đi quanh mép chữ.\n"
                       "Mất dấu/chấm chữ i → GIẢM 'bỏ nét ngắn'\n"
                       "hoặc TĂNG cỡ chữ / độ mịn.",
                  foreground="#a6adc8", justify=tk.LEFT).pack(padx=5, pady=(2, 4),
                                                              anchor=tk.W)

        # --- Cung tròn G2/G3 ---
        self.arc_frame = ttk.LabelFrame(opts, text="◟ Cung tròn G2/G3 (I/J)")
        self.arc_frame.pack(fill=tk.X, pady=(0, 4))
        self.arcs_var = tk.BooleanVar(value=self.config.use_arcs)
        ttk.Checkbutton(self.arc_frame,
                        text="Dùng G2/G3 thay vì nhiều G1 ngắn",
                        variable=self.arcs_var).pack(padx=5, pady=2, anchor=tk.W)
        r3 = ttk.Frame(self.arc_frame)
        r3.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(r3, text="Sai số khớp cung (mm):", width=21).pack(side=tk.LEFT)
        self.arc_tol_var = tk.StringVar(value=str(self.config.arc_tolerance))
        ttk.Entry(r3, textvariable=self.arc_tol_var, width=6).pack(side=tk.RIGHT)
        r4 = ttk.Frame(self.arc_frame)
        r4.pack(fill=tk.X, padx=5, pady=(1, 4))
        ttk.Label(r4, text="Số điểm tối thiểu:", width=21).pack(side=tk.LEFT)
        self.arc_minpts_var = tk.StringVar(value=str(self.config.arc_min_points))
        ttk.Entry(r4, textvariable=self.arc_minpts_var, width=6).pack(side=tk.RIGHT)

        # Mốc cuối vùng tuỳ chọn — dùng làm neo khi pack lại line_frame/arc_frame
        # (pack(before=...) yêu cầu cùng widget cha, mà các nút nay ở khung khác)
        self.opts_tail = ttk.Frame(opts)
        self.opts_tail.pack(fill=tk.X)

        # === Vùng nút cố định ở đáy ===
        bf = ttk.LabelFrame(bottom, text="Thực hiện")
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="1. Xem trước nét vẽ",
                   command=self._preview).pack(fill=tk.X, padx=5, pady=(4, 2))
        ttk.Button(bf, text="2. TẠO G-CODE",
                   style="Accent.TButton",
                   command=self._generate).pack(fill=tk.X, padx=5, pady=2)
        self.save_btn = ttk.Button(bf, text="3. Lưu file .gcode",
                                   command=self._save, state=tk.DISABLED)
        self.save_btn.pack(fill=tk.X, padx=5, pady=(2, 5))

        self.status_label = ttk.Label(bottom, text="Sẵn sàng — chọn ảnh để bắt đầu.",
                                      foreground="#a6e3a1", wraplength=ui_px(330))
        self.status_label.pack(pady=3)

        # Info
        self.info_text = tk.Text(bottom, height=7, bg="#313244", fg="#cdd6f4",
                                  font=("Consolas", ui_font(9)), relief=tk.FLAT, wrap=tk.WORD)
        self.info_text.pack(fill=tk.X)

        # === RIGHT PANEL ===
        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # View buttons
        vf = ttk.Frame(right)
        vf.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(vf, text="Xem:", style="Header.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.view_btn_frame = vf

        # Method description
        self.method_desc = ttk.Label(right, text="", style="Method.TLabel")
        self.method_desc.pack(pady=(0, 2))
        self.view_desc = ttk.Label(right, text="", foreground="#a6adc8")
        self.view_desc.pack(pady=(0, 3))

        self.canvas = tk.Canvas(right, bg="#313244", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Legend
        self.legend_frame = ttk.Frame(right)
        self.legend_frame.pack(fill=tk.X, pady=(3, 0))
        self.legend_frame.pack_forget()

        self._on_method_change()  # Show/hide method-specific controls

    # ========================================================
    # KHUNG ĐẶT ẢNH — kéo thả trực tiếp trên hình vùng vẽ
    # ========================================================
    PLACE_PAD = 14          # lề quanh vùng vẽ trong ô xem trước (px)
    PLACE_GRIP = 11         # cỡ tay nắm kéo góc (px)

    def _build_place_panel(self, parent):
        # Đặt trước khi tạo widget: ô nhập có trace, đụng tới mấy biến này ngay
        self._place_drag_mode = None
        self._place_syncing = False
        self._img_aspect_cache = {}

        pf = ttk.LabelFrame(parent, text="Đặt ảnh trong vùng vẽ")
        pf.pack(fill=tk.X, pady=(0, 4))

        self.place_manual_var = tk.BooleanVar(value=self.config.place_mode == 'manual')
        ttk.Checkbutton(pf, text="Tự đặt (bỏ canh giữa)",
                        variable=self.place_manual_var,
                        command=self._place_mode_changed).pack(padx=5, pady=(3, 0), anchor=tk.W)
        self.place_ratio_var = tk.BooleanVar(value=self.config.place_keep_ratio)
        ttk.Checkbutton(pf, text="Giữ tỉ lệ ảnh (không kéo méo)",
                        variable=self.place_ratio_var,
                        command=self._place_ratio_changed).pack(padx=5, pady=(0, 3), anchor=tk.W)

        # Ô kéo thả: hình vuông mô phỏng vùng vẽ, kéo để đổi chỗ, kéo góc để phóng to
        side = ui_px(226)
        self.place_canvas = tk.Canvas(pf, width=side, height=side, bg="#181825",
                                      highlightthickness=0, cursor="hand2")
        self.place_canvas.pack(padx=5, pady=3)
        self.place_canvas.bind("<Button-1>", self._place_press)
        self.place_canvas.bind("<B1-Motion>", self._place_drag)
        self.place_canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_place_drag_mode", None))

        # Ô nhập số cho ai muốn đặt chính xác
        self.place_vars = {}
        grid = ttk.Frame(pf)
        grid.pack(fill=tk.X, padx=5, pady=(0, 4))
        for col, (attr, lbl) in enumerate([("place_x", "X"), ("place_y", "Y"),
                                           ("place_w", "Rộng"), ("place_h", "Cao")]):
            cell = ttk.Frame(grid)
            cell.grid(row=col // 2, column=col % 2, sticky="ew", padx=(0, 4), pady=1)
            grid.columnconfigure(col % 2, weight=1)
            ttk.Label(cell, text=f"{lbl}:", width=5).pack(side=tk.LEFT)
            var = tk.StringVar(value=f"{getattr(self.config, attr):g}")
            var.trace_add("write", lambda *_: self._place_from_entries())
            self.place_vars[attr] = var
            ttk.Entry(cell, textvariable=var, width=6).pack(side=tk.LEFT)

        btns = ttk.Frame(pf)
        btns.pack(fill=tk.X, padx=5, pady=(0, 5))
        ttk.Button(btns, text="Kín vùng vẽ",
                   command=lambda: self._place_preset("full")).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(btns, text="Vào giữa",
                   command=lambda: self._place_preset("center")).pack(side=tk.LEFT, expand=True,
                                                                      fill=tk.X, padx=(4, 0))

        self.place_hint = ttk.Label(pf, text="", foreground="#a6adc8", wraplength=ui_px(215))
        self.place_hint.pack(padx=5, pady=(0, 4), anchor="w")

        self.place_canvas.after(60, self._place_redraw)

    # ---- quy đổi mm <-> pixel trong ô xem trước ----
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
        """Tỉ lệ rộng/cao của ảnh đang chọn (None = chưa có ảnh)."""
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

        # Vùng vẽ + lưới 10mm
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
            c.create_rectangle(px1 - gs, py0 - gs, px1, py0, fill=col, outline="")  # tay nắm góc

        # Gốc toạ độ máy
        c.create_oval(x0 - 3, y0 - 3, x0 + 3, y0 + 3, fill="#f38ba8", outline="")
        c.create_text(x0 + 4, y0 - 8, text="0,0", anchor="sw", fill="#f38ba8",
                      font=("Segoe UI", ui_font(8)))

        if manual:
            self.place_hint.config(
                text=f"Kéo khung để đổi chỗ, kéo ô góc dưới-phải để phóng to/thu nhỏ. "
                     f"Nét vẽ sẽ nằm gọn trong {bw:.0f}×{bh:.0f} mm tại X{bx:.0f} Y{by:.0f}.")
        else:
            self.place_hint.config(text="Đang phủ kín vùng vẽ và canh giữa. "
                                        "Tích 'Tự đặt' để tự chọn chỗ và cỡ.")

    # ---- thao tác chuột ----
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
            # Kéo góc dưới-phải: mép trái/trên đứng yên, khung nở theo con trỏ
            top = cfg.place_y + cfg.place_h
            w = max(5.0, min(cfg.work_area_x - cfg.place_x, mx - cfg.place_x))
            h = max(5.0, min(top, top - my))
            aspect = self._img_aspect()
            if self.place_ratio_var.get() and aspect:
                h = w / aspect                      # bám tỉ lệ ảnh, không méo
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

    # ---- đồng bộ ô nhập <-> hình ----
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
        else:                                   # về giữa, giữ nguyên cỡ
            cfg.place_x = (cfg.work_area_x - cfg.place_w) / 2
            cfg.place_y = (cfg.work_area_y - cfg.place_h) / 2
        self._place_to_entries()
        self._place_redraw()

    # --- Method change ---
    def _on_method_change(self):
        m = self.method_var.get()
        self.current_method = m

        # TEXT là phương pháp duy nhất không có ảnh đầu vào -> giấu luôn khung
        # chọn ảnh và khung xử lý ảnh (ngưỡng/đảo màu không có tác dụng gì).
        if m == 'text':
            self.file_frame.pack_forget()
            self.proc_frame.pack_forget()
            self.text_frame.pack(fill=tk.X, pady=(0, 4), before=self.opts_tail)
        else:
            self.file_frame.pack(fill=tk.X, pady=(0, 4), before=self.method_frame)
            self.proc_frame.pack(fill=tk.X, pady=(0, 4), before=self.proc_tail)
            self.text_frame.pack_forget()

        # Show/hide controls
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

        # Gom nét dày về 1 đường — chỉ có nghĩa với CONTOUR
        if m == 'contour':
            self.ctr_frame.pack(fill=tk.X, padx=5, pady=2)
        else:
            self.ctr_frame.pack_forget()

        # Khung "Nét vẽ" chỉ cho LINE; cung G2/G3 áp dụng cho mọi phương pháp
        # đi theo đường (raster quét hàng ngang nên không dùng cung).
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
        # Cung G2/G3 dùng được cho mọi phương pháp, kể cả RASTER kiểu
        # "đường đồng mức" (nét tô là các vòng cong bám theo hình).
        self.arc_frame.pack(fill=tk.X, pady=(0, 4), before=self.opts_tail)

        descriptions = {
            'color': ' COLOR — Vẽ nét ở ranh giới giữa các vùng MÀU (hoạt hình, logo, vector)',
            'portrait': ' PORTRAIT — Ảnh chụp người → nét vẽ chân dung (XDoG), vẽ bằng cung G2/G3',
            'line': ' LINE — Ảnh → nét đen trắng ĐỀU (skeleton), vẽ bằng cung G2/G3',
            'contour': ' CONTOUR — Đi theo đường viền vùng tối; nét dày được gom về MỘT đường tâm',
            'raster': ' RASTER — Tô đặc vùng tối bằng nét LIÊN TỤC, ít nhấc bút (zigzag / gạch / đồng mức)',
            'edge': ' EDGE — Phát hiện cạnh bằng Canny, vẽ theo các nét mảnh',
            'text': ' TEXT — Gõ chữ (có dấu) → nét viết tay bằng font hệ thống, không cần ảnh',
        }
        if hasattr(self, 'method_desc'):
            self.method_desc.config(text=descriptions.get(m, ''))

    # --- View management ---
    def _update_view_buttons(self, view_modes):
        """Cập nhật các nút xem theo phương pháp."""
        # Xóa nút cũ (giữ label đầu tiên)
        for w in self.view_btn_frame.winfo_children()[1:]:
            w.destroy()
        for mode, label in view_modes:
            btn = ttk.Button(self.view_btn_frame, text=label,
                             command=lambda m=mode: self._switch_view(m))
            btn.pack(side=tk.LEFT, padx=2)

    def _switch_view(self, mode):
        if mode not in self.preview_images:
            messagebox.showinfo("Thông báo", "Nhấn 'Xem trước' trước!")
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
            'original': ' Ảnh gốc đầu vào',
            'preview': {
                'contour': 'Contour: đường trắng = máy sẽ VẼ | Xanh = điểm đầu',
                'raster': ' Nét tô: trắng = máy VẼ | Xanh = chỗ HẠ BÚT',
                'edge': 'Edge: đường trắng = nét máy sẽ VẼ | Xanh = điểm đầu',
            }.get(self.current_method, ''),
            'overlay': 'Contour/Edge chồng lên ảnh gốc',
            'binary': ' Nhị phân: TRẮNG = vùng cần tô | ĐEN = bỏ qua',
            'raster': ' Đường chạy: trắng = nét vẽ | đỏ = di chuyển khi NHẤC BÚT',
            'canny_raw': ' Ảnh Canny edge thô (trước khi tìm nét)',
        }
        self.view_desc.config(text=descs.get(self.current_view, ''))

        # Legend
        self.legend_frame.pack_forget()
        for w in self.legend_frame.winfo_children():
            w.destroy()
        if self.current_view in ('preview', 'raster'):
            items = [
                (" Trắng = nét vẽ (bút hạ)", "#ffffff"),
                (" Đỏ = di chuyển (bút nâng)", "#f38ba8"),
                (" Xanh = điểm đầu", "#a6e3a1"),
            ]
            for txt, clr in items:
                ttk.Label(self.legend_frame, text=txt, foreground=clr).pack(side=tk.LEFT, padx=6)
            self.legend_frame.pack(fill=tk.X, pady=(3, 0))

    # --- Browse ---
    def _browse(self):
        path = filedialog.askopenfilename(
            title="Chọn ảnh",
            filetypes=[("Ảnh", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"), ("Tất cả", "*.*")]
        )
        if path:
            self.image_path = path
            self.original_image_path = path
            self.crop_rect = None        # ảnh mới -> bỏ crop cũ
            self.crop_info_label.config(text="")
            self.gcode = None            # ảnh mới -> G-Code cũ không còn đúng
            self.save_btn.config(state=tk.DISABLED)
            self.crop_btn.config(state=tk.NORMAL)
            self.file_label.config(text=os.path.basename(path))
            self._place_redraw()         # khung đặt ảnh vẽ theo tỉ lệ ảnh mới
            try:
                img = Image.open(path)
                self.preview_images = {'original': img}
                self.current_view = 'original'
                self._update_view_buttons([('original', ' Ảnh gốc')])
                self._display_view()
            except Exception as e:
                pass
            self.status_label.config(text=f"Đã chọn: {os.path.basename(path)}", foreground="#a6e3a1")

    # --- Crop ---
    def _get_effective_image_path(self):
        """Trả về đường dẫn ảnh để xử lý: nếu có crop thì tạo file tạm đã crop."""
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
        # Lưu file tạm cạnh file gốc
        base, ext = os.path.splitext(self.original_image_path)
        crop_path = base + "_crop" + (ext if ext else ".png")
        cv2.imwrite(crop_path, cropped)
        self.image_path = crop_path
        return crop_path

    def _open_crop_dialog(self):
        """Mở cửa sổ crop ảnh với khung kéo thả."""
        src_path = self.original_image_path or self.image_path
        if not src_path:
            messagebox.showwarning("Cảnh báo", "Chọn ảnh trước!")
            return
        try:
            pil_img = Image.open(src_path)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không mở được ảnh: {e}")
            return

        CropDialog(self.root, pil_img, self.crop_rect, self._on_crop_done)

    def _on_crop_done(self, rect):
        """Callback khi người dùng xác nhận crop. rect = (x,y,w,h) hoặc None."""
        self.crop_rect = rect
        if rect is None:
            self.crop_info_label.config(text="")
            # Khôi phục ảnh gốc
            if self.original_image_path:
                self.image_path = self.original_image_path
            self.status_label.config(text="Đã bỏ crop — dùng ảnh gốc.", foreground="#a6e3a1")
        else:
            cx, cy, cw, ch = rect
            self.crop_info_label.config(
                text=f" Crop: {int(cw)}×{int(ch)} px tại ({int(cx)}, {int(cy)})")
            self._get_effective_image_path()
            self.status_label.config(
                text=f" Đã crop: {int(cw)}×{int(ch)} px", foreground="#a6e3a1")
        self.gcode = None
        self.save_btn.config(state=tk.DISABLED)
        self._img_aspect_cache.clear()
        self._place_redraw()
        # Cập nhật preview
        try:
            img = Image.open(self.image_path)
            self.preview_images = {'original': img}
            self.current_view = 'original'
            self._update_view_buttons([('original', ' Ảnh gốc')])
            self._display_view()
        except Exception:
            pass

    # --- Apply settings ---
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
        # Nét vẽ (LINE)
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
        # Ranh giới màu
        for attr, var_name, cast in [
                ("color_levels", "cl_levels_var", int),
                ("color_denoise", "cl_denoise_var", int),
                ("color_min_area", "cl_area_var", int)]:
            try:
                setattr(self.config, attr, cast(getattr(self, var_name).get()))
            except ValueError:
                pass
        # Chân dung
        for attr, var_name, cast in [
                ("portrait_sensitivity", "pt_thresh_var", float),
                ("portrait_detail", "pt_detail_var", float),
                ("portrait_denoise", "pt_denoise_var", float),
                ("portrait_min_area", "pt_area_var", int)]:
            try:
                setattr(self.config, attr, cast(getattr(self, var_name).get()))
            except ValueError:
                pass
        # Viết chữ
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
        # Cung tròn G2/G3
        self.config.use_arcs = self.arcs_var.get()
        try:
            self.config.arc_tolerance = float(self.arc_tol_var.get())
            self.config.arc_min_points = int(self.arc_minpts_var.get())
        except ValueError:
            pass
        # Đặt ảnh trong vùng vẽ
        self.config.place_mode = 'manual' if self.place_manual_var.get() else 'fit'
        self.config.place_keep_ratio = self.place_ratio_var.get()
        self._place_from_entries()
        # Đảm bảo file crop luôn cập nhật
        if self.crop_rect is not None:
            self._get_effective_image_path()

    # --- Preview ---
    def _preview(self):
        m = self.current_method
        if m != 'text' and not self.image_path:
            messagebox.showwarning("Cảnh báo", "Chọn ảnh trước!")
            return
        self._apply()
        self.status_label.config(text="Đang xử lý...", foreground="#f9e2af")
        self.root.update()

        try:
            if m == 'color':
                data, imgs_cv, w, h, info = process_color(self.image_path, self.config)
                views = [('original',' Gốc'), ('preview',' Nét'),
                         ('quant',' Gom màu'), ('overlay',' Chồng lớp')]
            elif m == 'portrait':
                data, imgs_cv, w, h, info = process_portrait(self.image_path, self.config)
                views = [('original',' Gốc'), ('preview',' Nét chân dung'),
                         ('ink',' XDoG'), ('stroke',' Skeleton'),
                         ('overlay',' Chồng lớp')]
            elif m == 'line':
                data, imgs_cv, w, h, info = process_line(self.image_path, self.config)
                views = [('original',' Gốc'), ('preview',' Nét vẽ'),
                         ('stroke',' Nhị phân/Skeleton'), ('overlay',' Chồng lớp')]
            elif m == 'contour':
                data, imgs_cv, w, h, info = process_contour(self.image_path, self.config)
                views = [('original',' Gốc'), ('preview','Contour'), ('overlay',' Chồng lớp')]
                if 'stroke' in imgs_cv:      # chế độ đường tâm có thêm ảnh nét 1px
                    views.append(('stroke', ' Nét 1px'))
            elif m == 'raster':
                data, imgs_cv, w, h, info = process_raster(self.image_path, self.config)
                views = [('original',' Gốc'), ('preview',' Nét tô'),
                         ('raster',' Đường chạy'), ('binary',' Nhị phân'),
                         ('overlay',' Chồng lớp')]
            elif m == 'edge':
                data, imgs_cv, w, h, info = process_edge(self.image_path, self.config)
                views = [('original',' Gốc'), ('preview',' Nét Edge'),
                         ('overlay',' Chồng lớp'), ('canny_raw',' Canny thô')]
            elif m == 'text':
                data, imgs_cv, w, h, info = process_text(self.config)
                views = [('original',' Chữ'), ('preview',' Nét viết'),
                         ('stroke',' Skeleton/Nhị phân'), ('overlay',' Chồng lớp')]

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
            self.info_text.insert(tk.END, f"Phương pháp: {self.METHODS[m]}\n")
            self.info_text.insert(tk.END, f"Ảnh: {w} x {h} px\n")
            self.info_text.insert(tk.END, f"{info}\n")
            self.info_text.insert(tk.END, f"\nDùng nút phía trên để chuyển chế độ xem.\n")

        except Exception as e:
            self.status_label.config(text=f" {e}", foreground="#f38ba8")
            messagebox.showerror("Lỗi", str(e))

    # --- Generate ---
    def _generate(self):
        m = self.current_method
        if m != 'text' and not self.image_path:
            messagebox.showwarning("Cảnh báo", "Chọn ảnh trước!")
            return
        self._apply()
        self.status_label.config(text="Đang tạo G-Code...", foreground="#f9e2af")
        self.root.update()

        try:
            if m == 'color':
                data, imgs_cv, w, h, info = process_color(self.image_path, self.config)
                self.gcode, stats = generate_gcode_color(data, w, h, self.config)
                stat_text = (f"Nét: {stats['lines_count']}\n"
                             f"Cung G2/G3: {stats['arcs']} | G1: {stats['segments']}\n"
                             f"Vẽ: {stats['draw_dist']:.1f}mm\n"
                             f"Di chuyển: {stats['travel_dist']:.1f}mm\n"
                             f"Thời gian: ~{stats['est_time']:.1f} phút")
                views = [('original',' Gốc'), ('preview',' Nét'),
                         ('quant',' Gom màu'), ('overlay',' Chồng lớp')]

            elif m == 'portrait':
                data, imgs_cv, w, h, info = process_portrait(self.image_path, self.config)
                self.gcode, stats = generate_gcode_portrait(data, w, h, self.config)
                stat_text = (f"Nét: {stats['lines_count']}\n"
                             f"Cung G2/G3: {stats['arcs']} | G1: {stats['segments']}\n"
                             f"Vẽ: {stats['draw_dist']:.1f}mm\n"
                             f"Di chuyển: {stats['travel_dist']:.1f}mm\n"
                             f"Thời gian: ~{stats['est_time']:.1f} phút")
                views = [('original',' Gốc'), ('preview',' Nét chân dung'),
                         ('ink',' XDoG'), ('stroke',' Skeleton'),
                         ('overlay',' Chồng lớp')]

            elif m == 'line':
                data, imgs_cv, w, h, info = process_line(self.image_path, self.config)
                self.gcode, stats = generate_gcode_line(data, w, h, self.config)
                stat_text = (f"Nét: {stats['lines_count']}\n"
                             f"Cung G2/G3: {stats['arcs']} | G1: {stats['segments']}\n"
                             f"Vẽ: {stats['draw_dist']:.1f}mm\n"
                             f"Di chuyển: {stats['travel_dist']:.1f}mm\n"
                             f"Thời gian: ~{stats['est_time']:.1f} phút")
                views = [('original',' Gốc'), ('preview',' Nét vẽ'),
                         ('stroke',' Nhị phân/Skeleton'), ('overlay',' Chồng lớp')]

            elif m == 'contour':
                data, imgs_cv, w, h, info = process_contour(self.image_path, self.config)
                self.gcode, stats = generate_gcode_contour(data, w, h, self.config)
                stat_text = (f"Contour: {stats['contours']}\n"
                             f"Vẽ: {stats['draw_dist']:.1f}mm\n"
                             f"Di chuyển: {stats['travel_dist']:.1f}mm\n"
                             f"Thời gian: ~{stats['est_time']:.1f} phút")
                views = [('original',' Gốc'), ('preview','Contour'), ('overlay',' Chồng lớp')]
                if 'stroke' in imgs_cv:
                    views.append(('stroke', ' Nét 1px'))

            elif m == 'raster':
                data, imgs_cv, w, h, info = process_raster(self.image_path, self.config)
                self.gcode, stats = generate_gcode_raster(data, w, h, self.config)
                stat_text = (f"Nét: {stats['strokes']} (= số lần nhấc bút)\n"
                             f"Điểm: {stats['points']}\n"
                             f"Vẽ: {stats['draw_dist']:.1f}mm\n"
                             f"Di chuyển: {stats['travel_dist']:.1f}mm\n"
                             f"Thời gian: ~{stats['est_time']:.1f} phút")
                views = [('original',' Gốc'), ('preview',' Nét tô'),
                         ('raster',' Đường chạy'), ('binary',' Nhị phân'),
                         ('overlay',' Chồng lớp')]

            elif m == 'edge':
                data, imgs_cv, w, h, info = process_edge(self.image_path, self.config)
                self.gcode, stats = generate_gcode_edge(data, w, h, self.config)
                stat_text = (f"Nét: {stats['edges']}\n"
                             f"Vẽ: {stats['draw_dist']:.1f}mm\n"
                             f"Di chuyển: {stats['travel_dist']:.1f}mm\n"
                             f"Thời gian: ~{stats['est_time']:.1f} phút")
                views = [('original',' Gốc'), ('preview',' Nét Edge'),
                         ('overlay',' Chồng lớp'), ('canny_raw',' Canny thô')]

            elif m == 'text':
                data, imgs_cv, w, h, info = process_text(self.config)
                self.gcode, stats = generate_gcode_text(data, w, h, self.config)
                stat_text = (f"Nét: {stats['lines_count']}\n"
                             f"Cung G2/G3: {stats['arcs']} | G1: {stats['segments']}\n"
                             f"Vẽ: {stats['draw_dist']:.1f}mm\n"
                             f"Di chuyển: {stats['travel_dist']:.1f}mm\n"
                             f"Thời gian: ~{stats['est_time']:.1f} phút")
                views = [('original',' Chữ'), ('preview',' Nét viết'),
                         ('stroke',' Skeleton/Nhị phân'), ('overlay',' Chồng lớp')]

            # Update preview images
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
            # Đã có G-Code -> mở khoá nút lưu file
            self.save_btn.config(state=tk.NORMAL)
            self.status_label.config(
                text=f" G-Code: {num_lines} dòng | ~{stats['est_time']:.1f} phút"
                     " — bấm '3. Lưu file .gcode'",
                foreground="#a6e3a1"
            )

            self.info_text.delete("1.0", tk.END)
            self.info_text.insert(tk.END, f"Phương pháp: {self.METHODS[m]}\n")
            self.info_text.insert(tk.END, f"Ảnh: {w} x {h} px\n")
            self.info_text.insert(tk.END, f"G-Code: {num_lines} dòng\n\n")
            self.info_text.insert(tk.END, stat_text + "\n")
            self.info_text.insert(tk.END, "\n--- G-Code Preview ---\n")
            self.info_text.insert(tk.END, "\n".join(self.gcode.split("\n")[:12]))

        except Exception as e:
            self.status_label.config(text=f" {e}", foreground="#f38ba8")
            messagebox.showerror("Lỗi", str(e))

    # --- Save ---
    def _save(self):
        if not self.gcode:
            messagebox.showwarning("Cảnh báo", "Tạo G-Code trước!")
            return
        default = os.path.splitext(os.path.basename(self.image_path))[0] + ".gcode"
        path = filedialog.asksaveasfilename(
            title="Lưu G-Code", defaultextension=".gcode", initialfile=default,
            filetypes=[("G-Code", "*.gcode *.nc *.ngc"), ("Text", "*.txt"), ("Tất cả", "*.*")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.gcode)
            self.status_label.config(text=f"Đã lưu: {os.path.basename(path)}", foreground="#a6e3a1")
            messagebox.showinfo("Thành công", f"Đã lưu:\n{path}")


# ============================================================
# CLI
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
        print(f"Chữ: {config.text_content!r} | Font: {config.text_font} | "
              f"Cỡ: {config.text_height}mm")
        data, _, w, h, info = process_text(config)
        gcode, stats = generate_gcode_text(data, w, h, config)
        print(f"{info}")
        if output_path is None:
            output_path = "text.gcode"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(gcode)
        print(f"Đã lưu: {output_path} ({gcode.count(chr(10)) + 1} dòng)")
        print(f"Thời gian: ~{stats['est_time']:.1f} phút")
        return

    print(f"Ảnh: {image_path} | Phương pháp: {method} | "
          f"Cung G2/G3: {'có' if config.use_arcs else 'không'}")

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
        print(f"Phương pháp không hợp lệ: {method}")
        return

    print(f"{info}")
    if output_path is None:
        output_path = os.path.splitext(image_path)[0] + f"_{method}.gcode"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(gcode)
    num = gcode.count("\n") + 1
    print(f"Đã lưu: {output_path} ({num} dòng)")
    print(f"Thời gian: ~{stats['est_time']:.1f} phút")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        flags = {a for a in sys.argv[1:] if a.startswith("--")}
        method = args[1] if len(args) > 1 else 'line'
        out = args[2] if len(args) > 2 else None
        # Với TEXT thì tham số đầu là NỘI DUNG CHỮ, không phải đường dẫn ảnh
        run_cli(None if method == 'text' else args[0], method, out,
                no_arcs="--no-arcs" in flags,
                no_uniform="--no-uniform" in flags,
                contour_outline="--contour-outline" in flags,
                text=args[0] if method == 'text' else None)
    else:
        root = tk.Tk()
        app = ImageToGCodeApp(root)
        root.mainloop()
