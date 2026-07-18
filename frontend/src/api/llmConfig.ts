/**
 * LLM 配置 API（仅 SUPER_ADMIN）
 */
import request from './request'
import type {
  LLMModel,
  LLMModelCreate,
  LLMModelUpdate,
  ReviewRule,
  ReviewRuleCreate,
  ReviewRuleUpdate,
} from '@/types'

// ------------------------- LLM 模型 -------------------------

/** 获取所有 LLM 模型 */
export function getModels(): Promise<LLMModel[]> {
  return request.get('/llm-config/models')
}

/** 创建 LLM 模型 */
export function createModel(data: LLMModelCreate): Promise<LLMModel> {
  return request.post('/llm-config/models', data)
}

/** 更新 LLM 模型 */
export function updateModel(id: string, data: LLMModelUpdate): Promise<LLMModel> {
  return request.put(`/llm-config/models/${id}`, data)
}

/** 禁用 LLM 模型（软删除，保留历史记录可追溯） */
export function disableModel(id: string): Promise<LLMModel> {
  return request.post(`/llm-config/models/${id}/disable`)
}

/** 启用 LLM 模型（恢复已禁用的模型） */
export function enableModel(id: string): Promise<LLMModel> {
  return request.post(`/llm-config/models/${id}/enable`)
}

/** 物理删除 LLM 模型（不可恢复；若被评审规则引用则拒绝） */
export function deleteModel(id: string): Promise<{ deleted: boolean; id: string; name: string }> {
  return request.delete(`/llm-config/models/${id}`)
}

// ------------------------- 评审规则 -------------------------

/** 获取所有评审规则 */
export function getRules(): Promise<ReviewRule[]> {
  return request.get('/llm-config/rules')
}

/** 创建评审规则 */
export function createRule(data: ReviewRuleCreate): Promise<ReviewRule> {
  return request.post('/llm-config/rules', data)
}

/** 更新评审规则 */
export function updateRule(id: string, data: ReviewRuleUpdate): Promise<ReviewRule> {
  return request.put(`/llm-config/rules/${id}`, data)
}


/** 物理删除评审规则（不可恢复） */
export function deleteRule(id: string): Promise<{ deleted: boolean; id: string }> {
  return request.delete(`/llm-config/rules/${id}`)
}
