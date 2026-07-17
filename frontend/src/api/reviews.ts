/**
 * 评审 API
 */
import request from './request'
import type { LLMReview, ReviewType, TriggerReviewResponse } from '@/types'

/** 获取某释放的所有 LLM 评审记录 */
export function getReleaseReviews(releaseId: string): Promise<LLMReview[]> {
  return request.get(`/reviews/release/${releaseId}`)
}

/** 触发一次 LLM 评审 */
export function triggerReview(
  releaseId: string,
  reviewType: ReviewType,
): Promise<TriggerReviewResponse> {
  return request.post(`/reviews/trigger/${releaseId}`, null, {
    params: { review_type: reviewType },
  })
}
