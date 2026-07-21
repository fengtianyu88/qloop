<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile } from 'element-plus'
import {
  getRelease,
  uploadCodePackage,
  uploadTestReport,
  uploadReviewReport,
  confirmRelease,
  downloadArtifact,
  getExternalDownloadLinks,
} from '@/api/releases'
import { getReleaseReviews, triggerReview } from '@/api/reviews'
import { getProject } from '@/api/projects'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'
import {
  reviewResultLabel,
  reviewResultTagType,
  reviewTypeLabel,
  statusLabel,
  statusTagType,
} from '@/utils/status'
import type { ExternalRecipientLink, LLMReview, Release, ReviewType } from '@/types'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const releaseId = computed(() => route.params.id as string)
const release = ref<Release | null>(null)
// P2-9: 面包屑用,展示所属项目名称(按需懒加载)
const projectName = ref<string>('')
// 功能7: 缓存项目 PM 用户 ID,用于 canForceAdvance 判断当前用户是否为该项目 PM
const projectPmUserId = ref<string>('')
const reviews = ref<LLMReview[]>([])
const loading = ref(false)
// 功能2.4: 外部接收方下载链接(含 access_token)
const externalLinks = ref<ExternalRecipientLink[]>([])

// 流程步骤
const steps = [
  { title: '草稿', status: 'draft' },
  { title: '代码评审', status: 'code_pending_review' },
  { title: '测试报告评审', status: 'test_pending_review' },
  { title: '专家报告评审', status: 'expert_pending_review' },
  { title: '待 PM 确认', status: 'pending_confirm' },
  { title: '已释放', status: 'released' },
]

const activeStep = computed(() => {
  const status = release.value?.status
  if (!status) return 0
  const idx = steps.findIndex((s) => s.status === status)
  return idx >= 0 ? idx : 0
})

const isFailed = computed(() => release.value?.status === 'review_failed')
const isReleased = computed(() => release.value?.status === 'released')

// 评审类型选项
const reviewTypeOptions: { label: string; value: ReviewType }[] = [
  { label: '代码评审', value: 'code_review' },
  { label: '测试报告评审', value: 'test_report_review' },
  { label: '专家报告评审', value: 'expert_report_review' },
]
const triggerReviewType = ref<ReviewType>('code_review')
const triggering = ref(false)

// 评审进度抽屉
const reviewDrawerVisible = ref(false)
const reviewDrawerCollapsed = ref(false)  // 收缩状态
const reviewProgressLogs = ref<{time: string, msg: string, type: 'info'|'success'|'warning'|'error'}[]>([])
let reviewPollingTimer: ReturnType<typeof setInterval> | null = null
// 功能4: SSE EventSource 连接(实时接收评审进度,与轮询互补)
let reviewEventSource: EventSource | null = null

// 评审当前状态(用于顶部醒目展示)
const reviewCurrentStatus = ref<'idle' | 'triggering' | 'running' | 'passed' | 'failed' | 'error'>('idle')
const reviewCurrentStep = ref('')  // 当前步骤文案
const reviewStartedAt = ref<number | null>(null)  // 开始时间戳(毫秒)
const reviewElapsedSec = ref(0)  // 已耗时(秒)
let reviewElapsedTimer: ReturnType<typeof setInterval> | null = null
let reviewHeartbeatTimer: ReturnType<typeof setInterval> | null = null
const reviewLastLogAt = ref<number | null>(null)  // 上次产生日志的时间戳
let lastLoggedStepKey = ''  // 上次记录日志的步骤标识(review_type + review_round + result)

// 添加进度日志
function addProgressLog(msg: string, type: 'info'|'success'|'warning'|'error' = 'info') {
  const now = new Date()
  const time = now.toTimeString().slice(0, 8)
  reviewProgressLogs.value.push({ time, msg, type })
  reviewLastLogAt.value = Date.now()
  // 自动滚动到底部
  nextTick(() => {
    const el = document.querySelector('.review-log-list')
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 清空评审日志
function clearReviewLogs() {
  reviewProgressLogs.value = []
}

// 导出评审日志为 .txt 文件
function exportReviewLogs() {
  if (reviewProgressLogs.value.length === 0) {
    ElMessage.warning('暂无日志可导出')
    return
  }
  const text = reviewProgressLogs.value
    .map(log => `[${log.time}] ${log.type.toUpperCase()}: ${log.msg}`)
    .join('\n')
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `review-logs-${releaseId.value}-${Date.now()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

// 格式化耗时 mm:ss
function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// 启动已耗时计时器(每秒更新)
function startElapsedTimer() {
  if (reviewElapsedTimer) clearInterval(reviewElapsedTimer)
  reviewElapsedTimer = setInterval(() => {
    if (reviewStartedAt.value !== null) {
      reviewElapsedSec.value = Math.floor((Date.now() - reviewStartedAt.value) / 1000)
    }
  }, 1000)
}

// 启动心跳计时器(每 5 秒添加一条活动日志,让用户知道评审仍在进行)
function startHeartbeat() {
  if (reviewHeartbeatTimer) clearInterval(reviewHeartbeatTimer)
  reviewHeartbeatTimer = setInterval(() => {
    if (reviewCurrentStatus.value === 'running') {
      const sinceLastLog = reviewLastLogAt.value ? (Date.now() - reviewLastLogAt.value) / 1000 : 999
      if (sinceLastLog >= 5) {
        addProgressLog(`仍在等待 LLM 返回...已耗时 ${formatElapsed(reviewElapsedSec.value)}`, 'info')
      }
    }
  }, 5000)
}

// 开始轮询评审状态
function startReviewPolling() {
  if (reviewPollingTimer) clearInterval(reviewPollingTimer)
  reviewPollingTimer = setInterval(async () => {
    try {
      const data = await getReleaseReviews(releaseId.value)
      // 找最新的评审记录
      if (data && data.length > 0) {
        const latest = data[0]
        const reviewLabel = reviewTypeLabel(latest.review_type as ReviewType) || latest.review_type
        const stepKey = `${latest.review_type}|${latest.review_round}|${latest.result}`
        // 判断评审状态
        if (latest.result === 'pending') {
          reviewCurrentStatus.value = 'running'
          reviewCurrentStep.value = `${reviewLabel} · 第 ${latest.review_round} 轮`
          // 仅在步骤变化时记录日志,避免刷屏
          if (stepKey !== lastLoggedStepKey) {
            addProgressLog(`[${reviewCurrentStep.value}] LLM 正在分析...`, 'info')
            lastLoggedStepKey = stepKey
          }
        } else if (latest.result === 'passed') {
          if (stepKey !== lastLoggedStepKey) {
            reviewCurrentStatus.value = 'passed'
            reviewCurrentStep.value = `${reviewLabel} · 已通过`
            addProgressLog(`评审通过!总分:${latest.total_score}`, 'success')
            addProgressLog(`结论:${latest.conclusion || '-'}`, 'info')
            lastLoggedStepKey = stepKey
            stopReviewPolling()
          }
        } else if (latest.result === 'failed') {
          if (stepKey !== lastLoggedStepKey) {
            reviewCurrentStatus.value = 'failed'
            reviewCurrentStep.value = `${reviewLabel} · 未通过`
            addProgressLog(`评审未通过。总分:${latest.total_score}`, 'warning')
            addProgressLog(`建议:${latest.suggestions || '-'}`, 'info')
            lastLoggedStepKey = stepKey
            stopReviewPolling()
          }
        } else if (latest.result === 'error') {
          if (stepKey !== lastLoggedStepKey) {
            reviewCurrentStatus.value = 'error'
            reviewCurrentStep.value = `${reviewLabel} · 出错`
            addProgressLog(`评审出错,请查看评审记录`, 'error')
            lastLoggedStepKey = stepKey
            stopReviewPolling()
          }
        }
      }
      // 同步刷新 reviews 列表
      reviews.value = data
    } catch {
      // 静默失败,继续轮询
    }
  }, 2000)  // 每 2 秒轮询一次
}

function stopReviewPolling() {
  if (reviewPollingTimer) {
    clearInterval(reviewPollingTimer)
    reviewPollingTimer = null
  }
  if (reviewElapsedTimer) {
    clearInterval(reviewElapsedTimer)
    reviewElapsedTimer = null
  }
  if (reviewHeartbeatTimer) {
    clearInterval(reviewHeartbeatTimer)
    reviewHeartbeatTimer = null
  }
  // 功能4: 同时关闭 SSE 连接
  stopSSEStream()
}

// 功能4: 启动 SSE 流式接收评审进度
function startSSEStream() {
  stopSSEStream()
  const token = localStorage.getItem('token')
  if (!token) return
  // EventSource 不支持自定义 header,通过 query 参数传 token
  const url = `/api/reviews/stream/${releaseId.value}?token=${encodeURIComponent(token)}`
  try {
    reviewEventSource = new EventSource(url)
  } catch (e) {
    // 浏览器不支持或 URL 无效,静默降级到轮询
    reviewEventSource = null
    return
  }

  reviewEventSource.onmessage = (event) => {
    let data: any
    try {
      data = JSON.parse(event.data)
    } catch {
      return  // 忽略无法解析的消息(如心跳注释不会触发 onmessage)
    }
    if (data.error) {
      addProgressLog(`SSE 错误:${data.error}`, 'error')
      stopSSEStream()
      return
    }
    const label = reviewTypeLabel(data.review_type as ReviewType) || data.review_type
    const stepKey = `${data.review_type}|${data.review_round}|${data.result}`
    if (data.result === 'pending') {
      reviewCurrentStatus.value = 'running'
      reviewCurrentStep.value = `${label} · 第 ${data.review_round} 轮`
      if (stepKey !== lastLoggedStepKey) {
        lastLoggedStepKey = stepKey
        addProgressLog(`[${reviewCurrentStep.value}] SSE:LLM 正在分析...`, 'info')
      }
    } else if (data.result === 'passed') {
      reviewCurrentStatus.value = 'passed'
      reviewCurrentStep.value = `${label} · 已通过`
      addProgressLog(`SSE:评审通过!总分:${data.total_score ?? '—'}`, 'success')
      if (data.conclusion) addProgressLog(`结论:${data.conclusion}`, 'info')
      stopSSEStream()
    } else if (data.result === 'failed') {
      reviewCurrentStatus.value = 'failed'
      reviewCurrentStep.value = `${label} · 未通过`
      addProgressLog(`SSE:评审未通过,总分:${data.total_score ?? '—'}`, 'warning')
      if (data.suggestions) addProgressLog(`建议:${data.suggestions}`, 'info')
      stopSSEStream()
    } else if (data.result === 'error') {
      reviewCurrentStatus.value = 'error'
      reviewCurrentStep.value = `${label} · 出错`
      addProgressLog(`SSE:评审出错,请查看评审记录`, 'error')
      stopSSEStream()
    }
  }

  reviewEventSource.onerror = () => {
    // SSE 连接异常(可能是终态关闭或网络中断),静默关闭,轮询会继续兜底
    stopSSEStream()
  }
}

// 功能4: 关闭 SSE 流
function stopSSEStream() {
  if (reviewEventSource) {
    reviewEventSource.close()
    reviewEventSource = null
  }
}

// 组件卸载时清理所有 timer,避免内存泄漏
onBeforeUnmount(() => {
  stopReviewPolling()
})

// 切换抽屉收缩/展开
function toggleReviewDrawer() {
  reviewDrawerCollapsed.value = !reviewDrawerCollapsed.value
}

// 打开抽屉并开始轮询
function openReviewDrawer() {
  reviewDrawerVisible.value = true
  reviewDrawerCollapsed.value = false
  reviewProgressLogs.value = []
  reviewCurrentStatus.value = 'triggering'
  reviewCurrentStep.value = '准备触发评审'
  reviewStartedAt.value = Date.now()
  reviewElapsedSec.value = 0
  reviewLastLogAt.value = null
  lastLoggedStepKey = ''
  addProgressLog('开始触发 LLM 评审...', 'info')
  startElapsedTimer()
  startHeartbeat()
}

// 根据当前状态推断默认评审类型
function syncTriggerType() {
  const status = release.value?.status
  if (status === 'code_pending_review') triggerReviewType.value = 'code_review'
  else if (status === 'test_pending_review') triggerReviewType.value = 'test_report_review'
  else if (status === 'expert_pending_review') triggerReviewType.value = 'expert_report_review'
  // 评审失败状态下,默认触发类型为失败的评审类型(便于用户重新触发)
  else if (status === 'review_failed' && failedReviewType.value) {
    triggerReviewType.value = failedReviewType.value
  }
}

// 文件上传
const codeFile = ref<File | null>(null)
const codeChangeNotes = ref('')
const codeUploading = ref(false)
const codeUploadProgress = ref(0)  // 代码包上传进度(0-100)

const testFile = ref<File | null>(null)
const testUploading = ref(false)
const testUploadProgress = ref(0)  // 测试报告上传进度(0-100)

const reviewFile = ref<File | null>(null)
const reviewUploading = ref(false)
const reviewUploadProgress = ref(0)  // 评审报告上传进度(0-100)

function handleCodeFileChange(file: UploadFile) {
  codeFile.value = file.raw || null
}
function handleTestFileChange(file: UploadFile) {
  testFile.value = file.raw || null
}
function handleReviewFileChange(file: UploadFile) {
  reviewFile.value = file.raw || null
}

async function doUploadCode() {
  if (!codeFile.value) {
    ElMessage.warning('请先选择代码包文件')
    return
  }
  codeUploading.value = true
  codeUploadProgress.value = 0
  try {
    // 直接使用 request.post 以支持 onUploadProgress 回调
    const formData = new FormData()
    formData.append('file', codeFile.value)
    if (codeChangeNotes.value) formData.append('change_notes', codeChangeNotes.value)
    release.value = await request.post(`/releases/${releaseId.value}/code-package`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          codeUploadProgress.value = Math.round((progressEvent.loaded / progressEvent.total) * 100)
        }
      }
    })
    ElMessage.success('代码包上传成功，已进入代码评审')
    codeFile.value = null
    codeChangeNotes.value = ''
    await loadReviews()
    syncTriggerType()
  } catch {
    // 错误已统一提示
  } finally {
    codeUploading.value = false
  }
}

async function doUploadTest() {
  if (!testFile.value) {
    ElMessage.warning('请先选择测试报告文件')
    return
  }
  testUploading.value = true
  testUploadProgress.value = 0
  try {
    // 直接使用 request.post 以支持 onUploadProgress 回调
    const formData = new FormData()
    formData.append('file', testFile.value)
    release.value = await request.post(`/releases/${releaseId.value}/test-report`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          testUploadProgress.value = Math.round((progressEvent.loaded / progressEvent.total) * 100)
        }
      }
    })
    ElMessage.success('测试报告上传成功，已进入测试报告评审')
    testFile.value = null
    await loadReviews()
    syncTriggerType()
  } catch {
    // 错误已统一提示
  } finally {
    testUploading.value = false
  }
}

async function doUploadReviewReport() {
  if (!reviewFile.value) {
    ElMessage.warning('请先选择评审报告文件')
    return
  }
  reviewUploading.value = true
  reviewUploadProgress.value = 0
  try {
    // 直接使用 request.post 以支持 onUploadProgress 回调
    const formData = new FormData()
    formData.append('file', reviewFile.value)
    release.value = await request.post(`/releases/${releaseId.value}/review-report`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          reviewUploadProgress.value = Math.round((progressEvent.loaded / progressEvent.total) * 100)
        }
      }
    })
    ElMessage.success('评审报告上传成功，已进入专家报告评审')
    reviewFile.value = null
    await loadReviews()
    syncTriggerType()
  } catch {
    // 错误已统一提示
  } finally {
    reviewUploading.value = false
  }
}

// 触发评审
async function handleTriggerReview() {
  triggering.value = true
  // 先打开抽屉,显示"正在提交评审请求..."
  openReviewDrawer()
  try {
    await triggerReview(releaseId.value, triggerReviewType.value)
    addProgressLog(`已触发${reviewTypeLabel(triggerReviewType.value)}评审`, 'info')
    reviewCurrentStatus.value = 'running'
    reviewCurrentStep.value = `${reviewTypeLabel(triggerReviewType.value)} · 第 1 轮`
    startReviewPolling()
  } catch (e: any) {
    const status = e?.response?.status
    const detail = e?.response?.data?.detail || ''
    reviewCurrentStatus.value = 'error'
    reviewCurrentStep.value = '触发失败'
    if (status === 412 || detail.includes('评审规则') || detail.includes('review rule')) {
      // 评审规则未配置
      const msg = `评审规则未配置:${detail || '请联系管理员在 LLM 配置页添加对应类型的评审规则'}`
      ElMessage.error(msg)
      addProgressLog(msg, 'error')
    } else {
      const msg = detail || '触发评审失败,请查看日志或联系管理员'
      ElMessage.error(msg)
      addProgressLog(msg, 'error')
    }
    stopReviewPolling()
  } finally {
    triggering.value = false
  }
}

// 是否有评审正在进行中(从后端 reviews 列表推断,切换页面再回来状态依然正确)
const reviewInProgress = computed(() => {
  if (!reviews.value || reviews.value.length === 0) return false
  // 取最新一条评审记录(列表按 created_at 倒序)
  const latest = reviews.value[0]
  return latest.result === 'pending'
})

// 评审中标签显示的文案
const reviewInProgressLabel = computed(() => {
  if (!reviewInProgress.value || !reviews.value.length) return ''
  const latest = reviews.value[0]
  const label = reviewTypeLabel(latest.review_type as ReviewType) || latest.review_type
  return `LLM 评审中 · ${label} 第 ${latest.review_round} 轮`
})

// PM 确认释放
const confirming = ref(false)
async function handleConfirm() {
  try {
    await ElMessageBox.confirm('确认释放该版本？释放后将生成下载链接。', '确认释放', {
      confirmButtonText: '确认释放',
      cancelButtonText: '取消',
      type: 'warning',
    })
    confirming.value = true
    release.value = await confirmRelease(releaseId.value)
    ElMessage.success('释放成功')
    await loadReviews()
  } catch {
    // 取消或错误
  } finally {
    confirming.value = false
  }
}

// 下载链接处理
function downloadUrl(link: string): string {
  // 若为相对路径则拼接 /api 前缀走代理
  if (link.startsWith('http')) return link
  return link.startsWith('/api') ? link : `/api${link}`
}

// 在新窗口打开下载链接
function openLink(link: string) {
  window.open(downloadUrl(link), '_blank')
}

// 下载单个交付物（代码包/测试报告/评审报告）
// 使用 axios blob 方式下载（自动携带 Authorization header）
const downloading = ref<string>('')

async function downloadArtifactFile(fileType: 'code_package' | 'test_report' | 'review_report') {
  downloading.value = fileType
  try {
    await downloadArtifact(releaseId.value, fileType)
    ElMessage.success('下载已开始')
  } catch {
    // 错误已统一提示
  } finally {
    downloading.value = ''
  }
}

function formatTime(t: string | null): string {
  if (!t) return '—'
  return t.replace('T', ' ').slice(0, 19)
}

// 从 MinIO 对象路径中提取文件名
function fileNameFromPath(path: string | null | undefined): string {
  if (!path) return ''
  // path 形如 "releases/{release_id}/code_package/{filename}" 或 "releases/.../uuid_filename.zip"
  const parts = path.split('/')
  return parts[parts.length - 1] || path
}

// 文件大小估算(根据路径无法准确获取,返回 null)
function formatBytes(_bytes: number | null | undefined): string {
  if (!_bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = _bytes
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(1)} ${units[i]}`
}

// 计算交付物列表(用于 v-for 渲染)
interface ArtifactItem {
  fileType: 'code_package' | 'test_report' | 'review_report'
  label: string
  path: string | null
  fileName: string
  uploaderName: string | null
  uploaderId: string | null
  uploadedAt: string | null
  icon: string  // 用于显示的图标名(可选)
  sha256: string | null  // 完整性校验摘要(功能3)
}

const artifacts = computed<ArtifactItem[]>(() => {
  if (!release.value) return []
  const r = release.value
  const items: ArtifactItem[] = []
  if (r.code_package_path) {
    items.push({
      fileType: 'code_package',
      label: '代码包',
      path: r.code_package_path,
      fileName: fileNameFromPath(r.code_package_path),
      uploaderName: r.code_package_uploader_name,
      uploaderId: r.code_package_uploaded_by,
      uploadedAt: r.code_package_uploaded_at,
      icon: 'Files',
      sha256: r.code_package_sha256,
    })
  }
  if (r.test_report_path) {
    items.push({
      fileType: 'test_report',
      label: '测试报告',
      path: r.test_report_path,
      fileName: fileNameFromPath(r.test_report_path),
      uploaderName: r.test_report_uploader_name,
      uploaderId: r.test_report_uploaded_by,
      uploadedAt: r.test_report_uploaded_at,
      icon: 'Document',
      sha256: r.test_report_sha256,
    })
  }
  if (r.review_report_path) {
    items.push({
      fileType: 'review_report',
      label: '评审报告',
      path: r.review_report_path,
      fileName: fileNameFromPath(r.review_report_path),
      uploaderName: r.review_report_uploader_name,
      uploaderId: r.review_report_uploaded_by,
      uploadedAt: r.review_report_uploaded_at,
      icon: 'Notebook',
      sha256: r.review_report_sha256,
    })
  }
  return items
})

function dimensionEntries(scores: Record<string, number> | null): [string, number][] {
  if (!scores) return []
  return Object.entries(scores)
}

async function loadExternalLinks() {
  // 功能2.4: 加载外部接收方下载链接(仅已释放时调用)
  try {
    externalLinks.value = await getExternalDownloadLinks(releaseId.value)
  } catch {
    externalLinks.value = []
  }
}

// 功能3.4: 复制 SHA256 到剪贴板
async function copySha256(sha256: string | null) {
  if (!sha256) return
  try {
    await navigator.clipboard.writeText(sha256)
    ElMessage.success('SHA256 已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败,请手动选择文本复制')
  }
}

// 功能2.4: 复制外部下载链接到剪贴板
async function copyDownloadLink(link: string | null) {
  if (!link) return
  try {
    await navigator.clipboard.writeText(link)
    ElMessage.success('下载链接已复制')
  } catch {
    ElMessage.warning('复制失败,请手动复制')
  }
}

async function loadRelease() {
  loading.value = true
  try {
    release.value = await getRelease(releaseId.value)
    syncTriggerType()
    // P2-9: 加载所属项目名称,用于面包屑展示
    if (release.value?.project_id) {
      try {
        const project = await getProject(release.value.project_id)
        projectName.value = project?.name || ''
        // 功能7: 缓存 PM 用户 ID,用于 canForceAdvance 判断
        projectPmUserId.value = project?.pm_user_id || ''
      } catch {
        // 项目名称加载失败不阻塞主流程
        projectName.value = ''
        projectPmUserId.value = ''
      }
    }
    // 已释放时加载外部接收方下载链接(功能2.4)
    if (release.value?.status === 'released') {
      await loadExternalLinks()
    }
  } catch {
    // 错误已统一提示
  } finally {
    loading.value = false
  }
}

async function loadReviews() {
  try {
    reviews.value = await getReleaseReviews(releaseId.value)
  } catch {
    // 错误已统一提示
  }
}

function goBack() {
  router.back()
}

const canTrigger = computed(() => authStore.isDeveloper)

// 是否可以删除版本:
// - admin: 仅未释放版本
// - super_admin: 任何版本(包括已释放)
const canDeleteVersion = computed(() => {
  if (!release.value || !authStore.user) return false
  if (authStore.isSuperAdmin) return true
  if (authStore.isAdmin) return !isReleased.value
  return false
})

async function handleDeleteVersion() {
  if (!release.value) return
  const ver = release.value.version_id
  const proj = release.value.project_id
  if (!ver || !proj) {
    ElMessage.error('无法确定版本或项目,删除失败')
    return
  }

  try {
    await ElMessageBox.confirm(
      '确定要删除此版本吗?删除后版本及其所有释放记录将无法恢复。',
      '删除版本确认',
      {
        type: 'warning',
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }

  try {
    await request.delete(`/projects/${proj}/versions/${ver}`)
    ElMessage.success('版本已删除')
    router.push('/projects/' + proj)
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '删除失败'
    ElMessage.error(msg)
  }
}

// 删除单个交付物的权限:
// - 已释放(released)的 release 不可删除任何交付物
// - admin / super_admin: 可删除任何已上传的交付物
// - 其他角色: 只能删除自己上传的交付物(uploaderId === 当前用户 id)
function canDeleteArtifact(row: ArtifactItem): boolean {
  if (!release.value || isReleased.value) return false
  if (!row.path) return false  // 没有文件不能删除
  if (authStore.isAdmin) return true
  // 非管理员:只能删自己上传的
  const userId = authStore.user?.id
  if (!userId) return false
  return row.uploaderId === userId
}

async function handleDeleteArtifact(row: ArtifactItem) {
  if (!release.value) return
  try {
    await ElMessageBox.confirm(
      `确定要删除交付物「${row.fileName}」吗?此操作不可恢复。`,
      '删除交付物确认',
      {
        type: 'warning',
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  try {
    await request.delete(`/releases/${release.value.id}/artifacts/${row.fileType}`)
    ElMessage.success('交付物已删除')
    await loadRelease()  // 重新加载以刷新 artifacts 列表
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '删除失败'
    ElMessage.error(msg)
  }
}

// 流水线方框内删除交付物(按 file_type 直接删除)
async function handleDeleteArtifactByType(
  fileType: 'code_package' | 'test_report' | 'review_report',
  fileName: string,
) {
  if (!release.value) return
  try {
    await ElMessageBox.confirm(
      `确定要删除交付物「${fileName}」吗?此操作不可恢复。`,
      '删除交付物确认',
      {
        type: 'warning',
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  try {
    await request.delete(`/releases/${release.value.id}/artifacts/${fileType}`)
    ElMessage.success('交付物已删除')
    await loadRelease()
    await loadReviews()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '删除失败'
    ElMessage.error(msg)
  }
}

// ============ 稍后评审 / 特批放行 ============
// 评审失败时,找出失败的评审类型(用于决定哪个步骤可以重新上传/触发)
const failedReviewType = computed<ReviewType | null>(() => {
  if (!reviews.value || reviews.value.length === 0) return null
  const failed = reviews.value.find(r => r.result === 'failed' || r.result === 'error')
  return failed?.review_type || null
})

// 判断指定步骤是否可重新上传(review_failed 状态下,失败的那一步允许重新上传)
function canReuploadAtStep(stepReviewType: ReviewType): boolean {
  if (!release.value) return false
  if (release.value.status !== 'review_failed') return false
  return failedReviewType.value === stepReviewType
}

// 判断指定步骤的已上传交付物是否可删除(达到成功释放之前,上传人和管理员都可删除)
function canDeleteArtifactByType(
  uploaderId: string | null | undefined,
): boolean {
  if (!release.value) return false
  if (isReleased.value) return false  // 已释放的不允许删除
  if (!uploaderId) return false  // 没有上传人不允许删除
  if (authStore.isAdmin) return true  // admin / super_admin 可删任意
  const userId = authStore.user?.id
  if (!userId) return false
  return uploaderId === userId  // 其他人只能删自己上传的
}

// 是否可以跳过当前评审(稍后评审按钮)
const canSkipReview = computed(() => {
  if (!release.value || !authStore.user) return false
  const status = release.value.status
  const reviewStages = ['code_pending_review', 'test_pending_review', 'expert_pending_review']
  if (!reviewStages.includes(status)) return false
  if (authStore.isAdmin) return true
  const userId = authStore.user.id
  if (status === 'code_pending_review') return release.value.code_package_uploaded_by === userId
  if (status === 'test_pending_review') return release.value.test_report_uploaded_by === userId
  if (status === 'expert_pending_review') return release.value.review_report_uploaded_by === userId
  return false
})

// 是否可以特批放行(功能7):
// - admin/super_admin:任意评审阶段 + pending_confirm + review_failed 都可见
// - PM:任意评审阶段 + pending_confirm + review_failed 都可见
// - 其他角色:不可见
const canForceAdvance = computed(() => {
  if (!release.value || !authStore.user) return false
  const status = release.value.status
  // 允许特批放行的状态:任意评审阶段、待确认、评审失败
  const allowedStages = [
    'code_pending_review',
    'test_pending_review',
    'expert_pending_review',
    'pending_confirm',
    'review_failed',  // 功能7:评审失败后 PM/管理员可特批放行到下一阶段
  ]
  if (!allowedStages.includes(status)) return false
  if (authStore.isAdmin) return true
  // PM:当前用户是该项目的 PM
  const userId = authStore.user.id
  if (projectPmUserId.value && projectPmUserId.value === userId) return true
  return false
})

async function handleSkipReview() {
  if (!release.value) return
  try {
    await ElMessageBox.confirm(
      '将跳过当前 LLM 评审,直接进入下一阶段。\n\n' +
      '当前评审类型:' + reviewTypeLabel(triggerReviewType.value) + '\n' +
      '跳过后仍可在后续阶段重新触发评审。',
      '稍后 LLM 评审',
      { type: 'warning', confirmButtonText: '确认跳过', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await request.post(`/releases/${releaseId.value}/skip-review`)
    ElMessage.success('已跳过当前评审')
    await loadRelease()
    await loadReviews()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '跳过评审失败'
    ElMessage.error(msg)
  }
}

async function handleForceAdvance() {
  if (!release.value) return
  try {
    // 功能7:根据当前状态显示不同提示
    const curStatus = release.value.status
    let actionDesc = '直接释放版本'
    if (curStatus === 'review_failed') {
      actionDesc = '推进到下一阶段(根据失败阶段决定)'
    } else if (curStatus === 'pending_confirm') {
      actionDesc = '直接释放版本'
    } else {
      actionDesc = '跳过当前 LLM 评审,推进到下一阶段'
    }
    await ElMessageBox.confirm(
      '将特批放行:' + actionDesc + '。\n\n' +
      '此操作需要 PM 或管理员权限,且会记录在审计日志中。\n' +
      '评审失败状态下放行将记录特批放行人。',
      '特批放行',
      {
        type: 'warning',
        confirmButtonText: '确认放行',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  try {
    await request.post(`/releases/${releaseId.value}/force-advance`)
    ElMessage.success('已特批放行')
    await loadRelease()
    await loadReviews()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '特批放行失败'
    ElMessage.error(msg)
  }
}

// ============ 流水线步骤状态 ============
type StepStatus = 'not_started' | 'in_progress' | 'completed' | 'failed' | 'current'

// 根据 review_type 获取最新的评审记录
function getReviewByType(reviewType: ReviewType): LLMReview | null {
  if (!reviews.value || reviews.value.length === 0) return null
  // reviews 数组按 created_at 倒序,取第一条匹配
  const found = reviews.value.find((r) => r.review_type === reviewType)
  return found || null
}

const step1Status = computed<StepStatus>(() => {
  if (!release.value) return 'not_started'
  return 'completed'  // 版本已创建
})

// 评审失败时,根据本步 LLMReview.result 决定颜色,而非一刀切全红
// 已通过的步骤保持 completed(绿),只有真正失败的那步变红
const step2Status = computed<StepStatus>(() => {
  if (!release.value) return 'not_started'
  const status = release.value.status
  if (status === 'draft') return 'current'
  if (status === 'code_pending_review') return 'in_progress'
  if (['test_pending_review', 'expert_pending_review', 'pending_confirm', 'released'].includes(status)) return 'completed'
  if (status === 'review_failed') {
    const review = getReviewByType('code_review')
    if (review?.result === 'failed' || review?.result === 'error') return 'failed'
    if (review?.result === 'passed') return 'completed'
    return 'current'  // 没有评审记录,说明未触发过,显示为当前可操作
  }
  return 'not_started'
})

const step3Status = computed<StepStatus>(() => {
  if (!release.value) return 'not_started'
  const status = release.value.status
  if (['draft', 'code_pending_review'].includes(status)) return 'not_started'
  if (status === 'test_pending_review') return 'in_progress'
  if (['expert_pending_review', 'pending_confirm', 'released'].includes(status)) return 'completed'
  if (status === 'review_failed') {
    const review = getReviewByType('test_report_review')
    if (review?.result === 'failed' || review?.result === 'error') return 'failed'
    if (review?.result === 'passed') return 'completed'
    // 如果失败的不是本步,根据 release 已上传的字段判断是否已完成
    if (release.value.test_report_path) return 'completed'
    return 'not_started'
  }
  return 'not_started'
})

const step4Status = computed<StepStatus>(() => {
  if (!release.value) return 'not_started'
  const status = release.value.status
  if (['draft', 'code_pending_review', 'test_pending_review'].includes(status)) return 'not_started'
  if (status === 'expert_pending_review') return 'in_progress'
  if (['pending_confirm', 'released'].includes(status)) return 'completed'
  if (status === 'review_failed') {
    const review = getReviewByType('expert_report_review')
    if (review?.result === 'failed' || review?.result === 'error') return 'failed'
    if (review?.result === 'passed') return 'completed'
    if (release.value.review_report_path) return 'completed'
    return 'not_started'
  }
  return 'not_started'
})

const step5Status = computed<StepStatus>(() => {
  if (!release.value) return 'not_started'
  const status = release.value.status
  if (['draft', 'code_pending_review', 'test_pending_review', 'expert_pending_review'].includes(status)) return 'not_started'
  if (status === 'pending_confirm') return 'current'
  if (status === 'released') return 'completed'
  return 'not_started'
})

onMounted(async () => {
  await loadRelease()
  await loadReviews()
  // 加载完 reviews 后再次同步 trigger 类型(用于 review_failed 状态下推断失败类型)
  syncTriggerType()
  // 检测是否有进行中的评审,自动恢复抽屉和轮询(切换路由回来时也能继续查看实时日志)
  if (reviewInProgress.value) {
    openReviewDrawer()
    reviewCurrentStatus.value = 'running'
    const latest = reviews.value[0]
    const label = reviewTypeLabel(latest.review_type as ReviewType) || latest.review_type
    reviewCurrentStep.value = `${label} · 第 ${latest.review_round} 轮`
    startReviewPolling()
  }
})
</script>

<template>
  <div class="page-container" v-loading="loading">
    <!-- P2-9: 面包屑导航,方便用户回到项目/首页 -->
    <el-breadcrumb separator="/" class="release-breadcrumb">
      <el-breadcrumb-item :to="{ path: '/home' }">首页</el-breadcrumb-item>
      <el-breadcrumb-item :to="{ path: '/projects' }">项目</el-breadcrumb-item>
      <el-breadcrumb-item
        v-if="release?.project_id"
        :to="{ path: '/projects/' + release.project_id }"
      >
        {{ projectName || '项目详情' }}
      </el-breadcrumb-item>
      <el-breadcrumb-item>版本 {{ release?.release_number }}</el-breadcrumb-item>
    </el-breadcrumb>

    <div class="detail-header">
      <el-button @click="goBack"><el-icon><ArrowLeft /></el-icon>返回</el-button>
      <h2 class="page-title">释放详情</h2>
      <el-button
        v-if="canDeleteVersion"
        type="danger"
        plain
        style="margin-left:auto"
        @click="handleDeleteVersion"
      >
        <el-icon><Delete /></el-icon>删除版本
      </el-button>
    </div>

    <template v-if="release">
      <!-- 释放流水线 -->
      <el-card class="table-card" shadow="never">
        <template #header><span>释放流水线</span></template>

        <el-alert
          v-if="isFailed"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        >
          <template #title>评审未通过</template>
          <template #default>
            <div>评审未通过，请根据评审建议修改后重新上传。</div>
          </template>
          <template #action>
            <el-button type="primary" size="small" @click="handleTriggerReview">
              重新触发评审
            </el-button>
          </template>
        </el-alert>

        <div class="pipeline">
          <!-- 步骤 1:版本创建 -->
          <!-- 功能7:特批放行横幅(评审失败被特批放行后展示) -->
          <el-alert
            v-if="release.force_advanced_by_name"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom:12px"
          >
            <template #title>
              本释放已由 <b>{{ release.force_advanced_by_name }}</b>
              于 {{ formatTime(release.force_advanced_at) }} 特批放行
              <span v-if="isFailed">(当前状态:评审失败)</span>
            </template>
          </el-alert>
          <!-- 功能7:评审失败时,显示特批放行按钮(仅 PM/管理员可见) -->
          <el-alert
            v-if="isFailed && canForceAdvance"
            type="error"
            :closable="false"
            show-icon
            style="margin-bottom:12px"
          >
            <template #title>
              评审失败 - PM/管理员可特批放行推进到下一阶段
            </template>
            <template #default>
              <el-button
                type="danger"
                size="small"
                style="margin-top:8px"
                @click="handleForceAdvance"
              >
                <el-icon><Promotion /></el-icon>立即特批放行
              </el-button>
            </template>
          </el-alert>

          <div :class="['step-box', step1Status]">
            <div class="step-header">
              <span class="step-number">1</span>
              <span>版本创建</span>
            </div>
            <div class="step-content">
              <div class="step-info">
                <div><span class="label">版本 ID:</span><span class="mono-id">{{ release.version_id }}</span></div>
                <div><span class="label">释放序号:</span>{{ release.release_number }}</div>
                <div>
                  <span class="label">状态:</span>
                  <el-tag :type="statusTagType(release.status)" size="small">{{ statusLabel(release.status) }}</el-tag>
                </div>
                <div><span class="label">创建时间:</span>{{ formatTime(release.created_at) }}</div>
                <div v-if="release.change_notes"><span class="label">变更点:</span>{{ release.change_notes }}</div>
              </div>
              <div class="step-actions"></div>
            </div>
          </div>

          <div class="step-connector">↓</div>

          <!-- 步骤 2:代码包上传 + LLM 评审 -->
          <div :class="['step-box', step2Status]">
            <div class="step-header">
              <span class="step-number">2</span>
              <span>代码包上传 + LLM 评审</span>
            </div>
            <div class="step-content">
              <div class="step-info">
                <div>
                  <span class="label">上传人:</span>
                  <span v-if="release.code_package_uploader_name">{{ release.code_package_uploader_name }}</span>
                  <span v-else class="mono-id">{{ release.code_package_uploaded_by || '—' }}</span>
                </div>
                <div><span class="label">上传时间:</span>{{ formatTime(release.code_package_uploaded_at) }}</div>
                <div v-if="release.code_package_path">
                  <span class="label">文件名:</span>{{ fileNameFromPath(release.code_package_path) }}
                  <el-button
                    v-if="canDeleteArtifactByType(release.code_package_uploaded_by)"
                    link
                    type="danger"
                    size="small"
                    style="margin-left:8px"
                    @click="handleDeleteArtifactByType('code_package', fileNameFromPath(release.code_package_path))"
                  >
                    <el-icon><Delete /></el-icon>删除
                  </el-button>
                </div>
                <div v-if="getReviewByType('code_review')">
                  <span class="label">评审结果:</span>
                  <el-tag :type="reviewResultTagType(getReviewByType('code_review')!.result)" size="small">
                    {{ reviewResultLabel(getReviewByType('code_review')!.result) }}
                  </el-tag>
                  <span v-if="getReviewByType('code_review')!.total_score !== null" style="margin-left:8px">
                    分数:<b>{{ getReviewByType('code_review')!.total_score }}</b>
                  </span>
                </div>
              </div>
              <div class="step-actions">
                <template v-if="release.status === 'draft' || canReuploadAtStep('code_review')">
                  <el-input
                    v-model="codeChangeNotes"
                    type="textarea"
                    :rows="2"
                    placeholder="变更点描述"
                    style="width:100%;margin-bottom:8px"
                  />
                  <el-upload
                    :auto-upload="false"
                    :limit="1"
                    :on-change="handleCodeFileChange"
                    :on-exceed="() => ElMessage.warning('只能上传一个文件')"
                    accept=".zip,.tar,.gz,.rar,.7z"
                    style="display:inline-block"
                  >
                    <el-button type="primary" plain size="small"><el-icon><Upload /></el-icon>选择文件</el-button>
                  </el-upload>
                  <el-button type="primary" size="small" :loading="codeUploading" @click="doUploadCode">
                    {{ canReuploadAtStep('code_review') ? '重新上传代码包' : '上传代码包' }}
                  </el-button>
                  <!-- 代码包上传进度条 -->
                  <el-progress
                    v-if="codeUploadProgress > 0 && codeUploadProgress < 100"
                    :percentage="codeUploadProgress"
                    :stroke-width="6"
                    status="success"
                    style="margin-top: 8px; width: 100%"
                  />
                </template>
                <template v-if="release.status === 'code_pending_review'">
                  <el-button type="primary" size="small" :loading="triggering" @click="handleTriggerReview">
                    <el-icon><Refresh /></el-icon>触发评审
                  </el-button>
                  <el-button v-if="canSkipReview" type="warning" plain size="small" @click="handleSkipReview">
                    <el-icon><Clock /></el-icon>稍后评审
                  </el-button>
                  <el-button v-if="canForceAdvance" type="danger" plain size="small" @click="handleForceAdvance">
                    <el-icon><Promotion /></el-icon>特批放行
                  </el-button>
                </template>
              </div>
            </div>
            <div v-if="getReviewByType('code_review')" class="review-result-box">
              <strong>结论:</strong> {{ getReviewByType('code_review')!.conclusion || '—' }}
              <span v-if="getReviewByType('code_review')!.suggestions" style="margin-left:12px">
                <strong>建议:</strong>{{ getReviewByType('code_review')!.suggestions }}
              </span>
            </div>
          </div>

          <div class="step-connector">↓</div>

          <!-- 步骤 3:测试报告上传 + LLM 评审 -->
          <div :class="['step-box', step3Status]">
            <div class="step-header">
              <span class="step-number">3</span>
              <span>测试报告上传 + LLM 评审</span>
            </div>
            <div class="step-content">
              <div class="step-info">
                <div>
                  <span class="label">上传人:</span>
                  <span v-if="release.test_report_uploader_name">{{ release.test_report_uploader_name }}</span>
                  <span v-else class="mono-id">{{ release.test_report_uploaded_by || '—' }}</span>
                </div>
                <div><span class="label">上传时间:</span>{{ formatTime(release.test_report_uploaded_at) }}</div>
                <div v-if="release.test_report_path">
                  <span class="label">文件名:</span>{{ fileNameFromPath(release.test_report_path) }}
                  <el-button
                    v-if="canDeleteArtifactByType(release.test_report_uploaded_by)"
                    link
                    type="danger"
                    size="small"
                    style="margin-left:8px"
                    @click="handleDeleteArtifactByType('test_report', fileNameFromPath(release.test_report_path))"
                  >
                    <el-icon><Delete /></el-icon>删除
                  </el-button>
                </div>
                <div v-if="getReviewByType('test_report_review')">
                  <span class="label">评审结果:</span>
                  <el-tag :type="reviewResultTagType(getReviewByType('test_report_review')!.result)" size="small">
                    {{ reviewResultLabel(getReviewByType('test_report_review')!.result) }}
                  </el-tag>
                  <span v-if="getReviewByType('test_report_review')!.total_score !== null" style="margin-left:8px">
                    分数:<b>{{ getReviewByType('test_report_review')!.total_score }}</b>
                  </span>
                </div>
              </div>
              <div class="step-actions">
                <template v-if="release.status === 'test_pending_review' || canReuploadAtStep('test_report_review')">
                  <el-upload
                    :auto-upload="false"
                    :limit="1"
                    :on-change="handleTestFileChange"
                    :on-exceed="() => ElMessage.warning('只能上传一个文件')"
                    accept=".pdf,.doc,.docx,.xlsx,.zip"
                    style="display:inline-block"
                  >
                    <el-button type="primary" plain size="small"><el-icon><Upload /></el-icon>选择文件</el-button>
                  </el-upload>
                  <el-button type="primary" size="small" :loading="testUploading" @click="doUploadTest">
                    {{ canReuploadAtStep('test_report_review') ? '重新上传测试报告' : '上传测试报告' }}
                  </el-button>
                  <!-- 测试报告上传进度条 -->
                  <el-progress
                    v-if="testUploadProgress > 0 && testUploadProgress < 100"
                    :percentage="testUploadProgress"
                    :stroke-width="6"
                    status="success"
                    style="margin-top: 8px; width: 100%"
                  />
                </template>
                <template v-if="release.status === 'test_pending_review'">
                  <el-button type="primary" size="small" :loading="triggering" @click="handleTriggerReview">
                    <el-icon><Refresh /></el-icon>触发评审
                  </el-button>
                  <el-button v-if="canSkipReview" type="warning" plain size="small" @click="handleSkipReview">
                    <el-icon><Clock /></el-icon>稍后评审
                  </el-button>
                  <el-button v-if="canForceAdvance" type="danger" plain size="small" @click="handleForceAdvance">
                    <el-icon><Promotion /></el-icon>特批放行
                  </el-button>
                </template>
              </div>
            </div>
            <div v-if="getReviewByType('test_report_review')" class="review-result-box">
              <strong>结论:</strong> {{ getReviewByType('test_report_review')!.conclusion || '—' }}
              <span v-if="getReviewByType('test_report_review')!.suggestions" style="margin-left:12px">
                <strong>建议:</strong>{{ getReviewByType('test_report_review')!.suggestions }}
              </span>
            </div>
          </div>

          <div class="step-connector">↓</div>

          <!-- 步骤 4:评审报告上传 + LLM 评审 -->
          <div :class="['step-box', step4Status]">
            <div class="step-header">
              <span class="step-number">4</span>
              <span>评审报告上传 + LLM 评审</span>
            </div>
            <div class="step-content">
              <div class="step-info">
                <div>
                  <span class="label">上传人:</span>
                  <span v-if="release.review_report_uploader_name">{{ release.review_report_uploader_name }}</span>
                  <span v-else class="mono-id">{{ release.review_report_uploaded_by || '—' }}</span>
                </div>
                <div><span class="label">上传时间:</span>{{ formatTime(release.review_report_uploaded_at) }}</div>
                <div v-if="release.review_report_path">
                  <span class="label">文件名:</span>{{ fileNameFromPath(release.review_report_path) }}
                  <el-button
                    v-if="canDeleteArtifactByType(release.review_report_uploaded_by)"
                    link
                    type="danger"
                    size="small"
                    style="margin-left:8px"
                    @click="handleDeleteArtifactByType('review_report', fileNameFromPath(release.review_report_path))"
                  >
                    <el-icon><Delete /></el-icon>删除
                  </el-button>
                </div>
                <div v-if="getReviewByType('expert_report_review')">
                  <span class="label">评审结果:</span>
                  <el-tag :type="reviewResultTagType(getReviewByType('expert_report_review')!.result)" size="small">
                    {{ reviewResultLabel(getReviewByType('expert_report_review')!.result) }}
                  </el-tag>
                  <span v-if="getReviewByType('expert_report_review')!.total_score !== null" style="margin-left:8px">
                    分数:<b>{{ getReviewByType('expert_report_review')!.total_score }}</b>
                  </span>
                </div>
              </div>
              <div class="step-actions">
                <template v-if="release.status === 'expert_pending_review' || canReuploadAtStep('expert_report_review')">
                  <el-upload
                    :auto-upload="false"
                    :limit="1"
                    :on-change="handleReviewFileChange"
                    :on-exceed="() => ElMessage.warning('只能上传一个文件')"
                    accept=".pdf,.doc,.docx,.zip"
                    style="display:inline-block"
                  >
                    <el-button type="primary" plain size="small"><el-icon><Upload /></el-icon>选择文件</el-button>
                  </el-upload>
                  <el-button type="primary" size="small" :loading="reviewUploading" @click="doUploadReviewReport">
                    {{ canReuploadAtStep('expert_report_review') ? '重新上传评审报告' : '上传评审报告' }}
                  </el-button>
                  <!-- 评审报告上传进度条 -->
                  <el-progress
                    v-if="reviewUploadProgress > 0 && reviewUploadProgress < 100"
                    :percentage="reviewUploadProgress"
                    :stroke-width="6"
                    status="success"
                    style="margin-top: 8px; width: 100%"
                  />
                </template>
                <template v-if="release.status === 'expert_pending_review'">
                  <el-button type="primary" size="small" :loading="triggering" @click="handleTriggerReview">
                    <el-icon><Refresh /></el-icon>触发评审
                  </el-button>
                  <el-button v-if="canSkipReview" type="warning" plain size="small" @click="handleSkipReview">
                    <el-icon><Clock /></el-icon>稍后评审
                  </el-button>
                  <el-button v-if="canForceAdvance" type="danger" plain size="small" @click="handleForceAdvance">
                    <el-icon><Promotion /></el-icon>特批放行
                  </el-button>
                </template>
              </div>
            </div>
            <div v-if="getReviewByType('expert_report_review')" class="review-result-box">
              <strong>结论:</strong> {{ getReviewByType('expert_report_review')!.conclusion || '—' }}
              <span v-if="getReviewByType('expert_report_review')!.suggestions" style="margin-left:12px">
                <strong>建议:</strong>{{ getReviewByType('expert_report_review')!.suggestions }}
              </span>
            </div>
          </div>

          <div class="step-connector">↓</div>

          <!-- 步骤 5:PM 确认释放 -->
          <div :class="['step-box', step5Status]">
            <div class="step-header">
              <span class="step-number">5</span>
              <span>PM 确认释放</span>
            </div>
            <div class="step-content">
              <div class="step-info">
                <div>
                  <span class="label">确认人:</span>
                  <span v-if="release.confirmed_by_name">{{ release.confirmed_by_name }}</span>
                  <span v-else class="mono-id">{{ release.confirmed_by || '—' }}</span>
                </div>
                <div><span class="label">确认时间:</span>{{ formatTime(release.confirmed_at) }}</div>
                <!-- 功能7:特批放行人展示 -->
                <div v-if="release.force_advanced_by_name" class="force-advance-info">
                  <span class="label">特批放行人:</span>
                  <el-tag type="warning" size="small" effect="plain">
                    <el-icon style="margin-right:4px"><Promotion /></el-icon>{{ release.force_advanced_by_name }}
                  </el-tag>
                  <span style="margin-left:8px;color:#909399">{{ formatTime(release.force_advanced_at) }}</span>
                </div>
              </div>
              <div class="step-actions">
                <template v-if="release.status === 'pending_confirm'">
                  <el-button type="success" size="small" :loading="confirming" @click="handleConfirm">
                    <el-icon><Check /></el-icon>确认释放
                  </el-button>
                  <el-button v-if="canForceAdvance" type="danger" plain size="small" @click="handleForceAdvance">
                    <el-icon><Promotion /></el-icon>特批放行
                  </el-button>
                </template>
                <template v-if="release.status === 'released'">
                  <el-tag type="success" size="small">已释放</el-tag>
                  <el-button v-if="release.download_link" type="primary" size="small" @click="openLink(release.download_link)">
                    <el-icon><Download /></el-icon>下载完整交付包
                  </el-button>
                </template>
              </div>
            </div>
          </div>
        </div>
      </el-card>

      <!-- LLM 评审结果 -->
      <el-card class="table-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span>LLM 评审结果</span>
            <div class="trigger-area">
              <!-- LLM 评审中状态标签(从后端 reviews 推断,切换页面不丢失) -->
              <el-tag
                v-if="reviewInProgress"
                type="warning"
                size="default"
                effect="light"
                class="review-in-progress-tag"
              >
                <el-icon class="is-loading" size="14" style="margin-right: 4px"><Loading /></el-icon>
                {{ reviewInProgressLabel }}
              </el-tag>
              <el-select v-if="canTrigger" v-model="triggerReviewType" size="small" style="width: 160px">
                <el-option
                  v-for="opt in reviewTypeOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-button v-if="canTrigger" type="primary" size="small" :loading="triggering" @click="handleTriggerReview">
                <el-icon><Refresh /></el-icon>触发评审
              </el-button>
              <el-tooltip content="跳过当前 LLM 评审,直接进入下一阶段(开发/测试人员可用)" placement="top">
                <el-button v-if="canSkipReview" type="warning" plain size="small" @click="handleSkipReview">
                  <el-icon><Clock /></el-icon>稍后 LLM 评审
                </el-button>
              </el-tooltip>
              <el-tooltip content="跳过剩余所有评审,直接释放版本(仅 PM/管理员可用)" placement="top">
                <el-button v-if="canForceAdvance" type="danger" plain size="small" @click="handleForceAdvance">
                  <el-icon><Promotion /></el-icon>特批放行
                </el-button>
              </el-tooltip>
            </div>
          </div>
        </template>

        <!-- 功能2: 评审历史时间线(多轮对比) -->
        <el-timeline v-if="reviews.length > 0" class="review-timeline">
          <el-timeline-item
            v-for="review in reviews"
            :key="review.id"
            :timestamp="formatTime(review.created_at)"
            :type="review.result === 'passed' ? 'success' : review.result === 'failed' ? 'danger' : review.result === 'pending' ? 'primary' : 'info'"
            placement="top"
          >
            <el-card shadow="hover" class="timeline-card">
              <h4 class="timeline-title">{{ reviewTypeLabel(review.review_type) }} · 第 {{ review.review_round }} 轮</h4>
              <p class="timeline-line"><span class="timeline-label">结果:</span>
                <el-tag size="small" :type="reviewResultTagType(review.result)">{{ reviewResultLabel(review.result) }}</el-tag>
              </p>
              <p v-if="review.total_score !== null" class="timeline-line">
                <span class="timeline-label">总分:</span>{{ review.total_score }}
              </p>
              <p v-if="review.model_used" class="timeline-line">
                <span class="timeline-label">模型:</span>{{ review.model_used }}
              </p>
              <p v-if="review.conclusion" class="timeline-line">
                <span class="timeline-label">结论:</span>{{ review.conclusion }}
              </p>
              <p v-if="review.suggestions" class="timeline-line">
                <span class="timeline-label">建议:</span>{{ review.suggestions }}
              </p>
            </el-card>
          </el-timeline-item>
        </el-timeline>

        <el-empty v-if="reviews.length === 0" description="暂无评审记录" />

        <div v-else class="review-list">
          <el-card
            v-for="r in reviews"
            :key="r.id"
            shadow="hover"
            class="review-item"
          >
            <div class="review-item-header">
              <el-tag>{{ reviewTypeLabel(r.review_type) }}</el-tag>
              <el-tag :type="reviewResultTagType(r.result)">{{ reviewResultLabel(r.result) }}</el-tag>
              <span class="review-round">第 {{ r.review_round }} 轮</span>
              <span class="review-model" v-if="r.model_used">模型：{{ r.model_used }}</span>
              <span class="review-trigger" v-if="r.triggered_by">触发人：{{ r.triggered_by_name || r.triggered_by.slice(0,8) }}</span>
              <span class="review-time">{{ formatTime(r.created_at) }}</span>
            </div>

            <el-descriptions :column="2" border size="small" style="margin-top: 12px">
              <el-descriptions-item label="总分">
                <span v-if="r.total_score !== null" class="score">{{ r.total_score }}</span>
                <span v-else>—</span>
              </el-descriptions-item>
              <el-descriptions-item label="完成时间">{{ formatTime(r.completed_at) }}</el-descriptions-item>
              <el-descriptions-item label="分项评分" :span="2">
                <div v-if="dimensionEntries(r.dimension_scores).length" class="dim-scores">
                  <el-tag
                    v-for="[k, v] in dimensionEntries(r.dimension_scores)"
                    :key="k"
                    type="info"
                    effect="plain"
                    class="dim-tag"
                  >
                    {{ k }}: {{ v }}
                  </el-tag>
                </div>
                <span v-else>—</span>
              </el-descriptions-item>
              <el-descriptions-item label="结论" :span="2">{{ r.conclusion || '—' }}</el-descriptions-item>
              <el-descriptions-item label="建议" :span="2">{{ r.suggestions || '—' }}</el-descriptions-item>
              <el-descriptions-item label="风险点" :span="2">
                <span class="risk-text">{{ r.risk_points || '—' }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </div>
      </el-card>

      <!-- 交付物列表(所有状态可见) -->
      <el-card class="table-card" shadow="never">
        <template #header>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>交付物</span>
            <el-tag v-if="isReleased" type="success" size="small">已释放</el-tag>
            <el-tag v-else-if="artifacts.length > 0" type="warning" size="small">{{ artifacts.length }} 个文件</el-tag>
          </div>
        </template>

        <!-- 变更点描述 -->
        <el-alert
          v-if="release.change_notes"
          type="info"
          :closable="false"
          show-icon
          :title="`变更点描述：${release.change_notes}`"
          style="margin-bottom: 12px"
        />

        <!-- 交付物表格 -->
        <el-table :data="artifacts" border stripe>
          <el-table-column label="文件名" min-width="280">
            <template #default="{ row }">
              <div style="display:flex;align-items:center;gap:6px">
                <el-icon style="color:#409eff"><Document /></el-icon>
                <span :title="row.fileName" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ row.fileName }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="row.fileType === 'code_package' ? 'warning' : row.fileType === 'test_report' ? 'success' : 'danger'">
                {{ row.label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="上传人" width="150">
            <template #default="{ row }">
              <span v-if="row.uploaderName">{{ row.uploaderName }}</span>
              <span v-else-if="row.uploaderId" class="mono-id">{{ row.uploaderId.slice(0, 8) }}…</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="上传时间" width="170">
            <template #default="{ row }">{{ formatTime(row.uploadedAt) }}</template>
          </el-table-column>
          <el-table-column label="SHA256" width="200">
            <template #default="{ row }">
              <el-tooltip
                v-if="row.sha256"
                :content="row.sha256"
                placement="top"
              >
                <span class="sha256-value" @click="copySha256(row.sha256)">
                  SHA256: {{ row.sha256.substring(0, 16) }}...
                </span>
              </el-tooltip>
              <span v-else style="color:#909399">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button
                type="primary"
                link
                :loading="downloading === row.fileType"
                @click="downloadArtifactFile(row.fileType)"
              >
                <el-icon><Download /></el-icon>下载
              </el-button>
              <el-button
                v-if="canDeleteArtifact(row)"
                type="danger"
                link
                @click="handleDeleteArtifact(row)"
              >
                <el-icon><Delete /></el-icon>删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 已释放时的完整交付包下载 -->
        <div v-if="isReleased" style="margin-top:12px;padding-top:12px;border-top:1px dashed #e4e7ed">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <el-button v-if="release.download_link" type="primary" @click="openLink(release.download_link)">
              <el-icon><Download /></el-icon>下载完整交付包
            </el-button>
            <span v-if="release.link_expiry" class="expiry-text" style="color:#909399;font-size:12px">
              预签名链接有效期至：{{ formatTime(release.link_expiry) }}
            </span>
          </div>
        </div>

        <!-- 功能2.4: 外部接收方下载链接(含 access_token) -->
        <div
          v-if="isReleased && externalLinks.length > 0"
          style="margin-top:12px;padding-top:12px;border-top:1px dashed #e4e7ed"
        >
          <div style="font-weight:600;margin-bottom:8px">外部接收方下载链接</div>
          <el-table :data="externalLinks" border stripe size="small">
            <el-table-column label="接收方" min-width="180">
              <template #default="{ row }">
                <div>{{ row.name || row.email }}</div>
                <div style="color:#909399;font-size:12px">{{ row.email }}</div>
              </template>
            </el-table-column>
            <el-table-column label="Access Token" min-width="200">
              <template #default="{ row }">
                <span v-if="row.access_token" class="mono-id">
                  {{ row.access_token.substring(0, 16) }}…
                </span>
                <span v-else style="color:#909399">未生成</span>
              </template>
            </el-table-column>
            <el-table-column label="下载次数" width="120">
              <template #default="{ row }">
                {{ row.download_count }} / {{ row.max_downloads }}
              </template>
            </el-table-column>
            <el-table-column label="过期时间" width="170">
              <template #default="{ row }">
                {{ row.token_expires_at ? formatTime(row.token_expires_at) : '—' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.download_link"
                  type="primary"
                  link
                  @click="copyDownloadLink(row.download_link)"
                >
                  复制链接
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 空状态 -->
        <el-empty v-if="artifacts.length === 0" description="暂无已上传的交付物" :image-size="80" />
      </el-card>
    </template>

    <!-- LLM 评审进度抽屉 -->
    <el-drawer
      v-model="reviewDrawerVisible"
      :with-header="false"
      :modal="false"
      :size="reviewDrawerCollapsed ? '48px' : '440px'"
      direction="rtl"
      :show-close="false"
      :append-to-body="true"
      modal-class="review-drawer-overlay"
      class="review-drawer"
    >
      <div class="review-drawer-content" :class="{ collapsed: reviewDrawerCollapsed }">
        <!-- 收缩状态:只显示一个展开按钮 + 当前步骤缩略 -->
        <div v-if="reviewDrawerCollapsed" class="drawer-collapsed-bar">
          <el-button link @click="toggleReviewDrawer" title="向左展开">
            <el-icon size="20"><DArrowLeft /></el-icon>
          </el-button>
          <div class="collapsed-status" :class="'status-' + reviewCurrentStatus">
            <el-icon
              v-if="reviewCurrentStatus === 'running' || reviewCurrentStatus === 'triggering'"
              class="is-loading"
              size="16"
            ><Loading /></el-icon>
            <el-icon v-else-if="reviewCurrentStatus === 'passed'" size="16" color="#67c23a"><CircleCheck /></el-icon>
            <el-icon v-else-if="reviewCurrentStatus === 'failed'" size="16" color="#e6a23c"><WarningFilled /></el-icon>
            <el-icon v-else-if="reviewCurrentStatus === 'error'" size="16" color="#f56c6c"><CircleClose /></el-icon>
          </div>
          <div class="collapsed-text">
            {{ reviewCurrentStep || '评审进度' }}
            <span v-if="reviewCurrentStatus === 'running' || reviewCurrentStatus === 'triggering'" class="collapsed-elapsed">
              {{ formatElapsed(reviewElapsedSec) }}
            </span>
          </div>
        </div>
        <!-- 展开状态:完整内容 -->
        <div v-else class="drawer-expanded-content">
          <div class="drawer-header">
            <span>LLM 评审进度</span>
            <el-button link @click="toggleReviewDrawer" title="向右收缩">
              <el-icon size="18"><DArrowRight /></el-icon>
            </el-button>
          </div>

          <!-- 当前步骤醒目展示卡 -->
          <div class="current-step-card" :class="'status-' + reviewCurrentStatus">
            <div class="step-card-row">
              <div class="step-icon">
                <el-icon
                  v-if="reviewCurrentStatus === 'running' || reviewCurrentStatus === 'triggering'"
                  class="is-loading"
                  size="22"
                ><Loading /></el-icon>
                <el-icon v-else-if="reviewCurrentStatus === 'passed'" size="22" color="#67c23a"><CircleCheck /></el-icon>
                <el-icon v-else-if="reviewCurrentStatus === 'failed'" size="22" color="#e6a23c"><WarningFilled /></el-icon>
                <el-icon v-else-if="reviewCurrentStatus === 'error'" size="22" color="#f56c6c"><CircleClose /></el-icon>
                <el-icon v-else size="22" color="#909399"><InfoFilled /></el-icon>
              </div>
              <div class="step-text">
                <div class="step-label">当前步骤</div>
                <div class="step-value">{{ reviewCurrentStep || '等待开始' }}</div>
              </div>
              <div class="step-elapsed" v-if="reviewCurrentStatus === 'running' || reviewCurrentStatus === 'triggering'">
                <div class="elapsed-label">已耗时</div>
                <div class="elapsed-value">{{ formatElapsed(reviewElapsedSec) }}</div>
              </div>
            </div>
            <div class="step-hint" v-if="reviewCurrentStatus === 'running'">
              大模型正在分析中,请耐心等待... 通常需要 30 秒 ~ 2 分钟
            </div>
            <div class="step-hint" v-else-if="reviewCurrentStatus === 'triggering'">
              正在提交评审请求...
            </div>
            <div class="step-hint success" v-else-if="reviewCurrentStatus === 'passed'">
              评审已通过,可继续下一步操作
            </div>
            <div class="step-hint warning" v-else-if="reviewCurrentStatus === 'failed'">
              评审未通过,请查看下方建议并改进
            </div>
            <div class="step-hint error" v-else-if="reviewCurrentStatus === 'error'">
              评审出错,请查看日志或联系管理员
            </div>
          </div>

          <div class="review-log-header">
            <span>实时日志</span>
            <div class="review-log-actions">
              <el-button size="small" link @click="clearReviewLogs">清空</el-button>
              <el-button size="small" link @click="exportReviewLogs">导出 .txt</el-button>
            </div>
          </div>
          <div class="review-log-list">
            <div
              v-for="(log, i) in reviewProgressLogs"
              :key="i"
              class="review-log-item"
              :class="'log-' + log.type"
            >
              <span class="log-time">{{ log.time }}</span>
              <span class="log-msg">{{ log.msg }}</span>
            </div>
            <div v-if="reviewProgressLogs.length === 0" class="log-empty">
              暂无评审进度日志
            </div>
            <div v-if="reviewCurrentStatus === 'running' || reviewCurrentStatus === 'triggering'" class="log-pending">
              <span class="log-dot">·</span>
              <span>等待 LLM 返回<span class="loading-dots"><span>.</span><span>.</span><span>.</span></span></span>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.force-advance-info {
  margin-top: 6px;
  padding: 6px 8px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 2px;
}
.release-breadcrumb {
  margin-bottom: 12px;
  font-size: 13px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.detail-header .page-title {
  margin: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.trigger-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* LLM 评审中状态标签 */
.review-in-progress-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  animation: pulse-tag 2s ease-in-out infinite;
}
@keyframes pulse-tag {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.75; }
}

.mono-id {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}
.sha256-value {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  color: var(--el-color-primary);
  cursor: pointer;
}
.sha256-value:hover {
  text-decoration: underline;
}

.upload-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.review-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-item {
  border: 1px solid #ebeef5;
}

.review-item-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.review-round,
.review-model,
.review-time {
  font-size: 12px;
  color: #909399;
}

.score {
  font-size: 18px;
  font-weight: 700;
  color: #409eff;
}

.dim-scores {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.dim-tag {
  font-size: 12px;
}

.risk-text {
  color: #f56c6c;
}

.download-links {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}

.expiry-text {
  font-size: 12px;
  color: #909399;
}

/* LLM 评审进度抽屉 */
/* 关键修复:让 overlay 不拦截左侧页面事件,但 drawer 本身可点击 */
:global(.review-drawer-overlay) {
  pointer-events: none !important;
  background: transparent !important;
}
:global(.review-drawer-overlay .el-drawer) {
  pointer-events: auto;
}
.review-drawer :deep(.el-drawer__body) {
  padding: 0;
}
.review-drawer-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.drawer-collapsed-bar {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0 12px 0;
  gap: 12px;
}
.collapsed-status {
  display: flex;
  align-items: center;
  justify-content: center;
}
.collapsed-status .is-loading {
  color: #409eff;
}
.collapsed-text {
  writing-mode: vertical-rl;
  font-size: 12px;
  color: #606266;
  text-align: center;
  line-height: 1.4;
  word-break: break-all;
  max-height: 280px;
  overflow: hidden;
}
.collapsed-elapsed {
  color: #409eff;
  font-weight: bold;
  font-family: monospace;
}
.drawer-expanded-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.drawer-header {
  padding: 12px 16px;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  font-size: 14px;
}

/* 当前步骤醒目展示卡 */
.current-step-card {
  margin: 12px 14px 8px;
  padding: 14px 16px;
  border-radius: 8px;
  background: #f0f7ff;
  border-left: 4px solid #409eff;
  transition: all 0.3s;
}
.current-step-card.status-triggering,
.current-step-card.status-running {
  background: linear-gradient(135deg, #f0f7ff 0%, #e6f1ff 100%);
  border-left-color: #409eff;
  animation: pulse-border 2s ease-in-out infinite;
}
.current-step-card.status-passed {
  background: #f0f9eb;
  border-left-color: #67c23a;
}
.current-step-card.status-failed {
  background: #fdf6ec;
  border-left-color: #e6a23c;
}
.current-step-card.status-error {
  background: #fef0f0;
  border-left-color: #f56c6c;
}
.current-step-card.status-idle {
  background: #f4f4f5;
  border-left-color: #909399;
}
@keyframes pulse-border {
  0%, 100% { box-shadow: 0 0 0 0 rgba(64, 158, 255, 0.3); }
  50% { box-shadow: 0 0 0 6px rgba(64, 158, 255, 0); }
}
.step-card-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.step-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.step-text {
  flex: 1;
  min-width: 0;
}
.step-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 2px;
}
.step-value {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  word-break: break-word;
  line-height: 1.3;
}
.step-elapsed {
  flex-shrink: 0;
  text-align: right;
}
.elapsed-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 2px;
}
.elapsed-value {
  font-size: 18px;
  font-weight: bold;
  color: #409eff;
  font-family: monospace;
  line-height: 1;
}
.step-hint {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed rgba(0,0,0,0.08);
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}
.step-hint.success { color: #67c23a; }
.step-hint.warning { color: #e6a23c; }
.step-hint.error { color: #f56c6c; }

.review-log-header {
  padding: 8px 16px 4px;
  font-size: 12px;
  color: #909399;
  font-weight: 500;
  background: #fafafa;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.review-log-actions {
  display: flex;
  gap: 8px;
}
.review-log-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
  background: #fafafa;
}
.review-log-item {
  padding: 6px 8px;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
  line-height: 1.6;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.log-time {
  color: #909399;
  font-family: monospace;
  font-size: 12px;
  flex-shrink: 0;
}
.log-msg {
  flex: 1;
  word-break: break-word;
}
.log-info { color: #606266; }
.log-success { color: #67c23a; }
.log-warning { color: #e6a23c; }
.log-error { color: #f56c6c; }
.log-empty {
  color: #c0c4cc;
  text-align: center;
  padding: 24px;
  font-size: 13px;
}
.log-pending {
  padding: 8px;
  font-size: 12px;
  color: #909399;
  display: flex;
  gap: 6px;
  align-items: center;
  font-style: italic;
}
.log-dot {
  color: #409eff;
  font-weight: bold;
  animation: blink 1.4s infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.loading-dots span {
  display: inline-block;
  animation: dot-bounce 1.4s infinite;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-bounce {
  0%, 80%, 100% { opacity: 0.2; }
  40% { opacity: 1; }
}

/* ============ 流水线方框样式 ============ */
.pipeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.step-box {
  border: 1px solid #e4e7ed;
  border-left: 4px solid #c0c4cc;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 8px;
  background: #fff;
  position: relative;
}
.step-box.current { border-left-color: #409eff; background: #f0f7ff; }
.step-box.in_progress { border-left-color: #e6a23c; background: #fdf6ec; }
.step-box.completed { border-left-color: #67c23a; }
.step-box.failed { border-left-color: #f56c6c; background: #fef0f0; }
.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: bold;
}
.step-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #c0c4cc;
  color: #fff;
  font-size: 13px;
  flex-shrink: 0;
}
.step-box.current .step-number { background: #409eff; }
.step-box.in_progress .step-number { background: #e6a23c; }
.step-box.completed .step-number { background: #67c23a; }
.step-box.failed .step-number { background: #f56c6c; }
.step-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.step-info { font-size: 14px; line-height: 1.8; color: #606266; }
.step-info .label { color: #909399; margin-right: 6px; }
.step-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start; }
.step-connector {
  text-align: center;
  color: #c0c4cc;
  font-size: 20px;
  margin: -4px 0;
  line-height: 1;
}
.review-result-box {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  background: #f5f7fa;
  font-size: 13px;
}
@media (max-width: 768px) {
  .step-content { grid-template-columns: 1fr; }
}

/* 功能2: 评审历史时间线样式 */
.review-timeline {
  margin-bottom: 24px;
}
.timeline-card {
  margin: 0;
}
.timeline-title {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
}
.timeline-line {
  margin: 4px 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.timeline-label {
  color: #909399;
  margin-right: 4px;
}

</style>
