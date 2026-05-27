export interface BatchDeleteResponse {
  deleted: number
}

export interface PageMeta {
  total: number
  page: number
  page_size: number
}

export interface Page<T> {
  items: T[]
  meta: PageMeta
}

export interface AdminUser {
  id: string
  name: string
  email: string
  device_token: string | null
  created_at: string
  group_ids?: string[]
  group_names?: string[]
  password_needs_reset?: boolean
}

export interface AdminGroup {
  id: string
  name: string
  created_at: string
  is_active: boolean
  condition: string
}

export interface AdminMembership {
  id: string
  group_id: string
  user_id: string
  role: string
  status: string
  created_at: string
  group_name?: string
  user_name?: string
}

export interface AdminChatSession {
  id: string
  group_id: string
  group_name?: string | null
  session_title: string
  created_at: string
  last_updated: string
  status: 'not_started' | 'ongoing' | 'ended' | null
  started_at: string | null
  ended_at: string | null
}

export interface AdminTranscript {
  transcript_id: string
  group_id: string
  session_id: string
  user_id: string | null
  speaker: string | null
  speaker_name?: string | null
  text: string | null
  start: string
  end: string
  duration: number | null
  confidence: number | null
  is_edited: boolean
  created_at: string
  audio_url: string | null
  original_text: string | null
}

export interface AdminVoiceProfileSummary {
  id: string
  user_id: string
  user_name?: string | null
  user_email?: string | null
  primary_group_id?: string | null
  primary_group_name?: string | null
  sample_count: number
  has_embedding: boolean
  created_at: string
}

/** 声纹配置详情中的 profile 部分（与后端 VoiceProfileOut 一致） */
export interface AdminVoiceProfileDetailProfile {
  id: string
  user_id: string
  sample_audio_urls: string[]
  created_at: string
  voice_embedding: Record<string, unknown> | null
  embedding_status: string
  embedding_updated_at: string | null
}

/** 后台 GET 详情接口返回：嵌套 profile + 用户/小组信息 */
export interface AdminVoiceProfileDetail {
  profile: AdminVoiceProfileDetailProfile
  user_name?: string | null
  user_email?: string | null
  primary_group_id?: string | null
  primary_group_name?: string | null
}

// ── 讨论状态 ─────────────────────────────────────────────────────────
export interface DiscussionStateAnchor {
  transcript_id: string
  speaker_id: string
  speaker_name?: string | null
  text: string
}

export type DiscussionStateTriggerMetrics = Record<string, unknown> & {
  queued_push_id?: string
  anchor?: DiscussionStateAnchor
}

export type DiscussionStateType =
  | 'stagnation'
  | 'shallow'
  | 'none'
  | 'low_participation'
  | 'over_dominance'
  | 'disengaged'
  | 'deadlock'
  | 'topic_drift'
  | 'low_depth'
  | 'homogeneous'

export interface AdminDiscussionState {
  id: string
  session_id: string
  triggered_at: string
  state_type: DiscussionStateType
  target_user_id: string | null
  target_user_name: string | null
  trigger_metrics: DiscussionStateTriggerMetrics | null
  ai_analysis_done: boolean
  push_sent: boolean
  window_start: string | null
  push_cooldown_until: string | null
}

// ── 推送日志 ──────────────────────────────────────────────────────────
export type PushChannel = 'web' | 'app' | 'glasses' | 'info_gap'
export type DeliveryStatus = 'pending' | 'delivered' | 'failed' | 'skipped' | 'deferred'

export interface AdminPushLog {
  id: string
  session_id: string
  session_title: string | null
  state_id: string | null
  state_type: string | null
  target_user_id: string
  target_user_name: string | null
  push_content: string | null
  push_channel: PushChannel
  jpush_message_id: string | null
  delivery_status: DeliveryStatus
  delivery_reason: string | null
  triggered_at: string
  delivered_at: string | null
}

// ── 推送队列 ──────────────────────────────────────────────────────────
export type PushQueueStatus = 'pending' | 'processing' | 'delivered' | 'skipped' | 'failed' | 'deferred'

export interface AdminPushQueue {
  id: string
  session_id: string
  session_title: string | null
  target_user_id: string
  target_user_name: string | null
  state_type: DiscussionStateType
  push_content: string
  analysis_window_start: string
  status: PushQueueStatus
  created_at: string
  delivered_at: string | null
}

// ── 窗口指标 ──────────────────────────────────────────────────────────
export interface AdminWindowMetric {
  id: string
  session_id: string
  user_id: string
  user_name: string | null
  window_start: string
  window_end: string
  speaking_ratio: number | null
  silence_s: number | null
  ttr: number | null
  arg_density: number | null
  srep: number | null
  info_gain: number | null
  has_reasoning: boolean | null
  has_evidence: boolean | null
  created_at: string | null
}

export interface AdminWindowMetricsKeyword {
  id: string
  session_id: string
  window_start: string
  keyword: string
  created_at: string | null
}

export interface AdminWindowMetricsBatchReasoningMember {
  user_id: string
  reasoning_status: boolean | null
  evidence_status: boolean | null
  reasoning_source: string | null
  evidence_source: string | null
}

export interface AdminWindowMetricsBatchReasoning {
  id: string
  session_id: string
  window_start: string
  members: AdminWindowMetricsBatchReasoningMember[]
  created_at: string | null
}

// ── 讨论摘要 ──────────────────────────────────────────────────────────
export interface AdminDiscussionSummary {
  id: string
  session_id: string
  session_title: string | null
  version: number
  content: string
  window_start: string
  window_end: string
  created_at: string | null
}

// ── 信息缺口按钮 ──────────────────────────────────────────────────────
export type InfoGapButtonStatus = 'pending' | 'clicked' | 'dismissed'

export interface AdminInfoGapButton {
  id: string
  session_id: string
  user_id: string
  user_name: string | null
  keyword: string
  skw_score: number | null
  status: InfoGapButtonStatus | null
  window_start: string
  created_at: string | null
  clicked_at: string | null
}

// ── 关键词 SKW ────────────────────────────────────────────────────────
export interface AdminKeywordSkw {
  id: string
  session_id: string
  window_start: string
  keyword: string
  user_a_id: string | null
  user_a_name: string | null
  user_b_id: string | null
  user_b_name: string | null
  skw_score: number | null
  mention_count: number | null
  skw_status: string | null
  created_at: string | null
}

// ── AI 推送分析 ───────────────────────────────────────────────────────
export type AiPushDropReason =
  | 'passed'
  | 'needs_prompt_false'
  | 'anchor_invalid'
  | 'content_empty'
  | 'persist_failed'
  | 'session_not_ongoing'

export interface AdminAiPushAnalysis {
  id: string
  session_id: string
  target_user_id: string
  target_user_name: string | null
  state_type: string
  window_start: string
  ai_needs_prompt: boolean
  ai_anchor: {
    transcript_id: string
    speaker_id: string
    speaker_name: string
    text: string
  } | null
  ai_content: string | null
  ai_analysis: string | null
  drop_reason: AiPushDropReason | null
  created_at: string | null
}

// ── 关键词召回分析 ────────────────────────────────────────────────────
export interface AdminKeywordRecallAnalysis {
  id: string
  session_id: string
  window_start: string
  keyword: string
  needs_prompt: boolean
  target_user_id: string | null
  target_user_name: string | null
  llm_reason: string | null
  created_at: string | null
}

// ── 语音转写（后台列表）──────────────────────────────────────────────
export interface AdminSpeechTranscript {
  transcript_id: string
  group_id: string
  session_id: string
  user_id: string | null
  speaker: string | null
  text: string | null
  start: string | null
  end: string | null
  duration: number | null
  created_at: string | null
  audio_url: string | null
  confidence: number | null
  speaker_confidence: number | null
  speaker_user_id: string | null
  original_text: string | null
  is_edited: boolean
}
