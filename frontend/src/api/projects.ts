/**
 * 项目管理 API
 */
import request from './request'
import type {
  Project,
  ProjectCreate,
  ProjectMember,
  ProjectMemberCreate,
  Version,
  VersionCreate,
} from '@/types'

/** 获取当前用户参与的项目列表 */
export function getProjects(): Promise<Project[]> {
  return request.get('/projects')
}

/** 创建项目 */
export function createProject(data: ProjectCreate): Promise<Project> {
  return request.post('/projects', data)
}

/** 获取项目详情 */
export function getProject(id: string): Promise<Project> {
  return request.get(`/projects/${id}`)
}

/** 添加项目成员（PM） */
export function addMember(
  projectId: string,
  data: ProjectMemberCreate,
): Promise<ProjectMember> {
  return request.post(`/projects/${projectId}/members`, data)
}

/** 创建版本（PM） */
export function createVersion(
  projectId: string,
  data: VersionCreate,
): Promise<Version> {
  return request.post(`/projects/${projectId}/versions`, data)
}
