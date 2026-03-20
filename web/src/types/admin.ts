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

