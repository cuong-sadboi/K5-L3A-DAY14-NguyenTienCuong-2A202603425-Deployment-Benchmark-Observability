# Day 14 Lab - Mission Answers

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **Hardcoded secrets trong source code (`app.py` dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - Khi commit lên GitHub, bí mật lộ ngay trong lịch sử git; bản `01-localhost-vs-production/production/app.py` tách toàn bộ cấu hình ra `config.py` (`settings`) đọc từ biến môi trường.
2. **Không quản lý cấu hình theo môi trường (`app.py` dòng 21–22):**
   - `DEBUG = True`, `MAX_TOKENS = 500` ghi cứng trong code, không phân biệt `development` / `staging` / `production`.
3. **Dùng `print()` và làm lộ secret ra log (`app.py` dòng 33–38):**
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` (dòng 34) in thẳng API key ra stdout; bản `production/app.py` dùng `logging` định dạng JSON (dòng 28–31, 111–122) và tuyệt đối không log secret.
4. **Thiếu endpoint kiểm tra sức khỏe `/health` và `/ready` (`app.py` dòng 42–43):**
   - Cloud platform và load balancer không biết khi nào process treo hoặc chưa sẵn sàng; bản `production/app.py` có `GET /health` (dòng 135–149) và `GET /ready` trả 503 khi chưa sẵn sàng (dòng 152–161).
5. **Bind `host="localhost"` và hardcode `port=8000` (`app.py` dòng 51–52):**
   - `localhost` chỉ lắng nghe loopback nên bên ngoài Docker container không kết nối vào được; `port=8000` không nhận biến `PORT` do platform cấp. Bản `production/app.py` dùng `settings.host` (`0.0.0.0`) và `settings.port` từ biến `PORT` (dòng 194–198).
6. **Bật `reload=True` trong uvicorn (`app.py` dòng 53) & không có graceful shutdown:**
   - `reload=True` tốn CPU/RAM theo dõi file và làm rớt request; bản `production/app.py` chỉ bật `reload` khi `settings.debug` là True và dùng `lifespan` (dòng 39–67) + `SIGTERM` handler (dòng 180–189) để tắt êm.

### Exercise 1.2: Kết quả chạy bản develop

```http
$ curl -i -s -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:03:28 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 1.3: So sánh Develop vs Production

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG = True` ngay trong code | Đọc từ biến môi trường qua `config.py` (`settings`) | Tách biệt config khỏi code (12-Factor), đổi cấu hình theo môi trường không cần sửa code, tránh lộ secret lên Git |
| **Network & Port** | `host="localhost"`, `port=8000`, `reload=True` | `host=settings.host` (`0.0.0.0`), `port=settings.port` (`PORT` env), `reload=settings.debug` | Trong container/cloud, app phải lắng nghe `0.0.0.0` và cổng động `PORT` do platform cấp mới nhận được traffic từ ngoài |
| **Health Check** | Không có `/health`, `/ready` | Có `GET /health` (liveness) và `GET /ready` (readiness, trả 503 khi chưa sẵn sàng) | Platform/load balancer tự động phát hiện container treo để restart (`/health`) hoặc tạm ngưng route traffic (`/ready`) |
| **Logging** | `print("[DEBUG] ...")` dạng text thuần, in cả API key | `logging` định dạng JSON có `time`, `level`, `msg`, không log secret | Log JSON giúp hệ thống thu thập log (Loki, Datadog, CloudWatch) parse, lọc và truy vết sự cố nhanh, an toàn bảo mật |
| **Shutdown** | Tắt đột ngột khi nhận signal | FastAPI `lifespan` + bắt `SIGTERM` để hoàn tất request đang xử lý | Tránh cắt ngang request của người dùng và rò rỉ kết nối database/Redis khi deploy bản mới hoặc scale down |
| **CORS** | Không cấu hình | `CORSMiddleware` giới hạn `allow_origins` và `allow_methods` | Kiểm soát domain web nào được phép gọi API từ trình duyệt |

---

## Part 2: Docker

### Exercise 2.1: Đọc `02-docker/develop/Dockerfile` và trả lời câu hỏi

1. **Base image là gì?**
   - `python:3.11` (dòng 8) — image Debian đầy đủ có sẵn Python 3.11 cùng nhiều công cụ build/OS (~1 GB).
2. **Working directory là gì?**
   - `/app` (`WORKDIR /app`, dòng 11) — mọi lệnh `COPY`, `RUN`, `CMD` phía sau thực thi tương đối trong thư mục này.
3. **Tại sao `COPY 02-docker/develop/requirements.txt .` và `pip install` lại đặt trước `COPY 02-docker/develop/app.py .`?**
   - Để tận dụng **Docker layer cache**. Khi chỉ sửa code `app.py` mà không đổi `requirements.txt`, Docker tái sử dụng lại layer đã cài thư viện ở lần build trước thay vì tải và cài lại toàn bộ dependencies từ đầu.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` chỉ định lệnh/tham số mặc định khi chạy container và có thể bị ghi đè hoàn toàn nếu truyền thêm command sau `docker run <image> ...`.
   - `ENTRYPOINT` cố định file thực thi chính của container; các tham số truyền vào `docker run` (hoặc giá trị của `CMD`) sẽ được nối vào làm đối số cho `ENTRYPOINT`.

### Exercise 2.2: Build và chạy container `my-agent:develop`

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
# [+] Building 97.2s (13/13) FINISHED

docker run -d --rm --name test-dev -p 8000:8000 my-agent:develop
curl -s -X POST "http://localhost:8000/ask?question=Docker"
# {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
docker stop test-dev
```

### Exercise 2.3: Multi-stage build & so sánh kích thước image

- **Stage 1 (`builder`, `python:3.11-slim`):** cài các build tools (`gcc`, `libpq-dev`) và chạy `pip install --no-cache-dir --user -r requirements.txt` để biên dịch và cài đặt toàn bộ Python packages vào `/root/.local`.
- **Stage 2 (`runtime`, `python:3.11-slim`):** bắt đầu từ image sạch, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local` sang `/home/appuser/.local` cùng `main.py` và `utils/mock_llm.py`, bổ sung `HEALTHCHECK`, rồi chạy `uvicorn` với quyền `appuser`.
- **Tại sao image nhỏ hơn?** Vì toàn bộ trình biên dịch (`gcc`, `libpq-dev`), cache apt và công cụ build ở Stage 1 bị loại bỏ hoàn toàn khỏi image cuối, đồng thời dùng base `python:3.11-slim` thay vì `python:3.11` full.

**Số đo kích thước thực tế (`docker images | grep my-agent`):**
```text
my-agent:advanced              3e917ab4ae9f        240MB         57.4MB
my-agent:develop               1a52781ffc1f       1.67GB          426MB
```
- Develop (`my-agent:develop`): **1.67 GB (1670 MB)** (disk usage `426MB`)
- Production (`my-agent:advanced`): **240 MB** (disk usage `57.4MB`)
- Chênh lệch / giảm: giảm **1430 MB (~85.6%)**

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc các service (network nội bộ `internal`):**

```text
Client
  │  HTTP :80 / HTTPS :443
  ▼
Nginx (reverse proxy / load balancer)
  │  proxy pass :8000
  ▼
Agent (FastAPI :8000, depends_on redis & qdrant healthy)
  ├──────────────▶ Redis (:6379, session cache & rate limiting, volume redis_data)
  └──────────────▶ Qdrant (:6333, vector database cho RAG, volume qdrant_data)
```

**Kết quả test stack qua Nginx (`http://localhost/health` và `http://localhost/ask`):**

```text
[+] up 6/6
 ✔ Image k5-day14-part2-agent        Built                                         1.8s
 ✔ Network k5-day14-part2_internal   Created                                       0.1s
 ✔ Container k5-day14-part2-qdrant-1 Healthy                                       6.5s
 ✔ Container k5-day14-part2-redis-1  Healthy                                      12.0s
 ✔ Container k5-day14-part2-agent-1  Started                                      11.9s
 ✔ Container k5-day14-part2-nginx-1  Started                                      11.7s

$ curl -s http://localhost/health
{"status":"ok","uptime_seconds":7.0,"version":"2.0.0","timestamp":"2026-11-25T09:59:03.338353"}

$ curl -s -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.2: Deploy lên Render (nền tảng chính — deploy agent Part 6 từ `06-lab-complete/`)

- **Platform:** Render (`Web Service` dùng `Docker` runtime với Root Directory `06-lab-complete`, region Singapore + `Render Key Value` / Valkey 8 cho Redis ở cùng region Singapore).
- **Public URL:** `https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com`
- **Biến môi trường đặt trên Render Dashboard:** `ENVIRONMENT=production`, `LOG_LEVEL=INFO`, `AGENT_API_KEY` (đặt bí mật trên dashboard, không lưu trong code/repo), `REDIS_URL` (Internal Key Value URL), `RATE_LIMIT_PER_MINUTE=10`, `DAILY_BUDGET_USD=1.0`, `MONTHLY_BUDGET_USD=10.0`, cùng `PORT` do Render tự cấp.
- **Kết quả chạy 4 lệnh tự kiểm CP6:**
  ```text
  BASE=https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com
  /health       -> 200
  /ready        -> 200
  /ask (no key) -> 401
  /ask (valid)  -> 200
  ```
- **Screenshots:**
  - Dashboard Render (Web Service + Key Value): [screenshots/dashboard.png](screenshots/dashboard.png)
  - Service đang chạy (`/ready` trả `{"status": "ready", "redis": "ok"}`): [screenshots/running.png](screenshots/running.png)
  - Kết quả kiểm tra HTTP 200 / 200 / 401 / 200: [screenshots/test.png](screenshots/test.png)

### So sánh `railway.toml` với `render.yaml`

| Tiêu chí | `railway.toml` | `render.yaml` | Lý do khác nhau |
| --- | --- | --- | --- |
| **Định dạng & vai trò** | File **TOML** cấu hình cho **1 service** đang deploy | File **YAML** dạng **Infrastructure-as-Code (Blueprint)** | Railway quản lý tài nguyên (như Redis add-on) qua dashboard/CLI rồi gắn `railway.toml` vào từng service; Render Blueprint cho phép khai báo trọn bộ kiến trúc gồm nhiều service trong 1 file |
| **Khai báo hạ tầng & DB** | Chỉ có `[build]` và `[deploy]`, không khai báo database đi kèm | Khai báo danh sách `services:` gồm cả Web Service và Redis (`type: redis` / Key Value), kèm `region`, `plan`, `autoDeploy` | Render Blueprint tự tạo mới và đồng bộ toàn bộ stack từ repo git; Railway ưu tiên workflow `railway init` / add service trực quan |
| **Build & Healthcheck** | `builder = "DOCKERFILE"`, `healthcheckPath = "/health"`, `restartPolicyType` | `runtime: docker` (hoặc `python`), `dockerfilePath`, `healthCheckPath: /health` | Khác quy ước đặt tên trường (snake/camel case) và cơ chế khởi động: Railway dùng `startCommand` hoặc `CMD` trong Dockerfile, Render có `buildCommand` + `startCommand` (hoặc `Dockerfile`) |
| **Quản lý biến môi trường & secret** | Không khai báo secret trong file; biến môi trường đặt bằng `railway variables set` hoặc Dashboard | Khai báo mục `envVars:` trực tiếp trong YAML; secret đánh dấu `sync: false` (nhập tay trên UI) hoặc `generateValue: true` (Render tự sinh) | Đảm bảo không commit secret lên Git mà vẫn ghi nhận được danh sách biến môi trường mà service yêu cầu |

### Exercise 3.3: GCP Cloud Run CI/CD (`03-cloud-deployment/production-cloud-run/`)

Pipeline CI/CD trong [cloudbuild.yaml](03-cloud-deployment/production-cloud-run/cloudbuild.yaml) chạy tự động qua 4 bước tuần tự (`waitFor`):
1. **Test (`test`):** dùng container `python:3.11-slim` cài `requirements.txt`, `pytest` và chạy `pytest tests/ -v --tb=short` — fail là dừng ngay pipeline.
2. **Build (`build`):** build Docker image gắn hai tag `gcr.io/$PROJECT_ID/ai-agent:$COMMIT_SHA` và `:latest` (tận dụng `--cache-from` từ image `:latest` để tăng tốc).
3. **Push (`push`):** đẩy cả hai tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** triển khai lên Cloud Run (`asia-southeast1`, managed) với cấu hình 1 vCPU / 512Mi RAM, scale 1–10 instance (giảm cold start), concurrency 80 request/instance như định nghĩa ở [service.yaml](03-cloud-deployment/production-cloud-run/service.yaml), đọc secret từ Google Secret Manager và kiểm tra sức khỏe bằng `/health` (`livenessProbe`) và `/ready` (`startupProbe`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- API key đọc từ biến môi trường `AGENT_API_KEY`, kiểm tra trong dependency `verify_api_key` dùng `APIKeyHeader(name="X-API-Key", auto_error=False)`. Thiếu header trả **401**, sai key trả **403** (trong bản Part 6 chuẩn hóa cả thiếu và sai key đều trả **401**). Rotate key bằng cách cập nhật `AGENT_API_KEY` trong env (production hỗ trợ đồng thời key cũ/mới trong giai đoạn chuyển tiếp rồi thu hồi key cũ).

```http
# Không có X-API-Key -> 401
$ curl -i -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 10:03:56 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có X-API-Key hợp lệ -> 200
$ curl -i -s -X POST http://localhost:8000/ask -H "X-API-Key: <API_KEY>" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:03:56 GMT
server: uvicorn
content-length: 122
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **JWT Flow (`auth.py`):** Client gửi username/password (`student` / `demo123`) tới `POST /auth/token` → server xác thực và ký HS256 JWT chứa `sub` (username), `role`, `iat`, `exp` (60 phút) → các request sau gửi `Authorization: Bearer <token>`, server verify chữ ký không cần tra DB mỗi request.
- **Rate Limiting (`rate_limiter.py`):** Dùng thuật toán **Sliding Window** (lưu `deque` timestamp trong 60 giây). Giới hạn mặc định **10 req/phút** cho role `user` (`rate_limiter_user`) và **100 req/phút** cho `admin` (`rate_limiter_admin`), vượt giới hạn trả **429 Too Many Requests** kèm `Retry-After` và các header `X-RateLimit-*`. Có thể tách hạn mức/bypass cho admin dựa theo `role` lấy từ payload JWT.

```text
Token received (masked): eyJhbGciOiJI***
--- Request 1 ---
HTTP/1.1 200 OK
{"question":"Test 1","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
...
--- Request 10 ---
HTTP/1.1 200 OK
{"question":"Test 10","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000181}}
--- Request 11 ---
HTTP/1.1 429 Too Many Requests
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
--- Request 12 ---
HTTP/1.1 429 Too Many Requests
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Thiết kế Cost Guard

- **Cơ chế:** Tính chi phí ước lượng từ số `input_tokens` và `output_tokens` nhân với đơn giá từng 1K token (`$0.00015 / 1K input`, `$0.0006 / 1K output` cho `gpt-4o-mini`).
- **Quy trình kiểm soát:**
  1. **Trước khi gọi LLM (`check_budget`):** đọc tổng chi phí hiện tại (theo ngày/tháng) trong Redis; nếu đã đạt hoặc vượt ngân sách (`DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD`) → chặn ngay bằng **HTTP 402 Payment Required**, không gửi request sang LLM tránh phát sinh chi phí ngoài kiểm soát.
  2. **Sau khi gọi LLM (`record_cost`):** tính chi phí thật của request và cộng dồn vào Redis bằng lệnh atomic `INCRBYFLOAT` kèm `EXPIRE` để tự động reset sang chu kỳ ngày/tháng mới.
- **Vì sao cần cả Rate Limit lẫn Cost Guard:** Rate Limit bảo vệ **tốc độ** request (chống spam/DoS theo thời gian ngắn), còn Cost Guard bảo vệ **ngân sách tiền** (vì một vài request có prompt/response rất dài vẫn có thể đốt hết budget dù chưa vượt rate limit).

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Health Checks, Graceful Shutdown & Stateless Design

- **Liveness (`/health`) vs Readiness (`/ready`):**
  - `GET /health` kiểm tra tiến trình còn sống hay không (trong Part 6 luôn trả **200** ngay cả khi Redis mất kết nối để platform không restart oan container khi phụ thuộc ngoài tạm chập chờn).
  - `GET /ready` kiểm tra khả năng sẵn sàng phục vụ (ping Redis); nếu mất kết nối trả **503** để load balancer tạm ngừng gửi traffic mới tới instance đó.
- **Graceful Shutdown (`SIGTERM`):** Khi orchestrator muốn dừng container (deploy mới hoặc scale down), nó gửi `SIGTERM`. App ngừng nhận request mới, đợi các request *in-flight* xử lý xong và trả 200 cho client, đóng kết nối Redis sạch sẽ qua `lifespan` rồi mới thoát với exit code `0`.
- **Stateless Design:** Không lưu session, lịch sử chat, rate limit hay cost counter trong RAM của từng process Python vì khi chạy nhiều instance sau load balancer, các request liên tiếp của cùng 1 user sẽ rơi vào các instance khác nhau. Toàn bộ state được đưa ra **Redis** dùng chung để mọi instance đọc/ghi nhất quán và giữ nguyên dữ liệu kể cả khi 1 instance bị tắt hoặc restart.

### Exercise 5.4 & 5.5: Load Balanced Stack (`agent=3`) & Test Stateless

```bash
cd 05-scaling-reliability/production
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python test_stateless.py
docker compose -p k5-day14-scaling down
```

**Output thực tế từ `python test_stateless.py`:**
```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 2649b4ca-61f5-4fbb-af83-d74d1d537821

Request 1: [instance-7a9c01]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-25c3a6]
  Q: Why do we need containers?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 3: [instance-c09e6b]
  Q: What is Kubernetes?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 4: [instance-7a9c01]
  Q: How does load balancing work?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 5: [instance-25c3a6]
  Q: What is Redis used for?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-c09e6b', 'instance-7a9c01', 'instance-25c3a6'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Kubernetes?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: How does load balancing work?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Redis used for?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...

✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:** Nginx phân phối 5 request liên tiếp của cùng 1 `session_id` (`2649b4ca-61f5-4fbb-af83-d74d1d537821`) theo round-robin tới cả 3 container (`instance-7a9c01`, `instance-25c3a6`, `instance-c09e6b`). Vì toàn bộ lịch sử hội thoại được lưu tập trung trong Redis theo key `session:{session_id}` thay vì trong RAM của từng instance, mọi instance đều đọc và cập nhật cùng một mạch hội thoại (đủ 10 message: 5 user + 5 assistant) mà không bị mất ngữ cảnh.

---

## Part 6: Final Project (`06-lab-complete/`)

Kết quả chạy `python check_production_ready.py` đầy đủ trong môi trường WSL2 Ubuntu có Docker (`python3` 3.11, `Docker 29.8.1`):

- Image Docker multi-stage build thành công trong **73s**, dung lượng **273 MB** (`< 500 MB`).
- Rate limit qua Redis (`RATE_LIMIT_PER_MINUTE=5`) trả `429` sau 5 request thành công, giữ nguyên trạng thái `429` sau khi restart agent.
- Cost guard trả `402`, structured logging xuất **17 dòng JSON** hợp lệ, `SIGTERM` xử lý trọn request đang chạy (exit code `0`), `docker stop` thoát êm với **exit code `0` trong `0.8s`**.

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

| Giai đoạn | Hỏi AI điều gì | Nhận gì từ AI | Tự sửa & tự kiểm tra thế nào |
| --- | --- | --- | --- |
| **Setup & Part 6 (`06-lab-complete/`)** | Cách hoàn thiện các `TODO` theo đúng 12 tiêu chí (multi-stage Dockerfile, Redis sliding window rate limit, cost guard, JSON logging, FastAPI lifespan, config env, deploy config) và xử lý lỗi môi trường WSL2/Docker | Code hoàn chỉnh cho `app/*.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml` và hướng dẫn tạo venv Python 3.11 + cấp quyền Docker group trên Ubuntu WSL2 | Đọc lại từng file trong `06-lab-complete/`, chạy kiểm tra trực tiếp bằng `python check_production_ready.py` trong WSL2 đạt **`PASS 12/12 · 43/43 checks passed`** |
| **Part 3 (Cloud Deployment)** | Hướng dẫn chi tiết từng bước deploy `06-lab-complete/` kèm Redis lên Render và viết `DEPLOYMENT.md` | Các bước tạo Render Key Value (Singapore) + Web Service Docker (`Root Directory: 06-lab-complete`), so sánh `railway.toml` vs `render.yaml` và tóm tắt pipeline Cloud Run | Tự tạo service trên Render Dashboard, tự đặt secret env vars (không đưa vào repo), chạy 4 lệnh `curl` kiểm tra URL public ra đúng `200 / 200 / 401 / 200` và tự chụp 3 ảnh trong `screenshots/` |
| **Part 1–5 (Tổng hợp & kiểm chứng thực tế)** | Rà soát anti-pattern, kiến trúc Compose và cấu trúc bảo mật từ code mẫu trong repo để lập bảng so sánh và giải thích cơ chế | Khung phân tích đối chiếu code trong `01-` đến `05-` kèm lệnh chạy trong WSL2 | Tự chạy kiểm chứng `01-localhost-vs-production/develop`, build/đo `my-agent:develop` (1.67 GB) vs `my-agent:advanced` (240 MB) & Compose Nginx, chạy `04-api-gateway` (401/200/JWT/429), chạy `05-scaling-reliability/production` (`--scale agent=3` + `test_stateless.py`) và điền số đo thật vào bài |
| **Part 7 (Benchmark & Observability)** | Hỗ trợ tìm 2 câu thiếu trong `eval_v2.json`, sửa lỗi startup `PYTHONUSERBASE` trong `production/Dockerfile`, tạo CI workflow `.github/workflows/eval.yml` và đối chiếu số liệu từ JSON/CSV vào `BENCHMARK_REPORT.md` | 2 entry bổ sung trong `KNOWLEDGE_BASE` (`utils/mock_llm.py`), bản vá `Dockerfile`, file `.github/workflows/eval.yml`, tổng hợp bảng biểu và phân tích trong `BENCHMARK_REPORT.md` | Tự chạy toàn bộ load test (`c=1,10,50,100` và `MOCK_SLOW_RATE=0,0.03,0.1`), eval `v1` (4.35%), `v2` (91.3%), `v2_fixed` (23/23 — 100%, 0 regression), chạy Locust headless `scale_1` & `scale_3`, kiểm tra Grafana, Jaeger (`trace_id`), kích hoạt 3 Prometheus alerts firing và chụp đủ 4 ảnh vào `screenshots/` |
