<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  getModels,
  createModel,
  updateModel,
  disableModel,
  enableModel,
  deleteModel,
  testModel,
  testModelInline,
  getRules,
  createRule,
  updateRule,
  deleteRule,
} from '@/api/llmConfig'
import { reviewTypeLabel } from '@/utils/status'
import type {
  LLMModel,
  LLMProtocol,
  LLMModelCreate,
  LLMModelUpdate,
  LLMTestResult,
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
  protocol: 'openai',
  api_base: '',
  api_key: '',
  model_name: '',
  priority: 1,
  is_active: true,
})
const protocolOptions: { label: string; value: string }[] = [
  { label: 'OpenAI 兼容 (/chat/completions)', value: 'openai' },
  { label: 'Anthropic 原生 (/v1/messages)', value: 'anthropic' },
]


// 预设模型模板 - 一键填充常见模型配置
const presetModels: { label: string; name: string; protocol: LLMProtocol; api_base: string; model_name: string; note?: string }[] = [
  {
    label: 'MiniMax-M3 (OpenAI)',
    name: 'MiniMax-M3',
    protocol: 'openai',
    api_base: 'https://api.minimaxi.com/v1',
    model_name: 'MiniMax-M3',
  },
  {
    label: 'MiniMax-M2.7 (OpenAI)',
    name: 'MiniMax-M2.7',
    protocol: 'openai',
    api_base: 'https://api.minimaxi.com/v1',
    model_name: 'MiniMax-Text-01',
  },
  {
    label: 'GLM-5.2 (OpenAI)',
    name: 'GLM-5.2',
    protocol: 'openai',
    api_base: 'https://open.bigmodel.cn/api/paas/v4',
    model_name: 'glm-5-plus',
  },
  {
    label: 'DeepSeek-V4-flash (OpenAI)',
    name: 'DeepSeek-V4-flash',
    protocol: 'openai',
    api_base: 'https://api.deepseek.com/v1',
    model_name: 'deepseek-chat',
  },
  {
    label: 'Claude Sonnet 4.5 (Anthropic)',
    name: 'Claude Sonnet 4.5',
    protocol: 'anthropic',
    api_base: 'https://api.anthropic.com',
    model_name: 'claude-sonnet-4-5-20250929',
  },
  {
    label: 'Claude Opus 4 (Anthropic)',
    name: 'Claude Opus 4',
    protocol: 'anthropic',
    api_base: 'https://api.anthropic.com',
    model_name: 'claude-opus-4-20250514',
  },
  {
    label: 'OpenAI GPT-4o (OpenAI)',
    name: 'GPT-4o',
    protocol: 'openai',
    api_base: 'https://api.openai.com/v1',
    model_name: 'gpt-4o',
  },
  {
    label: '本地 Ollama (OpenAI 兼容)',
    name: 'Ollama (本地)',
    protocol: 'openai',
    api_base: 'http://localhost:11434/v1',
    model_name: 'qwen2.5:14b',
  },
]

function applyPreset(preset: { name: string; protocol: LLMProtocol; api_base: string; model_name: string }) {
  modelForm.name = preset.name
  modelForm.protocol = preset.protocol
  modelForm.api_base = preset.api_base
  modelForm.model_name = preset.model_name
  // 不覆盖 api_key，让用户自己填
}

const modelRules: FormRules = {
  name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  protocol: [{ required: true, message: '请选择接口协议', trigger: 'change' }],
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
  modelForm.protocol = 'openai'
  modelForm.api_base = ''
  modelForm.api_key = ''
  modelForm.model_name = ''
  modelForm.priority = 1
  modelForm.is_active = true
  dialogTestResult.value = null  // 重置测试结果,显示蓝色说明提示框
  modelDialogVisible.value = true
}

function openModelEdit(row: LLMModel) {
  modelDialogMode.value = 'edit'
  modelForm.id = row.id
  modelForm.name = row.name
  modelForm.protocol = row.protocol
  modelForm.api_base = row.api_base
  modelForm.api_key = row.api_key
  modelForm.model_name = row.model_name
  modelForm.priority = row.priority
  modelForm.is_active = row.is_active
  dialogTestResult.value = null  // 重置测试结果,显示蓝色说明提示框
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
          protocol: modelForm.protocol,
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
          protocol: modelForm.protocol,
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

async function handleModelDisable(row: LLMModel) {
  try {
    await ElMessageBox.confirm(
      `确认禁用模型「${row.name}」吗？禁用后历史评审记录仍可追溯，且可随时重新启用。`,
      '禁用确认',
      { type: 'warning' },
    )
    await disableModel(row.id)
    ElMessage.success('模型已禁用')
    await loadModels()
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error(err?.response?.data?.detail || '禁用失败')
    }
  }
}

async function handleModelEnable(row: LLMModel) {
  try {
    await enableModel(row.id)
    ElMessage.success('模型已启用')
    await loadModels()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '启用失败')
  }
}

async function handleModelDelete(row: LLMModel) {
  try {
    await ElMessageBox.confirm(
      `确认「物理删除」模型「${row.name}」吗？\n\n` +
      '物理删除不可恢复。若该模型被评审规则引用将拒绝删除。\n' +
      '历史评审记录不受影响（model_used 为字符串字段，非外键）。',
      '物理删除确认',
      { type: 'error', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await deleteModel(row.id)
    ElMessage.success('模型已物理删除')
    await loadModels()
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error(err?.response?.data?.detail || '删除失败')
    }
  }
}

async function handleRuleDelete(row: ReviewRule) {
  try {
    await ElMessageBox.confirm(
      `确认「物理删除」此评审规则吗？\n类型: ${reviewTypeLabel(row.review_type)}\n\n` +
      '物理删除不可恢复。历史评审记录不受影响。',
      '删除评审规则',
      { type: 'error', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await deleteRule(row.id)
    ElMessage.success('评审规则已删除')
    await loadRules()
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error(err?.response?.data?.detail || '删除失败')
    }
  }
}

// ======================== 模型连通性测试 ========================
const testingIds = ref<Set<string>>(new Set())
const dialogTesting = ref(false)
const dialogTestResult = ref<LLMTestResult | null>(null)

async function handleTestModel(row: LLMModel) {
  testingIds.value.add(row.id)
  try {
    const result = await testModel(row.id)
    if (result.success) {
      ElMessage.success(`「${row.name}」连通正常（${result.latency_ms ?? 0}ms）`)
    } else {
      ElMessage.error(`「${row.name}」测试失败：${result.message}`)
    }
  } catch {
    // 错误已统一提示
  } finally {
    testingIds.value.delete(row.id)
  }
}

async function handleTestModelInline() {
  // 在弹窗中点测试：用当前表单内容（不保存）调用 test-inline 端点
  if (!modelForm.api_base || !modelForm.api_key || !modelForm.model_name) {
    ElMessage.warning('请先填写 API 地址、API Key、模型标识')
    return
  }
  dialogTesting.value = true
  dialogTestResult.value = null
  try {
    const result = await testModelInline({
      name: modelForm.name || '(unsaved)',
      protocol: modelForm.protocol,
      api_base: modelForm.api_base,
      api_key: modelForm.api_key,
      model_name: modelForm.model_name,
      is_active: true,
      priority: modelForm.priority,
    })
    dialogTestResult.value = result
    if (result.success) {
      ElMessage.success(`连通正常（${result.latency_ms ?? 0}ms）`)
    } else {
      ElMessage.error(`测试失败：${result.message}`)
    }
  } catch {
    // 错误已统一提示
  } finally {
    dialogTesting.value = false
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

// 维度阈值 JSON 默认模板(用户不知道该填什么时直接用这个)
// 每个维度包含:阈值 threshold(0-100)、权重 weight(0-1,所有维度权重之和应为 1)、描述
const DEFAULT_DIMENSION_TEMPLATE = {
  completeness: { threshold: 70, weight: 0.3, description: '完整性 - 功能覆盖、文档齐全' },
  correctness: { threshold: 70, weight: 0.4, description: '正确性 - 逻辑正确、无缺陷' },
  performance: { threshold: 70, weight: 0.2, description: '性能 - 响应时间、资源占用' },
  security: { threshold: 70, weight: 0.1, description: '安全性 - 漏洞、权限控制' },
}
const DEFAULT_DIMENSION_JSON_TEXT = JSON.stringify(DEFAULT_DIMENSION_TEMPLATE, null, 2)

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
  dimensionJsonText.value = DEFAULT_DIMENSION_JSON_TEXT
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
        <el-table-column label="协议" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="row.protocol === 'anthropic' ? 'warning' : 'primary'" size="small">
              {{ row.protocol === 'anthropic' ? 'Anthropic' : 'OpenAI' }}
            </el-tag>
          </template>
        </el-table-column>
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
        <el-table-column label="操作" width="220" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link @click="openModelEdit(row)">编辑</el-button>
            <el-button
              type="success"
              link
              :loading="testingIds.has(row.id)"
              @click="handleTestModel(row)"
            >测试 API</el-button>
            <el-button
              v-if="row.is_active"
              type="warning"
              link
              @click="handleModelDisable(row)"
            >禁用</el-button>
            <el-button
              v-else
              type="success"
              link
              @click="handleModelEnable(row)"
            >启用</el-button>
            <el-button type="danger" link @click="handleModelDelete(row)">删除</el-button>
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
            <el-button type="danger" link @click="handleRuleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 模型对话框 -->
    <el-dialog
      v-model="modelDialogVisible"
      :title="modelDialogMode === 'create' ? '新增模型' : '编辑模型'"
      width="520px"
      class="dialog-scroll"
    >
      <el-alert
        v-if="dialogTestResult"
        :type="dialogTestResult.success ? 'success' : 'error'"
        :title="dialogTestResult.success ? 'API 调用成功' : 'API 调用失败'"
        :description="dialogTestResult.message + (dialogTestResult.latency_ms ? `（耗时 ${dialogTestResult.latency_ms}ms）` : '')"
        show-icon
        :closable="true"
        style="margin-bottom: 16px"
      />
      <el-alert
        v-if="!dialogTestResult"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #title>
          <span style="font-size: 12px">点击「测试调用 API」会发送一个真实请求验证:API 地址、API Key、模型名、协议格式是否正确。</span>
        </template>
      </el-alert>
      <el-form ref="modelFormRef" :model="modelForm" :rules="modelRules" label-width="100px">
        <el-form-item label="快速预设">
          <el-select
            placeholder="选择预设模板自动填充"
            style="width: 100%"
            @change="(val: string) => { const p = presetModels.find(m => m.label === val); if (p) applyPreset(p) }"
          >
            <el-option
              v-for="p in presetModels"
              :key="p.label"
              :label="p.label"
              :value="p.label"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="modelForm.name" placeholder="模型显示名称" />
        </el-form-item>
        <el-form-item label="接口协议" prop="protocol">
          <el-select v-model="modelForm.protocol" style="width: 100%">
            <el-option
              v-for="opt in protocolOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="API 地址" prop="api_base">
          <el-input
            v-model="modelForm.api_base"
            :placeholder="modelForm.protocol === 'anthropic' ? 'https://api.anthropic.com' : 'https://api.openai.com/v1 或 https://api.minimaxi.com/v1 或 http://localhost:11434/v1'"
          />
          <div class="api-base-hint">
            <el-icon size="12"><InfoFilled /></el-icon>
            <span>系统会自动补全路径后缀(OpenAI 协议补 <code>/v1/chat/completions</code>,Anthropic 协议补 <code>/v1/messages</code>)。以下写法都可识别:根域名 / <code>/v1</code> / 完整路径。</span>
          </div>
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="modelForm.api_key" show-password placeholder="sk-..." />
        </el-form-item>
        <el-form-item label="模型标识" prop="model_name">
          <el-input v-model="modelForm.model_name" placeholder="如 gpt-4o / claude-sonnet-4-5 / MiniMax-M3 / glm-5-plus / deepseek-chat" />
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
        <el-button
          type="success"
          :loading="dialogTesting"
          @click="handleTestModelInline"
        >测试调用 API</el-button>
        <el-button type="primary" :loading="modelSubmitting" @click="handleModelSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 规则对话框 -->
    <el-dialog
      v-model="ruleDialogVisible"
      :title="ruleDialogMode === 'create' ? '新增评审规则' : '编辑评审规则'"
      width="640px"
      class="dialog-scroll"
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
            :rows="8"
            placeholder='{"completeness": {"threshold": 70, "weight": 0.3, "description": "完整性"}}'
          />
          <div class="api-base-hint">
            <el-icon size="12"><InfoFilled /></el-icon>
            <span>每个维度包含 <code>threshold</code>(0-100 阈值)、<code>weight</code>(0-1 权重,总和应为 1)、<code>description</code>(描述)。默认模板已填好 4 个维度:完整性、正确性、性能、安全性。可直接修改或新增维度。</span>
          </div>
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

:deep(.dialog-scroll .el-dialog__body) {
  max-height: 60vh;
  overflow-y: auto;
}

/* API 地址提示信息 */
.api-base-hint {
  margin-top: 6px;
  padding: 8px 10px;
  background: #f4f4f5;
  border-left: 3px solid #909399;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
  display: flex;
  gap: 6px;
  align-items: flex-start;
}
.api-base-hint :deep(.el-icon) {
  flex-shrink: 0;
  margin-top: 2px;
  color: #909399;
}
.api-base-hint code {
  background: #e4e7ed;
  padding: 1px 4px;
  border-radius: 2px;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
  color: #303133;
}
</style>
