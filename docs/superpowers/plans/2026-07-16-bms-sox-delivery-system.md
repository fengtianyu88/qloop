# BMS SOX 算法软件交付管理系统 — 实现计划

> 日期：2026-07-16

**Goal:** 构建完整的 BMS SOX 算法软件交付管理系统

**Architecture:** 前后端分离。后端 FastAPI + SQLAlchemy + Celery，前端 Vue 3 + Element Plus。PostgreSQL + MinIO + Redis。

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Celery, Redis, MinIO, PostgreSQL, Vue 3, Element Plus, Vite, TypeScript, Pinia

---

## 实现阶段

### Phase 1: 后端脚手架与数据模型 (Task 1-6)
- 后端项目初始化（FastAPI + config + requirements）
- 数据库连接与会话管理
- 前端项目初始化（Vue 3 + Element Plus + Vite）
- 用户与组织数据模型（User, OrgUnit, AdminScope）
- 项目/版本/释放数据模型（Project, Version, Release, ProjectMember, ExternalRecipient）
- LLM评审数据模型（LLMModel, ReviewRule, LLMReview）
- 审计日志与通知数据模型（AuditLog, Notification）

### Phase 2: 认证与用户管理 (Task 7-8)
- 安全工具（密码哈希、JWT）
- 认证服务与API（登录/登出）
- 依赖注入（get_current_user, require_roles）
- 用户管理CRUD API
- 管理员管理范围（过程域树状过滤）

### Phase 3: 组织与项目管理 (Task 9-11)
- 组织管理API（树状层级、管理员范围配置）
- 项目管理API（创建项目、添加成员、创建版本）
- 释放管理API（上传代码包/测试报告/评审报告、确认释放）
- 文件存储（MinIO客户端）

### Phase 4: LLM评审引擎 (Task 12-17)
- 代码包解析引擎（C/Python/MATLAB/Simulink/mat/pth）
- Word/Excel文档解析
- LLM客户端（多模型+自动回退）
- 评审Prompt模板
- 评审引擎（组装输入→调用LLM→解析输出→更新状态）
- Celery异步任务
- LLM配置API与评审触发API

### Phase 5: 首页搜索、通知与审计 (Task 18-20)
- 首页搜索筛选API（释放视图+项目视图）
- 通知服务与API
- 审计日志服务与API
- 邮件发送异步任务
- 路由注册与数据库迁移

### Phase 6: 前端实现 (Task 21-23)
- 前端基础设施（路由、Store、API封装、TypeScript类型）
- 登录页与布局组件
- 首页（双视图+搜索筛选）
- 项目管理页面
- 释放详情页（流程可视化+文件上传+评审结果展示）
- 用户管理页面
- 组织管理页面
- LLM配置页面
- 审计日志页面
- 个人信息页面

---

## 详细任务定义

见代码实现部分，每个任务包含完整的文件创建和代码。
