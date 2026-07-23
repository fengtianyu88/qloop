# CHANGELOG

## v1.5.3 (2026-07-23)

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
