# QLoop v1.5.1 测试报告

**版本**：v1.5.1
**测试日期**：2026-07-23
**测试范围**：特批放行状态机 + 分阶段标记 + 占位评审创建
**测试用例数**：14
**通过**：14
**失败**：0
**通过率**：100%

## 测试目标

验证 v1.5.1 版本的三项功能增强：

1. **RELEASED_FORCED 状态机**：释放流水线中任何阶段被特批放行时，最终状态为 `RELEASED_FORCED`（已特批释放），与 `RELEASED`（已释放）区分。
2. **force_passed 标记机制**：每个评审阶段特批放行时，标记对应阶段最近的 LLMReview 为 `force_passed=True`，并记录放行人和放行时间。
3. **占位评审创建**：当特批放行的阶段没有 LLMReview 记录时，自动创建占位评审（`force_passed=True`），确保前端能显示"特批放行"标签。

## 测试环境

- 后端：FastAPI + SQLAlchemy 2.0 async + PostgreSQL 16 + asyncpg
- 前端：Vue 3 + Element Plus + TypeScript
- Python：3.12 (venv)
- HTTP 客户端：httpx 0.27.0（同步模式）
- 数据库查询：psql 子进程

## 测试用例

| TC ID | 测试内容 | 预期结果 | 实际结果 | 状态 |
|-------|---------|---------|---------|------|
| TC-V151-01 | 健康检查 | HTTP 200, status=healthy | status=healthy | PASS |
| TC-V151-02 | admin 登录 | 获取 access_token | 登录成功 | PASS |
| TC-V151-03 | 数据库枚举包含 RELEASED_FORCED | pg_enum 包含 RELEASED_FORCED | 8 个枚举值含 RELEASED_FORCED | PASS |
| TC-V151-04 | llm_reviews 表新字段 | force_passed/force_passed_by/force_passed_at | 3 个字段齐全 | PASS |
| TC-V151-05 | /api/search/releases 过滤 | 支持 status=released_forced | 返回 0 条（无数据） | PASS |
| TC-V151-06 | ReleaseListResponse 字段 | 包含 force_passed_count | force_passed_count=0 | PASS |
| TC-V151-07 | 查找 pending_confirm release | 至少 1 条 | 找到 72b69968 | PASS |
| TC-V151-08 | 特批放行 pending_confirm | status=released_forced | 特批放行成功 | PASS |
| TC-V151-09 | 查找 code_pending_review release | 至少 1 条 | 找到 5b13abbd | PASS |
| TC-V151-10 | 代码评审特批放行 | force_passed=True | 标记成功 | PASS |
| TC-V151-11 | 查找 released release | 至少 1 条 | 找到 863465c6 | PASS |
| TC-V151-12 | 已释放 release 不允许再次特批 | 返回 400 | 400 Bad Request | PASS |
| TC-V151-13 | 详情接口 force_passed_count | 字段存在 | force_passed_count=0 | PASS |
| TC-V151-14 | LLMReviewResponse 字段 | 包含 4 个新字段 | 字段齐全 | PASS |

## 破坏性测试回滚策略

破坏性测试（TC-V151-08、TC-V151-10）在测试后通过 SQL 自动回滚：

- TC-V151-08：恢复 release 状态为 `PENDING_CONFIRM`，清理 `confirmed_by/confirmed_at/force_advanced_*`，删除可能创建的占位 review。
- TC-V151-10：恢复 release 状态为 `CODE_PENDING_REVIEW`，恢复所有 `CODE_REVIEW` 评审的 `force_passed` 原值，删除占位 review。

测试后验证：所有 release 状态分布与测试前完全一致，无数据污染。

## Bug 修复记录

### Bug #1: force_advance 用新状态查找 review_type

**现象**：对 `CODE_PENDING_REVIEW` release 特批放行后，没有标记 `code_review` 评审的 `force_passed=True`。
**根因**：`force_advance` 先执行 `release.status = next_status`，然后用 `release.status` 查找 `status_to_review_type`，导致查找的是新状态而非原状态。
**修复**：在修改 `release.status` 之前保存 `original_status = release.status`，后续用 `original_status` 查找 `status_to_review_type`。

### Bug #2: 数据库枚举值大小写不一致

**现象**：`/api/releases/{id}/force-advance` 对 `PENDING_CONFIRM` release 返回 HTTP 500。
**根因**：初次添加枚举值时用小写 `'released_forced'`，但 SQLAlchemy 用 `.name`（大写 `RELEASED_FORCED`）存储到数据库。
**修复**：`ALTER TYPE release_status RENAME VALUE 'released_forced' TO 'RELEASED_FORCED';`

## 测试结论

14 个测试用例全部通过，0 缺陷遗留。v1.5.1 的三项功能增强均已正确实现，且修复了开发过程中发现的 2 个 Bug。

