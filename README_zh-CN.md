# qloop

> [English](README.md) | 简体中文

> 版本：1.3.0  日期：2026-07-20

## 品牌释义

**qloop** = **Q**uality + **Loop**。把「质量」和「闭环」融为一体，暗含测试在开发中不断循环、完善、不留漏洞。5 个字母，极度简短，抽象现代。

## 项目简介

qloop 是一套质量闭环管理系统，用于管理团队中代码开发、测试、评审与对外交付的全流程。系统支持代码包管理、评审报告管理、测试报告管理、LLM 自动化评审、用户权限管理、项目全生命周期管理等功能。

## 目录结构

```
qloop/
├── backend/                 # 后端 FastAPI 应用
│   ├── app/
│   │   ├── api/             # API 路由（auth, users, projects, releases, reviews 等）
│   │   ├── models/          # 数据库模型（User, Project, Release, LLMReview 等）
│   │   ├── schemas/         # Pydantic 请求/响应模型
│   │   ├── services/        # 业务逻辑层
│   │   ├── llm/             # LLM 评审引擎（代码解析、文档解析、LLM 调用）
│   │   ├── tasks/           # Celery 异步任务（LLM 评审、邮件、通知）
│   │   ├── storage/         # MinIO 文件存储
│   │   ├── utils/           # 工具函数（安全、分页）
│   │   ├── config.py        # 配置管理
│   │   ├── database.py      # 数据库连接
│   │   └── main.py          # 应用入口
│   ├── .env.example         # 环境变量模板
│   └── requirements.txt     # Python 依赖
├── frontend/                # 前端 Vue 3 应用
│   ├── src/
│   │   ├── api/             # API 请求模块
│   │   ├── components/      # 公共组件（Layout）
│   │   ├── router/          # 路由配置
│   │   ├── stores/          # Pinia 状态管理
│   │   ├── types/           # TypeScript 类型定义
│   │   ├── views/           # 页面组件
│   │   ├── App.vue          # 根组件
│   │   └── main.ts          # 应用入口
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
└── docs/                    # 文档
    ├── DEPLOYMENT.md                     # 部署指南（Linux + Windows）
    └── superpowers/
        ├── specs/                        # 设计文档
        │   └── 2026-07-16-qloop-design.md
        └── plans/                        # 实施计划
            └── 2026-07-16-qloop.md
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Element Plus + Vite + TypeScript + Pinia |
| 后端 | FastAPI + SQLAlchemy 2.0 (async) + Pydantic 2 |
| 数据库 | PostgreSQL 15+ |
| 缓存/队列 | Redis 7+ |
| 对象存储 | MinIO |
| 异步任务 | Celery |
| 认证 | JWT (python-jose) |

## 快速开始

请阅读 **[部署指南](docs/DEPLOYMENT.md)** 了解完整的部署步骤。

### 简要步骤

1. **安装依赖服务**：PostgreSQL、Redis、MinIO
2. **配置后端**：复制 `backend/.env.example` 为 `backend/.env`，填写数据库地址、账号密码、MinIO 配置等
3. **安装 Python 依赖**：`pip install -r backend/requirements.txt`
4. **初始化数据库**：运行建表脚本（见部署指南）
5. **创建超级管理员**：运行初始化脚本（见部署指南）
6. **启动后端**：`uvicorn app.main:app --host 0.0.0.0 --port 8000`
7. **启动 Celery Worker**：`celery -A app.tasks.celery_app worker --loglevel=info`
8. **构建前端**：`cd frontend && npm install && npm run build`
9. **配置 Nginx**：指向前端构建产物，反向代理 `/api` 到后端

## 核心功能

- **项目管理**：项目 → 版本 → 释放 三层结构
- **交付流程**：7 步释放流程 + 3 次 LLM 自动评审
- **代码包解析**：支持 C 代码、Python、MATLAB m 文件、Simulink 模型、.mat 文件、.pth 权重
- **文档解析**：支持 Word (.docx) 和 Excel (.xlsx)
- **LLM 评审**：多模型 + 自动回退，评分 + 建议输出。支持所有 OpenAI 兼容接口 — minimax-M3/M2.7、GLM-5.2、Deepseek-V4-flash、通义千问、Ollama 等
- **权限管理**：系统级角色（访客/开发者/管理员/超级管理员）× 项目级角色（项目经理/开发人员/测试人员/外部技术专家）
- **矩阵组织**：过程域维度（部门→科室→小组）× 项目维度
- **审计日志**：全操作审计记录
- **通知系统**：站内通知 + 邮件提醒
- **用户自助**：注册账号、忘记密码找回

## 默认管理员

首次部署后使用以下账号登录：

- 用户名：`admin`
- 密码：`admin123`

**登录后请立即修改密码！**

## 更新日志

### v1.3.0 (2026-07-20) — 流水线可视化 + 评审流程优化

**释放详情页流水线方框布局**:
- 5 个步骤方框从上往下排列:版本创建 → 代码包上传+LLM评审 → 测试报告上传+LLM评审 → 评审报告上传+LLM评审 → PM 确认释放
- 左侧颜色条标识状态(灰=未开始,蓝=当前,橙=进行中,绿=完成,红=失败)
- 圆圈序号 + 两栏布局(信息+操作),所有字段(成员/上传内容/时间/上传人)集中在同一方框内
- LLM 评审进度抽屉:点击触发评审后在右侧抽屉实时显示大模型输出,可收缩/展开

**评审流程优化**:
- 新增「稍后评审」按钮:开发人员/测试人员可跳过当前 LLM 评审阶段直接进入下一阶段(`POST /api/releases/{id}/skip-review`)
- 新增「特批放行」按钮:项目经理/管理员可特批放行当前版本(`POST /api/releases/{id}/force-advance`)

**版本删除权限细化**:
- 超级管理员可删除任意版本(含已释放),管理员仅可删除未释放版本
- 交付物删除权限:管理员/超级管理员可删除任意交付物,其他角色仅可删除自己上传的交付物

**首页与批量操作**:
- 「我的待办」与「我的已办」窗格等高 + 滚动支持,点击跳转释放详情
- 项目/用户/组织管理页新增「下载模板」和「批量导入」按钮(管理员可见),Excel 模板匹配表结构
- 项目列表新增 PM/测试/专家列与列筛选排序

**默认管理员密码变更**:
- 由 `Admin@123` 调整为 `admin123`(更易记忆,部署后请立即修改)

### v1.2.0 (2026-07-18) — 生产级 SOX 合规增强

**P0 修复 (SOX 审计追溯)**:
- Release 详情页显示每个节点的上传人/触发人（代码包/测试报告/评审报告上传人 + LLM 评审触发人 + 释放确认人）
- 修复代码包/测试报告/评审报告下载按钮 401 错误（`window.open` 不携 token → 改用 axios blob 下载）
- 下载端点添加下载审计日志（SOX 合规要求）
- 数据库新增 6 个 `uploaded_by/uploaded_at` 字段，并从 `audit_logs` 回填历史数据

**LLM 多协议支持**:
- 前端 LLM 配置页新增 8 个预设模板：MiniMax-M3/M2.7、GLM-5.2、DeepSeek-V4-flash（OpenAI 协议）；Claude Sonnet 4.5、Claude Opus 4（Anthropic 协议）；GPT-4o、本地 Ollama
- 后端 `LLMProtocol` enum + `client.py` 已支持 OpenAI/Anthropic 双协议调用

**部署脚本增强**:
- `deploy.sh` 新增 `run_migrations()` 幂等迁移函数，支持 `ALTER TABLE` + 历史数据回填
- 支持 Ubuntu 20.04+/Debian 11+/CentOS 8+/RHEL 8+（apt-get/dnf/yum 自动识别）

### v1.1.0 (2026-07-18)

- 初始生产部署版本
- 修复 6 个功能 Bug（review_rules 模型引用、Celery worker 解析器、LLM 评分阈值、doc_parser zip 支持、overall_rating 字段、dimension_thresholds 维度名）
- 一键部署脚本支持多 LLM 种子与可配置后端地址
- MiniMax-M3 评审解析修复并支持多模型

### v1.0.0 (2026-07-17)

- 首次发布
- 质量 7 步释放流程：draft → code_pending_review → test_pending_review → expert_pending_review → pending_confirm → released
- FastAPI + Vue 3 + PostgreSQL + MinIO + Redis + Celery 技术栈
- LLM 自动化评审、JWT 认证、RBAC 权限、审计日志

## 许可证

本项目基于 [MIT License](LICENSE) 开源，允许任何用途（含商用），仅需保留版权声明。

Copyright (c) 2026 fengtianyu88
