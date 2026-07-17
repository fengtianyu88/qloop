# BMS SOX 算法软件交付管理系统

> 版本：1.0.0  日期：2026-07-16

## 项目简介

BMS SOX 算法软件交付管理系统，用于管理 BMS SOX（SOC/SOH/SOF 等）算法软件的对外交付流程。系统支持代码包管理、评审报告管理、测试报告管理、LLM 自动化评审、用户权限管理、项目全生命周期管理等功能。

## 目录结构

```
bms-sox-delivery-system/
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
        │   └── 2026-07-16-bms-sox-delivery-system-design.md
        └── plans/                        # 实施计划
            └── 2026-07-16-bms-sox-delivery-system.md
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
- **LLM 评审**：多模型 + 自动回退，评分 + 建议输出
- **权限管理**：系统级角色（访客/开发者/管理员/超级管理员）× 项目级角色（项目经理/开发人员/测试人员/外部技术专家）
- **矩阵组织**：过程域维度（部门→科室→小组）× 项目维度
- **审计日志**：全操作审计记录
- **通知系统**：站内通知 + 邮件提醒
- **用户自助**：注册账号、忘记密码找回

## 默认管理员

首次部署后使用以下账号登录：

- 用户名：`admin`
- 密码：`Admin@123`

**登录后请立即修改密码！**

## 许可证

内部使用，版权所有。
