<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import type { LoginRequest } from '@/types'
import { useSiteInfoStore } from '@/stores/siteInfo'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const siteInfoStore = useSiteInfoStore()
const APP_TITLE = computed(() => siteInfoStore.siteName)

onMounted(async () => {
  await siteInfoStore.refresh()
})

const loginFormRef = ref<FormInstance>()
const loading = ref(false)
// P2-8: 记住我 - 默认根据上次选择初始化
const rememberMe = ref(localStorage.getItem('remember_me') !== 'false')

const loginForm = reactive<LoginRequest>({
  username: '',
  password: '',
})

const rules: FormRules<LoginRequest> = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不少于 6 位', trigger: 'blur' },
  ],
}

async function handleLogin() {
  if (!loginFormRef.value) return
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      // P2-8: 把"记住我"选择传给 store,决定 token 存储位置
      await authStore.login(loginForm, rememberMe.value)
      ElMessage.success('登录成功')
      const redirect = (route.query.redirect as string) || '/home'
      router.push(redirect)
    } catch {
      // 错误信息已由拦截器统一提示
    } finally {
      loading.value = false
    }
  })
}

</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <el-icon class="login-logo"><Cpu /></el-icon>
        <h2 class="login-title">{{ APP_TITLE }}</h2>
        <p class="login-subtitle">请登录以继续</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="rules"
        size="large"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="用户名"
            :prefix-icon="'User'"
            clearable
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            :prefix-icon="'Lock'"
            show-password
            clearable
          />
        </el-form-item>
        <el-form-item>
          <!-- P2-8: 记住我 - 勾选时 token 存 localStorage,否则存 sessionStorage -->
          <div class="login-options">
            <el-checkbox v-model="rememberMe">记住我</el-checkbox>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="login-button"
            :loading="loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-actions">
        <el-button text type="primary" @click="router.push('/register')">注册新账号</el-button>
        <el-button text type="info" @click="router.push('/forgot-password')">忘记密码？</el-button>
      </div>

      <div class="login-footer">
        <span>{{ APP_TITLE }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2a44 0%, #2b3a67 40%, #4062b8 100%);
}

.login-card {
  width: 420px;
  padding: 40px 36px 28px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
}

.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.login-logo {
  font-size: 44px;
  color: #409eff;
  margin-bottom: 12px;
}

.login-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.login-subtitle {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.login-form {
  margin-top: 8px;
}

.login-button {
  width: 100%;
}

.login-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
}

.login-options {
  width: 100%;
  display: flex;
  justify-content: flex-start;
  align-items: center;
}

.login-footer {
  text-align: center;
  margin-top: 18px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
