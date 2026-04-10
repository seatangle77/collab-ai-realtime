import { http } from '../http'
import type { AdminDiscussionSummary, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListDiscussionSummariesParams {
  page?: number
  page_size?: number
  session_id?: string
  version?: number
  window_start_from?: string
  window_start_to?: string
}

export async function listDiscussionSummaries(
  params: ListDiscussionSummariesParams,
): Promise<Page<AdminDiscussionSummary>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.version !== undefined) query.set('version', String(params.version))
  if (params.window_start_from) query.set('window_start_from', params.window_start_from)
  if (params.window_start_to) query.set('window_start_to', params.window_start_to)

  const qs = query.toString()
  return http.get<Page<AdminDiscussionSummary>>(
    '/api/admin/discussion-summaries/' + (qs ? `?${qs}` : ''),
  )
}

export async function getDiscussionSummary(id: string): Promise<AdminDiscussionSummary> {
  return http.get<AdminDiscussionSummary>(`/api/admin/discussion-summaries/${id}`)
}

export async function updateDiscussionSummary(
  id: string,
  content: string,
): Promise<AdminDiscussionSummary> {
  return http.put<AdminDiscussionSummary>(`/api/admin/discussion-summaries/${id}`, { content })
}

export async function deleteDiscussionSummary(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/discussion-summaries/${id}`)
}

export async function batchDeleteDiscussionSummaries(
  ids: string[],
): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/discussion-summaries/batch-delete', { ids })
}
