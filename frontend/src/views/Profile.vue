<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { getCurrentUser, updateUser, changeMyPassword, updateMyGitCredentials } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import { systemRoleLabel } from '@/utils/status'
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
  currentPassword: '',
  password: '',
  confirmPassword: '',
})
const passwordRules: FormRules = {
  currentPassword: [
    { required: true, message: '请输入当前密码', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码长度不少于 8 位', trigger: 'blur' },
    {
      pattern: /^(?=.*[A-Za-z])(?=.*\d).{8,}$/,
      message: '密码必须至少 8 位,且包含字母和数字',
      trigger: 'blur',
    },
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

// Git 凭据
const gitFormRef = ref<FormInstance>()
const gitForm = reactive({
  git_username: '',
  git_token: '',
})
const gitRules: FormRules = {
  git_username: [
    { max: 200, message: 'Git 用户名长度不能超过 200', trigger: 'blur' },
  ],
}
const gitSubmitting = ref(false)
// 是否已配置 Git token(从后端获取,用于显示"已配置"标记)
const hasGitToken = ref(false)

async function loadProfile() {
  try {
    const user = await getCurrentUser()
    authStore.user = user
    profileForm.full_name = user.full_name
    profileForm.email = user.email
    profileForm.department = user.department || ''
    profileForm.section = user.section || ''
    // 加载 Git 凭据信息
    gitForm.git_username = user.git_username || ''
    gitForm.git_token = '' // 永远不回显 token,用户重新输入才更新
    hasGitToken.value = user.has_git_token ?? false
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
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return
    passwordSubmitting.value = true
    try {
      await changeMyPassword(passwordForm.currentPassword, passwordForm.password)
      ElMessage.success('密码修改成功')
      passwordForm.currentPassword = ''
      passwordForm.password = ''
      passwordForm.confirmPassword = ''
    } catch {
      // 错误已统一提示
    } finally {
      passwordSubmitting.value = false
    }
  })
}

async function handleSaveGit() {
  if (!gitFormRef.value) return
  await gitFormRef.value.validate(async (valid) => {
    if (!valid) return
    gitSubmitting.value = true
    try {
      // token 为空字符串时表示"不修改";用户若想清除 token,需要点击"清除 token"按钮
      const tokenToSend = gitForm.git_token || null
      const res = await updateMyGitCredentials(gitForm.git_username, tokenToSend)
      hasGitToken.value = res.has_git_token
      // 清空 token 输入框(不回显)
      gitForm.git_token = ''
      // 同步更新 authStore 中的 git_username
      if (authStore.user) {
        authStore.user.git_username = res.git_username
        authStore.user.has_git_token = res.has_git_token
      }
      ElMessage.success(res.message || 'Git 凭据已保存')
    } catch {
      // 错误已统一提示
    } finally {
      gitSubmitting.value = false
    }
  })
}

async function handleClearGitToken() {
  gitSubmitting.value = true
  try {
    const res = await updateMyGitCredentials(null, '')
    hasGitToken.value = res.has_git_token
    gitForm.git_token = ''
    if (authStore.user) {
      authStore.user.has_git_token = res.has_git_token
    }
    ElMessage.success(res.message || 'Git Token 已清除')
  } catch {
    // 错误已统一提示
  } finally {
    gitSubmitting.value = false
  }
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
              <el-tag>{{ systemRoleLabel(authStore.user?.system_role || 'guest') }}</el-tag>
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
            <el-form-item label="当前密码" prop="currentPassword">
              <el-input v-model="passwordForm.currentPassword" type="password" show-password placeholder="请输入当前密码" />
            </el-form-item>
            <el-form-item label="新密码" prop="password">
              <el-input v-model="passwordForm.password" type="password" show-password placeholder="至少8位,含字母和数字" />
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

        <el-card shadow="never">
          <template #header>
            <span>Git 推送凭据</span>
            <el-tag v-if="hasGitToken" type="success" size="small" style="margin-left:8px;">Token 已配置</el-tag>
            <el-tag v-else type="info" size="small" style="margin-left:8px;">未配置 Token</el-tag>
          </template>
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom:16px;"
            title="用于版本释放后,以你的 Git 账号推送交付物到项目 Git 仓库"
            description="Git Token 不会回显,留空表示本次不修改;需要修改时重新输入即可。"
          />
          <el-form
            ref="gitFormRef"
            :model="gitForm"
            :rules="gitRules"
            label-width="100px"
          >
            <el-form-item label="Git 用户名" prop="git_username">
              <el-input v-model="gitForm.git_username" placeholder="如 fengtianyu88" />
            </el-form-item>
            <el-form-item label="Git Token" prop="git_token">
              <el-input
                v-model="gitForm.git_token"
                type="password"
                show-password
                :placeholder="hasGitToken ? '已配置,留空表示不修改' : '请输入 Git Personal Access Token'"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="gitSubmitting" @click="handleSaveGit">
                保存 Git 凭据
              </el-button>
              <el-button
                v-if="hasGitToken"
                type="danger"
                plain
                :loading="gitSubmitting"
                @click="handleClearGitToken"
              >
                清除 Token
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
