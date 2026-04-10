import { http } from '../http'
import type { AdminPushLog, BatchDeleteResponse, DeliveryStatus, Page, PushChannel } from '../../types/admin'

export interface ListPushLogsParams {
  page?: number
  page_size?: number
  session_id?: string
  state_id?: string
  target_user_id?: string
  push_channel?: PushChannel
  delivery_status?: DeliveryStatus
  jpush_message_id?: string
  triggered_from?: string
  triggered_to?: string
}

export async function listPushLogs(params: ListPushLogsParams): Promise<Page<AdminPushLog>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.state_id) query.set('state_id', params.state_id)
  if (params.target_user_id) query.set('target_user_id', params.target_user_id)
  if (params.push_channel) query.set('push_channel', params.push_channel)
  if (params.delivery_status) query.set('delivery_status', params.delivery_status)
  if (params.jpush_message_id) query.set('jpush_message_id', params.jpush_message_id)
  if (params.triggered_from) query.set('triggered_from', params.triggered_from)
  if (params.triggered_to) query.set('triggered_to', params.triggered_to)

  const qs = query.toString()
  return http.get<Page<AdminPushLog>>('/api/admin/push-logs/' + (qs ? `?${qs}` : ''))
}

export async function deletePushLog(id: string): Promise<void> {
  await http.delete<void>(`/api/admin/push-logs/${id}`)
}

export async function batchDeletePushLogs(ids: string[]): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/push-logs/batch-delete', { ids })
}
