import { http } from '../http'
import type { AdminWindowMetricsBatchReasoning, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListWindowMetricsBatchReasoningParams {
  page?: number
  page_size?: number
  session_id?: string
  window_start_from?: string
  window_start_to?: string
}

export async function listWindowMetricsBatchReasoning(
  params: ListWindowMetricsBatchReasoningParams,
): Promise<Page<AdminWindowMetricsBatchReasoning>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.window_start_from) query.set('window_start_from', params.window_start_from)
  if (params.window_start_to) query.set('window_start_to', params.window_start_to)

  const qs = query.toString()
  return http.get<Page<AdminWindowMetricsBatchReasoning>>(
    '/api/admin/window-metrics-batch-reasoning/' + (qs ? `?${qs}` : ''),
  )
}

export async function deleteWindowMetricsBatchReasoning(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/window-metrics-batch-reasoning/${id}`)
}

export async function batchDeleteWindowMetricsBatchReasoning(
  ids: string[],
): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/window-metrics-batch-reasoning/batch-delete', { ids })
}
