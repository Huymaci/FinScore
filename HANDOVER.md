# Bản gộp — đọc trước khi chạy

**Ngày:** 01/09/2026 · **Người gộp:** MSc. Huỳnh Vinh Nam · ICTLab / USTH

Bản này lấy **code của em làm nền** và vá 6 lỗi. Không có chỗ nào công việc của em bị thay bằng công việc của anh.

---

## 1. Việc cần làm ngay: quay lại MySQL

`.env` của em đang là:

```
DATABASE_URL=sqlite:///D:/SmartExpense/instance/smartexpense.db
```

Việc này vi phạm **MY-01** (bắt buộc MySQL ≥ 8.0.16) và **MY-10** (SQLite chỉ cho unit test thuần). Nhưng lý do thật sự quan trọng hơn ràng buộc trên giấy.

**Cả bốn lỗi P0 nặng nhất của dự án này đều là loại SQLite chạy được / MySQL chết.** Em đang phát triển trong đúng môi trường đã che giấu chúng:

| Lỗi | Trên SQLite | Trên MySQL |
|---|---|---|
| `SUM()` trả `Decimal` | trả `int`, chạy bình thường | `TypeError`, sập FR-19 |
| `audit_logs.action` `VARCHAR(100)` | không ép độ dài | lỗi 1406, hỏng quyền xóa dữ liệu |
| EXISTS lồng nhau | không có EXPLAIN để thấy | quét toàn bảng, bỏ qua index |
| `preview_json` kiểu `TEXT` | không giới hạn | **lỗi 1406, 6/8 file import chết 500** |

Lỗi cuối cùng anh **vừa tìm ra trong chính lần gộp này**, khi chạy code của em lên MySQL. Trên máy em nó sẽ không bao giờ xuất hiện.

Sửa `.env`:

```
DATABASE_URL=mysql+pymysql://smartfinance:<mật khẩu>@127.0.0.1:3306/smartfinance?charset=utf8mb4
```

Ký tự đặc biệt trong mật khẩu phải percent-encode: `#` → `%23`, `@` → `%40`.

---

## 2. Sáu lỗi đã vá

| # | Lỗi | Hậu quả thật |
|---|---|---|
| 1 | `import_batches.preview_json` khai `TEXT` (65.535 byte) | **6/8 file sao kê trả HTTP 500.** Một file 183 giao dịch, mỗi dòng kèm `dedup_key` hex 64 ký tự và câu lý do phân loại tiếng Việt, vượt ngưỡng. → migration `20260901_11`, đổi sang `LONGTEXT` |
| 2 | `if debit:` kiểm trên **chuỗi** `"0.00"` | **Mọi khoản thu nhập biến mất.** Template MB ghi cột không dùng là `"0.00"` chứ không để trống; `"0.00"` là truthy nên mọi dòng ghi có bị đẩy sang nhánh ghi nợ, tính ra 0, rồi loại. File SHB mất **đúng 15 dòng lương**. → `_zero_as_absent()` |
| 3 | `find_header_row(max_scan=15)` | Header thật của template MB nằm ở **dòng 19**, sau logo song ngữ. Quét không tới nên bám nhầm dòng "Loại tiền/Currency", rồi dòng header bị đọc thành giao dịch. → `DEFAULT_HEADER_SCAN = 40` |
| 4 | `csv.Sniffer` chết vì dòng preamble | CSV phân cách `;` (Excel mặc định ở locale dùng dấu phẩy thập phân) bị đọc thành **một cột**. **Đây là lỗi khiến test `test_uc05_auto_template_reads_bilingual_preamble_and_debit_credit` của chính em đang đỏ.** → `_sniff_delimiter()` đếm tần suất trên các dòng có dạng bảng |
| 5 | XLSX không giới hạn dung lượng sau giải nén | File **797 KB giải nén ra 800 MB** lọt qua `MAX_CONTENT_LENGTH` 5 MB rồi giết worker bằng `MemoryError`. Với 5 MB được phép, cùng tỉ lệ cho ra ~5 GB. → `MAX_UNCOMPRESSED_MEMBER` / `_safe_read()` |
| 6 | Biểu đồ xu hướng không theo khoảng ngày chọn | Chọn khoảng mới → biểu đồ quạt đổi, đường xu hướng đứng yên ở cửa sổ nạp lúc khởi động. Hai biểu đồ cạnh nhau mô tả hai thời kỳ khác nhau, không có dấu hiệu gì. → `trendAnchorMonth()` + form submit gọi cả hai |

---

## 3. Những gì anh **không** đụng vào — vì em làm tốt

Anh phải nói rõ: trong lần rà này anh đã **ba lần** tìm tên hàm của mình trong code em, không thấy, rồi kết luận sai rằng em chưa tích hợp. Thực tế em tự làm, đặt tên khác. Kiểm bằng tên hàm thay vì bằng hành vi là lỗi của anh.

**Cách em nối profiler tinh tế hơn bản anh đưa.** Anh lấy thẳng kết quả profiler. Em thêm một lớp phòng vệ:

> Khi bất biến số dư chứng minh được mapping → tin profiler cho các cột số, chỉ dùng header cho phần ngữ nghĩa. Khi **không** chứng minh được → ưu tiên header rõ ràng, vì "STT dễ bị nhầm thành Số tiền".

Đó là nhận xét đúng mà anh không nghĩ tới, và nó xử lý đúng trường hợp nguy hiểm nhất: profiler đoán sai một cột số mà không ai kiểm chứng được. Anh giữ nguyên.

Các phần khác cũng giữ nguyên:

- **Avatar upload** viết chuẩn: kiểm magic-byte thay vì tin đuôi file, tên ngẫu nhiên `token_hex(24)`, chặn path traversal bằng `Path(filename).name != filename`, ghi atomic qua file tạm rồi `os.replace`, dọn ảnh cũ. `delete_account()` lấy đường dẫn avatar **trước** khi xóa user rồi unlink **sau** — đúng thứ tự, xử lý cả file trên đĩa cho NFR-10.
- **Support reports**: validate độ dài min/max, `@admin_required` đúng chỗ trên cả hai endpoint admin, ghi audit log khi đổi trạng thái, `list_for_user` lọc theo `user_id`.
- **Khoảng ngày tùy chọn** cho biểu đồ quạt, có validate cả phía server.
- Bỏ qua dòng trống khi import — em tự làm trước anh.

Một điểm đáng khen riêng: em **viết test cho ca "preamble song ngữ + nợ/có" trước khi giải quyết được nó**. Test đúng, code chưa tới. Đó là thứ tự làm việc đúng. Chỉ nhắc một điều: **đừng nộp khi suite còn đỏ** — hãy sửa, hoặc đánh dấu `@unittest.expectedFailure` kèm ghi chú, để người đọc biết em đã biết.

---

## 4. Đã bổ sung

- `tests/fixtures/statements/` — **8 file sao kê giả lập** làm corpus hồi quy (mỗi file có footer ghi rõ là dữ liệu giả lập, nên đưa vào repo được).
- `tests/test_real_statements.py` — khoá lại từng lỗi ở mục 2, kèm phép kiểm độc lập: file VPBank tự khai tổng phát sinh nợ/có trong phần đầu, và hệ thống tính ra **đúng từng đồng** (`11.800.000` / `7.289.000`, số dư cuối kỳ khớp). Đây là bằng chứng số liệu **đúng**, không chỉ "parse được".
- `AlertMonthScopeTest` trong `test_regressions.py` — ghim lại việc `recompute()` chỉ xét tháng hiện tại.
- `APPLYING.md` — hướng dẫn áp dụng.

---

## 5. Kết quả kiểm chứng

Chạy thật, không suy luận:

| Hạng mục | Kết quả |
|---|---|
| `alembic upgrade head` từ DB **rỗng** trên MySQL 8.0.46 | 11 revision, sạch |
| Schema drift so với model | **0** |
| Unit test | **101 pass** (từ 92 pass + 1 fail) |
| E2E qua HTTP trên MySQL | **50/50** và **17/17** |
| Import 8 file sao kê thật | **8/8**, tổng **1.198 giao dịch**, 0 lỗi (VPBank 1 lỗi là dòng footer ghi chú — từ chối đúng) |
| `ruff` | sạch |
| Inline style trong frontend | 0 (CSP vẫn nghiêm, NFR-17) |

---

## 6. Việc em cần làm

**Bắt buộc:**

1. **Đổi `.env` về MySQL.** Không thương lượng. Xem mục 1.
2. Chạy `alembic upgrade head` — sẽ chạy migration `20260901_11`.
3. Chạy lại test + **tự bấm thử trên trình duyệt**: import một file sao kê, kiểm xem các khoản **thu nhập** có xuất hiện không (đó là lỗi số 2).

**Về quy trình:**

4. Lần này em **thay cả repo bằng file zip**, nên mất sạch 3 commit lịch sử — đúng thứ `APPLYING.md` cảnh báo. Lần sau chép đè từng thư mục con, xem `git diff`, rồi commit.
5. Khi nộp bài dùng `git archive -o nop-bai.zip HEAD`, đừng nén cả thư mục. Bản `.rar` em gửi nặng 124 MB, trong đó **110 MB là `.venv`** — mà lại là venv Windows, người chấm dùng hệ khác cũng không chạy được.

**Đưa test MySQL vào CI** là biện pháp duy nhất ngăn loại lỗi ở mục 1 tái diễn. Bốn lần rồi.

---

**MSc. Huỳnh Vinh Nam** · ICTLab / USTH
