<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { getProject, addMember, createVersion } from '@/api/projects'
import { getUsers } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import { roleLabel } from '@/utils/status'
import type {
  Project,
  ProjectMemberCreate,
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

// 用户字典（仅 admin 可获取完整用户列表用于姓名解析与选择）
const userMap = ref<Record<string, User>>({})
const userList = ref<User[]>([])

// 版本列表（后端暂无列表接口，使用本地态，创建后即时展示）
const versions = ref<Version[]>([])

// 是否为当前项目的 PM
const isPm = computed(
  () => project.value?.pm_user_id === authStore.user?.id || authStore.isAdmin,
)

function userName(id: string | null | undefined): string {
  if (!id) return '—'
  return userMap.value[id]?.full_name || id.slice(0, 8) + '…'
}

async function loadProject() {
  loading.value = true
  try {
    project.value = await getProject(projectId.value)
  } catch {
    // 错误已统一提示
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  // 仅 admin / super_admin 可获取用户列表；失败则降级使用项目成员 ID
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
      versions.value.unshift(created)
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
})
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div class="detail-header">
      <el-button @click="goBack"><el-icon><ArrowLeft /></el-icon>返回</el-button>
      <h2 class="page-title">项目详情</h2>
    </div>

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

    <!-- 创建版本对话框 -->
    <el-dialog v-model="versionDialogVisible" title="创建版本" width="520px">
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
</style>
