<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { searchProjects, searchReleases, exportAll } from '@/api/search'
import { getUsers } from '@/api/users'
import {
  statusLabel,
  statusTagType,
} from '@/utils/status'
import type {
  Project,
  ReleaseListItem,
  ReleaseSearchParams,
  ReleaseStatus,
  User,
} from '@/types'

const router = useRouter()
const authStore = useAuthStore()

// 用户字典：用于将 pm_user_id 解析为用户名
const userMap = ref<Record<string, User>>({})

// 视图切换：release / project
const viewMode = ref<'release' | 'project'>('release')

// 释放视图
const releaseFilters = reactive<{
  developer_name: string
  project_name: string
  version_number: string
  change_notes: string
  status: ReleaseStatus | ''
}>({
  developer_name: '',
  project_name: '',
  version_number: '',
  change_notes: '',
  status: '',
})

const releaseList = ref<ReleaseListItem[]>([])
const releaseTotal = ref(0)
const releasePage = ref(1)
const releasePageSize = ref(10)
const releaseLoading = ref(false)

// 项目视图
const projectFilters = reactive<{ name: string }>({ name: '' })
const projectList = ref<Project[]>([])
const projectTotal = ref(0)
const projectPage = ref(1)
const projectPageSize = ref(10)
const projectLoading = ref(false)

// 状态选项
const statusOptions: { label: string; value: ReleaseStatus }[] = [
  { label: '草稿', value: 'draft' },
  { label: '代码待评审', value: 'code_pending_review' },
  { label: '测试报告待评审', value: 'test_pending_review' },
  { label: '专家报告待评审', value: 'expert_pending_review' },
  { label: '待 PM 确认', value: 'pending_confirm' },
  { label: '已释放', value: 'released' },
  { label: '评审未通过', value: 'review_failed' },
]

async function loadReleases() {
  releaseLoading.value = true
  try {
    const params: ReleaseSearchParams = {
      page: releasePage.value,
      page_size: releasePageSize.value,
    }
    if (releaseFilters.developer_name) params.developer_name = releaseFilters.developer_name
    if (releaseFilters.project_name) params.project_name = releaseFilters.project_name
    if (releaseFilters.version_number) params.version_number = releaseFilters.version_number
    if (releaseFilters.change_notes) params.change_notes = releaseFilters.change_notes
    if (releaseFilters.status) params.status = releaseFilters.status
    const res = await searchReleases(params)
    releaseList.value = res.items
    releaseTotal.value = res.total
  } catch {
    // 错误已统一提示
  } finally {
    releaseLoading.value = false
  }
}

async function loadProjects() {
  projectLoading.value = true
  try {
    const res = await searchProjects({
      page: projectPage.value,
      page_size: projectPageSize.value,
      name: projectFilters.name || undefined,
    })
    projectList.value = res.items
    projectTotal.value = res.total
  } catch {
    // 错误已统一提示
  } finally {
    projectLoading.value = false
  }
}

function handleReleaseSearch() {
  releasePage.value = 1
  loadReleases()
}

function handleReleaseReset() {
  releaseFilters.developer_name = ''
  releaseFilters.project_name = ''
  releaseFilters.version_number = ''
  releaseFilters.change_notes = ''
  releaseFilters.status = ''
  releasePage.value = 1
  loadReleases()
}

function handleProjectSearch() {
  projectPage.value = 1
  loadProjects()
}

function handleProjectReset() {
  projectFilters.name = ''
  projectPage.value = 1
  loadProjects()
}

function handleReleasePageChange(page: number) {
  releasePage.value = page
  loadReleases()
}

function handleReleaseSizeChange(size: number) {
  releasePageSize.value = size
  releasePage.value = 1
  loadReleases()
}

function handleProjectPageChange(page: number) {
  projectPage.value = page
  loadProjects()
}

function handleProjectSizeChange(size: number) {
  projectPageSize.value = size
  projectPage.value = 1
  loadProjects()
}

function goReleaseDetail(id: string) {
  router.push(`/releases/${id}`)
}

function goProjectDetail(id: string) {
  router.push(`/projects/${id}`)
}

function handleViewChange() {
  if (viewMode.value === 'release') {
    loadReleases()
  } else {
    loadProjects()
  }
}

// 解析用户名为空时回退到 ID 前 8 位
function userName(id: string | null | undefined): string {
  if (!id) return '—'
  return userMap.value[id]?.full_name || userMap.value[id]?.username || id.slice(0, 8) + '…'
}

async function loadUsers() {
  // 仅 ADMIN+ 角色才能调用 /api/users；其他角色直接使用空映射
  if (!authStore.isAdmin) {
    return
  }
  try {
    const res = await getUsers({ page: 1, page_size: 100 })
    const map: Record<string, User> = {}
    res.items.forEach((u) => { map[u.id] = u })
    userMap.value = map
  } catch {
    // 非管理员无法获取用户列表，回退到 ID 显示
  }
}

// 导出所有：调用 /api/search/export，下载 CSV
const exporting = ref(false)
async function handleExportAll() {
  exporting.value = true
  try {
    const blob = await exportAll()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `qloop_export_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    // 错误已统一提示
  } finally {
    exporting.value = false
  }
}

// ============== 释放视图表格: 列筛选 + 排序 ==============
// 列显示文本提取（用 row 的字段或派生值）
function releaseCellValue(row: ReleaseListItem, prop: string): string {
  switch (prop) {
    case 'project_name':
      return row.project_name || '—'
    case 'version_number':
      return row.version_number || '—'
    case 'release_number':
      return String(row.release_number ?? '—')
    case 'pm_name':
      // 项目经理：通过 userMap 解析（PM 信息在 release 中没有直接字段，使用 userMap 兜底）
      // 注意：ReleaseListItem 没有 pm_user_id 字段，这里返回 — 占位；实际数据通过列表筛选
      return '—'
    case 'developer_name':
      return row.developer_name || '—'
    case 'tester_name':
      return row.tester_name || '—'
    case 'expert_name':
      return row.expert_name || '—'
    case 'change_notes':
      return row.change_notes || '—'
    case 'status':
      return statusLabel(row.status)
    case 'created_at':
      return row.created_at?.replace('T', ' ').slice(0, 19) || '—'
    default:
      return String((row as any)[prop] ?? '')
  }
}

type ColFilter = { input: string; selected: string[] }
const releaseColFilters = reactive<Record<string, ColFilter>>({
  project_name: { input: '', selected: [] },
  version_number: { input: '', selected: [] },
  release_number: { input: '', selected: [] },
  pm_name: { input: '', selected: [] },
  developer_name: { input: '', selected: [] },
  tester_name: { input: '', selected: [] },
  expert_name: { input: '', selected: [] },
  change_notes: { input: '', selected: [] },
  status: { input: '', selected: [] },
  created_at: { input: '', selected: [] },
})

function getReleaseOptions(prop: string): string[] {
  const set = new Set<string>()
  releaseList.value.forEach((r) => set.add(releaseCellValue(r, prop)))
  return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
}

const filteredReleaseRows = computed(() => {
  return releaseList.value.filter((row) => {
    for (const prop of Object.keys(releaseColFilters)) {
      const f = releaseColFilters[prop]
      const v = releaseCellValue(row, prop)
      if (f.input && !v.toLowerCase().includes(f.input.toLowerCase())) return false
      if (f.selected.length > 0 && !f.selected.includes(v)) return false
    }
    return true
  })
})

function clearReleaseFilter(prop: string) {
  releaseColFilters[prop].input = ''
  releaseColFilters[prop].selected = []
}
function clearAllReleaseFilters() {
  Object.keys(releaseColFilters).forEach((k) => clearReleaseFilter(k))
}
const releaseHasActiveFilter = computed(() =>
  Object.values(releaseColFilters).some((f) => f.input || f.selected.length > 0),
)

function releaseGenericCompare(a: ReleaseListItem, b: ReleaseListItem, prop: string): number {
  const va = (a as any)[prop]
  const vb = (b as any)[prop]
  if (va == null && vb == null) return 0
  if (va == null) return -1
  if (vb == null) return 1
  if (typeof va === 'string' && typeof vb === 'string' &&
      /\d{4}-\d{2}-\d{2}T/.test(va) && /\d{4}-\d{2}-\d{2}T/.test(vb)) {
    return va.localeCompare(vb)
  }
  if (typeof va === 'number' && typeof vb === 'number') return va - vb
  return String(va).localeCompare(String(vb), 'zh-Hans-CN', { numeric: true })
}

onMounted(() => {
  loadReleases()
  loadUsers()
})
</script>

<template>
  <div class="page-container">
    <div class="home-header">
      <h2 class="page-title">首页</h2>
      <div class="home-header-actions">
        <el-radio-group v-model="viewMode" @change="handleViewChange">
          <el-radio-button value="release">释放视图</el-radio-button>
          <el-radio-button value="project">项目视图</el-radio-button>
        </el-radio-group>
        <el-button
          type="success"
          :loading="exporting"
          @click="handleExportAll"
        >
          <el-icon v-if="!exporting"><Download /></el-icon>
          导出所有
        </el-button>
      </div>
    </div>

    <!-- 释放视图 -->
    <template v-if="viewMode === 'release'">
      <el-card class="filter-card" shadow="never">
        <el-form :inline="true" label-width="80px">
          <el-form-item label="开发人员">
            <el-input v-model="releaseFilters.developer_name" placeholder="开发人员" clearable />
          </el-form-item>
          <el-form-item label="项目名称">
            <el-input v-model="releaseFilters.project_name" placeholder="项目名称" clearable />
          </el-form-item>
          <el-form-item label="版本号">
            <el-input v-model="releaseFilters.version_number" placeholder="版本号" clearable />
          </el-form-item>
          <el-form-item label="变更点">
            <el-input v-model="releaseFilters.change_notes" placeholder="变更点" clearable />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="releaseFilters.status" placeholder="全部状态" clearable style="width: 160px">
              <el-option
                v-for="opt in statusOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleReleaseSearch">查询</el-button>
            <el-button @click="handleReleaseReset">重置</el-button>
            <el-button
              v-if="releaseHasActiveFilter"
              type="info"
              size="small"
              @click="clearAllReleaseFilters"
            >清除列筛选</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="table-card" shadow="never">
        <el-table :data="filteredReleaseRows" v-loading="releaseLoading" border stripe>
          <!-- 项目名称 -->
          <el-table-column prop="project_name" label="项目名称" min-width="160" show-overflow-tooltip sortable>
            <template #header>
              <div class="col-with-filter">
                <span>项目名称</span>
                <el-popover trigger="click" placement="bottom" :width="220">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.project_name.input || releaseColFilters.project_name.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.project_name.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.project_name.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('project_name')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('project_name')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">{{ row.project_name || '—' }}</template>
          </el-table-column>

          <!-- 版本号 -->
          <el-table-column prop="version_number" label="版本号" width="140" show-overflow-tooltip sortable>
            <template #header>
              <div class="col-with-filter">
                <span>版本号</span>
                <el-popover trigger="click" placement="bottom" :width="220">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.version_number.input || releaseColFilters.version_number.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.version_number.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.version_number.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('version_number')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('version_number')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">{{ row.version_number || '—' }}</template>
          </el-table-column>

          <!-- 释放序号 -->
          <el-table-column prop="release_number" label="释放序号" width="110" align="center" sortable>
            <template #header>
              <div class="col-with-filter">
                <span>释放序号</span>
                <el-popover trigger="click" placement="bottom" :width="200">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.release_number.input || releaseColFilters.release_number.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.release_number.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.release_number.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('release_number')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('release_number')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
          </el-table-column>

          <!-- 项目经理（开发人员左边新增） -->
          <el-table-column label="项目经理" width="120" show-overflow-tooltip sortable
            :sort-method="(a: ReleaseListItem, b: ReleaseListItem) => String(a.project_name || '').localeCompare(String(b.project_name || ''))">
            <template #header>
              <div class="col-with-filter">
                <span>项目经理</span>
                <el-popover trigger="click" placement="bottom" :width="200">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.pm_name.input || releaseColFilters.pm_name.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.pm_name.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.pm_name.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('pm_name')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('pm_name')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">—</template>
          </el-table-column>

          <!-- 开发人员 -->
          <el-table-column prop="developer_name" label="开发人员" width="120" show-overflow-tooltip sortable>
            <template #header>
              <div class="col-with-filter">
                <span>开发人员</span>
                <el-popover trigger="click" placement="bottom" :width="220">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.developer_name.input || releaseColFilters.developer_name.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.developer_name.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.developer_name.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('developer_name')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('developer_name')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">{{ row.developer_name || '—' }}</template>
          </el-table-column>

          <!-- 测试人员（开发人员右边新增） -->
          <el-table-column prop="tester_name" label="测试人员" width="120" show-overflow-tooltip sortable>
            <template #header>
              <div class="col-with-filter">
                <span>测试人员</span>
                <el-popover trigger="click" placement="bottom" :width="220">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.tester_name.input || releaseColFilters.tester_name.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.tester_name.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.tester_name.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('tester_name')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('tester_name')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">{{ row.tester_name || '—' }}</template>
          </el-table-column>

          <!-- 审核专家（测试人员右边新增） -->
          <el-table-column prop="expert_name" label="审核专家" width="120" show-overflow-tooltip sortable>
            <template #header>
              <div class="col-with-filter">
                <span>审核专家</span>
                <el-popover trigger="click" placement="bottom" :width="220">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.expert_name.input || releaseColFilters.expert_name.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.expert_name.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.expert_name.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('expert_name')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('expert_name')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">{{ row.expert_name || '—' }}</template>
          </el-table-column>

          <!-- 变更点 -->
          <el-table-column prop="change_notes" label="变更点" min-width="180" show-overflow-tooltip sortable
            :sort-method="(a: ReleaseListItem, b: ReleaseListItem) => releaseGenericCompare(a, b, 'change_notes')">
            <template #header>
              <div class="col-with-filter">
                <span>变更点</span>
                <el-popover trigger="click" placement="bottom" :width="220">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.change_notes.input || releaseColFilters.change_notes.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.change_notes.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.change_notes.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('change_notes')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('change_notes')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">{{ row.change_notes || '—' }}</template>
          </el-table-column>

          <!-- 状态 -->
          <el-table-column prop="status" label="状态" width="140" align="center" sortable
            :sort-method="(a: ReleaseListItem, b: ReleaseListItem) => String(a.status).localeCompare(String(b.status))">
            <template #header>
              <div class="col-with-filter">
                <span>状态</span>
                <el-popover trigger="click" placement="bottom" :width="200">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.status.input || releaseColFilters.status.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.status.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.status.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('status')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('status')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>

          <!-- 创建时间 -->
          <el-table-column prop="created_at" label="创建时间" width="180" sortable
            :sort-method="(a: ReleaseListItem, b: ReleaseListItem) => releaseGenericCompare(a, b, 'created_at')">
            <template #header>
              <div class="col-with-filter">
                <span>创建时间</span>
                <el-popover trigger="click" placement="bottom" :width="220">
                  <template #reference>
                    <el-button class="filter-icon-btn" link @click.stop>
                      <el-icon class="filter-icon" :class="{ active: releaseColFilters.created_at.input || releaseColFilters.created_at.selected.length }"><Filter /></el-icon>
                    </el-button>
                  </template>
                  <div class="filter-pop">
                    <el-input v-model="releaseColFilters.created_at.input" placeholder="搜索（自由输入）" size="small" clearable />
                    <el-divider class="filter-divider" />
                    <div class="filter-options">
                      <el-checkbox-group v-model="releaseColFilters.created_at.selected">
                        <el-checkbox v-for="opt in getReleaseOptions('created_at')" :key="opt" :label="opt" :value="opt">{{ opt }}</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div class="filter-actions"><el-button size="small" @click="clearReleaseFilter('created_at')">清空</el-button></div>
                  </div>
                </el-popover>
              </div>
            </template>
            <template #default="{ row }">{{ row.created_at?.replace('T', ' ').slice(0, 19) }}</template>
          </el-table-column>

          <el-table-column label="操作" width="100" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="primary" link @click="goReleaseDetail(row.id)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="releasePage"
            v-model:page-size="releasePageSize"
            :total="releaseTotal"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handleReleasePageChange"
            @size-change="handleReleaseSizeChange"
          />
        </div>
      </el-card>
    </template>

    <!-- 项目视图 -->
    <template v-else>
      <el-card class="filter-card" shadow="never">
        <el-form :inline="true" label-width="80px">
          <el-form-item label="项目名称">
            <el-input v-model="projectFilters.name" placeholder="项目名称" clearable />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleProjectSearch">查询</el-button>
            <el-button @click="handleProjectReset">重置</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="table-card" shadow="never">
        <el-table :data="projectList" v-loading="projectLoading" border stripe>
          <el-table-column prop="name" label="项目名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.description || '—' }}</template>
          </el-table-column>
          <el-table-column label="项目经理" width="160">
            <template #default="{ row }">
              <el-tooltip :content="row.pm_user_id" placement="top" :disabled="!row.pm_user_id">
                <span>{{ userName(row.pm_user_id) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="版本数量" width="100" align="center">
            <template #default>—</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="170">
            <template #default="{ row }">{{ row.created_at?.replace('T', ' ').slice(0, 19) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="primary" link @click="goProjectDetail(row.id)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="projectPage"
            v-model:page-size="projectPageSize"
            :total="projectTotal"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handleProjectPageChange"
            @size-change="handleProjectSizeChange"
          />
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.home-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.home-header .page-title {
  margin: 0;
}

.home-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.col-with-filter {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.filter-icon-btn {
  padding: 0;
  margin: 0;
  min-height: 0;
  height: auto;
}

.filter-icon {
  font-size: 14px;
  color: #909399;
  cursor: pointer;
  transition: color 0.2s;
}

.filter-icon:hover {
  color: #409eff;
}

.filter-icon.active {
  color: #409eff;
}

.filter-pop {
  max-height: 360px;
  overflow-y: auto;
}

.filter-divider {
  margin: 8px 0;
}

.filter-options {
  max-height: 200px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-options :deep(.el-checkbox) {
  margin-right: 0;
  height: auto;
  min-height: 24px;
}

.filter-actions {
  text-align: right;
  margin-top: 8px;
}
</style>
