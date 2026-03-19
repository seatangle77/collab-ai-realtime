import { http } from '../http'
import type { AdminTranscript, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListAdminTranscriptsParams {
  page?: number
  page_size?: number
  session_id?: string
  user_id?: string
  speaker?: string
}

export interface CreateAdminTranscriptPayload {
  session_id: string
  group_id: string
  text: string
  start: string
  end: string
  user_id?: string | null
  speaker?: string | null
  duration?: number | null
  confidence?: number | null
}

export interface UpdateAdminTranscriptPayload {
  text?: string
  speaker?: string | null
  start?: string
  end?: string
  user_id?: string | null
  duration?: number | null
  confidence?: number | null
}

export async function listAdminTranscripts(
  params: ListAdminTranscriptsParams,
): Promise<Page<AdminTranscript>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.user_id) query.set('user_id', params.user_id)
  if (params.speaker) query.set('speaker', params.speaker)

  const qs = query.toString()
  const url = '/api/admin/transcripts/' + (qs ? `?${qs}` : '')
  return http.get<Page<AdminTranscript>>(url)
}

export async function createAdminTranscript(
  payload: CreateAdminTranscriptPayload,
): Promise<AdminTranscript> {
  return http.post<AdminTranscript>('/api/admin/transcripts/', payload)
}

export async function updateAdminTranscript(
  transcriptId: string,
  payload: UpdateAdminTranscriptPayload,
): Promise<AdminTranscript> {
  return http.patch<AdminTranscript>(`/api/admin/transcripts/${transcriptId}`, payload)
}

export async function deleteAdminTranscript(transcriptId: string): Promise<void> {
  await http.delete<void>(`/api/admin/transcripts/${transcriptId}`)
}

export async function deleteAdminTranscriptsBatch(
  transcriptIds: string[],
): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/transcripts/batch-delete', {
    ids: transcriptIds,
  })
}
