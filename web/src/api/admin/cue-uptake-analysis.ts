import { http } from '../http'
export type Condition = 'glasses' | 'app_notification'
export type Design = 'descriptive' | 'independent' | 'paired'
export type Metric = 'adoption_rate' | 'discussion_rate' | 'conditional_adoption_rate'
export interface Counts {
  total: number; valid: number; not_discussed: number; discussed_not_adopted: number; discussed_adopted: number
  uncertain: number; not_included: number; uncoded: number; duplicate_count: number
  adoption_rate: number | null; discussion_rate: number | null; conditional_adoption_rate: number | null
}
export interface GroupSummary extends Counts {
  group_id: string; group_name: string; condition: Condition; session_count: number; session_id?: string; session_title?: string
}
export interface Distribution { n: number; mean: number | null; sd: number | null; median: number | null; q1: number | null; q3: number | null }
export interface ConditionSummary extends Counts { condition: Condition; group_count: number; session_count: number; stats: Record<Metric, Distribution> }
export interface CueAnalysisEvent {
  push_log_id: string; group_id: string; group_name: string; condition: Condition; session_id: string; session_title: string | null
  target_user_name: string; push_content: string; state_type: string; received_at: string; code: string | null
  evidence_ids: string[]; evidence_text: string; missing_evidence_count: number; coding_reason: string | null
  coded_by: string | null; coded_at: string | null; possible_duplicate: boolean
}
export interface Comparison {
  metric: Metric; design: Design; n_glasses: number; n_app: number; dropped_pairs: number; difference: number | null
  t_statistic: number | null; degrees_of_freedom: number | null; ci_low: number | null; ci_high: number | null; p_value: number | null; method: string; status: string
}
export interface AnalysisRequest {
  conditions?: Condition[]; group_ids?: string[]; session_ids?: string[]; design: Design
  pairs?: { glasses: string; app_notification: string }[]
}
export interface CueAnalysisReport {
  generated_at: string; version: string; design: Design; pairs: { glasses: string; app_notification: string }[]
  scope: AnalysisRequest; totals: Counts; groups: GroupSummary[]; sessions: GroupSummary[]
  conditions: ConditionSummary[]; comparisons: Comparison[]; events: CueAnalysisEvent[]
}
export const getCueAnalysis = (request: AnalysisRequest) => http.post<CueAnalysisReport>('/api/admin/cue-uptake-analysis/report', request)
