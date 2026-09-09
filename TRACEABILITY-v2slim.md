# Ma trận truy vết SRS v2-slim — trạng thái đã kiểm chứng

**Ngày kiểm:** 25/08/2026 · **Môi trường:** MySQL 8.0.46 · Python 3.12 · gunicorn 4 worker × 4 thread
**Người kiểm:** MSc. Huỳnh Vinh Nam · ICTLab / USTH

## Quy ước mức độ bằng chứng

Đây là phần quan trọng nhất của tài liệu. Bài học lớn nhất từ đợt review vừa rồi là **"đã cài đặt" không đồng nghĩa "đã chạy"** — FR-19 từng được ghi nhận là hoàn thành trong khi nó crash 500 trên MySQL. Vì vậy mỗi dòng dưới đây ghi rõ bằng chứng thuộc loại nào:

| Ký hiệu | Nghĩa |
|---|---|
| **CHẠY** | Đã thực thi thật và quan sát kết quả (HTTP, SQL, đo đạc) |
| **ĐỌC** | Đã đọc mã nguồn xác nhận, chưa chạy kịch bản riêng |
| **THIẾU** | Chưa cài đặt |
| **CHƯA KIỂM** | Có mã nguồn nhưng chưa xác minh — **không được ghi là đạt** |

---

## 1. Use Case

| UC | Nội dung | Ưu tiên | Trạng thái | Bằng chứng |
|---|---|---|---|---|
| UC-01 | Đăng ký, đăng nhập, khóa sau 5 lần sai | Must | Đạt | **CHẠY** — E2E: đăng ký/đăng nhập, chặn <18 tuổi, chặn mật khẩu yếu |
| UC-02 | Hồ sơ, export, yêu cầu xóa | Must | Đạt | **CHẠY** — export trả ZIP hợp lệ; xóa xác minh zero rows |
| UC-03 | Quản lý tài khoản tiền | Must | Đạt | **CHẠY** — tạo CASH/BANK, chặn số tài khoản đầy đủ |
| UC-04 | Ghi giao dịch thủ công | Must | Đạt | **CHẠY** — thu/chi, chặn số tiền ≤ 0 |
| UC-05 | Import sao kê CSV/XLSX | Must | Đạt | **CHẠY** — preview đếm đúng new=4/error=1 |
| UC-06 | Xử lý trùng và lỗi import | Must | Đạt | **CHẠY** — confirm 4 dòng, tải được error report |
| UC-07 | Ngân sách tháng + Safe-to-Spend | Must | Đạt | **CHẠY** — CRUD, copy tháng trước, STS tính đúng |
| UC-08 | Cảnh báo chi tiêu | Must | Đạt | **CHẠY** — nightly sinh alert, có explanation + action |
| UC-09 | Thống kê | Must | Đạt | **CHẠY** — dashboard/breakdown/trend khớp số liệu tay |
| UC-10 | Chia sẻ trạng thái ngân sách | **Should** | **THIẾU** | Có chủ đích — priority Should |
| UC-11 | Quản trị | Must | Đạt | **CHẠY** — API + UI, kiểm tra administrative blindness |

**10/10 Must đạt. UC-10 là Should, bỏ có chủ đích và đã ghi trong README.**

---

## 2. Functional Requirements (FR-01 → FR-30)

Toàn bộ 30 FR đã được phủ bởi 67 assertion E2E qua HTTP thật trên MySQL. Các FR đáng chú ý:

| FR | Nội dung | Trạng thái | Ghi chú |
|---|---|---|---|
| FR-06 | Chỉ lưu 4 số cuối | **CHẠY** | Gửi số tài khoản đầy đủ → 400 |
| FR-12 | Preview phân loại new/duplicate/error | **CHẠY** | Đếm chính xác, error CSV tải được |
| FR-15 | Luật phân loại theo thứ tự ưu tiên | **CHẠY** | HIGHLANDS→Ăn uống, SHOPEE→Mua sắm, GRAB→Di chuyển, LUONG→Thu nhập |
| FR-19 | Burn-rate detector | **CHẠY** | *Từng crash 500 trên MySQL* — đã sửa, nay sinh alert thật |
| FR-20 | Alert có explanation + suggested action + cooldown 72h | **CHẠY** | Chạy nightly 2 lần → không nhân đôi |
| FR-27→30 | Quản trị | **CHẠY** | Có cả UI (bổ sung trong đợt này) |

---

## 3. Non-Functional Requirements

| NFR | Nội dung | Trạng thái | Bằng chứng |
|---|---|---|---|
| NFR-01 | `pbkdf2:sha256` ≥ 600.000 vòng | Đạt | **CHẠY** — `pbkdf2:sha256:600000$...` trong DB |
| NFR-02 | Cookie `HttpOnly`/`Secure`/`SameSite=Lax`, timeout 30' | Đạt | **CHẠY** — *đây là bug P0 đã sửa*; nay `Secure` bám đúng `HTTPS_ENABLED` |
| NFR-03 | Không nối chuỗi SQL | Đạt | **CHẠY** — grep `text(f"` → 0 kết quả |
| NFR-04 | CSRF mọi endpoint non-GET | Đạt | **CHẠY** — POST không token → 400 JSON |
| NFR-05 | Phân quyền cấp đối tượng | Đạt | **CHẠY** — user khác truy cập → 404 JSON |
| NFR-06 | An toàn upload | **Một phần** | **CHẠY** magic-byte ZIP, whitelist, 5 MB, `secure_filename`. **File không ghi xuống đĩa** (chỉ đọc vào RAM) nên "xóa trong 24h" không áp dụng — nhưng `UPLOAD_FOLDER` vẫn được tạo và bỏ không |
| NFR-07 | Coverage ≥ 60% | Đạt | **CHẠY** — **90%** tổng thể |
| NFR-08 | p95 < 800ms, 20.000 giao dịch, 10 user đồng thời | Đạt | **CHẠY** — *từng FAIL*, xem mục 5 |
| NFR-09 | Dashboard ≤ 10 query, không N+1 | Đạt | **CHẠY** — dashboard 7 query; *trend từng 12 query*, nay 1 |
| NFR-10 | Xóa sạch mọi bảng | Đạt | **CHẠY** — 8 bảng, zero orphan; *từng hỏng do `VARCHAR(100)` tràn* |
| NFR-11 | Import lại file giống hệt → 0 dòng mới | Đạt | **CHẠY** — new=0, duplicate=4 |
| NFR-12 | Administrative blindness | Đạt | **CHẠY** — response admin không chứa `amount`/`balance` |

### NFR chỉ có trong phần văn xuôi của SRS

| Yêu cầu | Trạng thái | Ghi chú |
|---|---|---|
| NFR-13 mật khẩu ≥10 ký tự, 3/4 nhóm | Đạt — **CHẠY** | mật khẩu yếu → 400 |
| NFR-14 secret từ biến môi trường | Đạt — **CHẠY** | `.env` đã loại khỏi bản nộp; **Huy phải xóa khỏi git history** |
| NFR-15 rate limit 10/phút | **CHƯA KIỂM** | Có mã nguồn, chưa chạy kịch bản |
| NFR-16 autoescape, không `\|safe` | Đạt — **ĐỌC** | Frontend dùng `esc()` thủ công |
| NFR-17 CSP không `unsafe-inline` | Đạt — **CHẠY** | *từng chặn toàn bộ progress bar*; nay 0 inline style |
| NFR-18 validate phía server | Đạt — **CHẠY** | Mọi input sai đều bị chặn ở server |
| NFR-19 `DEBUG=False` ngoài local | **Một phần** | Flask mặc định False, nhưng **không set tường minh** ở đâu cả |
| NFR-20 `pip-audit` sạch | Đạt — **CHẠY** | *No known vulnerabilities found* |
| NFR-21 tối thiểu hóa dữ liệu | Đạt — **ĐỌC** | Không thu ID/số thẻ/OTP/vị trí |
| NFR-27 chặn <18 tuổi | Đạt — **CHẠY** | |
| Accessibility (WCAG AA) | **CHƯA KIỂM** | Chưa chạy axe/Lighthouse |

---

## 4. Data & MySQL Requirements

| ID | Nội dung | Trạng thái | Giá trị đo được |
|---|---|---|---|
| DR-01 | Tiền là `BIGINT` VND | Đạt — **CHẠY** | *từng trả JSON string do `Decimal`* |
| DR-02 | Dedup ép ở tầng DB | Đạt — **CHẠY** | UNIQUE trên `dedup_key` |
| DR-03 | `DATETIME(6)` UTC, cấm `TIMESTAMP` | Đạt — **CHẠY** | 0 cột `TIMESTAMP` |
| DR-04 | `ON DELETE CASCADE` | Đạt — **CHẠY** | Zero orphan sau xóa |
| DR-05 | Alembic, cấm `create_all` ngoài test | Đạt — **CHẠY** | *chuỗi từng vỡ*; nay 8 revision sạch, **drift = 0** |
| DR-06 | Index bắt buộc | **Đạt sau khi sửa** | Index có sẵn nhưng **không được dùng** — xem mục 5 |
| MY-01 | MySQL ≥ 8.0.16 | Đạt — **CHẠY** | 8.0.46 |
| MY-02 | `utf8mb4` / `utf8mb4_0900_ai_ci` | Đạt — **CHẠY** | 0 bảng lệch, 0 cột lệch |
| MY-03 | charset trong URI | Đạt — **CHẠY** | |
| MY-04 | `dedup_key` là `BINARY(32)` | Đạt — **CHẠY** | `binary(32)` |
| MY-05 | `STRICT_TRANS_TABLES` + `ONLY_FULL_GROUP_BY` | Đạt — **CHẠY** | cả hai bật |
| MY-06 | `pool_pre_ping` + `pool_recycle=280` | Đạt — **ĐỌC** | |
| MY-07 | InnoDB toàn bộ | Đạt — **CHẠY** | 14/14 bảng InnoDB |
| MY-08 | `VARCHAR` + `CHECK`, cấm `ENUM` native | Đạt — **CHẠY** | 0 ENUM, 12 CHECK |
| MY-09 | `BIGINT` có dấu | Đạt — **CHẠY** | 0 cột unsigned |
| MY-10 | Integration test trên MySQL | **Một phần** | Đã chạy tay; **chưa có trong CI** |
| MY-11 | Migration một thay đổi logic mỗi bản | Đạt — **CHẠY** | Đã viết lại 01/02 |

---

## 5. Hai lỗi hiệu năng phát hiện trong đợt kiểm này

Cả hai chỉ lộ ra khi chạy thật với 20.000 giao dịch. Không lỗi nào có thể thấy bằng đọc code.

### 5.1 Pattern ORM vô hiệu hóa index mà DR-06 bắt buộc

`Transaction.account.has(Account.ledger.has(user_id=...))` đọc rất xuôi, nhưng biên dịch thành EXISTS lồng nhau. MySQL **không dùng được** `ix_transactions_account_posted` qua đó:

| Cách viết | `type` | `key` | Số dòng quét |
|---|---|---|---|
| `Account.ledger.has(user_id=…)` | `ALL` | `NULL` | **19.786** |
| `account_id IN (1,2,3)` | `range` | `ix_transactions_account_posted` | **625** |

Index tồn tại nhưng chưa bao giờ được dùng — **DR-06 đạt trên giấy, vô dụng trong thực tế.** Đã thay 8 chỗ bằng helper `user_account_ids()`.

### 5.2 `trend` là N+1 kinh điển

Vòng lặp 12 tháng, mỗi tháng một query. NFR-09 nói thẳng "N+1 patterns are defects". Gộp thành một `GROUP BY`: **12 query → 1 query, 105ms → 29ms**.

### Kết quả đo (gunicorn, 20.000 giao dịch, 10 client đồng thời, 60 request/endpoint)

| Endpoint | p95 trước | p95 sau | Ngưỡng |
|---|---|---|---|
| dashboard | 1202ms ❌ | **675ms** ✅ | 800ms |
| trend | 1632ms ❌ | **276ms** ✅ | 800ms |
| safe-to-spend | 762ms | 382ms | 800ms |
| transactions | 652ms | 269ms | 800ms |
| breakdown | 630ms | 209ms | 800ms |
| budgets | 350ms | 61ms | 800ms |
| alerts | 345ms | 68ms | 800ms |

**NFR-08: FAIL → PASS.**

### 5.3 Ghi chú quan trọng về cách đo

Số liệu trên đo bằng **gunicorn**, không phải `python run.py`. Dev server của Flask không phải WSGI production và không dùng để đo hiệu năng được. README hiện hướng dẫn `python run.py` — **cần bổ sung hướng dẫn chạy gunicorn cho phần đo NFR-08**, nếu không hội đồng hỏi "em đo trên gì" thì câu trả lời sẽ sai.

Đã thêm `gunicorn` vào `requirements.txt`.

---

## 6. Tình trạng chung

| Chỉ số | Giá trị |
|---|---|
| Unit test | **71 pass** |
| E2E qua HTTP trên MySQL | **67 assertion pass** |
| Coverage | **90%** (yêu cầu 60%) |
| Lint (`ruff`) | sạch |
| `pip-audit` | không có CVE |
| Migration từ DB rỗng | 8 revision, drift = 0 |
| Use Case **Must** | **10/10** |

---

## 7. Kết luận: bản này đã sẵn sàng chưa?

### Để nâng lên v3 — **RỒI**

Nền v2-slim đã vững: mọi Must đạt, đã kiểm bằng chạy thật, không còn lỗi P0/P1 nào đã biết. Có thể bắt đầu v3 ngay.

Phần v3 còn lại **thực chất chỉ là UC-10** (FR-55→59: ShareGrant). FR-54 (UI Admin) đã làm xong trong đợt trước dù v3 vẫn ghi *Planned*.

**Nhưng một cảnh báo bắt buộc:** v3 tự đánh dấu FR-31→FR-53 là *Implemented*. Đó là tuyên bố trên giấy. Đợt kiểm này cho thấy chính xác loại tuyên bố đó có thể sai — FR-19 từng ghi "Implemented" trong khi crash 500. **Trước khi chốt v3, phải kiểm từng dòng "Implemented" bằng chạy thật rồi mới giữ nhãn.** Nếu không, v3 sẽ thành tài liệu ghi nhận những thứ chưa từng chạy.

### Để viết thesis — **GẦN RỒI, còn 4 việc**

Phần **kỹ thuật** đã đủ cho một luận văn thực tập tốt. Cái còn thiếu là phần **học thuật**:

| # | Việc | Vì sao bắt buộc |
|---|---|---|
| 1 | **Xóa `.env` khỏi git history** | NFR-14. `SECRET_KEY` cũ coi như đã lộ |
| 2 | **Kiểm NFR-15 (rate limit) và accessibility** | Đang là *CHƯA KIỂM*. Không được viết "đạt" khi chưa đo |
| 3 | **Đưa test MySQL vào CI** (MY-10) | Ba lỗi P0 nặng nhất đều là SQLite-pass/MySQL-fail. Không có CI trên MySQL thì chắc chắn tái diễn |
| 4 | **Một đóng góp có thể đo được** | Đây là điểm yếu lớn nhất, xem dưới |

### Về việc thiếu "đóng góp"

Hiện tại đây là một **bài tập kỹ thuật tốt**: hiện thực hóa một SRS cho sẵn, làm cẩn thận, kiểm chứng nghiêm túc. Nhưng luận văn cần một câu hỏi có thể **đo** được — thứ mà một người đọc có thể phản bác bằng số liệu.

Ứng viên rõ ràng nhất là **module trích xuất sao kê** (`statement_profiler.py`). Nó có đủ hình dạng của một đóng góp: một luận điểm phản trực giác (*phần lớn bài toán này không cần AI, và cố dùng AI vào chỗ không cần chỉ làm mất khả năng kiểm chứng*), một cơ chế tự chứng minh (bất biến số dư), và một thiết kế ablation sẵn sàng chạy. Cái còn thiếu duy nhất là **dữ liệu thật**: sao kê từ nhiều ngân hàng, đã ẩn danh, cùng ground truth.

Nếu Huy dành phần thời gian còn lại cho việc thu thập bộ dữ liệu đó và chạy 5 cấu hình ablation ở mục 7 của `DESIGN-statement-extraction.md`, em ấy sẽ có một luận văn có nội dung thay vì một bản báo cáo tính năng.

### Thứ tự anh khuyến nghị

1. Việc 1–3 ở trên (nhanh, bắt buộc)
2. **Thu thập bộ dữ liệu sao kê thật + đo ablation** ← ưu tiên cao nhất cho luận văn
3. UC-10 để hoàn tất v3 (nếu còn thời gian)

Lưu ý thứ tự: UC-10 là tính năng, làm xong chỉ được thêm một mục trong bảng chức năng. Bộ dữ liệu và ablation mới là thứ quyết định luận văn có nội dung hay không. **Nếu phải chọn một, chọn cái sau.**

---

**MSc. Huỳnh Vinh Nam** · ICTLab / USTH
