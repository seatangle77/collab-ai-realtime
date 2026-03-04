import { http } from '../http'
import type { AdminUser, Page } from '../../types/admin'

export interface ListAdminUsersParams {
  page?: number
  page_size?: number
  email?: string
  name?: string
}

export async function listAdminUsers(params: ListAdminUsersParams): Promise<Page<AdminUser>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.email) query.set('email', params.email)
  if (params.name) query.set('name', params.name)

  const qs = query.toString()
  const url = '/api/admin/users' + (qs ? `?${qs}` : '')
  return http.get<Page<AdminUser>>(url)
}

