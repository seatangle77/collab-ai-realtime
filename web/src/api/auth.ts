import { http } from './http'
import type { AdminUser } from '../types/admin'

export interface RegisterUserPayload {
  name: string
  email: string
  password: string
  device_token?: string | null
}

export async function registerUser(payload: RegisterUserPayload): Promise<AdminUser> {
  // 后端 /api/auth/register 返回的字段集合与 AdminUser 一致，这里直接复用类型
  return http.post<AdminUser>('/api/auth/register', payload)
}

