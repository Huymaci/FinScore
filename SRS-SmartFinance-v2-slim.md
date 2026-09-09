# SOFTWARE REQUIREMENTS SPECIFICATION (SRS)

## Smart Personal Finance Management System (SmartFinance / SPFM)

| Trường | Giá trị |
|---|---|
| Phiên bản | 4.1 — Cập nhật tài khoản ngân hàng, logo và số dư hiện tại |
| Ngày cập nhật | 07/09/2026 |
| Dự án | Thực tập cử nhân — ICTLab / USTH |
| Người hướng dẫn | MSc. Huỳnh Vinh Nam |
| Công nghệ | HTML5/CSS/JavaScript · Python 3.11+ / Flask · SQLAlchemy 2.x · MySQL 8.0.16+ / InnoDB |

> Tài liệu được đối chiếu với mã nguồn, migration và test suite ngày 06/09/2026.
> Yêu cầu “Dự kiến” không được dùng làm bằng chứng hoàn thành.
> Bản 4.1 bổ sung các thay đổi quản lý tài khoản ngày 07/09/2026 theo mã nguồn.
> Đã kiểm tra cú pháp JavaScript và sự tồn tại của 65 logo; test backend số dư đã
> bổ sung nhưng chưa chạy được do môi trường Python lỗi. “Đã triển khai” không
> đồng nghĩa đã hoàn tất nghiệm thu.

---

## 1. Giới thiệu

### 1.1 Mục đích và mục tiêu

SmartFinance giúp người trưởng thành quản lý tài chính cá nhân bằng cách ghi nhận
hoặc nhập giao dịch từ sao kê, lập ngân sách tháng, tính Safe-to-Spend (STS), cảnh
báo sớm nguy cơ vượt ngân sách và đề xuất thử thách giảm chi tiêu lặp lại. Hệ thống
không thực hiện thanh toán và không kết nối trực tiếp tới ngân hàng.

### 1.2 Phạm vi

Baseline bắt buộc gồm xác thực, hồ sơ và avatar, tài khoản tiền, giao dịch, danh mục,
nhập sao kê, ngân sách, cảnh báo, thống kê, thử thách thói quen, hỗ trợ người dùng và
quản trị. Chia sẻ trạng thái ngân sách là tính năng Should chưa triển khai.

### 1.3 Thuật ngữ

| Thuật ngữ | Định nghĩa |
|---|---|
| Tài khoản tiền | Ví tiền mặt hoặc tài khoản ngân hàng do người dùng khai báo; không phải kết nối ngân hàng trực tuyến. |
| Tài khoản STS | Tài khoản có số dư và giao dịch được đưa vào phép tính Safe-to-Spend. |
| Số dư đầu kỳ | Số tiền người dùng khai báo làm mốc trước các giao dịch được ghi nhận trong tài khoản. |
| Số dư hiện tại | Số dư đầu kỳ cộng toàn bộ giao dịch thu đã lưu, trừ toàn bộ giao dịch chi đã lưu của chính tài khoản; không phải số dư đồng bộ trực tiếp từ ngân hàng. |
| Safe-to-Spend | Số dư khả dụng đến cuối tháng, trừ phần ngân sách cam kết/bán cố định còn phải dành. |
| Nature | `COMMITTED`, `SEMI_FIXED` hoặc `DISCRETIONARY`. |
| Burn-rate | Tốc độ chi dùng để dự phóng tổng chi cuối tháng. |
| Import template | Cấu hình ánh xạ cột để đọc một định dạng sao kê. |
| Probable duplicate | Dòng nhập gần giống giao dịch thủ công theo tài khoản, ngày và số tiền. |
| Administrative blindness | Admin quản trị vận hành nhưng không được xem dữ liệu tài chính định danh. |

### 1.4 Tác nhân

| Tác nhân | Mô tả |
|---|---|
| Khách | Xem thông báo quyền riêng tư, đăng ký, đăng nhập. |
| Người dùng | Quản lý hồ sơ và dữ liệu tài chính của mình. |
| Admin | Tài khoản được seed; quản trị metadata và vận hành. |
| Tác vụ định kỳ | Tính cảnh báo, đánh giá thử thách và dọn dữ liệu hết hạn. |

Trạng thái yêu cầu gồm **Đã triển khai**, **Một phần** (lõi đã có nhưng còn phụ thuộc
cấu hình/bằng chứng) và **Dự kiến** (chưa có trong baseline).

---

## 2. Tổng quan kỹ thuật

```text
Browser (HTML/CSS/JavaScript, Fetch API, Chart.js)
                         |
                         | HTTPS / JSON, same origin
                         v
Flask routes -> services -> repositories -> SQLAlchemy models
                         |
                         v
                  MySQL 8 / InnoDB
```

- VND là đơn vị tiền duy nhất và được lưu bằng số nguyên.
- Người đăng ký phải đủ 18 tuổi.
- File sao kê tối đa 5 MB; avatar tối đa 2 MB.
- Production dùng MySQL 8.0.16+; SQLite chỉ dùng cho unit test độc lập.
- Request thay đổi trạng thái phải qua session authentication và CSRF.
- Bí mật/chuỗi kết nối lấy từ biến môi trường; không nhận số tài khoản đầy đủ, OTP,
  mật khẩu ngân hàng hoặc thông tin thẻ.

---

## 3. Use case

| ID | Use case | Tác nhân | Ưu tiên | Trạng thái |
|---|---|---|---|---|
| UC-01 | Đăng ký, đăng nhập, đăng xuất | Khách/User | Must | Đã triển khai |
| UC-02 | Quản lý hồ sơ, avatar, mật khẩu, xuất/xóa dữ liệu | User | Must | Đã triển khai |
| UC-03 | Quản lý tài khoản tiền và phạm vi STS | User | Must | Đã triển khai |
| UC-04 | Quản lý giao dịch và danh mục | User | Must | Đã triển khai |
| UC-05 | Xem trước và xác nhận nhập sao kê | User | Must | Đã triển khai |
| UC-06 | Xử lý lỗi/trùng và lịch sử import | User | Must | Đã triển khai |
| UC-07 | Lập ngân sách và tính STS | User | Must | Đã triển khai |
| UC-08 | Nhận và xử lý cảnh báo | User/Tác vụ | Must | Đã triển khai |
| UC-09 | Xem dashboard và thống kê | User | Must | Đã triển khai |
| UC-10 | Tham gia thử thách thói quen | User/Tác vụ | Must | Đã triển khai |
| UC-11 | Gửi và xử lý báo cáo hỗ trợ | User/Admin | Must | Đã triển khai |
| UC-12 | Quản trị người dùng và vận hành | Admin | Must | Đã triển khai |
| UC-13 | Chia sẻ trạng thái ngân sách có đồng thuận | User | Should | Dự kiến |

---

## 4. Yêu cầu chức năng

### 4.1 Xác thực, hồ sơ và vòng đời tài khoản

| ID | Yêu cầu | Trạng thái |
|---|---|---|
| FR-01 | Hiển thị thông báo quyền riêng tư trước đăng ký; lựa chọn đồng ý không được chọn sẵn. | Đã triển khai |
| FR-02 | Đăng ký bằng email duy nhất, họ tên, ngày sinh và mật khẩu hợp lệ; từ chối người dưới 18 tuổi. | Đã triển khai |
| FR-03 | Khóa tài khoản 15 phút sau 5 lần đăng nhập sai liên tiếp; đăng nhập thành công tạo session mới. | Đã triển khai |
| FR-04 | Đăng xuất xóa session; đổi mật khẩu yêu cầu mật khẩu hiện tại. | Đã triển khai |
| FR-05 | User cập nhật email, họ tên, ngày sinh và trạng thái đồng ý xử lý dữ liệu. | Đã triển khai |
| FR-06 | User xuất ZIP gồm JSON, CSV giao dịch và avatar nếu có. | Đã triển khai |
| FR-07 | User gửi yêu cầu xóa; admin thực thi xóa dữ liệu cá nhân. | Đã triển khai |
| FR-08 | User tải/xem/thay/xóa avatar PNG, JPEG hoặc WebP tối đa 2 MB. | Đã triển khai |
| FR-09 | Avatar được kiểm tra magic byte, đặt tên ngẫu nhiên, chống path traversal và ghi atomic; file cũ được dọn. | Đã triển khai |

### 4.2 Tài khoản, giao dịch và danh mục

| ID | Yêu cầu | Trạng thái |
|---|---|---|
| FR-10 | Đăng ký tạo đúng một ledger cá nhân. | Đã triển khai |
| FR-11 | API hỗ trợ tạo/sửa tài khoản `CASH`/`BANK` với tên và số dư đầu kỳ. Giao diện thêm tài khoản chỉ tạo `BANK`, gồm tên, số dư đầu kỳ, bốn số cuối và chọn ngân hàng; không nhập mã ngân hàng tự do. | Đã triển khai |
| FR-12 | User lưu trữ, khôi phục hoặc xóa vĩnh viễn tài khoản theo điều kiện toàn vẹn dữ liệu. | Đã triển khai |
| FR-13 | Cờ `include_in_safe_to_spend` cho phép loại tiền tiết kiệm/dự phòng khỏi STS. | Đã triển khai |
| FR-14 | User CRUD giao dịch: ngày, amount dương, `IN`/`OUT`, tài khoản, danh mục, mô tả. | Đã triển khai |
| FR-15 | Danh sách giao dịch phân trang server, lọc theo ngày/tài khoản/danh mục/chiều; tối đa 100 dòng/trang. | Đã triển khai |
| FR-16 | Mọi thao tác theo ID kiểm tra ownership; ID của user khác không làm lộ đối tượng tài chính. | Đã triển khai |
| FR-17 | Hệ thống seed cây danh mục hai cấp; danh mục lá có nature. | Đã triển khai |
| FR-18 | User thêm/đổi tên danh mục riêng; xóa danh mục đang dùng phải chỉ định danh mục thay thế. | Đã triển khai |

#### 4.2.1 Chọn ngân hàng và số dư tài khoản (UC-03)

Các ID bổ sung tiếp nối FR-54 để giữ nguyên tham chiếu yêu cầu hiện có.

| ID | Yêu cầu | Trạng thái |
|---|---|---|
| FR-55 | Bộ chọn ngân hàng đọc `frontend/assets/bank-logos/manifest.json`, hiển thị logo, tên ngắn và tên đầy đủ; tìm theo tên/mã, không phân biệt hoa/thường và dấu tiếng Việt. | Đã triển khai |
| FR-56 | Người dùng phải chọn một mục trong danh mục trước khi gửi form; mục đã chọn hiển thị logo và tên, còn API nhận `bank_code`. Có trạng thái đang tải, không có kết quả, lỗi và nút thử lại. | Đã triển khai |
| FR-57 | “Tài khoản của tôi” hiển thị logo tương ứng bên trái mỗi tài khoản ngân hàng, kể cả tài khoản đã lưu trữ. Nhận diện các alias được hỗ trợ; thiếu ảnh/mã không nhận diện được dùng biểu tượng dự phòng, không hiện đồng thời logo và fallback. | Đã triển khai |
| FR-58 | API tài khoản trả `opening_balance` và `current_balance`; số dư hiện tại tính độc lập theo tài khoản bằng `opening_balance + Σ(IN.amount) − Σ(OUT.amount)` từ toàn bộ giao dịch đã lưu, không phụ thuộc bộ lọc ngày/tháng hoặc phân trang giao diện. | Đã triển khai |
| FR-59 | Danh sách tài khoản ghi rõ “Số dư hiện tại”; làm mới số dư sau thêm/xóa giao dịch, xác nhận nhập/xóa giao dịch sao kê, theo chu kỳ 60 giây khi trang hoạt động và khi tab hiển thị trở lại. | Đã triển khai |
| FR-60 | Có script PowerShell tải logo theo danh mục VietQR, chuẩn hóa PNG 256×256 giữ tỷ lệ và căn giữa, xuất ZIP kèm manifest. Giao diện dùng asset cục bộ của ứng dụng. | Đã triển khai |

Luồng thêm tài khoản: mở “Tài khoản của tôi” → nhập tên, số dư đầu kỳ và bốn số
cuối → mở bộ chọn, tìm và chọn ngân hàng → lưu → tải lại danh sách tài khoản với
logo và số dư hiện tại. Sau khi lưu thành công, form trở về trạng thái chưa chọn
ngân hàng. Bộ chọn hỗ trợ Tab/Enter và Escape để đóng danh sách, trả focus về ô chọn.

Bốn ô trong form bố trí hai cột rộng bằng nhau, chiều cao ô nhập và ô chọn khi đóng
là 42 px. Logo trong ô chọn là 28×28 px; logo ở dòng tài khoản là 40×40 px; file
nguồn vẫn là PNG 256×256. Tên dài trong ô chọn được rút gọn bằng dấu ba chấm.

Danh mục hiện có 65 mục gồm ngân hàng và một số tổ chức/dịch vụ thanh toán theo
nguồn VietQR; không xem đây là cam kết bao phủ mọi ngân hàng tại Việt Nam. Script
`scripts/download_bank_logos.ps1` tạo `frontend/assets/bank-logos/` và
`frontend/assets/bank-logos.zip`; manifest ghi mã, tên, file, nguồn và thời điểm tạo.

Số dư hiện tại bao gồm giao dịch thủ công và giao dịch import đã xác nhận; dữ liệu
chỉ đang preview không ảnh hưởng số dư. Tài khoản chưa có giao dịch có số dư bằng
số dư đầu kỳ; kết quả được phép âm. Việc tính toán không ghi đè số dư đầu kỳ và
không thay đổi phạm vi/công thức STS tại FR-31–FR-32.

### 4.3 Nhập sao kê

| ID | Yêu cầu | Trạng thái |
|---|---|---|
| FR-19 | User tải `.csv`/`.xlsx`, chọn tài khoản đích và template đang hoạt động. | Đã triển khai |
| FR-20 | Parser hỗ trợ amount có dấu hoặc cột nợ/có, preamble song ngữ, delimiter phổ biến và header trong 40 dòng đầu. | Đã triển khai |
| FR-21 | Template tổng quát dùng profiler suy luận header/cột; bất biến số dư ưu tiên kiểm chứng cột số. | Đã triển khai |
| FR-22 | Import luôn preview trước, thống kê mới, trùng, nghi trùng và lỗi mà chưa tạo giao dịch. | Đã triển khai |
| FR-23 | SHA-256 dedup key dùng tài khoản, ngày, amount, tham chiếu và mô tả; nhập lại dữ liệu giống nhau tạo 0 dòng. | Đã triển khai |
| FR-24 | Dòng gần giao dịch thủ công theo cùng tài khoản, ngày ±1, amount ±1% yêu cầu quyết định bỏ/gộp hoặc giữ cả hai. | Đã triển khai |
| FR-25 | Regex phân loại theo priority; user được override; dòng không khớp vào `Uncategorised`. | Đã triển khai |
| FR-26 | Lỗi giữ số dòng/lý do và tải được CSV; confirm ghi atomic các dòng hợp lệ được chấp nhận. | Đã triển khai |
| FR-27 | XLSX zip bomb bị chặn bằng giới hạn kích thước thành phần sau giải nén. | Đã triển khai |
| FR-28 | User xem lịch sử import và xóa toàn bộ giao dịch của batch `COMMITTED`; batch chuyển `REVERTED`, cảnh báo được tính lại. | Đã triển khai |
| FR-29 | Lịch sử import giữ đến khi user tự xóa (từng lần hoặc toàn bộ); khi xóa user chọn giữ hay xóa kèm giao dịch đã nhập, giữ thì giao dịch chỉ bị gỡ liên kết batch. | Đã triển khai |

### 4.4 Ngân sách, cảnh báo và thống kê

| ID | Yêu cầu | Trạng thái |
|---|---|---|
| FR-30 | User tạo/cập nhật một ngân sách không âm cho mỗi category/month và sao chép phần còn thiếu từ tháng trước. | Đã triển khai |
| FR-31 | STS chỉ dùng tài khoản được chọn và giao dịch đến cuối tháng đang xem. | Đã triển khai |
| FR-32 | `STS = số dư STS − Σ max(0, ngân sách − đã chi)` cho `COMMITTED` và `SEMI_FIXED`. | Đã triển khai |
| FR-33 | Detector ngưỡng cảnh báo ở 80% và nghiêm trọng ở 100% ngân sách danh mục. | Đã triển khai |
| FR-34 | Burn-rate dùng trung vị tỷ lệ tích lũy 6 tháng, fallback `d/D` nếu dưới 3 tháng; cảnh báo khi dự phóng >105%. | Đã triển khai |
| FR-35 | Cảnh báo có loại, severity, giải thích, hành động gợi ý, trạng thái, category, thời điểm, dedup key và cooldown 72 giờ. | Đã triển khai |
| FR-36 | User xem inbox và đặt `READ`/`DISMISSED`; import kích hoạt tính lại. Lệnh nightly có sẵn nhưng lịch production do operator cấu hình. | Một phần |
| FR-37 | Dashboard hiển thị thu, chi, ròng, STS và tiến độ ngân sách bằng cả màu lẫn chữ. | Đã triển khai |
| FR-38 | Thống kê có cơ cấu chi theo khoảng ngày và xu hướng 12 tháng theo tháng neo. | Đã triển khai |
| FR-39 | Dữ liệu làm mới sau mutation, mỗi 60 giây khi active và khi tab visible trở lại. | Đã triển khai |
| FR-40 | UI hỗ trợ Việt/Anh, theme sáng/tối/hệ thống, responsive từ 360 px và lưu preference cục bộ. | Đã triển khai |

### 4.5 Thử thách thói quen

| ID | Yêu cầu | Trạng thái |
|---|---|---|
| FR-41 | Phân tích 28 ngày, tìm khoản chi tùy ý lặp lại ít nhất 4 lần và tạo tối đa một đề xuất đang mở. | Đã triển khai |
| FR-42 | User chấp nhận/từ chối; thử thách được chấp nhận kéo dài 7 ngày. | Đã triển khai |
| FR-43 | Hệ thống theo dõi số lần, đánh giá `COMPLETED`/`FAILED`, ước tính tiền tiết kiệm và điều chỉnh mục tiêu lần sau. | Đã triển khai |
| FR-44 | Không đề xuất lại cùng thói quen trong 30 ngày sau khi bị từ chối. | Đã triển khai |

### 4.6 Hỗ trợ và quản trị

| ID | Yêu cầu | Trạng thái |
|---|---|---|
| FR-45 | User gửi báo cáo hỗ trợ với subject 3–160, message 10–4.000 ký tự và xem lịch sử của mình. | Đã triển khai |
| FR-46 | Admin lọc báo cáo `OPEN`/`RESOLVED`, đổi trạng thái và ghi audit log. | Đã triển khai |
| FR-47 | Chỉ role `ADMIN` được seed mới vào `/admin`; không có đường nâng quyền runtime. | Đã triển khai |
| FR-48 | Admin tìm kiếm/phân trang metadata user, khóa/mở khóa, cấp mật khẩu tạm và thực thi xóa. | Đã triển khai |
| FR-49 | Admin xem/bật tắt template/rule seed; authoring mới thực hiện qua seed script. | Đã triển khai |
| FR-50 | Admin xem chỉ số vận hành/audit; tổng hợp dưới 5 user bị ẩn. | Đã triển khai |
| FR-51 | API/UI admin không hiển thị số dư, amount, merchant, mô tả hoặc giao dịch định danh. | Đã triển khai |

### 4.7 Chia sẻ có đồng thuận

| ID | Yêu cầu | Trạng thái |
|---|---|---|
| FR-52 | Chủ dữ liệu cấp quyền tối đa 90 ngày cho user đã đăng ký; không có cơ chế yêu cầu truy cập. | Dự kiến |
| FR-53 | Người nhận chỉ xem trạng thái xanh/vàng/đỏ; không nhận amount, balance, merchant, mô tả hay giao dịch. | Dự kiến |
| FR-54 | Chủ dữ liệu thu hồi ngay; quyền hết hạn không tự gia hạn; mọi lượt xem được ghi log. | Dự kiến |

---

## 5. Yêu cầu dữ liệu

### 5.1 Thực thể

`users`, `ledgers`, `accounts`, `categories`, `transactions`, `import_templates`,
`import_batches`, `import_errors`, `categorization_rules`, `budgets`, `alerts`,
`habit_challenges`, `support_reports`, `audit_logs`.

Chia sẻ dự kiến mới bổ sung `share_grants` và `share_access_logs`.

### 5.2 Quy tắc bắt buộc

| ID | Quy tắc |
|---|---|
| DR-01 | Tiền là signed `BIGINT`; transaction amount dương, direction mang ngữ nghĩa dấu. |
| DR-02 | `transactions.dedup_key` là database-unique `BINARY(32)`. |
| DR-03 | Instant lưu UTC bằng `DATETIME(6)`; không dùng MySQL `TIMESTAMP` cho dữ liệu miền. |
| DR-04 | Dữ liệu thuộc user dùng FK/cascade phù hợp để xóa đầy đủ. |
| DR-05 | Mỗi user có một ledger; budget unique theo user/category/month. |
| DR-06 | Enum miền là chuỗi có `CHECK`, không dùng native `ENUM`. |
| DR-07 | Schema chỉ thay đổi qua Alembic; `create_all()` chỉ dùng trong test. |
| DR-08 | Bảng dùng InnoDB, `utf8mb4`, `utf8mb4_0900_ai_ci`. |
| DR-09 | Có index cho transaction(account/date), dedup, alert(user/time), challenge(user/status), support(status/time). |
| DR-10 | `preview_json` dùng `LONGTEXT` trên MySQL. |
| DR-11 | Export bao gồm mọi thực thể cá nhân, trạng thái STS và avatar. |
| DR-12 | `current_balance` là giá trị tính khi trả API, không phải cột mới trong database; tổng hợp giao dịch theo `account_id` thuộc người dùng hiện tại. |
| DR-13 | Logo và manifest là asset dùng chung, không chứa số tài khoản hay giao dịch; việc chọn ngân hàng chỉ lưu mã cùng bốn số cuối trong thông tin tài khoản. |

MySQL phải từ 8.0.16; URI chỉ định `charset=utf8mb4`; giữ `STRICT_TRANS_TABLES` và
`ONLY_FULL_GROUP_BY`; engine bật `pool_pre_ping=True`, `pool_recycle=280`. Test về
collation, constraint, ngày và kiểu số phải chạy trên MySQL. Migration chứa một thay
đổi logic và phải được diễn tập vì MySQL DDL không rollback đầy đủ.

---

## 6. Yêu cầu phi chức năng

### 6.1 Bảo mật và quyền riêng tư

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| NFR-01 | PBKDF2-SHA256 ≥600.000 vòng; cấm mật khẩu plaintext/reversible. | Hash review, auth test |
| NFR-02 | Mật khẩu ≥10 ký tự, có 3/4 nhóm ký tự và từ chối mật khẩu phổ biến. | Unit test |
| NFR-03 | Cookie `HttpOnly`, `SameSite=Lax`, `Secure` khi HTTPS; idle timeout 30 phút. | Header/session test |
| NFR-04 | Login/register tối đa 10 request/phút; khóa nghiệp vụ độc lập rate limit. | Rate-limit test |
| NFR-05 | Endpoint thay đổi trạng thái yêu cầu CSRF; truy cập trái phép trả 401/403/404 phù hợp. | Security test |
| NFR-06 | Chỉ dùng ORM/bound parameter; không ghép SQL từ input. | Code review/Bandit |
| NFR-07 | Upload kiểm tra size, extension, magic byte và zip bomb; file tạm được dọn. | Upload test |
| NFR-08 | CSP không `unsafe-inline`; có `nosniff`, chống frame, autoescape. | Header/static scan |
| NFR-09 | Admin không có code path đọc dữ liệu tài chính định danh. | Review + negative test |
| NFR-10 | Log không chứa password, token, amount, description hay email đầy đủ. | Log review |
| NFR-11 | Xóa user loại bỏ bản ghi/file cá nhân; chỉ giữ hash email có salt trong audit xóa. | Truy vấn trước/sau |
| NFR-12 | Không quảng cáo, credit scoring, model training hoặc tiết lộ bên thứ ba. | Code/policy review |

### 6.2 Hiệu năng, độ tin cậy và chất lượng

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| NFR-13 | Coverage tổng ≥60%; parser, dedup, STS, detector ≥85%. | `pytest-cov` |
| NFR-14 | p95 trang đọc <800 ms với 20.000 giao dịch, 10 user đồng thời trên WSGI. | Locust/ApacheBench |
| NFR-15 | Dashboard ≤10 SQL query/render. | Query-count test |
| NFR-16 | Import lại file giống nhau tạo 0 transaction mới. | Automated test |
| NFR-17 | Confirm import, xóa batch, ghi transaction và đổi support status là atomic. | Integration test |
| NFR-18 | Lỗi chưa xử lý trả thông báo chung/correlation ID, không lộ stack trace. | Error test |
| NFR-19 | Tuân theo `routes → services → repositories → models`; ruff sạch. | Review + CI |
| NFR-20 | UI dùng được bằng bàn phím, focus rõ, có loading/empty/error; màu không là dấu hiệu duy nhất. | Accessibility review |
| NFR-21 | Dependency được pin, không có CVE High/Critical khi nộp. | `pip-audit` |

---

## 7. Nghiệm thu và thí nghiệm

### 7.1 Kiểm thử bắt buộc

1. Unit/component suite chạy xanh trên môi trường sạch.
2. Alembic nâng từ database rỗng đến `head` trên MySQL.
3. Smoke test HTTP trên MySQL cho auth, CRUD, import, budget, alert, challenge,
   support và admin.
4. Corpus sao kê kiểm tra số dòng và tổng nợ/có, không chỉ “parse không lỗi”.
5. Kiểm tra xóa tài khoản trên mọi bảng và vùng avatar.
6. Chạy ruff, coverage, pip-audit và kiểm tra security header.

#### Nghiệm thu bổ sung cho UC-03 (v4.1)

| Kịch bản | Kết quả mong đợi |
|---|---|
| Tìm theo mã/tên có hoặc không dấu; chọn ngân hàng và lưu | Danh sách lọc đúng; payload chứa mã đã chọn; tài khoản mới hiển thị đúng logo. |
| Chưa chọn ngân hàng hoặc tải manifest thất bại | Không gửi form thiếu lựa chọn; có thông báo phù hợp và thử tải lại khi lỗi. |
| Logo thiếu; tài khoản dùng alias hỗ trợ | Thiếu ảnh chỉ hiện fallback; alias ánh xạ đúng ảnh. |
| Kiểm tra form sáng/tối và màn hình 360 px | Bốn ô rộng bằng nhau theo hai cột, cao 42 px khi bộ chọn đóng; logo không làm tăng chiều cao ô. |
| Tài khoản A: đầu kỳ 1.000.000, thu 500.000, chi 200.000 | Số dư hiện tại 1.300.000 VND; đầu kỳ vẫn 1.000.000 VND. |
| Tài khoản B: đầu kỳ 1.000.000, chi 1.500.000; C chưa có giao dịch | B là −500.000 VND; C là 1.000.000 VND; không cộng lẫn giao dịch các tài khoản. |
| Xóa khoản chi 200.000 của A | Số dư A thành 1.500.000 VND sau làm mới. |
| Preview, xác nhận và xóa giao dịch sao kê | Preview không đổi số dư; chỉ các giao dịch đã lưu đóng góp vào số dư; xóa giao dịch tính lại tổng. |
| Đổi tháng/bộ lọc giao dịch hoặc truy cập bằng user khác | Số dư tài khoản không bị giới hạn theo bộ lọc; không trả tài khoản/số dư của user khác. |

Test hồi quy số dư nằm trong `tests/test_account_management.py`, phương thức
`test_current_balance_is_per_account_and_tracks_deleted_transactions`. Cần chạy
test backend và nghiệm thu giao diện trên trình duyệt trước khi kết luận toàn bộ
các kịch bản bổ sung đạt.

### 7.2 Thí nghiệm

- **E1 — Cảnh báo:** ít nhất 50 episode vượt ngân sách trên 24 tháng; báo cáo
  Precision, Recall, F1 và lead time cho ngưỡng 80%, `d/D` và `w(d)`.
- **E2 — Phát hiện trùng:** đo Precision/Recall qua nhập lại giống hệt, khoảng ngày
  chồng lấn, import sau nhập thủ công và thứ tự dòng thay đổi.
- **E3 — Trích xuất sao kê:** trên dữ liệu ẩn danh có ground truth, đo độ chính xác
  header/cột, hướng tiền, số dòng và chạy ablation theo
  `docs/DESIGN-statement-extraction.md`.

### 7.3 Bàn giao

Repository và lịch sử commit; Alembic/seed; bộ sinh ≥24 tháng và 20.000 giao dịch;
test suite; bằng chứng NFR; báo cáo có ERD, kết quả E1–E3 và giới hạn nghiên cứu.

---

## 8. Ngoài phạm vi

| Hạng mục | Lý do |
|---|---|
| API ngân hàng trực tiếp, thanh toán/chuyển tiền | Cần hợp đồng, quyền truy cập và kiểm soát tuân thủ ngoài đồ án. |
| Đọc SMS/thông báo | Rủi ro riêng tư, hạn chế nền tảng, dữ liệu thiếu định danh ổn định. |
| Sổ cái hộ gia đình | Mở rộng lớn bề mặt tenancy/phân quyền. |
| Chia sẻ transaction/balance | Merchant và mô tả có thể tiết lộ dữ liệu nhạy cảm. |
| Friendship/access request | Có thể gây áp lực đồng thuận; nếu làm UC-13 chỉ chủ dữ liệu được khởi tạo. |
| Visual template editor | Template là data nhưng authoring thực hiện qua seed script. |
| Đa tiền tệ, đầu tư, nợ, mobile, microservice | Ngoài timebox và mục tiêu nghiên cứu. |
| AI/dịch vụ phân loại bên ngoài | Khó tái lập và tăng rủi ro dữ liệu; baseline dùng heuristic/regex kiểm chứng được. |

---

## 9. Thay đổi chính so với v2

| Thay đổi | Cập nhật |
|---|---|
| Avatar | Thêm FR-08–FR-09. |
| Tài khoản loại khỏi STS | Đặc tả tại FR-13. |
| Profiler tổng quát/bảo vệ XLSX | Thêm FR-20–FR-21, FR-27. |
| Lịch sử import/xóa theo batch | Đưa vào phạm vi tại FR-28–FR-29 theo implementation. |
| Thử thách thói quen | Thêm UC-10, FR-41–FR-44. |
| Báo cáo hỗ trợ | Thêm UC-11, FR-45–FR-46. |
| Admin UI | Chuyển sang Đã triển khai. |
| Chia sẻ trạng thái | Giữ Should/Dự kiến vì chưa có model, API hoặc UI. |
| Thí nghiệm profiler | Thêm E3 để phản ánh đóng góp kỹ thuật. |
| Mã hóa | Chuẩn hóa UTF-8, loại bỏ lỗi mojibake của bản cũ. |

---

### Cập nhật v4.1 ngày 07/09/2026

- Làm rõ FR-11: UI thêm tài khoản ngân hàng, API vẫn hỗ trợ `CASH`/`BANK`.
- Bổ sung FR-55–FR-60: bộ chọn logo, số dư hiện tại, làm mới và script asset/ZIP.
- Bổ sung DR-12–DR-13, quy cách kích thước form và kịch bản nghiệm thu UC-03.
- Phân biệt trạng thái triển khai với bằng chứng kiểm thử còn cần thực hiện.

*Prepared for ICTLab / USTH — SmartFinance SRS v4.1*
