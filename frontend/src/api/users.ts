/**
 * 用户管理 API
 */
import request from './request'
import type {
  PaginatedResponse,
  User,
  UserCreate,
  UserListParams,
  UserUpdate,
} from '@/types'

/** 分页获取用户列表 */
export function getUsers(
  params: UserListParams = {},
): Promise<PaginatedResponse<User>> {
  return request.get('/users', { params })
}

/** 创建用户 */
export function createUser(data: UserCreate): Promise<User> {
  return request.post('/users', data)
}

/** 获取单个用户 */
export function getUser(id: string): Promise<User> {
  return request.get(`/users/${id}`)
}

/** 更新用户 */
export function updateUser(id: string, data: UserUpdate): Promise<User> {
  return request.put(`/users/${id}`, data)
}

/** 禁用用户（软删除） */
export function deleteUser(id: string): Promise<void> {
  return request.delete(`/users/${id}`)
}

/** 获取当前登录用户信息 */
export function getCurrentUser(): Promise<User> {
  return request.get('/users/me')
}

/** 修改自己的密码 */
export function changeMyPassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ message: string }> {
  return request.put('/users/me/password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

/** 更新自己的 Git 推送凭据（git_username / git_token）
 *
 * 传入空字符串会清除对应字段。仅返回 has_git_token 标记,不返回 token 原文。
 */
export function updateMyGitCredentials(
  gitUsername?: string | null,
  gitToken?: string | null,
): Promise<{
  message: string
  has_git_token: boolean
  git_username: string | null
}> {
  return request.put('/users/me/git', {
    git_username: gitUsername ?? null,
    git_token: gitToken ?? null,
  })
}
