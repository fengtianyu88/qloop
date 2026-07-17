/**
 * 组织管理 API
 */
import request from './request'
import type {
  AdminScope,
  AdminScopeCreate,
  OrgTreeNode,
  OrgUnit,
  OrgUnitCreate,
  OrgUnitUpdate,
} from '@/types'

/** 获取组织树 */
export function getOrgTree(): Promise<OrgTreeNode[]> {
  return request.get('/organizations/tree')
}

/** 创建组织单元 */
export function createOrg(data: OrgUnitCreate): Promise<OrgUnit> {
  return request.post('/organizations', data)
}

/** 更新组织单元 */
export function updateOrg(id: string, data: OrgUnitUpdate): Promise<OrgUnit> {
  return request.put(`/organizations/${id}`, data)
}

/** 设置管理员管理范围 */
export function createAdminScope(data: AdminScopeCreate): Promise<AdminScope> {
  return request.post('/organizations/admin-scopes', data)
}

/** 获取某用户的管理范围 */
export function getAdminScopes(userId: string): Promise<AdminScope[]> {
  return request.get(`/organizations/admin-scopes/${userId}`)
}
