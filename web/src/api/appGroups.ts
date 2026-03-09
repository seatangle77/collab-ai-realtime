import { appHttp } from './appHttp'

export interface AppGroup {
  id: string
  name: string
  created_at: string
  is_active: boolean
}

export interface AppGroupSummary extends AppGroup {
  member_count: number
  my_role: string
}

export interface AppGroupMember {
  user_id: string
  role: string
  status: string
  user_name?: string | null
  device_token?: string | null
}

export interface AppGroupDetail {
  group: AppGroup
  member_count: number
  members: AppGroupMember[]
  my_role?: string | null
}

export interface CreateGroupPayload {
  name: string
}

export async function listMyGroups(): Promise<AppGroupSummary[]> {
  return appHttp.get<AppGroupSummary[]>('/api/groups/my')
}

export async function getGroupDetail(groupId: string): Promise<AppGroupDetail> {
  return appHttp.get<AppGroupDetail>(`/api/groups/${groupId}`)
}

export async function createGroup(payload: CreateGroupPayload): Promise<AppGroupDetail> {
  return appHttp.post<AppGroupDetail>('/api/groups', payload)
}

export async function joinGroup(groupId: string): Promise<AppGroupDetail> {
  return appHttp.post<AppGroupDetail>(`/api/groups/${groupId}/join`)
}

export interface LeaveGroupResponse {
  success: boolean
}

export async function leaveGroup(groupId: string): Promise<LeaveGroupResponse> {
  return appHttp.post<LeaveGroupResponse>(`/api/groups/${groupId}/leave`)
}

export async function renameGroup(groupId: string, name: string): Promise<AppGroupDetail> {
  return appHttp.patch<AppGroupDetail>(`/api/groups/${groupId}`, { name })
}

export async function kickMember(groupId: string, userId: string): Promise<AppGroupDetail> {
  return appHttp.post<AppGroupDetail>(`/api/groups/${groupId}/members/${userId}/kick`)
}

export interface AppDiscoverGroup extends AppGroup {
  member_count: number
}

export interface ListDiscoverGroupsParams {
  name?: string
  limit?: number
}

export async function listDiscoverGroups(params: ListDiscoverGroupsParams = {}): Promise<AppDiscoverGroup[]> {
  const query = new URLSearchParams()
  if (params.name) query.set('name', params.name)
  if (params.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  const url = '/api/groups/discover' + (qs ? `?${qs}` : '')
  return appHttp.get<AppDiscoverGroup[]>(url)
}

