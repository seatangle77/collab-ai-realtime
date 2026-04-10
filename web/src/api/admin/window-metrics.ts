import { http } from '../http'
import type { AdminWindowMetric, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListWindowMetricsParams {
  page?: number
  page_size?: number
  session_id?: string
  user_id?: string
  window_start_from?: string
  window_start_to?: string
  has_reasoning?: boolean
  has_evidence?: boolean
}

export async function listWindowMetrics(
  params: ListWindowMetricsParams,
): Promise<Page<AdminWindowMetric>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.user_id) query.set('user_id', params.user_id)
  if (params.window_start_from) query.set('window_start_from', params.window_start_from)
  if (params.window_start_to) query.set('window_start_to', params.window_start_to)
  if (params.has_reasoning !== undefined) query.set('has_reasoning', String(params.has_reasoning))
  if (params.has_evidence !== undefined) query.set('has_evidence', String(params.has_evidence))

  const qs = query.toString()
  return http.get<Page<AdminWindowMetric>>('/api/admin/window-metrics/' + (qs ? `?${qs}` : ''))
}

export async function deleteWindowMetric(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/window-metrics/${id}`)
}

export async function batchDeleteWindowMetrics(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/window-metrics/batch-delete', { ids })
}
