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

/** 释放状态上下文(用于精细化判断"待上传"还是"待评审") */
export interface StatusContext {
  code_package_path?: string | null
  test_report_path?: string | null
  review_report_path?: string | null
}

/** 释放状态 -> 中文标签
 *
 * 当传入 ``ctx`` 时,会根据文件是否已上传做精细化显示:
 * - 代码阶段无代码包 -> "待上传代码"; 有代码包 -> "代码待评审"
 * - 测试阶段无测试报告 -> "待上传测试报告"; 有测试报告 -> "测试报告待评审"
 *
 * 不传 ``ctx`` 时使用默认映射(向后兼容)。
 */
export function statusLabel(status: ReleaseStatus, ctx?: StatusContext): string {
  if (ctx) {
    switch (status) {
      case 'draft':
      case 'code_pending_review':
        return ctx.code_package_path ? '代码待评审' : '待上传代码'
      case 'test_pending_review':
        return ctx.test_report_path ? '测试报告待评审' : '待上传测试报告'
    }
  }
  const map: Record<ReleaseStatus, string> = {
    draft: '待上传代码',
    code_pending_review: '代码待评审',
    test_pending_review: '测试报告待评审',
    pending_confirm: '待 PM 确认',
    released: '已释放',
    released_forced: '已特批释放',
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
    pending_confirm: 'primary',
    released: 'success',
    released_forced: 'warning',
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
  }
  return map[type] ?? type
}

/** 系统角色 -> 中文标签 */
export function systemRoleLabel(role: SystemRole): string {
  const map: Record<SystemRole, string> = {
    guest: '访客',
    developer: '工程师',
    admin: '管理员',
    super_admin: '超级管理员',
  }
  return map[role] ?? role
}

/** 项目角色 -> 中文标签 */
export function roleLabel(role: ProjectRole): string {
  const map: Record<ProjectRole, string> = {
    project_manager: '项目经理',
    developer: '开发人员',
    tester: '测试人员',
  }
  return map[role] ?? role
}
