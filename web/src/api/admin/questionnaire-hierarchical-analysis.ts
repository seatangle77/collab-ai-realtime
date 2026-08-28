import { http } from '../http'
import type {
  QMetricConditionStats,
  QStatisticalTestResult,
  QuestionnaireAnalysisMode,
  QuestionnaireAnalysisResult,
  QuestionnaireScaleKind,
} from './questionnaire-analysis'

export type HierarchicalAnalysisStatus =
  | 'ok'
  | 'insufficient_data'
  | 'constant_values'
  | 'dependency_missing'
  | 'calculation_error'

export interface ConditionSampleSummary {
  condition: string
  participant_count: number
  group_count: number
  min_group_size: number | null
  max_group_size: number | null
  mean_group_size: number | null
}

export interface GroupMeanObservation {
  metric: string
  group_id: string
  condition: string
  participant_count: number
  value: number
}

export interface PairwiseContrast {
  condition_a: string
  condition_b: string
  estimate: number | null
  standard_error: number | null
  ci_low: number | null
  ci_high: number | null
  p_value: number | null
  p_value_adjusted: number | null
  significant: boolean | null
}

export interface HierarchicalTestResult {
  metric: string
  label: string
  method: string
  statistic_name: string | null
  statistic: number | null
  p_value: number | null
  p_value_adjusted: number | null
  effect_size_name: string | null
  effect_size: number | null
  status: HierarchicalAnalysisStatus
  note: string
  pairwise: PairwiseContrast[]
}

export interface GroupMeanMetricResult {
  metric: string
  label: string
  conditions: QMetricConditionStats[]
  observations: GroupMeanObservation[]
  test: HierarchicalTestResult
}

export interface ModelEstimatedMean {
  condition: string
  estimate: number
  standard_error: number
  ci_low: number
  ci_high: number
}

export interface MixedModelMetricResult {
  metric: string
  label: string
  status: HierarchicalAnalysisStatus
  participant_count: number
  group_count: number
  converged: boolean | null
  fixed_effect_test: HierarchicalTestResult
  estimated_means: ModelEstimatedMean[]
  random_intercept_variance: number | null
  residual_variance: number | null
  icc: number | null
  note: string
}

export interface QuestionnaireHierarchicalAnalysisResult {
  scale: QuestionnaireScaleKind
  mode: QuestionnaireAnalysisMode
  conditions: string[]
  participant_count: number
  group_count: number
  sample_summary: ConditionSampleSummary[]
  individual_analysis: QuestionnaireAnalysisResult
  individual_p_values_adjusted: Record<string, number | null>
  group_mean_metrics: GroupMeanMetricResult[]
  mixed_model_metrics: MixedModelMetricResult[]
  warnings: string[]
}

export interface CreateQuestionnaireHierarchicalAnalysisPayload {
  scale: QuestionnaireScaleKind
  mode: QuestionnaireAnalysisMode
  group_ids_by_condition: Record<string, string[]>
}

export function createQuestionnaireHierarchicalAnalysis(
  payload: CreateQuestionnaireHierarchicalAnalysisPayload,
): Promise<QuestionnaireHierarchicalAnalysisResult> {
  return http.post<QuestionnaireHierarchicalAnalysisResult>(
    '/api/admin/questionnaire-hierarchical-analysis/',
    payload,
  )
}

export function individualTestFor(
  report: QuestionnaireHierarchicalAnalysisResult,
  metric: string,
): QStatisticalTestResult | undefined {
  return report.individual_analysis.statistical_tests.find((item) => item.metric === metric)
}
