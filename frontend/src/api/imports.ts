/** 批量导入 + 模板下载 API */
import request from './request'

export interface ImportResult {
  success: number
  failed: number
  errors: string[]
}

/** 下载项目导入模板 */
export function downloadProjectsTemplate(): Promise<Blob> {
  return request.get('/import/projects/template', { responseType: 'blob' })
}

/** 下载用户导入模板 */
export function downloadUsersTemplate(): Promise<Blob> {
  return request.get('/import/users/template', { responseType: 'blob' })
}

/** 下载组织导入模板 */
export function downloadOrganizationsTemplate(): Promise<Blob> {
  return request.get('/import/organizations/template', { responseType: 'blob' })
}

/** 批量导入项目 */
export function importProjects(file: File): Promise<ImportResult> {
  const fd = new FormData()
  fd.append('file', file)
  return request.post('/import/projects', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 批量导入用户 */
export function importUsers(file: File): Promise<ImportResult> {
  const fd = new FormData()
  fd.append('file', file)
  return request.post('/import/users', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 批量导入组织 */
export function importOrganizations(file: File): Promise<ImportResult> {
  const fd = new FormData()
  fd.append('file', file)
  return request.post('/import/organizations', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 通用的模板下载 + 浏览器保存 */
export async function downloadAndSaveTemplate(
  fetcher: () => Promise<Blob>,
  filename: string,
): Promise<void> {
  const blob = await fetcher()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}
