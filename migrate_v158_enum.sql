-- v1.5.8 枚举值统一迁移脚本
-- 问题: 部分枚举列使用 SAEnum 未加 values_callable, 导致 PostgreSQL 存储
--       枚举的 .name (大写, 如 "ADMIN") 而非 .value (小写, 如 "admin")。
--       LLMProtocol 已正确使用 values_callable (存 "openai"), 其他枚举不一致。
-- 修复: 1. 为所有枚举添加 values_callable (代码层面已修改)
--       2. 本脚本将数据库中已有的大写枚举值转换为小写, 并向 PostgreSQL
--          枚举类型添加小写值 (ALTER TYPE ... ADD VALUE IF NOT EXISTS)
--
-- 幂等: 使用 IF NOT EXISTS 和条件 UPDATE, 可安全重复执行。
-- 兼容: 新部署(已有小写值)和旧部署(大写值)均可安全执行。
-- 前置: PostgreSQL 9.6+ (支持 ADD VALUE IF NOT EXISTS)

-- ===========================================================================
-- 1. system_role 枚举 (users.system_role)
--    原值: GUEST, DEVELOPER, ADMIN, SUPER_ADMIN
--    新值: guest, developer, admin, super_admin
-- ===========================================================================
ALTER TYPE system_role ADD VALUE IF NOT EXISTS 'guest';
ALTER TYPE system_role ADD VALUE IF NOT EXISTS 'developer';
ALTER TYPE system_role ADD VALUE IF NOT EXISTS 'admin';
ALTER TYPE system_role ADD VALUE IF NOT EXISTS 'super_admin';

UPDATE users SET system_role = 'guest'       WHERE system_role = 'GUEST';
UPDATE users SET system_role = 'developer'  WHERE system_role = 'DEVELOPER';
UPDATE users SET system_role = 'admin'       WHERE system_role = 'ADMIN';
UPDATE users SET system_role = 'super_admin' WHERE system_role = 'SUPER_ADMIN';

-- ===========================================================================
-- 2. project_role 枚举 (project_members.project_role)
--    原值: PROJECT_MANAGER, DEVELOPER, TESTER
--    新值: project_manager, developer, tester
-- ===========================================================================
ALTER TYPE project_role ADD VALUE IF NOT EXISTS 'project_manager';
ALTER TYPE project_role ADD VALUE IF NOT EXISTS 'developer';
ALTER TYPE project_role ADD VALUE IF NOT EXISTS 'tester';

UPDATE project_members SET project_role = 'project_manager' WHERE project_role = 'PROJECT_MANAGER';
UPDATE project_members SET project_role = 'developer'       WHERE project_role = 'DEVELOPER';
UPDATE project_members SET project_role = 'tester'           WHERE project_role = 'TESTER';

-- ===========================================================================
-- 3. release_status 枚举 (releases.status)
--    原值: DRAFT, CODE_PENDING_REVIEW, TEST_PENDING_REVIEW, PENDING_CONFIRM,
--          RELEASED, RELEASED_FORCED, REVIEW_FAILED
--    新值: draft, code_pending_review, test_pending_review, pending_confirm,
--          released, released_forced, review_failed
-- ===========================================================================
ALTER TYPE release_status ADD VALUE IF NOT EXISTS 'draft';
ALTER TYPE release_status ADD VALUE IF NOT EXISTS 'code_pending_review';
ALTER TYPE release_status ADD VALUE IF NOT EXISTS 'test_pending_review';
ALTER TYPE release_status ADD VALUE IF NOT EXISTS 'pending_confirm';
ALTER TYPE release_status ADD VALUE IF NOT EXISTS 'released';
ALTER TYPE release_status ADD VALUE IF NOT EXISTS 'released_forced';
ALTER TYPE release_status ADD VALUE IF NOT EXISTS 'review_failed';

UPDATE releases SET status = 'draft'                 WHERE status = 'DRAFT';
UPDATE releases SET status = 'code_pending_review'  WHERE status = 'CODE_PENDING_REVIEW';
UPDATE releases SET status = 'test_pending_review'  WHERE status = 'TEST_PENDING_REVIEW';
UPDATE releases SET status = 'pending_confirm'      WHERE status = 'PENDING_CONFIRM';
UPDATE releases SET status = 'released'             WHERE status = 'RELEASED';
UPDATE releases SET status = 'released_forced'      WHERE status = 'RELEASED_FORCED';
UPDATE releases SET status = 'review_failed'        WHERE status = 'REVIEW_FAILED';

-- ===========================================================================
-- 4. notification_type 枚举 (notifications.type)
--    原值: TASK_ASSIGNED, REVIEW_FAILED, REVIEW_PASSED, YOUR_TURN,
--          RELEASE_COMPLETED, SYSTEM
--    新值: task_assigned, review_failed, review_passed, your_turn,
--          release_completed, system
-- ===========================================================================
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'task_assigned';
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'review_failed';
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'review_passed';
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'your_turn';
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'release_completed';
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'system';

UPDATE notifications SET type = 'task_assigned'      WHERE type = 'TASK_ASSIGNED';
UPDATE notifications SET type = 'review_failed'      WHERE type = 'REVIEW_FAILED';
UPDATE notifications SET type = 'review_passed'      WHERE type = 'REVIEW_PASSED';
UPDATE notifications SET type = 'your_turn'          WHERE type = 'YOUR_TURN';
UPDATE notifications SET type = 'release_completed'  WHERE type = 'RELEASE_COMPLETED';
UPDATE notifications SET type = 'system'              WHERE type = 'SYSTEM';

-- ===========================================================================
-- 5. review_type 枚举 (review_rules.review_type)
--    原值: CODE_REVIEW, TEST_REPORT_REVIEW
--    新值: code_review, test_report_review
-- ===========================================================================
ALTER TYPE review_type ADD VALUE IF NOT EXISTS 'code_review';
ALTER TYPE review_type ADD VALUE IF NOT EXISTS 'test_report_review';

UPDATE review_rules SET review_type = 'code_review'         WHERE review_type = 'CODE_REVIEW';
UPDATE review_rules SET review_type = 'test_report_review'  WHERE review_type = 'TEST_REPORT_REVIEW';

-- ===========================================================================
-- 6. llm_review_type 枚举 (llm_reviews.review_type)
--    原值: CODE_REVIEW, TEST_REPORT_REVIEW
--    新值: code_review, test_report_review
-- ===========================================================================
ALTER TYPE llm_review_type ADD VALUE IF NOT EXISTS 'code_review';
ALTER TYPE llm_review_type ADD VALUE IF NOT EXISTS 'test_report_review';

UPDATE llm_reviews SET review_type = 'code_review'         WHERE review_type = 'CODE_REVIEW';
UPDATE llm_reviews SET review_type = 'test_report_review'  WHERE review_type = 'TEST_REPORT_REVIEW';

-- ===========================================================================
-- 7. review_result 枚举 (llm_reviews.result)
--    原值: PASSED, FAILED, PENDING, ERROR
--    新值: passed, failed, pending, error
-- ===========================================================================
ALTER TYPE review_result ADD VALUE IF NOT EXISTS 'passed';
ALTER TYPE review_result ADD VALUE IF NOT EXISTS 'failed';
ALTER TYPE review_result ADD VALUE IF NOT EXISTS 'pending';
ALTER TYPE review_result ADD VALUE IF NOT EXISTS 'error';

UPDATE llm_reviews SET result = 'passed'  WHERE result = 'PASSED';
UPDATE llm_reviews SET result = 'failed'  WHERE result = 'FAILED';
UPDATE llm_reviews SET result = 'pending'  WHERE result = 'PENDING';
UPDATE llm_reviews SET result = 'error'   WHERE result = 'ERROR';

-- ===========================================================================
-- 8. llm_protocol 枚举 (llm_models.protocol)
--    已使用 values_callable, 原值就是小写, 无需迁移。
--    但为安全起见, 检查是否有大写值残留。
-- ===========================================================================
-- llm_protocol 已使用 values_callable, 正常情况下值已经是小写, 无需操作。
-- 如果有异常数据, 可取消注释以下语句:
-- ALTER TYPE llm_protocol ADD VALUE IF NOT EXISTS 'openai';
-- ALTER TYPE llm_protocol ADD VALUE IF NOT EXISTS 'anthropic';
-- UPDATE llm_models SET protocol = 'openai'    WHERE protocol = 'OPENAI';
-- UPDATE llm_models SET protocol = 'anthropic' WHERE protocol = 'ANTHROPIC';
