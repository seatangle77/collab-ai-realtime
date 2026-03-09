import { appHttp } from './appHttp'
import type { AdminUser } from '../types/admin'

export interface AppRegisterPayload {
  name: string
  email: string
  password: string
  device_token?: string | null
}

export interface AppLoginPayload {
  email: string
  password: string
}

export interface AppTokenResponse {
  access_token: string
  token_type: string
  user: AdminUser
}

export interface ChangePasswordPayload {
  old_password: string
  new_password: string
}

export async function appRegister(payload: AppRegisterPayload): Promise<AdminUser> {
  return appHttp.post<AdminUser>('/api/auth/register', payload)
}

export async function appLogin(payload: AppLoginPayload): Promise<AppTokenResponse> {
  return appHttp.post<AppTokenResponse>('/api/auth/login', payload)
}

export async function fetchAppMe(): Promise<AdminUser> {
  return appHttp.get<AdminUser>('/api/auth/me')
}

export async function changeAppPassword(payload: ChangePasswordPayload): Promise<AdminUser> {
  return appHttp.post<AdminUser>('/api/auth/change-password', payload)
}

