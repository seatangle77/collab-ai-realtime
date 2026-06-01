import { http } from '../http'
import type { AdminSpeechTranscript, BatchDeleteResponse, Page } from '../../types/admin'

export interface ListSpeechTranscriptsParams {
  page?: number
  page_size?: number
  session_id?: string
  group_id?: string
  speaker?: string
  text?: string
  created_from?: string
  created_to?: string
}

export async function listSpeechTranscripts(
  params: ListSpeechTranscriptsParams,
): Promise<Page<AdminSpeechTranscript>> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.session_id) query.set('session_id', params.session_id)
  if (params.group_id) query.set('group_id', params.group_id)
  if (params.speaker) query.set('speaker', params.speaker)
  if (params.text) query.set('text', params.text)
  if (params.created_from) query.set('created_from', params.created_from)
  if (params.created_to) query.set('created_to', params.created_to)

  const qs = query.toString()
  return http.get<Page<AdminSpeechTranscript>>(
    '/api/admin/speech-transcripts/' + (qs ? `?${qs}` : ''),
  )
}

export async function deleteSpeechTranscript(transcriptId: string): Promise<void> {
  await http.delete<void>(`/api/admin/speech-transcripts/${transcriptId}`)
}

export async function updateSpeechTranscript(
  transcriptId: string,
  text: string,
): Promise<AdminSpeechTranscript> {
  return http.patch<AdminSpeechTranscript>(`/api/admin/speech-transcripts/${transcriptId}`, { text })
}

export async function batchDeleteSpeechTranscripts(
  transcriptIds: string[],
): Promise<BatchDeleteResponse> {
  return http.post<BatchDeleteResponse>('/api/admin/speech-transcripts/batch-delete', {
    ids: transcriptIds,
  })
}
