import { appHttp } from './appHttp'
import type { AppHttpConfig } from './appHttp'

export interface AppChatSession {
  id: string
  group_id: string
  created_at: string
  last_updated: string
  session_title: string
  status?: 'not_started' | 'ongoing' | 'ended' | null
  started_at?: string | null
  ended_at?: string | null
}

export interface AppTranscript {
  transcript_id: string
  group_id: string
  session_id: string
  user_id?: string | null
  speaker?: string | null
  text: string
  start: any
  end: any
  duration?: number | null
  created_at: string
}

export async function listGroupSessions(
  groupId: string,
  options: { includeEnded?: boolean } = {},
  config?: AppHttpConfig,
): Promise<AppChatSession[]> {
  const params = new URLSearchParams()
  if (options.includeEnded) {
    params.set('include_ended', 'true')
  }
  const qs = params.toString()
  const url = `/api/groups/${groupId}/sessions` + (qs ? `?${qs}` : '')
  return appHttp.get<AppChatSession[]>(url, config)
}

export interface CreateSessionOptions {
  createdAt?: string
  lastUpdatedAt?: string
  endedAt?: string
}

export async function createSession(
  groupId: string,
  sessionTitle: string,
  options: CreateSessionOptions = {},
): Promise<AppChatSession> {
  const payload: Record<string, unknown> = {
    session_title: sessionTitle,
  }

  if (options.createdAt) payload.created_at = options.createdAt
  if (options.lastUpdatedAt) payload.last_updated = options.lastUpdatedAt
  if (options.endedAt) payload.ended_at = options.endedAt

  return appHttp.post<AppChatSession>(`/api/groups/${groupId}/sessions`, payload)
}

export interface UpdateSessionOptions {
  createdAt?: string
  lastUpdatedAt?: string
  endedAt?: string
}

export async function updateSession(
  sessionId: string,
  sessionTitle: string,
  options: UpdateSessionOptions = {},
): Promise<AppChatSession> {
  const payload: Record<string, unknown> = {
    session_title: sessionTitle,
  }

  if (options.createdAt) payload.created_at = options.createdAt
  if (options.lastUpdatedAt) payload.last_updated = options.lastUpdatedAt
  if (options.endedAt) payload.ended_at = options.endedAt

  return appHttp.patch<AppChatSession>(`/api/sessions/${sessionId}`, payload)
}

export async function endSession(sessionId: string): Promise<AppChatSession> {
  return appHttp.post<AppChatSession>(`/api/sessions/${sessionId}/end`)
}

export async function listSessionTranscripts(sessionId: string): Promise<AppTranscript[]> {
  return appHttp.get<AppTranscript[]>(`/api/sessions/${sessionId}/transcripts`)
}

