/**
 * 通知 API
 */
import request from './request'
import type { Notification, PaginatedResponse, PageParams } from '@/types'

/** 获取当前用户的通知列表 */
export function getNotifications(
  params: PageParams & { unread_only?: boolean } = {},
): Promise<PaginatedResponse<Notification>> {
  return request.get('/notifications', { params })
}

/** 标记通知为已读 */
export function markAsRead(id: string): Promise<Notification> {
  return request.post(`/notifications/${id}/read`)
}

/** 把所有未读通知标记为已读 */
export function markAllAsRead(): Promise<{ marked_read: number }> {
  return request.post('/notifications/read-all')
}
