import { appHttp } from './appHttp'

export interface VoiceProfileOut {
  id: string
  user_id: string
  sample_audio_urls: string[]
  created_at: string
  voice_embedding: Record<string, unknown> | null
}

export interface UploadAudioResponse {
  url: string
}

export function getMyVoiceProfile(): Promise<VoiceProfileOut> {
  return appHttp.get<VoiceProfileOut>('/api/voice-profile/me')
}

export function updateMySamples(sample_audio_urls: string[]): Promise<VoiceProfileOut> {
  return appHttp.put<VoiceProfileOut>('/api/voice-profile/me/samples', { sample_audio_urls })
}

export function generateMyEmbedding(): Promise<VoiceProfileOut> {
  return appHttp.post<VoiceProfileOut>('/api/voice-profile/me/generate-embedding')
}

export function uploadMyVoiceSample(file: File): Promise<UploadAudioResponse> {
  const formData = new FormData()
  formData.append('file', file)

  // 不显式设置 Content-Type，交由浏览器/HTTP 客户端自动带上 multipart 边界，避免与后端解析不一致导致 422
  return appHttp.post<UploadAudioResponse>('/api/voice-profile/me/upload-audio', formData)
}

