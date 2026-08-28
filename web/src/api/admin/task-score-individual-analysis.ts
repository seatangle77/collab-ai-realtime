import { http } from '../http'
import type { TaskScoreAnalysisMode, TaskScoreAnalysisTaskId, MetricConditionStats } from './task-score-analysis'

export interface IndividualScoreObservation {
  entry_id: string
  group_id: string
  task_id: string
  condition: string
  participant_id: string
  participant_name: string | null
  score: number
}

export interface IndividualTaskSummary {
  task_id: string
  conditions: MetricConditionStats[]
}

export interface IndividualAisConsistency {
  checked_groups: number
  consistent_groups: number
  max_absolute_difference: number | null
  status: 'ok' | 'warning' | 'not_available'
  note: string
}

export interface IndividualClusterTest {
  method: string
  statistic_name: string
  statistic: number | null
  p_value: number | null
  effect_size_name: string
  effect_size: number | null
  permutations: number
  cluster_unit: 'group'
  status: 'ok' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
  note: string
}

export interface IndividualPairwiseResult {
  condition_a: string
  condition_b: string
  mean_difference: number | null
  p_value: number | null
  p_value_adjusted: number | null
  significant: boolean | null
  method: string
}

export interface IndividualScoreExcludedEntry {
  entry_id: string
  group_id: string
  task_id: string
  condition: string
  reason: string
  note: string
}

export interface TaskScoreIndividualAnalysisResult {
  mode: TaskScoreAnalysisMode
  task_id: TaskScoreAnalysisTaskId
  conditions: string[]
  total_groups: number
  total_individuals: number
  groups_by_condition: Record<string, number>
  individuals_by_condition: Record<string, number>
  score_direction: 'lower_is_better'
  individual_stats: MetricConditionStats[]
  task_summaries: IndividualTaskSummary[]
  ais_consistency: IndividualAisConsistency
  statistical_test: IndividualClusterTest
  pairwise_tests: IndividualPairwiseResult[]
  observations: IndividualScoreObservation[]
  excluded_entries: IndividualScoreExcludedEntry[]
}

export interface CreateTaskScoreIndividualAnalysisPayload {
  mode: TaskScoreAnalysisMode
  task_id: TaskScoreAnalysisTaskId
  group_ids_by_condition: Record<string, string[]>
}

export async function createTaskScoreIndividualAnalysis(
  payload: CreateTaskScoreIndividualAnalysisPayload,
): Promise<TaskScoreIndividualAnalysisResult> {
  return http.post<TaskScoreIndividualAnalysisResult>('/api/admin/task-score-individual-analysis/', payload)
}
