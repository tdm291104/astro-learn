# Đánh giá chiến lược agent FITS — So sánh ReAct · Plan-and-Execute · Reflexion

So sánh ba chiến lược agent trên tác vụ phát hiện bất thường trong file FITS. Dữ liệu: 360 dòng (3 chiến lược × 3 loại tác vụ × 40 file; mô hình Groq Llama 3.3 70B; tối đa 2 vòng reflection). Bảng chỉ giữ những cột thể hiện rõ sự khác biệt — cột T1 (trích xuất metadata) bão hoà ở 1.000 cho cả ba nên đã được lược bỏ.

| Chiến lược      | Phát hiện bất thường (F1, ↑) | Chất lượng câu trả lời (0–1, ↑) | Chi phí mỗi truy vấn (giây, ↓) |
| --------------- | :--------------------------: | :-----------------------------: | :----------------------------: |
| react           |            0.000             |              0.757              |             1.76               |
| plan_execute    |            0.000             |              0.939              |             2.99               |
| **reflexion**   |          **0.287**           |            **0.980**            |             7.21               |

Mũi tên chỉ chiều "tốt hơn" (↑ càng cao càng tốt, ↓ càng thấp càng tốt). In đậm là giá trị tốt nhất theo cột.

## Giải thích các tham số

### 1. Phát hiện bất thường — F1 (Task T3)

Đo độ chính xác khi agent phát hiện các vấn đề chất lượng dữ liệu trong file FITS (tỉ lệ NaN cao, EXPTIME âm/bằng 0, HDU rỗng, NAXIS/BITPIX không khớp, ảnh toàn 0, thiếu WCS, v.v.). So sánh tập anomaly agent liệt kê với ground truth do `SymbolicFITSChecker` tạo ra một cách xác định.

Công thức:

$$
\text{Precision} = \frac{|A_{\text{pred}} \cap A_{\text{gt}}|}{|A_{\text{pred}}|}, \quad
\text{Recall} = \frac{|A_{\text{pred}} \cap A_{\text{gt}}|}{|A_{\text{gt}}|}, \quad
F_1 = \frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}
$$

Trong đó $A_{\text{pred}}$ là tập câu mô tả anomaly do agent đưa ra (được tách từ `raw_answer` theo các từ khoá `nan`, `anomaly`, `missing`, `invalid`, `naxis mismatch`, ...), $A_{\text{gt}}$ là tập câu mô tả anomaly từ ground truth. Hai phần tử khớp khi một chuỗi là chuỗi con của chuỗi kia (substring match sau khi chuẩn hoá viết thường).

Miền giá trị: $[0, 1]$, càng cao càng tốt.

### 2. Chất lượng câu trả lời — AstroExplain

Rubric tất định gồm 4 tiêu chí, mỗi tiêu chí 0 hoặc 0.25, tổng tối đa 1.0. Không cần LLM-judge.

$$
\text{AstroExplain} = 0.25 \cdot (E_1 + E_2 + E_3 + E_4)
$$

| Tiêu chí | Tên gọi | Điều kiện đạt 0.25 |
|---|---|---|
| $E_1$ | Precision | Câu trả lời tham chiếu chỉ số HDU cụ thể hoặc tên header (EXPTIME, NAXIS, BITPIX, TELESCOP, INSTRUME, CTYPE1, CRVAL1) |
| $E_2$ | Uncertainty | Nếu `nan_ratio > 0.1`, câu trả lời dùng ngôn ngữ thận trọng (*may*, *approximately*, *seems*, *likely*, ...); ngược lại tự động đạt |
| $E_3$ | Traceability | Có ít nhất một giá trị số trong câu trả lời khớp với một số xuất hiện trong output của tool (sai số tương đối ≤ 0.005) |
| $E_4$ | Anomaly flag | Nếu file có anomaly thật, câu trả lời phải nhắc đến (`nan`, `anomaly`, `missing`, `saturat`, `invalid`, `data quality`, ...); ngược lại tự động đạt |

Miền giá trị: $\{0, 0.25, 0.5, 0.75, 1.0\}$ ở mức từng dòng; sau khi trung bình hoá thành số thực bất kỳ trong $[0, 1]$. Càng cao càng tốt.

### 3. Chi phí mỗi truy vấn — Latency

Thời gian thực (wall-clock) đo cho mỗi cặp (file, chiến lược, tác vụ), tính bằng giây:

$$
\text{Latency} = t_{\text{end}} - t_{\text{start}}
$$

Bao gồm toàn bộ vòng đời của agent: các lần gọi LLM, thực thi tool, parse JSON, và với Reflexion là toàn bộ vòng critique + refine. Số báo cáo trong bảng là trung bình cộng theo từng chiến lược. Càng thấp càng tốt.

## Đọc bảng

- **Phát hiện bất thường (F1)** là đóng góp chính của đề tài. Chỉ Reflexion + `SymbolicFITSChecker` đạt F1 > 0 (0.287 so với 0.000 của hai chiến lược còn lại). ReAct và Plan-Execute liên tục bỏ sót các anomaly mang tính cấu trúc (theo luật) mà bộ kiểm tra ký hiệu phát hiện được.
- **Chất lượng câu trả lời** cải thiện đơn điệu: 0.757 → 0.939 → 0.980. Khoảng cách giữa Plan-Execute và Reflexion nhỏ (+0.041); ưu thế của Reflexion tập trung ở những file *có* anomaly — chính là nơi `SymbolicFITSChecker` kích hoạt feedback và buộc agent sửa câu trả lời.
- **Chi phí**: Reflexion chậm hơn ReAct khoảng 4× (7.21 s so với 1.76 s) vì mỗi vòng reflection chạy lại một lượt ReAct đầy đủ. Bị giới hạn bởi `MAX_REFLECTIONS=2`.

## Kết luận

Với các luồng cần phát hiện bất thường (kiểm tra file FITS, validate dữ liệu nạp vào), Reflexion là chiến lược duy nhất sinh ra tín hiệu dùng được — chi phí ~4× latency là chấp nhận được. Với tác vụ chỉ cần metadata hoặc thống kê (T1/T2) mà không quan tâm T3, ReAct vẫn là mặc định tốt hơn. Phiên bản production đã được port sang `backend/agents/astronomy/reflexion_data_analyst_agent.py`.
