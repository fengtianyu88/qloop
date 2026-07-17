/**
 * 认证相关 API
 */
import request from './request'
import type { LoginRequest, TokenResponse } from '@/types'

/** 登录 */
export function login(data: LoginRequest): Promise<TokenResponse> {
  return request.post('/auth/login', data)
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
