/**
 * 释放管理 API
 */
import request from './request'
import type { ExternalRecipientLink, Release, ReleaseListItem } from '@/types'

/** 获取释放详情 */
export function getRelease(id: string): Promise<Release> {
  return request.get(`/releases/${id}`)
}

/** 上传代码包（附带变更点说明） */
export function uploadCodePackage(
  id: string,
  file: File,
  changeNotes?: string,
): Promise<Release> {
  const formData = new FormData()
  formData.append('file', file)
  if (changeNotes) {
    formData.append('change_notes', changeNotes)
  }
  return request.post(`/releases/${id}/code-package`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 上传测试报告 */
export function uploadTestReport(id: string, file: File): Promise<Release> {
  const formData = new FormData()
  formData.append('file', file)
  return request.post(`/releases/${id}/test-report`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 上传评审报告（专家报告） */
export function uploadReviewReport(id: string, file: File): Promise<Release> {
  const formData = new FormData()
  formData.append('file', file)
  return request.post(`/releases/${id}/review-report`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** PM 确认释放 */
export function confirmRelease(id: string): Promise<Release> {
  return request.post(`/releases/${id}/confirm`)
}

/** 下载交付物（代码包/测试报告/评审报告）
 *
 * 后端 GET /api/releases/{id}/download/{file_type} 会 302 重定向到 MinIO 预签名 URL。
 * 注意：window.open 不会携带 Authorization header，所以这里通过 axios 请求获取 blob，
 * 然后创建 object URL 触发浏览器原生下载对话框。
 */
export async function downloadArtifact(
  id: string,
  fileType: 'code_package' | 'test_report' | 'review_report',
): Promise<void> {
  const response = await request.get(`/releases/${id}/download/${fileType}`, {
    responseType: 'blob',
    // axios 会自动跟随 302 重定向并下载最终内容
  })
  // 从响应头提取文件名
  let fileName = `${fileType}`
  const contentDisposition = response.headers?.['content-disposition']
  if (contentDisposition) {
    const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?(["']?)([^;"']+)\1/i)
    if (match && match[2]) {
      fileName = decodeURIComponent(match[2])
    }
  } else {
    // 根据文件类型给默认扩展名
    const extMap: Record<string, string> = {
      code_package: '.zip',
      test_report: '.md',
      review_report: '.md',
    }
    fileName = fileType + (extMap[fileType] || '')
  }

  // 创建下载链接
  const blob = new Blob([response.data || response])
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}



/** 获取某版本的所有释放列表 */
export function getReleasesByVersion(versionId: string): Promise<ReleaseListItem[]> {
  return request.get(`/releases/by-version/${versionId}`)
}


/** 获取 release 对应版本的外部接收方下载链接(含 access_token,功能2.4) */
export function getExternalDownloadLinks(
  releaseId: string,
): Promise<ExternalRecipientLink[]> {
  return request.get(`/releases/${releaseId}/external-download-links`)
}
