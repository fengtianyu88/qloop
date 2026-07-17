<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { getCurrentUser, updateUser } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import { roleLabel } from '@/utils/status'
import type { UserUpdate } from '@/types'

const authStore = useAuthStore()

const profileFormRef = ref<FormInstance>()
const profileForm = reactive({
  full_name: '',
  email: '',
  department: '',
  section: '',
})
const profileRules: FormRules = {
  full_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
}
const profileSubmitting = ref(false)

// 修改密码
const passwordFormRef = ref<FormInstance>()
const passwordForm = reactive({
  password: '',
  confirmPassword: '',
})
const passwordRules: FormRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度不少于 6 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (e?: Error) => void) => {
        if (value !== passwordForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}
const passwordSubmitting = ref(false)

async function loadProfile() {
  try {
    const user = await getCurrentUser()
    authStore.user = user
    profileForm.full_name = user.full_name
    profileForm.email = user.email
    profileForm.department = user.department || ''
    profileForm.section = user.section || ''
  } catch {
    // 错误已统一提示
  }
}

async function handleSaveProfile() {
  if (!profileFormRef.value) return
  const user = authStore.user
  if (!user) return
  await profileFormRef.value.validate(async (valid) => {
    if (!valid) return
    profileSubmitting.value = true
    try {
      const payload: UserUpdate = {
        full_name: profileForm.full_name,
        email: profileForm.email,
        department: profileForm.department || null,
        section: profileForm.section || null,
      }
      const updated = await updateUser(user.id, payload)
      authStore.user = updated
      ElMessage.success('个人信息保存成功')
    } catch {
      // 错误已统一提示
    } finally {
      profileSubmitting.value = false
    }
  })
}

async function handleChangePassword() {
  if (!passwordFormRef.value) return
  const user = authStore.user
  if (!user) return
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return
    passwordSubmitting.value = true
    try {
      await updateUser(user.id, { password: passwordForm.password })
      ElMessage.success('密码修改成功')
      passwordForm.password = ''
      passwordForm.confirmPassword = ''
    } catch {
      // 错误已统一提示
    } finally {
      passwordSubmitting.value = false
    }
  })
}

onMounted(() => {
  loadProfile()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">个人信息</h2>

    <el-row :gutter="20">
      <!-- 基础信息展示 -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>账号信息</span></template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="用户名">
              {{ authStore.user?.username || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="系统角色">
              <el-tag>{{ roleLabel(authStore.user?.system_role || 'guest') }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="账号状态">
              <el-tag :type="authStore.user?.is_active ? 'success' : 'danger'">
                {{ authStore.user?.is_active ? '启用' : '禁用' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <!-- 编辑表单 -->
      <el-col :span="16">
        <el-card class="table-card" shadow="never">
          <template #header><span>编辑个人信息</span></template>
          <el-form
            ref="profileFormRef"
            :model="profileForm"
            :rules="profileRules"
            label-width="90px"
          >
            <el-form-item label="姓名" prop="full_name">
              <el-input v-model="profileForm.full_name" />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="profileForm.email" />
            </el-form-item>
            <el-form-item label="部门">
              <el-input v-model="profileForm.department" placeholder="部门（可选）" />
            </el-form-item>
            <el-form-item label="科室">
              <el-input v-model="profileForm.section" placeholder="科室（可选）" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="profileSubmitting" @click="handleSaveProfile">
                保存
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never">
          <template #header><span>修改密码</span></template>
          <el-form
            ref="passwordFormRef"
            :model="passwordForm"
            :rules="passwordRules"
            label-width="100px"
          >
            <el-form-item label="新密码" prop="password">
              <el-input v-model="passwordForm.password" type="password" show-password />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input v-model="passwordForm.confirmPassword" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="passwordSubmitting" @click="handleChangePassword">
                修改密码
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
