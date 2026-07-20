<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Download, Upload } from '@element-plus/icons-vue'
import { getProjects, createProject } from '@/api/projects'
import { downloadProjectsTemplate, importProjects } from '@/api/imports'
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

async function handleDownloadTemplate() {
  try {
    const blob = await downloadProjectsTemplate()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'projects_template.xlsx'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('下载模板失败')
  }
}

const importInputRef = ref<HTMLInputElement | null>(null)
function handleImportClick() {
  importInputRef.value?.click()
}
async function handleImportFile(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  const file = target.files[0]
  try {
    const res = await importProjects(file)
    ElMessage.success(`导入完成：成功 ${res.success} 个，失败 ${res.failed} 个`)
    if (res.errors.length > 0) {
      ElMessageBox.alert(res.errors.slice(0, 5).join('\n'), '失败详情', { type: 'warning' })
    }
    await loadProjects()  // 刷新列表
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    target.value = ''  // 清空,允许重复选择同一文件
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

// ============== 列筛选 + 排序 ==============
// 每列的筛选状态: { input: 自由文本, selected: 多选下拉 }
type ColFilter = { input: string; selected: string[] }
const colFilters = reactive<Record<string, ColFilter>>({
  name: { input: '', selected: [] },
  description: { input: '', selected: [] },
  pm_name: { input: '', selected: [] },
  member_count: { input: '', selected: [] },
  status: { input: '', selected: [] },
  created_at: { input: '', selected: [] },
  latest_activity_at: { input: '', selected: [] },
})

// 取列显示文本（用于生成筛选项 + 应用筛选）
function cellValue(row: Project, prop: string): string {
  switch (prop) {
    case 'pm_name':
      return row.pm_name || '—'
    case 'member_count':
      return String(row.members?.length || 0)
    case 'status':
      return row.is_active ? '活跃' : '停用'
    case 'created_at':
      return row.created_at?.replace('T', ' ').slice(0, 19) || '—'
    case 'latest_activity_at':
      return row.latest_activity_at?.replace('T', ' ').slice(0, 19) || '—'
    case 'description':
      return row.description || '—'
    default:
      return String((row as any)[prop] ?? '')
  }
}

// 每列可选项（来自当前数据去重）
function getOptions(prop: string): string[] {
  const set = new Set<string>()
  projectList.value.forEach((r) => set.add(cellValue(r, prop)))
  return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
}

// 应用筛选后的数据
const filteredRows = computed(() => {
  return projectList.value.filter((row) => {
    for (const prop of Object.keys(colFilters)) {
      const f = colFilters[prop]
      const v = cellValue(row, prop)
      // 自由文本：包含匹配
      if (f.input && !v.toLowerCase().includes(f.input.toLowerCase())) {
        return false
      }
      // 多选下拉：选中为空表示不过滤；否则必须命中
      if (f.selected.length > 0 && !f.selected.includes(v)) {
        return false
      }
    }
    return true
  })
})

function clearColFilter(prop: string) {
  colFilters[prop].input = ''
  colFilters[prop].selected = []
}

function clearAllFilters() {
  Object.keys(colFilters).forEach((k) => clearColFilter(k))
}

// 是否有任意列处于激活筛选状态（用于显示清除按钮）
const hasActiveFilter = computed(() =>
  Object.values(colFilters).some((f) => f.input || f.selected.length > 0),
)

// 排序比较器：支持字符串 / 时间 / 数字
function genericCompare(a: Project, b: Project, prop: string): number {
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
  loadProjects()
})
</script>

<template>
  <div class="page-container">
    <div class="list-header">
      <h2 class="page-title">项目管理</h2>
      <div class="list-header-actions">
        <el-button
          v-if="hasActiveFilter"
          type="info"
          size="small"
          @click="clearAllFilters"
        >
          <el-icon><Close /></el-icon>清除筛选
        </el-button>
        <el-button
          v-if="authStore.isDeveloper"
          type="primary"
          @click="openCreateDialog"
        >
          <el-icon><Plus /></el-icon>创建项目
        </el-button>
        <el-button size="default" @click="handleDownloadTemplate">
          <el-icon><Download /></el-icon>下载模板
        </el-button>
        <el-button size="default" @click="handleImportClick">
          <el-icon><Upload /></el-icon>批量导入
        </el-button>
        <input ref="importInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleImportFile" />
      </div>
    </div>

    <el-card class="table-card" shadow="never">
      <el-table
        :data="filteredRows"
        v-loading="loading"
        border
        stripe
        :default-sort="{ prop: 'created_at', order: 'descending' }"
      >
        <!-- 项目名称 -->
        <el-table-column
          prop="name"
          label="项目名称"
          min-width="200"
          show-overflow-tooltip
          sortable
        >
          <template #header>
            <div class="col-with-filter">
              <span>项目名称</span>
              <el-popover trigger="click" placement="bottom" :width="240">
                <template #reference>
                  <el-button class="filter-icon-btn" link @click.stop>
                    <el-icon class="filter-icon" :class="{ active: colFilters.name.input || colFilters.name.selected.length }">
                      <Filter />
                    </el-icon>
                  </el-button>
                </template>
                <div class="filter-pop">
                  <el-input
                    v-model="colFilters.name.input"
                    placeholder="搜索（自由输入）"
                    size="small"
                    clearable
                  />
                  <el-divider class="filter-divider" />
                  <div class="filter-options">
                    <el-checkbox-group v-model="colFilters.name.selected">
                      <el-checkbox
                        v-for="opt in getOptions('name')"
                        :key="opt"
                        :label="opt"
                        :value="opt"
                      >
                        {{ opt }}
                      </el-checkbox>
                    </el-checkbox-group>
                  </div>
                  <div class="filter-actions">
                    <el-button size="small" @click="clearColFilter('name')">清空</el-button>
                  </div>
                </div>
              </el-popover>
            </div>
          </template>
        </el-table-column>

        <!-- 描述 -->
        <el-table-column
          prop="description"
          label="描述"
          min-width="220"
          show-overflow-tooltip
          sortable
          :sort-method="(a: Project, b: Project) => genericCompare(a, b, 'description')"
        >
          <template #header>
            <div class="col-with-filter">
              <span>描述</span>
              <el-popover trigger="click" placement="bottom" :width="240">
                <template #reference>
                  <el-button class="filter-icon-btn" link @click.stop>
                    <el-icon class="filter-icon" :class="{ active: colFilters.description.input || colFilters.description.selected.length }">
                      <Filter />
                    </el-icon>
                  </el-button>
                </template>
                <div class="filter-pop">
                  <el-input v-model="colFilters.description.input" placeholder="搜索（自由输入）" size="small" clearable />
                  <el-divider class="filter-divider" />
                  <div class="filter-options">
                    <el-checkbox-group v-model="colFilters.description.selected">
                      <el-checkbox
                        v-for="opt in getOptions('description')"
                        :key="opt"
                        :label="opt"
                        :value="opt"
                      >
                        {{ opt }}
                      </el-checkbox>
                    </el-checkbox-group>
                  </div>
                  <div class="filter-actions">
                    <el-button size="small" @click="clearColFilter('description')">清空</el-button>
                  </div>
                </div>
              </el-popover>
            </div>
          </template>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>

        <!-- 项目经理 -->
        <el-table-column
          label="项目经理"
          width="180"
          sortable
          :sort-method="(a: Project, b: Project) => String(a.pm_name || '').localeCompare(String(b.pm_name || ''))"
        >
          <template #header>
            <div class="col-with-filter">
              <span>项目经理</span>
              <el-popover trigger="click" placement="bottom" :width="240">
                <template #reference>
                  <el-button class="filter-icon-btn" link @click.stop>
                    <el-icon class="filter-icon" :class="{ active: colFilters.pm_name.input || colFilters.pm_name.selected.length }">
                      <Filter />
                    </el-icon>
                  </el-button>
                </template>
                <div class="filter-pop">
                  <el-input v-model="colFilters.pm_name.input" placeholder="搜索（自由输入）" size="small" clearable />
                  <el-divider class="filter-divider" />
                  <div class="filter-options">
                    <el-checkbox-group v-model="colFilters.pm_name.selected">
                      <el-checkbox
                        v-for="opt in getOptions('pm_name')"
                        :key="opt"
                        :label="opt"
                        :value="opt"
                      >
                        {{ opt }}
                      </el-checkbox>
                    </el-checkbox-group>
                  </div>
                  <div class="filter-actions">
                    <el-button size="small" @click="clearColFilter('pm_name')">清空</el-button>
                  </div>
                </div>
              </el-popover>
            </div>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="row.pm_user_id" placement="top" :disabled="!row.pm_user_id">
              <span>{{ row.pm_name || '—' }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 成员数量 -->
        <el-table-column
          label="成员数量"
          width="130"
          align="center"
          sortable
          :sort-method="(a: Project, b: Project) => (a.members?.length || 0) - (b.members?.length || 0)"
        >
          <template #header>
            <div class="col-with-filter">
              <span>成员数量</span>
              <el-popover trigger="click" placement="bottom" :width="200">
                <template #reference>
                  <el-button class="filter-icon-btn" link @click.stop>
                    <el-icon class="filter-icon" :class="{ active: colFilters.member_count.input || colFilters.member_count.selected.length }">
                      <Filter />
                    </el-icon>
                  </el-button>
                </template>
                <div class="filter-pop">
                  <el-input v-model="colFilters.member_count.input" placeholder="搜索（自由输入）" size="small" clearable />
                  <el-divider class="filter-divider" />
                  <div class="filter-options">
                    <el-checkbox-group v-model="colFilters.member_count.selected">
                      <el-checkbox
                        v-for="opt in getOptions('member_count')"
                        :key="opt"
                        :label="opt"
                        :value="opt"
                      >
                        {{ opt }}
                      </el-checkbox>
                    </el-checkbox-group>
                  </div>
                  <div class="filter-actions">
                    <el-button size="small" @click="clearColFilter('member_count')">清空</el-button>
                  </div>
                </div>
              </el-popover>
            </div>
          </template>
          <template #default="{ row }">{{ row.members?.length || 0 }}</template>
        </el-table-column>

        <!-- 状态 -->
        <el-table-column
          label="状态"
          width="130"
          align="center"
          sortable
          :sort-method="(a: Project, b: Project) => Number(a.is_active) - Number(b.is_active)"
        >
          <template #header>
            <div class="col-with-filter">
              <span>状态</span>
              <el-popover trigger="click" placement="bottom" :width="180">
                <template #reference>
                  <el-button class="filter-icon-btn" link @click.stop>
                    <el-icon class="filter-icon" :class="{ active: colFilters.status.input || colFilters.status.selected.length }">
                      <Filter />
                    </el-icon>
                  </el-button>
                </template>
                <div class="filter-pop">
                  <el-input v-model="colFilters.status.input" placeholder="搜索（自由输入）" size="small" clearable />
                  <el-divider class="filter-divider" />
                  <div class="filter-options">
                    <el-checkbox-group v-model="colFilters.status.selected">
                      <el-checkbox
                        v-for="opt in getOptions('status')"
                        :key="opt"
                        :label="opt"
                        :value="opt"
                      >
                        {{ opt }}
                      </el-checkbox>
                    </el-checkbox-group>
                  </div>
                  <div class="filter-actions">
                    <el-button size="small" @click="clearColFilter('status')">清空</el-button>
                  </div>
                </div>
              </el-popover>
            </div>
          </template>
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '活跃' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 项目创建时间 -->
        <el-table-column
          prop="created_at"
          label="项目创建时间"
          width="200"
          sortable
          :sort-method="(a: Project, b: Project) => genericCompare(a, b, 'created_at')"
        >
          <template #header>
            <div class="col-with-filter">
              <span>项目创建时间</span>
              <el-popover trigger="click" placement="bottom" :width="240">
                <template #reference>
                  <el-button class="filter-icon-btn" link @click.stop>
                    <el-icon class="filter-icon" :class="{ active: colFilters.created_at.input || colFilters.created_at.selected.length }">
                      <Filter />
                    </el-icon>
                  </el-button>
                </template>
                <div class="filter-pop">
                  <el-input v-model="colFilters.created_at.input" placeholder="搜索（自由输入）" size="small" clearable />
                  <el-divider class="filter-divider" />
                  <div class="filter-options">
                    <el-checkbox-group v-model="colFilters.created_at.selected">
                      <el-checkbox
                        v-for="opt in getOptions('created_at')"
                        :key="opt"
                        :label="opt"
                        :value="opt"
                      >
                        {{ opt }}
                      </el-checkbox>
                    </el-checkbox-group>
                  </div>
                  <div class="filter-actions">
                    <el-button size="small" @click="clearColFilter('created_at')">清空</el-button>
                  </div>
                </div>
              </el-popover>
            </div>
          </template>
          <template #default="{ row }">{{ row.created_at?.replace('T', ' ').slice(0, 19) }}</template>
        </el-table-column>

        <!-- 最新动态时间 -->
        <el-table-column
          label="最新动态时间"
          width="200"
          sortable
          :sort-method="(a: Project, b: Project) => genericCompare(a, b, 'latest_activity_at')"
        >
          <template #header>
            <div class="col-with-filter">
              <span>最新动态时间</span>
              <el-popover trigger="click" placement="bottom" :width="240">
                <template #reference>
                  <el-button class="filter-icon-btn" link @click.stop>
                    <el-icon class="filter-icon" :class="{ active: colFilters.latest_activity_at.input || colFilters.latest_activity_at.selected.length }">
                      <Filter />
                    </el-icon>
                  </el-button>
                </template>
                <div class="filter-pop">
                  <el-input v-model="colFilters.latest_activity_at.input" placeholder="搜索（自由输入）" size="small" clearable />
                  <el-divider class="filter-divider" />
                  <div class="filter-options">
                    <el-checkbox-group v-model="colFilters.latest_activity_at.selected">
                      <el-checkbox
                        v-for="opt in getOptions('latest_activity_at')"
                        :key="opt"
                        :label="opt"
                        :value="opt"
                      >
                        {{ opt }}
                      </el-checkbox>
                    </el-checkbox-group>
                  </div>
                  <div class="filter-actions">
                    <el-button size="small" @click="clearColFilter('latest_activity_at')">清空</el-button>
                  </div>
                </div>
              </el-popover>
            </div>
          </template>
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

.list-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
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
