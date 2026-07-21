/**
 * 全局 TypeScript 类型定义
 * 与后端 Pydantic schema 保持一致
 */

// ---------------------------------------------------------------------------
// 枚举类型
// ---------------------------------------------------------------------------

/** 系统级角色 */
export type SystemRole = 'guest' | 'developer' | 'admin' | 'super_admin'

/** 项目内角色 */
export type ProjectRole = 'project_manager' | 'developer' | 'tester' | 'external_expert'

/** 释放状态：覆盖 7 步评审流程 */
export type ReleaseStatus =
  | 'draft'
  | 'code_pending_review'
  | 'test_pending_review'
  | 'expert_pending_review'
  | 'pending_confirm'
  | 'released'
  | 'review_failed'

/** LLM 评审类型 */
export type ReviewType = 'code_review' | 'test_report_review' | 'expert_report_review'

/** LLM 评审结果 */
export type ReviewResult = 'passed' | 'failed' | 'pending' | 'error'

/** 通知类型 */
export type NotificationType =
  | 'task_assigned'
  | 'review_failed'
  | 'review_passed'
  | 'your_turn'
  | 'release_completed'
  | 'system'

/** 组织单元类型 */
export type OrgType = 'department' | 'division' | 'group'

// ---------------------------------------------------------------------------
// 数据模型
// ---------------------------------------------------------------------------

/** 用户 */
export interface User {
  id: string
  username: string
  email: string
  full_name: string
  system_role: SystemRole
  org_unit_id: string | null
  department: string | null
  section: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** 创建用户请求 */
export interface UserCreate {
  username: string
  email: string
  full_name: string
  password: string
  system_role?: SystemRole
  org_unit_id?: string | null
  department?: string | null
  section?: string | null
}

/** 更新用户请求 */
export interface UserUpdate {
  email?: string
  full_name?: string
  system_role?: SystemRole
  org_unit_id?: string | null
  department?: string | null
  section?: string | null
  is_active?: boolean
  password?: string
}

/** 登录请求 */
export interface LoginRequest {
  username: string
  password: string
}

/** 登录响应（Token） */
export interface TokenResponse {
  access_token: string
  /** Refresh token(P1-9):用于在 access token 过期后换取新 token */
  refresh_token?: string
  token_type: string
  user_id: string
  username: string
  system_role: SystemRole
}

/** 项目成员 */
export interface ProjectMember {
  id: string
  project_id: string
  user_id: string
  project_role: ProjectRole
}

/** 添加成员请求 */
export interface ProjectMemberCreate {
  user_id: string
  project_role?: ProjectRole
}

/** 更新成员请求（修改项目内角色） */
export interface ProjectMemberUpdate {
  project_role: ProjectRole
}

/** 项目 */
export interface Project {
  id: string
  name: string
  description: string | null
  pm_user_id: string
  /** 项目经理姓名（后端 join 后填充） */
  pm_name: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  /** 项目最新动态时间（取 releases.updated_at 的最大值） */
  latest_activity_at: string | null
  members: ProjectMember[]
}

/** 创建项目请求 */
export interface ProjectCreate {
  name: string
  description?: string
}

/** 版本 */
export interface Version {
  id: string
  project_id: string
  version_number: string
  description: string | null
  developer_id: string | null
  tester_id: string | null
  expert_id: string | null
  created_at: string
  updated_at: string
}

/** 创建版本请求 */
export interface VersionCreate {
  version_number: string
  description?: string
  developer_id?: string | null
  tester_id?: string | null
  expert_id?: string | null
}

/** 外部接收方下载链接(含 access_token,功能2) */
export interface ExternalRecipientLink {
  id: string
  version_id: string
  email: string
  name: string | null
  link_expiry_hours: number
  access_scope: string
  access_token: string | null
  token_expires_at: string | null
  download_count: number
  max_downloads: number
  download_link: string | null
}

/** 释放详情 */
export interface Release {
  id: string
  version_id: string
  release_number: number
  status: ReleaseStatus
  change_notes: string | null
  code_package_path: string | null
  test_report_path: string | null
  review_report_path: string | null
  // 释放包完整性校验:SHA256(功能3)
  code_package_sha256: string | null
  test_report_sha256: string | null
  review_report_sha256: string | null
  // Uploader info for each artifact (SOX audit traceability).
  code_package_uploaded_by: string | null
  code_package_uploaded_at: string | null
  test_report_uploaded_by: string | null
  test_report_uploaded_at: string | null
  review_report_uploaded_by: string | null
  review_report_uploaded_at: string | null
  code_package_uploader_name: string | null
  test_report_uploader_name: string | null
  review_report_uploader_name: string | null
  download_link: string | null
  link_expiry: string | null
  confirmed_by: string | null
  confirmed_at: string | null
  confirmed_by_name: string | null
  // 特批放行人(功能7):PM/管理员在评审失败时强制推进的审计信息
  force_advanced_by: string | null
  force_advanced_at: string | null
  force_advanced_by_name: string | null
  created_at: string
  updated_at: string
  // Associated project ID (populated via version join in _enrich_release_response)
  project_id: string | null
}

/** 释放列表项（含关联字段） */
export interface ReleaseListItem extends Release {
  project_name: string | null
  version_number: string | null
  developer_id: string | null
  developer_name: string | null
  tester_id: string | null
  tester_name: string | null
  expert_id: string | null
  expert_name: string | null
}

/** LLM 评审记录 */
export interface LLMReview {
  id: string
  release_id: string
  review_type: ReviewType
  review_round: number
  result: ReviewResult
  total_score: number | null
  dimension_scores: Record<string, number> | null
  conclusion: string | null
  suggestions: string | null
  risk_points: string | null
  raw_response: string | null
  model_used: string | null
  triggered_by: string
  triggered_by_name: string | null
  created_at: string
  completed_at: string | null
}

/** LLM 模型配置 */
export interface LLMModel {
  id: string
  name: string
  protocol: LLMProtocol
  api_base: string
  api_key: string
  model_name: string
  is_active: boolean
  priority: number
  created_at: string
}

/** LLM API 协议 */
export type LLMProtocol = 'openai' | 'anthropic'

/** 创建/更新 LLM 模型 */
export interface LLMModelCreate {
  name: string
  protocol?: LLMProtocol
  api_base: string
  api_key: string
  model_name: string
  is_active?: boolean
  priority?: number
}

export interface LLMModelUpdate {
  name?: string
  protocol?: LLMProtocol
  api_base?: string
  api_key?: string
  model_name?: string
  is_active?: boolean
  priority?: number
}

/** LLM 模型连通性测试结果 */
export interface LLMTestResult {
  success: boolean
  message: string
  model_used: string | null
  latency_ms: number | null
}


/** 评审规则 */
export interface ReviewRule {
  id: string
  review_type: ReviewType
  llm_model_id: string
  fallback_model_id: string | null
  prompt_template: string
  pass_threshold: number
  dimension_thresholds: Record<string, unknown>
  is_active: boolean
}

/** 创建/更新评审规则 */
export interface ReviewRuleCreate {
  review_type: ReviewType
  llm_model_id: string
  fallback_model_id?: string | null
  prompt_template: string
  pass_threshold?: number
  dimension_thresholds?: Record<string, unknown>
  is_active?: boolean
}

export interface ReviewRuleUpdate {
  llm_model_id?: string
  fallback_model_id?: string | null
  prompt_template?: string
  pass_threshold?: number
  dimension_thresholds?: Record<string, unknown>
  is_active?: boolean
}

/** 触发评审响应 */
export interface TriggerReviewResponse {
  task_id: string
  release_id: string
  review_type: string
  status: string
}

/** 通知 */
export interface Notification {
  id: string
  user_id: string
  type: NotificationType
  title: string
  content: string
  is_read: boolean
  link_url: string | null
  created_at: string
}

/** 审计日志 */
export interface AuditLog {
  id: string
  user_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}

/** 组织单元 */
export interface OrgUnit {
  id: string
  name: string
  org_type: OrgType
  parent_id: string | null
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** 组织树节点 */
export interface OrgTreeNode extends OrgUnit {
  /** 该组织单元的管理员全名列表（后端 join AdminScope 后填充） */
  manager_names: string[]
  children: OrgTreeNode[]
}

/** 创建组织单元请求 */
export interface OrgUnitCreate {
  name: string
  org_type?: OrgType
  parent_id?: string | null
  description?: string
  is_active?: boolean
}

/** 更新组织单元请求 */
export interface OrgUnitUpdate {
  name?: string
  org_type?: OrgType
  parent_id?: string | null
  description?: string
  is_active?: boolean
}

/** 管理员范围 */
export interface AdminScope {
  id: string
  user_id: string
  org_unit_id: string
}

/** 创建管理员范围请求 */
export interface AdminScopeCreate {
  user_id: string
  org_unit_id: string
}

/** 外部接收人 */
export interface ExternalRecipient {
  id: string
  version_id: string
  user_id: string | null
  email: string
  name: string | null
  link_expiry_hours: number
  access_scope: string
}

// ---------------------------------------------------------------------------
// 系统设置
// ---------------------------------------------------------------------------

/** 系统设置（单例，仅 super_admin 可写） */
export interface SystemSettings {
  id: string
  site_name: string
  site_short_name: string
  email_notification_enabled: boolean
  updated_by: string | null
  updated_at: string | null
  created_at: string
}

/** 更新系统设置请求 */
export interface SystemSettingsUpdate {
  site_name?: string
  site_short_name?: string
  email_notification_enabled?: boolean
}

/** 公开站点信息（无需登录） */
export interface PublicSiteInfo {
  site_name: string
  site_short_name: string
}

// ---------------------------------------------------------------------------
// 通用响应
// ---------------------------------------------------------------------------

/** 分页响应 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages?: number
}

/** 查询参数基类 */
export interface PageParams {
  page?: number
  page_size?: number
}

/** 释放搜索参数 */
export interface ReleaseSearchParams extends PageParams {
  developer_name?: string
  project_name?: string
  version_number?: string
  change_notes?: string
  status?: ReleaseStatus
}

/** 项目搜索参数 */
export interface ProjectSearchParams extends PageParams {
  name?: string
}

/** 用户列表参数 */
export interface UserListParams extends PageParams {
  search?: string
  org_unit_id?: string
}

/** 审计日志查询参数 */
export interface AuditLogParams extends PageParams {
  action?: string
  resource_type?: string
  user_id?: string
}
