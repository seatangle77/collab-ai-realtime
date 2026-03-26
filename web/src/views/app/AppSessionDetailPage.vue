<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Capacitor } from '@capacitor/core'
import type { PluginListenerHandle } from '@capacitor/core'
import { App as CapApp } from '@capacitor/app'
import { useAudioRecorder } from '../../composables/useAudioRecorder'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  type AppChatSession,
  type AppTranscript,
  startSession,
  cancelSession,
  endSession,
  updateSession,
  listGroupSessions,
  listSessionTranscripts,
  endSessionBeacon,
} from '../../api/appSessions'
import { listMyGroups } from '../../api/appGroups'
import { formatDateTimeToCST } from '../../utils/datetime'
import { extractErrorMessage } from '../../utils/error'

interface AppUser {
  id: string
  name: string
  email: string
}

function loadCurrentUser(): AppUser | null {
  const raw = localStorage.getItem('app_user')
  if (!raw) return null
  try { return JSON.parse(raw) as AppUser } catch { return null }
}

const route = useRoute()
const router = useRouter()
const sessionId = route.params.id as string

const currentUser = ref<AppUser | null>(null)
const session = ref<AppChatSession | null>(null)
const transcripts = ref<AppTranscript[]>([])
const pageLoading = ref(true)
const transcriptsLoading = ref(false)
const error = ref('')
/** 里程碑 3/6：WS 状态 + 指数退避重连 */
const wsStatus = ref<'connecting' | 'connected' | 'reconnecting' | 'disconnected'>('disconnected')
const wsErrorMessage = ref('')
const lastPongAt = ref<number | null>(null)
const reconnectAttempt = ref(0)
const pendingRecordingStart = ref(false)
const metaExpanded = ref(false)
const { onChunk, startRecording, stopRecording } = useAudioRecorder()
const transcriptsListEl = ref<HTMLElement | null>(null)

const wsStatusLabel = computed(() => {
  switch (wsStatus.value) {
    case 'connecting':
      return '连接中'
    case 'connected':
      return '已连接'
    case 'reconnecting':
      return reconnectAttempt.value > 0
        ? `连接中断，正在重连（第 ${reconnectAttempt.value} 次）`
        : '连接中断（待恢复）'
    case 'disconnected':
      return '已断开'
    default:
      return ''
  }
})

const BASE_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 30_000
const MAX_RECONNECT_TRIES = 5

let appStateListener: PluginListenerHandle | null = null
let ws: WebSocket | null = null
let pingTimer: ReturnType<typeof setInterval> | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let unmounted = false
/** 为 true 时不自动重连（页面卸载、主动关闭） */
let wsIntentionalClose = false
let chunkSeq = 0

const statusLabel = computed(() => {
  const s = session.value?.status
  if (s === 'ended') return '已结束'
  if (s === 'not_started') return '未开始'
  if (s === 'ongoing') return '进行中'
  return '未知'
})

const launching = ref(false)
const canStart = computed(() => session.value?.status === 'not_started' && !launching.value)
const canCancel = computed(() => session.value?.status === 'not_started')
const canEnd = computed(() => session.value?.status === 'ongoing')

const isHost = computed(() => {
  if (!session.value?.created_by) return true // 老数据兼容
  return currentUser.value?.id === session.value.created_by
})

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

async function handleLaunchSession() {
  if (!canStart.value) return
  launching.value = true

  try {
    // 1. 先检查麦克风权限（失败直接终止，无需回滚后端状态）
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop())
    } catch {
      ElMessage.error('需要麦克风权限才能发起会话')
      return
    }

    // 2. 改会话状态为进行中
    try {
      const updated = await startSession(sessionId)
      session.value = updated
    } catch (err) {
      ElMessage.error(extractErrorMessage(err))
      return
    }

    // 3. 标记待录音，建立 WS（connected 后自动开始录音）
    pendingRecordingStart.value = true
    wsIntentionalClose = false
    openWebSocket()
  } finally {
    launching.value = false
  }
}

async function handleCancel() {
  if (!canCancel.value) return
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
    await cancelSession(sessionId)
    ElMessage.success('会话已取消')
    router.push({ name: 'AppSessions' })
  } catch (err) {
    ElMessage.error(extractErrorMessage(err))
  }
}

async function handleEnd() {
  if (!canEnd.value) return
  try {
    await ElMessageBox.confirm('确认要结束这个会话吗？结束后将标记为已结束，录音同步停止。', '结束会话', {
      type: 'warning',
      confirmButtonText: '结束',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    // 先停止录音、关闭 WS
    stopRecording()
    wsIntentionalClose = true
    ws?.close(1000, 'host_ended')
    // 再通知后端
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

function handleLeave() {
  router.push({ name: 'AppSessions' })
}

function handleBeforeUnload() {
  if (isHost.value && session.value?.status === 'ongoing') {
    endSessionBeacon(sessionId)
  }
}

function handleManualReconnect() {
  reconnectAttempt.value = 0
  wsErrorMessage.value = ''
  wsIntentionalClose = false
  openWebSocket()
}

function buildWsUrl(id: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) || window.location.origin
  const wsBase = base.replace(/^http/i, 'ws').replace(/\/$/, '')
  const token = localStorage.getItem('app_access_token') ?? ''
  return `${wsBase}/ws/sessions/${id}?token=${encodeURIComponent(token)}`
}

function clearPingTimer() {
  if (pingTimer) {
    clearInterval(pingTimer)
    pingTimer = null
  }
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        reject(new Error('读取音频失败'))
        return
      }
      const base64 = result.split(',')[1]
      if (!base64) {
        reject(new Error('音频编码失败'))
        return
      }
      resolve(base64)
    }
    reader.onerror = () => reject(new Error('读取音频失败'))
    reader.readAsDataURL(blob)
  })
}

async function sendAudioChunk(blob: Blob) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  chunkSeq += 1
  const audioB64 = await blobToBase64(blob)
  ws.send(
    JSON.stringify({
      type: 'audio_chunk',
      data: {
        seq: chunkSeq,
        mime_type: blob.type || 'audio/webm',
        audio_b64: audioB64,
        duration_ms: 1000,
        sent_at: Date.now(),
      },
    }),
  )
}

// 注册音频分块回调，每块数据直接发送 WS
onChunk((blob) => {
  void sendAudioChunk(blob).catch((err) => {
    wsErrorMessage.value = extractErrorMessage(err)
  })
})


function startPingTimer() {
  clearPingTimer()
  pingTimer = setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    try {
      ws.send(JSON.stringify({ type: 'ping', data: {} }))
    } catch {
      // Ignore send errors; close handler will refresh status.
    }
  }, 10000)
}

function handleWsMessage(event: MessageEvent<string>) {
  let payload: unknown
  try {
    payload = JSON.parse(event.data)
  } catch {
    wsErrorMessage.value = '收到非法消息格式'
    return
  }
  if (typeof payload !== 'object' || payload === null) {
    wsErrorMessage.value = '消息格式无效'
    return
  }
  const p = payload as { type?: unknown; data?: unknown }
  const msgType = p.type
  const data = p.data
  if (typeof msgType !== 'string' || typeof data !== 'object' || data === null) {
    wsErrorMessage.value = '消息缺少 type 或 data'
    return
  }
  if (msgType === 'connected') {
    reconnectAttempt.value = 0
    clearReconnectTimer()
    wsStatus.value = 'connected'
    wsErrorMessage.value = ''
    void refetchTranscriptsAndMerge()
    if (pendingRecordingStart.value) {
      pendingRecordingStart.value = false
      chunkSeq = 0
      startRecording().catch((err) => {
        ElMessage.error(extractErrorMessage(err))
      })
    }
    return
  }
  if (msgType === 'pong') {
    lastPongAt.value = Date.now()
    return
  }
  if (msgType === 'error') {
    const d = data as { message?: string }
    wsErrorMessage.value = d?.message || 'WebSocket 错误'
    return
  }
  if (msgType === 'audio_chunk_ack') {
    const d = data as { seq?: number }
    if (typeof d.seq === 'number') {
      console.debug('ack chunk:', d.seq)
    }
    return
  }
  if (msgType === 'transcript') {
    const d = data as Partial<AppTranscript> & { transcript_id?: string; text?: string }
    if (!d.transcript_id || typeof d.text !== 'string') return
    if (transcripts.value.some((t) => t.transcript_id === d.transcript_id)) return
    const item: AppTranscript = {
      transcript_id: d.transcript_id,
      group_id: d.group_id ?? '',
      session_id: d.session_id ?? sessionId,
      user_id: d.user_id,
      speaker: d.speaker,
      speaker_name: d.speaker_name,
      text: d.text,
      start: d.start ?? '',
      end: d.end ?? '',
      duration: d.duration,
      confidence: d.confidence,
      created_at:
        typeof d.created_at === 'string'
          ? d.created_at
          : d.created_at != null
            ? String(d.created_at)
            : '',
    }
    transcripts.value = [...transcripts.value, item]
    return
  }
  if (msgType === 'session_ended') {
    const d = data as { session_id?: string; reason?: string }
    if (session.value) {
      session.value = { ...session.value, status: 'ended' }
    }
    stopRecording()
    wsIntentionalClose = true
    ws?.close(1000, 'session_ended')
    void loadTranscripts()
    if (d.reason === 'host_timeout') {
      ElMessage.warning('发起人长时间未响应，会话已自动结束')
    } else {
      ElMessage.info('会话已结束')
    }
    return
  }
}

function speakerInitial(speaker: string | null | undefined): string {
  const s = (speaker || '未').trim()
  return s.slice(0, 1)
}

function scrollTranscriptsToBottom() {
  nextTick(() => {
    const el = transcriptsListEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(
  () => transcripts.value.length,
  () => {
    scrollTranscriptsToBottom()
  },
)

function mergeTranscriptsById(local: AppTranscript[], remote: AppTranscript[]): AppTranscript[] {
  const map = new Map<string, AppTranscript>()
  for (const t of local) {
    if (t.transcript_id) map.set(t.transcript_id, t)
  }
  for (const t of remote) {
    if (t.transcript_id) map.set(t.transcript_id, t)
  }
  return Array.from(map.values()).sort((a, b) => {
    const sa = String(a.start ?? '')
    const sb = String(b.start ?? '')
    return sa.localeCompare(sb)
  })
}

async function refetchTranscriptsAndMerge() {
  try {
    const remote = await listSessionTranscripts(sessionId, { noRedirectOn401: true })
    transcripts.value = mergeTranscriptsById(transcripts.value, remote)
    scrollTranscriptsToBottom()
  } catch (err) {
    wsErrorMessage.value = extractErrorMessage(err)
  }
}

function clearReconnectTimer() {
  if (reconnectTimer != null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function scheduleReconnect() {
  clearReconnectTimer()
  if (unmounted || wsIntentionalClose) return

  reconnectAttempt.value += 1
  if (reconnectAttempt.value > MAX_RECONNECT_TRIES) {
    wsStatus.value = 'disconnected'
    wsErrorMessage.value = '重连失败次数过多，请刷新页面'
    return
  }

  const delay = Math.min(
    MAX_RECONNECT_DELAY_MS,
    BASE_RECONNECT_DELAY_MS * 2 ** (reconnectAttempt.value - 1),
  )
  wsStatus.value = 'reconnecting'

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    if (unmounted || wsIntentionalClose) return
    openWebSocket()
  }, delay)
}

function closeWsForUnmount() {
  wsIntentionalClose = true
  clearReconnectTimer()
  clearPingTimer()
  const current = ws
  ws = null
  if (!current) return
  try {
    current.close(1000, 'client_closed')
  } catch {
    // Ignore close errors.
  }
}

function openWebSocket() {
  if (unmounted || wsIntentionalClose) return
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return
  }

  wsStatus.value = 'connecting'
  if (reconnectAttempt.value === 0) {
    wsErrorMessage.value = ''
  }

  const socket = new WebSocket(buildWsUrl(sessionId))
  ws = socket

  socket.onopen = () => {
    if (unmounted || wsIntentionalClose) return
    startPingTimer()
  }
  socket.onmessage = (event) => {
    if (unmounted) return
    handleWsMessage(event)
  }
  socket.onerror = () => {
    if (unmounted || wsIntentionalClose) return
    wsErrorMessage.value = '连接发生错误'
  }
  socket.onclose = () => {
    clearPingTimer()
    if (socket === ws) {
      ws = null
    }
    if (unmounted || wsIntentionalClose) {
      wsStatus.value = 'disconnected'
      return
    }
    scheduleReconnect()
  }
}

onMounted(async () => {
  unmounted = false
  wsIntentionalClose = false
  reconnectAttempt.value = 0
  currentUser.value = loadCurrentUser()
  await loadData()
  // 仅会话已「进行中」时才自动连接 WS（如刷新页面场景）
  if (session.value?.status === 'ongoing') {
    openWebSocket()
  }
  window.addEventListener('beforeunload', handleBeforeUnload)
  if (Capacitor.isNativePlatform()) {
    appStateListener = await CapApp.addListener('appStateChange', ({ isActive }) => {
      if (!isActive && isHost.value && session.value?.status === 'ongoing') {
        endSessionBeacon(sessionId)
      }
    })
  }
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  appStateListener?.remove()
  appStateListener = null
  unmounted = true
  stopRecording()
  closeWsForUnmount()
  wsStatus.value = 'disconnected'
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
        <button
          type="button"
          class="app-session-detail-meta-toggle"
          @click="metaExpanded = !metaExpanded"
        >
          详细信息 {{ metaExpanded ? '▴' : '▾' }}
        </button>
        <div v-show="metaExpanded" class="app-session-detail-meta">
          <span>会话 ID：{{ session.id }}</span>
          <span>创建时间：{{ formatDateTimeToCST(session.created_at) }}</span>
          <span>最后更新：{{ formatDateTimeToCST(session.last_updated) }}</span>
          <span v-if="session.started_at">开始时间：{{ formatDateTimeToCST(session.started_at) }}</span>
          <span v-if="session.ended_at">结束时间：{{ formatDateTimeToCST(session.ended_at) }}</span>
        </div>
        <div class="app-session-detail-actions">
          <template v-if="isHost">
            <!-- not_started：发起 + 取消 -->
            <template v-if="session.status === 'not_started'">
              <button
                type="button"
                class="app-session-detail-primary-btn app-session-detail-icon-btn"
                :disabled="!canStart"
                @click="handleLaunchSession"
                title="发起会话"
              >
                <span class="app-session-detail-btn-icon" aria-hidden="true">▶</span>
                发起
              </button>
              <button
                type="button"
                class="app-session-detail-danger-btn"
                @click="handleCancel"
                title="取消会话"
              >
                取消会话
              </button>
            </template>
            <!-- ongoing：结束 -->
            <template v-else-if="session.status === 'ongoing'">
              <button
                type="button"
                class="app-session-detail-danger-btn app-session-detail-icon-btn"
                @click="handleEnd"
                title="结束会话"
              >
                <span class="app-session-detail-btn-icon" aria-hidden="true">⏹</span>
                结束
              </button>
            </template>
            <!-- 修改标题（always visible for host when not ended） -->
            <button
              v-if="session.status !== 'ended'"
              type="button"
              class="app-session-detail-secondary-btn"
              @click="handleEditTitle"
            >
              修改标题
            </button>
          </template>
          <button
            v-else
            type="button"
            class="app-session-detail-secondary-btn"
            @click="handleLeave"
          >
            离开会话
          </button>
        </div>
      </div>

      <div class="app-session-detail-transcripts">
        <h3 class="app-session-detail-transcripts-title">
          转写记录
          <span v-if="!isHost" class="app-session-detail-readonly-badge">只读</span>
        </h3>
        <div
          v-if="wsStatus !== 'connected' && session?.status === 'ongoing'"
          class="app-session-detail-ws-banner"
          :class="{
            'is-reconnecting': wsStatus === 'reconnecting',
            'is-disconnected': wsStatus === 'disconnected',
            'is-connecting': wsStatus === 'connecting',
          }"
        >
          <span class="app-session-detail-ws-banner-icon" aria-hidden="true">
            {{ wsStatus === 'disconnected' ? '✕' : '↻' }}
          </span>
          <span class="app-session-detail-ws-banner-text">{{ wsStatusLabel }}</span>
          <button
            v-if="wsStatus === 'disconnected'"
            type="button"
            class="app-session-detail-ws-banner-retry"
            @click="handleManualReconnect"
          >
            重新连接
          </button>
        </div>

        <div v-if="transcriptsLoading" class="app-session-detail-loading">正在加载转写...</div>
        <div v-else-if="!transcripts.length" class="app-session-detail-transcripts-empty">
          暂无转写记录
        </div>
        <div v-else ref="transcriptsListEl" class="app-session-detail-transcripts-scroll">
          <ul class="app-session-detail-transcripts-list">
            <li
              v-for="item in transcripts"
              :key="item.transcript_id"
              class="app-session-detail-transcript-item"
            >
              <div class="app-session-detail-transcript-row">
                <div class="app-session-detail-transcript-avatar" aria-hidden="true">
                  {{ speakerInitial(item.speaker_name || item.speaker) }}
                </div>
                <div class="app-session-detail-transcript-body">
                  <div class="app-session-detail-transcript-meta">
                    <span class="app-session-detail-transcript-speaker">
                      {{ item.speaker_name || item.speaker || '未知说话人' }}
                    </span>
                    <span class="app-session-detail-transcript-time">
                      {{ item.start }} - {{ item.end }}
                      <template v-if="item.created_at"> · {{ item.created_at }}</template>
                    </span>
                  </div>
                  <p class="app-session-detail-transcript-text">{{ item.text }}</p>
                </div>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.app-session-detail-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 8px 0 16px;
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

.app-session-detail-meta-toggle {
  background: none;
  border: none;
  padding: 0 0 10px;
  font-size: 12px;
  color: #6b7280;
  cursor: pointer;
  display: block;
  text-align: left;
}

.app-session-detail-meta-toggle:hover {
  color: #374151;
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

.app-session-detail-primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.app-session-detail-primary-btn:not(:disabled):hover {
  background: #1d4ed8;
}

.app-session-detail-icon-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.app-session-detail-btn-icon {
  font-size: 12px;
  line-height: 1;
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
  display: flex;
  align-items: center;
}

.app-session-detail-readonly-badge {
  font-size: 11px;
  font-weight: 400;
  color: #9ca3af;
  background: #f3f4f6;
  border-radius: 999px;
  padding: 2px 8px;
  margin-left: 8px;
}

.app-session-detail-ws-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 12px;
}

.app-session-detail-ws-banner.is-connecting {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
}

.app-session-detail-ws-banner.is-reconnecting {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}

.app-session-detail-ws-banner.is-disconnected {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.app-session-detail-ws-banner-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.app-session-detail-ws-banner-text {
  flex: 1;
}

.app-session-detail-ws-banner-retry {
  background: none;
  border: 1px solid currentColor;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  color: inherit;
  cursor: pointer;
  flex-shrink: 0;
}

.app-session-detail-ws-banner-retry:hover {
  opacity: 0.75;
}

.app-session-detail-recorder-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.app-session-detail-recorder-meta {
  font-size: 12px;
  color: #4b5563;
}

.app-session-detail-transcripts-empty {
  font-size: 13px;
  color: #9ca3af;
  padding: 8px 0;
}

.app-session-detail-transcripts-scroll {
  max-height: calc(100vh - 360px);
  min-height: 200px;
  overflow-y: auto;
  padding-right: 4px;
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

.app-session-detail-transcript-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.app-session-detail-transcript-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: #e0e7ff;
  color: #3730a3;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.app-session-detail-transcript-body {
  min-width: 0;
  flex: 1;
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
