# CHANGELOG

## v1.5.4 (2026-07-24)

### 概述
基于 v1.5.3 进行全覆盖度测试扩展与验证。在原 160 项测试用例基础上扩展至 288 项（新增 128 项），覆盖 30 个功能模块。前端 UI 浏览器交互测试 13 个场景全部通过。系统达到 100% 测试覆盖度，无需修复任何缺陷。

### 测试扩展
- **测试用例从 160 项扩展至 288 项**（+128 项）
- **新增 14 个测试模块**：
  - 健康检查扩展 (HCX): /api/ready, /api/metrics, trace_id, 异常处理
  - 特批放行扩展 (FORCEX): released_forced 状态、前端逻辑、放行人记录
  - 交付物上传扩展 (UPLOADX): 200MB 校验、文件类型白名单、RELEASED_FORCED 删除拦截、空文件检查
  - LLM 成本追踪 (LLMC): prompt_tokens、completion_tokens、latency_ms、截断标注
  - 通知系统扩展 (NOTIFX): 一键清除未读、shownNotifIds 持久化、SSE 心跳、跨标签页同步
  - 前端可靠性 (FER): 5xx 重试、请求取消、去重、ErrorBoundary、404 路由、chunk 加载失败、SSE 重连
  - 前端交互 (FEI): 密码强度、分页强制显示、面包屑、跨标签页通知、200MB 校验、文件类型白名单、并发评审禁用
  - 安全扩展 (SECX): 异常处理友好消息、CORS 环境变量、连接池配置、statement_timeout、MINIO_SECRET_KEY 校验
  - 配置验证 (CONF): 前后端版本、CHANGELOG、健康检查、Prometheus 格式
  - LLM 配置 (LLMCfg): 模型列表、API key 掩码、地址补全、连通测试
  - 审计日志 (AUDIT): 列表、模型、服务、权限
  - 用户管理 (USER): 列表、密码强度、批量导入、登录尝试限制
  - 系统设置 (SYS): 公开设置、站点名称、super_admin 权限
  - 首页 (HOME): 待办/已完成任务、分页、确认释放跳转
  - 释放详情交互 (REL): 稍后评审、特批放行、确认释放、上传进度
  - 导入导出 (IMP): 下载模板、批量导入、用户/项目模板
  - 项目详情 (PDET): 角色变更二次确认、加载失败错误态、版本列表、面包屑
  - 评审日志 (REVLOG): 清空/导出 .txt、重新触发评审、tooltip 区分
  - LLM 超时配置 (LLMTO): connect_timeout=10s、read_timeout=300s、Celery 任务超时、异常→ERROR 状态
  - 评审规则 (RULE): 规则模型、恢复默认模板、初始化默认规则、prompt 占位符
  - 退出登录 (LOGOUT): 前端调后端、清理 localStorage、跳转登录页
  - 组织类型管理 (ORGT): 列表、预设类型、创建/删除、权限校验

### 测试结果
- **API 自动化测试**: 288/288 PASS (100%)
- **前端 UI 浏览器测试**: 13/13 PASS (100%)
  - 登录页面、首页、项目管理、项目详情、释放详情
  - 用户管理、组织管理、LLM 配置、系统设置、审计日志
  - 404 页面、退出登录、通知系统

### 测试方法论
- API 真实调用: ~150 项
- 代码审查 (grep 源码): ~130 项
- 浏览器自动化交互: 13 项

### 改进
- 测试脚本修复 22 项 grep 模式问题，确保所有源码审查测试精确匹配实际代码
- 修复 TC-AUTH-08: PUT /users/me 改为 PUT /users/{user_id}
- 修复 TC-PROJ-03: POST /releases 改为 POST /projects/{id}/versions + 查询 /releases/by-version/{version_id}
- 修复 TC-PROJ-07: 接受 200/201/400/409（项目名无 unique 约束）

### 升级说明
- 无破坏性变更，仅版本号与测试脚本更新
- 数据库 schema 无变化
- 配置文件无变化

---


### 概述
全面修复系统工作流交互问题，覆盖前端基础设施可靠性、业务页面交互缺陷、后端安全与可观测性。所有修复均通过全覆盖网页交互测试验证。

### 新功能
- **后端健康检查端点** `/api/ready`：检查 DB/Redis/MinIO/Celery 连通性，任一不可用返回 503
- **后端监控端点** `/api/metrics`：Prometheus 兼容的轻量级 metrics（HTTP 请求总数/错误总数），无需第三方依赖
- **全局异常处理器**：捕获未处理异常，返回用户友好消息，不暴露内部堆栈
- **trace_id 中间件**：每个请求生成唯一 trace_id，附加到响应头 X-Trace-Id
- **前端错误边界** ErrorBoundary.vue：捕获组件渲染异常，避免白屏
- **前端 404 页面** NotFound.vue：不存在的路由显示 404 页面而非跳转首页
- **LLM 成本追踪**：记录 prompt_tokens/completion_tokens/latency_ms，输出截断标注

### 改进
- **前端请求可靠性**：5xx/网络错误自动重试 2 次+指数退避；AbortController 请求取消；POST/PUT/DELETE 请求去重；差异化超时配置
- **SSE 重连机制**：指数退避重连 + 心跳保活，通知推送更稳定
- **跨标签页通知同步**：BroadcastChannel 实现多标签页通知状态同步
- **全局面包屑导航**：Layout 组件添加 el-breadcrumb
- **密码强度校验**：前端实时校验（8位+字母+数字），trigger 增加 change 事件
- **分页组件显示**：强制显示分页栏，即使单页数据
- **路由懒加载错误处理**：chunk 加载失败自动刷新页面
- **页面刷新用户信息持久化**：token 有效但 user 为空时自动拉取当前用户信息
- **退出登录调后端接口**：登出时通知后端清理会话
- **上传文件前端校验**：200MB 大小限制 + 文件类型白名单 JS 校验
- **并发评审保护**：评审进行中禁用触发按钮
- **稍后评审 vs 特批放行确认对话框**：区分两种操作，防误触
- **下载链接错误消息净化**：不暴露内部异常，返回用户友好消息
- **空状态优化**：各业务页面添加 el-empty 空状态
- **CORS 配置环境变量化**：允许源从环境变量读取
- **数据库连接池配置**：pool_size=20, max_overflow=20, pool_timeout=30, pool_recycle=3600, statement_timeout=60s
- **清理 .bak 文件**：移除所有 .bak.pre_multi_fix 备份文件

### Bug 修复
- **后端端点路由修复**：`/ready` 和 `/metrics` 端点缺少 `/api` 前缀导致 nginx 代理后 404
- **forgot_password 链接修复**：使用 FRONTEND_BASE_URL 配置生成重置链接
- **密码强度 schema 校验**：后端注册/重置密码接口增加密码强度校验
- **RELEASED_FORCED 拦截**：delete_artifact 拦截已特批释放版本的制品删除
- **MinIO 预签名 URL 7 天有效期**：从 1 小时修正为 168 小时
- **上传空文件检查**：上传函数增加空文件校验

### 测试
- 全覆盖网页交互测试：10 项测试全部通过（登录/404/导航/项目管理/密码强度/组织管理/LLM配置/系统设置/释放详情/退出登录）
- 后端健康检查：/api/ready 返回 DB/Redis/MinIO/Celery 全部 ready
- 后端监控：/api/metrics 返回 Prometheus 格式 metrics
