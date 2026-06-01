import { http } from '../http'

export interface CoiUtterance {
  id: string
  session_id: string
  group_id: string
  speaker: string | null
  speaker_name: string | null
  speaker_user_id: string | null
  content: string
  source_transcript_ids: string[]
  order_index: number
  coi_category: 'TE' | 'EX' | 'IN' | 'RE' | null
  coded_by: string | null
  coded_at: string | null
  created_at: string
}

export interface ImportResponse {
  imported: number
  skipped: number
}

export async function listCoiUtterances(sessionId: string): Promise<CoiUtterance[]> {
  return http.get<CoiUtterance[]>(`/api/admin/coi-utterances/?session_id=${encodeURIComponent(sessionId)}`)
}

export async function importFromTranscripts(sessionId: string): Promise<ImportResponse> {
  return http.post<ImportResponse>(`/api/admin/coi-utterances/import?session_id=${sessionId}`)
}

export async function updateCoiUtterance(
  id: string,
  payload: { speaker?: string; content?: string; speaker_user_id?: string },
): Promise<CoiUtterance> {
  return http.patch<CoiUtterance>(`/api/admin/coi-utterances/${id}`, payload)
}

export async function deleteCoiUtterance(id: string): Promise<void> {
  await http.delete(`/api/admin/coi-utterances/${id}`)
}

export async function mergeCoiUtterances(ids: string[]): Promise<CoiUtterance> {
  return http.post<CoiUtterance>('/api/admin/coi-utterances/merge', { ids })
}

export async function splitCoiUtterance(id: string, offset: number): Promise<CoiUtterance[]> {
  return http.post<CoiUtterance[]>(`/api/admin/coi-utterances/${id}/split`, { offset })
}

export async function codeCoiUtterance(
  id: string,
  coi_category: 'TE' | 'EX' | 'IN' | 'RE' | null,
  coded_by?: string,
): Promise<CoiUtterance> {
  return http.patch<CoiUtterance>(`/api/admin/coi-utterances/${id}/code`, { coi_category, coded_by })
}

export async function reorderCoiUtterances(
  items: { id: string; order_index: number }[],
): Promise<void> {
  await http.post('/api/admin/coi-utterances/reorder', { items })
}
