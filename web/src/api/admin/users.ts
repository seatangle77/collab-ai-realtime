import { http } from '../http'
import type { AdminUser, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListAdminUsersParams {
  page?: number
  page_size?: number
  email?: string
  name?: string
  id?: string
  device_token?: string
  created_from?: string
  created_to?: string
  group_name?: string
  group_id?: string
}

export async function listAdminUsers(params: ListAdminUsersParams): Promise<Page<AdminUser>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.email) query.set('email', params.email)
  if (params.name) query.set('name', params.name)
  if (params.id) query.set('id', params.id)
  if (params.device_token) query.set('device_token', params.device_token)
  if (params.created_from) query.set('created_from', params.created_from)
  if (params.created_to) query.set('created_to', params.created_to)
  if (params.group_name) query.set('group_name', params.group_name)
  if (params.group_id) query.set('group_id', params.group_id)

  const qs = query.toString()
  const url = '/api/admin/users/' + (qs ? `?${qs}` : '')
  return http.get<Page<AdminUser>>(url)
}

export async function deleteAdminUser(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/users/${id}`)
}

export async function deleteAdminUsersBatch(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/users/batch-delete', { ids })
}

export interface UpdateAdminUserPayload {
  name?: string
  device_token?: string | null
}

export async function updateAdminUser(id: string, payload: UpdateAdminUserPayload): Promise<AdminUser> {
  return http.patch<AdminUser>(`/api/admin/users/${id}`, payload)
}

export interface ImpersonateResponse {
  access_token: string
  token_type: string
}

export async function impersonateUser(id: string): Promise<ImpersonateResponse> {
  return http.post<ImpersonateResponse>(`/api/admin/users/${id}/impersonate`)
}

export async function markUserPasswordReset(id: string): Promise<AdminUser> {
  return http.post<AdminUser>(`/api/admin/users/${id}/mark-password-reset`)
}

