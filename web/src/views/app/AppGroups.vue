<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTimeToCST } from '../../utils/datetime'
import {
  type AppGroupDetail,
  type AppGroupSummary,
  type AppDiscoverGroup,
  joinGroup,
  listMyGroups,
  createGroup,
  getGroupDetail,
  leaveGroup,
  renameGroup,
  kickMember,
  listDiscoverGroups,
} from '../../api/appGroups'

interface AppUser {
  id: string
  name: string
  email: string
}

interface AppCurrentGroup {
  id: string
  name: string
}

function loadUserFromStorage(): AppUser | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem('app_user')
  if (!raw) return null
  try {
    return JSON.parse(raw) as AppUser
  } catch {
    return null
  }
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

function saveCurrentGroupToStorage(group: AppCurrentGroup | null) {
  if (typeof window === 'undefined') return
  if (!group) {
    window.localStorage.removeItem('app_current_group')
  } else {
    window.localStorage.setItem('app_current_group', JSON.stringify(group))
  }
}

function extractErrorMessage(err: unknown): string {
  const msg = (err as any)?.message ?? '请求失败'
  if (typeof msg !== 'string') return '请求失败'
  try {
    const parsed = JSON.parse(msg)
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
      const detail = (parsed as any).detail
      if (typeof detail === 'string') return detail
    }
  } catch {
    // ignore
  }
  return msg
}

const router = useRouter()
const currentUser = ref<AppUser | null>(loadUserFromStorage())
const currentGroup = ref<AppCurrentGroup | null>(loadCurrentGroupFromStorage())

const loading = ref(false)
const groups = ref<AppGroupSummary[]>([])
const discoverLoading = ref(false)
const discoverGroups = ref<AppDiscoverGroup[]>([])
const activeGroupId = ref<string | null>(currentGroup.value?.id ?? null)
const detailLoading = ref(false)
const activeGroupDetail = ref<AppGroupDetail | null>(null)

const joinGroupId = ref('')

const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({
  name: '',
})

const createRules: FormRules<typeof createForm> = {
  name: [{ required: true, message: '请输入群组名称', trigger: 'blur' }],
}

const isLeader = computed(() => activeGroupDetail.value?.my_role === 'leader')

const totalMyGroups = computed(() => groups.value.length)
const totalDiscoverGroups = computed(() => discoverGroups.value.length)
const currentMemberCount = computed(() => activeGroupDetail.value?.member_count ?? 0)

async function fetchMyGroups() {
  loading.value = true
  try {
    const data = await listMyGroups()
    groups.value = data

    if (!data.length) {
      activeGroupId.value = null
      activeGroupDetail.value = null
      if (currentGroup.value) {
        currentGroup.value = null
        saveCurrentGroupToStorage(null)
      }
      return
    }

    const existing = activeGroupId.value
      ? data.find((g) => g.id === activeGroupId.value)
      : null

    const next = existing ?? data[0]
    if (!next) return
    activeGroupId.value = next.id
    if (!currentGroup.value || currentGroup.value.id !== next.id) {
      const cg = { id: next.id, name: next.name }
      currentGroup.value = cg
      saveCurrentGroupToStorage(cg)
    }
    await loadGroupDetail(next.id)
  } catch (e) {
    console.error(e)
    ElMessage.error(extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}

async function fetchDiscoverGroups() {
  discoverLoading.value = true
  try {
    const data = await listDiscoverGroups()
    discoverGroups.value = data
  } catch (e) {
    console.error(e)
    ElMessage.error(extractErrorMessage(e))
  } finally {
    discoverLoading.value = false
  }
}

async function loadGroupDetail(groupId: string) {
  if (!groupId) return
  detailLoading.value = true
  try {
    const detail = await getGroupDetail(groupId)
    activeGroupDetail.value = detail
  } catch (e) {
    console.error(e)
    ElMessage.error(extractErrorMessage(e))
  } finally {
    detailLoading.value = false
  }
}

function openCreateDialog() {
  createForm.name = ''
  createDialogVisible.value = true
}

async function submitCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const detail = await createGroup({ name: createForm.name.trim() })
      ElMessage.success('创建群组成功')
      createDialogVisible.value = false

      await fetchMyGroups()
      const g = detail.group
      activeGroupId.value = g.id
      activeGroupDetail.value = detail
      const cg = { id: g.id, name: g.name }
      currentGroup.value = cg
      saveCurrentGroupToStorage(cg)
      await fetchDiscoverGroups()
    } catch (e) {
      console.error(e)
      ElMessage.error(extractErrorMessage(e))
    }
  })
}

async function handleJoinGroup() {
  const rawId = joinGroupId.value.trim()
  if (!rawId) return

  try {
    const detail = await joinGroup(rawId)
    ElMessage.success('加入群组成功')
    joinGroupId.value = ''

    await fetchMyGroups()
    await fetchDiscoverGroups()
    const g = detail.group
    activeGroupId.value = g.id
    activeGroupDetail.value = detail
    const cg = { id: g.id, name: g.name }
    currentGroup.value = cg
    saveCurrentGroupToStorage(cg)
  } catch (e) {
    console.error(e)
    ElMessage.error(extractErrorMessage(e))
  }
}

async function handleSelectGroup(row: AppGroupSummary) {
  if (!row || row.id === activeGroupId.value) return
  activeGroupId.value = row.id
  const cg = { id: row.id, name: row.name }
  currentGroup.value = cg
  saveCurrentGroupToStorage(cg)
  await loadGroupDetail(row.id)
}

async function handleRefresh() {
  await fetchMyGroups()
}

async function handleLeaveCurrentGroup() {
  if (!activeGroupDetail.value) return
  const gid = activeGroupDetail.value.group.id
  try {
    await ElMessageBox.confirm('确认退出该群组吗？', '退出确认', {
      type: 'warning',
      confirmButtonText: '退出群组',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await leaveGroup(gid)
    ElMessage.success('已退出群组')
    if (currentGroup.value?.id === gid) {
      currentGroup.value = null
      saveCurrentGroupToStorage(null)
    }
    await fetchMyGroups()
    await fetchDiscoverGroups()
  } catch (e) {
    console.error(e)
    ElMessage.error(extractErrorMessage(e))
  }
}

async function handleRenameGroup() {
  if (!activeGroupDetail.value || !isLeader.value) return
  const gid = activeGroupDetail.value.group.id
  const oldName = activeGroupDetail.value.group.name

  let newName = ''
  try {
    newName = await ElMessageBox.prompt('请输入新的群组名称', '修改群组名称', {
      inputValue: oldName,
      inputPlaceholder: '新的群组名称',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValidator: (val: string) => {
        if (!val || !val.trim()) return '群组名称不能为空'
        return true
      },
    }).then((res) => res.value as string)
  } catch {
    return
  }

  const finalName = newName.trim()
  if (!finalName || finalName === oldName) return

  try {
    const detail = await renameGroup(gid, finalName)
    ElMessage.success('群组名称已更新')
    activeGroupDetail.value = detail

    groups.value = groups.value.map((g) => (g.id === gid ? { ...g, name: finalName } : g))
    if (currentGroup.value?.id === gid) {
      const cg = { id: gid, name: finalName }
      currentGroup.value = cg
      saveCurrentGroupToStorage(cg)
    }
  } catch (e) {
    console.error(e)
    ElMessage.error(extractErrorMessage(e))
  }
}

async function handleKickMember(userId: string) {
  if (!activeGroupDetail.value || !isLeader.value) return
  const gid = activeGroupDetail.value.group.id
  const member = activeGroupDetail.value.members.find((m) => m.user_id === userId)
  const displayName = member?.user_name || member?.user_id || '该成员'

  try {
    await ElMessageBox.confirm(`确认将「${displayName}」移出该群组吗？`, '踢出成员确认', {
      type: 'warning',
      confirmButtonText: '踢出',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    const detail = await kickMember(gid, userId)
    ElMessage.success('已将成员移出群组')
    activeGroupDetail.value = detail

    const newCount = detail.member_count
    groups.value = groups.value.map((g) => (g.id === gid ? { ...g, member_count: newCount } : g))
  } catch (e) {
    console.error(e)
    ElMessage.error(extractErrorMessage(e))
  }
}

onMounted(() => {
  fetchMyGroups()
  fetchDiscoverGroups()
})
</script>

<template>
  <div class="app-groups">
    <div class="app-groups-header">
      <h2 class="app-groups-title">我的群组</h2>
      <div class="app-groups-meta">
        <span class="app-groups-user" v-if="currentUser">
          {{ currentUser.name || currentUser.email }}（{{ currentUser.email }}）
        </span>
        <span class="app-groups-group">
          <span class="app-groups-group-label">当前群组：</span>
          <span class="app-groups-group-value">
            {{ currentGroup?.name || '未选择' }}
          </span>
        </span>
      </div>
    </div>

    <div class="app-groups-overview">
      <div class="app-groups-overview-pill">
        <span class="app-groups-overview-label">已加入群组</span>
        <span class="app-groups-overview-value">{{ totalMyGroups }}</span>
      </div>
      <div class="app-groups-overview-pill">
        <span class="app-groups-overview-label">当前群成员</span>
        <span class="app-groups-overview-value">
          {{ activeGroupDetail ? currentMemberCount : '—' }}
        </span>
      </div>
      <div class="app-groups-overview-pill">
        <span class="app-groups-overview-label">可加入群组</span>
        <span class="app-groups-overview-value">{{ totalDiscoverGroups }}</span>
      </div>
    </div>

    <el-card class="app-groups-card" shadow="never">
      <div class="app-groups-list-header">
        <div>
          <h3 class="app-groups-list-title">我的群组</h3>
          <p class="app-groups-list-subtitle">
            你可以加入多个群组，切换当前群组会影响「我的会话」等页面中展示的内容。
          </p>
        </div>
        <el-button type="primary" size="small" @click="openCreateDialog">新建群组</el-button>
      </div>

      <p v-if="!groups.length && !loading" class="app-groups-empty">
        你还没有加入任何群组，可以先新建一个群组，或等待他人创建并邀请你加入。
      </p>

      <div v-else class="app-groups-list" :class="{ 'is-loading': loading }">
        <div
          v-for="g in groups"
          :key="g.id"
          class="app-groups-list-item"
          :data-active="g.id === activeGroupId"
          @click="handleSelectGroup(g)"
        >
          <div class="app-groups-list-main">
            <div class="app-groups-list-name-row">
              <span class="app-groups-list-name">{{ g.name }}</span>
              <span class="app-groups-list-role">
                {{ g.my_role === 'leader' ? '群主' : '成员' }}
              </span>
              <span
                v-if="currentGroup && currentGroup.id === g.id"
                class="app-groups-list-current"
              >
                当前
              </span>
            </div>
            <div class="app-groups-list-meta">
              成员：{{ g.member_count }} 人 · 创建时间：{{ formatDateTimeToCST(g.created_at) }}
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="app-groups-card" shadow="never">
      <h3 class="app-groups-join-title">加入已有群组</h3>
      <p class="app-groups-join-desc">
        从下拉列表中选择一个当前可加入的群组，点击「加入群组」即可加入。列表仅展示未满员且你尚未加入的群组。
      </p>
      <div class="app-groups-join-row">
        <el-select
          v-model="joinGroupId"
          class="app-groups-join-input"
          placeholder="选择一个可加入的群组"
          :loading="discoverLoading"
          clearable
          filterable
          :disabled="!discoverGroups.length"
        >
          <el-option
            v-for="g in discoverGroups"
            :key="g.id"
            :label="`${g.name}（${g.member_count} 人）`"
            :value="g.id"
          />
        </el-select>
        <el-button type="primary" :disabled="!joinGroupId" @click="handleJoinGroup">
          加入群组
        </el-button>
      </div>
      <p v-if="!discoverLoading && !discoverGroups.length" class="app-groups-join-hint">
        当前没有可加入的公开群组，请让群主或管理员创建群并邀请你加入。
      </p>
    </el-card>

    <el-card class="app-groups-card" shadow="never">
      <template v-if="activeGroupDetail">
        <div class="app-groups-detail-header">
          <div>
            <div class="app-groups-detail-name-row">
              <h3 class="app-groups-detail-name">
                {{ activeGroupDetail.group.name }}
              </h3>
              <el-tag v-if="isLeader" type="warning" size="small">群主</el-tag>
              <el-tag
                v-if="!activeGroupDetail.group.is_active"
                type="info"
                size="small"
                class="app-groups-detail-tag"
              >
                已停用
              </el-tag>
            </div>
            <div class="app-groups-detail-sub">
              <span class="app-groups-detail-id">ID：{{ activeGroupDetail.group.id }}</span>
              <span class="app-groups-detail-dot">·</span>
              <span>
                创建时间：{{ formatDateTimeToCST(activeGroupDetail.group.created_at) }}
              </span>
              <span class="app-groups-detail-dot">·</span>
              <span>成员数：{{ activeGroupDetail.member_count }}</span>
            </div>
          </div>
          <div class="app-groups-detail-actions">
            <el-button size="small" @click="handleRefresh">刷新</el-button>
            <el-button v-if="isLeader" size="small" @click="handleRenameGroup">修改名称</el-button>
            <el-button size="small" type="danger" @click="handleLeaveCurrentGroup">退出群组</el-button>
            <el-button size="small" type="primary" @click="router.push('/app/groups/' + activeGroupDetail.group.id)">进入群组</el-button>
          </div>
        </div>

        <p class="app-groups-detail-desc">
          当前群组会影响你在「我的会话」等页面看到的内容。你可以在上方切换群组，或在这里管理成员。
        </p>

        <div class="app-groups-members">
          <h4 class="app-groups-members-title">成员列表</h4>
          <div v-if="detailLoading" class="app-groups-members-loading">成员信息加载中...</div>
          <div v-else class="app-groups-members-list">
            <div
              v-for="m in activeGroupDetail.members"
              :key="m.user_id"
              class="app-groups-member-item"
            >
              <div class="app-groups-member-main">
                <div class="app-groups-member-avatar">
                  {{ (m.user_name || m.user_id).slice(0, 1).toUpperCase() }}
                </div>
                <div class="app-groups-member-text">
                  <div class="app-groups-member-name-row">
                    <span class="app-groups-member-name">
                      {{ m.user_name || m.user_id }}
                    </span>
                    <span
                      v-if="currentUser && m.user_id === currentUser.id"
                      class="app-groups-self-tag"
                    >
                      我
                    </span>
                  </div>
                  <div class="app-groups-member-meta">
                    角色：{{ m.role === 'leader' ? '群主' : '成员' }}
                  </div>
                </div>
              </div>
              <div class="app-groups-member-actions">
                <el-tag v-if="m.status === 'active'" type="success" size="small">在群</el-tag>
                <el-tag v-else type="info" size="small">{{ m.status }}</el-tag>
                <el-button
                  v-if="isLeader && !(currentUser && m.user_id === currentUser.id)"
                  type="danger"
                  link
                  size="small"
                  @click="handleKickMember(m.user_id)"
                >
                  移出
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="app-groups-detail-empty">
          <p class="app-groups-detail-empty-title">尚未选择群组</p>
          <p class="app-groups-detail-empty-desc">
            先在上方「我的群组」中选择一个群组，或者创建 / 加入一个群组后，在这里查看成员与详细信息。
          </p>
        </div>
      </template>
    </el-card>

    <el-dialog v-model="createDialogVisible" title="新建群组" width="420px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入群组名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitCreate">创建</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.app-groups {
  max-width: 880px;
  margin: 0 auto;
}

.app-groups-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.app-groups-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.app-groups-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-size: 12px;
}

.app-groups-user {
  color: #4b5563;
}

.app-groups-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #374151;
}

.app-groups-group-label {
  color: #6b7280;
}

.app-groups-group-value {
  font-weight: 500;
}

.app-groups-overview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.app-groups-overview-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
}

.app-groups-overview-label {
  font-size: 12px;
  color: #6b7280;
}

.app-groups-overview-value {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}

.app-groups-card {
  border-radius: 12px;
  margin-bottom: 12px;
}

.app-groups-list-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.app-groups-list-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.app-groups-list-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #6b7280;
}

.app-groups-empty {
  margin: 8px 0 12px;
  font-size: 13px;
  color: #6b7280;
}

.app-groups-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.app-groups-list.is-loading {
  opacity: 0.6;
}

.app-groups-list-item {
  display: flex;
  align-items: stretch;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: #f9fafb;
  cursor: pointer;
  transition:
    background-color 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.08s ease;
}

.app-groups-list-item:hover {
  background: #f3f4f6;
  border-color: #e5e7eb;
}

.app-groups-list-item[data-active='true'] {
  background: #eff6ff;
  border-color: #2563eb;
  box-shadow: 0 4px 10px rgba(37, 99, 235, 0.16);
}

.app-groups-list-main {
  flex: 1;
  min-width: 0;
}

.app-groups-list-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

.app-groups-list-name {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.app-groups-list-role {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
}

.app-groups-list-current {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
}

.app-groups-list-meta {
  font-size: 12px;
  color: #6b7280;
}

.app-groups-join {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed #e5e7eb;
}

.app-groups-join-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.app-groups-join-desc {
  margin: 0 0 8px;
  font-size: 12px;
  color: #6b7280;
}

.app-groups-join-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #9ca3af;
}

.app-groups-join-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.app-groups-join-input {
  flex: 1;
}

.app-groups-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.app-groups-detail-name-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.app-groups-detail-name {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.app-groups-detail-tag {
  margin-left: 2px;
}

.app-groups-detail-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.app-groups-detail-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.app-groups-detail-dot {
  color: #d1d5db;
}

.app-groups-detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.app-groups-members {
  margin-top: 12px;
}

.app-groups-members-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.app-groups-self-tag {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 11px;
}

.app-groups-detail-desc {
  margin: 4px 0 8px;
  font-size: 12px;
  color: #6b7280;
}

.app-groups-members-loading {
  font-size: 13px;
  color: #6b7280;
}

.app-groups-members-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.app-groups-member-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
}

.app-groups-member-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.app-groups-member-avatar {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
}

.app-groups-member-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.app-groups-member-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.app-groups-member-name {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
}

.app-groups-member-meta {
  font-size: 12px;
  color: #6b7280;
}

.app-groups-member-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-groups-detail-empty {
  padding: 12px 4px;
}

.app-groups-detail-empty-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.app-groups-detail-empty-desc {
  margin: 0;
  font-size: 13px;
  color: #6b7280;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>

