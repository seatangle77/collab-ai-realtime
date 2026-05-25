import { appHttp } from './appHttp'

export interface IcebreakerTranscribePayload {
  groupId: string
  userId: string
  round: number
  turnIndex: number
  mimeType: string
  audio: Blob
}

export interface IcebreakerTranscribeResponse {
  text: string
}

export interface IcebreakerMemberPayload {
  user_id: string
  user_name?: string | null
}

export interface IcebreakerStoryTurnPayload {
  user_id: string
  user_name?: string | null
  round: number
  turn_index: number
  text: string
}

export interface IcebreakerEvaluatePayload {
  group_id: string
  story_opening: string
  members: IcebreakerMemberPayload[]
  turns: IcebreakerStoryTurnPayload[]
}

export interface IcebreakerEvaluateResponse {
  polished_story: string
  score: number
  comment: string
  mvp_user_id: string
  mvp_title: string
  mvp_reason: string
}

export async function transcribeIcebreakerTurn(
  payload: IcebreakerTranscribePayload,
): Promise<IcebreakerTranscribeResponse> {
  const form = new FormData()
  form.set('group_id', payload.groupId)
  form.set('user_id', payload.userId)
  form.set('round', String(payload.round))
  form.set('turn_index', String(payload.turnIndex))
  form.set('mime_type', payload.mimeType)
  form.set('audio', payload.audio, `icebreaker-${payload.turnIndex}.${payload.mimeType.includes('aac') ? 'aac' : 'webm'}`)

  return appHttp.post<IcebreakerTranscribeResponse>('/api/icebreaker/transcribe', form, {
    noRedirectOn401: true,
  })
}

export async function evaluateIcebreakerStory(
  payload: IcebreakerEvaluatePayload,
): Promise<IcebreakerEvaluateResponse> {
  return appHttp.post<IcebreakerEvaluateResponse>('/api/icebreaker/evaluate', payload, {
    noRedirectOn401: true,
  })
}
