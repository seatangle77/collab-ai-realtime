import { http } from '../http'
import type { CoiCategory } from './coi-units'

export interface AiCodingItem {
  unit_id: string
  order_index: number
  content: string
  start_time: number | null
  ai_segmentation_suggestion: string | null
  ai_segmentation_reviewed_at: string | null
  coi_categories: CoiCategory[]
  ai_original_categories: CoiCategory[]
  coding_reason: string
  has_ai_result: boolean
  coded_by: string | null
  coded_at: string | null
  updated_at: string | null
}

export interface AiCodingResponse {
  saved: number
  items: AiCodingItem[]
}

export interface AiCodeAdjustment {
  unit_id: string
  coi_categories: CoiCategory[]
  coding_reason: string
}

export async function getAiCodingItems(sessionId: string): Promise<AiCodingItem[]> {
  return http.get<AiCodingItem[]>(
    `/api/admin/coi-ai-coding/sessions/${encodeURIComponent(sessionId)}`,
  )
}

export async function generateAiCodes(
  sessionId: string,
  unitIds: string[],
): Promise<AiCodingResponse> {
  return http.post<AiCodingResponse>(
    `/api/admin/coi-ai-coding/sessions/${encodeURIComponent(sessionId)}/generate`,
    { unit_ids: unitIds },
  )
}

export async function reviewAiCodingUnits(
  sessionId: string,
  unitIds: string[],
): Promise<AiCodingResponse> {
  return http.post<AiCodingResponse>(
    `/api/admin/coi-ai-coding/sessions/${encodeURIComponent(sessionId)}/review-units`,
    { unit_ids: unitIds },
  )
}

export async function saveAiCodeAdjustments(
  sessionId: string,
  codes: AiCodeAdjustment[],
): Promise<AiCodingResponse> {
  return http.put<AiCodingResponse>(
    `/api/admin/coi-ai-coding/sessions/${encodeURIComponent(sessionId)}/codes`,
    { codes },
  )
}
