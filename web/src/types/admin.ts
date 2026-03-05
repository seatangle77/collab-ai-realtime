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
}

export interface AdminChatSession {
  id: string
  group_id: string
  session_title: string
  created_at: string
  last_updated: string
  is_active: boolean | null
  ended_at: string | null
}



