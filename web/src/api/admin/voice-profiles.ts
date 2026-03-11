import { http } from '../http'
import type {
  Page,
  AdminVoiceProfileSummary,
  AdminVoiceProfileDetail,
  AdminVoiceProfileDetailProfile,
} from '../../types/admin'

export interface ListAdminVoiceProfilesParams {
  page?: number
  page_size?: number
  user_id?: string
  has_samples?: boolean
  has_embedding?: boolean
}

export type AdminVoiceProfilePage = Page<AdminVoiceProfileSummary>

export interface AdminUploadAudioResponse {
  url: string
}

export async function listAdminVoiceProfiles(
  params: ListAdminVoiceProfilesParams,
): Promise<AdminVoiceProfilePage> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.user_id) query.set('user_id', params.user_id)
  if (typeof params.has_samples === 'boolean') query.set('has_samples', String(params.has_samples))
  if (typeof params.has_embedding === 'boolean') query.set('has_embedding', String(params.has_embedding))

  const qs = query.toString()
  const url = '/api/admin/voice-profiles' + (qs ? `?${qs}` : '')
  return http.get<AdminVoiceProfilePage>(url)
}

export async function getAdminVoiceProfileDetail(id: string): Promise<AdminVoiceProfileDetail> {
  return http.get<AdminVoiceProfileDetail>(`/api/admin/voice-profiles/${id}`)
}

export async function updateAdminVoiceProfileSamples(
  id: string,
  sample_audio_urls: string[],
): Promise<AdminVoiceProfileDetailProfile> {
  return http.put<AdminVoiceProfileDetailProfile>(`/api/admin/voice-profiles/${id}/samples`, {
    sample_audio_urls,
  })
}

export async function generateAdminVoiceProfileEmbedding(
  id: string,
): Promise<AdminVoiceProfileDetailProfile> {
  return http.post<AdminVoiceProfileDetailProfile>(`/api/admin/voice-profiles/${id}/generate-embedding`)
}

export async function uploadAdminVoiceProfileSample(
  id: string,
  file: File,
): Promise<AdminUploadAudioResponse> {
  const formData = new FormData()
  formData.append('file', file)

  // 同样不手动设置 Content-Type，避免 multipart 边界缺失导致后端解析失败
  return http.post<AdminUploadAudioResponse>(`/api/admin/voice-profiles/${id}/upload-audio`, formData)
}


