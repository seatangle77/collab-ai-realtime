<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getGroupDetail, renameGroup, kickMember, leaveGroup } from '../../api/appGroups'
import type { AppGroupDetail, AppGroupMember } from '../../api/appGroups'
import { listGroupSessions, createSession } from '../../api/appSessions'
import type { AppChatSession } from '../../api/appSessions'
import { formatDateTimeToCST } from '../../utils/datetime'
import { extractErrorMessage } from '../../utils/error'

const route = useRoute()
const router = useRouter()
const groupId = route.params.id as string

interface AppUser {
  id: string
  name: string
  email: string
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

const currentUser = ref<AppUser | null>(loadUserFromStorage())
const currentUserId = computed(() => currentUser.value?.id ?? null)

const groupDetail = ref<AppGroupDetail | null>(null)
const sessions = ref<AppChatSession[]>([])
const pageLoading = ref(true)
const error = ref('')

const myRole = computed(() => groupDetail.value?.my_role ?? null)
const isLeader = computed(() => myRole.value === 'leader')

// 发起讨论 dialog
const createSessionVisible = ref(false)
const createSessionFormRef = ref<FormInstance>()
const createSessionForm = reactive({ title: '' })
const createSessionLoading = ref(false)
const createSessionRules: FormRules<typeof createSessionForm> = {
  title: [{ required: true, message: '请输入会话标题', trigger: 'blur' }],
}

function sessionStatusLabel(status: string | null | undefined): string {
  if (status === 'not_started') return '未开始'
  if (status === 'ongoing') return '进行中'
  if (status === 'ended') return '已结束'
  return '未知'
}

function sessionStatusType(status: string | null | undefined): string {
  if (status === 'not_started') return 'info'
  if (status === 'ongoing') return 'success'
  if (status === 'ended') return ''
  return 'info'
}

async function loadData() {
  pageLoading.value = true
  error.value = ''
  const [detailResult, sessionsResult] = await Promise.allSettled([
    getGroupDetail(groupId, { noRedirectOn401: true }),
    listGroupSessions(groupId, { includeEnded: true }, { noRedirectOn401: true }),
  ])

  if (detailResult.status === 'fulfilled') {
    if (detailResult.value.my_role === null || detailResult.value.my_role === undefined) {
      error.value = '您不是该群组的成员，无法查看此页面'
    } else {
      groupDetail.value = detailResult.value
    }
  } else {
    error.value = extractErrorMessage(detailResult.reason) || '加载群组信息失败，请检查是否有权限访问该群组'
  }

  if (sessionsResult.status === 'fulfilled') {
    sessions.value = sessionsResult.value
  }
  // sessions 加载失败静默处理，不影响主体展示

  pageLoading.value = false
}

async function handleRename() {
  if (!groupDetail.value || !isLeader.value) return
  const oldName = groupDetail.value.group.name
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
    const detail = await renameGroup(groupId, finalName)
    groupDetail.value = detail
    ElMessage.success('群组名称已更新')
  } catch (e) {
    ElMessage.error(extractErrorMessage(e) || '修改群组名称失败')
  }
}

async function handleKick(member: AppGroupMember) {
  if (!isLeader.value) return
  const displayName = member.user_name || member.user_id

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
    const detail = await kickMember(groupId, member.user_id)
    groupDetail.value = detail
    ElMessage.success('已将成员移出群组')
  } catch (e) {
    ElMessage.error(extractErrorMessage(e) || '踢出成员失败')
  }
}

async function handleLeave() {
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
    await leaveGroup(groupId)
    ElMessage.success('已退出群组')
    router.push('/app/groups')
  } catch (e) {
    ElMessage.error(extractErrorMessage(e) || '退出群组失败')
  }
}

function openCreateSession() {
  createSessionForm.title = ''
  createSessionVisible.value = true
}

async function submitCreateSession() {
  if (!createSessionFormRef.value) return
  await createSessionFormRef.value.validate(async (valid) => {
    if (!valid) return
    createSessionLoading.value = true
    try {
      const session = await createSession(groupId, createSessionForm.title.trim())
      sessions.value.unshift(session)
      createSessionVisible.value = false
      ElMessage.success('会话创建成功')
    } catch (e) {
      ElMessage.error(extractErrorMessage(e) || '创建会话失败')
    } finally {
      createSessionLoading.value = false
    }
  })
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="app-group-detail-page">
    <!-- 顶部导航 -->
    <div class="app-group-detail-nav">
      <el-button text @click="router.push('/app/groups')">← 返回我的群组</el-button>
      <span class="app-group-detail-nav-title">
        {{ groupDetail?.group.name ?? groupId }}
      </span>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="app-group-detail-error">
      <p class="app-group-detail-error-msg">{{ error }}</p>
      <el-button @click="router.push('/app/groups')">返回群组列表</el-button>
    </div>

    <template v-else-if="!pageLoading">
      <!-- 群组信息卡 -->
      <el-card class="app-group-detail-card" shadow="never">
        <div class="app-group-detail-info-header">
          <div>
            <div class="app-group-detail-name-row">
              <h2 class="app-group-detail-name">{{ groupDetail?.group.name }}</h2>
              <el-tag v-if="isLeader" type="warning" size="small">群主</el-tag>
              <el-tag v-else type="" size="small">成员</el-tag>
              <el-tag v-if="groupDetail && !groupDetail.group.is_active" type="info" size="small">已停用</el-tag>
            </div>
            <div class="app-group-detail-meta">
              <span class="app-group-detail-id">ID：{{ groupDetail?.group.id }}</span>
              <span class="app-group-detail-dot">·</span>
              <span>创建时间：{{ groupDetail ? formatDateTimeToCST(groupDetail.group.created_at) : '' }}</span>
              <span class="app-group-detail-dot">·</span>
              <span>成员数：{{ groupDetail?.member_count ?? 0 }}</span>
            </div>
          </div>
          <div class="app-group-detail-actions">
            <el-button v-if="isLeader" size="small" @click="handleRename">修改名称</el-button>
            <el-button v-if="!isLeader" size="small" type="danger" @click="handleLeave">退出群组</el-button>
          </div>
        </div>
      </el-card>

      <!-- 成员列表卡 -->
      <el-card class="app-group-detail-card" shadow="never">
        <h3 class="app-group-detail-section-title">
          成员（{{ groupDetail?.member_count ?? 0 }} 人）
        </h3>
        <div class="app-group-detail-members">
          <div
            v-for="m in groupDetail?.members ?? []"
            :key="m.user_id"
            class="app-group-detail-member-item"
          >
            <div class="app-group-detail-member-main">
              <div class="app-group-detail-member-avatar">
                {{ (m.user_name || m.user_id).slice(0, 1).toUpperCase() }}
              </div>
              <div class="app-group-detail-member-text">
                <div class="app-group-detail-member-name-row">
                  <span class="app-group-detail-member-name">{{ m.user_name || m.user_id }}</span>
                  <span v-if="currentUserId && m.user_id === currentUserId" class="app-group-detail-self-tag">我</span>
                </div>
                <div class="app-group-detail-member-meta">
                  角色：{{ m.role === 'leader' ? '群主' : '成员' }}
                </div>
              </div>
            </div>
            <div class="app-group-detail-member-actions">
              <el-tag :type="m.status === 'active' ? 'success' : 'info'" size="small">
                {{ m.status === 'active' ? '在群' : m.status }}
              </el-tag>
              <el-button
                v-if="isLeader && !(currentUserId && m.user_id === currentUserId)"
                type="danger"
                link
                size="small"
                @click="handleKick(m)"
              >
                移出
              </el-button>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 历史会话卡 -->
      <el-card class="app-group-detail-card" shadow="never">
        <div class="app-group-detail-sessions-header">
          <h3 class="app-group-detail-section-title">历史会话</h3>
          <el-button
            type="primary"
            size="small"
            :disabled="!groupDetail?.group.is_active"
            @click="openCreateSession"
          >
            发起讨论
          </el-button>
        </div>

        <p v-if="sessions.length === 0" class="app-group-detail-sessions-empty">
          该群组暂无历史会话，点击「发起讨论」创建第一个会话。
        </p>

        <div v-else class="app-group-detail-sessions-list">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="app-group-detail-session-item"
          >
            <div class="app-group-detail-session-main">
              <span class="app-group-detail-session-title">{{ s.session_title }}</span>
              <el-tag :type="sessionStatusType(s.status)" size="small">
                {{ sessionStatusLabel(s.status) }}
              </el-tag>
            </div>
            <div class="app-group-detail-session-meta">
              {{ formatDateTimeToCST(s.created_at) }}
            </div>
          </div>
        </div>
      </el-card>
    </template>

    <!-- 发起讨论 dialog -->
    <el-dialog v-model="createSessionVisible" title="发起讨论" :width="'min(480px, 92vw)'">
      <el-form
        ref="createSessionFormRef"
        :model="createSessionForm"
        :rules="createSessionRules"
        label-width="80px"
      >
        <el-form-item label="会话标题" prop="title">
          <el-input v-model="createSessionForm.title" placeholder="请输入会话标题" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createSessionVisible = false">取消</el-button>
          <el-button type="primary" :loading="createSessionLoading" @click="submitCreateSession">
            发起
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.app-group-detail-page {
  max-width: 880px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.app-group-detail-nav {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}

.app-group-detail-nav-title {
  font-size: 14px;
  color: #6b7280;
}

.app-group-detail-error {
  padding: 32px 16px;
  text-align: center;
}

.app-group-detail-error-msg {
  margin: 0 0 16px;
  font-size: 14px;
  color: #ef4444;
}

.app-group-detail-card {
  border-radius: 12px;
}

.app-group-detail-info-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.app-group-detail-name-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}

.app-group-detail-name {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.app-group-detail-meta {
  font-size: 12px;
  color: #6b7280;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.app-group-detail-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.app-group-detail-dot {
  color: #d1d5db;
}

.app-group-detail-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.app-group-detail-section-title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.app-group-detail-members {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.app-group-detail-member-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
}

.app-group-detail-member-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.app-group-detail-member-avatar {
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
  flex-shrink: 0;
}

.app-group-detail-member-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.app-group-detail-member-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.app-group-detail-member-name {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
}

.app-group-detail-self-tag {
  padding: 1px 6px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 11px;
}

.app-group-detail-member-meta {
  font-size: 12px;
  color: #6b7280;
}

.app-group-detail-member-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.app-group-detail-sessions-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.app-group-detail-sessions-header .app-group-detail-section-title {
  margin-bottom: 0;
}

.app-group-detail-sessions-empty {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
}

.app-group-detail-sessions-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.app-group-detail-session-item {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
}

.app-group-detail-session-main {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.app-group-detail-session-title {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
}

.app-group-detail-session-meta {
  font-size: 12px;
  color: #6b7280;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
