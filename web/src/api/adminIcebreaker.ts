/**
 * 管理员破冰 API —— 使用 X-Admin-Token 认证，无需用户 token。
 * 接口逻辑与 appIcebreaker.ts 相同，仅切换为 admin http 客户端。
 */
import { http } from './http'
import type {
  IcebreakerVoiceSamplePayload,
  IcebreakerVoiceSampleResponse,
  IcebreakerEvaluatePayload,
  IcebreakerEvaluateResponse,
  IcebreakerTranscribePayload,
  IcebreakerTranscribeResponse,
} from './appIcebreaker'

export type {
  IcebreakerVoiceSamplePayload,
  IcebreakerVoiceSampleResponse,
  IcebreakerEvaluatePayload,
  IcebreakerEvaluateResponse,
  IcebreakerTranscribePayload,
  IcebreakerTranscribeResponse,
}

export async function adminTranscribeIcebreakerTurn(
  payload: IcebreakerTranscribePayload,
): Promise<IcebreakerTranscribeResponse> {
  const form = new FormData()
  form.set('group_id', payload.groupId)
  form.set('user_id', payload.userId)
  form.set('round', String(payload.round))
  form.set('turn_index', String(payload.turnIndex))
  form.set('mime_type', payload.mimeType)
  form.set('audio', payload.audio, `icebreaker-${payload.turnIndex}.${payload.mimeType.includes('aac') ? 'aac' : 'webm'}`)
  return http.post<IcebreakerTranscribeResponse>('/api/icebreaker/transcribe', form)
}

export async function adminUploadIcebreakerVoiceSample(
  payload: IcebreakerVoiceSamplePayload,
): Promise<IcebreakerVoiceSampleResponse> {
  const form = new FormData()
  form.set('group_id', payload.groupId)
  form.set('user_id', payload.userId)
  form.set('source', payload.source)
  form.set('mime_type', payload.mimeType)
  if (typeof payload.questionIndex === 'number') form.set('question_index', String(payload.questionIndex))
  if (typeof payload.round === 'number') form.set('round', String(payload.round))
  if (typeof payload.turnIndex === 'number') form.set('turn_index', String(payload.turnIndex))
  const index = payload.turnIndex ?? payload.questionIndex ?? Date.now()
  form.set('audio', payload.audio, `icebreaker-${payload.source}-${index}.${payload.mimeType.includes('aac') ? 'aac' : 'webm'}`)
  return http.post<IcebreakerVoiceSampleResponse>('/api/icebreaker/voice-sample', form)
}

export async function adminEvaluateIcebreakerStory(
  payload: IcebreakerEvaluatePayload,
): Promise<IcebreakerEvaluateResponse> {
  return http.post<IcebreakerEvaluateResponse>('/api/icebreaker/evaluate', payload)
}
