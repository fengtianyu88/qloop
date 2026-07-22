/**
 * 通知 Store
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getNotifications, markAllAsRead, markAsRead } from '@/api/notifications'
import type { Notification } from '@/types'

export const useNotificationStore = defineStore('notification', () => {
  const unreadCount = ref<number>(0)
  const notifications = ref<Notification[]>([])

  /** 拉取未读通知数量 */
  async function fetchUnreadCount(): Promise<void> {
    try {
      const res = await getNotifications({ unread_only: true, page: 1, page_size: 1 })
      unreadCount.value = res.total
    } catch {
      // 忽略错误，避免影响主流程
      unreadCount.value = 0
    }
  }

  /** 拉取通知列表 */
  async function fetchNotifications(
    params: { unread_only?: boolean; page?: number; page_size?: number } = {},
  ): Promise<{ items: Notification[]; total: number }> {
    const res = await getNotifications(params)
    notifications.value = res.items
    return { items: res.items, total: res.total }
  }

  /** 标记单条通知为已读 */
  async function markNotificationRead(id: string): Promise<void> {
    await markAsRead(id)
    const target = notifications.value.find((n) => n.id === id)
    if (target) {
      target.is_read = true
    }
    if (unreadCount.value > 0) {
      unreadCount.value -= 1
    }
  }

  /** 把所有未读通知标记为已读 */
  async function markAllNotificationsRead(): Promise<number> {
    const res = await markAllAsRead()
    // 把当前列表中的未读通知也标记为已读
    notifications.value.forEach((n) => {
      if (!n.is_read) n.is_read = true
    })
    unreadCount.value = 0
    return res.marked_read || 0
  }

  return {
    unreadCount,
    notifications,
    fetchUnreadCount,
    fetchNotifications,
    markNotificationRead,
    markAllNotificationsRead,
  }
})
