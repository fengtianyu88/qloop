/**
 * 认证 Store
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { login as loginApi } from '@/api/auth'
import { getCurrentUser } from '@/api/users'
import type { LoginRequest, SystemRole, User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  // state
  const token = ref<string>(localStorage.getItem('token') || '')
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
  async function login(payload: LoginRequest): Promise<void> {
    const res = await loginApi(payload)
    token.value = res.access_token
    localStorage.setItem('token', res.access_token)
    // 登录后拉取完整用户信息
    await fetchCurrentUser()
  }

  /** 获取当前用户信息 */
  async function fetchCurrentUser(): Promise<void> {
    if (!token.value) return
    try {
      user.value = await getCurrentUser()
    } catch {
      // 拉取失败则登出
      logout()
    }
  }

  /** 退出登录 */
  function logout(): void {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
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
