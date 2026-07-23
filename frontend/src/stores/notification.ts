/**
 * 通知 Store
 */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { getNotifications, markAllAsRead, markAsRead } from '@/api/notifications'
import type { Notification } from '@/types'

// 跨标签页通知同步 channel(SSR 或不支持 BroadcastChannel 的环境降级为 null)
let bc: BroadcastChannel | null = null
try {
  bc = new BroadcastChannel('qloop-notif')
} catch {
  bc = null
}

export const useNotificationStore = defineStore('notification', () => {
  const unreadCount = ref<number>(0)
  const notifications = ref<Notification[]>([])
  // 记录最近一次拉取错误(可选,便于调试)
  const lastError = ref<string | null>(null)

  // 监听其他标签页发来的未读数同步消息
  if (bc) {
    bc.onmessage = (event: MessageEvent) => {
      const data = event.data
      if (data?.type === 'unread' && typeof data.count === 'number') {
        unreadCount.value = data.count
      }
    }
  }

  // 当本地 unreadCount 变化时广播到其他标签页
  watch(unreadCount, (newCount) => {
    if (bc) {
      try {
        bc.postMessage({ type: 'unread', count: newCount })
      } catch {
        // 广播失败忽略
      }
    }
  })

  /** 拉取未读通知数量 */
  async function fetchUnreadCount(): Promise<void> {
    try {
      const res = await getNotifications({ unread_only: true, page: 1, page_size: 1 })
      unreadCount.value = res.total
      lastError.value = null
    } catch (e) {
      // 失败不清零,保留原值,仅记录错误
      console.error('拉取未读通知数量失败:', e)
      lastError.value = String(e)
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
    lastError,
    fetchUnreadCount,
    fetchNotifications,
    markNotificationRead,
    markAllNotificationsRead,
  }
})
