import { http } from '../http'
import type {
  AdminDiscussionState,
  BatchDeleteResponse,
  DiscussionStateType,
  Page,
} from '../../types/admin'

export interface ListDiscussionStatesParams {
  page?: number
  page_size?: number
  session_id?: string
  state_type?: DiscussionStateType
  target_user_id?: string
  ai_analysis_done?: boolean
  push_sent?: boolean
  triggered_from?: string
  triggered_to?: string
}

export async function listDiscussionStates(
  params: ListDiscussionStatesParams,
): Promise<Page<AdminDiscussionState>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.state_type) query.set('state_type', params.state_type)
  if (params.target_user_id) query.set('target_user_id', params.target_user_id)
  if (params.ai_analysis_done !== undefined)
    query.set('ai_analysis_done', String(params.ai_analysis_done))
  if (params.push_sent !== undefined) query.set('push_sent', String(params.push_sent))
  if (params.triggered_from) query.set('triggered_from', params.triggered_from)
  if (params.triggered_to) query.set('triggered_to', params.triggered_to)

  const qs = query.toString()
  return http.get<Page<AdminDiscussionState>>(
    '/api/admin/discussion-states/' + (qs ? `?${qs}` : ''),
  )
}

export async function deleteDiscussionState(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/discussion-states/${id}`)
}

export async function batchDeleteDiscussionStates(
  ids: string[],
): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/discussion-states/batch-delete', { ids })
}
