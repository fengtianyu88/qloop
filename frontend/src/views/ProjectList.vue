<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { getProjects, createProject } from '@/api/projects'
import { useAuthStore } from '@/stores/auth'
import type { Project, ProjectCreate } from '@/types'

const router = useRouter()
const authStore = useAuthStore()

const projectList = ref<Project[]>([])
const loading = ref(false)

// 创建项目对话框
const dialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive<ProjectCreate>({
  name: '',
  description: '',
})
const createRules: FormRules<ProjectCreate> = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}
const submitting = ref(false)

async function loadProjects() {
  loading.value = true
  try {
    const res = await getProjects()
    projectList.value = res
  } catch {
    // 错误已统一提示
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  createForm.name = ''
  createForm.description = ''
  dialogVisible.value = true
}

async function handleCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      await createProject({
        name: createForm.name,
        description: createForm.description || undefined,
      })
      ElMessage.success('项目创建成功')
      dialogVisible.value = false
      await loadProjects()
    } catch {
      // 错误已统一提示
    } finally {
      submitting.value = false
    }
  })
}

function goDetail(id: string) {
  router.push(`/projects/${id}`)
}

// ---- 列筛选：基于当前数据自动生成可选值 ----
const pmFilterOptions = computed(() => {
  const seen = new Map<string, string>()
  projectList.value.forEach((p) => {
    const label = p.pm_name || '—'
    if (!seen.has(label)) seen.set(label, label)
  })
  return Array.from(seen.values()).map((v) => ({ text: v, value: v }))
})

const statusFilterOptions = [
  { text: '活跃', value: 'active' },
  { text: '停用', value: 'inactive' },
]

function pmFilterHandler(value: string, row: Project) {
  return (row.pm_name || '—') === value
}

function statusFilterHandler(value: string, row: Project) {
  return (row.is_active ? 'active' : 'inactive') === value
}

function filterMethod(query: string, row: Project, column: { property: string }) {
  const prop = column.property
  if (!prop) return true
  const v = (row as any)[prop]
  if (v == null) return query === ''
  return String(v).toLowerCase().includes(String(query).toLowerCase())
}

// 排序比较器：支持字符串 / 时间 / 数字
function genericCompare(a: Project, b: Project, prop: string): number {
  const va = (a as any)[prop]
  const vb = (b as any)[prop]
  if (va == null && vb == null) return 0
  if (va == null) return -1
  if (vb == null) return 1
  // 时间戳
  if (typeof va === 'string' && typeof vb === 'string' &&
      /\d{4}-\d{2}-\d{2}T/.test(va) && /\d{4}-\d{2}-\d{2}T/.test(vb)) {
    return va.localeCompare(vb)
  }
  if (typeof va === 'number' && typeof vb === 'number') return va - vb
  return String(va).localeCompare(String(vb), 'zh-Hans-CN', { numeric: true })
}

onMounted(() => {
  loadProjects()
})
</script>

<template>
  <div class="page-container">
    <div class="list-header">
      <h2 class="page-title">项目管理</h2>
      <el-button
        v-if="authStore.isDeveloper"
        type="primary"
        @click="openCreateDialog"
      >
        <el-icon><Plus /></el-icon>创建项目
      </el-button>
    </div>

    <el-card class="table-card" shadow="never">
      <el-table
        :data="projectList"
        v-loading="loading"
        border
        stripe
        :default-sort="{ prop: 'created_at', order: 'descending' }"
      >
        <el-table-column
          prop="name"
          label="项目名称"
          min-width="180"
          show-overflow-tooltip
          sortable
          :filters="[]"
          :filter-method="(v: string, r: Project) => filterMethod(String(v), r, { property: 'name' })"
          filter-placement="bottom-end"
        >
          <template #header="{ column }">
            <div class="col-header">
              <span>项目名称</span>
              <el-input
                v-model="(column as any).filterValue"
                placeholder="筛选"
                size="small"
                clearable
                style="width: 100px; margin-left: 4px"
                @input="() => { if (!(column as any).filteredValue) (column as any).filteredValue = []; (column as any).filteredValue = [(column as any).filterValue || ''] }"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column
          prop="description"
          label="描述"
          min-width="220"
          show-overflow-tooltip
          sortable
        >
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column
          label="项目经理"
          width="160"
          sortable
          :filters="pmFilterOptions"
          :filter-method="pmFilterHandler"
          filter-placement="bottom-end"
        >
          <template #default="{ row }">
            <el-tooltip :content="row.pm_user_id" placement="top" :disabled="!row.pm_user_id">
              <span>{{ row.pm_name || '—' }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="成员数量" width="100" align="center" sortable :sort-method="(a: Project, b: Project) => (a.members?.length || 0) - (b.members?.length || 0)">
          <template #default="{ row }">{{ row.members?.length || 0 }}</template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="100"
          align="center"
          sortable
          :sort-method="(a: Project, b: Project) => Number(a.is_active) - Number(b.is_active)"
          :filters="statusFilterOptions"
          :filter-method="statusFilterHandler"
          filter-placement="bottom-end"
        >
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '活跃' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          label="项目创建时间"
          width="180"
          sortable
          :sort-method="(a: Project, b: Project) => genericCompare(a, b, 'created_at')"
        >
          <template #default="{ row }">{{ row.created_at?.replace('T', ' ').slice(0, 19) }}</template>
        </el-table-column>
        <el-table-column
          label="最新动态时间"
          width="180"
          sortable
          :sort-method="(a: Project, b: Project) => genericCompare(a, b, 'latest_activity_at')"
        >
          <template #default="{ row }">
            <span v-if="row.latest_activity_at">{{ row.latest_activity_at.replace('T', ' ').slice(0, 19) }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link @click="goDetail(row.id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建项目对话框 -->
    <el-dialog v-model="dialogVisible" title="创建项目" width="480px">
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-width="90px"
      >
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入项目名称" />
        </el-form-item>
        <el-form-item label="项目描述" prop="description">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="4"
            placeholder="请输入项目描述（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.list-header .page-title {
  margin: 0;
}

.col-header {
  display: inline-flex;
  align-items: center;
}
</style>
