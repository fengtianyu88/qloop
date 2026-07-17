/**
 * 搜索 API
 */
import request from './request'
import type {
  PaginatedResponse,
  Project,
  ProjectSearchParams,
  ReleaseListItem,
  ReleaseSearchParams,
} from '@/types'

/** 搜索释放记录 */
export function searchReleases(
  params: ReleaseSearchParams = {},
): Promise<PaginatedResponse<ReleaseListItem>> {
  return request.get('/search/releases', { params })
}

/** 搜索项目 */
export function searchProjects(
  params: ProjectSearchParams = {},
): Promise<PaginatedResponse<Project>> {
  return request.get('/search/projects', { params })
}
