import { http } from '../http'
import type { AdminMembership, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListAdminMembershipsParams {
  page?: number
  page_size?: number
  group_id?: string
  user_id?: string
  status?: string
  created_from?: string
  created_to?: string
}

export interface CreateAdminMembershipPayload {
  group_id: string
  user_id: string
  role: 'leader' | 'member'
  status?: 'active' | 'left' | 'kicked'
}

export async function listAdminMemberships(params: ListAdminMembershipsParams): Promise<Page<AdminMembership>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.group_id) query.set('group_id', params.group_id)
  if (params.user_id) query.set('user_id', params.user_id)
  if (params.status) query.set('status', params.status)
  if (params.created_from) query.set('created_from', params.created_from)
  if (params.created_to) query.set('created_to', params.created_to)

  const qs = query.toString()
  const url = '/api/admin/memberships' + (qs ? `?${qs}` : '')
  return http.get<Page<AdminMembership>>(url)
}

export async function createAdminMembership(payload: CreateAdminMembershipPayload): Promise<AdminMembership> {
  return http.post<AdminMembership>('/api/admin/memberships', payload)
}

export interface UpdateAdminMembershipPayload {
  role?: string
  status?: string
}

export async function updateAdminMembership(
  id: string,
  payload: UpdateAdminMembershipPayload,
): Promise<AdminMembership> {
  return http.patch<AdminMembership>(`/api/admin/memberships/${id}`, payload)
}

export async function deleteAdminMembership(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/memberships/${id}`)
}

export async function deleteAdminMembershipsBatch(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/memberships/batch-delete', { ids })
}

