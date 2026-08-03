-- v1.5.7 数据库迁移脚本
-- 功能3: Git 集成支持
--   - users 表:新增 git_username / git_token 字段(用于以当前用户 Git 账号推送交付物)
--   - projects 表:新增 git_repo_url / git_branch 字段(由项目经理配置项目 Git 仓库)
--
-- 所有新字段均为 nullable,不影响现有数据。
-- 使用 IF NOT EXISTS 确保可重复执行(idempotent)。

-- users 表:Git 推送凭据
ALTER TABLE users ADD COLUMN IF NOT EXISTS git_username VARCHAR(200);
ALTER TABLE users ADD COLUMN IF NOT EXISTS git_token VARCHAR(500);

-- projects 表:项目 Git 仓库配置
ALTER TABLE projects ADD COLUMN IF NOT EXISTS git_repo_url VARCHAR(500);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS git_branch VARCHAR(200);
