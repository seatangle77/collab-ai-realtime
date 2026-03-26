<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
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
      <div class="app-sessions-meta">
        <span class="app-sessions-user" v-if="currentUser">
          {{ currentUser.name || currentUser.email }}
        </span>
        <span class="app-sessions-group">
          <span class="app-sessions-group-label">当前群组：</span>
          <span class="app-sessions-group-value">{{ currentGroup?.name || '未选择' }}</span>
        </span>
      </div>
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
          + 新建会话
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
                  class="app-sessions-item-tag"
                >
                  {{ formatStatus(session) }}
                </el-tag>
              </div>
              <div class="app-sessions-item-meta">
                <span>创建：{{ formatDateTimeToCST(session.created_at) }}</span>
                <span>更新：{{ formatDateTimeToCST(session.last_updated) }}</span>
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
                @click.stop
              >
                ⋯
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
  padding-bottom: 80px; /* 给 FAB 留空间 */
}

.app-sessions-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
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
  flex-direction: column;
  gap: 12px;
}

.app-sessions-empty-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
}

/* Tab 栏 + 新建按钮同行 */
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
  transition: background-color 0.18s ease, color 0.18s ease;
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
  transition: background-color 0.18s ease, box-shadow 0.18s ease, transform 0.1s ease;
}

.app-sessions-primary-btn:hover {
  background: #1d4ed8;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.3);
  transform: translateY(-1px);
}

/* 移动端：隐藏 inline 新建按钮，改用 FAB */
.app-sessions-new-btn-inline {
  display: inline-block;
}

/* 会话列表 */
.app-sessions-list-wrapper {
  margin-top: 4px;
}

.app-sessions-loading {
  padding: 16px 0;
  font-size: 13px;
  color: #6b7280;
}

.app-sessions-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 整行可点击 */
.app-sessions-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.04);
  cursor: pointer;
  transition: background-color 0.16s ease, box-shadow 0.16s ease, transform 0.08s ease;
}

.app-sessions-item:hover {
  background: #f8faff;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.1);
  transform: translateY(-1px);
}

.app-sessions-item:active {
  transform: translateY(0);
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
  font-size: 14px;
  font-weight: 600;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-sessions-item-tag {
  flex-shrink: 0;
}

.app-sessions-item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #6b7280;
}

/* ⋯ 更多按钮 */
.app-sessions-more-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: #9ca3af;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.16s ease, color 0.16s ease;
  line-height: 1;
  padding-bottom: 4px;
}

.app-sessions-more-btn:hover {
  background: #f3f4f6;
  color: #374151;
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
  bottom: 80px; /* 底部 tab bar 高度之上 */
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: none;
  background: #2563eb;
  color: #ffffff;
  font-size: 28px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.4);
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

  .app-sessions-item-meta {
    gap: 6px;
  }
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
