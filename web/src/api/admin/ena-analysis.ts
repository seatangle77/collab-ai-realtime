import { http } from '../http'

export type EnaAnalysisMode = 'two_conditions' | 'three_conditions'
export type NormalityStatus = 'ok' | 'insufficient_n' | 'constant_values' | 'dependency_missing'
export type RecommendedTest =
  | 'independent_samples_t_test'
  | 'mann_whitney_u'
  | 'one_way_anova'
  | 'kruskal_wallis'
  | 'insufficient_data'
export type StatTestStatus = 'ok' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
export type PostHocStatus = 'ok' | 'not_applicable' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
export type PostHocMethod = 'tukey_hsd' | 'dunn_bonferroni'

export interface MetricConditionStats {
  condition: string
  n: number
  mean: number | null
  sd: number | null
  median: number | null
  min: number | null
  max: number | null
}

export interface EnaMetricSummary {
  metric: string
  label: string
  conditions: MetricConditionStats[]
}

export interface EnaNormalityResult {
  metric: string
  label: string
  condition: string
  n: number
  test: 'shapiro_wilk'
  statistic: number | null
  p_value: number | null
  is_normal: boolean | null
  alpha: number
  status: NormalityStatus
  note: string
}

export interface EnaStatTestResult {
  metric: string
  label: string
  test: RecommendedTest
  statistic_name: string | null
  statistic: number | null
  p_value: number | null
  p_value_adjusted: number | null
  effect_size_name: string | null
  effect_size: number | null
  status: StatTestStatus
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

export interface EnaPostHocResult {
  metric: string
  label: string
  method: PostHocMethod | null
  pairs: PostHocPairResult[]
  status: PostHocStatus
  note: string
}

export interface EnaEdge {
  source: string
  target: string
  weight: number
  weight_diff: number | null
}

export interface EnaNetworkCondition {
  condition: string
  nodes: string[]
  edges: EnaEdge[]
}

export interface EnaObservation {
  session_id: string
  group_id: string
  condition: string
  ex_in_strength: number
  in_re_strength: number
  higher_order_strength: number
  total_windows: number
}

export interface EnaAnalysisResult {
  mode: EnaAnalysisMode
  conditions: string[]
  total_sessions: number
  sessions_by_condition: Record<string, number>
  observations: EnaObservation[]
  metrics: EnaMetricSummary[]
  normality: EnaNormalityResult[]
  test_recommendations: EnaStatTestResult[]
  statistical_tests: EnaStatTestResult[]
  post_hoc_tests: EnaPostHocResult[]
  networks: EnaNetworkCondition[]
  diff_network: EnaNetworkCondition | null
  charts: Record<string, string>
}

export interface CreateEnaAnalysisPayload {
  mode: EnaAnalysisMode
  group_ids_by_condition: Record<string, string[]>
}

export async function createEnaAnalysis(payload: CreateEnaAnalysisPayload): Promise<EnaAnalysisResult> {
  return http.post('/api/admin/ena-analysis/', payload)
}
