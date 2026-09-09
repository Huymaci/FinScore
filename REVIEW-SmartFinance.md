# Rà soát & nâng cấp source code SmartFinance

**Sinh viên:** Nguyễn Tuấn Huy
**Đề tài:** Smart Personal Finance Management System (SmartFinance / SPFM)
**Chuẩn đối chiếu:** SRS v2-slim
**Người rà soát:** MSc. Huỳnh Vinh Nam
**Ngày:** 25/08/2026

---

## A. Kết luận tổng quan

Kiến trúc và chất lượng backend của em ở mức tốt. Phân tầng `routes → services → repositories → models` giữ đúng NFR-31, không có chỗ nào route gọi thẳng ORM. Parser XLSX tự viết bằng `zipfile` + `ElementTree` (không cần `openpyxl`) là điểm sáng thật sự. `dedup_key` lưu `BINARY(32)` đúng MY-04 thay vì `VARCHAR(64)` như đa số người làm. Coverage 89% trên yêu cầu 60%.

**Nhưng phần mềm không chạy được.** Đây là điều em cần hiểu rõ nhất từ lần review này: 28 test xanh, coverage 89%, lint sạch — mà một người dùng mở trình duyệt lên thì **không đăng ký nổi tài khoản**. Ba lỗi P0 nghiêm trọng nhất đều thuộc cùng một loại: *môi trường test khác môi trường thật, nên test không thể nhìn thấy lỗi*.

Toàn bộ đã được sửa và kiểm chứng. Sau khi sửa: `alembic upgrade head` chạy sạch từ DB rỗng, schema drift so với model = 0, 48 unit test pass, và **67 assertion end-to-end qua HTTP thật trên MySQL 8.0.46 đều pass**.

---

## B. Bài học phương pháp — phần quan trọng nhất

Ba lỗi P0 dưới đây có chung một nguyên nhân gốc: **SQLite trong test không hành xử giống MySQL trong thực tế, và Werkzeug test client không hành xử giống trình duyệt.**

| Lỗi | Trong test (SQLite / test client) | Trong thực tế (MySQL / trình duyệt) |
|---|---|---|
| Cookie `Secure` | test client bỏ qua cờ `Secure` → pass | trình duyệt không gửi cookie qua HTTP → **không đăng nhập được** |
| `SUM()` trên `BIGINT` | trả `int` → pass | trả `Decimal` → **`TypeError` sập FR-19** |
| `VARCHAR(100)` | SQLite không ép độ dài → pass | MySQL strict mode → **error 1406, xóa dữ liệu hỏng** |

Rút ra: **test suite xanh không phải bằng chứng phần mềm chạy được.** Trước mỗi lần nộp, bắt buộc chạy thêm smoke test trên MySQL thật và bấm thử trên trình duyệt thật. Anh đã ghi cảnh báo này vào `README.md` mục Test.

Lỗi thứ tư (chuỗi migration vỡ) đến từ nguyên nhân khác nhưng cùng bản chất: **test dùng `db.create_all()` nên chưa bao giờ chạy qua migration**. Đường đi mà người dùng thật sự dùng thì không ai kiểm tra.

Anh cũng lưu ý một điều về quy trình: em code backend bằng một session AI và frontend bằng một session khác. Điều đó không sai, nhưng nó tạo ra đúng loại lỗi ở mục D3 và D5 — hai bên đều "đúng" theo giả định riêng, chỉ sai ở chỗ giao nhau. Khi chia việc như vậy, **hợp đồng giữa hai bên (danh sách endpoint, kiểu dữ liệu trả về, danh sách category) phải là một tài liệu duy nhất** mà cả hai session cùng đọc, chứ không phải suy đoán của từng bên.

---

## C. Lỗi P0 — chặn hoàn toàn, phải hiểu rõ

### C1. Không ai đăng nhập được — cookie phiên bị đánh dấu `Secure` trên HTTP

`Flask-Talisman` ghi đè `SESSION_COOKIE_SECURE = True` ở **mọi request** (`talisman.py::_force_https`, dòng 247–249), bất kể `config.py` đặt gì. Trên setup HTTP localhost mà chính `README.md` của em hướng dẫn:

```
Set-Cookie: session=...; Secure; HttpOnly; Path=/; SameSite=Lax
                          ^^^^^^ trình duyệt sẽ không bao giờ gửi lại qua http://
```

Không có cookie quay về ⇒ `session['csrf_token']` biến mất ⇒ mọi `POST` chết với `The CSRF session token is missing.` ⇒ không đăng ký, không đăng nhập, không dùng được gì.

**Đây mới là lý do thật sự khiến "backend và frontend chưa unify"** — không phải lỗi ghép API như em nghĩ.

**Sửa:** truyền `session_cookie_secure=app.config["HTTPS_ENABLED"] and not app.testing` vào `talisman.init_app`. Production đặt `HTTPS_ENABLED=true` thì cờ `Secure` vẫn bật đúng.

### C2. FR-19 burn-rate detector sập trên MySQL

```
app/services/alerts.py:66, in recompute
TypeError: unsupported operand type(s) for /: 'decimal.Decimal' and 'float'
```

MySQL trả `SUM(BIGINT)` là `decimal.Decimal`; SQLite trả `int`. Dòng `projected = actual / weight` với `weight` là `float` (nhánh fallback `d/D` của FR-19) nổ ngay.

Hệ quả dây chuyền: `recompute()` được gọi trong `imports.confirm()`, nên **mọi lần confirm import đều trả 500**, và nightly job cũng chết. Nói cách khác, đúng cái thành phần mà SRS §1.2 nói cả hệ thống tồn tại để chứng minh thì không chạy được trên database thật.

Hệ quả thứ hai: Flask serialise `Decimal` thành **chuỗi JSON**, nên API trả `"7065000"` thay vì `7065000`. Frontend tạm thời sống sót nhờ JavaScript tự ép kiểu, nhưng đó là may mắn chứ không phải thiết kế.

**Sửa:** thêm helper `money()` trong `app/services/common.py`, ép về `int` tại ranh giới service (đúng DR-01: tiền là `BIGINT` VND). Áp cho cả 10 vị trí aggregate.

### C3. Chuỗi Alembic vỡ — `upgrade head` không chạy được từ DB rỗng

Migration `01` và `02` không viết DDL tường minh mà lặp `db.metadata.sorted_tables` rồi gọi `table.create()`. Nghĩa là chúng tạo bảng theo **model hiện tại**, không phải schema tại thời điểm revision đó. Hệ quả: `accounts` đã có sẵn cột `include_in_safe_to_spend` ngay từ migration 01, nên migration `03` chết:

```
(1060, "Duplicate column name 'include_in_safe_to_spend'")
```

Máy sạch làm đúng theo README sẽ hỏng ở bước 4. Vi phạm DR-05 và MY-11.

**Sửa:** viết lại `01` và `02` bằng `op.create_table()` tường minh, phản ánh đúng schema *tại thời điểm đó* (accounts chưa có cột kia). Đã kiểm chứng: chạy sạch 8 revision từ DB rỗng, và `compare_metadata()` cho **drift = 0** so với model.

### C4. CSP chặn chính giao diện của em

NFR-17 cấm `unsafe-inline`. Nhưng CSP `style-src` chặn **cả thuộc tính HTML `style=""`**, không chỉ thẻ `<style>`. Frontend của em sinh `style="width:83%"` cho mọi thanh tiến độ ⇒ trình duyệt chặn hết ⇒ **mọi progress bar hiển thị 0%**: tiến độ ngân sách, vòng ring, thanh Safe-to-Spend.

**Sửa:** phát ra `data-fill="83"` rồi để hàm `applyFills()` gán qua CSSOM (`element.style.width`). CSP **không** chặn CSSOM, nên cách này giữ được CSP nghiêm ngặt đúng NFR-17 thay vì phải nới lỏng. Đã thêm test tự động fail nếu có inline style lọt vào `index.html` hoặc `app.js`.

### C5. Quyền xóa dữ liệu hỏng trên MySQL

FR-05 ghi biên nhận xóa dạng `ACCOUNT_DELETED:<salt hex 32>:<sha256 hex 64>` = **113 ký tự**, nhưng cột `audit_logs.action` là `VARCHAR(100)`.

```
pymysql.err.DataError: (1406, "Data too long for column 'action' at row 1")
```

SQLite không ép độ dài `VARCHAR` nên test pass; MySQL strict mode lỗi cứng. Admin **không bao giờ thực thi được yêu cầu xóa** — vi phạm FR-05 và NFR-10.

**Sửa:** migration `08` nới cột lên `VARCHAR(200)`, cập nhật model kèm comment giải thích. Thiết kế salt+hash giữ nguyên vì nó đúng (chứng minh đã xóa mà không lưu lại email).

### C6. Lỗi 404/403/405 trả HTML thay vì JSON

`owned_or_404()` được dùng khắp service layer, nhưng 404 trả trang HTML mặc định của Flask. Hàm `responseData()` trong `app.js` thấy HTML là ném `"Không kết nối được API. Hãy chạy Flask..."` — người dùng bị báo sai hoàn toàn nguyên nhân.

**Sửa:** thêm `app/errors.py` trả JSON đồng nhất cho mọi mã lỗi, kèm correlation ID cho 500 đúng NFR-30 (không lộ stack trace ra trình duyệt).

---

## D. Lỗi P1 — chức năng khuyết

### D1. Không ghi được khoản thu

`scripts/seed.py` chỉ tạo 6 category: Nhà ở, Học phí, Điện nước, Ăn uống, Mua sắm, Nhiên liệu. Frontend lọc `.filter(x => x.nature)`, nên dropdown "Danh mục" **không có mục nào cho khoản thu**. Người dùng mới đăng ký không ghi nổi lương tháng.

Đồng thời `app.js` có bảng dịch cho 14 category (Di chuyển, Y tế, Học tập, Viễn thông, Thu nhập, Chuyển khoản…) mà seed chỉ tạo 6 — đây chính là dấu vết hai session viết lệch nhau.

**Sửa:** seed đủ 17 category theo cây 2 cấp đúng FR-09, 12 luật phân loại FR-15, 4 bank template. Idempotent, chạy lại không nhân đôi. Đã thêm test tự động fail nếu `app.js` dịch một category mà `seed.py` không tạo.

### D2. `Chuyển khoản` bị lọc nhưng không tồn tại

`statistics.py` lọc `Category.name != "Chuyển khoản"` ở cả dashboard, breakdown và trend để tránh đếm trùng khi chuyển tiền giữa hai tài khoản của chính mình. Nhưng seed không tạo category này, nên logic chống double-count là **no-op**. Đã tạo, cùng với `Uncategorised` cho FR-15.

### D3. Panel "Cảnh báo thông minh" trên dashboard là dữ liệu giả cứng

Hai thẻ cảnh báo và badge "3 mới" nằm cứng trong `index.html`, JS không bao giờ cập nhật. Dashboard vĩnh viễn hiển thị "Mua sắm đã vượt ngân sách 108%" bất kể dữ liệu thật. Đã nối vào API `/alerts`, badge lấy số unread thật.

Tương tự: 4 thẻ metric, bảng giao dịch gần đây, tổng ngân sách, phân trang "1–6 trong 48 giao dịch", avatar "LA" — đều là mock. Đã dọn sạch.

### D4. Thiếu hoàn toàn màn hình Admin (UC-11 là Must)

Backend có đủ 9 endpoint admin, frontend không có màn hình nào. Không demo được ở buổi bảo vệ.

**Đã dựng:** view `#admin` với 4 khối — chỉ số vận hành (FR-30, có ẩn khi < 5 user), danh sách user + tìm kiếm + khóa/mở/reset mật khẩu/thực thi xóa, bật-tắt bank template và luật phân loại, audit log. Mục "Quản trị" trên sidebar chỉ hiện khi `role = ADMIN`; `navigate()` chặn user thường gõ tay `#admin`. Đủ song ngữ vi/en (thêm 37 khóa dịch).

### D5. `delete_account()` sót bảng `habit_challenges`

NFR-10 yêu cầu truy vấn hậu-xóa trả zero rows **mọi bảng**. Hàm này cố tình xóa tường minh từng bảng để "verifiable", nhưng thiếu một bảng là thiếu bằng chứng. Đã bổ sung.

Kiểm chứng thực tế sau khi sửa: xóa 1 user ⇒ `users`, `ledgers`, `accounts`, `transactions`, `budgets`, `alerts`, `habit_challenges`, `import_batches` đều **0 dòng mồ côi**.

---

## E. Lỗi P2 — nợ kỹ thuật

| # | Vấn đề | Xử lý |
|---|---|---|
| E1 | `.env` commit kèm `SECRET_KEY=1234567890` — vi phạm NFR-14 | Đã loại khỏi bản nộp; **em phải xóa cả trong git history** |
| E2 | Migration `06` khai `created_at` là `DateTime()` không có `fsp=6` — lệch DR-03 | Sửa thành `DATETIME(fsp=6)`, thêm `mysql_engine/charset/collate` cho đồng bộ MY-02/MY-07 |
| E3 | Migration `07` để lại `server_default=""` cho `habit_key`/`habit_name`, model không có → drift | Drop default ngay sau backfill |
| E4 | `migrations/env.py` chỉ đọc được `DATABASE_URL` **một cách tình cờ** qua chuỗi import `app.models → app/__init__.py → config.py → load_dotenv()`. Đổi thứ tự import là hỏng | Gọi `load_dotenv()` tường minh |
| E5 | `scripts/nightly.py` chỉ gọi `recompute()` alerts, bỏ `evaluate_due()` và `generate_proposal()` của challenges | Đã bổ sung |
| E6 | `statistics/trend` frontend luôn gửi tháng hiện tại, bỏ qua tháng đang chọn | Dùng `state.statisticsMonth` |
| E7 | `new_count:'3 mới'` hardcode số 3 trong i18n | Đổi thành `'{count} mới'` |
| E8 | README chỉ có lệnh test PowerShell, hỏng trên Linux/macOS | Thêm nhánh bash |
| E9 | 13 lỗi lint `ruff` | Đã sạch |

---

## F. Kiểm chứng — bằng chứng, không phải lời hứa

Anh không đọc code rồi đoán. Anh dựng môi trường thật và chạy:

- **MySQL 8.0.46** thật, không phải SQLite
- `alembic upgrade head` từ database **rỗng hoàn toàn** → 8 revision chạy sạch
- `compare_metadata()` model vs schema đã migrate → **drift = 0**
- **48 unit test** pass, coverage **88.68%**
- **67 assertion end-to-end qua HTTP thật** (register → login → account → transaction → import CSV → confirm → budget → safe-to-spend → alert → statistics → admin → export → erasure) → **toàn bộ pass**
- `ruff` sạch

### Kiểm chứng ngược: test có thật sự bắt được lỗi không?

Anh không tin một test chỉ vì nó xanh. Anh **cố tình hoàn tác từng bản sửa** rồi chạy lại:

| Hoàn tác | Test phản ứng |
|---|---|
| Bỏ `session_cookie_secure` | `SessionCookieTest::test_cookie_is_not_secure_when_https_is_disabled` **FAIL** |
| Đổi `money()` về `value or 0` | `MoneyCoercionTest` **2 test FAIL** |
| Khôi phục cả hai | 19/19 **PASS** |

Đây gọi là mutation testing. Em nên áp dụng cách này: **viết xong test thì phá code xem test có đỏ không.** Test không đỏ khi code sai là test vô dụng.

### 19 regression test mới

File `tests/test_regressions.py` khoá lại từng lỗi trên, mỗi test có comment giải thích *vì sao suite cũ không thể bắt được nó*. Bao gồm cả các test cấu trúc: cấm migration dùng `db.metadata`, cấm inline style trong frontend, bắt buộc `.gitignore` phủ `.env`, kiểm tra chuỗi migration tuyến tính và chỉ có một head.

---

## G. Việc em cần làm tiếp

**Bắt buộc trước khi nộp:**

1. **Xóa `.env` khỏi git history**, không chỉ khỏi thư mục. Dùng `git filter-repo` hoặc BFG. `SECRET_KEY` cũ coi như đã lộ — sinh key mới bằng `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Chạy lại toàn bộ quy trình trong `README.md` **trên máy sạch** và bấm thử trên trình duyệt. Đừng nộp khi chưa tự làm bước này.
3. Thống nhất bản SRS. Repo đang có cả `SRS-SmartFinance.md` (v1), `v2-slim` và `v3`. **v2-slim là bản chuẩn cho vòng này.** Xóa hoặc chuyển hai bản kia vào thư mục `docs/archive/`.

**Nên làm:**

4. Bổ sung test chạy trên MySQL trong CI, không chỉ SQLite. Đây là biện pháp duy nhất ngăn tái diễn ba lỗi ở mục B.
5. Cân nhắc thời điểm tính lại alert. Hiện tại đúng FR-20 (nightly + sau import), nhưng khi demo em ghi giao dịch tay thì cảnh báo không hiện ngay — hội đồng dễ tưởng là lỗi. Chuẩn bị sẵn câu trả lời, hoặc chạy `python -m scripts.nightly` trước khi demo.
6. `pip-audit` theo NFR-20 trước khi nộp.

**Ngoài phạm vi lần này:**

7. UC-10 (chia sẻ trạng thái) vẫn chưa làm — đúng, vì priority là **Should**.
8. Nâng lên SRS v3: thêm FR-31→FR-59, DR-07→DR-10. Việc này làm sau khi v2-slim đã ổn định và được duyệt.

---

## Nhận xét cuối

Em viết code sạch và có kỷ luật kiến trúc — đó là phần khó dạy. Phần còn thiếu là **kỷ luật kiểm chứng**: em tin vào test suite thay vì tin vào việc phần mềm thật sự chạy. Ba lỗi P0 nặng nhất đều nằm đúng ở khoảng trống giữa "môi trường test" và "môi trường thật", và không lỗi nào trong đó đòi hỏi kỹ thuật cao để phát hiện — chỉ cần một lần mở trình duyệt lên bấm thử.

Lần sau, trước khi báo cáo "đã xong", hãy tự trả lời: *mình đã chạy nó đúng như cách người dùng sẽ chạy chưa?*

---

**MSc. Huỳnh Vinh Nam**
ICTLab / USTH
