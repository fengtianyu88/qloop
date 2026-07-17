<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { forgotPassword } from '@/api/auth'

const router = useRouter()
const forgotFormRef = ref<FormInstance>()
const loading = ref(false)
const sent = ref(false)

const forgotForm = reactive({
  email: '',
})

const rules: FormRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' },
  ],
}

async function handleSend() {
  if (!forgotFormRef.value) return
  await forgotFormRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await forgotPassword(forgotForm.email)
      sent.value = true
      ElMessage.success('重置链接已发送')
    } catch {
      // 错误信息已由拦截器统一提示
    } finally {
      loading.value = false
    }
  })
}
</script>

<template>
  <div class="forgot-container">
    <div class="forgot-card">
      <div class="forgot-header">
        <el-icon class="forgot-logo"><Key /></el-icon>
        <h2 class="forgot-title">找回密码</h2>
        <p class="forgot-subtitle">输入注册邮箱，我们将向您发送密码重置链接</p>
      </div>

      <!-- 发送前表单 -->
      <el-form
        v-if="!sent"
        ref="forgotFormRef"
        :model="forgotForm"
        :rules="rules"
        size="large"
        class="forgot-form"
        @keyup.enter="handleSend"
      >
        <el-form-item prop="email">
          <el-input v-model="forgotForm.email" placeholder="注册邮箱" :prefix-icon="'Message'" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="forgot-button" :loading="loading" @click="handleSend">
            发送重置链接
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 发送后提示 -->
      <div v-else class="forgot-success">
        <el-result icon="success" title="重置链接已发送" sub-title="请检查您的邮箱，点击邮件中的链接重置密码。链接1小时内有效。">
          <template #extra>
            <el-button type="primary" @click="router.push('/login')">返回登录</el-button>
          </template>
        </el-result>
      </div>

      <div v-if="!sent" class="forgot-actions">
        <el-button text type="primary" @click="router.push('/login')">返回登录</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.forgot-container {
  height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2a44 0%, #2b3a67 40%, #4062b8 100%);
}

.forgot-card {
  width: 420px;
  padding: 40px 36px 28px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
}

.forgot-header {
  text-align: center;
  margin-bottom: 28px;
}

.forgot-logo {
  font-size: 44px;
  color: #e6a23c;
  margin-bottom: 12px;
}

.forgot-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.forgot-subtitle {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.forgot-form {
  margin-top: 8px;
}

.forgot-button {
  width: 100%;
}

.forgot-actions {
  text-align: center;
  margin-top: 8px;
}
</style>
