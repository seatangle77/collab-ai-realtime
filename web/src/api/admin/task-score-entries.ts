import { http } from '../http'

export interface TaskScoreIndividualAnswer {
  participant_id: string
  participant_name?: string | null
  ordered_items: string[]
}

export interface TaskScoreAnswers {
  individual: TaskScoreIndividualAnswer[]
  group_final: {
    ordered_items: string[]
  }
}

export interface TaskScoreIndividualResult {
  participant_id: string
  participant_name?: string | null
  score: number
}

export interface TaskScoreResult {
  individual_scores: TaskScoreIndividualResult[]
  ais: number
  best_is: number
  best_participant_id: string
  gs: number
  weak_synergy: number
  strong_synergy: number
  item_count: number
  score_direction: string
}

export interface TaskScoreEntryPayload {
  group_id: string
  task_id: string
  answers: TaskScoreAnswers
}

export interface AdminTaskScoreEntry {
  id: string
  group_id: string
  task_id: string
  condition: string
  answers_json: TaskScoreAnswers
  result_json: TaskScoreResult | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export async function getTaskScoreEntry(groupId: string, taskId: string): Promise<AdminTaskScoreEntry | null> {
  const query = new URLSearchParams({ group_id: groupId, task_id: taskId })
  return http.get<AdminTaskScoreEntry | null>(`/api/admin/task-score-entries/?${query.toString()}`)
}

export async function saveTaskScoreEntry(payload: TaskScoreEntryPayload): Promise<AdminTaskScoreEntry> {
  return http.post<AdminTaskScoreEntry>('/api/admin/task-score-entries/', payload)
}

