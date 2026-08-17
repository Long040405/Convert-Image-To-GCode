# Camera Vision & Image to G-Code Pipeline

Hệ thống xử lý ảnh và chuyển đổi hình ảnh thành mã G-Code cho máy CNC / Máy vẽ Plotter / Hệ thống Linear System 3 trục (X, Y, Z), tích hợp chụp ảnh từ Camera công nghiệp (Basler GigE).

---

## Quy Trình Hoạt Động (Pipeline)

```mermaid
flowchart LR
    A[camera.py\nChụp ảnh Basler GigE\nSan phẳng sáng & Tách vật] --> B[convert_3d_to_2d.py\nTiền xử lý 3D -> 2D\n(Line Art / Cartoon / Cạnh)]
    B --> C[image_to_gcode.py\nChuyển ảnh -> G-Code\n(Khớp cung G2/G3, 7 Chế độ)]
    C --> D[gcode_viewer.py\nMô phỏng & Kiểm tra\nĐường chạy dao trước khi cắt]
```

---

## Cấu Trúc Thư Mục

```text
.
├── camera.py             # Điều khiển Camera Basler GigE, khử bóng, chuẩn nền & chụp ảnh
├── convert_3d_to_2d.py   # GUI/CLI chuyển đổi ảnh chụp thực tế thành nét 2D phẳng
├── image_to_gcode.py     # Bộ tạo G-Code chuyên sâu (hỗ trợ 7 phương pháp, khớp G2/G3)
├── gcode_viewer.py       # Bộ mô phỏng & trực quan hóa file G-Code
├── flatfield.png         # File ảnh hiệu chuẩn trường sáng mẫu (Flat-field)
├── captures/             # Thư mục chứa ảnh chụp đầu ra từ camera
├── requirements.txt      # Danh sách thư viện Python cần thiết
└── .gitignore            # Cấu hình bỏ qua file tạm, cache, ảnh chụp thử nghiệm
```

---

## Cài Đặt Môi Trường

### 1. Cài đặt Python Dependencies
Khuyến nghị sử dụng Python 3.9+ :

```bash
pip install -r requirements.txt
```

> **Lưu ý về Camera Basler (`pypylon`):**  
> Cần cài đặt thêm **Basler Pylon Camera Software Suite** nếu bạn kết nối trực tiếp với camera phần cứng Basler GigE.

---

## Hướng Dẫn Sử Dụng Từng Module

### 1. Chụp ảnh bằng Camera (`camera.py`)
Mở luồng camera trực tiếp, điều chỉnh thông số phơi sáng, khử bóng và chuẩn hóa nền:

```bash
python camera.py
```

* **Phím tắt trong cửa sổ camera:**
  * <kbd>Space</kbd> hoặc <kbd>S</kbd>: Chụp ảnh và tự động tách vật thể dán lên nền trắng.
  * <kbd>F</kbd>: Chuẩn hóa nền trắng (*Flat-field Calibration* — thực hiện khi khung hình chỉ có nền trắng trống).
  * <kbd>C</kbd>: Đổi chế độ giải mã màu Bayer.
  * <kbd>Esc</kbd> hoặc <kbd>Q</kbd>: Thoát chương trình.

---

### 2. Chuyển đổi Ảnh 3D sang 2D (`convert_3d_to_2d.py`)
Ảnh chụp ngoài đời có bóng đổ và chuyển sắc mượt khiến G-Code dễ bị nét vụn. Sử dụng công cụ này để đưa về ảnh phẳng:

* **Mở giao diện đồ họa (GUI):**
  ```bash
  python convert_3d_to_2d.py
  ```
* **Chạy dòng lệnh (CLI):**
  ```bash
  python convert_3d_to_2d.py input.jpg lineart
  python convert_3d_to_2d.py input.jpg all
  ```

* **6 Phương pháp hỗ trợ:**
  1. `Line Art`: Nét viền đen trên nền trắng (tối ưu cho nét vẽ đơn).
  2. `Cartoon`: Gom mảng màu phẳng + viền cạnh.
  3. `Threshold`: Nhị phân hóa thích ứng.
  4. `Posterize`: Rút gọn mức sáng, loại bỏ gradient.
  5. `Edge Drawing`: Lọc cạnh Canny làm sạch.
  6. `Stipple`: Mô phỏng tông đậm nhạt bằng mật độ điểm.

---

### 3. Xuất G-Code từ Ảnh (`image_to_gcode.py`)
Chuyển đổi ảnh 2D sang tập lệnh G-Code hoàn chỉnh cho máy 3 trục:

* **Mở giao diện cấu hình trực quan (GUI):**
  ```bash
  python image_to_gcode.py
  ```
* **Chạy dòng lệnh (CLI):**
  ```bash
  python image_to_gcode.py input.png -o output.gcode --method line
  ```

* **7 Phương pháp vẽ:**
  * `LINE`: Rút nét dày về đường tâm 1px (skeleton/centerline), độ dày nét vẽ đồng nhất.
  * `CONTOUR`: Đi theo đường viền đối tượng, tự động tối ưu hóa đường khép kín.
  * `COLOR`: Tách ranh giới giữa các mảng màu phẳng (dành cho logo, hoạt hình).
  * `PORTRAIT`: Xử lý nét chân dung bằng DoG chuẩn hóa (không bị loang mảng).
  * `RASTER`: Tô đặc vùng tối (Zigzag liên tục / Hatching chéo / Offset đồng mức).
  * `EDGE`: Phát hiện cạnh biên Canny nét mảnh.
  * `TEXT`: Vẽ chữ trực tiếp (hỗ trợ font tiếng Việt có dấu, không cần ảnh đầu vào).

---

### 4. Mô Phỏng G-Code (`gcode_viewer.py`)
Kiểm tra lại đường đi của đầu bút/dao trước khi nạp vào máy:

```bash
python gcode_viewer.py output.gcode
```

* **Thao tác chuột & phím tắt:**
  * **Chuột:** Lăn chuột để phóng to/thu nhỏ tại con trỏ · Kéo chuột để di chuyển (Pan) · Nháy đúp chuột để căn vừa khung hình.
  * <kbd>Space</kbd>: Phát / Dừng mô phỏng từng bước vẽ.
  * <kbd>R</kbd>: Chạy lại mô phỏng từ đầu.
  * <kbd>F</kbd>: Căn vừa khung nhìn.

---

## Tính Năng Nổi Bật

- **Khử bóng đổ thông minh (`illum_field`):** Phân tích màu trong không gian LAB để tách bóng đổ ra khỏi vật thể.
- **Tối ưu hóa G-Code:**
  - Tự động khớp các chuỗi điểm uốn cong thành lệnh cung tròn `G2`/`G3` (I/J) giúp giảm dung lượng file và chuyển động mượt mà.
  - Sắp xếp thứ tự nét vẽ theo khoảng cách gần nhất (TSP heuristic), giảm thiểu tối đa số lần nhấc trục Z và hành trình chạy không tải (G0).
- **Hỗ trợ Unicode & Tiếng Việt:** Đọc/ghi ảnh an toàn với đường dẫn tiếng Việt có dấu trên Windows.

---

## Bản Quyền & Giấy Phép
Dự án được phân phối phục vụ mục đích nghiên cứu, học tập và ứng dụng trong tự động hóa điều khiển máy vẽ/CNC.
