import { http } from '../http'
import type { AdminEngagementMetric, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListEngagementMetricsParams {
  page?: number
  page_size?: number
  session_id?: string
  user_id?: string
  calculated_from?: string
  calculated_to?: string
}

export async function listEngagementMetrics(
  params: ListEngagementMetricsParams,
): Promise<Page<AdminEngagementMetric>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.user_id) query.set('user_id', params.user_id)
  if (params.calculated_from) query.set('calculated_from', params.calculated_from)
  if (params.calculated_to) query.set('calculated_to', params.calculated_to)

  const qs = query.toString()
  return http.get<Page<AdminEngagementMetric>>(
    '/api/admin/engagement-metrics/' + (qs ? `?${qs}` : ''),
  )
}

export async function deleteEngagementMetric(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/engagement-metrics/${id}`)
}

export async function batchDeleteEngagementMetrics(
  ids: string[],
): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/engagement-metrics/batch-delete', { ids })
}
