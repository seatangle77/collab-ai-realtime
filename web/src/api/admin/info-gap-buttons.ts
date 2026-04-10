import { http } from '../http'
import type { AdminInfoGapButton, BatchDeleteResponse, InfoGapButtonStatus, Page } from '../../types/admin'

export interface ListInfoGapButtonsParams {
  page?: number
  page_size?: number
  session_id?: string
  user_id?: string
  keyword?: string
  status?: InfoGapButtonStatus
  has_clicked?: boolean
  window_start_from?: string
  window_start_to?: string
}

export async function listInfoGapButtons(
  params: ListInfoGapButtonsParams,
): Promise<Page<AdminInfoGapButton>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.user_id) query.set('user_id', params.user_id)
  if (params.keyword) query.set('keyword', params.keyword)
  if (params.status) query.set('status', params.status)
  if (params.has_clicked !== undefined) query.set('has_clicked', String(params.has_clicked))
  if (params.window_start_from) query.set('window_start_from', params.window_start_from)
  if (params.window_start_to) query.set('window_start_to', params.window_start_to)

  const qs = query.toString()
  return http.get<Page<AdminInfoGapButton>>(
    '/api/admin/info-gap-buttons/' + (qs ? `?${qs}` : ''),
  )
}

export async function deleteInfoGapButton(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/info-gap-buttons/${id}`)
}

export async function batchDeleteInfoGapButtons(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/info-gap-buttons/batch-delete', { ids })
}
