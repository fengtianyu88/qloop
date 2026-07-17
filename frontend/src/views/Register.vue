<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { register } from '@/api/auth'

const router = useRouter()
const registerFormRef = ref<FormInstance>()
const loading = ref(false)

const registerForm = reactive({
  username: '',
  email: '',
  full_name: '',
  password: '',
  confirm_password: '',
  department: '',
  section: '',
})

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 100, message: '用户名长度 3-100 个字符', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' },
  ],
  full_name: [
    { required: true, message: '请输入姓名', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 128, message: '密码长度 6-128 个字符', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: any) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

async function handleRegister() {
  if (!registerFormRef.value) return
  await registerFormRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await register({
        username: registerForm.username,
        email: registerForm.email,
        full_name: registerForm.full_name,
        password: registerForm.password,
        department: registerForm.department || undefined,
        section: registerForm.section || undefined,
      })
      ElMessage.success('注册成功，请登录')
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
  <div class="register-container">
    <div class="register-card">
      <div class="register-header">
        <el-icon class="register-logo"><UserFilled /></el-icon>
        <h2 class="register-title">注册新账号</h2>
        <p class="register-subtitle">注册后默认为访客角色，管理员可后续调整权限</p>
      </div>

      <el-form
        ref="registerFormRef"
        :model="registerForm"
        :rules="rules"
        size="large"
        class="register-form"
        @keyup.enter="handleRegister"
      >
        <el-form-item prop="username">
          <el-input v-model="registerForm.username" placeholder="用户名" :prefix-icon="'User'" clearable />
        </el-form-item>
        <el-form-item prop="full_name">
          <el-input v-model="registerForm.full_name" placeholder="姓名" :prefix-icon="'Postcard'" clearable />
        </el-form-item>
        <el-form-item prop="email">
          <el-input v-model="registerForm.email" placeholder="邮箱" :prefix-icon="'Message'" clearable />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="registerForm.password" type="password" placeholder="密码" :prefix-icon="'Lock'" show-password clearable />
        </el-form-item>
        <el-form-item prop="confirm_password">
          <el-input v-model="registerForm.confirm_password" type="password" placeholder="确认密码" :prefix-icon="'Lock'" show-password clearable />
        </el-form-item>
        <el-form-item prop="department">
          <el-input v-model="registerForm.department" placeholder="所属部门（选填）" :prefix-icon="'OfficeBuilding'" clearable />
        </el-form-item>
        <el-form-item prop="section">
          <el-input v-model="registerForm.section" placeholder="所属科室（选填）" :prefix-icon="'Briefcase'" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="register-button" :loading="loading" @click="handleRegister">
            注 册
          </el-button>
        </el-form-item>
      </el-form>

      <div class="register-actions">
        <el-button text type="primary" @click="router.push('/login')">已有账号？返回登录</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.register-container {
  min-height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2a44 0%, #2b3a67 40%, #4062b8 100%);
  padding: 20px 0;
}

.register-card {
  width: 420px;
  padding: 36px 36px 24px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
}

.register-header {
  text-align: center;
  margin-bottom: 24px;
}

.register-logo {
  font-size: 40px;
  color: #409eff;
  margin-bottom: 10px;
}

.register-title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.register-subtitle {
  margin: 0;
  font-size: 12px;
  color: #909399;
}

.register-form {
  margin-top: 8px;
}

.register-button {
  width: 100%;
}

.register-actions {
  text-align: center;
  margin-top: 8px;
}
</style>
