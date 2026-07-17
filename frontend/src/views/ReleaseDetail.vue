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
} from '@/api/releases'
import { getReleaseReviews, triggerReview } from '@/api/reviews'
import { useAuthStore } from '@/stores/auth'
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

// 下载单个交付物（代码包/测试报告/评审报告）：
// 后端 GET /api/releases/{id}/download/{file_type} 会 302 重定向到 MinIO 预签名 URL
function downloadArtifact(fileType: 'code_package' | 'test_report' | 'review_report') {
  window.open(`/api/releases/${releaseId.value}/download/${fileType}`, '_blank')
}

function formatTime(t: string | null): string {
  if (!t) return '—'
  return t.replace('T', ' ').slice(0, 19)
}

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
            <span class="mono-id">{{ release.confirmed_by || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="确认时间">{{ formatTime(release.confirmed_at) }}</el-descriptions-item>
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

      <!-- 已释放下载 -->
      <el-card class="table-card" shadow="never" v-if="isReleased">
        <template #header><span>下载</span></template>
        <el-result icon="success" title="该释放已完成" sub-title="可下载相关交付物">
          <template #extra>
            <div class="download-links">
              <el-button v-if="release.download_link" type="primary" @click="openLink(release.download_link)">
                <el-icon><Download /></el-icon>下载交付包
              </el-button>
              <el-button v-if="release.code_package_path" @click="downloadArtifact('code_package')">
                代码包
              </el-button>
              <el-button v-if="release.test_report_path" @click="downloadArtifact('test_report')">
                测试报告
              </el-button>
              <el-button v-if="release.review_report_path" @click="downloadArtifact('review_report')">
                评审报告
              </el-button>
              <span v-if="release.link_expiry" class="expiry-text">
                链接有效期至：{{ formatTime(release.link_expiry) }}
              </span>
            </div>
          </template>
        </el-result>
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
