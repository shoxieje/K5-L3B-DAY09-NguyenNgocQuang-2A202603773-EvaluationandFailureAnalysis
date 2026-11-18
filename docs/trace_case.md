# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.

## Case đã điền: `seeded_regression C-002@11` (FM-03)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-325d` (eval set `325ddcd80bad`) |
| Triệu chứng | Lab 8 `trial_pass` FAIL: `status resolved != denied`. `db_fact_kept` = False (1 override event). Ledger `refund_vnd=20000`, `refund_count=1` trong khi nhãn là 0 / 0. Reply #6: "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." — trôi chảy, khớp ledger, nhưng **ledger sai**. |
| Bước sai đầu tiên | **#3 `model_override` `{"delay_days": 5}`** |
| Vì sao là bước *đầu tiên* | #1 `handoff` đúng contract (`check_applicable_policy`, chỉ tool read-only). #2 `investigator` đọc đúng DB: O-202 `delay_days=2`, `status=delivered`. Ở #3 agent lấy "trễ 5 ngày" từ ticket đè lên DB. #4 `quote` 20.000đ `SHIP-LATE-03` là tính đúng **trên dữ liệu đã bị đè**; #5 `refund_history` và refund chỉ là hệ quả. |
| Failure mode | FM-03 `ticket_trust` |
| Đối chứng | `fixed C-002@11`: không có event `model_override`; #3 `quote` = 0đ `no_entitlement`; #4 reply "chưa đủ điều kiện hoàn"; ledger 0, status `denied`, Lab 8 PASS. Shape `swarm` gốc của Lab 8 cũng có lỗi này nhưng chỉ ở seed 55 (`seed % 5 == 0`) → lỗi chập chờn có sẵn trong baseline. |
| Regression test | `tests/test_lab9_trace_case.py::test_lab9_c002_ticket_must_not_override_db_delay` — chạy shape thật, chấm bằng `DbFactKept`; **FAIL trên `seeded_regression`, PASS trên `fixed`** (đã chạy, cả 2 tham số xanh). Ở mức eval: metric `db_fact_kept` (0.9286 trên `seeded_regression` vs 1.0 trên `fixed`) và `pass_rate`. Test thứ hai cùng file (`test_lab9_c014_reply_amount_equals_ledger`) khóa FM-05/FM-08 trên C-014@11. |
| Chưa chắc chắn | Trace chỉ cho thấy agent dùng số ngày của ticket, không cho thấy *vì sao* (MockLLM là luật cứng; với LLM thật có thể là prompt ưu tiên lời khách). `DbFactKept` chỉ bắt được khi agent **ghi** event `model_override`; biến thể `quiet_override` (tin ticket mà không để lại event) chỉ bị bắt qua kết quả (`refund_amount_correct`, `pass_rate`), không qua step grader. Không chứng minh được FM-03 trên các trường DB khác ngoài `delay_days` (vd. `damage_verified`) vì variant chỉ override trường này. |
