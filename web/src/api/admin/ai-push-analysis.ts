import { http } from '../http'
import type { AdminAiPushAnalysis, AiPushDropReason, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListAiPushAnalysisParams {
  page?: number
  page_size?: number
  session_id?: string
  target_user_id?: string
  state_type?: string
  ai_needs_prompt?: boolean
  drop_reason?: AiPushDropReason
  window_start_from?: string
  window_start_to?: string
}

export async function listAiPushAnalysis(
  params: ListAiPushAnalysisParams,
): Promise<Page<AdminAiPushAnalysis>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.target_user_id) query.set('target_user_id', params.target_user_id)
  if (params.state_type) query.set('state_type', params.state_type)
  if (params.ai_needs_prompt !== undefined) query.set('ai_needs_prompt', String(params.ai_needs_prompt))
  if (params.drop_reason) query.set('drop_reason', params.drop_reason)
  if (params.window_start_from) query.set('window_start_from', params.window_start_from)
  if (params.window_start_to) query.set('window_start_to', params.window_start_to)

  const qs = query.toString()
  return http.get<Page<AdminAiPushAnalysis>>('/api/admin/ai-push-analysis/' + (qs ? `?${qs}` : ''))
}

export async function deleteAiPushAnalysis(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/ai-push-analysis/${id}`)
}

export async function batchDeleteAiPushAnalysis(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/ai-push-analysis/batch-delete', { ids })
}
