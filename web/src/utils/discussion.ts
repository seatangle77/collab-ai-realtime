import type { TagProps } from 'element-plus'
import type { DiscussionStateType } from '../types/admin'

export const DISCUSSION_STATE_LABELS: Record<DiscussionStateType, string> = {
  low_participation: '低参与度',
  over_dominance: '过度主导',
  disengaged: '脱离讨论',
  deadlock: '讨论僵局',
  topic_drift: '话题偏移',
  low_depth: '深度不足',
  homogeneous: '观点同质',
}

export const DISCUSSION_STATE_TAGS: Record<DiscussionStateType, TagProps['type']> = {
  low_participation: 'warning',
  over_dominance: 'danger',
  disengaged: 'info',
  deadlock: 'danger',
  topic_drift: 'warning',
  low_depth: 'info',
  homogeneous: 'info',
}
