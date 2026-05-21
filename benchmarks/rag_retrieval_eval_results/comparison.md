# Đánh giá pipeline truy hồi RAG — So sánh các bước cải thiện

So sánh ba pipeline truy hồi trên `arxiv_curated_v1` — 30 câu hỏi đã được biên soạn thủ công với ngữ cảnh xác định, trải qua 6 bài báo arXiv thuộc lĩnh vực thiên văn học. Cấu hình: `top_k = 10`; embedding + reranker Jina qua LiteLLM proxy.

| Bước | Pipeline                                  | Độ chính xác Top-1 (↑) | Độ chính xác Top-5 (↑) | Độ chính xác Top-10 (↑) | Độ bao phủ Top-5 (↑) | Chất lượng xếp hạng — MRR (↑) | Cải thiện so với baseline (MRR) |
|:----:|-------------------------------------------|:----------------------:|:----------------------:|:-----------------------:|:--------------------:|:-----------------------------:|:-------------------------------:|
|  0   | baseline (char-window 1000/200)           |         0.167          |         0.500          |          0.633          |        0.483         |             0.324             |               —                 |
|  1   | recursive đã tinh chỉnh (chunk 500/250)   |         0.367          |         0.567          |          0.800          |        0.550         |             0.450             |          **+0.126**             |
|  2   | **+ cross-encoder reranker (jina-v2)**    |       **0.600**        |       **0.800**        |        **0.900**        |      **0.783**       |           **0.687**           |          **+0.363**             |
|      | *Tổng cải thiện*                          |          ×3.6          |         +30pp          |          +27pp          |        +30pp         |             ×2.1              |                                 |

Mũi tên chỉ chiều "tốt hơn" (↑ càng cao càng tốt). In đậm là giá trị tốt nhất theo cột.

## Giải thích các tham số

Giả sử có $N$ câu hỏi đánh giá. Với mỗi câu hỏi thứ $i$:

- $R_i$ là tập **golden chunk** (chunk mục tiêu) được gán nhãn thủ công, $|R_i|$ là số chunk này.
- Pipeline trả về danh sách top-$k$ kết quả. Gọi $H_i^{(k)}$ là tập các thứ hạng (1, 2, …, $k$) của những chunk khớp một trong $R_i$ (khớp theo `doc_id` + `page ± 1` + chuỗi con `contains` sau chuẩn hoá khoảng trắng).
- $r_i^{*}$ là thứ hạng (1-indexed) của chunk đúng đầu tiên xuất hiện trong kết quả; $r_i^{*} = \infty$ nếu không tìm thấy.

### 1. Độ chính xác Top-k — hit_rate@k

Tỉ lệ câu hỏi có **ít nhất một** chunk đúng nằm trong top-$k$:

$$
\text{hit\_rate}@k = \frac{1}{N} \sum_{i=1}^{N} \mathbb{1}\!\left[\,\exists\, r \in H_i^{(k)} : r \le k\,\right]
$$

Trong đó $\mathbb{1}[\cdot]$ là hàm chỉ thị (trả về 1 nếu điều kiện đúng, ngược lại 0).

Trả lời câu hỏi: *"Trong top-$k$ kết quả, có chunk đúng nào không?"* — đây là metric gần nhất với trải nghiệm người dùng (nếu UI hiển thị $k$ citation thì người dùng có thấy nguồn đúng không).

Miền giá trị: $[0, 1]$, càng cao càng tốt.

### 2. Độ bao phủ Top-5 — recall@5

Trung bình phần trăm chunk relevant tìm được trong top-5:

$$
\text{recall}@5 = \frac{1}{N} \sum_{i=1}^{N} \frac{\min\!\big(|H_i^{(5)}|,\, |R_i|\big)}{|R_i|}
$$

Trả lời câu hỏi: *"Trong top-5, ta tìm được bao nhiêu phần trăm tổng số chunk đúng của câu hỏi đó?"* — quan trọng khi một câu hỏi có nhiều đoạn văn cùng hỗ trợ trả lời.

Hàm `min` ở tử số tránh giá trị > 1 khi có chunk lặp; nó cũng là lý do recall không phạt bộ truy hồi nếu top-5 chứa nhiều hơn 1 lần một golden chunk.

Miền giá trị: $[0, 1]$, càng cao càng tốt.

### 3. Chất lượng xếp hạng — MRR (Mean Reciprocal Rank)

Trung bình nghịch đảo của thứ hạng chunk đúng đầu tiên:

$$
\text{MRR} = \frac{1}{N} \sum_{i=1}^{N} \frac{1}{r_i^{*}}
$$

với quy ước $\dfrac{1}{\infty} = 0$ (không tìm thấy thì đóng góp 0).

Trả lời câu hỏi: *"Trung bình, kết quả đúng đầu tiên xuất hiện ở vị trí thứ mấy?"* — số duy nhất tổng hợp toàn bộ chất lượng xếp hạng. Một câu hỏi tìm thấy chunk đúng ở rank 1 đóng góp 1.0; ở rank 2 đóng góp 0.5; ở rank 10 đóng góp 0.1.

Miền giá trị: $[0, 1]$, càng cao càng tốt.

### 4. Cải thiện so với baseline (MRR)

Hiệu MRR tuyệt đối so với pipeline ở Bước 0:

$$
\Delta \text{MRR} = \text{MRR}_{\text{pipeline}} - \text{MRR}_{\text{baseline}}
$$

Đơn vị tính theo điểm phần trăm trong văn bản (ví dụ +12.6pp = +0.126).

## Đọc bảng

- **Bước 1** (đổi chunker, chưa rerank): chunk nhỏ hơn (500/250) đánh bại cấu hình mặc định cũ (1000/200) +12.6pp MRR. Tham số được chọn qua khảo sát lưới `size ∈ {500, 750, 1000, 1500}` × `overlap ∈ {100, 200, 250}`.
- **Bước 2** (thêm cross-encoder reranker): +23.7pp MRR trên đỉnh Bước 1 — đòn bẩy lớn nhất. Vector search trả về `top_k × 4 = 40` ứng viên; `jina-reranker-v2` sắp xếp lại còn top-$k$. Thêm khoảng 150–300 ms độ trễ cho mỗi truy vấn.
- **Các biến thể bị loại** (đã thử, không vượt được Bước 2 trên corpus này): MultiQueryRewriter, HyDE, contextual chunking với prefix tên file. Mỗi cái đều làm loãng xếp hạng gốc đang đủ mạnh; chi tiết trong các cell mã nguồn của notebook.

## Kết luận

Pipeline `recursive` chunker (500/250) kết hợp cross-encoder reranker là cấu hình truy hồi cho production. Đã được port sang:

- `backend/workers/notebook_worker.py` — `_CHUNK_SIZE=500`, `_CHUNK_OVERLAP=250`
- `backend/agents/notebook/qa_agent.py` — lấy `top_k × 4` ứng viên → rerank → top-$k$
- `backend/core/llm/llm_client.py` — thêm `rerank()` (HTTP đến LiteLLM `/v1/rerank`)
- `backend/core/config.py` — `RERANKER_MODEL='astrolearn-reranker'`, `RERANK_CANDIDATE_MULTIPLIER=4`
