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
  final_excluded?: boolean
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
  source_transcript_ids: string[]
  is_merged: boolean
}

export interface TranscriptCorrection {
  id: string
  transcript_id: string | null
  corrected_text: string
  correction_reason: string | null
  corrected_by: string | null
  created_at: string
  updated_at: string
}

export interface MergedTranscriptCorrection {
  id: string
  transcript_ids: string[]
  corrected_text: string
  correction_reason: string | null
  corrected_by: string | null
  created_at: string
  updated_at: string
}

export interface ListCorrectableTranscriptsParams {
  content_view?: 'original' | 'latest'
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

export interface SaveMergedTranscriptCorrectionPayload extends SaveTranscriptCorrectionPayload {
  transcript_ids: string[]
}

export type AlignmentRunStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_errors'
  | 'failed'

export type AlignmentConfidenceLevel = 'high' | 'medium' | 'low'

export interface AlignmentAnchorPayload {
  transcript_id: string
  transcript_relative_seconds: number
  reference_order: number
  reference_start_time: number
}

export interface AiAlignmentMatch {
  match_id: string
  reference_orders: number[]
  transcript_ids: string[]
  reference_text: string
  transcript_text: string
  corrected_text: string
  confidence: number
  confidence_level: AlignmentConfidenceLevel
  time_distance_seconds: number | null
  reason: string
  saved: boolean
  review_required: boolean
  review_reason: string
}

export interface AlignmentRunSummary {
  high: number
  medium: number
  low: number
  unmatched_references: number
  unmatched_transcripts: number
  skipped_corrected_transcripts: number
  replaceable_ai_transcripts: number
  organized_transcripts: number
  total_target_transcripts: number
  review_required: number
  out_of_scope_transcripts: number
}

export interface AlignmentRun {
  run_id: string
  session_id: string
  model: string
  status: AlignmentRunStatus
  completed_chunks: number
  total_chunks: number
  matches: AiAlignmentMatch[]
  summary: AlignmentRunSummary
  failed_chunks: number[]
  message: string
  total_tokens: number
  created_at: string
  out_of_scope_transcript_ids: string[]
  unmatched_transcript_ids?: string[]
  unmatched_reference_orders?: number[]
  excluded_transcript_ids?: string[]
}

export interface SaveAlignmentRunResult {
  saved_matches: number
  saved_transcripts: number
  saved_match_ids: string[]
  skipped: Array<{ match_id: string; reason: string }>
}

export interface UndoAlignmentRunResult {
  removed_matches: number
  removed_corrections: number
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

export async function createMergedTranscriptCorrection(
  sessionId: string,
  payload: SaveMergedTranscriptCorrectionPayload,
): Promise<MergedTranscriptCorrection> {
  return http.post<MergedTranscriptCorrection>(
    `/api/admin/transcript-corrections/sessions/${encodeURIComponent(sessionId)}/merged`,
    payload,
  )
}

export async function updateMergedTranscriptCorrection(
  correctionId: string,
  payload: SaveTranscriptCorrectionPayload,
): Promise<MergedTranscriptCorrection> {
  return http.put<MergedTranscriptCorrection>(
    `/api/admin/transcript-corrections/merged/${encodeURIComponent(correctionId)}`,
    payload,
  )
}

export async function deleteMergedTranscriptCorrection(correctionId: string): Promise<void> {
  await http.delete<void>(
    `/api/admin/transcript-corrections/merged/${encodeURIComponent(correctionId)}`,
  )
}

export async function startTranscriptAlignmentRun(
  sessionId: string,
  anchor: AlignmentAnchorPayload,
): Promise<AlignmentRun> {
  return http.post<AlignmentRun>(
    `/api/admin/transcript-corrections/sessions/${encodeURIComponent(sessionId)}/ai-match-runs`,
    { anchor },
  )
}

export async function getTranscriptAlignmentRun(runId: string): Promise<AlignmentRun> {
  return http.get<AlignmentRun>(
    `/api/admin/transcript-corrections/ai-match-runs/${encodeURIComponent(runId)}`,
  )
}

export async function resolveTranscriptAlignmentBoundary(
  runId: string,
  matchId: string,
  action: 'previous' | 'next' | 'keep',
): Promise<AlignmentRun> {
  return http.post<AlignmentRun>(
    `/api/admin/transcript-corrections/ai-match-runs/${encodeURIComponent(runId)}/resolve`,
    { match_id: matchId, action },
  )
}

export async function saveTranscriptAlignmentRun(
  runId: string,
  matchIds: string[],
  correctedBy?: string | null,
): Promise<SaveAlignmentRunResult> {
  return http.post<SaveAlignmentRunResult>(
    `/api/admin/transcript-corrections/ai-match-runs/${encodeURIComponent(runId)}/save`,
    { match_ids: matchIds, corrected_by: correctedBy || null },
  )
}

export async function undoTranscriptAlignmentRun(runId: string): Promise<UndoAlignmentRunResult> {
  return http.post<UndoAlignmentRunResult>(
    `/api/admin/transcript-corrections/ai-match-runs/${encodeURIComponent(runId)}/undo`,
    {},
  )
}
