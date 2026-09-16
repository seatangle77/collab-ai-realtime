import { http } from '../http'
export const conditions = ['no_assistance', 'glasses', 'app_notification'] as const
export type Condition = typeof conditions[number]
export type Metric = 'mattr_100' | 'mtld' | 'token_count' | 'type_count' | 'ttr'
export interface Selection { group_ids_by_condition: Record<string, string[]>; task_id: string }
export interface Observation {
  group_id: string; group_name: string; condition: Condition; session_id: string | null;
  session_title: string | null; task_id: string | null; token_count: number; type_count: number;
  ttr: number; mattr_100: number; mtld: number | null; window_count: number;
  utterance_count: number; source_hash: string; token_hash: string
}
export interface Excluded { group_id: string; group_name: string; condition: Condition; session_id: string | null; task_id: string | null; reason: string; token_count: number | null; source_hash: string }
export interface Summary { metric: Metric; condition: Condition; n: number; mean: number | null; sd: number | null; median: number | null; min: number | null; max: number | null }
export interface Pair { condition_a: Condition; condition_b: Condition; difference: number; p_value: number; p_adjusted: number; ci_low: number; ci_high: number }
export interface Test { metric: Metric; n: number; status: string; statistic: number | null; p_value: number | null; eta_squared: number | null; pairs: Pair[]; permutations: number }
export interface Report { generated_at: string; source_hash: string; selection: Selection; parameters: Record<string, unknown>; observations: Observation[]; excluded: Excluded[]; summaries: Summary[]; tests: Test[] }
export const analyzeLexical = (selection: Selection) => http.post<Report>('/api/admin/lexical-diversity/', selection)
