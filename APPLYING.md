# Cách áp dụng bản đã sửa vào repo hiện có

**Đọc hết trước khi làm.** Chỉ chép đè file là **chưa đủ** — có ba việc ngoài file, và một trường hợp có thể làm hỏng database nếu bỏ qua.

---

## 0. Vì sao file .zip chỉ 186 KB còn bản gốc 30 MB

Không mất gì cả. Bản `.rar` gốc giải nén ra 108 MB, trong đó:

| Thư mục | Dung lượng | Tỷ lệ |
|---|---|---|
| `.venv` | 104 MB | **96,3%** |
| `.git` | 2,7 MB | 2,5% |
| Toàn bộ mã nguồn thật | ~1,2 MB | 1,2% |

Đã đối chiếu danh sách file: bản gốc có **67 file** (không tính `.venv`, `.git`, cache), bản nộp có **74**. Thiếu đúng **một** file là `.env` (cố ý loại), thêm **tám** file mới.

Hai lưu ý:

- `.venv/Lib` và `.venv/Scripts` viết hoa — đó là venv **Windows**, không chạy được trên Linux/macOS. Venv không bao giờ nên nằm trong file nộp; nó phải dựng lại từ `requirements.txt`.
- **Lần sau nộp bài đừng nén cả thư mục.** Dùng `git archive -o nop-bai.zip HEAD`. Nó chỉ đóng gói những gì đã commit, tự động bỏ `.env`, `.venv` và mọi thứ trong `.gitignore`.

---

## 1. Đừng thay thế repo bằng file .zip

Bản nộp **không có `.git`**, nên nếu giải nén đè lên cả thư mục thì em mất 3 commit lịch sử.

Cách đúng:

```bash
# 1. Sao lưu trước cho chắc
git branch backup-truoc-review

# 2. Giải nén ra chỗ khác
unzip SmartExpense-v2slim-verified.zip -d /tmp/review

# 3. Chép đè phần mã nguồn (KHÔNG chép .env)
cp -r /tmp/review/SmartExpense/app        ./
cp -r /tmp/review/SmartExpense/frontend   ./
cp -r /tmp/review/SmartExpense/migrations ./
cp -r /tmp/review/SmartExpense/scripts    ./
cp -r /tmp/review/SmartExpense/tests      ./
cp -r /tmp/review/SmartExpense/docs       ./
cp /tmp/review/SmartExpense/{config.py,run.py,requirements.txt,README.md,.env.example,.gitignore} ./
cp /tmp/review/SmartExpense/REVIEW-SmartFinance.md ./

# 4. Xem đúng những gì thay đổi rồi mới commit
git status
git diff
```

`.env` của em giữ nguyên, không đụng vào.

---

## 2. `.venv` — giữ lại, nhưng phải cài thêm một gói

Không cần xóa `.venv`. Nhưng `requirements.txt` **có thay đổi**: thêm `gunicorn` (dùng để đo NFR-08 — dev server của Flask không đo hiệu năng được).

```bash
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Đó là khác biệt duy nhất về thư viện.

---

## 3. Database — phần dễ hỏng nhất

### 3.1 Kiểm em đang ở trạng thái nào

```bash
.\.venv\Scripts\python.exe -m alembic current
```

**Trạng thái A — lành (nhiều khả năng là trường hợp của em).**
Kết quả in ra `20260824_07`. Em đã migrate dần theo thời gian, mỗi migration chạy khi model còn nhỏ, nên schema của em đúng. Lỗi chuỗi migration chỉ xuất hiện khi dựng **database mới từ đầu** — đó là lý do em không gặp bao giờ.

**Trạng thái B — kẹt.**
Kết quả in ra `20260819_02`. Xảy ra nếu em (hoặc ai đó) từng thử dựng DB mới và chết ở migration 03. Ở trạng thái này `alembic upgrade head` sẽ **hỏng vĩnh viễn** với `Duplicate column name 'include_in_safe_to_spend'` — vì migration 01 cũ (chạy từ metadata) đã tạo sẵn cột đó rồi.

### 3.2 Trạng thái A: chạy migration 08

```bash
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Chỉ đúng **một** migration chạy: `20260824_07 -> 20260825_08` (nới `audit_logs.action` từ `VARCHAR(100)` lên `VARCHAR(200)`, cần cho FR-05).

Anh đã kiểm chứng đường này: chạy xong, so schema với model cho **drift = 0**.

Migration 01–07 giữ nguyên revision ID nên Alembic **không** chạy lại chúng — dữ liệu của em an toàn.

### 3.3 Trạng thái B: dựng lại database

Đây là DB dev, dựng lại nhanh hơn nhiều so với gỡ rối bằng `alembic stamp`, và chắc chắn khớp với thứ mà người chấm sẽ nhận được:

```sql
DROP DATABASE smartfinance;
CREATE DATABASE smartfinance CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

```bash
.\.venv\Scripts\python.exe -m alembic upgrade head    # chạy đủ 8 revision
.\.venv\Scripts\python.exe -m scripts.seed
```

**Đừng dùng `alembic stamp` để "nhảy cóc" qua chỗ kẹt.** Schema do migration cũ tạo ra không tương ứng chính xác với bất kỳ revision nào, nên stamp sẽ để lại drift âm thầm — đúng loại lỗi mà cả đợt review này đi tìm.

---

## 4. Seed lại — và một chỗ cần để ý

```bash
.\.venv\Scripts\python.exe -m scripts.seed
```

Seed là idempotent, chạy lại không nhân đôi. Nó sẽ bổ sung **11 category mới** (8 → 17) và **10 luật phân loại mới**.

### Chỗ cần để ý: hai luật cũ ở priority 10 và 20

Seed cũ đã tạo hai luật ở priority 10 và 20. Seed mới kiểm trùng **theo priority**, nên nó **giữ nguyên bản cũ** thay vì ghi đè — cố ý như vậy, vì admin có thể đã sửa luật qua giao diện (FR-29) và seed không được phép xóa công sức đó.

Hệ quả: hai luật của em vẫn dùng pattern hẹp hơn bản mới.

```
  [seed] priority 10 đã tồn tại với pattern khác, giữ nguyên bản cũ:
         hiện có : highlands|coffee|cafe
         bản mới : highlands|starbucks|coffee|cafe|ca phe|trung nguyen|phuc long
  [seed] priority 20 đã tồn tại với pattern khác, giữ nguyên bản cũ:
         hiện có : shopee|lazada|tiki
         bản mới : shopee|lazada|tiki|sendo|dien may|the gioi di dong
```

Seed sẽ **in cảnh báo** này ra màn hình (trước đây nó bỏ qua im lặng). Không phải lỗi — chỉ là pattern cũ khớp được ít hơn. Nếu em muốn dùng bản rộng hơn:

```sql
UPDATE categorization_rules
SET pattern = 'highlands|starbucks|coffee|cafe|ca phe|trung nguyen|phuc long'
WHERE priority = 10;

UPDATE categorization_rules
SET pattern = 'shopee|lazada|tiki|sendo|dien may|the gioi di dong'
WHERE priority = 20;
```

---

## 5. Kiểm lại sau khi áp dụng

```bash
.\.venv\Scripts\python.exe -m pytest -q                  # kỳ vọng: 71 passed
.\.venv\Scripts\python.exe -m ruff check app tests scripts migrations
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

Rồi mở trình duyệt và **tự bấm thử**: đăng ký → tạo tài khoản → ghi một khoản thu → ghi một khoản chi → đặt ngân sách → import một file CSV. Đây là bước mà nếu làm một lần từ đầu thì cả 5 lỗi P0 đã lộ ra hết.

Kiểm schema khớp model (nên chạy sau mọi lần đổi migration):

```bash
.\.venv\Scripts\python.exe -c "import os;from dotenv import load_dotenv;load_dotenv();from alembic.runtime.migration import MigrationContext;from alembic.autogenerate import compare_metadata;from sqlalchemy import create_engine;from app.extensions import db;import app.models;e=create_engine(os.environ['DATABASE_URL']);c=e.connect();print('DRIFT:',len(compare_metadata(MigrationContext.configure(c),db.metadata)))"
```

Kết quả phải là `DRIFT: 0`.

---

## 6. Tóm tắt

| Việc | Bắt buộc? |
|---|---|
| Chép đè mã nguồn (giữ `.git`, giữ `.env`) | có |
| `pip install -r requirements.txt` (gunicorn) | có |
| `alembic current` → xác định trạng thái A hay B | **có** |
| `alembic upgrade head` (A) hoặc dựng lại DB (B) | **có** |
| `python -m scripts.seed` | có |
| Sửa pattern luật 10 và 20 | tùy chọn |
| Chạy test + tự bấm thử trên trình duyệt | có |

---

**MSc. Huỳnh Vinh Nam** · ICTLab / USTH
