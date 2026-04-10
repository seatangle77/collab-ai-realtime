import { http } from '../http'
import type { AdminSessionTextMessage, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListSessionTextMessagesParams {
  page?: number
  page_size?: number
  session_id?: string
  group_id?: string
  user_id?: string
  sender_name?: string
  content?: string
  created_from?: string
  created_to?: string
}

export async function listSessionTextMessages(
  params: ListSessionTextMessagesParams,
): Promise<Page<AdminSessionTextMessage>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.group_id) query.set('group_id', params.group_id)
  if (params.user_id) query.set('user_id', params.user_id)
  if (params.sender_name) query.set('sender_name', params.sender_name)
  if (params.content) query.set('content', params.content)
  if (params.created_from) query.set('created_from', params.created_from)
  if (params.created_to) query.set('created_to', params.created_to)

  const qs = query.toString()
  return http.get<Page<AdminSessionTextMessage>>(
    '/api/admin/session-text-messages/' + (qs ? `?${qs}` : ''),
  )
}

export async function deleteSessionTextMessage(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/session-text-messages/${id}`)
}

export async function batchDeleteSessionTextMessages(
  ids: string[],
): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/session-text-messages/batch-delete', { ids })
}
