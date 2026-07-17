/**
 * 审计日志 API
 */
import request from './request'
import type { AuditLog, AuditLogParams, PaginatedResponse } from '@/types'

/** 分页获取审计日志 */
export function getAuditLogs(
  params: AuditLogParams = {},
): Promise<PaginatedResponse<AuditLog>> {
  return request.get('/audit', { params })
}
