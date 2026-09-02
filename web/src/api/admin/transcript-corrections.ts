import { http } from '../http'
import type { Page } from '../../types/admin'

export type AssistedCondition = 'glasses' | 'app_notification'
export type CorrectionStatus = 'corrected' | 'uncorrected'

export interface TranscriptCorrectionGroup {
  group_id: string
  group_name: string
  condition: AssistedCondition
  transcript_count: number
  corrected_count: number
}

export interface TranscriptCorrectionSession {
  session_id: string
  session_title: string | null
  group_id: string
  group_name: string
  condition: AssistedCondition
  transcript_count: number
  corrected_count: number
  created_at: string
  started_at: string | null
}

export interface CorrectableTranscript {
  transcript_id: string
  group_id: string
  session_id: string
  speaker_user_id: string | null
  speaker_name: string
  original_text: string | null
  effective_text: string | null
  start: string | null
  end: string | null
  created_at: string | null
  is_corrected: boolean
  correction_id: string | null
  correction_reason: string | null
  corrected_by: string | null
  corrected_at: string | null
}

export interface TranscriptCorrection {
  id: string
  transcript_id: string
  corrected_text: string
  correction_reason: string | null
  corrected_by: string | null
  created_at: string
  updated_at: string
}

export interface ListCorrectableTranscriptsParams {
  page?: number
  page_size?: number
  correction_status?: CorrectionStatus
  speaker?: string
  keyword?: string
}

export interface SaveTranscriptCorrectionPayload {
  corrected_text: string
  correction_reason?: string | null
  corrected_by?: string | null
}

function queryString(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const value = query.toString()
  return value ? `?${value}` : ''
}

export async function listTranscriptCorrectionGroups(
  condition?: AssistedCondition,
): Promise<TranscriptCorrectionGroup[]> {
  return http.get<TranscriptCorrectionGroup[]>(
    `/api/admin/transcript-corrections/groups${queryString({ condition })}`,
  )
}

export async function listTranscriptCorrectionSessions(
  groupId: string,
): Promise<TranscriptCorrectionSession[]> {
  return http.get<TranscriptCorrectionSession[]>(
    `/api/admin/transcript-corrections/sessions${queryString({ group_id: groupId })}`,
  )
}

export async function listCorrectableTranscripts(
  sessionId: string,
  params: ListCorrectableTranscriptsParams,
): Promise<Page<CorrectableTranscript>> {
  return http.get<Page<CorrectableTranscript>>(
    `/api/admin/transcript-corrections/sessions/${encodeURIComponent(sessionId)}/transcripts${queryString({ ...params })}`,
  )
}

export async function saveTranscriptCorrection(
  transcriptId: string,
  payload: SaveTranscriptCorrectionPayload,
): Promise<TranscriptCorrection> {
  return http.put<TranscriptCorrection>(
    `/api/admin/transcript-corrections/transcripts/${encodeURIComponent(transcriptId)}`,
    payload,
  )
}

export async function deleteTranscriptCorrection(transcriptId: string): Promise<void> {
  await http.delete<void>(
    `/api/admin/transcript-corrections/transcripts/${encodeURIComponent(transcriptId)}`,
  )
}
