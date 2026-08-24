import { http } from '../http'
import type {
  CoiAnalysisCoderRole,
  CoiAnalysisMode,
  ExcludedSession,
  MetricSummary,
  PostHocResult,
  StatisticalTestResult,
} from './coi-analysis'

export interface CoiCompositionObservation {
  session_id: string
  group_id: string
  condition: string
  te_count: number
  ex_count: number
  in_count: number
  re_count: number
  unit_count: number
  total_count: number
  te_ratio: number
  ex_ratio: number
  in_ratio: number
  re_ratio: number
}

export interface CompositionGlobalTest {
  method: string
  statistic_name: string
  statistic: number | null
  p_value: number | null
  effect_size_name: string
  effect_size: number | null
  permutations: number
  status: 'ok' | 'insufficient_data' | 'dependency_missing' | 'calculation_error'
  note: string
}

export interface CoiCompositionAnalysisResult {
  mode: CoiAnalysisMode
  conditions: string[]
  total_sessions: number
  sessions_by_condition: Record<string, number>
  excluded_sessions: ExcludedSession[]
  metrics: MetricSummary[]
  statistical_tests: StatisticalTestResult[]
  post_hoc_tests: PostHocResult[]
  observations: CoiCompositionObservation[]
  global_test: CompositionGlobalTest
}

export interface CreateCoiCompositionPayload {
  mode: CoiAnalysisMode
  group_ids_by_condition: Record<string, string[]>
  coder_role?: CoiAnalysisCoderRole
}

export async function createCoiCompositionAnalysis(
  payload: CreateCoiCompositionPayload,
): Promise<CoiCompositionAnalysisResult> {
  return http.post('/api/admin/coi-analysis/composition/', payload)
}
