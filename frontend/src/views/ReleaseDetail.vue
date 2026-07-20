<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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
} from '@/api/releases'
import { getReleaseReviews, triggerReview } from '@/api/reviews'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'
import {
  reviewResultLabel,
  reviewResultTagType,
  reviewTypeLabel,
  statusLabel,
  statusTagType,
} from '@/utils/status'
import type { LLMReview, Release, ReviewType } from '@/types'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const releaseId = computed(() => route.params.id as string)
const release = ref<Release | null>(null)
const reviews = ref<LLMReview[]>([])
const loading = ref(false)

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

// 根据当前状态推断默认评审类型
function syncTriggerType() {
  const status = release.value?.status
  if (status === 'code_pending_review') triggerReviewType.value = 'code_review'
  else if (status === 'test_pending_review') triggerReviewType.value = 'test_report_review'
  else if (status === 'expert_pending_review') triggerReviewType.value = 'expert_report_review'
}

// 文件上传
const codeFile = ref<File | null>(null)
const codeChangeNotes = ref('')
const codeUploading = ref(false)

const testFile = ref<File | null>(null)
const testUploading = ref(false)

const reviewFile = ref<File | null>(null)
const reviewUploading = ref(false)

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
  try {
    release.value = await uploadCodePackage(releaseId.value, codeFile.value, codeChangeNotes.value || undefined)
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
  try {
    release.value = await uploadTestReport(releaseId.value, testFile.value)
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
  try {
    release.value = await uploadReviewReport(releaseId.value, reviewFile.value)
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
  try {
    await triggerReview(releaseId.value, triggerReviewType.value)
    ElMessage.success('评审任务已提交，请稍后刷新查看结果')
    // 轮询刷新评审结果
    setTimeout(() => loadReviews(), 2000)
  } catch {
    // 错误已统一提示
  } finally {
    triggering.value = false
  }
}

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
    })
  }
  return items
})

function dimensionEntries(scores: Record<string, number> | null): [string, number][] {
  if (!scores) return []
  return Object.entries(scores)
}

async function loadRelease() {
  loading.value = true
  try {
    release.value = await getRelease(releaseId.value)
    syncTriggerType()
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

onMounted(async () => {
  await loadRelease()
  await loadReviews()
})
</script>

<template>
  <div class="page-container" v-loading="loading">
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
      <!-- 流程可视化 -->
      <el-card class="table-card" shadow="never">
        <template #header><span>释放流程</span></template>
        <el-steps :active="activeStep" finish-status="success" align-center>
          <el-step v-for="(s, i) in steps" :key="i" :title="s.title" />
        </el-steps>
        <el-alert
          v-if="isFailed"
          type="error"
          show-icon
          :closable="false"
          title="评审未通过"
          description="本次释放在评审环节未通过，请根据评审建议修改后重新上传。"
          style="margin-top: 16px"
        />
      </el-card>

      <!-- 基本信息 -->
      <el-card class="table-card" shadow="never">
        <template #header><span>基本信息</span></template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="释放序号">{{ release.release_number }}</el-descriptions-item>
          <el-descriptions-item label="版本 ID">
            <span class="mono-id">{{ release.version_id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(release.status)">{{ statusLabel(release.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="变更点" :span="3">
            {{ release.change_notes || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(release.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="确认人">
            <span v-if="release.confirmed_by_name">{{ release.confirmed_by_name }}</span>
            <span v-else class="mono-id">{{ release.confirmed_by || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="确认时间">{{ formatTime(release.confirmed_at) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>


      <!-- 各节点上传人/触发人 -->
      <el-card class="table-card" shadow="never">
        <template #header><span>节点操作人</span></template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="代码包上传人">
            <span v-if="release.code_package_uploader_name">{{ release.code_package_uploader_name }}</span>
            <span v-else class="mono-id">{{ release.code_package_uploaded_by || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="代码包上传时间">{{ formatTime(release.code_package_uploaded_at) }}</el-descriptions-item>
          <el-descriptions-item label="测试报告上传人">
            <span v-if="release.test_report_uploader_name">{{ release.test_report_uploader_name }}</span>
            <span v-else class="mono-id">{{ release.test_report_uploaded_by || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="测试报告上传时间">{{ formatTime(release.test_report_uploaded_at) }}</el-descriptions-item>
          <el-descriptions-item label="评审报告上传人">
            <span v-if="release.review_report_uploader_name">{{ release.review_report_uploader_name }}</span>
            <span v-else class="mono-id">{{ release.review_report_uploaded_by || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="评审报告上传时间">{{ formatTime(release.review_report_uploaded_at) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 文件上传区域 -->
      <el-card class="table-card" shadow="never" v-if="release.status === 'draft'">
        <template #header><span>代码包上传</span></template>
        <el-form label-width="90px">
          <el-form-item label="变更点">
            <el-input
              v-model="codeChangeNotes"
              type="textarea"
              :rows="3"
              placeholder="请描述本次代码包的变更点"
            />
          </el-form-item>
          <el-form-item label="代码包">
            <el-upload
              :auto-upload="false"
              :limit="1"
              :on-change="handleCodeFileChange"
              :on-exceed="() => ElMessage.warning('只能上传一个文件')"
              accept=".zip,.tar,.gz,.rar,.7z"
            >
              <el-button type="primary" plain><el-icon><Upload /></el-icon>选择文件</el-button>
              <template #tip>
                <div class="upload-tip">支持 zip / tar / gz 等压缩包格式</div>
              </template>
            </el-upload>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="codeUploading" @click="doUploadCode">上传代码包</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="table-card" shadow="never" v-if="release.status === 'test_pending_review'">
        <template #header><span>测试报告上传</span></template>
        <el-form label-width="90px">
          <el-form-item label="测试报告">
            <el-upload
              :auto-upload="false"
              :limit="1"
              :on-change="handleTestFileChange"
              :on-exceed="() => ElMessage.warning('只能上传一个文件')"
              accept=".pdf,.doc,.docx,.xlsx,.zip"
            >
              <el-button type="primary" plain><el-icon><Upload /></el-icon>选择文件</el-button>
              <template #tip>
                <div class="upload-tip">支持 PDF / Word / Excel / 压缩包</div>
              </template>
            </el-upload>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="testUploading" @click="doUploadTest">上传测试报告</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="table-card" shadow="never" v-if="release.status === 'expert_pending_review'">
        <template #header><span>评审报告上传</span></template>
        <el-form label-width="90px">
          <el-form-item label="评审报告">
            <el-upload
              :auto-upload="false"
              :limit="1"
              :on-change="handleReviewFileChange"
              :on-exceed="() => ElMessage.warning('只能上传一个文件')"
              accept=".pdf,.doc,.docx,.zip"
            >
              <el-button type="primary" plain><el-icon><Upload /></el-icon>选择文件</el-button>
              <template #tip>
                <div class="upload-tip">支持 PDF / Word / 压缩包</div>
              </template>
            </el-upload>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="reviewUploading" @click="doUploadReviewReport">上传评审报告</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- LLM 评审结果 -->
      <el-card class="table-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span>LLM 评审结果</span>
            <div v-if="canTrigger" class="trigger-area">
              <el-select v-model="triggerReviewType" size="small" style="width: 160px">
                <el-option
                  v-for="opt in reviewTypeOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-button type="primary" size="small" :loading="triggering" @click="handleTriggerReview">
                <el-icon><Refresh /></el-icon>触发评审
              </el-button>
            </div>
          </div>
        </template>

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

      <!-- PM 确认释放 -->
      <el-card class="table-card" shadow="never" v-if="release.status === 'pending_confirm'">
        <template #header><span>释放确认</span></template>
        <el-alert
          type="success"
          show-icon
          :closable="false"
          title="所有评审已通过，等待项目经理确认释放。"
          style="margin-bottom: 12px"
        />
        <el-button type="success" :loading="confirming" @click="handleConfirm">
          <el-icon><Check /></el-icon>确认释放
        </el-button>
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

        <!-- 空状态 -->
        <el-empty v-if="artifacts.length === 0" description="暂无已上传的交付物" :image-size="80" />
      </el-card>
    </template>
  </div>
</template>

<style scoped>
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
}

.mono-id {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
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
</style>
