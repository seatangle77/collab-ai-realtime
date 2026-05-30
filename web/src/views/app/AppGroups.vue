<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshRight, SwitchButton } from '@element-plus/icons-vue'
import AppEmptyState from '../../components/AppEmptyState.vue'
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

// 用户端暂时屏蔽新建群组入口；保留创建逻辑，后续如需恢复按钮可重新启用。
// function openCreateDialog() {
//   createForm.name = ''
//   createDialogVisible.value = true
// }

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
      <!-- 用户端暂时屏蔽新建群组按钮；后台管理员负责创建群组。 -->
      <!-- <button
        v-if="groups.length > 0"
        class="app-groups-create-btn"
        type="button"
        aria-label="创建群组"
        @click="openCreateDialog"
      >
        <el-icon class="app-groups-create-icon" :size="24">
          <Plus />
        </el-icon>
      </button> -->
    </div>

    <el-card class="app-groups-card app-groups-card--secondary" shadow="never">
      <AppEmptyState
        v-if="!groups.length && !loading"
        icon="group"
        title="你还没有加入任何群组"
        description="请先加入管理员创建的群组，然后选择本次要使用的群组。"
        compact
      />
      <!-- 原用户端创建入口暂时屏蔽，保留代码便于后续恢复。
      <AppEmptyState
        v-if="!groups.length && !loading"
        icon="group"
        title="你还没有加入任何群组"
        description="创建或加入一个群组后，就可以选择成员发起会话。"
        action-label="创建"
        compact
        @action="openCreateDialog"
      />
      -->

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
            </div>
            <div class="app-groups-list-meta">
              {{ g.member_count }} 位成员
            </div>
          </div>
        </div>
      </div>

      <div class="app-groups-detail-section">
        <template v-if="activeGroupDetail">
          <div class="app-groups-members-head">
            <div>
              <h4 class="app-groups-members-title">成员列表</h4>
              <p v-if="!activeGroupDetail.group.is_active" class="app-groups-members-count">已停用</p>
            </div>
          </div>

          <div class="app-groups-action-grid">
            <el-button class="app-groups-action-btn" :icon="RefreshRight" @click="handleRefresh">
              刷新
            </el-button>
            <el-button v-if="isLeader" class="app-groups-action-btn" @click="handleRenameGroup">
              改名
            </el-button>
            <el-button class="app-groups-action-btn" type="danger" :icon="SwitchButton" @click="handleLeaveCurrentGroup">
              退出
            </el-button>
          </div>

        <div class="app-groups-members">
          <div v-if="detailLoading" class="app-groups-members-loading">成员信息加载中...</div>
          <AppEmptyState
            v-else-if="activeGroupDetail.members.length === 0"
            icon="group"
            title="群组内还没有成员"
            description="当前群组暂无可展示成员，稍后再回来看看。"
            compact
          />
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
          <AppEmptyState
            icon="empty"
            title="尚未选择群组"
            description="请选择或加入管理员创建的群组后，可以在这里查看成员。"
          />
        </template>
      </div>
    </el-card>

    <el-card class="app-groups-card" shadow="never">
      <h3 class="app-groups-join-title">加入已有群组</h3>
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
        <el-button plain :disabled="!joinGroupId" @click="handleJoinGroup">
          加入群组
        </el-button>
      </div>
      <p v-if="!discoverLoading && !discoverGroups.length" class="app-groups-join-hint">
        当前没有可加入的公开群组，请让群主或管理员创建群并邀请你加入。
      </p>
    </el-card>

    <el-dialog
      v-model="createDialogVisible"
      class="app-mobile-sheet"
      title="新建群组"
      :width="'min(480px, 92vw)'"
    >
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
  max-width: var(--app-content-width-default);
  margin: 0 auto;
  padding-bottom: 8px;
}

.app-groups-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.app-groups-title {
  margin: 0;
  font-size: var(--app-font-size-title);
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
}

.app-groups-create-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--app-radius-pill);
  border: 1px solid var(--app-primary);
  padding: 0;
  font-family: inherit;
  background: var(--app-primary);
  color: #fff;
  cursor: pointer;
  box-shadow: var(--app-shadow-card);
  flex-shrink: 0;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.app-groups-create-btn:hover {
  background: var(--app-primary-hover);
  border-color: var(--app-primary-hover);
}

.app-groups-create-icon {
  flex-shrink: 0;
}

/* 卡片分区 */
.app-groups-card {
  margin-bottom: 12px;
  border-radius: var(--app-radius-card);
  border: 1px solid var(--app-border);
  background: var(--app-bg-elevated);
  box-shadow: var(--app-shadow-card);
}

.app-groups-card :deep(.el-card__body) {
  padding: 14px 16px;
}

.app-groups-card--secondary {
  background: transparent;
}

.app-groups-empty {
  margin: 8px 0 4px;
  font-size: var(--app-font-size-body);
  line-height: 1.55;
  color: var(--app-text-secondary);
}

.app-groups-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.app-groups-list.is-loading {
  opacity: 0.65;
  pointer-events: none;
}

.app-groups-list-item {
  display: flex;
  align-items: stretch;
  padding: 14px 16px;
  border-radius: var(--app-radius-card);
  border: 1px solid var(--app-border);
  background: var(--app-bg-elevated);
  box-shadow: var(--app-shadow-card);
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background-color 0.18s ease;
}

.app-groups-list-item:hover {
  border-color: var(--app-primary);
  box-shadow: var(--app-shadow-soft);
}

.app-groups-list-item[data-active='true'] {
  background: var(--app-primary-soft);
  border-color: var(--app-primary);
  box-shadow: var(--app-shadow-soft);
}

.app-groups-list-main {
  flex: 1;
  min-width: 0;
}

.app-groups-list-name-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}

.app-groups-list-name {
  font-size: 17px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.app-groups-list-role {
  font-size: var(--app-font-size-caption);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--app-radius-pill);
  background: var(--app-color-ai-soft);
  color: var(--app-color-ai);
}

.app-groups-list-meta {
  font-size: 15px;
  color: var(--app-text-secondary);
}

.app-groups-join-title {
  margin: 0 0 12px;
  font-size: var(--app-font-size-heading);
  font-weight: 600;
  color: var(--app-text-primary);
}

.app-groups-join-hint {
  margin: 10px 0 0;
  font-size: 15px;
  color: var(--app-text-muted);
}

.app-groups-join-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.app-groups-join-input {
  flex: 1;
  min-width: 200px;
}

.app-groups-detail-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--app-border);
}

.app-groups-members-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.app-groups-members-count {
  margin: 4px 0 0;
  font-size: 15px;
  color: var(--app-text-secondary);
}

.app-groups-action-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.app-groups-action-grid :deep(.el-button + .el-button) {
  margin-left: 0;
}

.app-groups-action-btn {
  width: 100%;
  min-width: 0;
  min-height: 42px;
  border-radius: var(--app-radius-md);
  font-weight: 700;
}

.app-groups-members {
  margin-top: 0;
  padding-top: 4px;
}

.app-groups-members-title {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.app-groups-self-tag {
  margin-left: 4px;
  color: var(--app-primary);
  font-size: 15px;
  font-weight: 500;
}

.app-groups-members-loading {
  font-size: var(--app-font-size-body);
  color: var(--app-text-secondary);
}

.app-groups-members-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.app-groups-member-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 16px;
  border-radius: var(--app-radius-card);
  background: var(--app-bg-page);
}

.app-groups-member-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.app-groups-member-avatar {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  background: #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--app-font-size-caption);
  font-weight: 600;
  color: var(--app-text-primary);
  flex-shrink: 0;
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
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.app-groups-member-meta {
  font-size: 15px;
  color: var(--app-text-secondary);
}

.app-groups-member-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
