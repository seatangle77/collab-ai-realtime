import type { TagProps } from 'element-plus'
import type { DiscussionStateType } from '../types/admin'

export interface DiscussionStateMeta {
  labelZh: string
  labelEn: string
  tag: TagProps['type']
}

export interface TriggerTypeMeta {
  productKey: string
  labelZh: string
  labelEn: string
}

export const TRIGGER_TYPE_META: Record<string, TriggerTypeMeta> = {
  group_silence: {
    productKey: 'group_stagnation',
    labelZh: '全组思路停滞',
    labelEn: 'group_stagnation',
  },
  stagnation: {
    productKey: 'individual_stagnation',
    labelZh: '个人思路停滞',
    labelEn: 'individual_stagnation',
  },
  low_participation: {
    productKey: 'individual_stagnation',
    labelZh: '个人思路停滞',
    labelEn: 'individual_stagnation',
  },
  shallow: {
    productKey: 'shallow_discussion',
    labelZh: '阐述浅薄',
    labelEn: 'shallow_discussion',
  },
  shallow_discussion: {
    productKey: 'shallow_discussion',
    labelZh: '阐述浅薄',
    labelEn: 'shallow_discussion',
  },
  info_gap: {
    productKey: 'information_gap',
    labelZh: '信息缺口',
    labelEn: 'information_gap',
  },
}

export const DISCUSSION_STATE_META: Record<DiscussionStateType, DiscussionStateMeta> = {
  stagnation: {
    labelZh: '个人思路停滞',
    labelEn: 'individual_stagnation',
    tag: 'warning',
  },
  shallow: {
    labelZh: '阐述浅薄',
    labelEn: 'shallow_discussion',
    tag: 'info',
  },
  none: {
    labelZh: '无需干预',
    labelEn: 'none',
    tag: 'info',
  },
  low_participation: {
    labelZh: '个人思路停滞',
    labelEn: 'individual_stagnation',
    tag: 'warning',
  },
  over_dominance: {
    labelZh: '过度主导',
    labelEn: 'over_dominance',
    tag: 'danger',
  },
  disengaged: {
    labelZh: '脱离讨论',
    labelEn: 'disengaged',
    tag: 'info',
  },
  deadlock: {
    labelZh: '讨论僵局',
    labelEn: 'deadlock',
    tag: 'danger',
  },
  topic_drift: {
    labelZh: '话题偏移',
    labelEn: 'topic_drift',
    tag: 'warning',
  },
  low_depth: {
    labelZh: '深度不足',
    labelEn: 'low_depth',
    tag: 'info',
  },
  homogeneous: {
    labelZh: '观点同质',
    labelEn: 'homogeneous',
    tag: 'info',
  },
}

export const DISCUSSION_STATE_LABELS: Record<DiscussionStateType, string> = {
  stagnation: DISCUSSION_STATE_META.stagnation.labelZh,
  shallow: DISCUSSION_STATE_META.shallow.labelZh,
  none: DISCUSSION_STATE_META.none.labelZh,
  low_participation: DISCUSSION_STATE_META.low_participation.labelZh,
  over_dominance: DISCUSSION_STATE_META.over_dominance.labelZh,
  disengaged: DISCUSSION_STATE_META.disengaged.labelZh,
  deadlock: DISCUSSION_STATE_META.deadlock.labelZh,
  topic_drift: DISCUSSION_STATE_META.topic_drift.labelZh,
  low_depth: DISCUSSION_STATE_META.low_depth.labelZh,
  homogeneous: DISCUSSION_STATE_META.homogeneous.labelZh,
}

export const DISCUSSION_STATE_TAGS: Record<DiscussionStateType, TagProps['type']> = {
  stagnation: DISCUSSION_STATE_META.stagnation.tag,
  shallow: DISCUSSION_STATE_META.shallow.tag,
  none: DISCUSSION_STATE_META.none.tag,
  low_participation: DISCUSSION_STATE_META.low_participation.tag,
  over_dominance: DISCUSSION_STATE_META.over_dominance.tag,
  disengaged: DISCUSSION_STATE_META.disengaged.tag,
  deadlock: DISCUSSION_STATE_META.deadlock.tag,
  topic_drift: DISCUSSION_STATE_META.topic_drift.tag,
  low_depth: DISCUSSION_STATE_META.low_depth.tag,
  homogeneous: DISCUSSION_STATE_META.homogeneous.tag,
}

export function getDiscussionStateLabel(stateType: string | null | undefined): string {
  if (!stateType) return '未知状态'
  return (DISCUSSION_STATE_LABELS as Record<string, string>)[stateType] ?? stateType
}
