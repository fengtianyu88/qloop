<script setup lang="ts">
// 根组件,承载路由视图 + 全局 SSE 实时通知(功能5)
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { ElNotification } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

const authStore = useAuthStore()
const notificationStore = useNotificationStore()

// 功能5: SSE 连接实例
let notifEventSource: EventSource | null = null

// 已弹出过的通知 ID 去重(避免 SSE 重连重放未读通知导致重复弹窗)
const shownNotifIds = new Set<string>()
const MAX_SHOWN_IDS = 200

// 功能5: 启动 SSE 通知流
function startNotificationStream() {
  stopNotificationStream()
  const token = localStorage.getItem('token')
  if (!token) return
  // EventSource 不支持自定义 header,通过 query 参数传 token
  const url = `/api/notifications/stream?token=${encodeURIComponent(token)}`
  try {
    notifEventSource = new EventSource(url)
  } catch {
    notifEventSource = null
    return
  }

  notifEventSource.onmessage = (event) => {
    let notif: any
    try {
      notif = JSON.parse(event.data)
    } catch {
      return  // 忽略无法解析的消息
    }
    if (notif.error) return  // 错误事件静默处理
    // 去重:同一条通知不重复弹出(SSE 重连重放未读通知时跳过)
    const notifId = String(notif.id ?? '')
    if (notifId && shownNotifIds.has(notifId)) {
      return
    }
    if (notifId) {
      shownNotifIds.add(notifId)
      // 限制 Set 大小,避免长时间运行后无限增长
      if (shownNotifIds.size > MAX_SHOWN_IDS) {
        const first = shownNotifIds.values().next().value
        if (first) shownNotifIds.delete(first)
      }
    }
    // 弹出桌面通知
    const typeMap: Record<string, 'success' | 'warning' | 'info' | 'error'> = {
      review_failed: 'error',
      review_passed: 'success',
      task_assigned: 'info',
      your_turn: 'warning',
      release_completed: 'success',
      system: 'info',
    }
    ElNotification({
      title: notif.title || '新通知',
      message: notif.content || '',
      type: typeMap[notif.type] || 'info',
      duration: 5000,
    })
    // 刷新未读数(notification store 暴露 fetchUnreadCount)
    try {
      notificationStore.fetchUnreadCount()
    } catch {
      // 忽略,不影响主流程
    }
  }

  notifEventSource.onerror = () => {
    // 连接异常时关闭,后续可由登录态变化重连
    stopNotificationStream()
  }
}

// 功能5: 关闭 SSE 通知流
function stopNotificationStream() {
  if (notifEventSource) {
    notifEventSource.close()
    notifEventSource = null
  }
}

// 监听登录状态:登录后启动 SSE,登出后停止
watch(
  () => authStore.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      startNotificationStream()
    } else {
      stopNotificationStream()
    }
  },
)

onMounted(() => {
  if (authStore.isLoggedIn) {
    startNotificationStream()
  }
})

onBeforeUnmount(() => {
  stopNotificationStream()
})
</script>

<template>
  <router-view />
</template>
