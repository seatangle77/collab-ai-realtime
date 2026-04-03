<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MoreFilled, Plus } from '@element-plus/icons-vue'
import { formatDateTimeToCST } from '../../utils/datetime'
import { listMyGroups } from '../../api/appGroups'
import {
  type AppChatSession,
  listGroupSessions,
  createSession,
  updateSession,
  cancelSession,
  endSession,
} from '../../api/appSessions'

interface AppUser {
  id: string
  name: string
  email: string
}

interface AppGroupSummary {
  id: string
  name: string
}

type SessionFilter = 'active' | 'ended' | 'all'

function loadCurrentUser(): AppUser | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem('app_user')
  if (!raw) return null
  try {
    return JSON.parse(raw) as AppUser
  } catch {
    return null
  }
}

function loadCurrentGroup(): AppGroupSummary | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem('app_current_group')
  if (!raw) return null
  try {
    return JSON.parse(raw) as AppGroupSummary
  } catch {
    return null
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

const currentUser = ref<AppUser | null>(loadCurrentUser())
const currentGroup = ref<AppGroupSummary | null>(loadCurrentGroup())

const loading = ref(false)
const sessions = ref<AppChatSession[]>([])
const activeFilter = ref<SessionFilter>('active')
const includeEndedLoaded = ref(false)
const allSessionsCache = ref<AppChatSession[] | null>(null)

const myGroups = ref<AppGroupSummary[]>([])
const groupsLoading = ref(false)

const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({
  sessionTitle: '',
  plannedStart: null as string | null,
  groupId: '' as string,
})

const createRules: FormRules<typeof createForm> = {
  sessionTitle: [{ required: true, message: '请输入会话标题', trigger: 'blur' }],
  groupId: [{ required: true, message: '请选择所属群组', trigger: 'change' }],
}

const editDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({
  id: '',
  sessionTitle: '',
  plannedStart: null as string | null,
  canEditTime: false,
})

const editRules: FormRules<typeof editForm> = {
  sessionTitle: [{ required: true, message: '请输入会话标题', trigger: 'blur' }],
}

const hasCurrentGroup = computed(() => !!currentGroup.value)

function isNotStartedSession(session: AppChatSession): boolean {
  return session.status === 'not_started'
}

const filteredSessions = computed(() => {
  if (activeFilter.value === 'active') {
    return sessions.value
  }
  if (activeFilter.value === 'all') {
    return sessions.value
  }
  return sessions.value.filter((s) => s.status === 'ended')
})

function statusTagType(session: AppChatSession): 'warning' | 'primary' | 'info' {
  if (session.status === 'not_started') return 'warning'
  if (session.status === 'ongoing') return 'primary'
  return 'info'
}

function formatStatus(session: AppChatSession): string {
  if (session.status === 'ended') return '已结束'
  if (session.status === 'not_started') return '未开始'
  return '进行中'
}

function canCancelSession(session: AppChatSession): boolean {
  return session.status === 'not_started'
}

function canEndSession(session: AppChatSession): boolean {
  return session.status === 'ongoing'
}

async function fetchSessions(filter: SessionFilter = activeFilter.value) {
  if (!currentGroup.value) {
    sessions.value = []
    return
  }
  loading.value = true
  try {
    if (filter === 'active') {
      const data = await listGroupSessions(currentGroup.value.id, { includeEnded: false })
      sessions.value = data
    } else {
      const data = await listGroupSessions(currentGroup.value.id, { includeEnded: true })
      sessions.value = data
      allSessionsCache.value = data
      includeEndedLoaded.value = true
    }
  } catch (err) {
    console.error(err)
    ElMessage.error(extractErrorMessage(err))
    sessions.value = []
  } finally {
    loading.value = false
  }
}

async function fetchMyGroupsForSessions() {
  groupsLoading.value = true
  try {
    const data = await listMyGroups()
    myGroups.value = data.map((g) => ({ id: g.id, name: g.name }))
    if (!currentGroup.value && myGroups.value.length) {
      const first = myGroups.value[0]!
      currentGroup.value = { id: first.id, name: first.name }
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('app_current_group', JSON.stringify(currentGroup.value))
      }
    }
  } catch (err) {
    console.error(err)
    ElMessage.error(extractErrorMessage(err))
  } finally {
    groupsLoading.value = false
  }
}

function handleFilterChange(filter: SessionFilter) {
  if (activeFilter.value === filter) return
  activeFilter.value = filter
  if (filter === 'active') {
    void fetchSessions('active')
  } else if (includeEndedLoaded.value && allSessionsCache.value) {
    sessions.value = allSessionsCache.value
  } else {
    void fetchSessions(filter)
  }
}

async function openCreateDialog() {
  if (!myGroups.value.length) {
    await fetchMyGroupsForSessions()
  }
  if (!myGroups.value.length) {
    ElMessage.info('你还没有加入任何群组，请先在「我的群组」中创建或加入群组')
    return
  }
  const currentId = currentGroup.value?.id
  const defaultId =
    currentId && myGroups.value.some((g) => g.id === currentId) ? currentId : myGroups.value[0]!.id

  createForm.sessionTitle = ''
  createForm.plannedStart = null
  createForm.groupId = defaultId
  createDialogVisible.value = true
}

async function submitCreate() {
  if (!currentGroup.value || !createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const targetGroupId = createForm.groupId
      const options: Parameters<typeof createSession>[2] = {}
      if (createForm.plannedStart) {
        options.createdAt = createForm.plannedStart
        options.lastUpdatedAt = createForm.plannedStart
      }
      const created = await createSession(targetGroupId, createForm.sessionTitle, options)
      ElMessage.success('创建会话成功')
      createDialogVisible.value = false

      const currentId = currentGroup.value?.id
      if (currentId && currentId === targetGroupId) {
        sessions.value = [created, ...sessions.value]
      } else {
        const g = myGroups.value.find((x) => x.id === targetGroupId)
        if (g) {
          const cg = { id: g.id, name: g.name }
          currentGroup.value = cg
          if (typeof window !== 'undefined') {
            window.localStorage.setItem('app_current_group', JSON.stringify(cg))
          }
        }
      }
      void fetchSessions(activeFilter.value)
    } catch (err) {
      console.error(err)
      ElMessage.error(extractErrorMessage(err))
    }
  })
}

function openEditDialog(session: AppChatSession) {
  editForm.id = session.id
  editForm.sessionTitle = session.session_title
  const notStarted = isNotStartedSession(session)
  editForm.canEditTime = notStarted
  editForm.plannedStart = notStarted ? session.created_at : null
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const options: Parameters<typeof updateSession>[2] = {}
      if (editForm.canEditTime && editForm.plannedStart) {
        options.createdAt = editForm.plannedStart
        options.lastUpdatedAt = editForm.plannedStart
      }
      await updateSession(editForm.id, editForm.sessionTitle, options)
      ElMessage.success('更新会话成功')
      editDialogVisible.value = false
      void fetchSessions(activeFilter.value)
    } catch (err) {
      console.error(err)
      ElMessage.error(extractErrorMessage(err))
    }
  })
}

async function handleCancelSession(session: AppChatSession) {
  if (!canCancelSession(session)) return
  try {
    await ElMessageBox.confirm('确认要取消这个会话吗？取消后将被删除，无法恢复。', '取消会话', {
      type: 'warning',
      confirmButtonText: '取消会话',
      cancelButtonText: '返回',
    })
  } catch {
    return
  }
  try {
    await cancelSession(session.id)
    ElMessage.success('会话已取消')
    void fetchSessions(activeFilter.value)
  } catch (err) {
    console.error(err)
    ElMessage.error(extractErrorMessage(err))
  }
}

async function handleEndSession(session: AppChatSession) {
  if (!canEndSession(session)) return
  try {
    await ElMessageBox.confirm('确认要结束这个会话吗？结束后将标记为已结束。', '结束会话', {
      type: 'warning',
      confirmButtonText: '结束',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await endSession(session.id)
    ElMessage.success('会话已结束')
    void fetchSessions(activeFilter.value)
  } catch (err) {
    console.error(err)
    ElMessage.error(extractErrorMessage(err))
  }
}

function goToGroups() {
  router.push('/app/groups')
}

function goToDetail(session: AppChatSession) {
  router.push({
    name: 'AppSessionDetail',
    params: { id: session.id },
    state: { session } as any,
  })
}

onMounted(() => {
  void fetchMyGroupsForSessions()
  if (currentGroup.value) {
    void fetchSessions('active')
  }
})
</script>

<template>
  <div class="app-sessions">
    <div class="app-sessions-header">
      <h2 class="app-sessions-title">我的会话</h2>
      <span class="app-sessions-group-inline">当前群组：{{ currentGroup?.name || '未选择' }}</span>
    </div>

    <div v-if="!hasCurrentGroup" class="app-sessions-empty-group">
      <p class="app-sessions-empty-text">
        当前未选择群组，请先前往「我的群组」选择或加入一个群组。
      </p>
      <button type="button" class="app-sessions-primary-btn" @click="goToGroups">
        前往我的群组
      </button>
    </div>

    <template v-else>
      <!-- Tab 栏 + 新建按钮同行 -->
      <div class="app-sessions-toolbar">
        <div class="app-sessions-tabs">
          <button
            type="button"
            class="app-sessions-tab"
            :data-active="activeFilter === 'active'"
            @click="handleFilterChange('active')"
          >
            进行中
          </button>
          <button
            type="button"
            class="app-sessions-tab"
            :data-active="activeFilter === 'ended'"
            @click="handleFilterChange('ended')"
          >
            已结束
          </button>
          <button
            type="button"
            class="app-sessions-tab"
            :data-active="activeFilter === 'all'"
            @click="handleFilterChange('all')"
          >
            全部
          </button>
        </div>
        <!-- 桌面端：Tab 同行显示 -->
        <button type="button" class="app-sessions-primary-btn app-sessions-new-btn-inline" @click="openCreateDialog">
          <el-icon class="app-sessions-new-icon" :size="16">
            <Plus />
          </el-icon>
          新建会话
        </button>
      </div>

      <div class="app-sessions-list-wrapper">
        <div v-if="loading" class="app-sessions-loading">正在加载会话列表...</div>

        <!-- 空状态：用 el-empty + 内联新建按钮 -->
        <el-empty
          v-else-if="filteredSessions.length === 0"
          :image-size="80"
          description="暂无会话，点击下方按钮创建第一个"
        >
          <el-button type="primary" @click="openCreateDialog">新建会话</el-button>
        </el-empty>

        <ul v-else class="app-sessions-list">
          <li
            v-for="session in filteredSessions"
            :key="session.id"
            class="app-sessions-item"
            @click="goToDetail(session)"
          >
            <div class="app-sessions-item-main">
              <div class="app-sessions-item-title-row">
                <span class="app-sessions-item-title">{{ session.session_title }}</span>
                <el-tag
                  :type="statusTagType(session)"
                  size="small"
                  effect="light"
                  class="app-sessions-item-tag"
                >
                  {{ formatStatus(session) }}
                </el-tag>
              </div>
              <div class="app-sessions-item-meta">
                创建：{{ formatDateTimeToCST(session.created_at) }}
                <span class="app-sessions-item-meta-sep">·</span>
                更新：{{ formatDateTimeToCST(session.last_updated) }}
              </div>
            </div>

            <!-- 右侧 ⋯ 下拉菜单，阻止点击冒泡到行 -->
            <el-dropdown
              trigger="click"
              @click.stop
              @command="(cmd: string) => {
                if (cmd === 'edit') openEditDialog(session)
                if (cmd === 'cancel') handleCancelSession(session)
                if (cmd === 'end') handleEndSession(session)
              }"
            >
              <button
                type="button"
                class="app-sessions-more-btn"
                aria-label="更多操作"
                @click.stop
              >
                <el-icon class="app-sessions-more-icon" :size="18">
                  <MoreFilled />
                </el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">编辑标题</el-dropdown-item>
                  <el-dropdown-item
                    v-if="canCancelSession(session)"
                    command="cancel"
                    class="app-sessions-dropdown-danger"
                  >
                    取消会话
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="canEndSession(session)"
                    command="end"
                    class="app-sessions-dropdown-danger"
                  >
                    结束会话
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </li>
        </ul>
      </div>
    </template>

    <!-- 移动端 FAB 新建按钮 -->
    <button
      v-if="hasCurrentGroup"
      type="button"
      class="app-sessions-fab"
      @click="openCreateDialog"
    >
      +
    </button>

    <!-- 新建会话弹窗 -->
    <el-dialog v-model="createDialogVisible" title="新建会话" :width="'min(480px, 92vw)'">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="所属群组" prop="groupId">
          <el-select
            v-model="createForm.groupId"
            placeholder="请选择所属群组"
            :loading="groupsLoading"
            :disabled="!myGroups.length"
          >
            <el-option
              v-for="g in myGroups"
              :key="g.id"
              :label="g.name"
              :value="g.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="会话标题" prop="sessionTitle">
          <el-input v-model="createForm.sessionTitle" placeholder="请输入这次会话的标题" />
        </el-form-item>
        <el-form-item label="预设开始" prop="plannedStart">
          <el-date-picker
            v-model="createForm.plannedStart"
            type="datetime"
            placeholder="可选：设置这次会话的起始时间"
            value-format="YYYY-MM-DDTHH:mm:ss[Z]"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createDialogVisible = false">取 消</el-button>
          <el-button type="primary" @click="submitCreate">确 定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 编辑会话弹窗 -->
    <el-dialog v-model="editDialogVisible" title="编辑会话" :width="'min(480px, 92vw)'">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="80px">
        <el-form-item label="会话标题" prop="sessionTitle">
          <el-input v-model="editForm.sessionTitle" placeholder="请输入新的会话标题" />
        </el-form-item>
        <el-form-item v-if="editForm.canEditTime" label="预设开始">
          <el-date-picker
            v-model="editForm.plannedStart"
            type="datetime"
            placeholder="仅未开始会话可编辑"
            value-format="YYYY-MM-DDTHH:mm:ss[Z]"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editDialogVisible = false">取 消</el-button>
          <el-button type="primary" @click="submitEdit">保 存</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.app-sessions {
  max-width: 880px;
  margin: 0 auto;
  padding-bottom: 88px; /* FAB + 与 AppLayout 底栏留白 */
}

.app-sessions-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.app-sessions-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
}

.app-sessions-group-inline {
  font-size: 13px;
  color: var(--app-text-secondary);
}

.app-sessions-empty-group {
  margin-top: 16px;
  padding: 18px 20px;
  border-radius: var(--app-radius-md);
  background: var(--app-bg-elevated);
  border: 1px dashed var(--app-border);
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: var(--app-shadow-card);
}

.app-sessions-empty-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
  color: var(--app-text-secondary);
}

/* 筛选胶囊 + 新建（与 demo：独立圆角按钮 + 主色实心） */
.app-sessions-toolbar {
  margin-top: 16px;
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.app-sessions-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.app-sessions-tab {
  border-radius: 999px;
  border: none;
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    border-color 0.18s ease;
}

.app-sessions-tab[data-active='true'] {
  background: var(--app-primary);
  color: #fff;
}

.app-sessions-tab:not([data-active='true']) {
  background: #f1f5f9;
  color: var(--app-text-secondary);
}

.app-sessions-tab:not([data-active='true']):hover {
  background: #e2e8f0;
  color: var(--app-text-primary);
}

.app-sessions-primary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 8px;
  border: 1px solid var(--app-primary);
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  background: var(--app-primary);
  color: #ffffff;
  cursor: pointer;
  box-shadow: var(--app-shadow-card);
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.app-sessions-primary-btn:hover {
  background: var(--app-primary-hover);
  border-color: var(--app-primary-hover);
}

.app-sessions-new-icon {
  flex-shrink: 0;
}

/* 移动端：隐藏 inline 新建按钮，改用 FAB */
.app-sessions-new-btn-inline {
  display: inline-flex;
}

/* 会话列表 */
.app-sessions-list-wrapper {
  margin-top: 4px;
}

.app-sessions-loading {
  padding: 20px 0;
  font-size: 14px;
  color: var(--app-text-secondary);
}

.app-sessions-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 整行可点击（卡片：浅边框 + 轻阴影，hover 主色边） */
.app-sessions-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: var(--app-radius-md);
  background: var(--app-bg-elevated);
  border: 1px solid var(--app-border);
  box-shadow: var(--app-shadow-card);
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background-color 0.18s ease;
}

.app-sessions-item:hover {
  border-color: var(--app-primary);
  box-shadow: var(--app-shadow-soft);
}

.app-sessions-item:active {
  box-shadow: var(--app-shadow-card);
}

.app-sessions-item-main {
  flex: 1;
  min-width: 0;
}

.app-sessions-item-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.app-sessions-item-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-sessions-item-tag {
  flex-shrink: 0;
}

.app-sessions-item-meta {
  font-size: 13px;
  color: var(--app-text-secondary);
  line-height: 1.45;
}

.app-sessions-item-meta-sep {
  margin: 0 6px;
  color: var(--app-text-muted);
}

/* 更多 */
.app-sessions-more-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.app-sessions-more-btn:hover {
  background: var(--app-bg-page);
  color: var(--app-text-primary);
}

.app-sessions-more-icon {
  transform: rotate(90deg);
}

/* 结束会话选项红色 */
:global(.app-sessions-dropdown-danger) {
  color: #b91c1c !important;
}

:global(.app-sessions-dropdown-danger:not(.is-disabled):hover) {
  background: #fef2f2 !important;
  color: #991b1b !important;
}

/* 移动端 FAB */
.app-sessions-fab {
  display: none;
  position: fixed;
  right: 20px;
  bottom: 88px; /* 底部 tab bar + 安全区之上 */
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: none;
  background: var(--app-primary);
  color: #ffffff;
  font-size: 28px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.35);
  z-index: 100;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.app-sessions-fab:active {
  transform: scale(0.95);
}

/* 移动端响应式 */
@media (max-width: 480px) {
  .app-sessions-new-btn-inline {
    display: none;
  }

  .app-sessions-fab {
    display: flex;
  }

  .app-sessions-tab {
    padding: 6px 10px;
    font-size: 12px;
  }
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
