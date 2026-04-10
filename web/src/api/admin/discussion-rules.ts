import { http } from '../http'
import type { AdminDiscussionRule, AdminDiscussionRuleUpdate } from '../../types/admin'

export async function getDiscussionRules(): Promise<AdminDiscussionRule> {
  return http.get<AdminDiscussionRule>('/api/admin/discussion-rules/')
}

export async function updateDiscussionRules(
  payload: AdminDiscussionRuleUpdate,
): Promise<AdminDiscussionRule> {
  return http.put<AdminDiscussionRule>('/api/admin/discussion-rules/', payload)
}
