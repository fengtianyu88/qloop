/**
 * 认证相关 API
 */
import axios from 'axios'
import request from './request'
import type { LoginRequest, TokenResponse } from '@/types'

/** 登录 */
export function login(data: LoginRequest): Promise<TokenResponse> {
  return request.post('/auth/login', data)
}

/** 退出登录 */
export function logout(): Promise<void> {
  return request.post('/auth/logout')
}

/**
 * 刷新 access token(P1-9)
 * 用 refresh token 换取新的 access token;refresh token 失效时抛 401。
 * 注意:本函数走原生 axios,避免触发 request.ts 的 401 拦截器形成死循环。
 */
export async function refreshToken(refreshToken: string): Promise<string> {
  const res = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
  return res.data.access_token
}

/** 注册 */
export function register(data: {
  username: string
  email: string
  full_name: string
  password: string
  department?: string
  section?: string
}): Promise<any> {
  return request.post('/auth/register', data)
}

/** 忘记密码 - 发送重置邮件 */
export function forgotPassword(email: string): Promise<any> {
  return request.post('/auth/forgot-password', { email })
}

/** 重置密码 */
export function resetPassword(token: string, new_password: string): Promise<any> {
  return request.post('/auth/reset-password', { token, new_password })
}
