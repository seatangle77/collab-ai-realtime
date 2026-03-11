import { appHttp } from './appHttp'

export interface VoiceProfileOut {
  id: string
  user_id: string
  sample_audio_urls: string[]
  created_at: string
  voice_embedding: Record<string, unknown> | null
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
