# SmartFinance

Flask API triển khai toàn bộ Use Case priority **Must** trong SRS SmartFinance v2. UC-10 (chia sẻ trạng thái) chưa triển khai vì priority là **Should**.

## Phạm vi theo Actor

- **Guest:** UC-01 đăng ký, privacy notice, đăng nhập và khóa 15 phút sau 5 lần sai.
- **User:** UC-02 hồ sơ/export/yêu cầu xóa; UC-03 tài khoản tiền; UC-04 giao dịch và custom category; UC-05 preview CSV/XLSX; UC-06 conflict/confirm/error report; UC-07 budget/Safe-to-Spend; UC-08 alert; UC-09 statistics.
- **Admin:** UC-11 quản trị user/import config/operations/audit với administrative blindness.

## Chạy ứng dụng

Yêu cầu Python 3.11 và MySQL 8.0.16+ (khuyến nghị Docker).

1. Sao chép `.env.example` thành `.env`, thay toàn bộ giá trị mẫu và đặt thêm `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` trong shell nếu dùng Compose.
2. Cài dependency: `python -m pip install -r requirements.txt`.
3. Khởi động MySQL: `docker compose up -d mysql`.
4. Chạy migration: `python -m alembic upgrade head`.
5. Seed category, 4 bank template, 12 rule phân loại và Admin: `python -m scripts.seed`.
6. Chạy ứng dụng: `python run.py`.
7. Mở `http://127.0.0.1:5000` — Flask phục vụ cả giao diện và API cùng origin.

Giao diện tự lấy CSRF token và gửi kèm mọi POST/PUT/PATCH/DELETE. Session cookie dùng `HttpOnly`, `SameSite=Lax` và timeout nhàn rỗi 30 phút. Ở production, đặt `HTTPS_ENABLED=true` sau reverse proxy HTTPS để bật chuyển hướng HTTPS và cờ cookie `Secure`; local mặc định dùng HTTP để có thể đăng nhập mà không cần chứng chỉ tự ký.

## Giao diện

Frontend tại `frontend/` kết nối đầy đủ API cho đăng ký/đăng nhập, tài khoản tiền,
giao dịch, import sao kê và xử lý trùng, ngân sách, Safe-to-Spend, cảnh báo,
thử thách hành vi, dashboard, thống kê và **màn hình Admin (UC-11)**. Mục
"Quản trị" trên sidebar chỉ hiện khi tài khoản đăng nhập có `role = ADMIN`;
đăng nhập bằng Admin sẽ vào thẳng màn hình này. UC-10 (chia sẻ trạng thái) chưa
triển khai vì priority là **Should**.

### Ràng buộc CSP

NFR-17 cấm `unsafe-inline`. CSP `style-src` chặn cả thuộc tính HTML `style=""`,
nên frontend **không được** sinh inline style — mọi độ rộng thanh tiến độ phải
phát ra `data-fill="NN"` rồi để `applyFills()` gán qua CSSOM. Test
`ContentSecurityPolicyTest` sẽ fail nếu có inline style lọt vào `index.html`
hoặc `app.js`.

## Test

```bash
# Linux / macOS
python -m pytest --cov=app --cov-report=term-missing -q
```

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing -q
```

Unit/component suite dùng SQLite in-memory để chạy độc lập.

**Cảnh báo về giới hạn của SQLite.** Một số lỗi chỉ xuất hiện trên MySQL và
SQLite không thể tái hiện — rõ nhất là `SUM()` trên cột `BIGINT`: MySQL trả
`decimal.Decimal`, SQLite trả `int`. Đã từng có lỗi `TypeError: Decimal / float`
làm sập detector FR-19 và mọi lần confirm import trên MySQL trong khi toàn bộ
test SQLite vẫn xanh. Vì vậy **luôn chạy `alembic upgrade head` + smoke test
trên MySQL thật trước khi nộp**, đừng tin mỗi test suite.

`tests/test_migrations.py` chạy `alembic upgrade head` từ DB rỗng trên một file
SQLite tạm mỗi lần test, nên chuỗi migration luôn được replay (không còn phụ
thuộc `db.create_all()`). Đặt `TEST_DATABASE_URL` trỏ tới MySQL để thêm bước
`alembic check` bắt drift giữa model và migration:

```powershell
$env:TEST_DATABASE_URL='mysql+pymysql://user:pass@host/db?charset=utf8mb4'
.\.venv\Scripts\python.exe -m pytest -q tests/test_migrations.py
```

`.github/workflows/ci.yml` chạy `ruff` + `pytest` trên mỗi push/PR, cộng một job
`alembic upgrade head` + `alembic check` + seed trên MySQL 8 thật — đây là chốt
chặn cho ba lớp lỗi chỉ hiện trên MySQL (cookie `Secure`, `Decimal`, `VARCHAR`).

Các bằng chứng đặc thù MySQL (collation, FK/check constraint, `DATETIME(6)`,
`BINARY(32)`) vẫn nên kiểm chứng thủ công thêm trên MySQL trước khi nộp.

Nightly alert job: `python -m scripts.nightly`.

## Đo hiệu năng (NFR-08)

`python run.py` chạy dev server của Flask — **không dùng để đo hiệu năng**. Số
liệu NFR-08 phải đo trên WSGI server thật:

```bash
gunicorn -w 4 -k gthread --threads 4 -b 127.0.0.1:5000 "run:app"
```

Khi chạy nhiều worker như trên, đặt `RATELIMIT_STORAGE_URI` trỏ tới store dùng
chung (vd `redis://127.0.0.1:6379/0`). Mặc định `memory://` đếm riêng từng
worker, nên giới hạn đăng nhập/đăng ký sẽ nhân lên theo số worker và reset mỗi
lần reload.

Cần 20.000 giao dịch trong DB trước khi đo (xem mục "Dữ liệu mock từ sao kê").
Ngưỡng: p95 dưới 800 ms trên các trang đọc với 10 người dùng đồng thời.

## Dữ liệu mock từ sao kê

Sau khi chạy migration, có thể tạo user demo và 20.000 giao dịch mang cấu trúc
mô tả của ba mẫu sao kê. Dòng tiền được mô phỏng theo tháng: MB nhận lương
25–30 triệu, chuyển tiền sang BIDV để chi tiêu (gồm đúng 3 triệu tiền nhà) và
chuyển phần muốn giữ sang VPBank (tài khoản thanh toán, không phải tiết kiệm).
Lần đầu chuyển từ bộ mock cũ sang mô hình này, dùng chế độ thay thế có giới hạn:

```powershell
$env:MOCK_USER_PASSWORD='SmartExpenseMock1!'
python -m scripts.seed_mock --replace-demo-data
```

Email mặc định là `demo@smartexpense.local`. Chế độ thay thế chỉ xóa dữ liệu tài
chính thuộc user này, giữ nguyên user khác và dữ liệu cấu hình dùng chung. Chạy
lại cùng tham số không nhân đôi. Dữ liệu mặc định trải từ 2024-01-01 đến
2026-08-19 và đạt đúng 20.000 dòng theo NFR-08. Có thể điều chỉnh quy mô:

Sau khi lệnh seed hoàn tất, đăng nhập bằng:

```text
Email: demo@smartexpense.local
Mật khẩu: SmartExpenseMock1!
```

Tài khoản demo không được tạo bởi `scripts.seed`; cần chạy `scripts.seed_mock`
ít nhất một lần trên đúng `DATABASE_URL` mà ứng dụng đang sử dụng.

```powershell
python -m scripts.seed_mock --synthetic-count 50000 --random-seed 42 `
  --start-date 2022-01-01 --end-date 2026-08-19
```

Cùng bộ tham số có thể chạy lại mà không nhân đôi. Đổi `--random-seed` sẽ tạo
một tập giao dịch khác. Ba CSV gốc chỉ được dùng làm mẫu ngôn ngữ; nếu cần nhập
nguyên văn để kiểm thử parser, truyền thêm `--include-source`.
## Seed 50 tài khoản người dùng

Để tạo 50 tài khoản mẫu có thu nhập và cơ cấu chi tiêu khác nhau trong 6 tháng gần nhất:

```powershell
$env:SEED_USERS_PASSWORD='SmartExpenseUser1!'
python -m scripts.seed_users --count 50 --months 6
```

Email được tạo từ `user001@smartexpense.local` đến `user050@smartexpense.local`.
Lệnh có thể chạy lại mà không nhân đôi giao dịch; dùng thêm `--replace` để tạo lại
riêng các giao dịch do seed này quản lý.
