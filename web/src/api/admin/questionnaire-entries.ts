import { http } from '../http'

export interface QuestionnaireEntryAdmin {
  user_id: string
  user_name: string | null
  group_id: string | null
  group_name: string | null
  condition: string | null
  srcc_responses: Record<string, number | null> | null
  srcc_result: Record<string, number | null> | null
  pcs_responses: Record<string, number | null> | null
  pcs_result: Record<string, number | null> | null
  updated_at: string | null
}

export interface QuestionnaireEntryListParams {
  group_id?: string
  condition?: string
  updated_from?: string
  updated_to?: string
  page?: number
  page_size?: number
}

export interface QuestionnaireEntryListResult {
  items: QuestionnaireEntryAdmin[]
  meta: { total: number; page: number; page_size: number }
}

export async function listQuestionnaireEntries(
  params?: QuestionnaireEntryListParams,
): Promise<QuestionnaireEntryListResult> {
  return http.get<QuestionnaireEntryListResult>('/api/admin/questionnaire-entries', { params })
}

export async function deleteQuestionnaireEntry(userId: string): Promise<void> {
  await http.delete(`/api/admin/questionnaire-entries/${userId}`)
}
