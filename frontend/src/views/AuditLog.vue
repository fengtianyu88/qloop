<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getAuditLogs } from '@/api/audit'
import { getUsers } from '@/api/users'
import type { AuditLog, AuditLogParams, User } from '@/types'

const list = ref<AuditLog[]>([])
const total = ref(0)
const loading = ref(false)
const userMap = ref<Record<string, User>>({})

const queryParams = reactive<AuditLogParams>({
  page: 1,
  page_size: 10,
  action: '',
  resource_type: '',
})

const actionOptions = [
  'login', 'logout', 'create', 'update', 'delete',
  'upload_code_package', 'upload_test_report', 'upload_review_report',
  'confirm_release', 'trigger_review', 'create_member', 'create_version',
]
const resourceTypeOptions = [
  'user', 'project', 'project_member', 'version', 'release',
  'review', 'llm_model', 'review_rule', 'org_unit', 'admin_scope', 'notification',
]

async function loadUsers() {
  try {
    const res = await getUsers({ page: 1, page_size: 500 })
    const map: Record<string, User> = {}
    res.items.forEach((u) => {
      map[u.id] = u
    })
    userMap.value = map
  } catch {
    // ignore
  }
}

function userName(id: string | null | undefined): string {
  if (!id) return '系统'
  return userMap.value[id]?.full_name || id.slice(0, 8) + '…'
}

function formatTime(t: string | null | undefined): string {
  if (!t) return '—'
  return t.replace('T', ' ').slice(0, 19)
}

function detailsText(d: Record<string, unknown> | null): string {
  if (!d) return '—'
  try {
    return JSON.stringify(d)
  } catch {
    return '—'
  }
}

async function loadList() {
  loading.value = true
  try {
    const params: AuditLogParams = {
      page: queryParams.page,
      page_size: queryParams.page_size,
    }
    if (queryParams.action) params.action = queryParams.action
    if (queryParams.resource_type) params.resource_type = queryParams.resource_type
    const res = await getAuditLogs(params)
    list.value = res.items
    total.value = res.total
  } catch {
    // 错误已统一提示
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  queryParams.page = 1
  loadList()
}

function handleReset() {
  queryParams.action = ''
  queryParams.resource_type = ''
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

onMounted(async () => {
  await loadUsers()
  await loadList()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">审计日志</h2>

    <el-card class="filter-card" shadow="never">
      <el-form :inline="true">
        <el-form-item label="操作类型">
          <el-select
            v-model="queryParams.action"
            placeholder="全部"
            clearable
            filterable
            style="width: 200px"
          >
            <el-option v-for="a in actionOptions" :key="a" :label="a" :value="a" />
          </el-select>
        </el-form-item>
        <el-form-item label="资源类型">
          <el-select
            v-model="queryParams.resource_type"
            placeholder="全部"
            clearable
            filterable
            style="width: 200px"
          >
            <el-option v-for="r in resourceTypeOptions" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table :data="list" v-loading="loading" border stripe>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="用户" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ userName(row.user_id) }}</template>
        </el-table-column>
        <el-table-column prop="action" label="操作" width="180" show-overflow-tooltip />
        <el-table-column prop="resource_type" label="资源类型" width="130" show-overflow-tooltip />
        <el-table-column label="资源 ID" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono-id">{{ row.resource_id || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ detailsText(row.details) }}</template>
        </el-table-column>
        <el-table-column label="IP" width="140">
          <template #default="{ row }">{{ row.ip_address || '—' }}</template>
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
  </div>
</template>

<style scoped>
.mono-id {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  color: #909399;
}
</style>
