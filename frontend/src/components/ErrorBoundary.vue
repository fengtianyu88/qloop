<template>
  <slot v-if="!hasError" />
  <div v-else class="error-boundary">
    <el-result icon="error" title="页面渲染异常" sub-title="请刷新页面重试，若问题持续请联系管理员">
      <template #extra>
        <el-button type="primary" @click="handleRetry">刷新页面</el-button>
      </template>
    </el-result>
  </div>
</template>
<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'

const hasError = ref(false)
const errorInfo = ref('')

onErrorCaptured((err, _instance, info) => {
  console.error('ErrorBoundary捕获:', err, info)
  hasError.value = true
  errorInfo.value = String(err)
  return false // 阻止继续向上冒泡
})

function handleRetry() {
  hasError.value = false
  errorInfo.value = ''
  location.reload()
}
</script>
<style scoped>
.error-boundary {
  padding: 40px;
}
</style>
