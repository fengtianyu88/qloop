/**
 * Axios 实例封装
 * - baseURL: /api（通过 Vite 代理到后端）
 * - 请求拦截器：自动附加 Bearer Token
 * - 响应拦截器：返回 response.data；401 时尝试 refresh token 后跳转登录
 * - 增强：
 *   1) GET 请求 5xx/网络错误重试（指数退避，最多 2 次）
 *   2) createAbortController 工具函数（支持手动取消）
 *   3) POST/PUT/DELETE/PATCH 请求去重（同 key 取消旧请求）
 *   4) 401 跳转改 router.push（避免整页刷新）
 *   5) 差异化超时（默认 15000ms，调用方可通过 config.timeout 覆盖）
 *   6) 网络错误细分提示
 */
import axios, {
  type AxiosInstance,
  type InternalAxiosRequestConfig,
  type AxiosError,
} from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

// 扩展 axios 配置类型，支持自定义标志位
declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 401 refresh 重试标志，防止死循环 */
    _retry?: boolean
    /** 5xx/网络错误已重试次数 */
    _retryCount?: number
    /** 写操作是否允许重试（默认 false，GET 自动重试） */
    _retryable?: boolean
    /** 去重缓存的 key（自动生成） */
    _dedupeKey?: string
    /** 是否关闭去重（默认 true，对写操作生效） */
    dedupe?: boolean
  }
}

const MAX_RETRY = 2
const DEFAULT_TIMEOUT = 15000

const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: DEFAULT_TIMEOUT,
})

// 请求去重：维护 pending 请求表，key=`${method}:${url}`
const pendingRequests = new Map<string, AbortController>()

function getRequestKey(config: InternalAxiosRequestConfig): string {
  return `${(config.method || 'get').toLowerCase()}:${config.url || ''}`
}

/** 请求完成后从 pending 表移除 */
function removePending(config: InternalAxiosRequestConfig) {
  if (!config) return
  const key = config._dedupeKey || getRequestKey(config)
  if (pendingRequests.has(key)) {
    pendingRequests.delete(key)
  }
}

/** 写操作（POST/PUT/DELETE/PATCH）入 pending 表，相同 key 取消旧请求 */
function addPending(config: InternalAxiosRequestConfig) {
  const method = (config.method || 'get').toLowerCase()
  const isWrite = ['post', 'put', 'delete', 'patch'].includes(method)
  if (!isWrite || config.dedupe === false) return
  const key = getRequestKey(config)
  config._dedupeKey = key
  // 已有相同 key 的 pending 请求：取消旧的
  const existing = pendingRequests.get(key)
  if (existing) {
    existing.abort()
  }
  // 调用方未传 signal 时，创建新的 AbortController 用于去重取消
  if (!config.signal) {
    const controller = new AbortController()
    config.signal = controller.signal
    pendingRequests.set(key, controller)
  }
}

// 请求拦截器：附加 Authorization + 注入去重逻辑
// P2-8: token 可能存在 localStorage(记住我)或 sessionStorage(不记住)中
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    addPending(config)
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：统一处理返回数据与错误
service.interceptors.response.use(
  (response) => {
    removePending(response.config)
    return response.data
  },
  async (error) => {
    const status = error?.response?.status
    const detail =
      error?.response?.data?.detail ||
      error?.response?.data?.message ||
      error.message ||
      '请求失败'
    const originalRequest: InternalAxiosRequestConfig | undefined = error.config

    // 请求完成后从 pending 移除（避免被取消后未清理）
    if (originalRequest) {
      removePending(originalRequest)
    }

    // 取消错误（被去重逻辑或其他 abort 取消），静默拒绝
    if (axios.isCancel(error) || error?.code === 'ERR_CANCELED') {
      return Promise.reject(error)
    }

    // ===== 5xx / 网络错误重试 =====
    // 仅对 GET 重试；POST 等写操作仅在 config._retryable === true 时重试
    const method = (originalRequest?.method || 'get').toLowerCase()
    const isRetryableMethod = method === 'get' || originalRequest?._retryable === true
    const isServerError = status !== undefined && status >= 500
    const isRetryableNetwork =
      status === undefined &&
      (error?.code === 'ECONNABORTED' || error?.code === 'ERR_NETWORK')
    const retryCount = originalRequest?._retryCount || 0

    if (
      originalRequest &&
      isRetryableMethod &&
      (isServerError || isRetryableNetwork) &&
      retryCount < MAX_RETRY
    ) {
      originalRequest._retryCount = retryCount + 1
      // 指数退避：500ms * 2^n + 随机抖动（0-200ms）
      const delay =
        500 * Math.pow(2, originalRequest._retryCount - 1) +
        Math.floor(Math.random() * 200)
      await new Promise((resolve) => setTimeout(resolve, delay))
      return service(originalRequest)
    }

    // ===== 401 处理：先尝试用 refresh token 换新 access token (P1-9) =====
    // 仅对非 /auth/refresh 与 /auth/login 请求重试一次，避免死循环。
    if (
      status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/refresh') &&
      !originalRequest.url?.includes('/auth/login')
    ) {
      // P2-8: refresh_token 优先从 localStorage 读取，其次 sessionStorage
      const refreshTokenStr =
        localStorage.getItem('refresh_token') ||
        sessionStorage.getItem('refresh_token')
      if (refreshTokenStr) {
        originalRequest._retry = true
        try {
          // 直接用 axios，绕过本拦截器避免递归
          const refreshRes = await axios.post('/api/auth/refresh', {
            refresh_token: refreshTokenStr,
          })
          const newAccessToken = refreshRes?.data?.access_token
          if (newAccessToken) {
            // P2-8: 根据原 token 存储位置回写新 token
            if (sessionStorage.getItem('token')) {
              sessionStorage.setItem('token', newAccessToken)
            } else {
              localStorage.setItem('token', newAccessToken)
            }
            originalRequest.headers = originalRequest.headers || {}
            originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
            return service(originalRequest)
          }
        } catch {
          // refresh 也失败，落到下方清空登录态的逻辑
        }
      }
      // 没有 refresh token 或刷新失败：清空登录态并跳登录
      clearAuthAndRedirect()
      return Promise.reject(error)
    }

    if (status === 401) {
      // /auth/refresh 或 /auth/login 自身返回 401：清空登录态
      clearAuthAndRedirect()
    } else if (status === 403) {
      ElMessage.error('没有权限执行该操作')
    } else if (status !== undefined) {
      ElMessage.error(typeof detail === 'string' ? detail : '请求失败')
    } else {
      // 网络错误细分
      ElMessage.error(getNetworkErrorMessage(error))
    }
    return Promise.reject(error)
  },
)

/** 清空登录态并跳转登录页（router.push 避免整页刷新丢失状态） */
function clearAuthAndRedirect() {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh_token')
  sessionStorage.removeItem('token')
  sessionStorage.removeItem('refresh_token')
  ElMessage.error('登录已失效，请重新登录')
  const currentPath = router.currentRoute.value.path
  if (currentPath !== '/login') {
    router.push({
      path: '/login',
      query: { redirect: router.currentRoute.value.fullPath },
    })
  }
}

/** 网络错误细分提示（status === undefined 时） */
function getNetworkErrorMessage(error: AxiosError): string {
  if (error?.code === 'ECONNABORTED') {
    return '请求超时，请稍后重试'
  }
  if (error?.code === 'ERR_NETWORK') {
    return '网络连接失败，请检查网络'
  }
  return '网络异常，请检查网络连接'
}

/** 创建 AbortController，供调用方手动取消请求 */
export function createAbortController(): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController()
  return {
    signal: controller.signal,
    cancel: () => controller.abort(),
  }
}

export default service
