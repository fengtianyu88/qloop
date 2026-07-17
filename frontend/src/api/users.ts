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
