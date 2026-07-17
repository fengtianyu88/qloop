<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
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
      <el-table :data="projectList" v-loading="loading" border stripe>
        <el-table-column prop="name" label="项目名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="成员数量" width="100" align="center">
          <template #default="{ row }">{{ row.members?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '活跃' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ row.created_at?.replace('T', ' ').slice(0, 19) }}</template>
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
</style>
