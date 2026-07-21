# qloop — 设计文档 v1.4.3 增量补充

> 日期：2026-07-22
> 基线版本：[2026-07-20-qloop-design-v1.3.0.md](./2026-07-20-qloop-design-v1.3.0.md) (v1.3.0)
> 当前版本：v1.4.3
> 状态：已实现并发布

---

## 0. 变更摘要

本文档是对 v1.3.0 设计文档的增量补充,覆盖 v1.4.0 → v1.4.3 期间已落地的所有新功能与 Bug 修复。**原设计文档中的所有内容仍然有效**,除非本文档明确声明覆盖。

| 版本 | 发布日期 | 主要内容 |
|------|---------|---------|
| v1.4.0 | 2026-07-20 | 稳定性/安全性/新功能大版本：流水线删除按钮、维度阈值默认模板、默认评审规则初始化、评审失败状态修复 |
| v1.4.1 | 2026-07-20 | 登录失败锁定时间从 15 分钟降为 3 分钟 |
| v1.4.2 | 2026-07-21 | 释放流水线角色分工 + 评审失败特批放行 + LLM 流式输出 |
| **v1.4.3** | **2026-07-22** | **文档解析器 ZIP 解压 + 权限自动授予 + 通知系统 + 状态引导 + 模板下载 + 演示快速登录** |

---

## 一、文档解析器 ZIP 解压与多格式支持(v1.4.3 修复)

### 1.1 问题描述

v1.4.2 之前,`doc_parser.py` 的 `parse_document` 仅支持 `.docx` 和 `.xlsx` 两种格式。当用户上传 `.zip` 压缩包(最常见的交付方式)时,解析器走 UTF-8 fallback 解码失败,LLM 拿到的内容是 `[无法解析的文档类型: .zip]`,导致**专家报告评审 100% 失败**(score=0,result=failed),用户只能靠特批放行推进。

### 1.2 修复方案

重写 `app/llm/doc_parser.py`,新增以下能力:

1. **`parse_zip()` 函数**:自动解压 ZIP 包并递归解析内部文档
   - 支持内嵌格式:`.docx` / `.xlsx` / `.txt` / `.md` / `.csv` / `.json` / `.yaml` / `.ini` / `.log` / `.rst`
   - 每个文件渲染时带 `--- {path} ---` 头部,让 LLM 能区分文件来源
   - 不支持的文件类型(如 `.exe` / `.dll` / `.png`)列出但跳过

2. **文本格式多编码探测**:`utf-8-sig` → `utf-8` → `gbk` → `gb18030` → `latin-1`

3. **`.pdf` 明确错误提示**:引导用户改用 `.docx` 或打包 `.zip` 内嵌 `.md`

4. **安全防护**:
   - ZIP-bomb 防护:最多解析 50 个文件
   - 输出长度截断:100KB(避免 LLM prompt 过长)

### 1.3 验证结果

| 评审阶段 | 修复前 | 修复后 |
|---------|--------|--------|
| 代码评审 | ✅ 40分 | ✅ 50分 |
| 测试报告评审 | ✅ 70分 | ✅ 42分 |
| 专家报告评审 | ❌ 0分失败 | ✅ 35分通过 |
| Release | 仅靠特批放行 | 直接成功 |

---

## 二、权限自动授予(v1.4.3 修复)

### 2.1 问题描述

v1.4.2 之前,PM 创建版本时虽然指定了 `developer_id` / `tester_id` / `expert_id`,但这些用户**并未自动加入 `ProjectMember` 表**。而 `check_project_access` 权限检查要求用户是 PM、ProjectMember 或 admin/super_admin,导致 dev/test/expert 登录后访问项目和 release 详情页直接 403:

```
GET /api/projects/{id} → 403 "You do not have access to this project"
GET /api/releases/{id} → 403 "You do not have access to this release's project"
```

### 2.2 修复方案(双管齐下)

#### 2.2.1 `project_service.create_version` 自动加入 ProjectMember

在 `create_version` 函数中,版本创建成功后自动把 developer/tester/expert 加入 `ProjectMember` 表:

```python
role_assignments = [
    (version_create.developer_id, ProjectRole.DEVELOPER),
    (version_create.tester_id,    ProjectRole.TESTER),
    (version_create.expert_id,    ProjectRole.EXTERNAL_EXPERT),
]
for user_id, role in role_assignments:
    if user_id is None:
        continue
    # 跳过已存在的成员(避免重复)
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(ProjectMember(project_id=project_id, user_id=user_id, project_role=role))
```

#### 2.2.2 `permission_service.check_project_access` 兜底检查

为兼容历史数据(早期 `create_version` 未自动加入 ProjectMember),在 `check_project_access` 中增加兜底逻辑:

```python
# 兜底: 检查是否被分配为该项目任一版本的 developer/tester/expert
result = await db.execute(
    select(Version).where(
        Version.project_id == project_id,
        Version.is_deleted == False,
        or_(
            Version.developer_id == user.id,
            Version.tester_id == user.id,
            Version.expert_id == user.id,
        ),
    )
)
if result.scalar_one_or_none() is not None:
    return True
```

### 2.3 验证结果

四角色完整流程 API 测试全部通过:

| 角色 | 修复前 | 修复后 |
|------|--------|--------|
| DEV (dev_lisi) | ❌ 403 | ✅ 200 |
| TEST (tester_wangwu) | ❌ 403 | ✅ 200 |
| EXPERT (expert_zhaoliu) | ❌ 403 | ✅ 200 |

---

## 三、通知系统自动触发(v1.4.3 新增)

### 3.1 问题描述

qloop 后端已有完整的通知基础设施(`Notification` model、`notification_service.create_notification`、`notification_tasks.send_notification` Celery 任务、`/api/notifications` API、前端 `useNotificationStore`),但**没有任何地方调用 `create_notification`**,通知系统形同虚设。

### 3.2 修复方案

在 3 个后端文件的关键事件中接入 `create_notification`:

#### 3.2.1 `project_service.create_version` — PM 创建版本

| 接收人 | 通知类型 | 标题 | 内容 |
|--------|---------|------|------|
| developer | task_assigned | 你有新的代码上传任务 | {项目名} {版本号} 需要你上传代码包 |
| tester | task_assigned | 你有新的测试任务 | {项目名} {版本号} 等待代码评审通过后需要你上传测试报告 |
| expert | task_assigned | 你有新的评审任务 | {项目名} {版本号} 等待测试报告评审通过后需要你上传专家评审报告 |

#### 3.2.2 `release_service` — 交付物上传

| 事件 | 接收人 | 通知类型 | 标题 |
|------|--------|---------|------|
| upload_code_package | PM | your_turn | 代码包已上传 |
| upload_test_report | PM | your_turn | 测试报告已上传 |
| upload_review_report | PM | your_turn | 专家评审报告已上传 |

#### 3.2.3 `release_service.confirm_release` — 确认释放

| 接收人 | 通知类型 | 标题 |
|--------|---------|------|
| developer + tester + expert + PM | release_completed | 版本已释放 |

#### 3.2.4 `release_service.force_advance` — 特批放行

| 接收人 | 通知类型 | 标题 |
|--------|---------|------|
| 下一角色(按 next_status 映射) | your_turn | 已特批放行 |

#### 3.2.5 `review_tasks._notify_after_review` — LLM 评审完成

| 评审结果 | 接收人 | 通知类型 | 标题 |
|---------|--------|---------|------|
| passed | 下一角色 | your_turn | {review_type}评审通过 |
| failed/error | PM | review_failed | {review_type}评审未通过 |

### 3.3 实现要点

1. **所有通知调用在 `await db.commit()` 之后**,避免事务回滚导致通知脏数据
2. **所有通知调用用 try/except 包裹**,通知失败不影响主流程
3. **避免 async 懒加载错误**:commit 后 ORM 关系已过期,改用独立查询 `_get_version_project_for_notify` 获取数据

### 3.4 验证结果

E2E 四角色完整流程产生 13 条通知,覆盖全流程:

| 事件 | 通知类型 | 接收人 |
|------|---------|--------|
| PM 创建版本 | task_assigned | dev_lisi / tester_wangwu / expert_zhaoliu |
| DEV 上传代码包 | your_turn | pm_zhangwei |
| 代码评审通过 | your_turn | tester_wangwu |
| 测试报告已上传 | your_turn | pm_zhangwei |
| 测试报告评审失败 | review_failed | pm_zhangwei |
| 专家报告已上传 | your_turn | pm_zhangwei |
| 专家报告评审通过 | your_turn | pm_zhangwei |
| PM 确认释放 | release_completed | 全员(4人) |

---

## 四、状态引导提示(v1.4.3 新增)

### 4.1 设计目标

用户进入 release 详情页时,不清楚当前状态该谁做什么。需要一个引导横幅,告诉用户"下一步该谁做什么"。

### 4.2 实现

在 `ReleaseDetail.vue` 的流水线顶部(步骤 1 卡片上方)添加 `<el-alert>` 横幅:

```typescript
const nextStepHint = computed(() => {
  switch (release.value?.status) {
    case 'draft':                 return { actor: '开发人员', action: '上传代码包', type: 'info' }
    case 'code_pending_review':   return { actor: '项目经理', action: '触发代码评审', type: 'info' }
    case 'test_pending_review':   return { actor: '测试人员', action: '上传测试报告', type: 'info' }
    case 'expert_pending_review': return { actor: '专家', action: '上传专家评审报告', type: 'info' }
    case 'pending_confirm':       return { actor: '项目经理', action: '确认释放', type: 'warning' }
    case 'released':              return { actor: '', action: '版本已释放', type: 'success' }
    case 'review_failed':         return { actor: '项目经理', action: '评审未通过,可特批放行或等待重新上传', type: 'warning' }
    default:                      return { actor: '', action: '', type: 'info' }
  }
})
```

横幅样式:圆角 8px,带图标,根据状态动态切换 `info` / `warning` / `success` 类型。

---

## 五、模板下载(v1.4.3 新增)

### 5.1 设计目标

用户上传交付物时不知道该上传什么格式和内容,需要模板参考。

### 5.2 实现

在三个上传按钮旁各添加一个"下载模板"链接按钮,点击后用前端纯 JS 生成并下载模板文件:

| 模板类型 | 文件格式 | 内容 |
|---------|---------|------|
| 代码包模板 | `.py` | BMS 核心算法模板(SOC 计算类) |
| 测试报告模板 | `.md` | 含测试用例表格、测试结果、结论 |
| 专家评审报告模板 | `.md` | 含评审维度表格、风险点、结论 |

模板内容自动填充:
- `{项目名}` → projectName
- `{版本号}` → version_id
- `{用户名}` → authStore.user.full_name
- `{当前日期}` → YYYY-MM-DD

实现方式:`Blob + URL.createObjectURL + a.click()`,文件名格式 `template_{type}_{timestamp}.{ext}`。

---

## 六、演示快速登录(v1.4.3 新增)

### 6.1 设计目标

演示/测试场景下,频繁切换 4 个角色账号(登出→登录)非常繁琐。需要在登录页提供一键登录入口。

### 6.2 实现

在 `Login.vue` 底部添加 4 个演示账号按钮:

| 按钮 | 账号 | 图标 | 颜色 |
|------|------|------|------|
| 项目经理 | pm_zhangwei | UserFilled | #409eff (蓝) |
| 开发人员 | dev_lisi | Edit | #67c23a (绿) |
| 测试人员 | tester_wangwu | Document | #e6a23c (橙) |
| 外部专家 | expert_zhaoliu | Star | #f56c6c (红) |

点击后自动填充用户名和密码(`Role@E2E2026`),并调用 `handleLogin()` 直接登录。

样式:圆角按钮,带图标 + 颜色区分,底部用虚线分隔。

**安全提示**:此功能仅在演示/测试环境使用,生产环境应移除或禁用。

---

## 七、LLM 流式输出(v1.4.2 引入,v1.4.3 确认)

### 7.1 SSE 端点

`GET /api/reviews/stream/{release_id}?token=xxx` — Server-Sent Events 流式推送评审进度:

| 事件类型 | 说明 |
|---------|------|
| `connected` | SSE 连接建立 |
| `llm_start` | LLM 开始调用 |
| `chunk` | 流式输出片段 |
| `llm_done` | LLM 调用完成 |
| `llm_error` | LLM 调用错误 |
| `done` | 评审任务完成 |
| `error` | 评审任务错误 |
| `final` | 最终结果 |

### 7.2 前端实现

`ReleaseDetail.vue` 中使用 `EventSource` 订阅 SSE,实时追加 LLM 输出到评审进度抽屉。支持心跳检测(5 秒间隔),区分"仍在等待"和"流式暂停"。

---

## 八、评审失败特批放行(v1.4.2 引入,v1.4.3 确认)

### 8.1 状态转换

`force_advance` 函数在 `REVIEW_FAILED` 状态下,根据最近一次失败的 `review_type` 决定推进目标:

| 失败的 review_type | 推进目标 |
|-------------------|---------|
| CODE_REVIEW | TEST_PENDING_REVIEW |
| TEST_REPORT_REVIEW | EXPERT_PENDING_REVIEW |
| EXPERT_REPORT_REVIEW | PENDING_CONFIRM |

### 8.2 权限

- PM(项目项目经理)
- admin / super_admin

### 8.3 前端

`canForceAdvance` computed 覆盖 5 个状态:`code_pending_review` / `test_pending_review` / `expert_pending_review` / `pending_confirm` / `review_failed`。

---

## 九、API 端点清单(v1.4.3 完整版)

### 9.1 释放相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/releases/{release_id}` | 获取 release 详情 |
| GET | `/api/releases/by-version/{version_id}` | 按版本 ID 获取 release 列表 |
| POST | `/api/releases/{release_id}/code-package` | 上传代码包 |
| POST | `/api/releases/{release_id}/test-report` | 上传测试报告 |
| POST | `/api/releases/{release_id}/review-report` | 上传评审报告 |
| POST | `/api/releases/{release_id}/confirm` | PM 确认释放 |
| POST | `/api/releases/{release_id}/force-advance` | 特批放行 |
| POST | `/api/releases/{release_id}/skip-review` | 稍后评审 |
| GET | `/api/releases/{release_id}/download/{file_type}` | 下载交付物 |

### 9.2 评审相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/reviews/release/{release_id}` | 获取 release 的评审记录 |
| POST | `/api/reviews/trigger/{release_id}?review_type=xxx` | 触发 LLM 评审 |
| GET | `/api/reviews/stream/{release_id}?token=xxx` | SSE 流式接收评审进度 |

### 9.3 待办与通知

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/my-tasks/todo` | 当前用户待办 |
| GET | `/api/my-tasks/done` | 当前用户已办 |
| GET | `/api/notifications` | 通知列表 |
| GET | `/api/notifications/unread-count` | 未读通知数 |
| POST | `/api/notifications/{id}/read` | 标记已读 |

---

## 十、数据库 Schema 变更(v1.4.0 → v1.4.3)

### 10.1 `releases` 表新增列

| 列名 | 数据类型 | 引入版本 | 说明 |
|------|---------|---------|------|
| force_advanced_by | UUID (FK→users) | v1.4.2 | 特批放行人 |
| force_advanced_at | TIMESTAMP WITH TIME ZONE | v1.4.2 | 特批放行时间 |

### 10.2 `notifications` 表(已存在,v1.4.3 开始有数据)

| 列名 | 数据类型 |
|------|---------|
| id | UUID |
| user_id | UUID (FK→users) |
| type | notification_type enum |
| title | VARCHAR |
| content | TEXT |
| is_read | BOOLEAN |
| link_url | VARCHAR |
| created_at | TIMESTAMP |

`notification_type` enum 值:`task_assigned` / `review_failed` / `review_passed` / `your_turn` / `release_completed` / `system`

---

## 十一、E2E 测试验证

### 11.1 四角色完整流程测试

| 步骤 | 角色 | 动作 | 结果 |
|------|------|------|------|
| 1 | PM | 创建项目+版本 | ✅ |
| 2 | DEV | 上传代码包 | ✅ status=code_pending_review |
| 3 | PM | 触发代码评审 | ✅ passed (score=52) |
| 4 | TEST | 上传测试报告 | ✅ status=test_pending_review |
| 5 | PM | 触发测试报告评审 | ✅ passed (score=40) |
| 6 | EXPERT | 上传专家报告 | ✅ status=expert_pending_review |
| 7 | PM | 触发专家报告评审 | ✅ passed (score=35) |
| 8 | PM | 确认释放 | ✅ status=released |
| - | 全员 | 通知接收 | ✅ 13 条通知覆盖全流程 |

### 11.2 特批放行测试

| 场景 | 结果 |
|------|------|
| review_failed → pending_confirm | ✅ force_advanced_by_name=admin |
| force_advanced_at 正确填充 | ✅ |

---

## 十二、文件变更清单(v1.4.0 → v1.4.3)

### 后端

| 文件 | 变更 |
|------|------|
| `app/llm/doc_parser.py` | 重写:新增 parse_zip / 文本格式支持 / 多编码探测 |
| `app/services/permission_service.py` | 新增兜底检查:versions 表 developer/tester/expert |
| `app/services/project_service.py` | create_version 自动加入 ProjectMember + 通知 dev/test/expert |
| `app/services/release_service.py` | upload/confirm/force_advance 后触发通知 |
| `app/tasks/review_tasks.py` | 评审完成后通知下一角色/PM |
| `app/llm/client.py` | 新增流式调用函数(v1.4.2) |

### 前端

| 文件 | 变更 |
|------|------|
| `src/views/ReleaseDetail.vue` | 状态引导横幅 + 模板下载按钮 + LLM 流式 chunk 渲染 |
| `src/views/Login.vue` | 演示账号快速登录按钮 |
| `src/views/Home.vue` | 我的待办/已办面板(v1.4.2) |

---

*Copyright (c) 2026 fengtianyu88*
