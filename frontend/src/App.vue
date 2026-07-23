<script setup lang="ts">
// 根组件,承载路由视图 + 全局 SSE 实时通知(功能5)
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { ElNotification, ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

const authStore = useAuthStore()
const notificationStore = useNotificationStore()

// 功能5: SSE 连接实例
let notifEventSource: EventSource | null = null

// 已弹出过的通知 ID 去重(避免 SSE 重连重放未读通知导致重复弹窗)
// 持久化到 sessionStorage，刷新页面后仍可去重
const SHOWN_NOTIF_KEY = 'qloop_shown_notif_ids'
const MAX_SHOWN_IDS = 200
const shownNotifIds = new Set<string>()

/** 从 sessionStorage 初始化已弹通知 ID 集合 */
function loadShownNotifIds() {
  try {
    const raw = sessionStorage.getItem(SHOWN_NOTIF_KEY)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr)) {
        arr.forEach((id) => shownNotifIds.add(String(id)))
      }
    }
  } catch {
    // 解析失败忽略
  }
}

/** 同步写入 sessionStorage（截断保留最近 MAX_SHOWN_IDS 个） */
function persistShownNotifIds() {
  try {
    const arr = Array.from(shownNotifIds)
    const toStore =
      arr.length > MAX_SHOWN_IDS ? arr.slice(arr.length - MAX_SHOWN_IDS) : arr
    sessionStorage.setItem(SHOWN_NOTIF_KEY, JSON.stringify(toStore))
  } catch {
    // 写入失败忽略
  }
}

// 初始化时加载已弹通知 ID
loadShownNotifIds()

// ===== SSE 重连（指数退避） =====
let reconnectAttempt = 0
const MAX_RECONNECT = 10
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

// ===== SSE 心跳检测 =====
let lastMessageTime = Date.now()
let heartbeatTimer: ReturnType<typeof setInterval> | null = null
const HEARTBEAT_CHECK_INTERVAL = 30 * 1000 // 30s 检查一次
const HEARTBEAT_TIMEOUT = 90 * 1000 // 90s 没消息则主动重连

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

  // 连接成功：重置重连计数与心跳时间
  notifEventSource.onopen = () => {
    reconnectAttempt = 0
    lastMessageTime = Date.now()
  }

  notifEventSource.onmessage = (event) => {
    lastMessageTime = Date.now()
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
      persistShownNotifIds()
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
    // 关闭当前连接，触发指数退避重连
    stopNotificationStream()
    if (reconnectAttempt < MAX_RECONNECT) {
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), 30000)
      reconnectAttempt++
      reconnectTimer = setTimeout(() => {
        startNotificationStream()
      }, delay)
    } else {
      // 超过最大重试次数，停止重连并提示用户
      ElMessage.warning('实时通知已断开，请刷新页面')
    }
  }

  // 启动心跳检测
  startHeartbeat()
}

/** 启动心跳检测：每 30s 检查一次，超过 90s 没收到消息则主动重连 */
function startHeartbeat() {
  stopHeartbeat()
  lastMessageTime = Date.now()
  heartbeatTimer = setInterval(() => {
    if (Date.now() - lastMessageTime > HEARTBEAT_TIMEOUT) {
      // 超时未收到消息，主动 close 并触发重连
      stopNotificationStream()
      if (reconnectAttempt < MAX_RECONNECT) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), 30000)
        reconnectAttempt++
        reconnectTimer = setTimeout(() => {
          startNotificationStream()
        }, delay)
      }
    }
  }, HEARTBEAT_CHECK_INTERVAL)
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

// 功能5: 关闭 SSE 通知流
function stopNotificationStream() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  stopHeartbeat()
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
      // 登录后重置重连计数
      reconnectAttempt = 0
      startNotificationStream()
    } else {
      stopNotificationStream()
    }
  },
)

onMounted(async () => {
  if (authStore.isLoggedIn) {
    // 统一初始化：拉取当前用户信息（若未加载）后启动 SSE
    if (!authStore.user) {
      try {
        await authStore.fetchCurrentUser()
      } catch {
        // fetchCurrentUser 内部已处理登出，忽略
      }
    }
    if (authStore.isLoggedIn) {
      startNotificationStream()
    }
  }
})

onBeforeUnmount(() => {
  stopNotificationStream()
})
</script>

<template>
  <ErrorBoundary>
    <router-view />
  </ErrorBoundary>
</template>
