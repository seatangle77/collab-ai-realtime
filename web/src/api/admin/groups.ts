import { http } from '../http'
import type { AdminGroup, Page } from '../../types/admin'

export interface ListAdminGroupsParams {
  page?: number
  page_size?: number
  name?: string
  is_active?: boolean
  created_from?: string
  created_to?: string
}

export async function listAdminGroups(params: ListAdminGroupsParams): Promise<Page<AdminGroup>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.name) query.set('name', params.name)
  if (params.is_active !== undefined) query.set('is_active', String(params.is_active))
  if (params.created_from) query.set('created_from', params.created_from)
  if (params.created_to) query.set('created_to', params.created_to)

  const qs = query.toString()
  const url = '/api/admin/groups/' + (qs ? `?${qs}` : '')
  return http.get<Page<AdminGroup>>(url)
}

export async function deleteAdminGroup(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/groups/${id}`)
}

export interface UpdateAdminGroupPayload {
  name?: string
  is_active?: boolean
}

export async function updateAdminGroup(id: string, payload: UpdateAdminGroupPayload): Promise<AdminGroup> {
  return http.patch<AdminGroup>(`/api/admin/groups/${id}`, payload)
}
