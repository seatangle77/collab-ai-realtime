import { http } from '../http'
import type { Page } from '../../types/admin'

export type CueUptakeCode =
  | 'not_discussed'
  | 'discussed_not_adopted'
  | 'discussed_adopted'
  | 'uncertain'

export type CueCodingStatus = 'coded' | 'uncoded'
export type CueCondition = 'glasses' | 'app_notification'

export interface CueUptakeCoding {
  id: string
  push_log_id: string
  coder_role: string
  uptake_code: CueUptakeCode
  evidence_transcript_ids: string[]
  coding_reason: string | null
  coded_by: string | null
  coded_at: string
  created_at: string
  updated_at: string
}

export interface CueEvent {
  push_log_id: string
  queue_id: string | null
  session_id: string
  session_title: string | null
  group_id: string
  group_name: string
  condition: CueCondition
  target_user_id: string
  target_user_name: string
  push_content: string
  state_type: string
  received_at: string
  delivery_reason: string | null
  possible_duplicate: boolean
  coding: CueUptakeCoding | null
}

export interface CueContextMember {
  user_id: string
  user_name: string
  role: string | null
}

export interface CueContextTranscript {
  transcript_id: string
  speaker_user_id: string | null
  speaker_name: string
  text: string | null
  start: string | null
  end: string | null
  created_at: string | null
}

export interface CueSessionContext {
  session_id: string
  session_title: string | null
  group_id: string
  group_name: string
  condition: CueCondition
  members: CueContextMember[]
  transcripts: CueContextTranscript[]
  cues: CueEvent[]
}

export interface CueCodingProgress {
  total: number
  coded: number
  uncoded: number
  completion_rate: number
  by_code: Record<CueUptakeCode, number>
}

export interface ListCueEventsParams {
  page?: number
  page_size?: number
  condition?: CueCondition
  group_id?: string
  session_id?: string
  target_user_id?: string
  coding_status?: CueCodingStatus
  uptake_code?: CueUptakeCode
  coder_role?: string
  keyword?: string
}

export interface CueProgressParams {
  condition?: CueCondition
  group_id?: string
  session_id?: string
  target_user_id?: string
  coder_role?: string
}

export interface SaveCueCodingPayload {
  coder_role: string
  uptake_code: CueUptakeCode
  evidence_transcript_ids: string[]
  coding_reason?: string | null
  coded_by?: string | null
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const value = query.toString()
  return value ? `?${value}` : ''
}

export async function listCueEvents(params: ListCueEventsParams): Promise<Page<CueEvent>> {
  return http.get<Page<CueEvent>>(
    `/api/admin/cue-uptake-coding/events${buildQuery({ ...params })}`,
  )
}

export async function getCueSessionContext(
  sessionId: string,
  coderRole = 'primary',
): Promise<CueSessionContext> {
  return http.get<CueSessionContext>(
    `/api/admin/cue-uptake-coding/sessions/${encodeURIComponent(sessionId)}/context${buildQuery({ coder_role: coderRole })}`,
  )
}

export async function saveCueCoding(
  pushLogId: string,
  payload: SaveCueCodingPayload,
): Promise<CueUptakeCoding> {
  return http.put<CueUptakeCoding>(
    `/api/admin/cue-uptake-coding/events/${encodeURIComponent(pushLogId)}/coding`,
    payload,
  )
}

export async function deleteCueCoding(pushLogId: string, coderRole = 'primary'): Promise<void> {
  await http.delete<void>(
    `/api/admin/cue-uptake-coding/events/${encodeURIComponent(pushLogId)}/coding${buildQuery({ coder_role: coderRole })}`,
  )
}

export async function getCueCodingProgress(params: CueProgressParams): Promise<CueCodingProgress> {
  return http.get<CueCodingProgress>(
    `/api/admin/cue-uptake-coding/progress${buildQuery({ ...params })}`,
  )
}

export async function downloadCueCodingExport(params: ListCueEventsParams): Promise<void> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  const token = window.localStorage.getItem('admin_api_key')
  const response = await fetch(
    `${baseUrl}/api/admin/cue-uptake-coding/export${buildQuery({ ...params })}`,
    { headers: token ? { 'X-Admin-Token': token } : {} },
  )
  if (response.status === 401 || response.status === 403) {
    window.location.href = '/admin/login'
    throw new Error('未授权访问后台接口')
  }
  if (!response.ok) {
    throw new Error((await response.text().catch(() => '')) || `导出失败，状态码 ${response.status}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `提示采纳编码-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
