import { http } from '../http'

export type QuestionnaireAnalysisMode = 'two_conditions' | 'three_conditions'
export type QuestionnaireScaleKind = 'srcc' | 'pcs'
export type QNormalityStatus = 'ok' | 'insufficient_n' | 'constant_values' | 'dependency_missing'
export type QRecommendedTest =
  | 'independent_samples_t_test'
  | 'mann_whitney_u'
  | 'one_way_anova'
  | 'kruskal_wallis'
  | 'insufficient_data'
export type QStatisticalTestStatus = 'ok' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
export type QPostHocStatus = 'ok' | 'not_applicable' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
export type QPostHocMethod = 'tukey_hsd' | 'dunn_bonferroni'
export type QCronbachStatus = 'ok' | 'insufficient_n' | 'insufficient_items' | 'constant_values'

export interface QMetricConditionStats {
  condition: string
  n: number
  mean: number | null
  sd: number | null
  median: number | null
  min: number | null
  max: number | null
}

export interface QMetricSummary {
  metric: string
  label: string
  conditions: QMetricConditionStats[]
}

export interface QCronbachAlphaResult {
  metric: string
  label: string
  n_items: number
  n_obs: number
  alpha: number | null
  status: QCronbachStatus
  note: string
}

export interface QNormalityConditionResult {
  metric: string
  label: string
  condition: string
  n: number
  test: 'shapiro_wilk'
  statistic: number | null
  p_value: number | null
  is_normal: boolean | null
  alpha: number
  status: QNormalityStatus
  note: string
}

export interface QStatisticalTestRecommendation {
  metric: string
  label: string
  recommended_test: QRecommendedTest
  normality_assumption_met: boolean | null
  conditions: string[]
  note: string
}

export interface QStatisticalTestResult {
  metric: string
  label: string
  test: QRecommendedTest
  statistic_name: string | null
  statistic: number | null
  p_value: number | null
  effect_size_name: string | null
  effect_size: number | null
  status: QStatisticalTestStatus
  note: string
}

export interface QPostHocPairResult {
  condition_a: string
  condition_b: string
  mean_diff: number | null
  p_value_adjusted: number | null
  significant: boolean | null
  alpha: number
}

export interface QPostHocResult {
  metric: string
  label: string
  method: QPostHocMethod | null
  pairs: QPostHocPairResult[]
  status: QPostHocStatus
  note: string
}

export interface QuestionnaireAnalysisResult {
  scale: QuestionnaireScaleKind
  mode: QuestionnaireAnalysisMode
  conditions: string[]
  total_entries: number
  entries_by_condition: Record<string, number>
  metrics: QMetricSummary[]
  reliability: QCronbachAlphaResult[]
  normality: QNormalityConditionResult[]
  test_recommendations: QStatisticalTestRecommendation[]
  statistical_tests: QStatisticalTestResult[]
  post_hoc_tests: QPostHocResult[]
  charts: Record<string, string>
}

export interface CreateQuestionnaireAnalysisPayload {
  scale: QuestionnaireScaleKind
  mode: QuestionnaireAnalysisMode
  group_ids_by_condition: Record<string, string[]>
}

export async function getQuestionnaireAnalysis(
  scale: QuestionnaireScaleKind,
  mode: QuestionnaireAnalysisMode,
): Promise<QuestionnaireAnalysisResult> {
  const query = new URLSearchParams({ scale, mode })
  return http.get<QuestionnaireAnalysisResult>(`/api/admin/questionnaire-analysis/?${query.toString()}`)
}

export async function createQuestionnaireAnalysis(
  payload: CreateQuestionnaireAnalysisPayload,
): Promise<QuestionnaireAnalysisResult> {
  return http.post<QuestionnaireAnalysisResult>('/api/admin/questionnaire-analysis/', payload)
}
