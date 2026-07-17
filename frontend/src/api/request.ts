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
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token')
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
  (error) => {
    const status = error?.response?.status
    const detail =
      error?.response?.data?.detail ||
      error?.response?.data?.message ||
      error.message ||
      '请求失败'

    if (status === 401) {
      // Token 失效或未登录
      localStorage.removeItem('token')
      ElMessage.error('登录已失效，请重新登录')
      // 跳转登录页（避免在登录页重复跳转）
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
