<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTimeToCST } from '../../utils/datetime'
import { listMyGroups } from '../../api/appGroups'
import {
  type AppChatSession,
  type AppTranscript,
  listGroupSessions,
  createSession,
  updateSession,
  endSession,
  listSessionTranscripts,
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

const transcriptsDialogVisible = ref(false)
const transcriptsLoading = ref(false)
const transcripts = ref<AppTranscript[]>([])
const currentSessionForTranscripts = ref<AppChatSession | null>(null)

const hasCurrentGroup = computed(() => !!currentGroup.value)

function isNotStartedSession(session: AppChatSession): boolean {
  return (
    (session.is_active === true || session.is_active == null) &&
    session.ended_at == null &&
    session.created_at === session.last_updated
  )
}

const filteredSessions = computed(() => {
  if (activeFilter.value === 'active') {
    return sessions.value
  }
  if (activeFilter.value === 'all') {
    return sessions.value
  }
  // 已结束
  return sessions.value.filter((s) => s.ended_at != null || s.is_active === false)
})

function formatStatus(session: AppChatSession): string {
  if (session.ended_at != null || session.is_active === false) {
    return '已结束'
  }
  if (isNotStartedSession(session)) {
    return '未开始'
  }
  return '进行中'
}

function canEndSession(session: AppChatSession): boolean {
  return session.ended_at == null && session.is_active !== false
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
      // all / ended：用 include_ended=true 拉全量，再在前端过滤
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
    // 只保留 id/name 字段
    myGroups.value = data.map((g) => ({ id: g.id, name: g.name }))

    // 如果当前没有已选群组，但用户有群组，默认选第一个群组
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
  // 确保群组列表已加载（无论当前是否在 loading 中，都先等一次拉取结束）
  if (!myGroups.value.length) {
    await fetchMyGroupsForSessions()
  }
  if (!myGroups.value.length) {
    ElMessage.info('你还没有加入任何群组，请先在「我的群组」中创建或加入群组')
    return
  }

  // 默认选当前群组；若当前群组不在列表中，则选第一个
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

      // 若新建会话在当前群组下，直接插入列表顶部保证立即可见
      if (currentId && currentId === targetGroupId) {
        sessions.value = [created, ...sessions.value]
      } else {
        // 否则自动切换当前群组到目标群组
        const g = myGroups.value.find((x) => x.id === targetGroupId)
        if (g) {
          const cg = { id: g.id, name: g.name }
          currentGroup.value = cg
          if (typeof window !== 'undefined') {
            window.localStorage.setItem('app_current_group', JSON.stringify(cg))
          }
        }
      }

      // 再次拉取以与服务端状态对齐（例如排序规则/最新状态）
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

async function openTranscripts(session: AppChatSession) {
  currentSessionForTranscripts.value = session
  transcriptsDialogVisible.value = true
  transcriptsLoading.value = true
  transcripts.value = []
  try {
    const data = await listSessionTranscripts(session.id)
    transcripts.value = data
  } catch (err) {
    console.error(err)
    ElMessage.error(extractErrorMessage(err))
  } finally {
    transcriptsLoading.value = false
  }
}

function goToGroups() {
  router.push('/app/groups')
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
      <div class="app-sessions-meta">
        <span class="app-sessions-user" v-if="currentUser">
          {{ currentUser.name || currentUser.email }}（{{ currentUser.email }}）
        </span>
        <span class="app-sessions-group">
          <span class="app-sessions-group-label">当前群组：</span>
          <span class="app-sessions-group-value">
            {{ currentGroup?.name || '未选择' }}
          </span>
        </span>
      </div>
    </div>

    <div v-if="!hasCurrentGroup" class="app-sessions-empty-group">
      <p class="app-sessions-empty-text">
        当前未选择群组，请先前往「我的群组」选择或加入一个群组。选择的当前群组会影响这里展示的会话列表。
      </p>
      <button type="button" class="app-sessions-primary-btn" @click="goToGroups">
        前往我的群组
      </button>
    </div>

    <template v-else>
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
        <button type="button" class="app-sessions-primary-btn" @click="openCreateDialog">
          新建会话
        </button>
      </div>

      <div class="app-sessions-list-wrapper">
        <div v-if="loading" class="app-sessions-loading">
          正在加载会话列表...
        </div>
        <div v-else-if="filteredSessions.length === 0" class="app-sessions-empty">
          <p class="app-sessions-empty-text">
            当前筛选条件下暂无会话。你可以点击右上角「新建会话」按钮创建一次会话，或稍后再来查看历史记录。
          </p>
        </div>
        <ul v-else class="app-sessions-list">
          <li v-for="session in filteredSessions" :key="session.id" class="app-sessions-item">
            <div class="app-sessions-item-main">
              <div class="app-sessions-item-title-row">
                <span class="app-sessions-item-title">{{ session.session_title }}</span>
                <span class="app-sessions-item-status" :data-status="formatStatus(session)">
                  {{ formatStatus(session) }}
                </span>
              </div>
              <div class="app-sessions-item-meta">
                <span>创建时间：{{ formatDateTimeToCST(session.created_at) }}</span>
                <span>最后更新：{{ formatDateTimeToCST(session.last_updated) }}</span>
              </div>
            </div>
            <div class="app-sessions-item-actions">
              <button type="button" class="app-sessions-secondary-btn" @click="openTranscripts(session)">
                查看转写
              </button>
              <button type="button" class="app-sessions-secondary-btn" @click="openEditDialog(session)">
                编辑
              </button>
              <button
                type="button"
                class="app-sessions-danger-btn"
                :disabled="!canEndSession(session)"
                @click="handleEndSession(session)"
              >
                结束会话
              </button>
            </div>
          </li>
        </ul>
      </div>
    </template>

    <el-dialog v-model="createDialogVisible" title="新建会话" width="420px">
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

    <el-dialog v-model="editDialogVisible" title="编辑会话" width="420px">
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

    <el-dialog
      v-model="transcriptsDialogVisible"
      :title="currentSessionForTranscripts ? `会话转写 - ${currentSessionForTranscripts.session_title}` : '会话转写'"
      width="680px"
    >
      <div class="app-sessions-transcripts">
        <div v-if="transcriptsLoading" class="app-sessions-loading">
          正在加载转写记录...
        </div>
        <div v-else-if="!transcripts.length" class="app-sessions-empty">
          <p class="app-sessions-empty-text">
            当前会话暂无转写记录。你可以稍后再来查看，或在其它页面触发转写生成。
          </p>
        </div>
        <ul v-else class="app-sessions-transcripts-list">
          <li
            v-for="item in transcripts"
            :key="item.transcript_id"
            class="app-sessions-transcripts-item"
          >
            <div class="app-sessions-transcripts-meta">
              <span class="app-sessions-transcripts-speaker">
                {{ item.speaker || '未知说话人' }}
              </span>
              <span class="app-sessions-transcripts-time">
                {{ item.start }} - {{ item.end }}
              </span>
            </div>
            <p class="app-sessions-transcripts-text">
              {{ item.text }}
            </p>
          </li>
        </ul>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="transcriptsDialogVisible = false">关 闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.app-sessions {
  max-width: 880px;
  margin: 0 auto;
}

.app-sessions-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.app-sessions-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.app-sessions-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-size: 12px;
}

.app-sessions-user {
  color: #4b5563;
}

.app-sessions-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #374151;
}

.app-sessions-group-label {
  color: #6b7280;
}

.app-sessions-group-value {
  font-weight: 500;
}

.app-sessions-empty-group {
  margin-top: 16px;
  padding: 16px 18px;
  border-radius: 12px;
  background: #f9fafb;
  border: 1px dashed #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.app-sessions-desc,
.app-sessions-empty-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
}

.app-sessions-toolbar {
  margin-top: 16px;
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.app-sessions-tabs {
  display: inline-flex;
  gap: 6px;
  padding: 2px;
  border-radius: 999px;
  background: #f3f4f6;
}

.app-sessions-tab {
  border-radius: 999px;
  border: none;
  padding: 6px 14px;
  font-size: 13px;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;
}

.app-sessions-tab[data-active='true'] {
  background: #ffffff;
  color: #1d4ed8;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12);
}

.app-sessions-tab:not([data-active='true']):hover {
  color: #111827;
}

.app-sessions-primary-btn {
  border-radius: 999px;
  border: 1px solid #2563eb;
  padding: 6px 16px;
  font-size: 13px;
  background: #2563eb;
  color: #ffffff;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.22);
  transition:
    background-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.1s ease;
}

.app-sessions-primary-btn:hover {
  background: #1d4ed8;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.3);
  transform: translateY(-1px);
}

.app-sessions-primary-btn:active {
  transform: translateY(0);
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.2);
}

.app-sessions-secondary-btn,
.app-sessions-danger-btn {
  border-radius: 999px;
  border: 1px solid #e5e7eb;
  padding: 4px 12px;
  font-size: 12px;
  background: #ffffff;
  color: #374151;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;
}

.app-sessions-secondary-btn:hover {
  background: #f3f4f6;
}

.app-sessions-danger-btn {
  border-color: rgba(248, 113, 113, 0.5);
  color: #b91c1c;
}

.app-sessions-danger-btn:hover:enabled {
  background: #fef2f2;
  border-color: #ef4444;
  color: #991b1b;
}

.app-sessions-danger-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.app-sessions-list-wrapper {
  margin-top: 4px;
}

.app-sessions-loading {
  padding: 16px 0;
  font-size: 13px;
  color: #6b7280;
}

.app-sessions-empty {
  margin-top: 8px;
  padding: 16px 18px;
  border-radius: 12px;
  background: #f9fafb;
  border: 1px dashed #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.app-sessions-list {
  list-style: none;
  margin: 0;
  margin-top: 4px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.app-sessions-item {
  display: flex;
  justify-content: space-between;
  align-items: stretch;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.04);
}

.app-sessions-item-main {
  flex: 1;
  min-width: 0;
}

.app-sessions-item-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.app-sessions-item-title {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.app-sessions-item-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #ecfdf3;
  color: #166534;
}

.app-sessions-item-status[data-status='已结束'] {
  background: #fef2f2;
  color: #b91c1c;
}

.app-sessions-item-meta {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #6b7280;
}

.app-sessions-item-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.app-sessions-transcripts {
  max-height: 420px;
  overflow: auto;
}

.app-sessions-transcripts-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.app-sessions-transcripts-item {
  padding: 8px 10px;
  border-radius: 8px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}

.app-sessions-transcripts-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.app-sessions-transcripts-speaker {
  font-weight: 500;
}

.app-sessions-transcripts-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: #111827;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>