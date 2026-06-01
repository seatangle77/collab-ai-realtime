import { http } from '../http'

export type CoiAnalysisMode = 'two_conditions' | 'three_conditions'
export type CoiNormalityStatus = 'ok' | 'insufficient_n' | 'constant_values' | 'dependency_missing'
export type CoiRecommendedTest =
  | 'independent_samples_t_test'
  | 'mann_whitney_u'
  | 'one_way_anova'
  | 'kruskal_wallis'
  | 'insufficient_data'
export type CoiStatisticalTestStatus = 'ok' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
export type CoiPostHocStatus = 'ok' | 'not_applicable' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
export type CoiPostHocMethod = 'tukey_hsd' | 'dunn_bonferroni'

export interface ExcludedSession {
  session_id: string
  group_id: string
  group_name: string | null
  condition: string
  uncoded_count: number
  total_count: number
}

export interface MetricConditionStats {
  condition: string
  n: number
  mean: number | null
  sd: number | null
  median: number | null
  min: number | null
  max: number | null
}

export interface MetricSummary {
  metric: string
  label: string
  conditions: MetricConditionStats[]
}

export interface NormalityConditionResult {
  metric: string
  label: string
  condition: string
  n: number
  test: 'shapiro_wilk'
  statistic: number | null
  p_value: number | null
  is_normal: boolean | null
  alpha: number
  status: CoiNormalityStatus
  note: string
}

export interface StatisticalTestResult {
  metric: string
  label: string
  test: CoiRecommendedTest
  statistic_name: string | null
  statistic: number | null
  p_value: number | null
  effect_size_name: string | null
  effect_size: number | null
  status: CoiStatisticalTestStatus
  note: string
}

export interface PostHocPairResult {
  condition_a: string
  condition_b: string
  mean_diff: number | null
  p_value_adjusted: number | null
  significant: boolean | null
  alpha: number
}

export interface PostHocResult {
  metric: string
  label: string
  method: CoiPostHocMethod | null
  pairs: PostHocPairResult[]
  status: CoiPostHocStatus
  note: string
}

export interface CoiAnalysisResult {
  mode: CoiAnalysisMode
  conditions: string[]
  total_sessions: number
  sessions_by_condition: Record<string, number>
  excluded_sessions: ExcludedSession[]
  metrics: MetricSummary[]
  normality: NormalityConditionResult[]
  statistical_tests: StatisticalTestResult[]
  post_hoc_tests: PostHocResult[]
  charts: Record<string, string>
}

export interface CreateCoiAnalysisPayload {
  mode: CoiAnalysisMode
  group_ids_by_condition: Record<string, string[]>
}

export async function createCoiAnalysis(payload: CreateCoiAnalysisPayload): Promise<CoiAnalysisResult> {
  return http.post('/api/admin/coi-analysis/', payload)
}
