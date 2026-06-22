# Logina Backend API Engine

Nội dung mã nguồn Backend cho nền tảng EdTech **Logina** — Công cụ chuyển đổi giáo trình sang các nhiệm vụ học tập nhập vai bằng AI (**Curriculum-to-Quest Engine**). 

Hệ thống được thiết kế dạng monorepo hỗ trợ giao thức bảo mật JWT, xác thực quyền (RBAC - Giáo viên & Học sinh), quản lý cơ sở dữ liệu quan hệ (PostgreSQL - Neon.tech), tài liệu phi cấu trúc (MongoDB Atlas), lưu trạng thái làm bài tạm thời (Render Redis Cache), và bộ máy phân tích hành vi học tập thời gian thực tích hợp mô hình ngôn ngữ lớn **Gemini 1.5 Flash**.

---

## 1. Hướng Dẫn Cài Đặt & Khởi Chạy (Local)

### Yêu cầu hệ thống
* Python 3.10 trở lên
* Conda / virtualenv

### Bước 1: Thiết lập môi trường ảo
```bash
# Tạo môi trường ảo
python3 -m venv venv

# Kích hoạt môi trường ảo
source venv/bin/activate
```

### Bước 2: Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### Bước 3: Cấu hình biến môi trường (`.env`)
Tạo một file `.env` ở thư mục gốc của dự án (`logina-backend/.env`) có nội dung sau:

```env
# --- PostgreSQL (Neon.tech / Local) ---
# Dùng "postgresql+asyncpg://" cho SQLAlchemy Async kết nối
DATABASE_URL=postgresql+asyncpg://[user]:[password]@[neon-host]/[database-name]?sslmode=require

# --- MongoDB (MongoDB Atlas / Local) ---
MONGO_URI=mongodb+srv://[username]:[password]@[cluster-host]/[database-name]?retryWrites=true&w=majority
MONGO_DB=logina_mongo

# --- Redis (Render.com / Local) ---
# Điền chuỗi kết nối Render cung cấp (thường bắt đầu bằng rediss://)
REDIS_URL=rediss://red-xxxxxxxxxx:password@singapore-redis.render.com:6379

# --- AI / LLM Keys ---
GEMINI_API_KEY=your_gemini_api_key_here

# --- Authentication ---
JWT_SECRET=super_secret_logina_key_change_me_in_production
JWT_EXPIRATION_TIME=3600s
```

### Bước 4: Khởi tạo cấu trúc bảng dữ liệu (Seed Data)
Chạy script Python để tự động tạo cấu trúc bảng PostgreSQL (Neon) và cấu hình Index MongoDB Atlas:
```bash
python scripts/init_db.py --all
```
*(Nếu muốn xóa sạch toàn bộ dữ liệu trên cả 2 database để làm lại từ đầu, hãy chạy: `python scripts/init_db.py --clean`)*

### Bước 5: Khởi chạy API Engine
Từ thư mục gốc `logina-backend/`, chạy lệnh sau để uvicorn nạp đúng biến môi trường:
```bash
PYTHONPATH=src uvicorn app.main:app --reload
```
Truy cập tài liệu API tự động (Swagger UI) tại: `http://localhost:8000/docs`

---

## 2. Tài Liệu Hệ Thống API (API Documentation)

Mọi API chính thức của hệ thống được bắt đầu bằng tiền tố `/api/v1`.

### 2.1. Authentication (`/api/v1/auth`)

* **`POST /api/v1/auth/login`**
  * **Mô tả**: Đăng nhập bằng tài khoản. Trả về Token và cấu hình HTTP-Only Cookie.
  * **Content-Type**: `application/x-www-form-urlencoded`
  * **Payload**: `{ "username": "email@example.com", "password": "password" }`
  * **Response**: `{ "access_token": "JWT_TOKEN", "token_type": "bearer", "role": "TEACHER" }`
  
* **`POST /api/v1/auth/logout`**
  * **Mô tả**: Đăng xuất, xóa HTTP-Only cookie của phiên làm việc.
  
* **`GET /api/v1/auth/me`**
  * **Mô tả**: Lấy thông tin profile người dùng đang đăng nhập thông qua Bearer Token.
  * **Response**: `{ "id": 1, "email": "...", "full_name": "...", "role": "TEACHER", "is_active": true }`

---

### 2.2. Quests Module (`/api/v1/quests`)
*API yêu cầu quyền hạn `TEACHER`.*

* **`POST /api/v1/quests/generate-draft`**
  * **Mô tả**: Trích xuất tài liệu (PDF và/hoặc text giáo trình) $\rightarrow$ gọi AI Pipeline 3 bước thiết lập Quest 10 Nodes $\rightarrow$ Lưu nháp tạm thời vào Redis.
  * **Content-Type**: `multipart/form-data`
  * **Payload**: Gửi kèm file đính kèm `files` (PDF) và/hoặc chuỗi text `curriculum_text`.
  * **Response**: Trả về cấu trúc Quest JSON nháp hoàn chỉnh.

* **`GET /api/v1/quests/draft`**
  * **Mô tả**: Lấy Quest nháp hiện tại của giáo viên đang lưu trữ trên Redis.

* **`PATCH /api/v1/quests/draft/node/{node_id}`**
  * **Mô tả**: Sửa đổi và sinh lại duy nhất một câu hỏi (Node) được chỉ định dựa trên feedback, tự động cập nhật các rules kiểm chứng chéo liên quan và ghi đè lại vào Redis.
  * **Payload**: `{ "feedback": "Nội dung phản hồi chỉnh sửa" }`
  * **Response**: Trả về cấu trúc Quest JSON nháp đã được cập nhật.

* **`POST /api/v1/quests/publish`**
  * **Mô tả**: Đọc Quest nháp cuối cùng từ Redis lưu chính thức vào MongoDB Atlas (`quests` collection) và xóa cache nháp trên Redis.
  * **Response**: `{ "status": "success", "quest_id": "MONGO_OBJECT_ID" }`

---

### 2.3. Classes Module (`/api/v1/classes`)

* **`GET /api/v1/classes/`**
  * **Mô tả**: Lấy danh sách các lớp học của Giáo viên phụ trách hoặc các lớp học sinh tham gia.
  
* **`POST /api/v1/classes/`** *(Yêu cầu role `TEACHER`)*
  * **Mô tả**: Tạo một lớp học mới.
  * **Payload**: `{ "name": "Tên lớp", "description": "Mô tả" }`
  
* **`POST /api/v1/classes/{class_id}/assign-quest`** *(Yêu cầu role `TEACHER`)*
  * **Mô tả**: Giao bài tập Quest (bằng ID của Quest trên MongoDB) cho toàn bộ lớp học (Khởi tạo `QuestRun`).
  * **Payload**: `{ "quest_id": "MONGO_OBJECT_ID" }`

* **`GET /api/v1/classes/{class_id}/students`** *(Yêu cầu role `TEACHER`)*
  * **Mô tả**: Xem danh sách học sinh thuộc lớp học chỉ định.

---

### 2.4. Quest Runtime (`/api/v1/runtime`)

* **`GET /api/v1/runtime/quest/{run_id}`** *(Yêu cầu đăng nhập)*
  * **Mô tả**: Bắt đầu làm bài. Lấy cấu trúc Quest từ MongoDB (ẩn trường `rules` để tránh hack đáp án) và khởi tạo trạng thái `game_state` trong Redis.

* **`POST /api/v1/runtime/quest/{run_id}/submit-action`** *(Yêu cầu đăng nhập)*
  * **Mô tả**: Học sinh gửi cặp lựa chọn [Quyết định, Bằng chứng]. Hệ thống chạy đối chiếu logic bằng bộ Validator, cập nhật trạng thái làm bài tạm thời trong Redis, ghi nhật ký EventLog bất đồng bộ vào MongoDB, và trả về cảnh báo (Flags) ngay lập tức.
  * **Payload**: `{ "node_id": "node_1", "decision_id": "dec_A", "selected_evidence_ids": ["ev_1", "ev_2"] }`

---

### 2.5. Reports & Analytics (`/api/v1/reports`)

* **`POST /api/v1/reports/quest/{run_id}/submit-quest`** *(Yêu cầu đăng nhập)*
  * **Mô tả**: Nộp bài làm chính thức. Lấy game state từ Redis, kích hoạt **Rubric Engine** tính điểm 4 trục năng lực (Knowledge, Evidence, Decision, Consistency), lưu báo cáo điểm vào Postgres, và xóa dữ liệu cache trên Redis.

* **`GET /api/v1/reports/student/{run_id}`** *(Yêu cầu đăng nhập)*
  * **Mô tả**: Học sinh xem chi tiết bảng điểm 4 trục của mình.

* **`GET /api/v1/reports/teacher/class/{class_id}`** *(Yêu cầu role `TEACHER`)*
  * **Mô tả**: Màn hình phân tích của Giáo viên. Tổng hợp điểm trung bình của cả lớp từ Postgres, đồng thời gom EventLogs lỗi tư duy của học sinh trên MongoDB gửi qua **Gemini** để phân tích và tự động xuất ra các **Teacher Action Cards** (Gợi ý hành động sư phạm).