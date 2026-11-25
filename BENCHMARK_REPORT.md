# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Nguyen Tien Cuong (2A202603425)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 Ubuntu + Docker Desktop (Docker 29.8.1)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Đảm bảo 95% request trả lời nhanh dưới nửa giây cho trải nghiệm chat tương tác (khớp ngưỡng SLO mặc định của `load_test.py`) |
| Error rate `/ask` | < 2.0 % | Chấp nhận ~1% lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=0.01`), giữ error budget 2% để kịp cảnh báo khi tỷ lệ lỗi tăng bất thường |
| Accuracy trên golden dataset | ≥ 85 % | Ngưỡng quality gate tối thiểu trong CI (`.github/workflows/eval.yml`) để chặn merge khi câu trả lời giảm chất lượng |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.22 | 188.0 | 221.0 | 1694.6 | 1.33% (4/300) | PASS |
| 10 | 33.72 | 190.6 | 227.1 | 1689.5 | 1.67% (5/300) | PASS |
| 50 | 105.27 | 196.4 | 260.9 | 1714.7 | 1.00% (3/300) | PASS |
| 100 | 52.99 | 450.5 | 3699.4 | 4000.7 | 1.33% (4/300) | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không tăng tuyến tính ở mức tải cao: từ `concurrency=1` lên `10` và `50`, RPS tăng nhanh (`4.22 → 33.72 → 105.27 req/s`) nhờ I/O async chạy song song khi chờ `asyncio.sleep`; nhưng tới `concurrency=100`, RPS tụt một nửa xuống `52.99 req/s`, p50 tăng lên `450.5 ms` và p95 vọt lên `3699.4 ms` (vi phạm SLO `< 500 ms`). Nguyên nhân là single-process uvicorn trên 1 worker bị bão hòa event loop / hàng đợi socket & connection khi 100 request dồn cùng lúc.

### 2.2 Tail latency (`concurrency=20`, `requests=300`)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 188.9 | 216.8 | 226.7 |
| 0.03 (mặc định) | 225.1 | 221.0 | 1698.9 |
| 0.1 | 300.9 | 1684.0 | 1716.1 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

`p99` nhạy nhất với request chậm: chỉ cần `MOCK_SLOW_RATE=0.03` (3% request chậm), `avg` chỉ nhích nhẹ từ `188.9 ms` lên `225.1 ms` (+36.2 ms) và `p95` gần như đứng yên (`221.0 ms`), nhưng `p99` nhảy vọt hơn 7.5 lần lên `1698.9 ms`. Khi tăng lên `0.1` (10% chậm > 5%), cả `p95` cũng vọt lên `1684.0 ms` trong khi `avg` mới đạt `300.9 ms`. Vì vậy trung bình che giấu nhóm người dùng chịu độ trễ lớn (tail latency), nên SLO phải đặt theo `p95`/`p99`.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.0 | 109.3 | 113.7 |
| Tổng cost (USD) | $0.000402 | $0.000764 | $0.000790 |
| Cost / câu đúng (USD) | $0.00040215 | $0.00003639 | $0.00003436 |
| Quality gate | FAIL | PASS | PASS (0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry trigger `["jwt"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` giải thích JWT là token có chữ ký số và thời điểm hết hạn (không sửa `golden_dataset.jsonl`) |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry trigger `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` giải thích Kubernetes HPA scale theo CPU, memory hoặc custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2 & CI Quality Gate:**

Agent v2 thêm bước retrieval nên tốn gần gấp đôi token mỗi câu (`109.3` so với `57.0`), tổng cost tăng gần 2 lần (`$0.000764` vs `$0.000402`) và latency tăng nhẹ (~20 ms retrieval + prompt dài hơn: p95 `215.5 ms` vs `189.7 ms`). Tuy nhiên accuracy nhảy vọt từ `4.35%` lên `91.3%` khiến **cost trên mỗi câu trả lời đúng** giảm hơn **11 lần** (`$0.00040215` → `$0.00003639`). Để ngăn regression trước khi merge code, workflow CI [.github/workflows/eval.yml](.github/workflows/eval.yml) chạy `python eval/run_eval.py --min-accuracy 0.85`; script sẽ trả **exit code `1`** nếu `accuracy < 0.85` hoặc có câu từng đúng ở baseline bị sai lại, làm job GitHub Actions fail và tự động chặn merge PR.

---

## 4. Observability stack (production)

### 4.1 Screenshot & trả lời Exercise 7.4

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png) *(hiển thị 2 instance đang chạy, `Latency p95 = 1.84 s`, `LLM cost = $0.5137`, biểu đồ traffic ~60 req/s)*
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png) *(`trace_id: 818a0b91f9740bb2750e0ffbb1e3a622`, `Duration: 1.7s`, span `chat mock-llm-small` chiếm gần như toàn bộ thời gian)*
- [x] Một trace lỗi trong Jaeger (503 trên span `chat mock-llm-small` và `POST /ask`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png) *(`trace_id: 62d1a63498184e44df2f38fc463687bb`, `Duration: 186ms`, span `chat mock-llm-small` 99.7ms lỗi 503)*
- [x] Trang Alerts của Prometheus với **3 alert cùng đang firing**: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png) *(`AgentHighErrorRate` = 33.3%, `AgentHighLatencyP95`, `AgentInstanceDown`)*

**Trả lời câu hỏi Exercise 7.4:**
1. **Khoảng cách giữa `avg` và `p95`/`p99`:** Trên dashboard khi có tải, p50 nằm quanh ~190 ms nhưng `Latency p95` vọt lên `1.84 s` (vùng đỏ) — khoảng cách lớn này phản ánh nhóm ~3% request bị tail latency (`MOCK_SLOW_RATE=0.03`, cộng thêm `1500 ms`), khiến người dùng rơi vào nhóm đuôi phải chờ gần 2 giây.
2. **Nginx có chia đều traffic cho các instance không?** Có. `nginx.conf` dùng `upstream agent_cluster` kết hợp `resolver 127.0.0.11 valid=10s` và `server agent:8000 resolve` nên Nginx tự nhận danh sách container qua Docker DNS và phân phối đều theo round-robin (gọi nhiều lần thấy header `X-Served-By` luân phiên giữa các IP container).
3. **Vì sao `input tokens/s` lớn hơn `output tokens/s`?** Với agent v2 (RAG), mỗi prompt gửi vào LLM ghép `SYSTEM_PROMPT` + đoạn context lấy từ `KNOWLEDGE_BASE` + câu hỏi của user nên độ dài input dài hơn câu trả lời output (ví dụ ở trace chậm bên dưới: `input_tokens = 81` gần gấp đôi `output_tokens = 46`).
4. **`curl http://localhost:8080/metrics` trả về gì và vì sao?** Trả về **HTTP 404 Not Found**, vì [nginx.conf](06-lab-complete/benchmark-observability/production/nginx/nginx.conf) cấu hình `location = /metrics { return 404; }`. `/metrics` chỉ để Prometheus scrape trực tiếp trong mạng nội bộ Docker (`obs_net`), chặn từ bên ngoài nhằm tránh lộ thông tin nội bộ hệ thống (route, lưu lượng, model, chi phí).

### 4.2 Thí nghiệm "phá hệ thống"

Trong lần chạy kiểm chứng trên Prometheus Alerts ([screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)), đã bật đồng thời fault injection (`MOCK_ERROR_RATE=0.2`, `MOCK_SLOW_RATE=0.3`, `LLM_MODEL=mock-llm-large`) kết hợp `docker pause` 1 instance agent (`agent-1`) và chạy tải Locust 30 users: **3 alert thuộc nhóm `agent-slo` đã cùng chuyển sang `FIRING`** (`AgentHighErrorRate` đạt `33.33%`, `AgentHighLatencyP95`, `AgentInstanceDown`).

| # | Thay đổi | Alert nào firing | Thời gian tới lúc firing (theo rule `for:` + chu kỳ scrape 5s/eval) | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`FIRING`, giá trị đo `33.33%`) | > 1 phút (`for: 1m`; ảnh chụp ghi nhận đã active `3m 6.9s`) | Panel **Error rate** (đỏ) & **Requests/s theo status code** (5xx) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`FIRING`) | > 2 phút (`for: 2m`) | Panel **Latency p95** & biểu đồ **Latency `/ask` p50/p95/p99** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` *(khi `rate(llm_cost_usd_total[5m])*3600 > 2`)* | > 2 phút (`for: 2m`, phụ thuộc tốc độ tích lũy của cửa sổ 5m) | Panel **LLM cost / giờ** & **LLM p95** |
| D | `docker pause k5-day14-observability-agent-1` | `AgentInstanceDown` (`FIRING`) | > 30 giây (`for: 30s`) | Panel **Instances** (số instance up giảm xuống) |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | N/A | Panel **Retrieval hit ratio** mất (về 0), **Tokens/s** giảm, bảng **Version** đổi sang `v1` |

- **Ghi chú thí nghiệm D (`docker pause` vs `docker stop` & lỗi 504):** Dùng `docker pause` vì container bị dừng hẳn (`docker stop`) sẽ biến mất khỏi Docker DNS khiến Prometheus bỏ target đó thay vì coi là `up == 0`. Khi container bị treo (`pause`), các request Nginx lỡ gửi vào sẽ timeout ở Nginx thành lỗi **504** và không hiện trên panel Error rate của agent (vì agent chưa trả response để đếm metric), do đó production cần giám sát thêm ở tầng load balancer / synthetic check.
- **Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**
  - Dùng **Eval Quality Gate tự động trong CI/CD** (chạy `eval/run_eval.py` trên golden dataset trước mỗi lần deploy, chặn merge nếu accuracy giảm hoặc có regression).
  - Theo dõi các **metric chất lượng/RAG ở mức ứng dụng** như `retrieval_hit_ratio` (tụt bất thường về 0 khi chuyển nhầm sang `v1` hoặc hỏng vector DB) và bảng version đang chạy (`agent_info{version=...}`).
  - Kết hợp **online evaluation** (chấm mẫu traffic thật bằng LLM-as-a-judge) và thu thập **user feedback** (thumbs up/down).

### 4.3 Debug bằng trace

Trace chậm được chọn (đã chụp ở [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)):

- `trace_id`: `818a0b91f9740bb2750e0ffbb1e3a622`
- Tổng thời gian: `1703.8 ms` (hiển thị `1.7s` trên Jaeger UI)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1682.5 ms`, chiếm **98.75%** tổng thời gian request; bước retrieval `agent.retrieve_context` chỉ mất `19.4 ms` ≈ **1.14%**)
- Dòng log tương ứng (grep theo `trace_id` từ `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-25T12:38:40.585993+00:00", "level": "INFO", "service": "observable-agent", "instance": "d41401009411", "event": "llm_call", "trace_id": "818a0b91f9740bb2750e0ffbb1e3a622", "span_id": "a355b6332b088f2b", "request_id": "e6bf07faf4ee", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 81, "output_tokens": 46, "cost_usd": 4e-05, "llm_ms": 1682.5}
{"ts": "2026-11-25T12:38:40.586468+00:00", "level": "INFO", "service": "observable-agent", "instance": "d41401009411", "event": "http_request", "trace_id": "818a0b91f9740bb2750e0ffbb1e3a622", "span_id": "a355b6332b088f2b", "request_id": "e6bf07faf4ee", "method": "POST", "route": "/ask", "status": 200, "ms": 1703.8}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu lấy từ [benchmark-results/scale_1_stats.csv](benchmark-results/scale_1_stats.csv) và [benchmark-results/scale_3_stats.csv](benchmark-results/scale_3_stats.csv) (dòng `Aggregated`; chi tiết riêng `POST /ask` ghi kèm bên dưới):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.63 | 190 | 230 | 1700 | 80 / 7856 (1.02%) |
| 3 | 66.38 | 190 | 230 | 1700 | 68 / 7943 (0.86%) |

- **Chi tiết riêng endpoint `POST /ask`:**
  - **1 instance:** `7151` requests, `80` failures (`1.12%`), `59.74` req/s, `avg = 235.5 ms`, `p50 = 190 ms`, `p95 = 240 ms`, `p99 = 1700 ms`.
  - **3 instances:** `7239` requests, `68` failures (`0.94%`), `60.50` req/s, `avg = 234.1 ms`, `p50 = 190 ms`, `p95 = 240 ms`, `p99 = 1700 ms`.

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ **1 lên 3 instance** giữ nguyên `p50 = 190 ms`, `p95 = 230 ms` (`240 ms` với riêng `/ask`), `p99 = 1700 ms`, và tổng RPS gần như không đổi (`65.63 → 66.38 req/s`). Nguyên nhân là **nút thắt nằm ở độ trễ chờ I/O từ upstream LLM** (`MOCK_LATENCY_MS=120ms` + jitter + `3%` slow `+1500ms`) cùng nhịp `wait_time` của 100 user Locust — FastAPI bất đồng bộ (`async`) trên 1 container chưa bị nghẽn CPU ở mức tải 100 users này. Do đó thêm replica giúp tăng **tính sẵn sàng (high availability)** và chịu tải khi có tác vụ nặng CPU/traffic lớn hơn nhiều, chứ không làm giảm latency của từng LLM call; muốn hạ p95/p99 phải tối ưu ở tầng LLM (semantic cache, streaming TTFT, chọn model nhanh hơn hoặc retry/hedging request chậm).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Average che giấu tail latency:** Chỉ 3% request chậm cũng đẩy `p99` lên ~1.7s trong khi `avg` trông vẫn bình thường; luôn phải đặt SLO và theo dõi theo `p95`/`p99`.
  2. **Hạ tầng xanh chưa chắc AI trả lời đúng:** Khi đổi sang `v1`, latency/error rate vẫn tốt nên Prometheus không báo đỏ, bắt buộc phải kết hợp **eval trên golden dataset** và **CI quality gate** trước khi deploy.
  3. **Liên kết 3 trụ cột (Metrics → Traces → Logs):** Dashboard Grafana phát hiện tăng `p95`, Jaeger chỉ ra span `chat mock-llm-small` chiếm 98.75% thời gian, và `trace_id` giúp grep chính xác dòng log JSON tương ứng.
- **Metric / alert sẽ bổ sung khi đưa agent lên production thật:**
  - Giám sát ở tầng Load Balancer / Nginx (`5xx` / `504` rate, upstream timeout) và synthetic health probe từ bên ngoài.
  - Theo dõi Redis (`redis_up`, command latency, bộ nhớ, tỉ lệ hit rate limit `429` và budget guard `402`).
  - Alert cho chất lượng & RAG: `retrieval_hit_ratio` tụt ngưỡng, TTFT (Time To First Token) cho streaming, và điểm đánh giá chất lượng online (LLM-as-a-judge / user feedback).
