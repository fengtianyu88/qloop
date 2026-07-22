# qloop

> [English](README.md) | 简体中文

> 版本：1.4.7  日期：2026-07-22

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
- **文档解析**：支持 Word (.docx)、Excel (.xlsx)、ZIP 压缩包（自动解压 + 递归解析内嵌文件）、纯文本（.md/.txt/.csv/.json/.yaml）
- **LLM 评审**：多模型 + 自动回退，评分 + 建议输出。支持所有 OpenAI 兼容接口 — minimax-M3/M2.7、GLM-5.2、Deepseek-V4-flash、通义千问、Ollama 等。**SSE 流式输出**实时展示评审进度。
- **权限管理**：系统级角色（访客/开发者/管理员/超级管理员）× 项目级角色（项目经理/开发人员/测试人员/外部技术专家）。**PM 创建版本时自动把 dev/test/expert 加入项目成员。**
- **矩阵组织**：过程域维度（部门→科室→小组）× 项目维度
- **审计日志**：全操作审计记录
- **通知系统**：站内通知 + 邮件提醒。**关键事件自动触发**：分配版本、上传交付物、评审通过/失败、确认释放。
- **角色待办中心**：首页展示当前用户待办 release 列表，按角色和状态自动过滤。
- **状态引导提示**：release 详情页顶部显示"下一步"横幅，提示该谁做什么。
- **模板下载**：一键下载代码包、测试报告、专家评审报告模板（自动填充项目/版本/用户信息）。
- **演示快速登录**：登录页提供 4 个演示角色一键登录（PM/开发/测试/专家）。
- **用户自助**：注册账号、忘记密码找回

## 默认管理员

首次部署后使用以下账号登录：

- 用户名：`admin`
- 密码：`admin123`

**登录后请立即修改密码！**
## 许可证

本项目基于 [MIT License](LICENSE) 开源，允许任何用途（含商用），仅需保留版权声明。

Copyright (c) 2026 fengtianyu88
