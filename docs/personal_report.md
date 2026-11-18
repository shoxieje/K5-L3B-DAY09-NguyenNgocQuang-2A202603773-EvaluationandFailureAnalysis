# Báo cáo cá nhân — Lab 9: Evaluation & Failure Analysis

- Họ tên: Nguyễn Ngọc Quang · MSSV: 2A202603773 · GitHub: shoxieje
- Repo: `K5-L3B-DAY09-NguyenNgocQuang-2A202603773-EvaluationandFailureAnalysis` · nhánh nộp `main` (code tại `0fbe19e`)
- Phạm vi: Core M0–M4 (PR #1) và Advanced/Expert M5–M7 (PR #2); job `eval-gate` xanh trên cả hai trước khi merge.

## 1. Kết quả theo mốc

| Mốc | Kết quả | Bằng chứng |
|---|---|---|
| M0 | Chép `src/` từ repo gốc Day 8 (không lấy bản đã sửa của nhóm), eval set v1 14 item | `lab9.smoke` → M0 PASS |
| M1 | Taxonomy FM-01…FM-09, mỗi FM có trace + bước sai đầu tiên; gắn `failure_modes` cho 14 item | `evalset --check` → 0 problem |
| M2 | Cài confusion, P/R, κ, Rogan-Gladen. `tone_ok` κ 0.757 / P 0.857 / R 0.80 → dùng; `helpful` κ 0.375 / R 0.30 → loại | `docs/judge_audit.md` (12 case audit) |
| M3 | `ApprovalBypass`, `RefundAmountCorrect`, thêm `reply_matches_ledger` (FM-08) và `proposal_correct` (FM-04/05) | `mutation --detect`: detection 100%, false alarm 0% |
| M4 | Paired bootstrap; gate cho qua `fixed` (exit 0), chặn `seeded_regression` (exit 1) | `pass_rate` Δ −0.271, CI [−0.500, −0.057] — khớp tham chiếu |
| M5 | `fm_map.yaml`, eval set v2 28 item (mỗi FM bị tấn công ≥ 3 item), slice gate `money_movement` / `adversarial` / `denial` | `slice_regression`: trung bình vẫn trên sàn, chỉ slice `money_movement` (0.85 < 0.95) chặn |
| M6 | `pass_at_k`, `pass_hat_k`; `pass_hat_5` blocking, sàn 0.80 | A/A (66,77,88,99,110): Δ = 0 mọi metric; `flaky_regression` pass^5 = 0.571 → chặn |
| M7 | `integrity_check` + ratchet | scorecard 3/3, 0 báo nhầm; 4/4 trap công khai bị chặn |

## 2. Quyết định chính

- **Tìm bằng chứng bằng probe một lỗi/lần:** bật từng công tắc lỗi trên nền `fixed`, chạy 14 claim × 5 seed để biết FM nào làm fail claim nào, thay vì đoán. Nhờ vậy thấy `swarm` gốc đã có FM-03 ở seed 55 (C-002) và Lab 8 **không** bắt FM-08 (reply nói 35.000đ, ledger 20.000đ ở C-008).
- **Loại judge `helpful`:** 18/21 ca judge bỏ sót là reply nói sai số tiền — judge không thấy ledger nên về cấu trúc không thể bắt. Phần "đúng tiền" chuyển sang grader code `reply_matches_ledger`; tiền và approval luôn chấm bằng code.
- **Chọn ngưỡng ngoài dải nhiễu:** MockLLM tất định nên A/A = 0; sàn `pass_hat_5` 0.80 thấp hơn baseline (0.893) ~2.6 item để chừa chỗ cho nhiễu khi dùng LLM thật.
- **Integrity không chỉ so số:** kiểm số dòng, dòng trùng, tập (item, seed), giá trị thiếu, tính lại aggregate từ dòng, slice tag, và ratchet (kể cả bootstrap `rng`/`n_resamples`, đổi tên `eval_set_version` để né ratchet). Đã tự dựng ~14 trap ẩn giả định, tất cả bị chặn.
- **Không sửa `src/lab8/`, variants, traps hay report bằng tay;** mọi report sinh bằng script và commit bằng `git add -f`.

## 3. Review và sửa sau review

Mỗi PR có một lượt review độc lập trước khi merge:

- PR #1: `--detect` chính thức chỉ 75% (C-013 `proposal_mismatch` không grader nào giải thích) → thêm `proposal_correct`, lên 100%. Sửa `rogan_gladen` crash khi judge không hơn ngẫu nhiên, `pass_at_k` nhận số nguyên numpy, parser số tiền hiểu "35k", "35 nghìn", "1 triệu"; sửa vài chỗ docs lệch dữ liệu.
- PR #2: ratchet chặn nhầm khi nâng version thật v1 → v2 → xác định eval set theo file thay vì sha report; khoá tham số bootstrap; giá trị không phải số bị chặn thay vì làm gate crash.

## 4. Giới hạn và bài học

- Lỗi chỉ xuất hiện 1/5 seed (`rare`) trên vài item **không phát hiện ổn định** với 5 seed (vd. `rare` + `sum_parts`/`ticket_trust` vẫn merge). Đây là giới hạn cỡ mẫu, đã ghi trong eval card; không hạ ngưỡng để "bắt" nó.
- Gate chỉ đọc report: report bị làm giả nhất quán từ dòng không thể phát hiện — phải dựa vào CI tự chạy eval.
- Bài học: một metric trung bình trên 28 item che được lỗi ở 3 item; cần slice. Một judge có P = 1.0 vẫn có thể vô dụng nếu R = 0.30. Và con số phải lấy từ công cụ chính thức — con số 87% tự đo ban đầu sai mẫu số so với `--detect` (75%).
