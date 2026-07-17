<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  getModels,
  createModel,
  updateModel,
  deleteModel,
  getRules,
  createRule,
  updateRule,
} from '@/api/llmConfig'
import { reviewTypeLabel } from '@/utils/status'
import type {
  LLMModel,
  LLMModelCreate,
  LLMModelUpdate,
  ReviewRule,
  ReviewRuleCreate,
  ReviewRuleUpdate,
  ReviewType,
} from '@/types'

// ======================== LLM 模型 ========================
const models = ref<LLMModel[]>([])
const modelLoading = ref(false)

const modelDialogVisible = ref(false)
const modelDialogMode = ref<'create' | 'edit'>('create')
const modelFormRef = ref<FormInstance>()
const modelSubmitting = ref(false)
const modelForm = reactive<LLMModelCreate & { id?: string; is_active?: boolean }>({
  name: '',
  api_base: '',
  api_key: '',
  model_name: '',
  priority: 1,
  is_active: true,
})
const modelRules: FormRules = {
  name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  api_base: [{ required: true, message: '请输入 API 地址', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
  model_name: [{ required: true, message: '请输入模型标识', trigger: 'blur' }],
}

const modelOptions = computed(() =>
  models.value.map((m) => ({ label: m.name, value: m.id })),
)

function modelName(id: string | null | undefined): string {
  if (!id) return '—'
  return models.value.find((m) => m.id === id)?.name || id.slice(0, 8) + '…'
}

async function loadModels() {
  modelLoading.value = true
  try {
    models.value = await getModels()
  } catch {
    // 错误已统一提示
  } finally {
    modelLoading.value = false
  }
}

function openModelCreate() {
  modelDialogMode.value = 'create'
  modelForm.id = undefined
  modelForm.name = ''
  modelForm.api_base = ''
  modelForm.api_key = ''
  modelForm.model_name = ''
  modelForm.priority = 1
  modelForm.is_active = true
  modelDialogVisible.value = true
}

function openModelEdit(row: LLMModel) {
  modelDialogMode.value = 'edit'
  modelForm.id = row.id
  modelForm.name = row.name
  modelForm.api_base = row.api_base
  modelForm.api_key = row.api_key
  modelForm.model_name = row.model_name
  modelForm.priority = row.priority
  modelForm.is_active = row.is_active
  modelDialogVisible.value = true
}

async function handleModelSubmit() {
  if (!modelFormRef.value) return
  await modelFormRef.value.validate(async (valid) => {
    if (!valid) return
    modelSubmitting.value = true
    try {
      if (modelDialogMode.value === 'create') {
        await createModel({
          name: modelForm.name,
          api_base: modelForm.api_base,
          api_key: modelForm.api_key,
          model_name: modelForm.model_name,
          priority: modelForm.priority,
          is_active: modelForm.is_active,
        })
        ElMessage.success('模型创建成功')
      } else {
        const payload: LLMModelUpdate = {
          name: modelForm.name,
          api_base: modelForm.api_base,
          api_key: modelForm.api_key,
          model_name: modelForm.model_name,
          priority: modelForm.priority,
          is_active: modelForm.is_active,
        }
        await updateModel(modelForm.id!, payload)
        ElMessage.success('模型更新成功')
      }
      modelDialogVisible.value = false
      await loadModels()
    } catch {
      // 错误已统一提示
    } finally {
      modelSubmitting.value = false
    }
  })
}

async function handleModelDelete(row: LLMModel) {
  try {
    await ElMessageBox.confirm(`确定要禁用模型「${row.name}」吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteModel(row.id)
    ElMessage.success('已禁用')
    await loadModels()
  } catch {
    // 取消或错误
  }
}

// ======================== 评审规则 ========================
const rules = ref<ReviewRule[]>([])
const ruleLoading = ref(false)

const reviewTypeOptions: { label: string; value: ReviewType }[] = [
  { label: '代码评审', value: 'code_review' },
  { label: '测试报告评审', value: 'test_report_review' },
  { label: '专家报告评审', value: 'expert_report_review' },
]

const ruleDialogVisible = ref(false)
const ruleDialogMode = ref<'create' | 'edit'>('create')
const ruleFormRef = ref<FormInstance>()
const ruleSubmitting = ref(false)
const dimensionJsonText = ref('{}')
const promptText = ref('')

const ruleForm = reactive<ReviewRuleCreate & { id?: string }>({
  review_type: 'code_review',
  llm_model_id: '',
  fallback_model_id: null,
  prompt_template: '',
  pass_threshold: 60,
  dimension_thresholds: {},
  is_active: true,
})
const ruleRules: FormRules = {
  review_type: [{ required: true, message: '请选择评审类型', trigger: 'change' }],
  llm_model_id: [{ required: true, message: '请选择主模型', trigger: 'change' }],
  pass_threshold: [{ required: true, message: '请输入通过阈值', trigger: 'blur' }],
}

async function loadRules() {
  ruleLoading.value = true
  try {
    rules.value = await getRules()
  } catch {
    // 错误已统一提示
  } finally {
    ruleLoading.value = false
  }
}

function openRuleCreate() {
  ruleDialogMode.value = 'create'
  ruleForm.id = undefined
  ruleForm.review_type = 'code_review'
  ruleForm.llm_model_id = models.value[0]?.id || ''
  ruleForm.fallback_model_id = null
  ruleForm.prompt_template = ''
  ruleForm.pass_threshold = 60
  ruleForm.dimension_thresholds = {}
  ruleForm.is_active = true
  dimensionJsonText.value = '{}'
  promptText.value = ''
  ruleDialogVisible.value = true
}

function openRuleEdit(row: ReviewRule) {
  ruleDialogMode.value = 'edit'
  ruleForm.id = row.id
  ruleForm.review_type = row.review_type
  ruleForm.llm_model_id = row.llm_model_id
  ruleForm.fallback_model_id = row.fallback_model_id
  ruleForm.prompt_template = row.prompt_template
  ruleForm.pass_threshold = row.pass_threshold
  ruleForm.dimension_thresholds = row.dimension_thresholds || {}
  ruleForm.is_active = row.is_active
  dimensionJsonText.value = JSON.stringify(row.dimension_thresholds || {}, null, 2)
  promptText.value = row.prompt_template || ''
  ruleDialogVisible.value = true
}

async function handleRuleSubmit() {
  if (!ruleFormRef.value) return
  await ruleFormRef.value.validate(async (valid) => {
    if (!valid) return
    // 解析维度阈值 JSON
    let dimThresholds: Record<string, unknown> = {}
    try {
      dimThresholds = JSON.parse(dimensionJsonText.value || '{}')
    } catch {
      ElMessage.error('维度阈值 JSON 格式不正确')
      return
    }
    ruleSubmitting.value = true
    try {
      const prompt = promptText.value || ruleForm.prompt_template
      if (ruleDialogMode.value === 'create') {
        await createRule({
          review_type: ruleForm.review_type,
          llm_model_id: ruleForm.llm_model_id,
          fallback_model_id: ruleForm.fallback_model_id || undefined,
          prompt_template: prompt,
          pass_threshold: ruleForm.pass_threshold,
          dimension_thresholds: dimThresholds,
          is_active: ruleForm.is_active,
        })
        ElMessage.success('规则创建成功')
      } else {
        const payload: ReviewRuleUpdate = {
          llm_model_id: ruleForm.llm_model_id,
          fallback_model_id: ruleForm.fallback_model_id || undefined,
          prompt_template: prompt,
          pass_threshold: ruleForm.pass_threshold,
          dimension_thresholds: dimThresholds,
          is_active: ruleForm.is_active,
        }
        await updateRule(ruleForm.id!, payload)
        ElMessage.success('规则更新成功')
      }
      ruleDialogVisible.value = false
      await loadRules()
    } catch {
      // 错误已统一提示
    } finally {
      ruleSubmitting.value = false
    }
  })
}

function truncate(text: string | null | undefined, len = 40): string {
  if (!text) return '—'
  return text.length > len ? text.slice(0, len) + '…' : text
}

onMounted(async () => {
  await loadModels()
  await loadRules()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">LLM 配置</h2>

    <!-- LLM 模型管理 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>LLM 模型管理</span>
          <el-button type="primary" size="small" @click="openModelCreate">
            <el-icon><Plus /></el-icon>新增模型
          </el-button>
        </div>
      </template>
      <el-table :data="models" v-loading="modelLoading" border stripe>
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="api_base" label="API 地址" min-width="200" show-overflow-tooltip />
        <el-table-column prop="model_name" label="模型标识" width="160" show-overflow-tooltip />
        <el-table-column prop="priority" label="优先级" width="90" align="center" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link @click="openModelEdit(row)">编辑</el-button>
            <el-button type="danger" link @click="handleModelDelete(row)">禁用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 评审规则管理 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>评审规则管理</span>
          <el-button type="primary" size="small" @click="openRuleCreate">
            <el-icon><Plus /></el-icon>新增规则
          </el-button>
        </div>
      </template>
      <el-table :data="rules" v-loading="ruleLoading" border stripe>
        <el-table-column label="评审类型" width="140">
          <template #default="{ row }">{{ reviewTypeLabel(row.review_type) }}</template>
        </el-table-column>
        <el-table-column label="主模型" width="150">
          <template #default="{ row }">{{ modelName(row.llm_model_id) }}</template>
        </el-table-column>
        <el-table-column label="备用模型" width="150">
          <template #default="{ row }">{{ modelName(row.fallback_model_id) }}</template>
        </el-table-column>
        <el-table-column prop="pass_threshold" label="通过阈值" width="100" align="center" />
        <el-table-column label="Prompt 模板" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ truncate(row.prompt_template, 50) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link @click="openRuleEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 模型对话框 -->
    <el-dialog
      v-model="modelDialogVisible"
      :title="modelDialogMode === 'create' ? '新增模型' : '编辑模型'"
      width="520px"
    >
      <el-form ref="modelFormRef" :model="modelForm" :rules="modelRules" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="modelForm.name" placeholder="模型显示名称" />
        </el-form-item>
        <el-form-item label="API 地址" prop="api_base">
          <el-input v-model="modelForm.api_base" placeholder="https://api.example.com/v1" />
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="modelForm.api_key" show-password placeholder="sk-..." />
        </el-form-item>
        <el-form-item label="模型标识" prop="model_name">
          <el-input v-model="modelForm.model_name" placeholder="如 gpt-4o" />
        </el-form-item>
        <el-form-item label="优先级" prop="priority">
          <el-input-number v-model="modelForm.priority" :min="1" :max="99" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="modelForm.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="modelSubmitting" @click="handleModelSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 规则对话框 -->
    <el-dialog
      v-model="ruleDialogVisible"
      :title="ruleDialogMode === 'create' ? '新增评审规则' : '编辑评审规则'"
      width="640px"
    >
      <el-form ref="ruleFormRef" :model="ruleForm" :rules="ruleRules" label-width="110px">
        <el-form-item label="评审类型" prop="review_type">
          <el-select
            v-model="ruleForm.review_type"
            :disabled="ruleDialogMode === 'edit'"
            style="width: 100%"
          >
            <el-option
              v-for="opt in reviewTypeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="主模型" prop="llm_model_id">
          <el-select v-model="ruleForm.llm_model_id" filterable style="width: 100%">
            <el-option
              v-for="opt in modelOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="备用模型">
          <el-select
            v-model="ruleForm.fallback_model_id"
            filterable
            clearable
            placeholder="可选"
            style="width: 100%"
          >
            <el-option
              v-for="opt in modelOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="通过阈值" prop="pass_threshold">
          <el-input-number v-model="ruleForm.pass_threshold" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="维度阈值 JSON">
          <el-input
            v-model="dimensionJsonText"
            type="textarea"
            :rows="4"
            placeholder='{"completeness": 60, "correctness": 70}'
          />
        </el-form-item>
        <el-form-item label="Prompt 模板">
          <el-input
            v-model="promptText"
            type="textarea"
            :rows="6"
            placeholder="请输入 Prompt 模板，可使用 {{变量}} 占位符"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="ruleForm.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="ruleSubmitting" @click="handleRuleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
