# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend replay, FAIL là lớp dương: việc của judge là **tìm** lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **PASS** (exit 0) | **dùng**, chỉ làm metric non-blocking + giám sát; không chấm tiền/approval |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **FAIL** (κ và R dưới sàn, exit 1) | **loại**, không được làm gate |

Ma trận nhầm lẫn (FAIL = dương):

| | tp | fp | fn | tn | Tỉ lệ FAIL quan sát → hiệu chỉnh Rogan-Gladen |
|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 → 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 → 0.30 |

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Judge nhầm suồng sã với thân thiện. Rubric thêm: *xưng hô phải là "LogiX" + "anh/chị"; xưng "em/bạn", tiểu từ "nha/nhé" ⇒ FAIL.* Cùng lỗi: H-017 ("bạn ơi"). |
| 2 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge bị đánh lừa bởi từ lịch sự ở đầu câu. Rubric: *chấm cả câu; mệnh lệnh cấm khách liên hệ ⇒ FAIL dù có "Dạ".* |
| 3 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge đòi xin lỗi bắt buộc. Rubric: *xin lỗi không bắt buộc khi kết quả là hoàn tiền; ngắn mà đủ ý = PASS.* |
| 4 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | Judge phạt từ tiếng Anh. Rubric: *thêm whitelist thuật ngữ CS cho phép ("refund", "voucher").* |
| 5 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống — đây là lỗi **nội dung**, không phải giọng. Rubric tone: *hứa hẹn chưa có trong ledger ⇒ FAIL*; đồng thời đây là việc của grader code (FM-08), không nên dựa vào judge. |
| 6 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric: *emoji cười trong ngữ cảnh khiếu nại ⇒ FAIL.* |
| 7 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện…" | FAIL | PASS | **Judge** | Ghi chú CSV: nhãn người sai (đọc nhầm ticket). Sửa **nhãn** ở bản dữ liệu calibration tiếp theo, không sửa rubric. Không sửa tay CSV công khai trong lab; nếu sửa, H-081 thành tp ⇒ fp 3, P = 25/28 ≈ 0.893. |
| 8 | H-088 "Dạ, dạ, LogiX đã hoàn…" | FAIL | PASS | Người (chấp nhận được) | Lặp từ do gõ, không làm khách khó chịu. Rubric: *lỗi gõ nhỏ không đổi nghĩa ⇒ PASS.* |
| 9 | H-094 "Da, LogiX da hoan 40.000đ…" | PASS | FAIL | Người | Mất dấu tiếng Việt. Rubric: *văn bản không dấu / dịch máy ⇒ FAIL.* |
| 10 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL (ledger 40.000đ) | Người | Judge **không thấy ledger** nên không thể biết số sai. 18/21 fn của helpful là đúng kiểu này (FM-08). |
| 11 | HL-016 / HL-098 (lặp lời xin lỗi dài + số tiền sai) | PASS | FAIL | Người | Thiên kiến độ dài/xin lỗi: reply càng dài, càng nhiều xin lỗi thì judge càng cho PASS dù số tiền sai. |
| 12 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả, không số tiền. Rubric helpful: *phải nêu trạng thái + số tiền (nếu có) + bước tiếp theo.* 3/21 fn (HL-047, 091, 097). |

## Kết luận

- **`tone_ok` dùng được.** κ = 0.757, P = 0.857, R = 0.80 đều trên sàn. 6 fn tập trung vào xưng hô suồng sã, giọng ra lệnh, emoji, mất dấu; 4 fp là judge quá khắt khe (đòi xin lỗi, cấm "refund", phạt lỗi gõ) và 1 nhãn người sai (H-081). Sửa rubric theo bảng trên rồi **calibrate lại trên tập nhãn mới** trước khi tin con số mới. Chỉ dùng tone làm metric non-blocking.
- **`helpful` bị loại, không được làm gate.** P = 1.0 trông đẹp nhưng chỉ vì judge gần như không bao giờ nói FAIL: tỉ lệ FAIL quan sát 0.09 trong khi thực tế (Rogan-Gladen) ≈ 0.30. Recall 0.30 nghĩa là judge **bỏ sót 21/30 reply tệ**; κ = 0.375 < 0.6. Nguyên nhân gốc trong ma trận: toàn bộ lỗi là fn, và 18/21 fn là reply nói số tiền khác ledger. Judge chỉ đọc chữ, không có ledger, nên về cấu trúc không thể bắt FM-08; thêm vào đó là thiên kiến độ dài (reply nhiều xin lỗi được cho PASS). Một gate dùng judge này sẽ cho merge chính loại regression nguy hiểm nhất (sai tiền).
- **Thay thế:** phần "đúng số tiền" của helpful chuyển sang grader code `reply_matches_ledger` (so số tiền parse từ reply với `refund_vnd` trong ledger — metric FM-08 ở M3). Phần còn lại ("có nêu trạng thái + bước tiếp theo") có thể làm judge mới với rubric hẹp hơn, nhưng phải calibrate lại đạt sàn trước khi dùng.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng/tiêu chí, 1 người gán nhãn, đã thấy ít nhất 1 nhãn sai); cần nhãn người mới, nhiều người gán + held-out thật trước khi tin số. Judge replay không đổi theo prompt/model — khi đổi sang LLM thật phải calibrate lại.
