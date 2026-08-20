# Reflection — Day 20 Lab (Personal Report)

> **Đây là báo cáo cá nhân.** Số liệu của bạn **không** so sánh được với bạn cùng lớp
> — chỉ so **before vs after trên chính máy bạn**. Rubric chấm độ rõ ràng của setup,
> đo lường và **lập luận**, không chấm tốc độ tuyệt đối.
>
> `make verify` sẽ fail nếu còn placeholder chưa điền. Đó là cố ý.

**Họ Tên:** Nguyễn Hùng Mạnh
**Cohort:** AICB-P2T2 (MSSV 2A202601256)
**Ngày submit:** 2026-08-20

---

## 1. Hardware & runtime  *(rubric 1, 2 — 10 điểm)*

> Từ `make probe`. Paste output hoặc điền tay.

- **OS:** Windows 11
- **CPU:** 12th Gen Intel Core i5-12450H
- **Cores:** 8 physical / 12 logical
- **CPU extensions:** not captured by `make probe` on this build (i5-12450H supports AVX2)
- **RAM:** 63.7 GB
- **Accelerator:** NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM, CUDA) — Vulkan also present
- **llama.cpp asset đã tải:** llama-b10488-bin-win-cuda-12.4-x64.zip (+ cudart-llama-bin-win-cuda-12.4-x64.zip)
- **Model đã dùng:** Gemma 4 E2B (`LAB_MODEL=gemma4-e2b`)
- **Quantization:** UD-Q4_K_XL (primary) + UD-Q2_K_XL (compare)

**Chạy ở đâu:** laptop của tôi

**Setup story** (≤ 80 chữ): Hai việc phải sửa: (1) `lib/labkit.py` ghi
`benchmarks/*.md` không chỉ định `encoding="utf-8"`, trên Windows locale mặc định nó
ghi cp1252 → hỏng ký tự `·`, khiến grader (đọc UTF-8) sẽ crash `make verify`; đã vá tại
nguồn. (2) Port 8080 mặc định trùng với một service Docker sẵn có trên máy (LLM
gateway) — mọi request qua `localhost` bị route nhầm sang service đó qua IPv6. Chuyển
hẳn sang `LAB_SERVER_PORT=8090` cho toàn bộ track 02/03.

---

## 2. Đo lường  *(rubric 3, 4, 5 — 20 điểm)*

> Paste bảng từ `benchmarks/01-quickstart-results.md` (`make bench` tự sinh).

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|---|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 4065 | 234 / 369 | 13.3 / 13.7 | 1060 / 1203 / 1203 | 75.3 |
| UD-Q2_K_XL | 2.24 | 4362 | 234 / 378 | 12.7 / 13.0 | 1037 / 1175 / 1175 | 78.8 |

**Quan sát** (≤ 60 chữ): Q2_K_XL decode nhanh hơn 1.05x, nhẹ hơn 0.73GB, nhưng **không
đáng dùng**: hỏi cùng câu "Explain what a KV cache is" trên cả hai, Q4 trả lời đúng
(cache key/value vectors lúc inference), còn Q2 trả lời **sai kỹ thuật** (nói là cache
"weights" dùng lúc "training"). Tốc độ nhanh hơn không bù được câu trả lời sai.
(Bảng này lấy từ lần chạy lại `make bench` sau khi máy đã "ấm" — số liệu ban đầu chậm
hơn do cold cache; kết luận chất lượng không đổi.)

---

## 3. Serving under load  *(rubric 8, 9, 10 — 20 điểm)*

> Từ `benchmarks/02-server-results.md` (`make load-report`).

| Users | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|--:|--:|--:|--:|--:|--:|--:|
| 10 | 2.29 | 3300 | 5800 | 6900 | 7.9 | 0.0% |
| 50 | 2.60 | 17000 | 19000 | 20000 | 39.7 | 0.0% |

- **Offered load tăng 5×, throughput thực tăng:** 1.14×  (gần như không đổi so với 5× tải)
- **P95 tăng:** 3.28×
- **Effective concurrency ở 50 users:** 39.7 so với `--parallel` = 4 slots

**Peak `llamacpp:n_busy_slots_per_decode`** (từ `make metrics` khi `make load-50` đang
chạy): 3.97 / 4 slots

**Saturation reading** (≤ 80 chữ): Server bão hoà ở hoặc dưới 50 users. Ba con số
đồng thuận: RPS gần như không đổi (2.29→2.60 cho 5× tải), `n_busy_slots_per_decode`
ghim ở 3.97/4 gần suốt 60s, và `requests_deferred` ~44 liên tục. P95 tăng 3.28× trong
khi throughput không đổi → phần latency thêm là **queue time**, không phải compute
time. Muốn tăng goodput@SLO, tôi sẽ đổi `--parallel` 4→8 **trước tiên** (không phải
quantization hay threads), vì bottleneck là số slot chứ không phải tốc độ decode mỗi
request (GPU đã nhanh) — còn VRAM (~3GB model / 6GB card) vẫn còn dư để thử.
(Bảng này lấy từ lần `load-10`/`load-50` chạy lại để chụp ảnh cuối cùng; con số đổi
theo từng lần chạy nhưng câu chuyện bão hoà giữ nguyên — xem ghi chú trong
`benchmarks/02-server-batching-u50.md`.)

---

## 4. Integration  *(rubric 12, 13 — 15 điểm)*

> Từ `make pipeline`. Nói thật cái nào real, cái nào stub — stub **không** mất điểm.

| Day | Piece | Real hay stub? |
|---|---|---|
| N16 Cloud/IaC | localhost only | stub |
| N17 Data pipeline | `TOY_DOCS` in-memory list | stub |
| N18 Lakehouse | (cùng in-memory list, không SQLite/Delta/Iceberg) | stub |
| N19 Vector + features | keyword-overlap fallback, không embedding server | stub |
| N20 Serving | `llama-server` | real |

**Latency split** (mean của 3 query, từ output của `pipeline.py`):

- embed: 0.0 ms
- retrieve: 0.03 ms
- llm: 3718.5 ms
- **stage chiếm nhiều nhất:** llm (100% của total)

**Reflection** (≤ 60 chữ): Đúng như kỳ vọng — embed/retrieve đang stub nên gần như 0ms,
llm luôn sẽ chiếm gần hết. Nếu phải giảm 2× latency, tôi sẽ tấn công **prefill của llm**
trước: giữ system prompt giống hệt byte-for-byte giữa các lần gọi để server tái dùng
KV-cache prefix (prompt caching), giảm chi phí prefill lặp lại — rẻ hơn nhiều so với
đổi quantization hay phần cứng.

---

## 5. The single change that mattered most  *(rubric 11 — 10 điểm)*

> **Phần quan trọng nhất của report.** Không cần bonus track: `make tune` đã cho bạn
> một before/after thật (`benchmarks/01-tuning-tg128.md`). Đổi quantization,
> `LAB_N_CTX`, hay `--parallel` rồi đo lại cũng được.

**Change:** Bật GPU offload — `-ngl 0` (CPU-only) → `-ngl 99` (toàn bộ layer lên RTX
4050), đo bằng `llama-bench -m gemma-4-E2B-it-UD-Q4_K_XL.gguf -t 8 -p 0 -n 128`

```
before:  10.89 tok/s   (-ngl 0, CPU-only, 8 threads)
after:   68.80 tok/s   (-ngl 99, GPU offload)
speedup: 6.32×
```

**Tại sao nó work**:

Decode bị chặn bởi **memory bandwidth**, không phải FLOPs: mỗi token sinh ra phải đọc
lại gần như toàn bộ ~2.97GB trọng số đã quantize từ bộ nhớ vào compute unit. Trên CPU,
băng thông đó bị giới hạn bởi kênh DDR5 hệ thống (dual-channel, chia sẻ giữa 8 core
tranh nhau cùng kênh nhớ) — đó là lý do `-t 1` và `-t 8` gần như ngang nhau khi CPU
đang thực sự làm việc (spread chỉ ~1.07x trong `01-tuning-tg128.md`, không phải vì
threads vô dụng, mà vì bản thân CPU decode luôn nghẽn cùng một băng thông đó bất kể
bao nhiêu thread cùng tranh nó). Chuyển sang GPU thay đổi hẳn chế độ băng thông: VRAM
GDDR6 trên RTX 4050 nhanh hơn nhiều so với DDR5 hệ thống, và hàng nghìn CUDA core đọc
song song thay vì 8 CPU core tuần tự tranh kênh nhớ. Đó là lý do 6.32× không phải một
con số ngẫu nhiên — nó phản ánh đúng tỉ lệ chênh lệch băng thông bộ nhớ giữa hai loại
thiết bị cho đúng một workload memory-bandwidth-bound.

Điều này cũng giải thích luôn kết quả "khác kỳ vọng" của `make tune`: đường cong thread
sweep phẳng gần như tuyệt đối (94%→100% suốt từ `-t 1` đến `-t 24`) *vì lab chạy mặc
định với `ngl=99`* — một khi GPU đã gánh hết phép nhân ma trận, CPU thread chỉ còn làm
việc vặt (sampling, KV-cache bookkeeping) giữa các lệnh gọi GPU, nên thêm thread gần
như không giúp gì. Nói cách khác: trên máy có GPU, "thay đổi quan trọng nhất" không
phải thread count — nó là chính quyết định offload lên GPU hay không.

---

## 6. Bonus  *(optional — tối đa 20 điểm)*

**Đã làm:** B2 (cả 4 sweep: `sweep-gpu`, `sweep-quant`, `sweep-ctx`, `sweep-batch`) ·
B4 + B5 cùng lúc qua **challenge C6** (Vulkan vs CUDA trên cùng RTX 4050 — không cần
compile, dùng 2 bản prebuilt Windows) · B1 (build từ source, xem cập nhật bên dưới).

### B3 — before/after chính (từ `make sweep-gpu`, khác với `make tune` ở §5)

```
before:  11.9 tok/s   (-ngl 0, CPU-only)
after:   70.9 tok/s   (-ngl 99, full GPU offload)
speedup: 5.97×
```

Khác với §5 (chỉ đo 2 điểm đầu/cuối), sweep này đo cả dải trung gian
(0, 8, 16, 24, 32, 99) và cho thấy đường cong **không tuyến tính**: nửa sau
(24→32→99) tăng nhanh hơn nửa đầu (0→8→16). Cơ chế: ở mức offload thấp, phần lớn
layer vẫn chạy trên CPU (chậm) *cộng thêm* chi phí đồng bộ host↔device mỗi layer khi
băng qua ranh giới CPU/GPU — nên throughput tổng vẫn bị kẹp bởi CPU. Chỉ khi đủ layer
chuyển sang GPU thì CPU mới hết là bottleneck, và phần tăng tốc dồn hết vào nửa sau.
Full offload thắng vì đây là điểm duy nhất tránh được cả hai chi phí (CPU chậm +
đồng bộ chéo) cùng lúc. Chi tiết: `benchmarks/bonus-gpu-offload-sweep.md`.

### Finding phụ đáng chú ý — C6: Vulkan vs CUDA trên cùng 1 GPU

```
before (Vulkan, RTX 4050 qua -dev Vulkan1): 28.3 tok/s
after  (CUDA, cùng RTX 4050):               66.9 tok/s
speedup: 2.36×
```

**Điều này nói lên gì mà deck chưa nói:** Deck nói vLLM/SGLang dùng kernel riêng
theo nhà cung cấp (FA3/FA4/FlashMLA/TRTLLM-MHA) thay vì một đường chung — số đo này
là bằng chứng cụ thể ở quy mô laptop cho đúng lập luận đó: **cùng một GPU vật lý**,
chỉ đổi API (CUDA riêng của NVIDIA so với Vulkan dùng chung mọi vendor) đã tạo ra
2.36× chênh lệch. Vulkan thấy được RTX 4050 có `matrix cores: KHR_coopmat` (tương
đương tensor core) nhưng vẫn phải gọi qua một extension portable thay vì instruction
set gốc của NVIDIA mà CUDA gọi trực tiếp — API càng portable, càng bỏ lại nhiều hiệu
năng phần cứng thật trên bàn. Cũng phát hiện một bug thực tế khi đo: `llama-bench`
mặc định `-mg 0` chọn nhầm Intel iGPU (thiết bị Vulkan 0) thay vì RTX 4050 (Vulkan1)
— nếu không kiểm tra kỹ, kết quả "Vulkan chậm hơn CUDA 3×" đã bị báo cáo sai vì đang
so sánh nhầm 2 GPU khác nhau, không phải 2 backend trên cùng 1 GPU. Chi tiết:
`benchmarks/bonus-vulkan-vs-cuda.md`.

### B1 — build từ source

```
before:  13.8 tok/s   (prebuilt release, CPU dispatch, -ngl 0)
after:   12.7 tok/s   (source build, -DGGML_NATIVE=ON, -ngl 0)
speedup: 0.92×  (prebuilt thắng 1.09×)
```

Trên máy anh, **tự compile không thắng** — trái ngược hoàn toàn kỳ vọng "máy yếu
mới thấy chênh lệch rõ nhất" của bonus README, và đây chính là finding đáng giá:
mọi lần chạy bản prebuilt cả buổi đều load `ggml-cpu-alderlake.dll` — tức bản release
**đã** ship sẵn kernel CPU tối ưu riêng cho đúng vi kiến trúc Alder Lake của
i5-12450H (chọn qua CPUID lúc runtime), không phải một bản chung chung cho mọi CPU.
`-DGGML_NATIVE=ON` nhắm đúng tập lệnh mà `ggml-cpu-alderlake.dll` đã nhắm sẵn, nên
không còn dư địa vector-width nào để bản tự build khai thác thêm. Cộng với việc
decode bị chặn bởi **memory bandwidth** (đúng phát hiện xuyên suốt cả §5 lẫn
`01-tuning-tg128.md`), cải thiện instruction-level từ compiler flag gần như không
có gì để phát huy khi CPU chủ yếu đang chờ RAM chứ không phải đang tính toán. Phần
âm 8% còn lại nhiều khả năng là do CI chính thức có thêm tối ưu (LTO, toolset khác)
mà local build không có, hoặc nhiễu nhiệt sau nhiều giờ máy chạy liên tục — không
phải do `-DGGML_NATIVE=ON` làm chậm đi. Chi tiết:
`benchmarks/bonus-build-compare-tg128.md`.

**Điều này nói lên gì mà deck chưa nói:** B1 không phải lúc nào cũng thắng — trên
máy đã có GPU mạnh và CPU đời mới (đã có sẵn kernel tối ưu vi kiến trúc trong bản
release), compile tay không mang lại gì, thậm chí có thể chậm hơn do thiếu các tối
ưu build của CI chính thức. "Tự build luôn nhanh hơn prebuilt" là một giả định cần
kiểm chứng trên từng máy, không phải một quy luật.

---

## 7. Điều làm bạn ngạc nhiên nhất  *(optional)*

Server không hề crash hay báo lỗi bind port khi `llama-server` (127.0.0.1:8080) và một
service Docker khác (0.0.0.0:8080) cùng "chiếm" port 8080 — Windows cho phép bind cụ
thể (127.0.0.1) và bind wildcard (0.0.0.0) cùng tồn tại. Hệ quả là mọi script Python
của lab gọi qua `localhost` (ưu tiên phân giải IPv6 `::1`) lặng lẽ nói chuyện với
service sai, trả về lỗi 404 trông y hệt lỗi thật của llama.cpp — không có cảnh báo
nào cho biết đang gọi nhầm server.

---

## 8. Self-check trước khi push

- [x] `hardware.json` committed
- [x] `models/active.json` committed
- [x] `benchmarks/01-quickstart-results.md` committed (`make bench`)
- [x] `benchmarks/01-tuning-tg128.md` committed (`make tune`)
- [x] `benchmarks/02-server-results.md` committed (`make load-report`)
- [x] `benchmarks/02-server-batching-u50.md` hoặc `-metrics-u50.csv` committed (`make metrics`)
- [x] `benchmarks/locust-10_stats.csv` + `locust-50_stats.csv` committed (`make load-10` / `load-50`)
- [x] `benchmarks/03-integration-results.md` committed (`make pipeline`)
- [x] Mọi section **"required — replace this line"** trong các file `benchmarks/*.md`
      đã được thay bằng nhận xét của bạn
- [ ] 5 screenshots trong `submission/screenshots/`
- [ ] `make verify` → **exit 0**
- [ ] Repo GitHub ở chế độ **public**
- [ ] Đã paste public URL vào VinUni LMS
- [x] **Không** commit `models/*.gguf` hay `runtime/` (đã có trong `.gitignore`)

**Quan trọng:** repo phải **public** đến khi điểm được công bố. Private → grader không
xem được → 0 điểm.
