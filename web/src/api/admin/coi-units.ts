import { http } from '../http'

export type CoiCategory = 'TE' | 'EX' | 'IN' | 'RE' | 'OTHER'
export type CoiCoderRole = 'coder_a' | 'coder_b' | 'coder_c' | 'final'

export interface CoiUnitIn {
  order_index: number
  content: string
  speaker?: string | null
  speaker_user_id?: string | null
  source_transcript_ids?: string[]
  start_time?: number | null
}

export interface CoiUnit {
  id: string
  session_id: string
  group_id: string
  speaker: string | null
  speaker_user_id: string | null
  content: string
  source_transcript_ids: string[]
  order_index: number
  start_time: number | null
  created_at: string
  updated_at: string
}

export interface SaveUnitsResponse {
  saved: number
  deleted_previous: number
  deleted_codes: number
}

export interface ImportUnitsResponse {
  imported: number
  deleted_previous: number
  deleted_codes: number
}

export interface UnitMutationResponse {
  units: CoiUnit[]
  invalidated_codes: number
}

export interface CoiCodeIn {
  unit_id: string
  coi_categories: CoiCategory[]
  coded_by?: string | null
}

export interface CoiCode {
  unit_id: string
  coder_role: CoiCoderRole
  coi_categories: CoiCategory[]
  coded_by: string | null
  coded_at: string
  updated_at: string
}

export interface SaveCodesResponse {
  saved: number
  coder_role: CoiCoderRole
}

export interface UnitWithCode {
  unit: CoiUnit
  code: CoiCode | null
}

export interface AgreementUnit {
  unit: CoiUnit
  coder_a: CoiCode | null
  coder_b: CoiCode | null
  coder_c: CoiCode | null
  final: CoiCode | null
  agreed: boolean
}

export interface CoiUnitSessionSummary {
  session_id: string
  session_title: string
  group_id: string
  group_name: string
  units_total: number
  coder_a_coded: number
  coder_b_coded: number
  final_coded: number
}

export async function listCoiUnitSessionsSummary(): Promise<CoiUnitSessionSummary[]> {
  return http.get<CoiUnitSessionSummary[]>('/api/admin/coi-units/sessions-summary')
}

export async function listCoiUnits(sessionId: string): Promise<CoiUnit[]> {
  return http.get<CoiUnit[]>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}`,
  )
}

export async function importCoiUnitsFromPreprocess(sessionId: string): Promise<ImportUnitsResponse> {
  return http.post<ImportUnitsResponse>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}/import-from-preprocess`,
  )
}

export async function saveCoiUnits(
  sessionId: string,
  units: CoiUnitIn[],
): Promise<SaveUnitsResponse> {
  return http.put<SaveUnitsResponse>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}`,
    { units },
  )
}

export async function splitCoiUnit(
  sessionId: string,
  unitId: string,
  firstContent: string,
  secondContent: string,
): Promise<UnitMutationResponse> {
  const query = new URLSearchParams({ coder_role: 'coder_a' })
  return http.post<UnitMutationResponse>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}/units/${encodeURIComponent(unitId)}/split?${query.toString()}`,
    { first_content: firstContent, second_content: secondContent },
  )
}

export async function mergeCoiUnitWithNext(
  sessionId: string,
  unitId: string,
): Promise<UnitMutationResponse> {
  const query = new URLSearchParams({ coder_role: 'coder_a' })
  return http.post<UnitMutationResponse>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}/units/${encodeURIComponent(unitId)}/merge-next?${query.toString()}`,
  )
}

export async function getCoiCodes(
  sessionId: string,
  coderRole: CoiCoderRole,
): Promise<UnitWithCode[]> {
  const query = new URLSearchParams({ coder_role: coderRole })
  return http.get<UnitWithCode[]>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}/codes?${query.toString()}`,
  )
}

export async function saveCoiCodes(
  sessionId: string,
  coderRole: CoiCoderRole,
  codes: CoiCodeIn[],
): Promise<SaveCodesResponse> {
  const query = new URLSearchParams({ coder_role: coderRole })
  return http.put<SaveCodesResponse>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}/codes?${query.toString()}`,
    { codes },
  )
}

export async function getCoiAgreement(sessionId: string): Promise<AgreementUnit[]> {
  return http.get<AgreementUnit[]>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}/agreement`,
  )
}

export async function saveFinalCoiCodes(
  sessionId: string,
  codes: CoiCodeIn[],
): Promise<SaveCodesResponse> {
  return http.put<SaveCodesResponse>(
    `/api/admin/coi-units/sessions/${encodeURIComponent(sessionId)}/final-codes`,
    { codes },
  )
}
