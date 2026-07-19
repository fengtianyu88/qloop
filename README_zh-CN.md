# qloop

> **Quality + Loop** —— 面向代码交付的闭环质量管理平台，内置 LLM 自动评审、全链路审计日志与矩阵式组织模型。

> [English](README.md) | 简体中文
>
> 版本：1.3.0  ·  日期：2026-07-19

---

## 项目亮点

|  | 特性 | 给团队带来的价值 |
|---|---|---|
|  | **7 步交付闭环** | 从代码包上传 → 3 次自动 LLM 评审 → 人工审批 → 对外释放，每一步都有闸门、可追溯。 |
|  | **多模型 LLM 评审引擎** | 同时支持任意 OpenAI 兼容与 Anthropic 兼容推理 API：minimax-M3/M2.7、GLM-5.2、DeepSeek-V4-flash、通义千问、Ollama、vLLM、Claude。模型失败时自动回退。 |
|  | **默认全链路审计** | 所有特权操作（释放、角色变更、品牌名修改、LLM 配置）都会写入不可变审计日志，记录操作者 + 修改前后内容。 |
|  | **矩阵组织 × 项目角色** | 一条轴是 部门 → 科室 → 小组；另一条轴是 项目 → 版本 → 释放。同一个用户在不同项目里可以戴不同的帽子。 |
|  | **品牌名称可在线配置** | 超级管理员在「系统设置」页面修改品牌名，顶栏、侧边栏、登录页、浏览器标签、邮件签名实时生效，无需重新部署。 |
|  | **Linux 一键部署** | 单个 `deploy.sh` 完成 PostgreSQL / Redis / MinIO / systemd / Nginx 反向代理的安装、幂等迁移、超管账号创建。 |
|  | **多文件类型解析** | C、Python、MATLAB `.m`、Simulink 模型、`.mat` 数据文件、`.pth` 权重；Word `.docx` 与 Excel `.xlsx` 文档 —— 全部由系统内部解析，无需调用第三方文档解析 LLM API。 |

---

## 截图

| 登录页 | 首页仪表盘 |
|:---:|:---:|
| ![登录](docs/screenshots/01-login.png) | ![首页](docs/screenshots/02-home.png) |

| 项目列表 | 项目详情 |
|:---:|:---:|
| ![项目列表](docs/screenshots/03-projects.png) | ![项目详情](docs/screenshots/04-project-detail.png) |

| LLM 配置 | 系统设置（品牌名） |
|:---:|:---:|
| ![LLM 配置](docs/screenshots/05-llm-config.png) | ![系统设置](docs/screenshots/06-system-settings.png) |

| 审计日志 | 用户管理 |
|:---:|:---:|
| ![审计日志](docs/screenshots/07-audit-log.png) | ![用户管理](docs/screenshots/08-users.png) |

---

## 技术路线

```
┌──────────────────────────────────────────────────────────────┐
│  浏览器  (Vue 3 + Element Plus + Vite + Pinia + TypeScript)   │
└───────────────────────────────┬──────────────────────────────┘
                                │ HTTPS  /api  +  静态资源
┌───────────────────────────────▼──────────────────────────────┐
│  Nginx  (TLS 终结、反向代理、gzip)                            │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│  FastAPI  (异步、Pydantic 2、JWT 鉴权、基于角色的访问控制)    │
│  ├── 鉴权 / 用户 / 项目 / 释放 / 评审                          │
│  ├── 系统设置（单例品牌名）                                    │
│  ├── 审计服务（不可变操作日志）                                │
│  ├── LLM 评审器 (code_parser + doc_parser + client)            │
│  └── 存储 (MinIO 预签名 URL，7 天有效期)                      │
└─────┬──────────────────┬──────────────────┬──────────────────┘
      │                  │                  │
┌─────▼─────┐    ┌───────▼───────┐   ┌──────▼──────┐
│PostgreSQL │    │     Redis     │   │    MinIO    │
│  15+      │    │ 缓存 + 队列   │   │ 交付物存储  │
└───────────┘    └───────┬───────┘   └────────────┘
                         │
                 ┌───────▼───────┐
                 │     Celery    │  异步 LLM 评审
                 │    worker     │  + 邮件 + 通知
                 └───────────────┘
```

| 层级 | 技术栈 |
|---|---|
| 前端 | Vue 3 · Element Plus · Vite · TypeScript · Pinia · Vue Router |
| 后端 | FastAPI · SQLAlchemy 2.0 (async) · Pydantic 2 · python-jose (JWT) |
| 数据库 | PostgreSQL 15+ |
| 缓存 / 队列 | Redis 7+ |
| 对象存储 | MinIO（S3 兼容，预签名 URL） |
| 异步任务 | Celery |
| Web 服务器 | Nginx（TLS、gzip、反向代理） |
| 进程管理 | systemd |

### 值得说明的几个架构决策

- **幂等迁移** —— 每次部署都会执行 `Base.metadata.create_all`，只创建不存在的表，无需 Alembic。
- **单例设置表** —— `system_settings` 使用固定 UUID 主键，upsert 简单原子，品牌名修改即改即生效。
- **存储隔离** —— 释放物永远通过 302 跳转到短时效 MinIO 预签名 URL 直传，绝不经过 API 转发。
- **跨标签页品牌同步** —— 前端 Pinia `siteInfo` store 同时监听自定义事件与浏览器 `storage` 事件，一个标签页修改品牌名，其它已打开的标签页无需刷新即可同步。

---

## 部署方法

### Linux 一键安装

```bash
# 1. 克隆仓库
git clone https://github.com/fengtianyu88/qloop.git
cd qloop

# 2. 编辑 deploy.sh 顶部的配置区
#    （APP_NAME、数据库密码、MinIO 密钥、JWT 密钥、端口等）
sudo vim deploy.sh

# 3. 执行
chmod +x deploy.sh
sudo ./deploy.sh                  # 全新部署
sudo ./deploy.sh --restart        # 仅重启服务
sudo ./deploy.sh --status         # 查看服务状态
sudo ./deploy.sh --stop           # 停止所有服务
sudo ./deploy.sh --logs           # 查看后端日志
```

`deploy.sh` 会以幂等方式完成以下事项：

1. 安装系统依赖（`postgresql`、`redis`、`minio`、`nginx`、`python3-venv`）。
2. 创建数据库、MinIO 桶以及 `qloop-backend` 与 `qloop-celery` 的 systemd unit。
3. 构建 Vue 前端，把产物 rsync 到 `/var/www/qloop/`。
4. 执行 `Base.metadata.create_all`（只创建不存在的表）。
5. 创建默认超级管理员账号。
6. 使用内置 `deploy/nginx_qloop.conf` 配置 Nginx 并 reload。
7. enable 并 start 所有服务。

### 默认超级管理员

首次部署后使用以下账号登录：

```
用户名：admin
密码：  admin@2026
```

**请登录后立即在用户中心修改密码。**

### 手动 / 非 Linux 环境

若无法运行 `deploy.sh`（例如 Windows 开发机），请按相同的逻辑步骤手动操作 —— [部署指南](docs/DEPLOYMENT.md) 有逐步说明。完整依赖清单：

- PostgreSQL 15+
- Redis 7+
- MinIO（或任意 S3 兼容存储）
- Python 3.10+（后端）
- Node.js 18+（前端构建）
- Nginx（或任意反向代理）

---

## 开放协议

qloop 围绕开放、与厂商无关的协议构建，任意一层都可以替换，无需改动应用代码。

### LLM 协议

[`backend/app/models/review.py`](backend/app/models/review.py) 中的 `LLMProtocol` 枚举与 [`backend/app/llm/client.py`](backend/app/llm/client.py) 的双路径客户端同时实现了两大主流推理 API：

| 协议 | 端点形态 | 鉴权头 | 已验证的提供方 |
|---|---|---|---|
| `OPENAI` | `POST {base}/chat/completions` | `Authorization: Bearer <key>` | minimax-M3、minimax-M2.7、GLM-5.2、DeepSeek-V4-flash、通义千问、vLLM、TGI、Ollama、OpenAI |
| `ANTHROPIC` | `POST {base}/v1/messages` | `x-api-key: <key>` + `anthropic-version: 2023-06-01` | Claude 3.5 / 4 系列 |

新增一个模型只需往 `llm_models` 表插入一条记录（或在「LLM 配置」页面提交一个表单），无需改任何代码。

### 存储协议

MinIO 完全 S3 兼容。任意 S3 客户端或网关（AWS S3、Ceph、SeaweedFS、Rclone）都能直接使用配置好的密钥读写 `qloop` 桶。

### 鉴权协议

无状态 JWT Bearer Token（`Authorization: Bearer <token>`），默认 8 小时有效期，可在用户中心刷新。不依赖有状态会话存储，后端可以水平扩展而无需粘性会话。

### 反向代理契约

前端只与两个明确的 URL 空间通信：
- `/api/**`  —— 后端 REST API（反代到 FastAPI `:8000`）
- `/**`（其余所有）—— 静态前端资源

这意味着你可以把 qloop 放在任意 CDN、TLS 终结器或负载均衡器后面，而无需改动应用层。

---

## 目录结构

```
qloop/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI 路由（auth、users、projects、releases、reviews、system_settings 等）
│   │   ├── models/         # SQLAlchemy 2.0 ORM 模型
│   │   ├── schemas/        # Pydantic v2 请求/响应模型
│   │   ├── services/       # 业务逻辑层（audit、system_settings 等）
│   │   ├── llm/            # LLM 评审引擎（code_parser、doc_parser、client、reviewer、prompts）
│   │   ├── tasks/          # Celery 异步任务
│   │   ├── storage/        # MinIO 客户端 + 预签名 URL 工具
│   │   ├── utils/
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/            # Axios 请求模块
│   │   ├── components/     # Layout.vue
│   │   ├── router/
│   │   ├── stores/         # Pinia（auth、siteInfo 等）
│   │   ├── types/
│   │   ├── views/          # Login、Home、ProjectList、ProjectDetail、ReleaseDetail、
│   │   │                   # LlmConfig、SystemSettings、AuditLog、UserManagement 等
│   │   ├── App.vue
│   │   └── main.ts
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── deploy/
│   └── nginx_qloop.conf
├── docs/
│   ├── DEPLOYMENT.md
│   └── screenshots/        # 本 README 引用的截图
├── deploy.sh               # Linux 一键安装脚本
└── LICENSE
```

---

## 许可证

[MIT](LICENSE) —— 随便 fork、随便上线、随便改成你自己的品牌名（品牌名现在可以从 UI 配置了，这就是它的意义）。
