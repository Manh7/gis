# gis
🟦 1. CÁCH RESTORE TỪ FILE .backup / .tar
✔ Bước 1: Tạo database mới (hoặc chọn database trống)

Trong pgAdmin → Databases → chuột phải → Create → Database…

✔ Bước 2: Chuột phải vào database mới → Restore…
✔ Bước 3: Chọn file backup

Format = Custom hoặc Tar

Filename = chọn file bạn export

✔ Bước 4: Nhấn Restore

→ pgAdmin sẽ import đầy đủ schema + data + constraints.

## chạy load data từ aqi
venv\Scripts\activate
python -m backend.etl
python -m backend.worker

## chạy server
uvicorn backend.app:app --reload --port 8000

## chạy giao diện
cd frontend
python -m http.server 5500
