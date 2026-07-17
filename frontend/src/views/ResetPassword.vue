<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { resetPassword } from '@/api/auth'

const route = useRoute()
const router = useRouter()
const resetFormRef = ref<FormInstance>()
const loading = ref(false)
const token = ref('')

const resetForm = reactive({
  new_password: '',
  confirm_password: '',
})

const rules: FormRules = {
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 128, message: '密码长度 6-128 个字符', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: any) => {
        if (value !== resetForm.new_password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

onMounted(() => {
  token.value = (route.query.token as string) || ''
  if (!token.value) {
    ElMessage.error('重置链接无效，请重新获取')
    router.push('/forgot-password')
  }
})

async function handleReset() {
  if (!resetFormRef.value) return
  await resetFormRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await resetPassword(token.value, resetForm.new_password)
      ElMessage.success('密码重置成功，请使用新密码登录')
      router.push('/login')
    } catch {
      // 错误信息已由拦截器统一提示
    } finally {
      loading.value = false
    }
  })
}
</script>

<template>
  <div class="reset-container">
    <div class="reset-card">
      <div class="reset-header">
        <el-icon class="reset-logo"><Lock /></el-icon>
        <h2 class="reset-title">重置密码</h2>
        <p class="reset-subtitle">请输入您的新密码</p>
      </div>

      <el-form
        ref="resetFormRef"
        :model="resetForm"
        :rules="rules"
        size="large"
        class="reset-form"
        @keyup.enter="handleReset"
      >
        <el-form-item prop="new_password">
          <el-input v-model="resetForm.new_password" type="password" placeholder="新密码" :prefix-icon="'Lock'" show-password clearable />
        </el-form-item>
        <el-form-item prop="confirm_password">
          <el-input v-model="resetForm.confirm_password" type="password" placeholder="确认新密码" :prefix-icon="'Lock'" show-password clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="reset-button" :loading="loading" @click="handleReset">
            重置密码
          </el-button>
        </el-form-item>
      </el-form>

      <div class="reset-actions">
        <el-button text type="primary" @click="router.push('/login')">返回登录</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reset-container {
  height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2a44 0%, #2b3a67 40%, #4062b8 100%);
}

.reset-card {
  width: 420px;
  padding: 40px 36px 28px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
}

.reset-header {
  text-align: center;
  margin-bottom: 28px;
}

.reset-logo {
  font-size: 44px;
  color: #f56c6c;
  margin-bottom: 12px;
}

.reset-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.reset-subtitle {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.reset-form {
  margin-top: 8px;
}

.reset-button {
  width: 100%;
}

.reset-actions {
  text-align: center;
  margin-top: 8px;
}
</style>
