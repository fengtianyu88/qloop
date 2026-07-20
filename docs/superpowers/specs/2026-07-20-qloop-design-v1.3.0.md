# qloop — 设计文档 v1.3.0 增量补充

> 日期：2026-07-20
> 基线版本：[2026-07-16-qloop-design.md](./2026-07-16-qloop-design.md) (v1.0.0)
> 当前版本：v1.3.0
> 状态：已实现并发布

---

## 0. 变更摘要

本文档是对 v1.0.0 初始设计的增量补充,覆盖 v1.1.0 → v1.3.0 期间已落地的所有新功能与权限规则变更。**原设计文档中的所有内容仍然有效**,除非本文档明确声明覆盖。

| 版本 | 发布日期 | 主要内容 |
|------|---------|---------|
| v1.0.0 | 2026-07-17 | 初始发布,7 步释放流程 + LLM 评审 |
| v1.1.0 | 2026-07-18 | 6 个 Bug 修复,多 LLM 种子,MiniMax-M3 解析修复 |
| v1.2.0 | 2026-07-18 | SOX 审计追溯 + 多 LLM 协议(OpenAI/Anthropic)+ 部署脚本迁移 |
| **v1.3.0** | **2026-07-20** | **流水线方框布局 + 评审流程优化 + 权限细化 + 批量导入** |

---

## 一、释放详情页流水线可视化(v1.3.0 新增)

### 1.1 设计目标

将原本散落的信息卡片重构为 **5 个步骤方框从上往下排列**,让整个交付流水线一目了然。

### 1.2 流水线方框结构

```
┌─────────────────────────────────────┐
│ ① 版本创建                           │
│   版本号 / 创建人 / 创建时间         │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ ② 代码包上传 + LLM 评审              │
│   上传人 / 上传时间 / 评审结果        │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ ③ 测试报告上传 + LLM 评审            │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ ④ 评审报告上传 + LLM 评审            │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ ⑤ PM 确认释放                        │
└─────────────────────────────────────┘
```

### 1.3 方框状态与颜色映射

| 状态 | 颜色条 | 触发条件 |
|------|-------|---------|
| 未开始 (not_started) | 灰色 `#c0c4cc` | 流程尚未推进到此步骤 |
| 当前 (current) | 蓝色 `#409eff` | release 当前 status 对应此步骤 |
| 进行中 (in_progress) | 橙色 `#e6a23c` | 已上传部分材料,等待 LLM 评审 |
| 完成 (completed) | 绿色 `#67c23a` | 此步骤已通过(含 LLM 评审通过或 PM 确认) |
| 失败 (failed) | 红色 `#f56c6c` | LLM 评审未通过,退回上传人 |

### 1.4 方框内部布局

每个方框采用 **圆圈序号 + 两栏布局**:

- **左栏(信息)**:成员、上传内容、时间、上传人、评审结果等所有字段
- **右栏(操作)**:对应步骤的动作按钮(上传、触发评审、稍后评审、特批放行、确认释放等)

这样所有相关字段集中在同一方框内,流水线视觉清晰度大幅提升。

### 1.5 LLM 评审进度抽屉

点击"触发评审"按钮后,右侧抽屉(`el-drawer`)实时显示大模型输出:

- 抽屉方向:`rtl`(right-to-left,从右滑入)
- 不阻挡页面:`:modal="false"`,可同时操作详情页
- 可收缩/展开:用户可点击向右收缩来隐藏,隐藏状态下点击变成向左展开
- 轮询机制:前端每 3 秒轮询评审任务状态,实时追加日志到抽屉
- 日志按时间戳排序,包含 LLM 调用开始、流式输出片段、解析结果、通过/不通过结论

---

## 二、评审流程优化(v1.3.0 新增)

### 2.1 设计目标

原设计中评审阶段只能等 LLM 评审通过后才能推进,流程刚性较大。v1.3.0 引入两个灵活控制按钮:

1. **稍后评审** — 开发/测试人员可跳过当前 LLM 评审,直接进入下一阶段
2. **特批放行** — PM/管理员可特批推进流程

### 2.2 稍后评审(Skip Review)

**使用场景**:LLM 评审耗时长或临时不可用,开发/测试人员希望先推进到下一阶段,稍后再补评审。

**权限规则**:

| 当前状态 | 允许操作的角色 |
|---------|---------------|
| `code_pending_review` | 代码包上传人 + admin/super_admin |
| `test_pending_review` | 测试报告上传人 + admin/super_admin |
| `expert_pending_review` | 评审报告上传人 + admin/super_admin |

**状态转换**:

```
code_pending_review    ──skip──> test_pending_review
test_pending_review   ──skip──> expert_pending_review
expert_pending_review ──skip──> pending_confirm
```

**API**:`POST /api/releases/{release_id}/skip-review`

**约束**:其他状态(如 draft、released、review_failed)不允许 skip。

### 2.3 特批放行(Force Advance)

**使用场景**:PM 或管理员判断某版本可推进,无需等待 LLM 评审完成。

**权限规则**:

| 当前状态 | 允许操作的角色 |
|---------|---------------|
| `code_pending_review` / `test_pending_review` / `expert_pending_review` | PM(项目内)+ admin/super_admin |
| `pending_confirm` | PM(项目内)+ admin/super_admin(直接释放) |

**状态转换**:

```
code_pending_review    ──force──> test_pending_review
test_pending_review   ──force──> expert_pending_review
expert_pending_review ──force──> pending_confirm
pending_confirm       ──force──> released (生成 7 天有效下载链接)
```

**API**:`POST /api/releases/{release_id}/force-advance`

**约束**:`draft` / `released` / `review_failed` 状态不允许特批放行。

### 2.4 评审流程对比

| 维度 | v1.0(原设计) | v1.3.0(新增) |
|------|--------------|-------------|
| 推进方式 | LLM 评审通过 → 自动推进 | LLM 通过 / 稍后评审 / 特批放行 |
| 退回后 | 修改后重新提交 | 修改后重新提交(不变) |
| PM 介入点 | 仅 `pending_confirm` 确认释放 | 任意评审阶段 + `pending_confirm` 均可特批 |
| 审计追溯 | 全程记录 | 全程记录(含 skip/force 操作人、时间) |

---

## 三、版本删除权限细化(v1.3.0 变更)

### 3.1 原设计(覆盖)

原设计未明确版本删除的权限规则。v1.3.0 明确如下:

### 3.2 新权限规则

| 角色 | 版本删除权限 |
|------|------------|
| 超级管理员 | 可删除任意版本(含已释放状态) |
| 管理员 | 仅可删除 **未释放** 状态的版本 |
| 项目经理 | 无删除权限 |
| 其他角色 | 无删除权限 |

**API**:`DELETE /api/projects/{project_id}/versions/{version_id}`

**约束**:删除版本时会级联删除该版本下的所有 release 记录、交付物文件(MinIO 对象)、评审记录。已释放版本的删除仅限 super_admin,避免误操作。

---

## 四、交付物删除权限(v1.3.0 新增)

### 4.1 设计目标

允许删除已上传的交付物(代码包/测试报告/评审报告),便于修订和重新上传。

### 4.2 权限规则

| 角色 | 交付物删除权限 |
|------|--------------|
| 超级管理员 | 任意版本下的任意交付物 |
| 管理员 | 未释放版本下的任意交付物 |
| 其他角色 | 仅自己上传的交付物(且版本未释放) |

**API**:`DELETE /api/releases/{release_id}/artifacts/{file_type}`

**file_type 取值**:`code_package` / `test_report` / `review_report` / `change_notes`

**实现细节**:
- 删除 MinIO 对象 → 清空 release 表对应字段(path/uploaded_by/uploaded_at)
- 写入审计日志
- 不影响已存在的 LLM 评审记录(保留历史)

---

## 五、首页待办/已办窗格(v1.3.0 新增)

### 5.1 设计目标

让用户在首页一眼看到自己的工作项,点击直接跳转处理。

### 5.2 双窗格布局

首页顶部并列两个等高窗格:

| 窗格 | 数据源 | 筛选规则 |
|------|-------|---------|
| 我的待办 | `GET /api/my-tasks/todo` | 当前用户作为上传人/PM,且 release 处于等待其操作的状态 |
| 我的已办 | `GET /api/my-tasks/done` | 当前用户参与过的已释放/已完成的 release |

**交互**:
- 两窗格等高(`display:flex; align-items:stretch`)
- 列表项过多时支持鼠标滚动上下(不撑开页面)
- 点击列表项跳转到 `/releases/{release_id}` 详情页
- 空数据时显示 `el-empty` 占位

### 5.3 待办判定逻辑

| 当前状态 | 待办人 |
|---------|-------|
| `draft` | 开发人员(待上传代码包) |
| `code_pending_review` | 代码包上传人(等待 LLM 评审,或可稍后评审) |
| `test_pending_review` | 测试报告上传人 |
| `expert_pending_review` | 评审报告上传人 |
| `pending_confirm` | PM |

---

## 六、批量导入导出(v1.3.0 新增)

### 6.1 设计目标

管理员可批量创建/更新项目、用户、组织,减少手动逐条录入。

### 6.2 适用范围

| 管理页面 | 模板下载 | 批量导入 |
|---------|---------|---------|
| 项目管理 (`/projects`) | ✓ | ✓ |
| 用户管理 (`/users`) | ✓ | ✓ |
| 组织管理 (`/organizations`) | ✓ | ✓ |

**权限**:仅 admin/super_admin 可见「下载模板」和「批量导入」按钮。

### 6.3 模板格式

- Excel (.xlsx),由 openpyxl 生成
- 列结构与对应数据库表字段一一对应
- 首行为字段名(中文),数据行从第二行开始
- 必填字段以红色背景标识

### 6.4 导入行为

- **新增**:主键字段为空时执行 INSERT
- **更新**:主键字段有值时执行 UPDATE(若存在)
- **错误处理**:逐行校验,错误行写入响应报告,不影响其他行
- **响应**:返回 `{total, success, failed, errors[]}` 结构

### 6.5 API 端点

```
GET  /api/projects/template      # 下载项目模板
POST /api/projects/import        # 批量导入项目
GET  /api/users/template         # 下载用户模板
POST /api/users/import           # 批量导入用户
GET  /api/organizations/template  # 下载组织模板
POST /api/organizations/import    # 批量导入组织
```

---

## 七、系统设置与站点品牌(v1.2.0 新增,v1.3.0 增强)

### 7.1 设计目标

允许 super_admin 自定义站点名称、Logo、品牌色等,支持不同公司/部门定制化部署。

### 7.2 配置项

| 配置项 | 类型 | 默认值 | 权限 |
|-------|------|-------|------|
| `site_name` | string | `qloop` | super_admin 可改 |
| `site_logo` | string (URL) | 内置 SVG | super_admin 可改 |
| `site_description` | text | 质量 闭环 管理系统 | super_admin 可改 |

### 7.3 API

```
GET /api/system-settings         # super_admin 读取所有配置
PUT /api/system-settings         # super_admin 修改配置
GET /api/system-settings/public  # 公开读取(无需登录,仅返回站点名/Logo 等公开项)
```

### 7.4 前端缓存机制

- Pinia `siteInfo` store 在首次加载时拉取 `/public` 配置
- 缓存到 `localStorage`,减少重复请求
- 跨标签页同步:通过 `window.dispatchEvent` 自定义事件,一个标签页修改后其他标签页立即更新

---

## 八、多 LLM 协议支持(v1.2.0 新增)

### 8.1 设计目标

原设计仅支持 OpenAI 兼容接口。v1.2.0 起增加 Anthropic 协议原生支持,无需通过代理转换。

### 8.2 协议枚举

```python
class LLMProtocol(str, Enum):
    OPENAI = "openai"      # OpenAI 兼容接口: /v1/chat/completions
    ANTHROPIC = "anthropic"  # Anthropic 原生: /v1/messages
```

### 8.3 预设模板

LLM 配置页内置 8 个预设模板:

| 模板 | 协议 | 模型名 |
|------|------|-------|
| MiniMax-M3 | OpenAI | minimax-M3 |
| MiniMax-M2.7 | OpenAI | minimax-M2.7 |
| GLM-5.2 | OpenAI | glm-5.2 |
| DeepSeek-V4-flash | OpenAI | deepseek-v4-flash |
| Claude Sonnet 4.5 | Anthropic | claude-sonnet-4-5 |
| Claude Opus 4 | Anthropic | claude-opus-4 |
| GPT-4o | OpenAI | gpt-4o |
| 本地 Ollama | OpenAI | qwen2.5:14b(可改) |

### 8.4 LLM 配置增强

- **测试按钮**:配置页右上角「测试连接」按钮,发送一个简单 prompt 验证配置是否可用
- **物理删除**:LLM 模型和评审规则支持物理删除(原仅软删除)
- **MiniMax-M3 解析器**:新增 Layout D-J 模式,适配 M3 模型的输出格式

---

## 九、SOX 审计追溯(v1.2.0 新增)

### 9.1 设计目标

满足 SOX 合规审计要求,release 详情页必须显示每个节点的操作人和操作时间。

### 9.2 数据库新增字段

`releases` 表新增 6 个字段:

| 字段 | 类型 | 说明 |
|------|------|------|
| `code_package_uploaded_by` | UUID FK→users | 代码包上传人 |
| `code_package_uploaded_at` | timestamp | 代码包上传时间 |
| `test_report_uploaded_by` | UUID FK→users | 测试报告上传人 |
| `test_report_uploaded_at` | timestamp | 测试报告上传时间 |
| `review_report_uploaded_by` | UUID FK→users | 评审报告上传人 |
| `review_report_uploaded_at` | timestamp | 评审报告上传时间 |

### 9.3 历史数据回填

通过 `run_migrations()` 函数从 `audit_logs` 表回填历史 release 记录的上传人/上传时间:

```sql
-- 示例回填逻辑
UPDATE releases r SET
  code_package_uploaded_by = a.user_id,
  code_package_uploaded_at = a.created_at
FROM audit_logs a
WHERE a.release_id = r.id
  AND a.action = 'upload_code_package'
  AND r.code_package_uploaded_by IS NULL;
```

### 9.4 下载审计日志

下载代码包/测试报告/评审报告时,自动写入审计日志:

```
action: download_artifact
resource_type: release
resource_id: <release_id>
metadata: {"file_type": "code_package", "size_bytes": 1234567}
user_id: <当前用户>
```

### 9.5 下载链接有效期

- MinIO 预签名 URL 有效期统一为 **7 天 (168 小时)**
- PM 确认释放时生成,存入 `releases.download_link` 和 `link_expiry` 字段
- 过期后用户访问详情页会自动重新生成

---

## 十、项目成员管理增强(v1.2.0 新增)

### 10.1 设计目标

原设计仅 PM 可管理项目成员。v1.2.0 起明确权限规则,支持 admin/super_admin 跨项目管理。

### 10.2 权限规则

| 操作 | super_admin | admin | PM(项目内) |
|------|------------|-------|------------|
| 添加成员 | ✓(任意项目) | ✓(任意项目) | ✓(自己项目) |
| 修改成员角色 | ✓(任意项目,含 PM) | ✓(任意项目,含 PM) | ✓(自己项目,但不可改其他 PM) |
| 删除成员 | ✓(任意项目) | ✓(任意项目) | ✓(自己项目,但不可删其他 PM) |

**API**:
- `POST /api/projects/{id}/members` — 添加成员
- `PATCH /api/projects/{id}/members/{user_id}` — 修改成员角色
- `DELETE /api/projects/{id}/members/{user_id}` — 删除成员

### 10.3 前端交互

- ProjectDetail.vue 中操作按钮按权限可见
- PM 不可见其他 PM 的「编辑/删除」按钮
- admin/super_admin 可见所有成员的「编辑/删除」按钮

---

## 十一、项目列表增强(v1.1.0 / v1.3.0)

### 11.1 新增列

项目列表页(`ProjectList.vue`)新增以下列:

| 列 | 数据来源 | 筛选 | 排序 |
|----|---------|------|------|
| 项目经理 | `Project.pm_id` → user.name | ✓ | ✓ |
| 测试人员 | 项目组成员中的 TESTER | ✓ | ✓ |
| 外部专家 | 项目组成员中的 EXTERNAL_EXPERT | ✓ | ✓ |

### 11.2 列筛选与排序

- 每列表头点击触发筛选/排序下拉
- 筛选支持多选 + 模糊搜索
- 排序支持升序/降序切换
- 状态保持:筛选条件记忆到 URL query,刷新页面不丢失

### 11.3 组织管理者管理范围刷新

- 组织管理页(`OrgManagement.vue`)点击「编辑」后,管理范围列表立即刷新
- 不再需要手动刷新页面

---

## 十二、默认管理员密码变更(v1.3.0)

### 12.1 变更内容

| 版本 | 默认密码 |
|------|---------|
| v1.0.0 ~ v1.2.0 | `Admin@123` |
| **v1.3.0** | **`admin123`** |

### 12.2 变更原因

- 原密码包含特殊字符 `@`,在 shell 命令中需要转义,易出错
- 新密码 `admin123` 更易记忆,降低首次登录失败率
- 部署脚本 `deploy.sh`、README、DEPLOYMENT.md 已同步更新

### 12.3 安全提示

**部署后请立即修改默认密码**。可通过登录后访问「个人信息」页面修改。

---

## 十三、部署脚本增强(v1.2.0)

### 13.1 幂等迁移函数

`deploy.sh` 新增 `run_migrations()` 函数:

```bash
run_migrations() {
    # 检查 releases 表是否已有 uploaded_by 字段
    # 若无,执行 ALTER TABLE + 从 audit_logs 回填
    # 幂等:可重复执行,不报错
}
```

### 13.2 多发行版支持

自动识别 Linux 发行版并选择对应包管理器:

| 发行版 | 包管理器 |
|-------|---------|
| Ubuntu 20.04+ | apt-get |
| Debian 11+ | apt-get |
| CentOS 8+ | dnf |
| RHEL 8+ | yum |

### 13.3 一键部署

```bash
# 单命令完成全栈部署
sudo bash deploy.sh
```

包括:依赖安装 → PostgreSQL/Redis/MinIO 配置 → 后端 venv → 前端构建 → Nginx 配置 → 系统服务注册 → 数据库迁移 → 超管创建 → LLM 种子数据。

---

## 十四、API 端点汇总(v1.3.0 完整版)

### 14.1 v1.3.0 新增端点

| 端点 | 方法 | 描述 | 引入版本 |
|------|------|------|---------|
| `/api/releases/{id}/skip-review` | POST | 跳过当前评审阶段 | v1.3.0 |
| `/api/releases/{id}/force-advance` | POST | 特批放行推进流程 | v1.3.0 |
| `/api/releases/{id}/artifacts/{file_type}` | DELETE | 删除指定交付物 | v1.3.0 |
| `/api/my-tasks/todo` | GET | 我的待办任务 | v1.3.0 |
| `/api/my-tasks/done` | GET | 我的已办任务 | v1.3.0 |
| `/api/projects/{id}/versions/{vid}` | DELETE | 删除版本(权限细化) | v1.3.0 |
| `/api/projects/import` | POST | 批量导入项目 | v1.3.0 |
| `/api/users/import` | POST | 批量导入用户 | v1.3.0 |
| `/api/organizations/import` | POST | 批量导入组织 | v1.3.0 |
| `/api/projects/template` | GET | 下载项目导入模板 | v1.3.0 |
| `/api/users/template` | GET | 下载用户导入模板 | v1.3.0 |
| `/api/organizations/template` | GET | 下载组织导入模板 | v1.3.0 |
| `/api/system-settings` | GET/PUT | 系统设置(仅 super_admin) | v1.2.0 |
| `/api/system-settings/public` | GET | 公开系统设置 | v1.2.0 |
| `/api/llm-configs/{id}/test` | POST | 测试 LLM 连接 | v1.1.0 |

### 14.2 完整端点列表

参见 [OpenAPI 文档](http://localhost:8000/docs)(后端启动后自动生成)。

---

## 十五、ReleaseResponse Schema 扩展(v1.3.0)

为支持前端流水线方框布局,`ReleaseResponse` Pydantic schema 新增 `project_id` 字段:

```python
class ReleaseResponse(ReleaseBase):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None  # v1.3.0 新增
    # ... 其他字段
    
    class Config:
        from_attributes = True
```

后端通过 `_enrich_release_response()` 函数在响应时动态填充 `project_id`(通过 version join 查询)。这样前端无需再单独调用 `getReleasesByVersion()` API,可直接从 release 详情获取 `project_id` 用于版本删除等操作。

---

## 十六、技术栈变更

无新增技术栈,但以下库版本升级:

| 库 | v1.0.0 | v1.3.0 |
|----|--------|--------|
| FastAPI | 0.110+ | 0.110+ |
| SQLAlchemy | 2.0+ | 2.0+(异步) |
| Pydantic | 2+ | 2+ |
| openpyxl | — | 3.1+(用于 Excel 模板) |
| Element Plus | 2.6+ | 2.6+(`el-drawer` `:modal="false"`) |

---

## 十七、未实现的原设计项

以下原设计文档中提及但 v1.3.0 尚未实现的能力(留待后续版本):

- **外部接收方邮件通知**:目前仅站内通知,邮件发送待对接 SMTP
- **下载链接访问范围控制**:目前生成 MinIO 预签名 URL,但未限定到具体接收方
- **过程域树状管理 UI**:后端 API 已就绪,前端管理界面待补全
- **项目视图首页**:目前仅有释放视图,项目视图待实现

---

## 十八、参考链接

- [原设计文档 v1.0](./2026-07-16-qloop-design.md)
- [实现计划](../plans/2026-07-16-qloop.md)
- [部署指南](../../DEPLOYMENT.md)
- [README(中文)](../../README_zh-CN.md)
- [v1.3.0 Release Notes](https://github.com/fengtianyu88/qloop/releases/tag/v1.3.0)
- [完整 commit 历史](https://github.com/fengtianyu88/qloop/commits/main)
