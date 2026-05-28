import { appHttp } from './appHttp'

export interface ScaleItem {
  id: string
  dimension: string
  en: string
  zh: string
}

export interface ScaleMeta {
  srcc_items: ScaleItem[]
  pcs_items: ScaleItem[]
  srcc_dimensions: Record<string, string>
  pcs_dimensions: Record<string, string>
}

export interface QuestionnaireEntry {
  user_id: string
  group_id: string | null
  condition: string | null
  srcc_responses: Record<string, number | null> | null
  srcc_result: Record<string, number | null> | null
  pcs_responses: Record<string, number | null> | null
  pcs_result: Record<string, number | null> | null
  updated_at: string | null
}

export type SrccResponses = Record<string, number | null>
export type PcsResponses = Record<string, number | null>

export async function fetchScaleMeta(): Promise<ScaleMeta> {
  return appHttp.get<ScaleMeta>('/api/questionnaire/meta')
}

export async function fetchMyEntry(): Promise<QuestionnaireEntry> {
  return appHttp.get<QuestionnaireEntry>('/api/questionnaire/me')
}

export async function submitSrcc(responses: SrccResponses): Promise<QuestionnaireEntry> {
  return appHttp.post<QuestionnaireEntry>('/api/questionnaire/srcc', { responses })
}

export async function submitPcs(responses: PcsResponses): Promise<QuestionnaireEntry> {
  return appHttp.post<QuestionnaireEntry>('/api/questionnaire/pcs', { responses })
}
