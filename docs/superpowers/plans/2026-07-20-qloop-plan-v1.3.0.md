# qloop — 实现计划 v1.3.0 更新

> 日期：2026-07-20
> 基线版本：[2026-07-16-qloop.md](./2026-07-16-qloop.md) (v1.0.0)
> 当前版本：v1.3.0
> 状态：v1.0 ~ v1.3 已实现并发布

---

## 0. 实现进度摘要

| 阶段 | v1.0.0 | v1.1.0 | v1.2.0 | v1.3.0 |
|------|--------|--------|--------|--------|
| Phase 1: 数据模型 | ✓ | ✓ | ✓ +6 字段 | ✓ +project_id schema |
| Phase 2: 认证用户 | ✓ | ✓ | ✓ | ✓ +批量导入 |
| Phase 3: 组织项目 | ✓ | ✓ | ✓ +成员管理 | ✓ +权限细化 |
| Phase 4: LLM 评审 | ✓ | ✓ +M3 解析 | ✓ +双协议 | ✓ +测试按钮 |
| Phase 5: 首页通知审计 | ✓ | ✓ | ✓ +SOX 审计 | ✓ +待办已办 |
| Phase 6: 前端 UI | ✓ | ✓ +表头筛选 | ✓ +站点品牌 | ✓ +流水线布局 |

---

## 一、v1.3.0 已实现的阶段

### Phase 7: 释放详情页可视化 + 评审流程优化 (Task 24-27)

- **Task 24**: 释放详情页流水线方框布局
  - 5 个步骤方框从上往下排列
  - 左侧颜色条标识状态(灰/蓝/橙/绿/红)
  - 圆圈序号 + 两栏布局(信息+操作)
  - 所有字段集中在同一方框内
  - 实现文件:[ReleaseDetail.vue](file:///opt/qloop/frontend/src/views/ReleaseDetail.vue)

- **Task 25**: LLM 评审进度抽屉
  - 右侧 el-drawer 实时显示 LLM 输出
  - `:modal="false"` 不阻挡页面
  - 可收缩/展开切换
  - 3 秒轮询评审任务状态

- **Task 26**: 稍后评审 + 特批放行 API
  - `POST /api/releases/{id}/skip-review`
  - `POST /api/releases/{id}/force-advance`
  - 权限:skip 按上传人 + admin;force 按 PM + admin
  - 实现文件:[release_service.py](file:///opt/qloop/backend/app/services/release_service.py) `skip_review()` / `force_advance()`

- **Task 27**: 版本/交付物删除权限细化
  - 版本删除:super_admin 任意,admin 仅未释放
  - 交付物删除:admin 任意,其他角色仅自己上传
  - `DELETE /api/releases/{id}/artifacts/{file_type}`
  - 实现:`minio_delete_object()` + `delete_artifact()`

### Phase 8: 首页与批量操作 (Task 28-31)

- **Task 28**: 首页待办/已办窗格
  - 等高布局 + 滚动支持
  - `GET /api/my-tasks/todo` 和 `/done`
  - 点击跳转 release 详情
  - 实现文件:[Home.vue](file:///opt/qloop/frontend/src/views/Home.vue)

- **Task 29**: 批量导入/导出
  - 项目/用户/组织三个管理页
  - Excel 模板下载 + 批量导入
  - 仅 admin/super_admin 可见按钮
  - 后端用 openpyxl 生成/解析 Excel

- **Task 30**: 项目列表表头筛选排序
  - 新增 PM/测试/专家列
  - 每列支持筛选(多选+模糊)+ 排序
  - 状态保持到 URL query

- **Task 31**: 组织管理者管理范围刷新
  - 点击编辑后立即刷新列表
  - 修复了原需手动刷新的问题

### Phase 9: LLM 配置增强 (Task 32-34)

- **Task 32**: LLM 测试按钮
  - 配置页右上角「测试连接」
  - 发送简单 prompt 验证配置可用性

- **Task 33**: LLM 模型/规则物理删除
  - 原仅软删除,现支持物理删除
  - super_admin 权限

- **Task 34**: MiniMax-M3 解析器 Layout D-J
  - 适配 M3 模型的输出格式
  - 新增 4 种 Layout 模式

### Phase 10: 系统设置与品牌 (Task 35-36)

- **Task 35**: 系统设置 API
  - `GET/PUT /api/system-settings` (super_admin)
  - `GET /api/system-settings/public` (公开)
  - 实现:[SystemSettings.vue](file:///opt/qloop/frontend/src/views/SystemSettings.vue)

- **Task 36**: 站点品牌前端缓存
  - Pinia `siteInfo` store + localStorage
  - 跨标签页同步(custom event)

### Phase 11: SOX 合规增强 (Task 37-39)

- **Task 37**: Release 详情页显示上传人/触发人
  - 数据库新增 6 个 uploaded_by/uploaded_at 字段
  - 从 audit_logs 回填历史数据
  - 前端在每个节点显示操作人姓名和时间

- **Task 38**: 下载审计日志
  - 下载代码包/测试报告/评审报告时自动写入审计日志
  - 记录:user_id、resource_id、file_type、size_bytes

- **Task 39**: 下载链接 7 天有效期
  - MinIO 预签名 URL 统一 168 小时有效期
  - PM 确认释放时生成,存入 download_link + link_expiry

### Phase 12: 部署脚本增强 (Task 40-41)

- **Task 40**: 幂等迁移函数
  - `run_migrations()` 函数
  - 支持 ALTER TABLE + 历史数据回填
  - 可重复执行不报错

- **Task 41**: 多发行版支持
  - Ubuntu/Debian: apt-get
  - CentOS/RHEL: dnf/yum
  - 自动识别并选择包管理器

---

## 二、v1.3.0 实现的关键技术决策

### 2.1 ReleaseResponse 动态字段填充

为避免前端单独调用 `getReleasesByVersion()` API 获取 `project_id`,在后端 `_enrich_release_response()` 中通过 version join 查询动态填充:

```python
async def _enrich_release_response(release: Release) -> ReleaseResponse:
    resp = ReleaseResponse.model_validate(release)
    # 通过 version join 查询 project_id
    version = await get_version_by_id(db, release.version_id)
    if version:
        resp.project_id = version.project_id
    return resp
```

### 2.2 权限判断统一函数

前端权限判断统一通过 computed 属性:

```ts
const canSkipReview = computed(() => {
  if (!release.value || !authStore.user) return false
  const status = release.value.status
  const reviewStages = ['code_pending_review', 'test_pending_review', 'expert_pending_review']
  if (!reviewStages.includes(status)) return false
  if (authStore.isAdmin) return true
  // 按当前状态对应的上传人判断
  ...
})

const canForceAdvance = computed(() => {
  if (!release.value || !authStore.user) return false
  if (authStore.isAdmin) return true
  return false  // PM 走原确认释放按钮
})
```

### 2.3 流水线方框状态计算

```ts
function getStepStatus(stepNum: number): StepStatus {
  const status = release.value?.status
  const statusOrder = [
    'draft', 'code_pending_review', 'test_pending_review',
    'expert_pending_review', 'pending_confirm', 'released'
  ]
  const currentIdx = statusOrder.indexOf(status)
  const stepIdx = stepNum - 1
  if (status === 'review_failed' && stepIdx === currentIdx) return 'failed'
  if (stepIdx < currentIdx) return 'completed'
  if (stepIdx === currentIdx) return 'current'
  return 'not_started'
}
```

---

## 三、v1.3.0 提交记录

| Commit | 描述 |
|--------|------|
| `163f7bf` | docs: bump version to 1.3.0 with changelog and password update |
| `eacd1a8` | feat: 释放详情页流水线方框布局 + 稍后评审/特批放行按钮 |
| `f745f13` | feat: 待办已办窗格对齐 + LLM 评审进度抽屉 |
| `a7a39d7` | feat: 版本删除权限细化 + 交付物删除 API |
| `3f8899d` | feat: 释放详情页新增交付物卡片(所有状态可见+下载) |
| `e4a15f7` | feat: 版本删除+待办已办+批量导入三大功能 |
| `a233c3b` | feat: 组织管理者点击编辑+管理范围立即刷新/项目页每列筛选排序 |
| `5d8d31b` | feat: 增加 LLM 测试按钮/组织管理者姓名/项目表头筛选排序 |
| `6269bb7` | feat: configurable site brand + README overhaul |
| `7502d52` | feat: project member management - add/edit/remove with permission rules |
| `d5e4d74` | docs: update default admin password from Admin@123 to admin123 |
| `ef885b7` | fix: Home/ProjectDetail 403 + ReleaseListResponse 500 |
| `1d94e5b` | fix: raise /api/users page_size limit to 500 |
| `45967ae` | feat: LLM model/rule physical delete + MiniMax-M3 parser Layout D-J |

---

## 四、待实现项(后续版本)

参考 [设计文档 v1.3.0 第十七节](../specs/2026-07-20-qloop-design-v1.3.0.md#十七未实现的原设计项):

- 外部接收方邮件通知(对接 SMTP)
- 下载链接访问范围控制(限定到具体接收方)
- 过程域树状管理 UI
- 项目视图首页
