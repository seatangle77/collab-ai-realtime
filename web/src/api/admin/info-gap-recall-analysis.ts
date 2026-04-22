import { http } from '../http'
import type { AdminKeywordRecallAnalysis, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListKeywordRecallAnalysisParams {
  page?: number
  page_size?: number
  session_id?: string
  keyword?: string
  needs_prompt?: boolean
  window_start_from?: string
  window_start_to?: string
}

export async function listKeywordRecallAnalysis(
  params: ListKeywordRecallAnalysisParams,
): Promise<Page<AdminKeywordRecallAnalysis>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.keyword) query.set('keyword', params.keyword)
  if (params.needs_prompt !== undefined) query.set('needs_prompt', String(params.needs_prompt))
  if (params.window_start_from) query.set('window_start_from', params.window_start_from)
  if (params.window_start_to) query.set('window_start_to', params.window_start_to)

  const qs = query.toString()
  return http.get<Page<AdminKeywordRecallAnalysis>>(
    '/api/admin/info-gap-recall-analysis/' + (qs ? `?${qs}` : ''),
  )
}

export async function deleteKeywordRecallAnalysis(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/info-gap-recall-analysis/${id}`)
}

export async function batchDeleteKeywordRecallAnalysis(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/info-gap-recall-analysis/batch-delete', { ids })
}
