# collab-ai-realtime

## Backend（FastAPI + PostgreSQL）

### 依赖安装

```bash
python -m pip install -r backend/requirements.txt
```

### 本地调试（SSH 隧道连云端 PostgreSQL）

- **先开隧道**（窗口别关；推荐用本地 15432，避免你机器上 5432 被占用）：

```bash
ssh -N -L 15432:127.0.0.1:5432 root@43.163.85.196
```

- **本地密码配置**（不进 git）：创建 `backend/.env.local`

```bash
DB_PASSWORD=StrongPass123
DB_PORT=15432
```

- **启动后端**（任选其一）：

```bash
uvicorn app.main:app --reload --port 8000
```

或在仓库根目录：

```bash
uvicorn backend.app.main:app --reload --port 8000
```

- **验证数据库连通性**：访问 `GET /db/ping`，返回 `{"ok": 1}` 即成功。

### 线上部署（应用与数据库同机）

- **更规范的做法**：在服务器创建 `/etc/collab-ai-realtime.env`（不进 git），内容例如：

```bash
DB_PASSWORD=StrongPass123
```

然后用 systemd / Docker / 启动脚本加载该环境变量文件即可（代码默认会尝试读取它）。

## Web 前端（Vue 3 + Vite + Element Plus）

### 本地开发启动

```bash
cd web
npm install
npm run dev
```

- 默认开发地址为 `http://localhost:5173`（Vite 默认端口）。
- 后端接口基地址在 `web/src/api/http.ts` 中配置，当前默认指向 `http://localhost:8000`。
- 访问 `http://localhost:5173/admin/login`，输入后端配置的 `ADMIN_API_KEY`（例如默认的 `TestAdminKey123`），即可进入管理后台。

### 构建与部署

```bash
cd web
npm install
npm run build
```

- 构建产物会生成到 `web/dist` 目录。
- 可以将 `dist` 目录部署到任意静态资源服务器（如 Nginx、CDN 或对象存储静态托管）：
  - 前端与后端可以分别部署，只要前端访问的后端地址（`http.ts` 中的 `baseURL`）可达即可。
  - 若前后端同域部署，可将 `dist` 目录挂载到 Nginx 的根目录，后端通过反向代理暴露 `/api/**`。
- 如需在不同环境使用不同后端地址，可后续改造为读取环境变量或构建时注入配置。