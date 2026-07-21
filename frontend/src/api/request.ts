/**
 * Axios 实例封装
 * - baseURL: /api（通过 Vite 代理到后端）
 * - 请求拦截器：自动附加 Bearer Token
 * - 响应拦截器：返回 response.data；401 时清除 Token 并跳转登录
 */
import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器：附加 Authorization
// P2-8: token 可能存在 localStorage(记住我)或 sessionStorage(不记住)中
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：统一处理返回数据与错误
service.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error?.response?.status
    const detail =
      error?.response?.data?.detail ||
      error?.response?.data?.message ||
      error.message ||
      '请求失败'

    // 401 时先尝试用 refresh token 换新 access token(P1-9),
    // 仅对非 /auth/refresh 与 /auth/login 请求重试一次,避免死循环。
    const originalRequest = error.config
    if (
      status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/refresh') &&
      !originalRequest.url?.includes('/auth/login')
    ) {
      // P2-8: refresh_token 优先从 localStorage 读取,其次 sessionStorage
      const refreshTokenStr =
        localStorage.getItem('refresh_token') ||
        sessionStorage.getItem('refresh_token')
      if (refreshTokenStr) {
        originalRequest._retry = true
        try {
          // 直接用 axios,绕过本拦截器避免递归
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
          // refresh 也失败,落到下方清空登录态的逻辑
        }
      }
      // 没有 refresh token 或刷新失败:清空登录态并跳登录
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('refresh_token')
      ElMessage.error('登录已失效，请重新登录')
      const currentPath = window.location.pathname
      if (currentPath !== '/login') {
        window.location.href = '/login'
      }
      return Promise.reject(error)
    }

    if (status === 401) {
      // /auth/refresh 或 /auth/login 自身返回 401:清空登录态
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('refresh_token')
      ElMessage.error('登录已失效，请重新登录')
      const currentPath = window.location.pathname
      if (currentPath !== '/login') {
        window.location.href = '/login'
      }
    } else if (status === 403) {
      ElMessage.error('没有权限执行该操作')
    } else if (status !== undefined) {
      ElMessage.error(typeof detail === 'string' ? detail : '请求失败')
    } else {
      ElMessage.error('网络异常，请检查网络连接')
    }
    return Promise.reject(error)
  },
)

export default service
