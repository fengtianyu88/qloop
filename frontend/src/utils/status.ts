/**
 * 状态/角色等显示工具函数
 */
import type {
  ProjectRole,
  ReleaseStatus,
  ReviewResult,
  ReviewType,
  SystemRole,
} from '@/types'

/** 释放状态 -> 中文标签 */
export function statusLabel(status: ReleaseStatus): string {
  const map: Record<ReleaseStatus, string> = {
    draft: '草稿',
    code_pending_review: '代码待评审',
    test_pending_review: '测试报告待评审',
    expert_pending_review: '专家报告待评审',
    pending_confirm: '待 PM 确认',
    released: '已释放',
    review_failed: '评审未通过',
  }
  return map[status] ?? status
}

/** 释放状态 -> el-tag 类型 */
export function statusTagType(status: ReleaseStatus): string {
  const map: Record<ReleaseStatus, string> = {
    draft: 'info',
    code_pending_review: 'warning',
    test_pending_review: 'warning',
    expert_pending_review: 'warning',
    pending_confirm: 'primary',
    released: 'success',
    review_failed: 'danger',
  }
  return map[status] ?? 'info'
}

/** 评审结果 -> 中文标签 */
export function reviewResultLabel(result: ReviewResult): string {
  const map: Record<ReviewResult, string> = {
    passed: '通过',
    failed: '未通过',
    pending: '评审中',
    error: '评审异常',
  }
  return map[result] ?? result
}

/** 评审结果 -> el-tag 类型 */
export function reviewResultTagType(result: ReviewResult): string {
  const map: Record<ReviewResult, string> = {
    passed: 'success',
    failed: 'danger',
    pending: 'warning',
    error: 'info',
  }
  return map[result] ?? 'info'
}

/** 评审类型 -> 中文标签 */
export function reviewTypeLabel(type: ReviewType): string {
  const map: Record<ReviewType, string> = {
    code_review: '代码评审',
    test_report_review: '测试报告评审',
    expert_report_review: '专家报告评审',
  }
  return map[type] ?? type
}

/** 角色（系统角色 / 项目角色） -> 中文标签 */
export function roleLabel(role: SystemRole | ProjectRole): string {
  const map: Record<string, string> = {
    guest: '访客',
    developer: '开发人员',
    admin: '管理员',
    super_admin: '超级管理员',
    project_manager: '项目经理',
    tester: '测试人员',
    external_expert: '外部专家',
  }
  return map[role] ?? role
}
