/**
 * 系统设置 API
 */
import request from './request'
import type { SystemSettings, SystemSettingsUpdate, PublicSiteInfo } from '@/types'

/** 获取系统设置（仅 super_admin） */
export function getSystemSettings(): Promise<SystemSettings> {
  return request.get('/system-settings')
}

/** 更新系统设置（仅 super_admin） */
export function updateSystemSettings(
  data: SystemSettingsUpdate,
): Promise<SystemSettings> {
  return request.put('/system-settings', data)
}

/** 获取公开站点信息（无需登录，登录页/布局使用） */
export function getPublicSiteInfo(): Promise<PublicSiteInfo> {
  return request.get('/system-settings/public')
}
