# Day 25 — GPU FinOps cho NimbusAI

**Nguyễn Khắc Giáp — 2A202602950** · Số liệu lấy từ `outputs/report.md` và các file `outputs/ext*.md` (dữ liệu sinh bằng seed cố định, tháng = 30 ngày).

## 1. Baseline vs. Optimized

| | Baseline | Optimized |
|---|---:|---:|
| Chi phí hàng tháng | **$27,133** | **$14,626** |
| Inference `$/1M-token` (M2) | $6.488 | $1.126 |
| Tiết kiệm | | **$12,507 (46%)** |

Baseline gồm chi phí inference $1,466/tháng (mọi request chạy model lớn, không cache, không batch) và chi phí GPU on-demand $25,667/tháng. Riêng inference giảm 82.6%, từ $6.488 xuống $1.126 mỗi 1M token.

## 2. Phân tích từng đòn bẩy

| Đòn bẩy | Tiết kiệm/tháng | Tỷ trọng |
|---|---:|---:|
| Purchasing (spot/reserved) | $10,040 | 80% |
| Inference (cascade/cache/batch) | $1,212 | 10% |
| Right-size GPU bị "lie" | $655 | 5% |
| Tắt GPU idle | $600 | 5% |

**Purchasing đóng góp nhiều nhất** vì chi phí GPU ($25.7k) lớn gấp ~17 lần chi phí inference ($1.5k), nên một phần trăm chiết khấu trên GPU đáng giá hơn nhiều so với cùng phần trăm trên token. Inference có tỷ lệ giảm cao nhất (82.6%) nhưng trên một nền nhỏ. Điều này cho thấy `$/GPU-giờ` và `$/1M-token` trả lời hai câu hỏi khác nhau: phải tối ưu cả cách mua GPU lẫn cách dùng chúng.

Lưu ý: con số $10,040 của M3 hơi lạc quan, vì M3 luôn tính giá reserved 3 năm và tỷ lệ spot bị thu hồi 5% cho mọi loại GPU. Phần mở rộng 1 bên dưới tính lại điều này.

## 3. GPU-Util Lie

Hai GPU báo bận ≥90% nhưng MFU < 30%:

| GPU | util | MFU | Ý nghĩa |
|---|---:|---:|---|
| `gpu-h100-4` | 98.2% | 0.194 | báo bận gần như tuyệt đối, nhưng chỉ khai thác ~19% sức tính toán |
| `gpu-a10g-1` | 96.9% | 0.268 | tương tự, ~27% |

`util%` chỉ cho biết GPU có kernel chạy, không cho biết kernel đó tận dụng bao nhiêu FLOPs. Hai GPU này khiến dashboard thông thường trông "khỏe" trong khi phần lớn tiền thuê không tạo ra tính toán hữu ích.

**Tác động tài chính theo lab:** hạ H100 → A100 và A10G → L4 tiết kiệm **$655/tháng** ($511 + $144). Đây là ước lượng theo bảng `RIGHTSIZE_MAP` của lab, chưa có benchmark chứng minh throughput giữ nguyên. Ngoài ra `gpu-h100-5` có 8 giờ idle/ngày, tương đương **$20/ngày = $600/tháng** nếu tắt. Trong bảng M1, các GPU `gpu-a10g-0`, `gpu-a100-0/1` có util chỉ 25–31% (dưới 40%) cũng đáng xem xét gộp workload, nhưng không bị tính là "lie".

## 4. Phần mở rộng đã làm

Tôi làm 4 phần (code ở `missions/ext*.py`, bảng ở `outputs/ext*.md`, test ở `tests_extensions/`). `pytest -q` mặc định vẫn là 15 passed, `verify.py` vẫn 11/11.

**Ext 1 — `recommend_tier()` theo chi phí.** Thêm tỷ lệ spot bị thu hồi theo loại GPU (H100 3%, A100 5%, A10G/L4 8%; đây là *giả định*, không có trong dữ liệu) và chọn reserved 1 năm hay 3 năm theo vòng đời workload (giả định dịch vụ inference sống ~24 tháng). Tính lại với chi phí lock-in và tỷ lệ thu hồi theo GPU:

| Cách tính | Chi phí/tháng | Tiết kiệm |
|---|---:|---:|
| Policy cũ, như M3 báo | $15,627 | 39.1% |
| Policy cũ, tính lại đúng | $18,413 | 28.3% |
| **Policy mới** | **$17,603** | **31.4%** |

Insight chính: con số 39.1% của M3 bị thổi phồng khoảng 11 điểm phần trăm vì bỏ qua lock-in của gói 3 năm. Policy mới chuyển 3 job inference sang `reserved_1yr` và rẻ hơn $810/tháng so với policy cũ khi cùng tính đúng.

**Ext 3 — `cache_is_worth_it()`.** M2 chỉ tính giá đọc cache (10%) mà bỏ qua phí ghi. Với phí ghi 1.25× giá input (giả định, kiểu Anthropic 5 phút), cache chỉ có lãi khi mỗi prefix được đọc lại **> 0.278 lần**. `$/1M-token` của M2 là $1.126 (không phí ghi) và thành $1.170 với 1 lần đọc lại, $1.141 với 3 lần, $1.282 nếu ít hơn ngưỡng nên tắt cache. CSV không có số lần đọc lại mỗi prefix nên đây là dải giả định, không phải số đo.

**Ext 4 — Ngân sách reasoning.** Reasoning chiếm **8.4% request** nhưng **16.5% chi phí** và **94% năng lượng** (148 Wh/request so với 0.86 Wh). 90% năng lượng reasoning nằm ở project `nightly-eval`. Vì traffic đã dưới 10%, cap 10% tiết kiệm $0; cap 5% tiết kiệm ~$12/tháng và ~11.9 kWh/ngày, cap 2% ~$23/tháng và ~22.5 kWh/ngày.

**Ext 5 — Carbon-aware scheduling.** Chuyển 5 job interruptible từ `us-east-1` sang `europe-north1` giảm 626 kgCO₂e (92%, 679.8 → 53.7 kg) và giảm tiền điện $215 → $161. `us-east-wa` rẻ nhất ($98 điện) và cân bằng nhất, giảm 76% carbon. Tính theo công suất GPU, không có PUE; giá thuê GPU coi như giống nhau giữa các vùng.

## 5. Khuyến nghị cho NimbusAI (3 việc đầu tiên)

1. **Chuyển training/eval sang spot có checkpoint và cam kết reserved 1 năm cho inference ổn định.** Đây là 80% mức tiết kiệm. Báo cáo chi phí cần tính cả lock-in, nếu không số tiết kiệm bị thổi phồng (Ext 1).
2. **Kiểm tra `gpu-h100-4` và `gpu-a10g-1`, tắt `gpu-h100-5`.** Đo MFU/MBU trước khi hạ GPU để chắc throughput giữ nguyên, tiết kiệm tới $655/tháng; tắt GPU idle thêm $600/tháng. Chuyển cảnh báo từ `util%` sang MFU.
3. **Đưa governance vào vận hành:** bật chargeback (tag coverage hiện 92%, vượt gate 80%) để các team thấy chi phí của mình (`assistant` $2.59/ngày, `search` $2.49, `eval` $1.79, `rag` $1.60 ở phần inference), chỉ cho phép reasoning ở `nightly-eval`, và đặt job interruptible ở `us-east-wa`/`europe-north1`.

> Các con số lấy từ snapshot tháng 6/2026 của lab, cần re-baseline trước khi áp dụng thật.
