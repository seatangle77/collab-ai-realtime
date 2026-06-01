import { http } from '../http'

export type TaskScoreAnalysisMode = 'two_conditions' | 'three_conditions'
export type TaskScoreAnalysisTaskId = 'all' | 'moon_survival' | 'lost_at_sea' | 'winter_survival'
export type TaskScoreMetricRole = 'primary' | 'baseline'
export type TaskScoreNormalityStatus = 'ok' | 'insufficient_n' | 'constant_values' | 'dependency_missing'
export type TaskScoreRecommendedTest =
  | 'independent_samples_t_test'
  | 'mann_whitney_u'
  | 'one_way_anova'
  | 'kruskal_wallis'
  | 'insufficient_data'
export type TaskScoreStatisticalTestStatus = 'ok' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
export type TaskScorePostHocStatus = 'ok' | 'not_applicable' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
export type TaskScorePostHocMethod = 'tukey_hsd' | 'dunn_bonferroni'

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
  role: TaskScoreMetricRole
  conditions: MetricConditionStats[]
}

export interface NormalityConditionResult {
  metric: string
  label: string
  role: TaskScoreMetricRole
  condition: string
  n: number
  test: 'shapiro_wilk'
  statistic: number | null
  p_value: number | null
  is_normal: boolean | null
  alpha: number
  status: TaskScoreNormalityStatus
  note: string
}

export interface StatisticalTestRecommendation {
  metric: string
  label: string
  role: TaskScoreMetricRole
  recommended_test: TaskScoreRecommendedTest
  normality_assumption_met: boolean | null
  conditions: string[]
  note: string
}

export interface StatisticalTestResult {
  metric: string
  label: string
  role: TaskScoreMetricRole
  test: TaskScoreRecommendedTest
  statistic_name: string | null
  statistic: number | null
  p_value: number | null
  effect_size_name: string | null
  effect_size: number | null
  status: TaskScoreStatisticalTestStatus
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
  role: TaskScoreMetricRole
  method: TaskScorePostHocMethod | null
  pairs: PostHocPairResult[]
  status: TaskScorePostHocStatus
  note: string
}

export interface TaskScoreObservation {
  entry_id: string
  group_id: string
  task_id: string
  condition: string
  gs: number
  ais: number
  best_is: number
  weak_synergy: number
  strong_synergy: number
}

export interface TaskScoreAnalysisResult {
  mode: TaskScoreAnalysisMode
  task_id: TaskScoreAnalysisTaskId
  conditions: string[]
  total_entries: number
  entries_by_condition: Record<string, number>
  metrics: MetricSummary[]
  normality: NormalityConditionResult[]
  test_recommendations: StatisticalTestRecommendation[]
  statistical_tests: StatisticalTestResult[]
  post_hoc_tests: PostHocResult[]
  observations: TaskScoreObservation[]
  charts: Record<string, string>
}

export interface GetTaskScoreAnalysisParams {
  mode: TaskScoreAnalysisMode
  task_id: TaskScoreAnalysisTaskId
}

export interface CreateTaskScoreAnalysisPayload extends GetTaskScoreAnalysisParams {
  group_ids_by_condition: Record<string, string[]>
}

export async function getTaskScoreAnalysis(params: GetTaskScoreAnalysisParams): Promise<TaskScoreAnalysisResult> {
  const query = new URLSearchParams({
    mode: params.mode,
    task_id: params.task_id,
  })
  return http.get<TaskScoreAnalysisResult>(`/api/admin/task-score-analysis/?${query.toString()}`)
}

export async function createTaskScoreAnalysis(
  payload: CreateTaskScoreAnalysisPayload,
): Promise<TaskScoreAnalysisResult> {
  return http.post<TaskScoreAnalysisResult>('/api/admin/task-score-analysis/', payload)
}
