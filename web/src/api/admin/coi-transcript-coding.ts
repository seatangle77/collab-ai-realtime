import { http } from '../http'

export interface UtteranceCountResult {
  session_id: string
  group_id: string | null
  count: number
}

export interface TranscriptUtteranceIn {
  order_index: number
  content: string
  start_time: number | null
  coi_category: 'TE' | 'EX' | 'IN' | 'RE' | null
}

export interface UtteranceOut {
  order_index: number
  content: string
  start_time: number | null
  coi_category: 'TE' | 'EX' | 'IN' | 'RE' | null
}

export interface UtterancesOut {
  session_id: string
  group_id: string | null
  utterances: UtteranceOut[]
}

export interface SaveTranscriptResponse {
  saved: number
  deleted_previous: number
}

export async function getUtteranceCount(sessionId: string): Promise<UtteranceCountResult> {
  return http.get<UtteranceCountResult>(
    `/api/admin/coi-transcript-coding/sessions/${encodeURIComponent(sessionId)}/utterance-count`,
  )
}

export async function getSessionUtterances(sessionId: string): Promise<UtterancesOut> {
  return http.get<UtterancesOut>(
    `/api/admin/coi-transcript-coding/sessions/${encodeURIComponent(sessionId)}/utterances`,
  )
}

export async function saveTranscriptUtterances(
  sessionId: string,
  utterances: TranscriptUtteranceIn[],
): Promise<SaveTranscriptResponse> {
  return http.post<SaveTranscriptResponse>(
    `/api/admin/coi-transcript-coding/sessions/${encodeURIComponent(sessionId)}/utterances`,
    { utterances },
  )
}
