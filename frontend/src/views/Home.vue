<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { searchProjects, searchReleases } from '@/api/search'
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
  try {
    const res = await getUsers({ page: 1, page_size: 100 })
    const map: Record<string, User> = {}
    res.items.forEach((u) => { map[u.id] = u })
    userMap.value = map
  } catch {
    // 非管理员无法获取用户列表，回退到 ID 显示
  }
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
      <el-radio-group v-model="viewMode" @change="handleViewChange">
        <el-radio-button value="release">释放视图</el-radio-button>
        <el-radio-button value="project">项目视图</el-radio-button>
      </el-radio-group>
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
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="table-card" shadow="never">
        <el-table :data="releaseList" v-loading="releaseLoading" border stripe>
          <el-table-column prop="project_name" label="项目名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="version_number" label="版本号" width="120" show-overflow-tooltip />
          <el-table-column prop="release_number" label="释放序号" width="90" align="center" />
          <el-table-column prop="developer_name" label="开发人员" width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ row.developer_name || '—' }}</template>
          </el-table-column>
          <el-table-column prop="change_notes" label="变更点" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.change_notes || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="130" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="170">
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
</style>
