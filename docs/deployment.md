# 部署说明

## 本地开发

后端默认监听 `127.0.0.1:8010`，前端默认监听 `127.0.0.1:5190`。根目录 `.env` 由后端读取，前端变量放在 `frontend-vue/.env.local`。

后端：

```powershell
Copy-Item .env.example .env
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

前端：

```powershell
cd frontend-vue
Copy-Item .env.example .env.local
npm ci
npm run dev
```

## 环境变量

### 服务

- `HOST`：后端监听地址，默认 `127.0.0.1`。
- `PORT`：后端端口，默认 `8010`。
- `RELOAD`：是否启用 Uvicorn 自动重载，默认 `false`。
- `CORS_ORIGINS`：逗号分隔的允许来源。

### LLM

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL_ID`
- `LLM_TIMEOUT`
- `LLM_RESPONSE_FORMAT`

### 外部数据

- `AMAP_WEB_SERVICE_KEY`：后端 POI、路线和地理编码。
- `AMAP_WEB_JS_KEY`：浏览器交互地图。
- `AMAP_SECURITY_JS_CODE`：高德 JS API 安全密钥，可选。
- `AMAP_SIG_PRIVATE_KEY`：高德 Web 服务数字签名私钥，可选。
- `OPENWEATHER_API_KEY`
- `OPENWEATHER_API_HOST`
- `TAVILY_API_KEY`
- `TAVILY_API_HOST`
- `TAVILY_INCLUDE_DOMAINS`

### 前端

- `VITE_API_BASE_URL`：后端公开地址。
- `VITE_DEV_HOST` / `VITE_DEV_PORT`：Vite 开发服务器。
- `VITE_PREVIEW_HOST` / `VITE_PREVIEW_PORT`：Vite 预览服务器。

## 生产部署注意事项

当前版本以本地演示为目标。对公网部署前至少需要：

1. 将 `CORS_ORIGINS` 设置为实际前端域名，不使用通配符。
2. 使用反向代理提供 HTTPS，并限制 `/api/settings` 和 `/api/memory`。
3. 将任务状态、缓存和用户记忆迁移到 Redis/数据库。
4. 为 API 增加认证、速率限制、请求体大小限制和审计日志。
5. 在高德控制台设置正确的域名/IP 白名单和配额告警。
6. 使用部署平台的 Secret 管理器注入密钥，不上传 `.env`。
7. 将 `frontend-vue` 执行 `npm run build` 后产生的 `dist/` 交给静态服务器发布。

项目当前未提供 Dockerfile 或 Compose 文件，避免在没有生产状态存储和认证方案前给出误导性的“一键生产部署”。
