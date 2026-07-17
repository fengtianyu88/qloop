/**
 * 释放管理 API
 */
import request from './request'
import type { Release } from '@/types'

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
