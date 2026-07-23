<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { getProject, addMember, updateMember, deleteMember, createVersion } from '@/api/projects'
import { getReleasesByVersion } from '@/api/releases'
import request from '@/api/request'
import { getUsers } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import { roleLabel } from '@/utils/status'
import type {
  Project,
  ProjectMember,
  ProjectMemberCreate,
  ProjectMemberUpdate,
  ProjectRole,
  User,
  Version,
  VersionCreate,
} from '@/types'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const projectId = computed(() => route.params.id as string)
const project = ref<Project | null>(null)
const loading = ref(false)
// 加载失败错误态
const loadError = ref(false)

// 用户字典（仅 admin 可获取完整用户列表用于姓名解析与选择）
const userMap = ref<Record<string, User>>({})
const userList = ref<User[]>([])

// 版本列表（含每个版本最新 release 状态，用于判断是否可删除）
interface VersionWithStatus extends Version {
  latest_release_status?: string | null
}
const versions = ref<VersionWithStatus[]>([])

// 功能1: 项目概览统计数据(版本数、待评审、待释放、已释放、阻塞中)
interface ProjectDashboard {
  total: number
  draft: number
  in_review: number
  pending_confirm: number
  released: number
  failed: number
}
const stats = ref<ProjectDashboard>({ total: 0, draft: 0, in_review: 0, pending_confirm: 0, released: 0, failed: 0 })

async function loadDashboard() {
  try {
    const data = await request.get(`/projects/${projectId.value}/dashboard`)
    stats.value = data as unknown as ProjectDashboard
  } catch {
    // 概览加载失败不影响主流程,保持默认 0 值
  }
}

// 是否为当前项目的 PM
const isPm = computed(
  () => project.value?.pm_user_id === authStore.user?.id || authStore.isAdmin,
)

async function viewRelease(versionId: string) {
  try {
    const releases = await getReleasesByVersion(versionId)
    if (releases && releases.length > 0) {
      router.push(`/releases/${releases[0].id}`)
    } else {
      ElMessage.warning('该版本暂无释放记录')
    }
  } catch {
    ElMessage.error('获取释放列表失败')
  }
}

async function handleDeleteVersion(row: VersionWithStatus) {
  // 已释放的版本不允许删除
  if (row.latest_release_status === 'released') {
    ElMessage.warning('该版本已释放，不可删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定要删除版本「${row.version_number}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return  // 用户取消
  }
  try {
    await request.delete(`/projects/${projectId.value}/versions/${row.id}`)
    ElMessage.success('版本已删除')
    await loadVersions()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '删除失败'
    ElMessage.error(msg)
  }
}

function userName(id: string | null | undefined): string {
  if (!id) return '—'
  return userMap.value[id]?.full_name || id.slice(0, 8) + '…'
}

async function loadProject() {
  loading.value = true
  loadError.value = false
  try {
    project.value = await getProject(projectId.value)
  } catch {
    loadError.value = true
    // 错误已统一提示
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  // 仅 admin / super_admin 可获取用户列表；其他角色直接使用空列表，userOptions 会降级到项目成员
  if (!authStore.isAdmin) {
    userList.value = []
    return
  }
  try {
    const res = await getUsers({ page: 1, page_size: 100 })
    userList.value = res.items
    const map: Record<string, User> = {}
    res.items.forEach((u) => {
      map[u.id] = u
    })
    userMap.value = map
  } catch {
    userList.value = []
  }
}

async function loadVersions() {
  try {
    const data = await request.get(`/projects/${projectId.value}/versions`)
    versions.value = (data || []) as unknown as VersionWithStatus[]
  } catch {
    versions.value = []
  }
}

// 用户选择器选项：优先使用完整用户列表，否则使用项目成员
const userOptions = computed(() => {
  if (userList.value.length > 0) {
    return userList.value.map((u) => ({ label: `${u.full_name} (${u.username})`, value: u.id }))
  }
  return (project.value?.members || []).map((m) => ({
    label: m.user_id.slice(0, 8) + '…',
    value: m.user_id,
  }))
})

// ------------------------- 添加成员 -------------------------
const memberDialogVisible = ref(false)
const memberFormRef = ref<FormInstance>()
const memberForm = reactive<ProjectMemberCreate>({
  user_id: '',
  project_role: 'developer',
})
const memberRules: FormRules<ProjectMemberCreate> = {
  user_id: [{ required: true, message: '请选择用户', trigger: 'change' }],
}
const roleOptions: { label: string; value: ProjectRole }[] = [
  { label: '项目经理', value: 'project_manager' },
  { label: '开发人员', value: 'developer' },
  { label: '测试人员', value: 'tester' },
  { label: '外部专家', value: 'external_expert' },
]
const memberSubmitting = ref(false)

function openMemberDialog() {
  memberForm.user_id = ''
  memberForm.project_role = 'developer'
  memberDialogVisible.value = true
}

async function handleAddMember() {
  if (!memberFormRef.value) return
  await memberFormRef.value.validate(async (valid) => {
    if (!valid) return
    memberSubmitting.value = true
    try {
      await addMember(projectId.value, { ...memberForm })
      ElMessage.success('成员添加成功')
      memberDialogVisible.value = false
      await loadProject()
    } catch {
      // 错误已统一提示
    } finally {
      memberSubmitting.value = false
    }
  })
}

// ------------------------- 编辑/删除成员 -------------------------
const editDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive<{ id: string; user_id: string; project_role: ProjectRole }>({
  id: '',
  user_id: '',
  project_role: 'developer',
})
const editRules: FormRules<{ project_role: ProjectRole }> = {
  project_role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}
const editSubmitting = ref(false)
// 记录正在编辑的成员及其原始角色(用于角色变更二次确认)
const editingMember = ref<(ProjectMember & { originalRole: ProjectRole }) | null>(null)

/** 当前用户是否可对该成员行执行编辑/删除操作。 */
function canMutateMember(row: ProjectMember): boolean {
  if (!project.value) return false
  // 仅 PM（含 admin）可见按钮
  if (!isPm.value) return false
  // PM 不可改 PM 行，admin/super_admin 可改任意行
  if (row.user_id === project.value.pm_user_id && !authStore.isAdmin) {
    return false
  }
  return true
}

function openEditDialog(row: ProjectMember) {
  editForm.id = row.id
  editForm.user_id = row.user_id
  editForm.project_role = row.project_role
  // 记录原始角色,用于在保存时检测是否发生变更
  editingMember.value = { ...row, originalRole: row.project_role }
  editDialogVisible.value = true
}

async function handleEditMember() {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    // 角色变更二次确认:避免误操作导致权限变化
    if (editingMember.value && editingMember.value.originalRole !== editForm.project_role) {
      try {
        if (editForm.project_role === 'project_manager') {
          // 项目经理角色变更二次确认:会影响项目权限分配
          await ElMessageBox.confirm(
            '确认将该成员设为项目经理？此操作会影响项目权限分配。',
            '角色变更确认',
            { type: 'warning', confirmButtonText: '确认变更', cancelButtonText: '取消' },
          )
        } else {
          await ElMessageBox.confirm(
            `确认将成员角色从「${roleLabel(editingMember.value.originalRole)}」改为「${roleLabel(editForm.project_role)}」吗?\n\n角色变更会影响该成员的权限,请确认操作。`,
            '角色变更确认',
            { type: 'warning', confirmButtonText: '确认变更', cancelButtonText: '取消' },
          )
        }
      } catch {
        return  // 用户取消,不执行保存
      }
    }
    editSubmitting.value = true
    try {
      const payload: ProjectMemberUpdate = { project_role: editForm.project_role }
      await updateMember(projectId.value, editForm.id, payload)
      ElMessage.success('角色已更新')
      editDialogVisible.value = false
      await loadProject()
    } catch {
      // 错误已统一提示
    } finally {
      editSubmitting.value = false
    }
  })
}

async function handleDeleteMember(row: ProjectMember) {
  try {
    await ElMessageBox.confirm(
      `确认从项目中移除成员「${userName(row.user_id)}」？`,
      '移除成员',
      {
        confirmButtonText: '确定移除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return // 用户取消
  }
  try {
    await deleteMember(projectId.value, row.id)
    ElMessage.success('成员已移除')
    await loadProject()
  } catch {
    // 错误已统一提示
  }
}

// ------------------------- 创建版本 -------------------------
const versionDialogVisible = ref(false)
const versionFormRef = ref<FormInstance>()
const versionForm = reactive<VersionCreate>({
  version_number: '',
  description: '',
  developer_id: null,
  tester_id: null,
  expert_id: null,
})
const versionRules: FormRules<VersionCreate> = {
  version_number: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
}
const versionSubmitting = ref(false)

function openVersionDialog() {
  versionForm.version_number = ''
  versionForm.description = ''
  versionForm.developer_id = null
  versionForm.tester_id = null
  versionForm.expert_id = null
  versionDialogVisible.value = true
}

async function handleCreateVersion() {
  if (!versionFormRef.value) return
  await versionFormRef.value.validate(async (valid) => {
    if (!valid) return
    versionSubmitting.value = true
    try {
      const created = await createVersion(projectId.value, {
        version_number: versionForm.version_number,
        description: versionForm.description || undefined,
        developer_id: versionForm.developer_id || undefined,
        tester_id: versionForm.tester_id || undefined,
        expert_id: versionForm.expert_id || undefined,
      })
      ElMessage.success('版本创建成功（已自动生成草稿释放）')
      await loadVersions()  // 重新加载以获取 latest_release_status
      versionDialogVisible.value = false
    } catch {
      // 错误已统一提示
    } finally {
      versionSubmitting.value = false
    }
  })
}

function goBack() {
  router.push('/projects')
}

onMounted(async () => {
  await loadProject()
  await loadUsers()
  await loadVersions()
})
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div class="detail-header">
      <el-button @click="goBack"><el-icon><ArrowLeft /></el-icon>返回</el-button>
      <h2 class="page-title">项目详情</h2>
    </div>

    <!-- 加载失败错误态 -->
    <el-result
      v-if="loadError"
      icon="error"
      title="加载失败"
      sub-title="项目信息加载失败，请重试"
    >
      <template #extra>
        <el-button type="primary" @click="loadProject">重新加载</el-button>
      </template>
    </el-result>

    <!-- 功能1: 项目概览卡片 -->
    <el-row v-if="!loadError" :gutter="16" class="project-overview">
      <el-col :span="4"><div class="overview-card"><div class="num">{{ stats.total }}</div><div class="label">版本总数</div></div></el-col>
      <el-col :span="4"><div class="overview-card draft"><div class="num">{{ stats.draft }}</div><div class="label">草稿</div></div></el-col>
      <el-col :span="4"><div class="overview-card review"><div class="num">{{ stats.in_review }}</div><div class="label">评审中</div></div></el-col>
      <el-col :span="4"><div class="overview-card pending"><div class="num">{{ stats.pending_confirm }}</div><div class="label">待释放</div></div></el-col>
      <el-col :span="4"><div class="overview-card released"><div class="num">{{ stats.released }}</div><div class="label">已释放</div></div></el-col>
      <el-col :span="4"><div class="overview-card failed"><div class="num">{{ stats.failed }}</div><div class="label">阻塞中</div></div></el-col>
    </el-row>

    <!-- 项目基本信息 -->
    <el-card class="table-card" shadow="never" v-if="project">
      <template #header>
        <span>项目基本信息</span>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="项目名称">{{ project.name }}</el-descriptions-item>
        <el-descriptions-item label="项目经理">{{ userName(project.pm_user_id) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="project.is_active ? 'success' : 'danger'">
            {{ project.is_active ? '活跃' : '停用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ project.created_at?.replace('T', ' ').slice(0, 19) }}
        </el-descriptions-item>
        <el-descriptions-item label="更新时间">
          {{ project.updated_at?.replace('T', ' ').slice(0, 19) }}
        </el-descriptions-item>
        <el-descriptions-item label="项目描述" :span="3">
          {{ project.description || '—' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 项目成员 -->
    <el-card class="table-card" shadow="never" v-if="project">
      <template #header>
        <div class="card-header">
          <span>项目成员</span>
          <el-button v-if="isPm" type="primary" size="small" @click="openMemberDialog">
            <el-icon><Plus /></el-icon>添加成员
          </el-button>
        </div>
      </template>
      <el-table :data="project.members" border stripe>
        <el-table-column label="成员" min-width="180">
          <template #default="{ row }">{{ userName(row.user_id) }}</template>
        </el-table-column>
        <el-table-column label="项目角色" width="160">
          <template #default="{ row }">
            <el-tag>{{ roleLabel(row.project_role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <template v-if="canMutateMember(row)">
              <el-button type="primary" link size="small" @click="openEditDialog(row)">编辑角色</el-button>
              <el-button type="danger" link size="small" @click="handleDeleteMember(row)">移除</el-button>
            </template>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 版本列表 -->
    <el-card class="table-card" shadow="never" v-if="project">
      <template #header>
        <div class="card-header">
          <span>版本列表</span>
          <el-button v-if="isPm" type="primary" size="small" @click="openVersionDialog">
            <el-icon><Plus /></el-icon>创建版本
          </el-button>
        </div>
      </template>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="提示：版本创建时会自动生成一个草稿状态的释放；释放详情请在「首页 - 释放视图」中查看。"
        style="margin-bottom: 12px"
      />
      <el-table :data="versions" border stripe>
        <el-table-column prop="version_number" label="版本号" width="140" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="开发人员" width="150">
          <template #default="{ row }">{{ userName(row.developer_id) }}</template>
        </el-table-column>
        <el-table-column label="测试人员" width="150">
          <template #default="{ row }">{{ userName(row.tester_id) }}</template>
        </el-table-column>
        <el-table-column label="专家" width="150">
          <template #default="{ row }">{{ userName(row.expert_id) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ row.created_at?.replace('T', ' ').slice(0, 19) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="viewRelease(row.id)">查看释放</el-button>
            <el-button
              v-if="isPm"
              type="danger"
              link
              :disabled="row.latest_release_status === 'released'"
              @click="handleDeleteVersion(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="versions.length === 0" description="暂无版本，创建版本后将在此展示" />
    </el-card>

    <!-- 添加成员对话框 -->
    <el-dialog v-model="memberDialogVisible" title="添加成员" width="460px">
      <el-form ref="memberFormRef" :model="memberForm" :rules="memberRules" label-width="90px">
        <el-form-item label="用户" prop="user_id">
          <el-select v-model="memberForm.user_id" placeholder="请选择用户" filterable style="width: 100%">
            <el-option
              v-for="opt in userOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="项目角色" prop="project_role">
          <el-select v-model="memberForm.project_role" style="width: 100%">
            <el-option
              v-for="opt in roleOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memberDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="memberSubmitting" @click="handleAddMember">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑成员角色对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑成员角色" width="460px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
        <el-form-item label="成员">
          <span>{{ userName(editForm.user_id) }}</span>
        </el-form-item>
        <el-form-item label="项目角色" prop="project_role">
          <el-select v-model="editForm.project_role" style="width: 100%">
            <el-option
              v-for="opt in roleOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-alert
          v-if="editForm.user_id === project?.pm_user_id"
          type="warning"
          :closable="false"
          show-icon
          title="该成员为当前项目经理；修改其角色将不会自动变更项目的 pm_user_id 字段。如需变更项目经理，请联系超级管理员或管理员。"
        />
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSubmitting" @click="handleEditMember">保存</el-button>
      </template>
    </el-dialog>

    <!-- 创建版本对话框 -->
    <el-dialog v-model="versionDialogVisible" title="创建版本" width="520px" class="dialog-scroll">
      <el-form ref="versionFormRef" :model="versionForm" :rules="versionRules" label-width="90px">
        <el-form-item label="版本号" prop="version_number">
          <el-input v-model="versionForm.version_number" placeholder="例如：v1.0.0" />
        </el-form-item>
        <el-form-item label="版本描述" prop="description">
          <el-input v-model="versionForm.description" type="textarea" :rows="3" placeholder="版本描述（可选）" />
        </el-form-item>
        <el-form-item label="开发人员" prop="developer_id">
          <el-select v-model="versionForm.developer_id" placeholder="选择开发人员（可选）" filterable clearable style="width: 100%">
            <el-option v-for="opt in userOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="测试人员" prop="tester_id">
          <el-select v-model="versionForm.tester_id" placeholder="选择测试人员（可选）" filterable clearable style="width: 100%">
            <el-option v-for="opt in userOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="外部专家" prop="expert_id">
          <el-select v-model="versionForm.expert_id" placeholder="选择外部专家（可选）" filterable clearable style="width: 100%">
            <el-option v-for="opt in userOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="versionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="versionSubmitting" @click="handleCreateVersion">确定</el-button>
      </template>
    </el-dialog>
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

:deep(.dialog-scroll .el-dialog__body) {
  max-height: 60vh;
  overflow-y: auto;
}
.muted-text {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
/* 功能1: 项目概览卡片 */
.project-overview {
  margin-bottom: 20px;
}
.overview-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 16px 12px;
  text-align: center;
  transition: all 0.2s;
}
.overview-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
.overview-card .num {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
}
.overview-card .label {
  font-size: 13px;
  color: #909399;
  margin-top: 6px;
}
.overview-card.draft .num { color: #909399; }
.overview-card.review .num { color: #e6a23c; }
.overview-card.pending .num { color: #409eff; }
.overview-card.released .num { color: #67c23a; }
.overview-card.failed .num { color: #f56c6c; }

</style>
