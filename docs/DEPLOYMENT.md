# qloop — 部署指南

> 版本：1.0.0  日期：2026-07-16

---

## 目录

1. [系统架构概览](#1-系统架构概览)
2. [环境要求](#2-环境要求)
3. [配置项清单](#3-配置项清单)
4. [Linux 部署](#4-linux-部署)
5. [Windows 部署](#5-windows-部署)
6. [Nginx 反向代理（可选）](#6-nginx-反向代理可选)
7. [系统初始化](#7-系统初始化)
8. [常见问题](#8-常见问题)

---

## 1. 系统架构概览

```
┌─────────────┐   ┌──────────────┐   ┌─────────────┐
│   前端 Vue   │──▶│  后端 FastAPI │──▶│ PostgreSQL  │
│  (5173端口)  │   │  (8000端口)   │   │  (5432端口)  │
└─────────────┘   └──────┬───────┘   └─────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌─────────────┐ ┌───────────┐ ┌───────────┐
   │    MinIO    │ │   Redis   │ │  Celery   │
   │ (9000端口)  │ │(6379端口) │ │  Worker   │
   │  文件存储    │ │ 任务队列   │ │ 异步任务   │
   └─────────────┘ └───────────┘ └───────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │  SMTP 邮件  │
                  │  服务       │
                  └─────────────┘
```

**需要部署的组件：**

| 组件 | 用途 | 默认端口 |
|------|------|---------|
| PostgreSQL 15+ | 主数据库 | 5432 |
| Redis 7+ | Celery 消息队列和缓存 | 6379 |
| MinIO | 文件存储（代码包/报告） | 9000 |
| Python 3.11+ | 后端运行环境 | — |
| Node.js 18+ | 前端构建环境 | — |
| Celery Worker | 异步任务（LLM评审/邮件） | — |
| SMTP 服务 | 邮件发送 | 25 |

---

## 2. 环境要求

### 后端

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.11 | 推荐 3.12 |
| PostgreSQL | 15 | 推荐 16 |
| Redis | 7.0 | — |
| MinIO | 最新稳定版 | 或兼容 S3 的对象存储 |

### 前端

| 依赖 | 最低版本 |
|------|---------|
| Node.js | 18 LTS |
| npm | 9+ |

### 内网大模型 API

系统需要对接已有的内网大模型 API（OpenAI 兼容接口格式 `/v1/chat/completions`）。在系统启动后由超级管理员在「LLM 配置」页面中填入。

---

## 3. 配置项清单

### 3.1 后端配置（`backend/.env`）

在 `backend/` 目录下创建 `.env` 文件，复制 `.env.example` 并修改以下配置：

```ini
# ═══════════════════════════════════════════════════
# 应用配置
# ═══════════════════════════════════════════════════

# JWT 密钥（必须修改！建议使用 openssl rand -hex 32 生成）
SECRET_KEY=change-me-in-production

# JWT Token 过期时间（分钟），默认 480 分钟（8小时）
ACCESS_TOKEN_EXPIRE_MINUTES=480

# ═══════════════════════════════════════════════════
# PostgreSQL 数据库
# ═══════════════════════════════════════════════════

# 格式: postgresql+asyncpg://用户名:密码@主机:端口/数据库名
DATABASE_URL=postgresql+asyncpg://qloop:YourPassword123@localhost:5432/qloop

# ═══════════════════════════════════════════════════
# Redis
# ═══════════════════════════════════════════════════

# 格式: redis://[:密码@]主机:端口/数据库编号
REDIS_URL=redis://:YourRedisPassword@localhost:6379/0

# ═══════════════════════════════════════════════════
# MinIO 对象存储
# ═══════════════════════════════════════════════════

# MinIO 服务地址（不含 http://）
MINIO_ENDPOINT=localhost:9000

# MinIO 访问密钥
MINIO_ACCESS_KEY=minioadmin

# MinIO 秘密密钥
MINIO_SECRET_KEY=YourMinioSecretKey

# 存储桶名称（不存在会自动创建）
MINIO_BUCKET=qloop

# 是否启用 HTTPS（内网通常为 false）
MINIO_SECURE=false

# ═══════════════════════════════════════════════════
# SMTP 邮件服务
# ═══════════════════════════════════════════════════

# SMTP 服务器地址
SMTP_HOST=localhost

# SMTP 端口（25=明文, 465=SSL, 587=STARTTLS）
SMTP_PORT=25

# SMTP 用户名（如无需认证则留空）
SMTP_USER=

# SMTP 密码（如无需认证则留空）
SMTP_PASSWORD=

# 发件人邮箱地址
SMTP_FROM=qloop@your-company.com

# ═══════════════════════════════════════════════════
# LLM 大模型（在系统页面中配置，此处仅设超时）
# ═══════════════════════════════════════════════════

# LLM 调用超时时间（秒）
LLM_TIMEOUT=300

# LLM 最大重试次数
LLM_MAX_RETRIES=3
```

### 3.2 前端配置（`frontend/vite.config.ts`）

前端构建时需要配置后端 API 地址。开发环境通过 Vite proxy 代理，生产环境通过 Nginx 反向代理。

**开发环境**（默认已配置）：
```typescript
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',  // ← 改为后端实际地址
      changeOrigin: true,
    },
  },
}
```

**生产环境构建**：构建为静态文件，由 Nginx 托管，`/api` 路径反向代理到后端。

### 3.3 配置项汇总表

| 配置项 | 位置 | 必填 | 示例值 | 说明 |
|--------|------|:----:|--------|------|
| `SECRET_KEY` | .env | 是 | `a1b2c3...` | JWT 密钥，必须修改 |
| `DATABASE_URL` | .env | 是 | `postgresql+asyncpg://qloop:pwd@host:5432/qloop` | 数据库连接串 |
| `REDIS_URL` | .env | 是 | `redis://:pwd@host:6379/0` | Redis 连接串 |
| `MINIO_ENDPOINT` | .env | 是 | `host:9000` | MinIO 地址 |
| `MINIO_ACCESS_KEY` | .env | 是 | `minioadmin` | MinIO 访问密钥 |
| `MINIO_SECRET_KEY` | .env | 是 | `minioadmin` | MinIO 秘密密钥 |
| `MINIO_BUCKET` | .env | 否 | `qloop` | 存储桶名 |
| `MINIO_SECURE` | .env | 否 | `false` | 是否 HTTPS |
| `SMTP_HOST` | .env | 是 | `smtp.company.com` | SMTP 服务器 |
| `SMTP_PORT` | .env | 是 | `25` | SMTP 端口 |
| `SMTP_USER` | .env | 否 | `sender@company.com` | SMTP 用户名 |
| `SMTP_PASSWORD` | .env | 否 | `password` | SMTP 密码 |
| `SMTP_FROM` | .env | 是 | `qloop@company.com` | 发件人地址 |
| `LLM_TIMEOUT` | .env | 否 | `300` | LLM 超时秒数 |
| LLM API 地址 | 系统页面 | 是 | `http://llm-host:8080/v1` | 超管在LLM配置页填写 |
| LLM API Key | 系统页面 | 是 | `sk-xxx` | 超管在LLM配置页填写 |
| LLM 模型名 | 系统页面 | 是 | `qwen-72b` | 超管在LLM配置页填写 |

### 3.4 LLM 模型种子配置（deploy.sh 一键部署）

使用 `deploy.sh` 一键部署时，可在脚本「配置区」预填 4 个 LLM 模型的 API Key，部署时自动注册到数据库。留空 API_KEY 的模型会被跳过（幂等，重复部署不会重复创建）。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MINIMAX_M3_API_BASE` | `https://api.minimaxi.com/v1` | MiniMax M3 API 地址 |
| `LLM_MINIMAX_M3_API_KEY` | （空） | 填入后自动注册 minimax-M3 |
| `LLM_MINIMAX_M3_MODEL` | `MiniMax-M3` | 模型名 |
| `LLM_MINIMAX_M3_PRIORITY` | `10` | 优先级（数字越小越高） |
| `LLM_MINIMAX_M27_API_BASE` | `https://api.minimaxi.com/v1` | MiniMax M2.7 API 地址 |
| `LLM_MINIMAX_M27_API_KEY` | （空） | 填入后自动注册 minimax-M2.7 |
| `LLM_MINIMAX_M27_MODEL` | `MiniMax-M2.7` | 模型名 |
| `LLM_MINIMAX_M27_PRIORITY` | `20` | 优先级 |
| `LLM_GLM_API_BASE` | `https://open.bigmodel.cn/api/paas/v4` | 智谱 GLM API 地址 |
| `LLM_GLM_API_KEY` | （空） | 填入后自动注册 GLM-5.2 |
| `LLM_GLM_MODEL` | `glm-5.2` | 模型名 |
| `LLM_GLM_PRIORITY` | `30` | 优先级 |
| `LLM_DEEPSEEK_API_BASE` | `https://api.deepseek.com/v1` | DeepSeek API 地址 |
| `LLM_DEEPSEEK_API_KEY` | （空） | 填入后自动注册 Deepseek-V4-flash |
| `LLM_DEEPSEEK_MODEL` | `deepseek-v4-flash` | 模型名 |
| `LLM_DEEPSEEK_PRIORITY` | `40` | 优先级 |

所有模型均使用 OpenAI 兼容接口。如需添加其他模型（通义千问、Ollama、vLLM 等），部署后可在「LLM 配置」页面手动添加。

### 3.5 后端监听地址（`BACKEND_HOST`）

`deploy.sh` 中 `BACKEND_HOST` 控制 Nginx 反向代理的目标地址：

| 场景 | `BACKEND_HOST` 值 | 说明 |
|------|-------------------|------|
| 普通 Linux 服务器 | `127.0.0.1`（默认） | 后端与 Nginx 在同一台机器 |
| WSL2 mirrored 网络模式 | `10.255.255.254` | 当 `127.0.0.1:8000` 返回 Connection refused 时改用此值 |

---

## 4. Linux 部署

### 4.1 安装系统依赖

**Ubuntu / Debian：**
```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip nodejs npm postgresql redis-server
```

**CentOS / RHEL：**
```bash
sudo dnf install -y python3.12 python3-pip nodejs npm postgresql-server redis
sudo postgresql-setup --initdb
```

### 4.2 安装 MinIO

```bash
# 下载 MinIO
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
sudo mv minio /usr/local/bin/

# 创建数据目录
sudo mkdir -p /data/minio
sudo chown $USER:$USER /data/minio

# 启动 MinIO（前台运行，测试用）
minio server /data/minio --console-address ":9001"

# 生产环境用 systemd 管理
sudo tee /etc/systemd/system/minio.service > /dev/null <<'EOF'
[Unit]
Description=MinIO Object Storage
After=network.target

[Service]
Type=simple
User=minio-user
ExecStart=/usr/local/bin/minio server /data/minio --console-address ":9001"
Environment="MINIO_ROOT_USER=minioadmin"
Environment="MINIO_ROOT_PASSWORD=YourMinioSecretKey"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo useradd -r minio-user -s /sbin/nologin
sudo chown -R minio-user:minio-user /data/minio
sudo systemctl daemon-reload
sudo systemctl enable minio
sudo systemctl start minio
```

### 4.3 配置 PostgreSQL

```bash
# 启动 PostgreSQL
sudo systemctl enable postgresql
sudo systemctl start postgresql

# 创建数据库和用户
sudo -u postgres psql <<'EOF'
CREATE USER qloop WITH PASSWORD 'YourPassword123';
CREATE DATABASE qloop OWNER qloop;
GRANT ALL PRIVILEGES ON DATABASE qloop TO qloop;
\c qloop
GRANT ALL ON SCHEMA public TO qloop;
EOF
```

### 4.4 配置 Redis

```bash
# 启动 Redis
sudo systemctl enable redis-server
sudo systemctl start redis-server

# 如需设置密码，编辑 /etc/redis/redis.conf
# 取消注释 requirepass 并设置密码：
# requirepass YourRedisPassword
# 然后重启: sudo systemctl restart redis-server
```

### 4.5 部署后端

```bash
# 解压项目
unzip qloop-delivery-system.zip -d /opt/qloop
cd /opt/qloop/backend

# 创建 Python 虚拟环境
python3.12 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建 .env 配置文件
cp .env.example .env
nano .env
# → 按照第 3 节的配置项清单填写

# 初始化数据库表（使用 SQLAlchemy 自动建表）
python -c "
import asyncio
from app.database import engine, Base
from app.models import *

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('数据库表创建成功')

asyncio.run(init())
"

# 创建超级管理员账号
python -c "
import asyncio
from app.database import async_session
from app.models.user import User, SystemRole
from app.utils.security import hash_password

async def create_admin():
    async with async_session() as db:
        admin = User(
            username='admin',
            email='admin@company.com',
            full_name='超级管理员',
            hashed_password=hash_password('admin123'),
            system_role=SystemRole.SUPER_ADMIN,
        )
        db.add(admin)
        await db.commit()
        print('超级管理员创建成功: admin / admin123')

asyncio.run(create_admin())
"

# 启动后端服务（开发模式）
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 生产环境用 systemd 管理
sudo tee /etc/systemd/system/qloop-backend.service > /dev/null <<'EOF'
[Unit]
Description=qloop Backend API
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/qloop/backend
ExecStart=/opt/qloop/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5
EnvironmentFile=/opt/qloop/backend/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable qloop-backend
sudo systemctl start qloop-backend
```

### 4.6 启动 Celery Worker

```bash
cd /opt/qloop/backend
source venv/bin/activate

# 前台启动（测试用）
celery -A app.tasks.celery_app worker --loglevel=info

# 生产环境用 systemd 管理
sudo tee /etc/systemd/system/qloop-celery.service > /dev/null <<'EOF'
[Unit]
Description=qloop Celery Worker
After=network.target redis-server.service qloop-backend.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/qloop/backend
ExecStart=/opt/qloop/backend/venv/bin/celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
Restart=always
RestartSec=5
EnvironmentFile=/opt/qloop/backend/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable qloop-celery
sudo systemctl start qloop-celery
```

### 4.7 构建并部署前端

```bash
cd /opt/qloop/frontend

# 安装依赖
npm install

# 构建生产版本
npm run build

# 将构建产物复制到 Web 目录
sudo mkdir -p /var/www/qloop
sudo cp -r dist/* /var/www/qloop/
```

### 4.8 启动 SMTP 邮件服务

```bash
# 安装 Postfix
sudo apt install -y postfix
# 安装时选择 "Internet Site"，填入域名

# 或使用现有内网邮件服务器，在 .env 中配置 SMTP_HOST 即可
```

### 4.9 验证服务

```bash
# 检查后端
curl http://localhost:8000/api/health
# 预期: {"status":"healthy","app":"qloop ...","version":"1.0.0"}

# 检查 Redis
redis-cli ping
# 预期: PONG

# 检查 Celery
celery -A app.tasks.celery_app inspect ping
# 预期: {"pong": true}

# 浏览器访问前端
# http://localhost (通过 Nginx) 或 http://localhost:5173 (开发模式)
```

---

## 5. Windows 部署

### 5.1 安装系统依赖

**安装 Python 3.12：**
1. 访问 https://www.python.org/downloads/ 下载 Python 3.12
2. 安装时勾选 "Add Python to PATH"
3. 验证：`python --version`

**安装 Node.js 18+：**
1. 访问 https://nodejs.org/ 下载 LTS 版本
2. 安装后验证：`node --version`

### 5.2 安装 PostgreSQL

1. 访问 https://www.postgresql.org/download/windows/ 下载安装包
2. 安装时设置超级用户密码
3. 安装完成后打开 pgAdmin 或使用命令行：

```powershell
# 使用 psql 创建数据库和用户
psql -U postgres
```

```sql
CREATE USER qloop WITH PASSWORD 'YourPassword123';
CREATE DATABASE qloop OWNER qloop;
GRANT ALL PRIVILEGES ON DATABASE qloop TO qloop;
\c qloop
GRANT ALL ON SCHEMA public TO qloop;
\q
```

### 5.3 安装 Redis

Windows 上推荐使用以下方式之一：

**方式一：使用 Memurai（Redis 兼容的 Windows 版）**
1. 访问 https://www.memurai.com/ 下载安装
2. 安装后作为 Windows 服务自动运行

**方式二：使用 WSL 中的 Redis**
```powershell
# 在 WSL 中安装 Redis
wsl --install -d Ubuntu
# 进入 WSL 后:
sudo apt update && sudo apt install -y redis-server
sudo service redis-server start
```

**方式三：使用 Docker**
```powershell
docker run -d --name redis -p 6379:6379 redis:7
```

### 5.4 安装 MinIO

1. 访问 https://min.io/download#/windows 下载 `minio.exe`
2. 创建数据目录 `C:\minio\data`
3. 启动：

```powershell
# 命令行启动
minio.exe server C:\minio\data --console-address ":9001"

# 或设置为 Windows 服务（推荐使用 NSSM）
# 下载 NSSM: https://nssm.cc/
nssm install MinIO "C:\minio\minio.exe" "server" "C:\minio\data" "--console-address" ":9001"
nssm set MinIO AppEnvironmentExtra MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=YourMinioSecretKey
nssm start MinIO
```

### 5.5 部署后端

```powershell
# 解压项目
Expand-Archive qloop-delivery-system.zip -DestinationPath C:\qloop
cd C:\qloop\backend

# 创建 Python 虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 创建 .env 配置文件
copy .env.example .env
notepad .env
# → 按照第 3 节的配置项清单填写

# 初始化数据库表
python -c "import asyncio; from app.database import engine, Base; from app.models import *; asyncio.run(lambda: engine.begin().__aenter__().run_sync(Base.metadata.create_all))(); print('OK')"

# 更简单的方式 - 创建初始化脚本
python -c "
import asyncio
from app.database import engine, Base
from app.models import *
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('数据库表创建成功')
asyncio.run(init())
"

# 创建超级管理员账号
python -c "
import asyncio
from app.database import async_session
from app.models.user import User, SystemRole
from app.utils.security import hash_password
async def create_admin():
    async with async_session() as db:
        admin = User(
            username='admin',
            email='admin@company.com',
            full_name='超级管理员',
            hashed_password=hash_password('admin123'),
            system_role=SystemRole.SUPER_ADMIN,
        )
        db.add(admin)
        await db.commit()
        print('超级管理员创建成功: admin / admin123')
asyncio.run(create_admin())
"

# 启动后端服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**注册为 Windows 服务（使用 NSSM）：**
```powershell
# 下载 NSSM: https://nssm.cc/
nssm install qloop-Backend "C:\qloop\backend\venv\Scripts\uvicorn.exe" "app.main:app" "--host" "0.0.0.0" "--port" "8000"
nssm set qloop-Backend AppDirectory "C:\qloop\backend"
nssm set qloop-Backend AppEnvironmentExtra PYTHONUNBUFFERED=1
nssm start qloop-Backend
```

### 5.6 启动 Celery Worker

```powershell
cd C:\qloop\backend
.\venv\Scripts\Activate.ps1

# 前台启动
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo

# 注册为 Windows 服务
nssm install qloop-Celery "C:\qloop\backend\venv\Scripts\celery.exe" "-A" "app.tasks.celery_app" "worker" "--loglevel=info" "--pool=solo"
nssm set qloop-Celery AppDirectory "C:\qloop\backend"
nssm start qloop-Celery
```

> **注意**：Windows 上 Celery 必须使用 `--pool=solo` 参数，因为 Windows 不支持 Celery 的默认 prefork 进程池。

### 5.7 构建并部署前端

```powershell
cd C:\qloop\frontend

# 安装依赖
npm install

# 构建生产版本
npm run build

# 构建产物在 dist\ 目录
# 将 dist\ 目录内容复制到 IIS 或 Nginx 的网站目录
```

### 5.8 启动 SMTP 邮件服务

Windows 上推荐使用已有的内网邮件服务器，在 `.env` 中配置 `SMTP_HOST` 即可。

如需本地安装，可使用 hMailServer：
1. 访问 https://www.hmailserver.com/ 下载安装
2. 配置 SMTP 服务

---

## 6. Nginx 反向代理（可选）

生产环境推荐使用 Nginx 统一入口，前端和 API 通过同一端口访问。

### 6.1 安装 Nginx

**Linux：**
```bash
sudo apt install -y nginx
```

**Windows：**
1. 访问 https://nginx.org/en/download.html 下载
2. 解压到 `C:\nginx`

### 6.2 配置 Nginx

**Linux** 编辑 `/etc/nginx/sites-available/qloop`：
```nginx
server {
    listen 80;
    server_name your-domain-or-ip;

    # 前端静态文件
    location / {
        root /var/www/qloop;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理到后端
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 文件上传大小限制（代码包可能较大）
        client_max_body_size 500M;
        proxy_read_timeout 600s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/qloop /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

**Windows** 编辑 `C:\nginx\conf\nginx.conf`，在 `http` 块内添加：
```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        root C:/qloop/frontend/dist;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 500M;
        proxy_read_timeout 600s;
    }
}
```

```powershell
cd C:\nginx
nginx.exe -t
nginx.exe -s reload
```

### 6.3 修改后端 CORS 配置

如果使用 Nginx 统一入口，修改 `backend/app/main.py` 中的 CORS 配置：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://your-domain-or-ip"],  # ← 改为实际访问地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 7. 系统初始化

### 7.1 首次登录

1. 浏览器访问系统地址（如 `http://localhost` 或 `http://localhost:5173`）
2. 使用超级管理员账号登录：
   - 用户名：`admin`
   - 密码：`admin123`
3. **登录后请立即修改密码**（在「个人信息」页面）

### 7.2 配置 LLM 大模型

**方式一：deploy.sh 预置种子（推荐）**

在 `deploy.sh` 配置区填入 4 个模型（minimax-M3 / minimax-M2.7 / GLM-5.2 / Deepseek-V4-flash）的 API Key，部署时自动注册（详见 3.4 节）。留空的模型跳过，不影响部署。

**方式二：页面手动添加**

1. 以超级管理员登录
2. 进入「LLM 配置」页面
3. 添加 LLM 模型：
   - 模型名称：如「通义千问72B」
   - API 地址：如 `http://llm-host:8080/v1`
   - API Key：如 `sk-xxx`
   - 模型名称：如 `qwen-72b`
   - 优先级：0（数字越小优先级越高）
4. 配置评审规则：
   - 选择评审类型（代码评审 / 测试报告评审 / 专家报告评审）
   - 选择主模型和备用模型
   - 设置通过阈值（默认 80 分）
   - 可自定义 Prompt 模板

### 7.3 创建组织结构

1. 进入「组织管理」页面（超管权限）
2. 创建过程域层级：部门 → 科室 → 小组
3. 为管理员配置管理范围

### 7.4 添加用户

1. 进入「用户管理」页面
2. 添加用户并分配系统级角色
3. 或告知用户通过登录页的「注册新账号」自行注册（注册后默认为访客角色，需管理员提升权限）

### 7.5 创建项目并开始使用

1. 进入「项目管理」，创建项目
2. 添加项目成员并分配项目级角色（开发人员/测试人员/外部技术专家）
3. 创建版本，指定开发/测试/专家
4. 开发人员上传代码包，系统自动触发 LLM 评审
5. 按 7 步流程完成释放

---

## 8. 常见问题

### Q: 后端启动报数据库连接失败

**A:** 检查 `.env` 中 `DATABASE_URL` 格式是否正确，确认 PostgreSQL 服务已启动，确认用户有数据库访问权限。

### Q: Celery Worker 启动后任务不执行

**A:** 检查 Redis 是否可连接（`redis-cli ping`），确认 `.env` 中 `REDIS_URL` 正确，确认 Celery Worker 进程正在运行。

### Q: 文件上传失败

**A:** 检查 MinIO 服务是否运行，确认 `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` 正确，确认存储桶已创建或可自动创建。

### Q: LLM 评审一直失败

**A:** 在「LLM 配置」页面检查模型配置是否正确，确认内网大模型 API 地址可达，确认 API Key 有效。可查看后端日志获取详细错误信息。

### Q: 邮件发送失败

**A:** 检查 `.env` 中 SMTP 配置，确认 SMTP 服务器地址和端口正确，确认认证信息有效。查看 Celery Worker 日志中的邮件发送错误。

### Q: Windows 上 Celery 报错

**A:** Windows 必须使用 `--pool=solo` 参数启动 Celery，不支持默认的 prefork 模式。

### Q: 前端页面空白

**A:** 检查浏览器控制台错误，确认前端构建成功，确认 Nginx 配置中 `try_files` 正确指向 `index.html`。

### Q: 数据库迁移

**A:** 首次部署使用以下命令创建表：
```bash
cd backend
source venv/bin/activate  # Windows: .\venv\Scripts\Activate.ps1
python -c "
import asyncio
from app.database import engine, Base
from app.models import *
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('OK')
asyncio.run(init())
"
```

---

## 附录：服务端口汇总

| 服务 | 默认端口 | 访问地址 |
|------|---------|---------|
| 后端 API | 8000 | `http://localhost:8000` |
| 前端（开发） | 5173 | `http://localhost:5173` |
| 前端（生产） | 80 | `http://localhost`（通过 Nginx） |
| PostgreSQL | 5432 | — |
| Redis | 6379 | — |
| MinIO API | 9000 | — |
| MinIO Console | 9001 | `http://localhost:9001` |
