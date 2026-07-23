/**
 * 组织管理 API
 */
import request from './request'
import type {
  AdminScope,
  AdminScopeCreate,
  OrgTreeNode,
  OrgTypeCreate,
  OrgTypeItem,
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


/** 删除一个管理范围（解除某用户对该组织单元的管理员身份） */
export function deleteAdminScope(scopeId: string): Promise<void> {
  return request.delete(`/organizations/admin-scopes/${scopeId}`)
}

/** 获取某组织单元的所有管理者（含 user_id/full_name/username） */
export function getOrgAdminScopes(orgId: string): Promise<Array<{
  id: string
  user_id: string
  full_name: string
  username: string
}>> {
  return request.get(`/organizations/org-units/${orgId}/admin-scopes`)
}

/** 删除组织单元(SUPER_ADMIN) */
export function deleteOrg(id: string): Promise<void> {
  return request.delete(`/organizations/${id}`)
}


// ---------------------------------------------------------------------------
// 组织类型管理 v1.5.2
// ---------------------------------------------------------------------------

/** 获取所有组织类型 */
export function getOrgTypes(): Promise<OrgTypeItem[]> {
  return request.get('/org-types')
}

/** 创建组织类型 */
export function createOrgType(data: OrgTypeCreate): Promise<OrgTypeItem> {
  return request.post('/org-types', data)
}

/** 删除组织类型(SUPER_ADMIN only) */
export function deleteOrgType(id: string): Promise<void> {
  return request.delete(`/org-types/${id}`)
}
