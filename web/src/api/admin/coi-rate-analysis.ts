import { http } from '../http'
import type { CoiAnalysisCoderRole, CoiAnalysisMode, MetricConditionStats } from './coi-analysis'

export type CoiRateMetric = 'total_rate' | 'te_rate' | 'ex_rate' | 'in_rate' | 're_rate' | 'other_rate'

export interface CoiRateExcludedSession {
  session_id: string
  group_id: string
  group_name: string | null
  condition: string
  reason: 'incomplete_coding' | 'missing_start_time' | 'missing_end_time' | 'invalid_duration'
  note: string
  uncoded_count: number
  total_units: number
}

export interface CoiRateObservation {
  session_id: string
  session_title: string | null
  group_id: string
  group_name: string | null
  condition: string
  started_at: string
  ended_at: string
  duration_minutes: number
  coded_unit_count: number
  phase_code_count: number
  other_count: number
  te_count: number
  ex_count: number
  in_count: number
  re_count: number
  total_rate: number
  other_rate: number
  te_rate: number
  ex_rate: number
  in_rate: number
  re_rate: number
}

export interface CoiRateMetricSummary {
  metric: CoiRateMetric
  label: string
  unit: 'codes_per_minute'
  conditions: MetricConditionStats[]
}

export interface CoiRatePermutationTest {
  metric: Exclude<CoiRateMetric, 'other_rate'>
  label: string
  method: string
  statistic_name: string
  statistic: number | null
  p_value: number | null
  p_value_adjusted: number | null
  effect_size_name: string
  effect_size: number | null
  permutations: number
  status: 'ok' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
  note: string
}

export interface CoiRateContrast {
  metric: Exclude<CoiRateMetric, 'other_rate'>
  label: string
  reference_condition: 'no_assistance'
  comparison_condition: string
  reference_mean: number
  comparison_mean: number
  mean_difference: number
  rate_ratio: number | null
  ci_low: number | null
  ci_high: number | null
  confidence_level: number
  method: string
}

export interface CoiRateAnalysisResult {
  mode: CoiAnalysisMode
  conditions: string[]
  duration_source: string
  total_sessions: number
  sessions_by_condition: Record<string, number>
  excluded_sessions: CoiRateExcludedSession[]
  duration_stats: MetricConditionStats[]
  metrics: CoiRateMetricSummary[]
  statistical_tests: CoiRatePermutationTest[]
  contrasts: CoiRateContrast[]
  observations: CoiRateObservation[]
}

export interface CreateCoiRateAnalysisPayload {
  mode: CoiAnalysisMode
  group_ids_by_condition: Record<string, string[]>
  coder_role?: CoiAnalysisCoderRole
}

export async function createCoiRateAnalysis(
  payload: CreateCoiRateAnalysisPayload,
): Promise<CoiRateAnalysisResult> {
  return http.post('/api/admin/coi-analysis/rate/', payload)
}
