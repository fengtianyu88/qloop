<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Download, Upload } from '@element-plus/icons-vue'
import {
  getUsers,
  createUser,
  updateUser,
  deleteUser,
} from '@/api/users'
import { downloadUsersTemplate, importUsers } from '@/api/imports'
import { useAuthStore } from '@/stores/auth'
import { roleLabel } from '@/utils/status'
import type {
  SystemRole,
  User,
  UserCreate,
  UserListParams,
  UserUpdate,
} from '@/types'

const authStore = useAuthStore()

const list = ref<User[]>([])
const total = ref(0)
const loading = ref(false)
const queryParams = reactive<UserListParams>({
  page: 1,
  page_size: 10,
  search: '',
})

const roleOptions: { label: string; value: SystemRole }[] = [
  { label: '访客', value: 'guest' },
  { label: '开发人员', value: 'developer' },
  { label: '管理员', value: 'admin' },
  { label: '超级管理员', value: 'super_admin' },
]

async function loadList() {
  loading.value = true
  try {
    const res = await getUsers(queryParams)
    list.value = res.items
    total.value = res.total
  } catch {
    // 错误已统一提示
  } finally {
    loading.value = false
  }
}

async function handleDownloadTemplate() {
  try {
    const blob = await downloadUsersTemplate()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'users_template.xlsx'
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
    const res = await importUsers(file)
    ElMessage.success(`导入完成：成功 ${res.success} 个，失败 ${res.failed} 个`)
    if (res.errors.length > 0) {
      ElMessageBox.alert(res.errors.slice(0, 5).join('\n'), '失败详情', { type: 'warning' })
    }
    await loadList()  // 刷新列表
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    target.value = ''  // 清空,允许重复选择同一文件
  }
}

function handleSearch() {
  queryParams.page = 1
  loadList()
}

function handleReset() {
  queryParams.search = ''
  queryParams.page = 1
  loadList()
}

function handlePageChange(page: number) {
  queryParams.page = page
  loadList()
}

function handleSizeChange(size: number) {
  queryParams.page_size = size
  queryParams.page = 1
  loadList()
}

// ------------------------- 创建 / 编辑用户 -------------------------
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = reactive<UserCreate & { id?: string; is_active?: boolean }>({
  username: '',
  full_name: '',
  email: '',
  password: '',
  system_role: 'developer',
  department: '',
  section: '',
  is_active: true,
})

// 密码强度校验：至少 8 位且须包含字母和数字；空值放行（编辑模式允许不改密码）
const passwordValidator = (rule: any, value: string, callback: any) => {
  if (!value) return callback()
  if (value.length < 8) return callback(new Error('密码长度不少于 8 位'))
  if (!/[a-zA-Z]/.test(value) || !/\d/.test(value)) {
    return callback(new Error('密码须包含字母和数字'))
  }
  callback()
}

const rules = computed<FormRules>(() => {
  const base: FormRules = {
    username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
    full_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
    email: [
      { required: true, message: '请输入邮箱', trigger: 'blur' },
      { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
    ],
    system_role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  }
  // 创建时密码必填，编辑时密码非必填（留空不修改）
  if (dialogMode.value === 'create') {
    base.password = [
      { required: true, message: '请输入密码', trigger: 'blur' },
      { validator: passwordValidator, trigger: ['blur', 'change'] },
    ]
  } else {
    base.password = [{ validator: passwordValidator, trigger: ['blur', 'change'] }]
  }
  return base
})

function openCreateDialog() {
  dialogMode.value = 'create'
  form.id = undefined
  form.username = ''
  form.full_name = ''
  form.email = ''
  form.password = ''
  form.system_role = 'developer'
  form.department = ''
  form.section = ''
  form.is_active = true
  dialogVisible.value = true
}

function openEditDialog(row: User) {
  dialogMode.value = 'edit'
  form.id = row.id
  form.username = row.username
  form.full_name = row.full_name
  form.email = row.email
  form.password = ''
  form.system_role = row.system_role
  form.department = row.department || ''
  form.section = row.section || ''
  form.is_active = row.is_active
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      if (dialogMode.value === 'create') {
        const payload: UserCreate = {
          username: form.username,
          full_name: form.full_name,
          email: form.email,
          password: form.password,
          system_role: form.system_role,
          department: form.department || null,
          section: form.section || null,
        }
        await createUser(payload)
        ElMessage.success('用户创建成功')
      } else {
        const payload: UserUpdate = {
          full_name: form.full_name,
          email: form.email,
          system_role: form.system_role,
          department: form.department || null,
          section: form.section || null,
          is_active: form.is_active,
        }
        if (form.password) {
          payload.password = form.password
        }
        await updateUser(form.id!, payload)
        ElMessage.success('用户更新成功')
      }
      dialogVisible.value = false
      await loadList()
    } catch {
      // 错误已统一提示
    } finally {
      submitting.value = false
    }
  })
}

async function handleToggleStatus(row: User) {
  const action = row.is_active ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确定要${action}用户「${row.full_name}」吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    if (row.is_active) {
      await deleteUser(row.id)
      ElMessage.success('已禁用')
    } else {
      await updateUser(row.id, { is_active: true })
      ElMessage.success('已启用')
    }
    await loadList()
  } catch {
    // 取消或错误
  }
}

onMounted(() => {
  loadList()
})
</script>

<template>
  <div class="page-container">
    <div class="list-header">
      <h2 class="page-title">用户管理</h2>
      <div class="list-header-actions">
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>创建用户
        </el-button>
        <template v-if="authStore.isAdmin">
          <el-button size="default" @click="handleDownloadTemplate">
            <el-icon><Download /></el-icon>下载模板
          </el-button>
          <el-button size="default" @click="handleImportClick">
            <el-icon><Upload /></el-icon>批量导入
          </el-button>
          <input ref="importInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleImportFile" />
        </template>
      </div>
    </div>

    <el-card class="filter-card" shadow="never">
      <el-form :inline="true">
        <el-form-item label="搜索">
          <el-input
            v-model="queryParams.search"
            placeholder="用户名 / 姓名 / 邮箱"
            clearable
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table :data="list" v-loading="loading" border stripe>
        <el-table-column prop="username" label="用户名" width="130" show-overflow-tooltip />
        <el-table-column prop="full_name" label="姓名" width="120" show-overflow-tooltip />
        <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column label="角色" width="120" align="center">
          <template #default="{ row }">
            <el-tag>{{ roleLabel(row.system_role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="department" label="部门" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.department || '—' }}</template>
        </el-table-column>
        <el-table-column prop="section" label="科室" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.section || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link @click="openEditDialog(row)">编辑</el-button>
            <el-button
              :type="row.is_active ? 'danger' : 'success'"
              link
              @click="handleToggleStatus(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="queryParams.page"
          v-model:page-size="queryParams.page_size"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <!-- 创建 / 编辑 用户对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '创建用户' : '编辑用户'"
      width="520px"
      class="dialog-scroll"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="dialogMode === 'edit'" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item label="姓名" prop="full_name">
          <el-input v-model="form.full_name" placeholder="真实姓名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="邮箱地址" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="dialogMode === 'edit' ? '留空则不修改密码' : '请输入密码'"
          />
        </el-form-item>
        <el-form-item label="系统角色" prop="system_role">
          <el-select v-model="form.system_role" style="width: 100%">
            <el-option
              v-for="opt in roleOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="form.department" placeholder="部门（可选）" />
        </el-form-item>
        <el-form-item label="科室">
          <el-input v-model="form.section" placeholder="科室（可选）" />
        </el-form-item>
        <el-form-item v-if="dialogMode === 'edit'" label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
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

:deep(.dialog-scroll .el-dialog__body) {
  max-height: 60vh;
  overflow-y: auto;
}
</style>
