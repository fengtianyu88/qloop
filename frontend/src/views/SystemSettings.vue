<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { getSystemSettings, updateSystemSettings } from '@/api/systemSettings'
import type { SystemSettingsUpdate } from '@/types'

const loading = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const lastUpdated = ref<string | null>(null)
const updatedByName = ref<string | null>(null)

const form = reactive<SystemSettingsUpdate>({
  site_name: '',
  site_short_name: '',
})

const rules: FormRules<SystemSettingsUpdate> = {
  site_name: [
    { required: true, message: '请输入站点完整名称', trigger: 'blur' },
    { max: 100, message: '不超过 100 个字符', trigger: 'blur' },
  ],
  site_short_name: [
    { required: true, message: '请输入站点简短名称', trigger: 'blur' },
    { max: 50, message: '不超过 50 个字符', trigger: 'blur' },
  ],
}

async function loadSettings() {
  loading.value = true
  try {
    const s = await getSystemSettings()
    form.site_name = s.site_name
    form.site_short_name = s.site_short_name
    lastUpdated.value = s.updated_at
    updatedByName.value = s.updated_by
  } catch {
    // 错误已统一提示
  } finally {
    loading.value = false
  }
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const updated = await updateSystemSettings({ ...form })
      ElMessage.success('系统设置已更新')
      lastUpdated.value = updated.updated_at
      updatedByName.value = updated.updated_by
      // 通知整站更新品牌名（通过自定义事件 + localStorage 信号）
      localStorage.setItem(
        'qloop_site_info',
        JSON.stringify({
          site_name: updated.site_name,
          site_short_name: updated.site_short_name,
          ts: Date.now(),
        }),
      )
      window.dispatchEvent(new Event('qloop:site-info-updated'))
    } catch {
      // 错误已统一提示
    } finally {
      submitting.value = false
    }
  })
}

function handleReset() {
  loadSettings()
}

onMounted(async () => {
  await loadSettings()
})
</script>

<template>
  <div class="page-container" v-loading="loading">
    <h2 class="page-title">系统设置</h2>

    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>站点品牌</span>
          <span v-if="lastUpdated" class="muted-text">
            最后更新：{{ lastUpdated.replace('T', ' ').slice(0, 19) }}
          </span>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="站点完整名称显示在浏览器标签、登录页大标题、顶栏；站点简短名称显示在侧边栏 logo。"
        style="margin-bottom: 16px"
      />

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="140px"
        style="max-width: 600px"
      >
        <el-form-item label="站点完整名称" prop="site_name">
          <el-input v-model="form.site_name" placeholder="例如：qloop 质量环" />
        </el-form-item>
        <el-form-item label="站点简短名称" prop="site_short_name">
          <el-input v-model="form.site_short_name" placeholder="例如：qloop" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            保存
          </el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card" shadow="never">
      <template #header>
        <span>说明</span>
      </template>
      <ul class="tips-list">
        <li>站点名称存储在数据库的 <code>system_settings</code> 表中，全系统仅一行（单例）。</li>
        <li>只有超级管理员（super_admin）可以查看和修改站点名称。</li>
        <li>修改后所有客户端会在下次刷新时生效；当前页面会立即更新顶栏与侧边栏。</li>
        <li>此处修改不会影响 <code>VITE_APP_TITLE</code> 环境变量（仅作为浏览器标签的初始值）。</li>
      </ul>
    </el-card>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.muted-text {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.tips-list {
  margin: 0;
  padding-left: 20px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
}

.tips-list code {
  background: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
}
</style>
