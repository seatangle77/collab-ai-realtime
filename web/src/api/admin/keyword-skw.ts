import { http } from '../http'
import type { AdminKeywordSkw, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListKeywordSkwParams {
  page?: number
  page_size?: number
  session_id?: string
  keyword?: string
  user_a_id?: string
  user_b_id?: string
  skw_score_min?: number
  skw_score_max?: number
  window_start_from?: string
  window_start_to?: string
}

export async function listKeywordSkw(
  params: ListKeywordSkwParams,
): Promise<Page<AdminKeywordSkw>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.keyword) query.set('keyword', params.keyword)
  if (params.user_a_id) query.set('user_a_id', params.user_a_id)
  if (params.user_b_id) query.set('user_b_id', params.user_b_id)
  if (params.skw_score_min !== undefined) query.set('skw_score_min', String(params.skw_score_min))
  if (params.skw_score_max !== undefined) query.set('skw_score_max', String(params.skw_score_max))
  if (params.window_start_from) query.set('window_start_from', params.window_start_from)
  if (params.window_start_to) query.set('window_start_to', params.window_start_to)

  const qs = query.toString()
  return http.get<Page<AdminKeywordSkw>>('/api/admin/keyword-skw/' + (qs ? `?${qs}` : ''))
}

export async function deleteKeywordSkw(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/keyword-skw/${id}`)
}

export async function batchDeleteKeywordSkw(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/keyword-skw/batch-delete', { ids })
}
