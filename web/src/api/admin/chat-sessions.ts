import { http } from '../http'
import type { AdminChatSession, Page } from '../../types/admin'

export interface ListAdminChatSessionsParams {
  page?: number
  page_size?: number
  group_id?: string
  session_title?: string
  status?: 'not_started' | 'ongoing' | 'ended'
  created_from?: string
  created_to?: string
  last_updated_from?: string
  last_updated_to?: string
  ended_from?: string
  ended_to?: string
}

export interface CreateAdminChatSessionPayload {
  group_id: string
  session_title: string
  is_active?: boolean | null
  created_at?: string
  last_updated?: string
  ended_at?: string | null
}

export async function listAdminChatSessions(params: ListAdminChatSessionsParams): Promise<Page<AdminChatSession>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.group_id) query.set('group_id', params.group_id)
  if (params.session_title) query.set('session_title', params.session_title)
  if (params.status) query.set('status', params.status)
  if (params.created_from) query.set('created_from', params.created_from)
  if (params.created_to) query.set('created_to', params.created_to)
  if (params.last_updated_from) query.set('last_updated_from', params.last_updated_from)
  if (params.last_updated_to) query.set('last_updated_to', params.last_updated_to)
  if (params.ended_from) query.set('ended_from', params.ended_from)
  if (params.ended_to) query.set('ended_to', params.ended_to)

  const qs = query.toString()
  const url = '/api/admin/chat-sessions' + (qs ? `?${qs}` : '')
  return http.get<Page<AdminChatSession>>(url)
}

export async function createAdminChatSession(payload: CreateAdminChatSessionPayload): Promise<AdminChatSession> {
  return http.post<AdminChatSession>('/api/admin/chat-sessions', payload)
}

export interface UpdateAdminChatSessionPayload {
  session_title?: string
  is_active?: boolean
  ended_at?: string | null
  created_at?: string
  last_updated?: string
}

export async function updateAdminChatSession(
  id: string,
  payload: UpdateAdminChatSessionPayload,
): Promise<AdminChatSession> {
  return http.patch<AdminChatSession>(`/api/admin/chat-sessions/${id}`, payload)
}

export async function deleteAdminChatSession(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/chat-sessions/${id}`)
}

