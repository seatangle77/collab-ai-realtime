import { http } from '../http'
import type { AdminWindowMetricsKeyword, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListWindowMetricsKeywordsParams {
  page?: number
  page_size?: number
  session_id?: string
  keyword?: string
  window_start_from?: string
  window_start_to?: string
}

export async function listWindowMetricsKeywords(
  params: ListWindowMetricsKeywordsParams,
): Promise<Page<AdminWindowMetricsKeyword>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.keyword) query.set('keyword', params.keyword)
  if (params.window_start_from) query.set('window_start_from', params.window_start_from)
  if (params.window_start_to) query.set('window_start_to', params.window_start_to)

  const qs = query.toString()
  return http.get<Page<AdminWindowMetricsKeyword>>('/api/admin/window-metrics-keywords/' + (qs ? `?${qs}` : ''))
}

export async function deleteWindowMetricsKeyword(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/window-metrics-keywords/${id}`)
}

export async function batchDeleteWindowMetricsKeywords(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/window-metrics-keywords/batch-delete', { ids })
}
