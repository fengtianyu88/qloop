<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Download, Upload, Setting } from '@element-plus/icons-vue'
import { getOrgTree, createOrg, updateOrg, deleteOrg, createAdminScope, getAdminScopes, deleteAdminScope, getOrgAdminScopes, getOrgTypes, createOrgType, deleteOrgType } from '@/api/organizations'
import { getUsers } from '@/api/users'
import { downloadOrganizationsTemplate, importOrganizations } from '@/api/imports'
import { useAuthStore } from '@/stores/auth'
import type {
  AdminScope,
  OrgTreeNode,
  OrgTypeItem,
  OrgUnitCreate,
  User,
} from '@/types'

const authStore = useAuthStore()

const treeData = ref<OrgTreeNode[]>([])
const loading = ref(false)
const treeProps = { label: 'name', children: 'children' }

// v1.5.2: 组织类型动态列表(替代硬编码)
const orgTypes = ref<OrgTypeItem[]>([])

// 组织类型 code -> name 的映射
const orgTypeLabel = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  orgTypes.value.forEach((t) => {
    map[t.code] = t.name
  })
  return map
})

// 扁平化组织单元（用于管理范围选择）
const flatOrgs = computed<{ id: string; name: string }[]>(() => {
  const result: { id: string; name: string }[] = []
  function walk(nodes: OrgTreeNode[]) {
    nodes.forEach((n) => {
      result.push({ id: n.id, name: n.name })
      if (n.children?.length) walk(n.children)
    })
  }
  walk(treeData.value)
  return result
})

async function loadTree() {
  loading.value = true
  try {
    treeData.value = await getOrgTree()
  } catch {
    // 错误已统一提示
  } finally {
    loading.value = false
  }
}

// v1.5.2: 加载组织类型列表
async function loadOrgTypes() {
  try {
    orgTypes.value = await getOrgTypes()
  } catch {
    orgTypes.value = []
  }
}

// v1.5.2: 组织类型管理对话框
const orgTypeDialogVisible = ref(false)
const orgTypeList = ref<OrgTypeItem[]>([])
const orgTypeLoading = ref(false)
const newOrgType = reactive({ code: '', name: '' })
const orgTypeSubmitting = ref(false)

async function openOrgTypeDialog() {
  orgTypeDialogVisible.value = true
  await refreshOrgTypeList()
}

async function refreshOrgTypeList() {
  orgTypeLoading.value = true
  try {
    orgTypeList.value = await getOrgTypes()
    orgTypes.value = orgTypeList.value // 同步更新下拉选项
  } catch {
    orgTypeList.value = []
  } finally {
    orgTypeLoading.value = false
  }
}

async function handleCreateOrgType() {
  if (!newOrgType.code.trim() || !newOrgType.name.trim()) {
    ElMessage.warning('请填写代码和名称')
    return
  }
  orgTypeSubmitting.value = true
  try {
    await createOrgType({
      code: newOrgType.code.trim(),
      name: newOrgType.name.trim(),
    })
    ElMessage.success('组织类型创建成功')
    newOrgType.code = ''
    newOrgType.name = ''
    await refreshOrgTypeList()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '创建失败'
    ElMessage.error(msg)
  } finally {
    orgTypeSubmitting.value = false
  }
}

async function handleDeleteOrgType(typeId: string, typeName: string) {
  try {
    await ElMessageBox.confirm(
      `确认删除组织类型「${typeName}」吗?`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteOrgType(typeId)
    ElMessage.success('组织类型已删除')
    await refreshOrgTypeList()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '删除失败'
    ElMessage.error(msg)
  }
}

// 格式化日期
function formatDate(dateStr: string): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hours = String(d.getHours()).padStart(2, '0')
  const mins = String(d.getMinutes()).padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day} ${hours}:${mins}`
}

async function handleDownloadTemplate() {
  try {
    const blob = await downloadOrganizationsTemplate()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'organizations_template.xlsx'
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
    const res = await importOrganizations(file)
    ElMessage.success(`导入完成：成功 ${res.success} 个，失败 ${res.failed} 个`)
    if (res.errors.length > 0) {
      ElMessageBox.alert(res.errors.slice(0, 5).join('\n'), '失败详情', { type: 'warning' })
    }
    await loadTree()  // 刷新组织树
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    target.value = ''  // 清空,允许重复选择同一文件
  }
}

// ------------------------- 新增组织 -------------------------
const orgDialogVisible = ref(false)
const orgFormRef = ref<FormInstance>()
const orgForm = reactive<OrgUnitCreate & { _parentName?: string }>({
  name: '',
  org_type: 'department',
  parent_id: null,
  description: '',
})
const orgRules: FormRules<OrgUnitCreate> = {
  name: [{ required: true, message: '请输入组织名称', trigger: 'blur' }],
}
const orgSubmitting = ref(false)

function openRootOrgDialog() {
  orgForm.name = ''
  orgForm.org_type = 'department'
  orgForm.parent_id = null
  orgForm.description = ''
  orgForm._parentName = undefined
  orgDialogVisible.value = true
}

function openChildOrgDialog(node: OrgTreeNode) {
  orgForm.name = ''
  orgForm.org_type = 'department'
  orgForm.parent_id = node.id
  orgForm.description = ''
  orgForm._parentName = node.name
  orgDialogVisible.value = true
}

// 功能3: 表格行操作 - 添加子节点 / 编辑 / 删除
function handleAddChild(row: OrgTreeNode) {
  openChildOrgDialog(row)
}

// 编辑组织单元
const editDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive<{
  id: string
  name: string
  org_type: string
  description: string
}>({
  id: '',
  name: '',
  org_type: 'department',
  description: '',
})
const editRules: FormRules<{ name: string }> = {
  name: [{ required: true, message: '请输入组织名称', trigger: 'blur' }],
}
const editSubmitting = ref(false)

function handleEdit(row: OrgTreeNode) {
  editForm.id = row.id
  editForm.name = row.name
  editForm.org_type = row.org_type
  editForm.description = row.description || ''
  editDialogVisible.value = true
}

async function handleEditSubmit() {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    editSubmitting.value = true
    try {
      await updateOrg(editForm.id, {
        name: editForm.name,
        org_type: editForm.org_type,
        description: editForm.description || undefined,
      })
      ElMessage.success('组织更新成功')
      editDialogVisible.value = false
      await loadTree()
    } catch {
      // 错误已统一提示
    } finally {
      editSubmitting.value = false
    }
  })
}

async function handleDelete(row: OrgTreeNode) {
  try {
    await ElMessageBox.confirm(
      `确认删除组织单元「${row.name}」吗?若存在子节点或关联用户将拒绝删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return  // 用户取消
  }
  try {
    await deleteOrg(row.id)
    ElMessage.success('组织已删除')
    await loadTree()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '删除失败'
    ElMessage.error(msg)
  }
}

async function handleCreateOrg() {
  if (!orgFormRef.value) return
  await orgFormRef.value.validate(async (valid) => {
    if (!valid) return
    orgSubmitting.value = true
    try {
      await createOrg({
        name: orgForm.name,
        org_type: orgForm.org_type,
        parent_id: orgForm.parent_id || undefined,
        description: orgForm.description || undefined,
      })
      ElMessage.success('组织创建成功')
      orgDialogVisible.value = false
      await loadTree()
    } catch {
      // 错误已统一提示
    } finally {
      orgSubmitting.value = false
    }
  })
}

// ------------------------- 管理员管理范围 -------------------------
const userList = ref<User[]>([])
const selectedUserId = ref('')
const userScopes = ref<AdminScope[]>([])
const scopeOrgId = ref('')
const scopeLoading = ref(false)
const scopeSubmitting = ref(false)

async function loadUsers() {
  try {
    const res = await getUsers({ page: 1, page_size: 200 })
    userList.value = res.items
  } catch {
    userList.value = []
  }
}

async function loadUserScopes() {
  if (!selectedUserId.value) {
    userScopes.value = []
    return
  }
  scopeLoading.value = true
  try {
    userScopes.value = await getAdminScopes(selectedUserId.value)
  } catch {
    userScopes.value = []
  } finally {
    scopeLoading.value = false
  }
}

function handleUserChange() {
  loadUserScopes()
}

function orgName(id: string): string {
  return flatOrgs.value.find((o) => o.id === id)?.name || id.slice(0, 8) + '…'
}

async function handleAddScope() {
  if (!selectedUserId.value) {
    ElMessage.warning('请先选择用户')
    return
  }
  if (!scopeOrgId.value) {
    ElMessage.warning('请选择组织单元')
    return
  }
  scopeSubmitting.value = true
  try {
    await createAdminScope({
      user_id: selectedUserId.value,
      org_unit_id: scopeOrgId.value,
    })
    ElMessage.success('管理范围添加成功')
    scopeOrgId.value = ''
    await loadUserScopes()
    await loadTree() // 立即刷新架构（管理者姓名立即更新）
  } catch {
    // 错误已统一提示
  } finally {
    scopeSubmitting.value = false
  }
}

// ------------------------- 管理者管理对话框（点击管理者姓名打开）-------------------------
const managerDialogVisible = ref(false)
const managerDialogOrgName = ref('')
const managerDialogOrgId = ref('')
const managerList = ref<Array<{ id: string; user_id: string; full_name: string; username: string }>>([])
const managerLoading = ref(false)
const newManagerUserId = ref('')

async function openManagerDialog(node: OrgTreeNode) {
  managerDialogOrgName.value = node.name
  managerDialogOrgId.value = node.id
  newManagerUserId.value = ''
  managerDialogVisible.value = true
  await loadManagers(node.id)
}

async function loadManagers(orgId: string) {
  managerLoading.value = true
  try {
    managerList.value = await getOrgAdminScopes(orgId)
  } catch {
    managerList.value = []
  } finally {
    managerLoading.value = false
  }
}

async function handleAddManager() {
  if (!newManagerUserId.value) {
    ElMessage.warning('请先选择用户')
    return
  }
  try {
    await createAdminScope({
      user_id: newManagerUserId.value,
      org_unit_id: managerDialogOrgId.value,
    })
    ElMessage.success('管理者添加成功')
    newManagerUserId.value = ''
    await loadManagers(managerDialogOrgId.value)
    await loadTree() // 立即刷新架构
  } catch {
    // 错误已统一提示
  }
}

async function handleRemoveManager(scopeId: string, fullName: string) {
  try {
    await ElMessageBox.confirm(
      `确认移除「${fullName}」在该组织单元的管理员身份？`,
      '确认移除',
      { type: 'warning' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await deleteAdminScope(scopeId)
    ElMessage.success('管理者移除成功')
    await loadManagers(managerDialogOrgId.value)
    await loadTree() // 立即刷新架构
  } catch {
    // 错误已统一提示
  }
}

onMounted(async () => {
  await loadTree()
  await loadUsers()
  await loadOrgTypes()
})
</script>

<template>
  <div class="page-container">
    <div class="list-header">
      <h2 class="page-title">组织管理</h2>
      <div v-if="authStore.isAdmin" class="list-header-actions">
        <el-button size="default" @click="openOrgTypeDialog">
          <el-icon><Setting /></el-icon>组织类型
        </el-button>
        <el-button size="default" @click="handleDownloadTemplate">
          <el-icon><Download /></el-icon>下载模板
        </el-button>
        <el-button size="default" @click="handleImportClick">
          <el-icon><Upload /></el-icon>批量导入
        </el-button>
        <input ref="importInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleImportFile" />
      </div>
    </div>

    <el-row :gutter="20">
      <!-- 组织树 -->
      <el-col :span="14">
        <el-card class="table-card" shadow="never" v-loading="loading">
          <template #header>
            <div class="card-header">
              <span>组织架构</span>
              <el-button type="primary" size="small" @click="openRootOrgDialog">
                <el-icon><Plus /></el-icon>新增根组织
              </el-button>
            </div>
          </template>
          <el-empty v-if="!treeData.length" description="暂无组织数据" />
          <!-- 功能3: 树形表格展示组织架构 -->
          <el-table
            v-else
            :data="treeData"
            row-key="id"
            :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
            border
            default-expand-all
          >
            <el-table-column prop="name" label="组织名称" min-width="180" show-overflow-tooltip />
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" type="info" effect="plain">
                  {{ orgTypeLabel[row.org_type ] || row.org_type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="管理者" min-width="180">
              <template #default="{ row }">
                <template v-if="row.manager_names && row.manager_names.length">
                  <el-tag
                    v-for="m in row.manager_names"
                    :key="m"
                    size="small"
                    type="success"
                    effect="dark"
                    class="manager-tag"
                    @click.stop="openManagerDialog(row)"
                  >
                    <el-icon style="margin-right: 2px"><User /></el-icon>{{ m }}
                  </el-tag>
                </template>
                <el-button
                  type="success"
                  link
                  size="small"
                  class="manage-managers-btn"
                  @click.stop="openManagerDialog(row)"
                >
                  管理者
                </el-button>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.description || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="handleAddChild(row)">添加子节点</el-button>
                <el-button size="small" @click="handleEdit(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 管理员管理范围 -->
      <el-col :span="10">
        <el-card class="table-card" shadow="never">
          <template #header><span>管理员管理范围配置</span></template>
          <el-form label-width="80px">
            <el-form-item label="用户">
              <el-select
                v-model="selectedUserId"
                placeholder="选择用户"
                filterable
                style="width: 100%"
                @change="handleUserChange"
              >
                <el-option
                  v-for="u in userList"
                  :key="u.id"
                  :label="`${u.full_name} (${u.username})`"
                  :value="u.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="组织单元">
              <el-select v-model="scopeOrgId" placeholder="选择组织单元" filterable style="width: 100%">
                <el-option
                  v-for="o in flatOrgs"
                  :key="o.id"
                  :label="o.name"
                  :value="o.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="scopeSubmitting"
                :disabled="!selectedUserId"
                @click="handleAddScope"
              >
                添加管理范围
              </el-button>
            </el-form-item>
          </el-form>

          <el-divider />

          <div v-loading="scopeLoading">
            <div class="scope-title">当前管理范围：</div>
            <el-empty v-if="!userScopes.length" description="暂无管理范围" :image-size="60" />
            <el-tag
              v-for="s in userScopes"
              :key="s.id"
              class="scope-tag"
            >
              {{ orgName(s.org_unit_id) }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 管理者管理对话框 -->
    <el-dialog
      v-model="managerDialogVisible"
      :title="'管理者管理 - ' + managerDialogOrgName"
      width="560px"
    >
      <div v-loading="managerLoading">
        <div class="manager-section-title">当前管理者：</div>
        <el-empty v-if="!managerList.length" description="暂无管理者" :image-size="60" />
        <div v-else class="manager-list">
          <el-tag
            v-for="m in managerList"
            :key="m.id"
            class="manager-item"
            closable
            type="success"
            effect="dark"
            @close="handleRemoveManager(m.id, m.full_name)"
          >
            <el-icon style="margin-right: 2px"><User /></el-icon>
            {{ m.full_name }} ({{ m.username }})
          </el-tag>
        </div>

        <el-divider />

        <div class="manager-section-title">添加新管理者：</div>
        <el-select
          v-model="newManagerUserId"
          placeholder="选择用户"
          filterable
          style="width: 100%"
        >
          <el-option
            v-for="u in userList"
            :key="u.id"
            :label="`${u.full_name} (${u.username})`"
            :value="u.id"
          />
        </el-select>
        <div style="text-align: right; margin-top: 12px">
          <el-button
            type="primary"
            :disabled="!newManagerUserId"
            @click="handleAddManager"
          >
            添加管理者
          </el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 新增组织对话框 -->
    <el-dialog
      v-model="orgDialogVisible"
      :title="orgForm.parent_id ? '新增子组织' : '新增根组织'"
      width="480px"
    >
      <el-form ref="orgFormRef" :model="orgForm" :rules="orgRules" label-width="90px">
        <el-form-item v-if="orgForm._parentName" label="上级组织">
          <el-input :model-value="orgForm._parentName" disabled />
        </el-form-item>
        <el-form-item label="组织名称" prop="name">
          <el-input v-model="orgForm.name" placeholder="请输入组织名称" />
        </el-form-item>
        <el-form-item label="组织类型" prop="org_type">
          <el-select v-model="orgForm.org_type" style="width: 100%" placeholder="请选择组织类型">
            <el-option
              v-for="t in orgTypes"
              :key="t.code"
              :label="t.name"
              :value="t.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="orgForm.description" type="textarea" :rows="3" placeholder="描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="orgDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="orgSubmitting" @click="handleCreateOrg">确定</el-button>
      </template>
    </el-dialog>

    <!-- 功能3: 编辑组织对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑组织单元" width="480px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
        <el-form-item label="组织名称" prop="name">
          <el-input v-model="editForm.name" placeholder="请输入组织名称" />
        </el-form-item>
        <el-form-item label="组织类型" prop="org_type">
          <el-select v-model="editForm.org_type" style="width: 100%" placeholder="请选择组织类型">
            <el-option
              v-for="t in orgTypes"
              :key="t.code"
              :label="t.name"
              :value="t.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSubmitting" @click="handleEditSubmit">保存</el-button>
      </template>
    </el-dialog>

    <!-- v1.5.2: 组织类型管理对话框 -->
    <el-dialog v-model="orgTypeDialogVisible" title="组织类型管理" width="720px">
      <div v-loading="orgTypeLoading">
        <el-table :data="orgTypeList" border style="width: 100%" size="small">
          <el-table-column prop="name" label="名称" min-width="100" />
          <el-table-column prop="code" label="代码" width="120" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.is_system" size="small" type="info">系统</el-tag>
              <el-tag v-else size="small" type="success">自定义</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建人" width="120">
            <template #default="{ row }">
              {{ row.created_by_name || '系统' }}
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="160">
            <template #default="{ row }">
              {{ formatDate(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="!row.is_system && authStore.isSuperAdmin"
                size="small"
                type="danger"
                link
                @click="handleDeleteOrgType(row.id, row.name)"
              >
                删除
              </el-button>
              <span v-else style="color: #c0c4cc; font-size: 12px">—</span>
            </template>
          </el-table-column>
        </el-table>

        <el-divider />

        <div style="font-size: 14px; font-weight: 500; margin-bottom: 12px">新增组织类型：</div>
        <el-form :inline="true" label-width="60px">
          <el-form-item label="名称">
            <el-input
              v-model="newOrgType.name"
              placeholder="如：中心、委员会"
              style="width: 180px"
            />
          </el-form-item>
          <el-form-item label="代码">
            <el-input
              v-model="newOrgType.code"
              placeholder="如：center、committee"
              style="width: 180px"
            />
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              :loading="orgTypeSubmitting"
              :disabled="!newOrgType.code.trim() || !newOrgType.name.trim()"
              @click="handleCreateOrgType"
            >
              添加
            </el-button>
          </el-form-item>
        </el-form>
        <div style="color: #909399; font-size: 12px; margin-top: 4px">
          代码为英文小写字母，创建后不可修改。系统预设类型（部门/科室/小组）不可删除。
        </div>
      </div>
      <template #footer>
        <el-button @click="orgTypeDialogVisible = false">关闭</el-button>
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

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.tree-node-name {
  font-size: 14px;
}

.tree-node :deep(.el-tag) {
  margin-left: 0;
}

.scope-title {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.scope-tag {
  margin: 0 8px 8px 0;
}

.manager-tag {
  cursor: pointer;
}

.manage-managers-btn {
  margin-left: 4px;
}

.manager-section-title {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
  font-weight: 500;
}

.manager-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.manager-item {
  cursor: default;
}
</style>
