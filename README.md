# EZVIZ LAN Camera Viewer

Web app xem camera EZVIZ trong mạng LAN thông qua giao thức RTSP.

## Tính năng

- 🎥 Xem trực tiếp camera EZVIZ qua RTSP trên trình duyệt web
- 📱 Giao diện responsive, hoạt động trên PC và điện thoại
- 🔄 Hỗ trợ xem nhiều camera cùng lúc
- ⚡ Chuyển đổi RTSP → HLS để phát trên trình duyệt
- 🌐 Chạy trên mạng LAN, không cần internet
- 🖥️ Hỗ trợ xem toàn màn hình

## Yêu cầu

- Python 3.9+
- FFmpeg (để chuyển đổi RTSP stream)
- Camera EZVIZ có hỗ trợ RTSP (hầu hết các dòng đều hỗ trợ)

## Cài đặt

### Cách 1: Chạy trực tiếp

```bash
# Cài FFmpeg (Ubuntu/Debian)
sudo apt install ffmpeg

# Cài dependencies Python
pip install .

# Chạy app
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Cách 2: Docker (khuyên dùng)

```bash
docker-compose up -d
```

## Sử dụng

1. Mở trình duyệt tại: `http://<IP_máy_chạy_app>:8000`
2. Thêm camera bằng cách điền thông tin:
   - **Tên camera**: Đặt tên dễ nhớ
   - **IP**: Địa chỉ IP của camera trong mạng LAN
   - **Port**: Mặc định 554
   - **Username**: Mặc định `admin`
   - **Password**: Mật khẩu xác minh RTSP của camera
   - **Kênh**: Mặc định 1
   - **Loại stream**: Main (HD) hoặc Sub (SD - nhẹ hơn)
3. Nhấn "Xem" để bắt đầu xem camera

## Cấu hình RTSP trên camera EZVIZ

### Bật RTSP trên camera EZVIZ:

1. Mở app EZVIZ trên điện thoại
2. Vào cài đặt camera → Nâng cao → RTSP
3. Bật dịch vụ RTSP
4. Đặt mật khẩu xác minh (verification code)

### Định dạng URL RTSP của EZVIZ:

```
rtsp://admin:<password>@<ip>:554/h264/ch1/1/av_stream   (Main stream - HD)
rtsp://admin:<password>@<ip>:554/h264/ch1/2/av_stream   (Sub stream - SD)
```

## Cấu trúc dự án

```
ezviz-lan-viewer/
├── app.py              # Backend FastAPI
├── templates/
│   └── index.html      # HTML template
├── static/
│   ├── style.css       # CSS styles
│   └── app.js          # Frontend JavaScript
├── streams/            # HLS stream output (auto-generated)
├── cameras.json        # Camera configuration (auto-generated)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Lưu ý

- Camera và máy chạy app phải cùng mạng LAN
- Nếu dùng Docker, sử dụng `network_mode: host` để truy cập mạng LAN
- Sub stream (SD) nhẹ hơn, phù hợp khi xem nhiều camera cùng lúc
- Đảm bảo camera đã bật dịch vụ RTSP

## Khắc phục sự cố

| Vấn đề | Giải pháp |
|--------|-----------|
| Không kết nối được | Kiểm tra IP, port, username/password |
| Video giật | Chuyển sang Sub stream (SD) |
| FFmpeg not found | Cài đặt FFmpeg: `sudo apt install ffmpeg` |
| Timeout | Kiểm tra camera đã bật RTSP chưa |
