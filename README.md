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