# Deployment Information

## Public URL
https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com

## Platform
- **Compute:** Render Web Service (Docker runtime, Root Directory: `06-lab-complete`, Region: Singapore)
- **State Store:** Render Key Value / Valkey 8 (Redis-compatible, Region: Singapore)

## Test Commands

### 1. Liveness Check (`/health`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com/health
# Expected: 200
```

```bash
curl -s https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com/health
# Expected: {"status":"ok","environment":"production"}
```

### 2. Readiness Check (`/ready`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com/ready
# Expected: 200
```

```bash
curl -s https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com/ready
# Expected: {"status":"ready","redis":"ok"}
```

### 3. API Test — Missing API Key (Authentication Required)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 401
```

### 4. API Test — Valid API Key
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com/ask \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: 200
```

Full JSON response test:
```bash
curl -X POST https://k5-l3a-day14-nguyentiencuong-2a202603425.onrender.com/ask \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is deployment?"}'
```

## Environment Variables Set
- `PORT` *(tự động inject bởi Render; Dockerfile lắng nghe `${PORT:-8000}`)*
- `ENVIRONMENT` (`production`)
- `LOG_LEVEL` (`INFO`)
- `AGENT_API_KEY` *(đặt bảo mật trên Render Dashboard, không commit vào code)*
- `REDIS_URL` *(Internal Key Value URL trỏ tới service Key Value cùng region Singapore)*
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `MONTHLY_BUDGET_USD` (`10.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running (/ready)](screenshots/running.png)
- [Test results (200/200/401/200)](screenshots/test.png)
