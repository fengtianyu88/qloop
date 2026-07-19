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


/**
 * 导出当前用户能访问的所有数据（释放 + 项目），返回 CSV blob。
 * 浏览器侧用 <a download> 触发下载。
 */
export async function exportAll(): Promise<Blob> {
  const res = await request.get('/search/export', {
    responseType: 'blob',
  })
  return res as unknown as Blob
}
