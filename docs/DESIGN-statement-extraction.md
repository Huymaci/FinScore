# Trích xuất sao kê ngân hàng bất kể định dạng

**Mission:** nạp lịch sử giao dịch từ file Excel của **bất kỳ ngân hàng nào**, không cần viết template thủ công cho từng ngân hàng.

**Người thiết kế:** MSc. Huỳnh Vinh Nam · ICTLab / USTH
**Trạng thái:** prototype đã chạy, 5/5 layout thử nghiệm nhận diện đúng
**File mã nguồn:** `app/services/statement_profiler.py`

---

## 1. Trực giác đầu tiên là sai

Khi nghe "mỗi ngân hàng một format, làm sao tự động?", phản xạ tự nhiên là: *đưa file cho LLM, bảo nó đọc*. Anh muốn em dừng lại ở đây và nghĩ kỹ, vì hướng đó sẽ **trượt ở buổi bảo vệ** dù demo có đẹp đến đâu.

Ba vấn đề không thể chối:

**Không kiểm chứng được.** LLM trả về `{"amount": 4}`. Đúng hay sai? Em không có cách nào biết ngoài việc tự nhìn. Với dữ liệu tài chính, "model bảo thế" không phải là câu trả lời chấp nhận được. Hội đồng sẽ hỏi *"làm sao em biết nó đúng?"* và em sẽ không có gì để nói.

**Sai âm thầm.** Nếu nó chọn nhầm cột số dư thành cột số tiền, hệ thống vẫn import trơn tru — chỉ là toàn bộ số liệu tài chính của người dùng sai. Đây là failure mode tệ nhất: hỏng mà không báo.

**Không tất định.** Cùng một file, chạy hai lần có thể ra hai kết quả. Không reproduce được thì không viết được test, không viết được test thì không có luận văn.

Cộng thêm một ràng buộc mà em hay quên: **NFR-21 yêu cầu data minimisation.** Sao kê ngân hàng là dữ liệu tài chính cá nhân. Gửi nguyên file lên API bên thứ ba là vấn đề nghiêm trọng về pháp lý lẫn đạo đức, không chỉ về kỹ thuật.

---

## 2. Câu hỏi đúng

Đừng hỏi *"cột nào tên giống 'số tiền'?"*. Hỏi:

> **Cách gán cột nào làm cho bảng tính này tự nhất quán về mặt số học?**

Với phần lớn sao kê, câu hỏi này có **đáp án chứng minh được**, không phải phỏng đoán.

### Bất biến số dư — chìa khóa của toàn bộ bài toán

Hầu hết sao kê đều in **cột số dư lũy kế**. Nếu có, thì với mọi dòng *i*:

```
balance[i] − balance[i−1] == signed_amount[i]
```

Một phương án gán cột hoặc thỏa mãn điều này trên ~toàn bộ số dòng, hoặc không. Khi nó thỏa mãn, phương án đó **được chứng minh đúng** — không cần điểm tin cậy, không cần model, không cần dữ liệu huấn luyện. Chỉ là số học.

Đây là toàn bộ ý tưởng. Nó biến một bài toán nhận dạng mơ hồ thành một bài toán **kiểm chứng tất định**.

Điểm mạnh phụ mà em nên nhấn trong luận văn: bất biến này còn phát hiện được **file bị sửa hoặc thiếu dòng**. Prototype đã kiểm chứng: khi chèn một sai lệch vào giữa file, hệ thống báo `18/19 dòng khớp` và **từ chối tuyên bố đã chứng minh**.

---

## 3. Kiến trúc 5 tầng

```
L0  grid          — ô đã có kiểu (parser xlsx của em đã làm được)
L1  profile       — thống kê kiểu/định dạng cho từng cột
L2  candidates    — liệt kê các phương án gán vai trò
L3  verify        — chấm điểm theo bất biến   ← quyết định đúng/sai
L4  fingerprint   — lưu phương án thắng thành template tái dùng
```

Không tầng nào cần gọi mạng hay chạy model. LLM — **nếu dùng** — chỉ nằm giữa L2 và L3: nó được phép **đề xuất**, không bao giờ được phép **quyết định**.

### Nguyên tắc xuyên suốt: quyết định ở cấp cột, không phải cấp ô

Đây là bài học kỹ thuật quan trọng nhất trong module này. Một ô đơn lẻ thường mơ hồ; năm mươi ô cùng cột thì gần như không bao giờ.

| Mơ hồ ở cấp ô | Giải quyết ở cấp cột |
|---|---|
| `01/02/2026` — dd/mm hay mm/dd? | Chỉ cần **một** ô có thành phần đầu > 12 là chốt cho cả cột |
| `1.234` — một nghìn hai trăm hay 1,234? | Nhóm cuối đúng 3 chữ số ⇒ dấu phân cách nghìn, áp cho cả cột |
| `46083` — số tiền hay Excel date-serial? | Cột ngày có ~mọi giá trị trong dải serial **và** trải trong cửa sổ ngắn |

Cái thứ ba anh chỉ phát hiện khi chạy test thật, và nó rất đáng chú ý: **một khoản 46.083 ₫ trông y hệt ngày 05/03/2026 dạng serial.** Đọc code chay không bao giờ thấy được điều này. Đây chính là lý do anh luôn bắt em chạy thật thay vì suy luận.

---

## 4. Kết quả prototype

Năm layout cố tình thiết kế xung khắc nhau:

| Layout | Đặc điểm | Kết quả |
|---|---|---|
| A · VCB-like | header dòng 0, một cột số tiền có dấu, **không có số dư** | đúng, tin cậy 0.74 |
| B · TCB-like | **3 dòng preamble**, ghi nợ/ghi có tách, có số dư | **chứng minh 24/24** |
| C · hostile | header `TXN_DT/BAL_AFT/MVMT` (không có trong alias nào), ngày mm/dd, cột nhiễu `FX_RT` | **chứng minh 24/24** |
| D · Excel-native | ngày là serial, tiền là float, không có chuỗi nào | **chứng minh 24/24** |
| E · headerless | **không có dòng tiêu đề** | **chứng minh 23/23** |

Case C và E là điểm đáng nói: chúng thắng **không nhờ đọc header** — C dùng tên cột không ai đoán được, E không có header. Chúng thắng nhờ số học. Đây là bằng chứng cho luận điểm ở mục 2.

### Ba bẫy — kiểm tra nó có biết *từ chối* không

Với dữ liệu tài chính, biết nói "tôi không chắc" quan trọng ngang biết trả lời đúng.

| Bẫy | Kỳ vọng | Kết quả |
|---|---|---|
| Cột mồi gần giống cột tiền | chọn đúng cột thật | chọn đúng, `proved=True` |
| Không có số dư, hai cột số ngang nhau | **không được tự tin** | `conf=0.35`, `needs_human_review=True` |
| Có số dư nhưng file bị sửa | **không được tuyên bố chứng minh** | `proved=False`, báo `18/19` |

---

## 5. LLM nằm ở đâu — và chỉ ở đó

Sau L3, chỉ còn lại các file **không có cột số dư** *và* header dùng từ ngữ lạ. Đó là phần LLM thực sự hữu ích: bài toán **đặt tên ngữ nghĩa**, không phải bài toán trích xuất.

Quy tắc bắt buộc:

**1. LLM đề xuất, bộ kiểm tra quyết định.** Output của LLM phải chạy ngược qua đúng bộ kiểm tra ở L3. Không đạt thì loại, chuyển sang giao diện map thủ công. Không bao giờ để output LLM đi thẳng vào database.

**2. Không gửi dữ liệu thật.** Đây là điểm em cần nghĩ kỹ. Không cần gửi file, thậm chí không cần gửi dòng mẫu. Chỉ cần gửi **hồ sơ thống kê**:

```
Cột 0: header "TXN_DT",  100% parse được thành ngày, tăng dần
Cột 2: header "BAL_AFT", 100% số, khoảng 4.6e7–5.3e7, không âm
Cột 4: header "MVMT",    100% số, có cả âm lẫn dương
```

Đủ để đặt tên vai trò, mà **không một số tiền, tên người hay nội dung giao dịch nào rời khỏi máy chủ**. Đây là cách thỏa mãn NFR-21 chứ không phải lách nó.

**3. Phải là opt-in tường minh.** Người dùng bấm nút "Nhờ AI hỗ trợ nhận diện", không phải mặc định.

---

## 6. Vòng học — lý do AI gần như không bao giờ phải chạy

Khi một phương án được xác nhận (bằng bất biến hoặc bằng người dùng sửa tay), lưu lại theo **fingerprint** = hash của (dòng header đã chuẩn hóa + số cột).

File sau từ cùng ngân hàng → trùng fingerprint → dùng lại mapping ngay, **không suy luận, không gọi AI**.

Nghĩa là chi phí AI là **một lần cho mỗi ngân hàng**, không phải một lần cho mỗi lần upload. Sau vài tuần vận hành, tỷ lệ file cần suy luận sẽ tiệm cận 0. Đây mới là phần có giá trị sản phẩm thật, và nó cũng là câu trả lời cho câu hỏi *"chi phí vận hành thế nào?"* mà hội đồng chắc chắn sẽ hỏi.

---

## 7. Cách đo — phần làm nên luận văn

Ý tưởng hay mà không đo được thì không thành luận văn. Em cần:

**Bộ dữ liệu.** Thu thập sao kê thật từ càng nhiều ngân hàng càng tốt (VCB, TCB, MB, BIDV, ACB, VPBank, Agribank, Sacombank, TPBank...). **Ẩn danh trước khi lưu vào repo** — thay tên, số tài khoản, giữ nguyên cấu trúc. Bổ sung biến thể tổng hợp cho các trường hợp hiếm.

**Chỉ số.**

| Chỉ số | Ý nghĩa |
|---|---|
| Exact-mapping accuracy | % file gán đúng **toàn bộ** vai trò |
| Transaction P/R/F1 | so với ground truth từng giao dịch |
| **Auto-resolution rate** | % file xử lý xong **không cần con người** ← chỉ số sản phẩm quan trọng nhất |
| **Proof rate** | % file được bất biến chứng minh |
| **Silent-failure rate** | % file sai mà hệ thống *tưởng* mình đúng ← **phải bằng 0** |

Chỉ số cuối là chỉ số quan trọng nhất về mặt an toàn. Một hệ thống có auto-resolution 70% và silent-failure 0% tốt hơn nhiều một hệ thống 95% mà thỉnh thoảng ghi sai số liệu không ai biết.

**So sánh (ablation).** Đây là phần cho điểm cao:

1. Chỉ khớp header (tức `_auto_mapping` hiện tại) — baseline
2. Chỉ LLM
3. Chỉ suy luận cấu trúc, không bất biến
4. Đầy đủ (suy luận + bất biến)
5. Đầy đủ + LLM cho phần còn dư

Nếu số liệu cho thấy (4) đã gần bằng (5), em có một kết luận đáng giá: *phần lớn bài toán này không cần AI, và cố dùng AI vào chỗ không cần chỉ làm mất khả năng kiểm chứng.* Đó là một phát biểu có nội dung, khác hẳn "em dùng AI để tự động hóa".

---

## 7b. Trả lời phản biện: "Mỗi ngân hàng mới lại phải định nghĩa template riêng?"

Đây là câu hỏi hội đồng gần như chắc chắn sẽ hỏi. Nó đúng với `_auto_mapping` cũ, và **sai với thiết kế này** — nhưng em phải trả lời bằng số liệu, không bằng lập luận.

### Thí nghiệm 1 — Sáu ngân hàng, bốn trong đó chưa từng thấy

Bốn định dạng dưới đây được nghĩ ra **sau khi** module đã viết xong, cố tình phá mọi giả định về thứ tự cột:

| Ngân hàng | Đặc điểm phá cách | Kết quả |
|---|---|---|
| VCB | một cột tiền có dấu, **không có số dư** | đúng, conf 0.74 |
| TCB | 3 dòng preamble, ghi nợ/ghi có | **chứng minh** |
| ACB\* | **số dư ở cột đầu, ngày ở cột cuối** | **chứng minh** |
| BIDV\* | **hai cột ngày** (hạch toán + giá trị) | **chứng minh** |
| VPB\* | mọi số có hậu tố ` VND`, mã GD trước ngày | **chứng minh** |
| AGRI\* | ngày `yyyy-mm-dd`, số âm trong ngoặc `(1,234)` | **chứng minh** |

`*` = định dạng mới, **không viết thêm một dòng code nào**. Đó là câu trả lời trực tiếp: không có template nào được thêm.

### Thí nghiệm 2 — Bảng gợi ý header có phải template trá hình không?

Phản biện sắc hơn sẽ chỉ vào `ROLE_HINTS` và nói: *"đấy chẳng phải template thì là gì?"*. Câu hỏi hay. Cách trả lời là **xóa nó đi rồi đo lại**.

| Điều kiện | Đúng | Chứng minh được |
|---|---|---|
| A. Đầy đủ gợi ý header | 6/6 | 5/6 |
| B. **Xóa sạch** `ROLE_HINTS` | 6/6 | 5/6 |
| C. Header thay bằng chuỗi vô nghĩa (`QWXZ`, `KJVB`…) | 6/6 | 5/6 |

**Giống hệt nhau.** Trên file có cột số dư, chữ trong header **không đóng góp gì** — số học quyết định. `ROLE_HINTS` chỉ là tiên nghiệm mềm, tối đa 6 điểm trên tổng ~140 khi bất biến kích hoạt (+100). Nó không bao giờ quyết định.

Test `HeaderIndependenceTest` khoá tính chất này lại: nếu sau này ai đó làm cho header trở nên quyết định, test sẽ đỏ.

### Thí nghiệm 3 — Quy ước số dư cũng tự suy được

Các ngân hàng bất đồng về hai quy ước mà vẫn giữ nguyên số học: số dư in **trước** hay **sau** khi áp giao dịch, và thứ tự dòng **cũ trước** hay **mới trước**. Thay vì đoán, hệ thống thử cả bốn cách đọc và giữ cách khớp. Bất biến tự chọn quy ước cho file đó:

| Quy ước | Kết quả |
|---|---|
| Số dư in **trước** giao dịch | **chứng minh**, conf 0.99 |
| Sắp xếp **mới nhất trước** | **chứng minh**, conf 0.99 |

Lại thêm hai biến thể ngân hàng nữa, vẫn không có template nào.

### Chi phí biên — đây mới là câu trả lời thật

Câu hỏi ngầm giả định công sức tăng tuyến tính theo số ngân hàng. Hãy so sánh trực tiếp:

| | Template thủ công (cách cũ) | Thiết kế này |
|---|---|---|
| Ngân hàng mới, **có** cột số dư | lập trình viên viết `mapping_json` → seed → release → deploy | **không ai làm gì cả** |
| Ngân hàng mới, **không** cột số dư | như trên | **người dùng xác nhận 1 lần**, rồi lưu theo fingerprint |
| Ai phải hành động | **lập trình viên** | **người dùng cuối** (hoặc không ai) |
| Có cần đổi code không | **có**, kèm chu kỳ phát hành | **không** |

Điểm mấu chốt không phải "không còn template". Điểm mấu chốt là **template không còn do người viết code tạo ra**. Nó được **sinh ra** từ suy luận và **xác nhận** bởi người dùng, ngay trong lúc chạy, không cần đổi mã nguồn.

Nói cách khác: câu hỏi giả định O(n) công sức lập trình viên. Thực tế là **O(1) lập trình viên**, và O(1) thao tác người dùng chỉ cho phần dư.

### Giới hạn trung thực — nói ra trước khi bị hỏi

Đừng tuyên bố nó giải quyết mọi thứ. Ba trường hợp bất biến **không** áp dụng được:

| Trường hợp | Hành vi | Ghi chú |
|---|---|---|
| Không có cột số dư | gán **đúng** nhưng conf 0.74, gắn cờ hỏi người | xác nhận 1 lần → fingerprint |
| Tiền luôn dương + cột chỉ dấu D/C, không số dư | gán **đúng**, vẫn hỏi người | như trên |
| Dưới ~4 dòng giao dịch | không đủ dữ liệu để chứng minh | giới hạn thật |
| Nhiều loại tiền tệ xen kẽ | gán đúng, chưa chứng minh | **cần làm**: nhóm theo cột tiền tệ rồi áp bất biến từng nhóm |

Cả bốn đều **gán đúng** trong thử nghiệm — chỉ là hệ thống **không tuyên bố chắc chắn**. Đó là hành vi đúng: với dữ liệu tài chính, "đúng nhưng nói mình không chắc" an toàn hơn nhiều "đúng và tự tin quá mức".

### Con số em BẮT BUỘC phải tự đo

Anh không đưa em con số này vì anh không có dữ liệu thật:

> **Bao nhiêu phần trăm sao kê ngân hàng Việt Nam thực sự có cột số dư?**

Đó là biến quyết định toàn bộ auto-resolution rate. Đi thu thập sao kê thật từ càng nhiều ngân hàng càng tốt, ẩn danh, rồi đo. Nếu tỷ lệ cao (anh đoán là cao, vì số dư là thông tin người dùng cần), luận điểm rất mạnh. Nếu thấp, em vẫn có kết quả trung thực để báo cáo — và tầng LLM ở mục 5 trở nên quan trọng hơn.

**Đừng đoán con số này trong luận văn.** Đo, hoặc nói rõ là chưa đo.

---

## 8. Việc còn lại

Prototype mới là L1–L4 ở dạng thư viện. Chưa nối vào luồng import.

| # | Việc | Ghi chú |
|---|---|---|
| 1 | Nối `statement_profiler` vào `imports.preview()` thay cho `_auto_mapping` | giữ `_auto_mapping` làm fallback |
| 2 | Bảng `learned_templates` (fingerprint, mapping_json, confirmed_by, confirmed_at) | + migration |
| 3 | Giao diện xác nhận mapping khi `needs_human_review` | hiện bằng chứng cho người dùng, cho sửa tay |
| 4 | Người dùng sửa tay → lưu thành learned template | đóng vòng học |
| 5 | Đọc `number_convention` trong `_parse_amount` của `imports.py` | hiện tại đang bỏ qua |
| 6 | Xử lý merged cell và mô tả tràn nhiều dòng | chưa làm |
| 7 | Nhiều sheet trong một workbook | chọn sheet có nhiều dòng giao dịch nhất |
| 8 | LLM adapter (chỉ gửi hồ sơ thống kê) + opt-in | **làm cuối cùng**, sau khi đã đo được (1)–(4) |

Thứ tự quan trọng. Làm (8) trước là cách chắc chắn nhất để có một demo đẹp và một luận văn rỗng.

---

## 9. Một lời

Mission anh giao có bẫy trong đó, và anh cố ý. Câu hỏi *"có model AI nào extract Excel bất kể định dạng không?"* dẫn dụ em đi thẳng tới LLM. Nhưng câu trả lời tốt nhất hóa ra là: **phần lớn bài toán này giải được bằng số học, và phần số học ấy còn tự chứng minh được — thứ mà không LLM nào cho em.**

Kỹ năng anh muốn em rèn không phải là dùng AI. Là **nhận ra khi nào không cần dùng nó** — và biết đặt nó vào đúng chỗ hẹp mà nó thực sự có ích, với một hàng rào kiểm chứng phía sau.

Cũng lưu ý: prototype này chạy trong **~15ms/file**, không cần GPU, không cần mạng, không cần dữ liệu huấn luyện, và mỗi quyết định đều giải thích được bằng tiếng Việt cho người dùng đọc. Khi bảo vệ, những tính chất đó dễ bảo vệ hơn nhiều so với một con số accuracy từ hộp đen.

---

**MSc. Huỳnh Vinh Nam**
ICTLab / USTH
