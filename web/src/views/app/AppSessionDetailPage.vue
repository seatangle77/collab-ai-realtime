<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  type AppChatSession,
  type AppTranscript,
  startSession,
  endSession,
  updateSession,
  listGroupSessions,
  listSessionTranscripts,
} from '../../api/appSessions'
import { listMyGroups } from '../../api/appGroups'
import { formatDateTimeToCST } from '../../utils/datetime'
import { extractErrorMessage } from '../../utils/error'

const route = useRoute()
const router = useRouter()
const sessionId = route.params.id as string

const session = ref<AppChatSession | null>(null)
const transcripts = ref<AppTranscript[]>([])
const pageLoading = ref(true)
const transcriptsLoading = ref(false)
const error = ref('')

const statusLabel = computed(() => {
  const s = session.value?.status
  if (s === 'ended') return '已结束'
  if (s === 'not_started') return '未开始'
  if (s === 'ongoing') return '进行中'
  return '未知'
})

const canStart = computed(() => session.value?.status === 'not_started')
const canEnd = computed(() => session.value?.status !== 'ended')

async function loadSession(): Promise<AppChatSession | null> {
  // 优先从 history.state 拿
  const stateSession = (window.history.state as any)?.session as AppChatSession | undefined
  if (stateSession && stateSession.id === sessionId) {
    return stateSession
  }
  // fallback：遍历用户所有群组的 sessions
  try {
    const groups = await listMyGroups()
    for (const g of groups) {
      const list = await listGroupSessions(g.id, { includeEnded: true }, { noRedirectOn401: true })
      const found = list.find((s) => s.id === sessionId)
      if (found) return found
    }
  } catch {
    // ignore
  }
  return null
}

async function loadTranscripts() {
  transcriptsLoading.value = true
  try {
    transcripts.value = await listSessionTranscripts(sessionId)
  } catch (err) {
    ElMessage.error(extractErrorMessage(err))
  } finally {
    transcriptsLoading.value = false
  }
}

async function loadData() {
  pageLoading.value = true
  error.value = ''
  try {
    const [sessionResult, transcriptsResult] = await Promise.allSettled([
      loadSession(),
      listSessionTranscripts(sessionId),
    ])
    if (sessionResult.status === 'fulfilled' && sessionResult.value) {
      session.value = sessionResult.value
    } else {
      error.value = '会话不存在或无权访问'
    }
    if (transcriptsResult.status === 'fulfilled') {
      transcripts.value = transcriptsResult.value
    }
  } finally {
    pageLoading.value = false
  }
}

async function handleStart() {
  if (!canStart.value) return
  try {
    const updated = await startSession(sessionId)
    session.value = updated
    ElMessage.success('会话已开始')
  } catch (err) {
    ElMessage.error(extractErrorMessage(err))
  }
}

async function handleEnd() {
  if (!canEnd.value) return
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
    const updated = await endSession(sessionId)
    session.value = updated
    ElMessage.success('会话已结束')
    await loadTranscripts()
  } catch (err) {
    ElMessage.error(extractErrorMessage(err))
  }
}

async function handleEditTitle() {
  if (!session.value) return
  let newTitle: string
  try {
    const result = await ElMessageBox.prompt('请输入新的会话标题', '修改标题', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: session.value.session_title,
      inputValidator: (v) => !!v?.trim() || '标题不能为空',
    })
    newTitle = (result.value as string).trim()
  } catch {
    return
  }
  try {
    const updated = await updateSession(sessionId, newTitle)
    session.value = updated
    ElMessage.success('标题已更新')
  } catch (err) {
    ElMessage.error(extractErrorMessage(err))
  }
}

function goBack() {
  router.push({ name: 'AppSessions' })
}

onMounted(() => {
  void loadData()
})
</script>

<template>
  <div class="app-session-detail-page">
    <div class="app-session-detail-back">
      <button type="button" class="app-session-detail-back-btn" @click="goBack">← 返回会话列表</button>
    </div>

    <div v-if="pageLoading" class="app-session-detail-loading">正在加载会话详情...</div>

    <div v-else-if="error" class="app-session-detail-error">{{ error }}</div>

    <template v-else-if="session">
      <div class="app-session-detail-header">
        <div class="app-session-detail-title-row">
          <h2 class="app-session-detail-title">{{ session.session_title }}</h2>
          <el-tag
            class="app-session-detail-status-tag"
            :type="session.status === 'ended' ? 'danger' : session.status === 'ongoing' ? 'success' : 'info'"
            size="small"
          >
            {{ statusLabel }}
          </el-tag>
        </div>
        <div class="app-session-detail-meta">
          <span>会话 ID：{{ session.id }}</span>
          <span>创建时间：{{ formatDateTimeToCST(session.created_at) }}</span>
          <span>最后更新：{{ formatDateTimeToCST(session.last_updated) }}</span>
          <span v-if="session.started_at">开始时间：{{ formatDateTimeToCST(session.started_at) }}</span>
          <span v-if="session.ended_at">结束时间：{{ formatDateTimeToCST(session.ended_at) }}</span>
        </div>
        <div class="app-session-detail-actions">
          <button
            v-if="canStart"
            type="button"
            class="app-session-detail-primary-btn"
            @click="handleStart"
          >
            开始会话
          </button>
          <button
            type="button"
            class="app-session-detail-secondary-btn"
            @click="handleEditTitle"
          >
            修改标题
          </button>
          <button
            type="button"
            class="app-session-detail-danger-btn"
            :disabled="!canEnd"
            @click="handleEnd"
          >
            结束会话
          </button>
        </div>
      </div>

      <div class="app-session-detail-transcripts">
        <h3 class="app-session-detail-transcripts-title">转写记录</h3>
        <div v-if="transcriptsLoading" class="app-session-detail-loading">正在加载转写...</div>
        <div v-else-if="!transcripts.length" class="app-session-detail-transcripts-empty">
          暂无转写记录
        </div>
        <ul v-else class="app-session-detail-transcripts-list">
          <li
            v-for="item in transcripts"
            :key="item.transcript_id"
            class="app-session-detail-transcript-item"
          >
            <div class="app-session-detail-transcript-meta">
              <span class="app-session-detail-transcript-speaker">
                {{ item.speaker || '未知说话人' }}
              </span>
              <span class="app-session-detail-transcript-time">
                {{ item.start }} - {{ item.end }}
              </span>
            </div>
            <p class="app-session-detail-transcript-text">{{ item.text }}</p>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.app-session-detail-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 8px 0 32px;
}

.app-session-detail-back {
  margin-bottom: 16px;
}

.app-session-detail-back-btn {
  background: none;
  border: none;
  font-size: 13px;
  color: #2563eb;
  cursor: pointer;
  padding: 0;
}

.app-session-detail-back-btn:hover {
  text-decoration: underline;
}

.app-session-detail-loading {
  padding: 16px 0;
  font-size: 13px;
  color: #6b7280;
}

.app-session-detail-error {
  padding: 16px 18px;
  border-radius: 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 14px;
}

.app-session-detail-header {
  padding: 18px 20px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.04);
  margin-bottom: 20px;
}

.app-session-detail-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.app-session-detail-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.app-session-detail-status-tag {
  flex-shrink: 0;
}

.app-session-detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 14px;
}

.app-session-detail-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.app-session-detail-primary-btn {
  border-radius: 999px;
  border: 1px solid #2563eb;
  padding: 6px 16px;
  font-size: 13px;
  background: #2563eb;
  color: #ffffff;
  cursor: pointer;
}

.app-session-detail-primary-btn:hover {
  background: #1d4ed8;
}

.app-session-detail-secondary-btn {
  border-radius: 999px;
  border: 1px solid #e5e7eb;
  padding: 6px 14px;
  font-size: 13px;
  background: #ffffff;
  color: #374151;
  cursor: pointer;
}

.app-session-detail-secondary-btn:hover {
  background: #f3f4f6;
}

.app-session-detail-danger-btn {
  border-radius: 999px;
  border: 1px solid rgba(248, 113, 113, 0.5);
  padding: 6px 14px;
  font-size: 13px;
  background: #ffffff;
  color: #b91c1c;
  cursor: pointer;
}

.app-session-detail-danger-btn:hover:enabled {
  background: #fef2f2;
  border-color: #ef4444;
}

.app-session-detail-danger-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.app-session-detail-transcripts {
  padding: 18px 20px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.04);
}

.app-session-detail-transcripts-title {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.app-session-detail-transcripts-empty {
  font-size: 13px;
  color: #9ca3af;
  padding: 8px 0;
}

.app-session-detail-transcripts-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.app-session-detail-transcript-item {
  padding: 10px 12px;
  border-radius: 8px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}

.app-session-detail-transcript-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.app-session-detail-transcript-speaker {
  font-weight: 500;
  color: #374151;
}

.app-session-detail-transcript-time {
  font-size: 11px;
}

.app-session-detail-transcript-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #111827;
}
</style>
