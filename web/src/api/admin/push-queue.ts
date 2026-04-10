import { http } from '../http'
import type {
  AdminPushQueue,
  BatchDeleteResponse,
  DiscussionStateType,
  Page,
  PushQueueStatus,
} from '../../types/admin'

export interface ListPushQueueParams {
  page?: number
  page_size?: number
  session_id?: string
  target_user_id?: string
  state_type?: DiscussionStateType
  status?: PushQueueStatus
  created_from?: string
  created_to?: string
}

export async function listPushQueue(params: ListPushQueueParams): Promise<Page<AdminPushQueue>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.target_user_id) query.set('target_user_id', params.target_user_id)
  if (params.state_type) query.set('state_type', params.state_type)
  if (params.status) query.set('status', params.status)
  if (params.created_from) query.set('created_from', params.created_from)
  if (params.created_to) query.set('created_to', params.created_to)

  const qs = query.toString()
  return http.get<Page<AdminPushQueue>>('/api/admin/push-queue/' + (qs ? `?${qs}` : ''))
}

export async function deletePushQueueItem(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/push-queue/${id}`)
}

export async function batchDeletePushQueue(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/push-queue/batch-delete', { ids })
}
