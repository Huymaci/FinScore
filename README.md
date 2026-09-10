# SmartFinance

Ứng dụng quản lý tài chính cá nhân (Smart Personal Finance Management System —
SPFM): ghi nhận giao dịch thu/chi trên nhiều tài khoản tiền, **nhập sao kê ngân
hàng** từ CSV/XLSX kèm phát hiện trùng, phân loại tự động theo rule, đặt ngân
sách và tính **Safe-to-Spend**, cảnh báo hành vi chi tiêu, thống kê xu hướng, và
một bảng điều khiển quản trị.

Backend là Flask + MySQL phục vụ JSON API; frontend là một bundle tĩnh không
framework do chính Flask phục vụ **cùng origin** (session cookie + CSRF).

Triển khai toàn bộ Use Case priority **Must** trong `SRS-SmartFinance-v2-slim.md`.
UC-10 (chia sẻ trạng thái) chưa triển khai vì priority là **Should**.

## Phạm vi theo Actor

- **Guest:** UC-01 đăng ký, privacy notice, đăng nhập và khóa 15 phút sau 5 lần sai.
- **User:** UC-02 hồ sơ/export/yêu cầu xóa; UC-03 tài khoản tiền; UC-04 giao dịch và custom category; UC-05 preview CSV/XLSX; UC-06 conflict/confirm/error report; UC-07 budget/Safe-to-Spend; UC-08 alert; UC-09 statistics.
- **Admin:** UC-11 quản trị user/import config/operations/audit với administrative blindness.

## Kiến trúc và bố cục mã

Backend chia 4 lớp; route **không** truy vấn DB trực tiếp, mọi quy tắc nghiệp vụ
nằm ở service.

| Thư mục | Vai trò |
|---|---|
| `app/routes/` | Blueprint HTTP: parse request, gọi service, trả JSON. Không chứa logic nghiệp vụ. |
| `app/services/` | Quy tắc nghiệp vụ (auth, imports, budgets, alerts, statistics, admin, metrics…). |
| `app/repositories/` | Truy vấn dữ liệu dùng lại được. |
| `app/models/` | SQLAlchemy model: `User`, `Ledger`, `Account`, `Category`, `Transaction`, `ImportTemplate`, `ImportBatch`, `ImportError`, `CategorizationRule`, `Budget`, `Alert`, `HabitChallenge`, `AuditLog`, `SupportReport`. |
| `app/errors.py` | Error handler chung — mọi lỗi trả JSON đúng một dạng. |
| `app/extensions.py` | `db`, `login_manager`, `limiter`, `csrf`, `talisman`. |
| `migrations/` | Alembic. Schema **chỉ** đổi qua migration, không dùng `db.create_all()`. |
| `frontend/` | Bundle tĩnh (xem mục Giao diện). |
| `scripts/` | `seed` (dữ liệu tham chiếu), `seed_mock`, `seed_users`, `nightly` (job cảnh báo). |

`app/__init__.py` là application factory: đăng ký blueprint, bật Talisman/CSP, và
gắn hai hook `before_request`/`after_request` để đo request cho console admin.

### Bề mặt API

Toàn bộ API trả JSON, dùng session cookie; mọi method ghi cần CSRF token.

| Prefix | Nội dung |
|---|---|
| `/auth` | Đăng ký, đăng nhập, đăng xuất, khóa tài khoản. |
| `/profile` | Hồ sơ, đổi mật khẩu, export dữ liệu, yêu cầu xóa. |
| `/accounts` · `/categories` · `/transactions` | Tài khoản tiền, danh mục (gồm custom), giao dịch. |
| `/imports` | Upload sao kê, preview, xử lý trùng, confirm, error report. |
| `/budgets` · `/alerts` · `/challenges` | Ngân sách + Safe-to-Spend, cảnh báo, thử thách hành vi. |
| `/statistics` | Thống kê danh mục và xu hướng. |
| `/support-reports` | Người dùng gửi báo lỗi. |
| `/admin` | UC-11: user, import config, operations, audit log, support report, system status/logs, error monitor, import batch. |
| `/` (catch-all) | `app/routes/ui.py` phục vụ `frontend/`, chỉ cho phép các đuôi file tĩnh. |

## Chạy ứng dụng

Yêu cầu Python 3.11 và MySQL 8.0.16+ (khuyến nghị Docker).

1. Sao chép `.env.example` thành `.env`, thay toàn bộ giá trị mẫu và đặt thêm `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` trong shell nếu dùng Compose.
2. Cài dependency: `python -m pip install -r requirements.txt`.
3. Khởi động MySQL: `docker compose up -d mysql`.
4. Chạy migration: `python -m alembic upgrade head`.
5. Seed category, 4 bank template, 12 rule phân loại và Admin: `python -m scripts.seed`.
6. Chạy ứng dụng: `python run.py`.
7. Mở `http://127.0.0.1:5000` — Flask phục vụ cả giao diện và API cùng origin.

Đăng nhập Admin bằng đúng `ADMIN_EMAIL` / `ADMIN_PASSWORD` đã đặt ở bước 1.

### Biến môi trường

| Biến | Ý nghĩa |
|---|---|
| `SECRET_KEY` | Bắt buộc. Sinh bằng `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `DATABASE_URL` | Bắt buộc. Ký tự đặc biệt trong mật khẩu phải percent-encode (`#`→`%23`, `@`→`%40`). |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Tài khoản Admin do `scripts.seed` tạo. |
| `HTTPS_ENABLED` | `false` cho localhost HTTP; `true` sau reverse proxy HTTPS. Cờ này điều khiển **cả** redirect HTTPS lẫn thuộc tính `Secure` của cookie. |
| `RATELIMIT_STORAGE_URI` | Nơi Flask-Limiter đếm. Mặc định `memory://` chỉ đúng khi chạy 1 process. |
| `UPLOAD_FOLDER` | Mặc định `instance/uploads`. |

Thiếu `SECRET_KEY` hoặc `DATABASE_URL`, factory sẽ raise ngay lúc khởi động thay
vì chạy với cấu hình nửa vời.

Giao diện tự lấy CSRF token và gửi kèm mọi POST/PUT/PATCH/DELETE. Session cookie dùng `HttpOnly`, `SameSite=Lax` và timeout nhàn rỗi 30 phút. Ở production, đặt `HTTPS_ENABLED=true` sau reverse proxy HTTPS để bật chuyển hướng HTTPS và cờ cookie `Secure`; local mặc định dùng HTTP để có thể đăng nhập mà không cần chứng chỉ tự ký.

## Giao diện

Frontend tại `frontend/` kết nối đầy đủ API cho đăng ký/đăng nhập, tài khoản tiền,
giao dịch, import sao kê và xử lý trùng, ngân sách, Safe-to-Spend, cảnh báo,
thử thách hành vi, dashboard, thống kê và **màn hình Admin (UC-11)**. Mục
"Quản trị" trên sidebar chỉ hiện khi tài khoản đăng nhập có `role = ADMIN`;
đăng nhập bằng Admin sẽ vào thẳng màn hình này. UC-10 (chia sẻ trạng thái) chưa
triển khai vì priority là **Should**.

Không có bước build và không có framework — mỗi file là một script thuần:

| File | Vai trò |
|---|---|
| `index.html` · `styles.css` | Khung ứng dụng thành viên. |
| `app.js` | Điều phối màn hình thành viên, gọi API, bật/tắt console admin. |
| `admin.js` · `admin.css` | Console quản trị — shell riêng dưới `#admin-console`, không phải một trang trong app thành viên. |
| `i18n.js` | Từ điển VI/EN. Lựa chọn lưu ở `localStorage` key `smartfinance-language`, mặc định `vi`. Nội dung do người dùng/backend sinh ra (tên, email, mô tả giao dịch, nội dung cảnh báo) **không** bị dịch. |
| `theme.js` | Chủ đề sáng/tối. |
| `tour.js` | Hướng dẫn lần đầu, mỗi bước spotlight một control. |
| `bank-picker.js` | Danh mục ngân hàng dùng chung cho form tài khoản và logo. |

Frontend là bundle không băm tên file, nên `ui.py` gắn `Cache-Control: no-cache`
để trình duyệt không giữ bản cũ sau khi deploy.

### Ràng buộc CSP

NFR-17 cấm `unsafe-inline`. CSP `style-src` chặn cả thuộc tính HTML `style=""`,
nên frontend **không được** sinh inline style — mọi độ rộng thanh tiến độ phải
phát ra `data-fill="NN"` rồi để `applyFills()` gán qua CSSOM. Test
`ContentSecurityPolicyTest` sẽ fail nếu có inline style lọt vào `index.html`
hoặc `app.js`. Console admin theo cùng quy tắc: kích thước cột/thanh do
`applySizes()` gán qua CSSOM.

## Bảng điều khiển Admin

Ngoài quản lý user/import config/audit, console báo cáo sức khỏe vận hành
(FR-50): lưu lượng request, phân vị độ trễ và các lỗi API gần đây.

Số liệu này nằm **trong bộ nhớ tiến trình** (`app/services/metrics.py`), không
ghi DB — thêm một dòng ghi vào mỗi request sẽ đặt chi phí ghi lên đường đi nóng
của từng lần tải trang. Hệ quả cần biết:

- Bộ đếm **reset khi tiến trình khởi động lại**.
- Chạy nhiều worker thì **mỗi worker chỉ thấy phần của mình**; `snapshot()` trả
  kèm `partial=True` để giao diện nói rõ điều đó thay vì ngụ ý đây là con số
  toàn cụm.

Theo NFR-10, metrics không giữ mật khẩu, token, số tiền, mô tả hay email đầy đủ;
endpoint được ghi theo `url_rule` đã khớp (`/admin/users/<int>`), không phải path
thật, nên không có id nào lọt vào khóa bucket. Riêng số lần đăng nhập sai được
ghi vào `audit_logs` (chỉ user id) vì `users.failed_logins` là bộ đếm chuỗi liên
tiếp, bị reset về 0 ngay lần đăng nhập đúng kế tiếp nên không trả lời được câu
hỏi "bao nhiêu lần sai trong một khoảng thời gian".

Console cũng tuân thủ **administrative blindness** (FR-51/NFR-09): mọi thứ hiển
thị là đếm, tỷ lệ hoặc trạng thái vận hành — không có tên file sao kê, tên tài
khoản, số tiền hay nội dung cảnh báo.

## Test

```bash
# Linux / macOS
python -m pytest --cov=app --cov-report=term-missing -q
```

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing -q
```

Unit/component suite dùng SQLite in-memory để chạy độc lập. Ngưỡng coverage tối
thiểu là 60% (`pyproject.toml`). Lint: `ruff check .`.

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
2026-08-19 và đạt đúng 20.000 dòng theo NFR-08.

Có thể điều chỉnh quy mô:

```powershell
python -m scripts.seed_mock --synthetic-count 50000 --random-seed 42 `
  --start-date 2022-01-01 --end-date 2026-08-19
```

Cùng bộ tham số có thể chạy lại mà không nhân đôi. Đổi `--random-seed` sẽ tạo
một tập giao dịch khác. Ba CSV gốc chỉ được dùng làm mẫu ngôn ngữ; nếu cần nhập
nguyên văn để kiểm thử parser, truyền thêm `--include-source`.

Sau khi lệnh seed hoàn tất, đăng nhập bằng:

```text
Email: demo@smartexpense.local
Mật khẩu: SmartExpenseMock1!
```

Tài khoản demo không được tạo bởi `scripts.seed`; cần chạy `scripts.seed_mock`
ít nhất một lần trên đúng `DATABASE_URL` mà ứng dụng đang sử dụng.

## Seed 50 tài khoản người dùng

Để tạo 50 tài khoản mẫu có thu nhập và cơ cấu chi tiêu khác nhau trong 6 tháng gần nhất:

```powershell
$env:SEED_USERS_PASSWORD='SmartExpenseUser1!'
python -m scripts.seed_users --count 50 --months 6
```

Email được tạo từ `user001@smartexpense.local` đến `user050@smartexpense.local`.
Lệnh có thể chạy lại mà không nhân đôi giao dịch; dùng thêm `--replace` để tạo lại
riêng các giao dịch do seed này quản lý.

## Tài liệu

| File | Nội dung |
|---|---|
| `SRS-SmartFinance-v2-slim.md` | Đặc tả yêu cầu đang có hiệu lực — nguồn của mọi mã UC/FR/NFR nhắc trong repo. |
| `TRACEABILITY-v2slim.md` · `docs/TRACEABILITY-v2slim.md` | Truy vết yêu cầu ↔ hiện thực. |
| `REVIEW-SmartFinance.md` | Bản rà soát code đối chiếu SRS v2-slim. |
| `HANDOVER.md` · `APPLYING.md` | Ghi chú bàn giao và cách áp bản đã sửa vào repo có sẵn — đọc `APPLYING.md` trước khi chép đè, có bước ngoài file ảnh hưởng database. |
| `docs/DESIGN-statement-extraction.md` | Thiết kế trích xuất sao kê không phụ thuộc template từng ngân hàng. |
| `docs/archive/` | Các bản SRS cũ, chỉ để tham chiếu. |
| `frontend/README.md` | Ghi chú riêng của frontend. |
