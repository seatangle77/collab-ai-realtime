import { ref } from 'vue'
import { getGroupDetail, listMyGroups } from '../../../api/appGroups'
import type { AppGroupMember } from '../../../api/appGroups'
import { listAdminMemberships } from '../../../api/admin/memberships'
import { extractErrorMessage } from '../../../utils/error'
import type { AppCurrentGroup, IcebreakerGroup, IcebreakerMember } from './types'

const AVATAR_COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f97316', '#ec4899', '#14b8a6']

export const FALLBACK_MEMBER: IcebreakerMember = {
  id: 'fallback',
  name: '成员',
  initial: '成',
  bg: '#3b82f6',
}

function loadCurrentGroupFromStorage(): AppCurrentGroup | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem('app_current_group')
  if (!raw) return null
  try {
    return JSON.parse(raw) as AppCurrentGroup
  } catch {
    return null
  }
}

function saveCurrentGroupToStorage(group: AppCurrentGroup) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem('app_current_group', JSON.stringify(group))
}

function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  }
  return hash
}

function toIcebreakerMember(member: AppGroupMember): IcebreakerMember {
  const name = member.user_name || member.user_id
  const initial = name.trim().slice(0, 1).toUpperCase() || '?'
  return {
    id: member.user_id,
    name,
    initial,
    bg: AVATAR_COLORS[hashString(member.user_id) % AVATAR_COLORS.length]!,
  }
}

async function resolveCurrentGroup(): Promise<AppCurrentGroup | null> {
  const stored = loadCurrentGroupFromStorage()
  if (stored?.id) return stored

  const myGroups = await listMyGroups()
  const firstGroup = myGroups[0]
  if (!firstGroup) return null

  const nextGroup = { id: firstGroup.id, name: firstGroup.name }
  saveCurrentGroupToStorage(nextGroup)
  return nextGroup
}

export function useIcebreakerMembers(
  onLoaded: () => void,
  options?: { groupId?: string; isAdmin?: boolean },
) {
  const pageLoading = ref(true)
  const pageError = ref('')
  const currentGroup = ref<IcebreakerGroup | null>(null)
  const currentGroupName = ref('')
  const members = ref<IcebreakerMember[]>([])

  async function loadIcebreakerMembers() {
    pageLoading.value = true
    pageError.value = ''
    try {
      // 管理员模式：只要求小组已有 3 名成员，不按 active/left/kicked 状态拦截。
      if (options?.isAdmin) {
        if (!options.groupId) {
          pageError.value = '缺少小组 ID，请从后台群组管理页进入破冰。'
          members.value = []
          return
        }

        const result = await listAdminMemberships({ group_id: options.groupId, page_size: 100 })
        const groupMembers = result.items
        if (groupMembers.length < 3) {
          pageError.value = '该小组成员不足 3 人。'
          members.value = []
          return
        }
        const groupName = groupMembers[0]?.group_name ?? options.groupId
        currentGroupName.value = groupName
        currentGroup.value = { id: options.groupId, name: groupName }
        members.value = groupMembers.map((m) => {
          const name = m.user_name || m.user_id
          return {
            id: m.user_id,
            name,
            initial: name.trim().slice(0, 1).toUpperCase() || '?',
            bg: AVATAR_COLORS[hashString(m.user_id) % AVATAR_COLORS.length]!,
          }
        })
        onLoaded()
        return
      }

      // 用户模式：从 localStorage 读当前小组
      const group = await resolveCurrentGroup()
      if (!group) {
        pageError.value = '你还没有加入小组，先创建或加入一个 3 人小组后再开始破冰。'
        members.value = []
        return
      }

      const detail = await getGroupDetail(group.id, { noRedirectOn401: true })
      if (detail.my_role === null || detail.my_role === undefined) {
        pageError.value = '你不是当前小组成员，请先回到小组页重新选择。'
        members.value = []
        return
      }

      currentGroupName.value = detail.group.name
      currentGroup.value = { id: detail.group.id, name: detail.group.name }
      saveCurrentGroupToStorage({ id: detail.group.id, name: detail.group.name })
      members.value = detail.members.map(toIcebreakerMember)
      onLoaded()
    } catch (e) {
      pageError.value = extractErrorMessage(e) || '加载小组成员失败，请稍后再试。'
      members.value = []
    } finally {
      pageLoading.value = false
    }
  }

  return {
    pageLoading,
    pageError,
    currentGroup,
    currentGroupName,
    members,
    loadIcebreakerMembers,
  }
}
