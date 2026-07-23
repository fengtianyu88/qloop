/**
 * 认证 Store
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { login as loginApi, logout as logoutApi } from '@/api/auth'
import { getCurrentUser } from '@/api/users'
import type { LoginRequest, SystemRole, User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  // state
  // P2-8: token 初始化优先读 localStorage,再回退到 sessionStorage(不记住我场景)
  const token = ref<string>(
    localStorage.getItem('token') || sessionStorage.getItem('token') || '',
  )
  const user = ref<User | null>(null)

  // getters
  const isLoggedIn = computed<boolean>(() => !!token.value)
  const isSuperAdmin = computed<boolean>(() => user.value?.system_role === 'super_admin')
  const isAdmin = computed<boolean>(
    () => user.value?.system_role === 'admin' || user.value?.system_role === 'super_admin',
  )
  const isDeveloper = computed<boolean>(
    () =>
      user.value?.system_role === 'developer' ||
      user.value?.system_role === 'admin' ||
      user.value?.system_role === 'super_admin',
  )
  const systemRole = computed<SystemRole | null>(() => user.value?.system_role ?? null)

  // actions
  /** 登录 */
  async function login(payload: LoginRequest, remember = true): Promise<void> {
    const res = await loginApi(payload)
    token.value = res.access_token
    // P2-8: 记住我勾选时 token 存 localStorage(关闭浏览器仍保留);
    // 不勾选时存 sessionStorage(关闭浏览器即失效)
    if (remember) {
      localStorage.setItem('token', res.access_token)
      localStorage.setItem('remember_me', 'true')
      // 清理可能存在的 sessionStorage 残留
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('refresh_token')
    } else {
      sessionStorage.setItem('token', res.access_token)
      localStorage.setItem('remember_me', 'false')
      // 不记住时仍把 refresh_token 存 localStorage,便于刷新页面后尝试续期
      localStorage.removeItem('token')
    }
    // 保存 refresh token(P1-9),用于 access token 过期后换新
    if (res.refresh_token) {
      localStorage.setItem('refresh_token', res.refresh_token)
      if (!remember) {
        sessionStorage.setItem('refresh_token', res.refresh_token)
      }
    }
    // 登录后拉取完整用户信息
    await fetchCurrentUser()
  }

  /** 获取当前用户信息 */
  async function fetchCurrentUser(): Promise<void> {
    if (!token.value) return
    try {
      user.value = await getCurrentUser()
    } catch (error: any) {
      // 仅 401(token 失效)才登出;其他错误(5xx/网络)保留登录态
      if (error?.response?.status === 401) {
        await logout()
      } else {
        console.error('获取用户信息失败:', error)
        ElMessage.warning('用户信息加载失败,请检查网络')
      }
    }
  }

  /** 退出登录 */
  async function logout(): Promise<void> {
    // 先尝试调后端登出接口,失败不阻塞前端清理
    try {
      await logoutApi()
    } catch (e) {
      console.error('后端登出失败:', e)
    }
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    // 同步清理 refresh token(P1-9)
    localStorage.removeItem('refresh_token')
    // P2-7: 清理可能残留的用户相关 localStorage(如记住我、站点偏好等)
    localStorage.removeItem('user')
    localStorage.removeItem('remember_me')
    Object.keys(localStorage).forEach((key) => {
      // 清理 qloop_ 与 site_ 前缀的缓存数据
      if (key.startsWith('qloop_') || key.startsWith('site_')) {
        localStorage.removeItem(key)
      }
    })
    // P2-8: 同步清理 sessionStorage 中的会话级 token(若使用了"不记住我"模式)
    sessionStorage.removeItem('token')
    sessionStorage.removeItem('refresh_token')
  }

  return {
    token,
    user,
    isLoggedIn,
    isSuperAdmin,
    isAdmin,
    isDeveloper,
    systemRole,
    login,
    fetchCurrentUser,
    logout,
  }
})
