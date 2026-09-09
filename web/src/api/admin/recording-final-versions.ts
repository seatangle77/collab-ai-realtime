import { http } from '../http'
export interface RecordingSource {
  recording: Array<{ order_index: number; content: string; start_time: number | null }>
  transcripts: Array<{ transcript_id: string; text: string; speaker_name: string; relative_seconds: number | null }>
  source_hash: string
}
export interface FinalSegment {
  id: string
  kind: 'before' | 'recording' | 'after'
  text: string
  time: number | null
  recording_order?: number
  speaker_name: string | null
  transcript_ids: string[]
  correspondence_status: 'original' | 'linked' | 'pending' | 'grouped'
}
export interface RecordingDocument {
  session_id: string
  start_transcript_id: string
  end_transcript_id: string
  segments: FinalSegment[]
  recording_count: number
  pending_count: number
  replaced_count: number
  before_count: number
  after_count: number
  source_hash: string
  preview_hash: string
}
export interface RecordingVersion {
  id: string
  document: RecordingDocument
  created_at: string
  created_by: string | null
}
export interface RecordingRange { start_transcript_id?: string; end_transcript_id?: string; alignment_run_id?: string; alignment_offset_seconds?: number }
const base = (session: string) => `/api/admin/transcript-corrections/sessions/${encodeURIComponent(session)}/final-version`
export const getRecordingSource = (session: string) => http.get<RecordingSource>(`${base(session)}/source`)
export const getRecordingVersion = (session: string) => http.get<RecordingVersion | null>(base(session))
export const previewRecordingVersion = (session: string, range: RecordingRange) => http.post<RecordingDocument>(`${base(session)}/preview`, range)
export const saveRecordingVersion = (session: string, payload: RecordingRange & {
  source_hash: string; preview_hash: string; boundary_confirmed: boolean; base_version_id: string | null
}) => http.post<RecordingVersion>(base(session), payload)
