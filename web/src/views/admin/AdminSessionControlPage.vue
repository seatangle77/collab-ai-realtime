<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import type { AdminChatSession, AdminTranscript } from '../../types/admin'
import {
  getAdminChatSession,
  startAdminChatSession,
  endAdminChatSession,
} from '../../api/admin/chat-sessions'
import { listAdminTranscripts } from '../../api/admin/adminTranscripts'
import { useAudioRecorder } from '../../composables/useAudioRecorder'
import { formatDateTimeToCST, formatTimeToCST } from '../../utils/datetime'

const route = useRoute()
const router = useRouter()
const sessionId = route.params.id as string

// ─── 会话状态 ──────────────────────────────────────────────────────
const session = ref<AdminChatSession | null>(null)
const pageLoading = ref(true)
const pageError = ref('')
const actionLoading = ref(false)

const statusLabel = computed(() => {
  const s = session.value?.status
  if (s === 'ended') return '已结束'
  if (s === 'not_started') return '未开始'
  if (s === 'ongoing') return '进行中'
  return '未知'
})

const statusType = computed(() => {
  const s = session.value?.status
  if (s === 'ongoing') return 'success'
  if (s === 'not_started') return 'warning'
  return 'info'
})

const canStart = computed(() => session.value?.status === 'not_started' && !actionLoading.value)
const canEnd = computed(() => session.value?.status === 'ongoing' && !actionLoading.value)

// ─── 转录 ──────────────────────────────────────────────────────────
interface LiveSegment {
  segment_key: string
  text: string
  speaker?: string
  status: 'live' | 'pending_final'
}

const transcripts = ref<AdminTranscript[]>([])
const liveSegments = ref<Record<string, LiveSegment>>({})
const transcriptListEl = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (transcriptListEl.value) {
      transcriptListEl.value.scrollTop = transcriptListEl.value.scrollHeight
    }
  })
}

async function loadTranscripts() {
  try {
    const page = await listAdminTranscripts({ session_id: sessionId, page_size: 200 })
    transcripts.value = page.items
    scrollToBottom()
  } catch {
    // 静默失败，WS 会持续补充
  }
}

// ─── WebSocket ─────────────────────────────────────────────────────
type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
const wsStatus = ref<WsStatus>('disconnected')
let ws: WebSocket | null = null
let pingTimer: ReturnType<typeof setInterval> | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempt = 0
let unmounted = false
let wsIntentionalClose = false
let chunkSeq = 0
const pendingRecordingStart = ref(false)

function buildWsUrl(id: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) || window.location.origin
  const wsBase = base.replace(/^http/i, 'ws').replace(/\/$/, '')
  // 管理员不传 user JWT token
  return `${wsBase}/ws/sessions/${id}`
}

function clearPingTimer() {
  if (pingTimer) { clearInterval(pingTimer); pingTimer = null }
}

function clearReconnectTimer() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
}

function startPingTimer() {
  clearPingTimer()
  pingTimer = setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify({ type: 'ping', data: {} })) } catch { /* ignore */ }
    }
  }, 10000)
}

function sendPingNow() {
  if (ws?.readyState === WebSocket.OPEN) {
    try { ws.send(JSON.stringify({ type: 'ping', data: {} })) } catch { /* ignore */ }
  }
}

function scheduleReconnect() {
  clearReconnectTimer()
  const delay = Math.min(1000 * 2 ** reconnectAttempt, 30000)
  reconnectAttempt++
  wsStatus.value = 'reconnecting'
  reconnectTimer = setTimeout(() => {
    if (!unmounted && !wsIntentionalClose) openWebSocket()
  }, delay)
}

function handleWsMessage(event: MessageEvent<string>) {
  let payload: unknown
  try { payload = JSON.parse(event.data) } catch { return }
  if (typeof payload !== 'object' || payload === null) return
  const p = payload as { type?: unknown; data?: unknown }
  const msgType = p.type
  const data = p.data
  if (typeof msgType !== 'string') return

  if (msgType === 'connected') {
    reconnectAttempt = 0
    clearReconnectTimer()
    wsStatus.value = 'connected'
    sendPingNow()
    // WS 连上后重新拉全量转录，并准备录音
    void loadTranscripts()
    if (pendingRecordingStart.value) {
      pendingRecordingStart.value = false
      chunkSeq = 0
      startRecording().catch((err) => ElMessage.error(String(err)))
    }
    return
  }

  if (msgType === 'pong') return

  if (msgType === 'audio_chunk_ack') return

  if (msgType === 'transcript') {
    const d = data as Partial<AdminTranscript> & { transcript_id?: string; text?: string; segment_key?: string }
    if (!d.transcript_id || typeof d.text !== 'string') return
    if (transcripts.value.some((t) => t.transcript_id === d.transcript_id)) return
    const item: AdminTranscript = {
      transcript_id: d.transcript_id,
      group_id: d.group_id ?? '',
      session_id: sessionId,
      user_id: d.user_id ?? null,
      speaker: d.speaker ?? null,
      speaker_name: d.speaker_name ?? null,
      text: d.text,
      start: d.start ?? '',
      end: d.end ?? '',
      duration: d.duration ?? null,
      confidence: d.confidence ?? null,
      is_edited: false,
      created_at: typeof d.created_at === 'string' ? d.created_at : '',
      audio_url: null,
      original_text: null,
    }
    transcripts.value = [...transcripts.value, item]
    // 清除对应 live segment
    const next = { ...liveSegments.value }
    if (typeof d.segment_key === 'string' && d.segment_key) {
      delete next[d.segment_key]
    }
    liveSegments.value = next
    scrollToBottom()
    return
  }

  if (msgType === 'transcript_segment') {
    const d = data as { segment_key?: string; text?: string; speaker?: string; is_final?: boolean }
    if (!d.segment_key) return
    if (d.is_final) {
      const existing = liveSegments.value[d.segment_key]
      const finalText = typeof d.text === 'string' && d.text.trim() ? d.text : existing?.text
      if (!finalText?.trim()) return
      liveSegments.value = {
        ...liveSegments.value,
        [d.segment_key]: { segment_key: d.segment_key, text: finalText, speaker: d.speaker ?? existing?.speaker, status: 'pending_final' },
      }
      return
    }
    if (typeof d.text !== 'string' || !d.text.trim()) return
    liveSegments.value = {
      ...liveSegments.value,
      [d.segment_key]: { segment_key: d.segment_key, text: d.text, speaker: d.speaker, status: 'live' },
    }
    scrollToBottom()
    return
  }

  if (msgType === 'session_ended') {
    if (session.value) session.value = { ...session.value, status: 'ended' }
    void stopRecording()
    wsIntentionalClose = true
    ws?.close(1000, 'session_ended')
    liveSegments.value = {}
    void loadTranscripts()
    ElMessage.info('会话已结束')
    return
  }

  // push_notification / group_notification / summary_update / info_gap_button — 管理员忽略
}

function openWebSocket() {
  if (unmounted || wsIntentionalClose) return
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  wsStatus.value = 'connecting'
  const socket = new WebSocket(buildWsUrl(sessionId))
  ws = socket
  socket.onopen = () => {
    if (unmounted || wsIntentionalClose) return
    startPingTimer()
    sendPingNow()
  }
  socket.onmessage = (event) => {
    if (unmounted) return
    handleWsMessage(event)
  }
  socket.onerror = () => { /* close 会跟着来 */ }
  socket.onclose = () => {
    clearPingTimer()
    if (socket === ws) ws = null
    if (unmounted || wsIntentionalClose) {
      wsStatus.value = 'disconnected'
      return
    }
    scheduleReconnect()
  }
}

function closeWebSocket(reason = 'admin_left') {
  wsIntentionalClose = true
  clearPingTimer()
  clearReconnectTimer()
  ws?.close(1000, reason)
  ws = null
  wsStatus.value = 'disconnected'
}

// ─── 录音 ──────────────────────────────────────────────────────────
const { isRecording, onChunk, startRecording, stopRecording } = useAudioRecorder()

const canStartRecording = computed(
  () => session.value?.status === 'ongoing' && wsStatus.value === 'connected' && !isRecording.value,
)
const canStopRecording = computed(
  () => session.value?.status === 'ongoing' && isRecording.value,
)

async function sendAudioChunk(blob: Blob, mimeType = blob.type || 'audio/webm') {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  try {
    const buffer = await blob.arrayBuffer()
    const bytes = new Uint8Array(buffer)
    let binary = ''
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]!)
    const audio_b64 = btoa(binary)
    ws.send(JSON.stringify({ type: 'audio_chunk', data: { seq: chunkSeq++, audio_b64, mime_type: mimeType } }))
  } catch { /* ignore */ }
}

onChunk((blob, mimeType) => {
  void sendAudioChunk(blob, mimeType).catch(() => {})
})

async function handleStartRecording() {
  if (!canStartRecording.value) return
  chunkSeq = 0
  try {
    await startRecording()
  } catch (err) {
    ElMessage.error('录音启动失败：' + String(err))
  }
}

async function handleStopRecording() {
  if (!canStopRecording.value) return
  try {
    await stopRecording()
  } catch { /* ignore */ }
}

// ─── 会话控制 ──────────────────────────────────────────────────────
async function handleStart() {
  if (!canStart.value) return
  try {
    await ElMessageBox.confirm('确认发起这个会话吗？发起后用户可以进入并开始讨论。', '发起会话', {
      confirmButtonText: '发起',
      cancelButtonText: '取消',
      type: 'info',
    })
  } catch { return }

  actionLoading.value = true
  try {
    // 先检查麦克风权限
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop())
    } catch {
      ElMessage.error('需要麦克风权限才能发起会话')
      return
    }

    const updated = await startAdminChatSession(sessionId)
    session.value = updated
    ElMessage.success('会话已发起')

    // 连接 WS，WS connected 后自动开始录音
    pendingRecordingStart.value = true
    wsIntentionalClose = false
    openWebSocket()
  } catch (err) {
    ElMessage.error((err as any)?.message ?? '发起失败')
  } finally {
    actionLoading.value = false
  }
}

async function handleEnd() {
  if (!canEnd.value) return
  try {
    await ElMessageBox.confirm('确认结束这个会话吗？结束后将通知所有已连接的用户。', '结束会话', {
      confirmButtonText: '结束',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch { return }

  actionLoading.value = true
  try {
    await stopRecording()
    const updated = await endAdminChatSession(sessionId)
    session.value = updated
    closeWebSocket('admin_ended')
    liveSegments.value = {}
    ElMessage.success('会话已结束')
    await loadTranscripts()
  } catch (err) {
    ElMessage.error((err as any)?.message ?? '结束失败')
  } finally {
    actionLoading.value = false
  }
}

// ─── 工具函数 ──────────────────────────────────────────────────────
function speakerLabel(t: AdminTranscript): string {
  return t.speaker_name ?? t.speaker ?? t.user_id ?? '未知'
}

function speakerInitial(t: AdminTranscript): string {
  const s = speakerLabel(t)
  const asciiOnly = /^[A-Za-z0-9]+$/.test(s)
  return asciiOnly ? s.slice(0, 2).toUpperCase() : s.slice(0, 1)
}

const AVATAR_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16',
]

function avatarColor(key: string): string {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length] ?? AVATAR_COLORS[0] ?? '#3b82f6'
}

function transcriptTimeLabel(t: AdminTranscript): string {
  if (t.created_at) {
    const label = formatTimeToCST(t.created_at)
    if (label) return label
  }
  return t.start ? String(t.start) : ''
}

// ─── 生命周期 ──────────────────────────────────────────────────────
onMounted(async () => {
  unmounted = false
  wsIntentionalClose = false
  try {
    session.value = await getAdminChatSession(sessionId)
  } catch {
    pageError.value = '会话不存在或加载失败'
    pageLoading.value = false
    return
  }
  await loadTranscripts()
  pageLoading.value = false

  // 已进行中时自动连 WS
  if (session.value?.status === 'ongoing') {
    openWebSocket()
  }
})

onUnmounted(() => {
  unmounted = true
  closeWebSocket('admin_left')
  if (isRecording.value) void stopRecording()
})
</script>

<template>
  <div class="asc-page">
    <!-- 顶部导航 -->
    <div class="asc-header">
      <el-button :icon="ArrowLeft" text @click="router.back()">返回</el-button>
      <div v-if="session" class="asc-header-info">
        <span class="asc-session-title">{{ session.session_title }}</span>
        <span class="asc-group-name">{{ session.group_name ?? session.group_id }}</span>
        <el-tag :type="statusType" size="small">{{ statusLabel }}</el-tag>
      </div>
    </div>

    <!-- 加载 / 错误 -->
    <div v-if="pageLoading" class="asc-loading">加载中...</div>
    <div v-else-if="pageError" class="asc-error">{{ pageError }}</div>

    <template v-else-if="session">
      <!-- 控制栏 -->
      <div class="asc-controls">
        <!-- 发起 -->
        <el-button
          v-if="canStart || session.status === 'not_started'"
          type="primary"
          :disabled="!canStart"
          :loading="actionLoading"
          @click="handleStart"
        >
          发起会话
        </el-button>

        <!-- 录音控制（进行中时显示） -->
        <template v-if="session.status === 'ongoing'">
          <div class="asc-ws-status">
            <span class="asc-ws-dot" :class="`asc-ws-dot--${wsStatus}`" />
            <span class="asc-ws-label">
              {{ wsStatus === 'connected' ? 'WS 已连接' : wsStatus === 'connecting' ? '连接中...' : wsStatus === 'reconnecting' ? '重连中...' : '未连接' }}
            </span>
          </div>

          <el-button
            v-if="!isRecording"
            type="success"
            :disabled="!canStartRecording"
            @click="handleStartRecording"
          >
            开始录音
          </el-button>
          <el-button
            v-else
            type="danger"
            plain
            :disabled="!canStopRecording"
            @click="handleStopRecording"
          >
            停止录音
          </el-button>

          <el-tag v-if="isRecording" type="danger" effect="dark" class="asc-recording-badge">
            ● 录音中
          </el-tag>
        </template>

        <!-- 结束 -->
        <el-button
          v-if="session.status === 'ongoing'"
          type="danger"
          plain
          :disabled="!canEnd"
          :loading="actionLoading"
          style="margin-left: auto"
          @click="handleEnd"
        >
          结束会话
        </el-button>
      </div>

      <!-- 会话信息 -->
      <div class="asc-meta">
        <span v-if="session.started_at">开始：{{ formatDateTimeToCST(session.started_at) }}</span>
        <span v-if="session.ended_at">结束：{{ formatDateTimeToCST(session.ended_at) }}</span>
        <span>创建：{{ formatDateTimeToCST(session.created_at) }}</span>
      </div>

      <!-- 转录区域 -->
      <div class="asc-transcript-panel">
        <div class="asc-transcript-header">
          <span class="asc-transcript-title">讨论记录</span>
          <span class="asc-transcript-count">{{ transcripts.length }} 条</span>
        </div>

        <div ref="transcriptListEl" class="asc-transcript-list">
          <!-- 空状态 -->
          <div
            v-if="transcripts.length === 0 && Object.keys(liveSegments).length === 0"
            class="asc-transcript-empty"
          >
            {{ session.status === 'ongoing' ? '等待讨论开始...' : '暂无讨论记录' }}
          </div>

          <!-- 已完成的转录 -->
          <div
            v-for="t in transcripts"
            :key="t.transcript_id"
            class="asc-transcript-item"
          >
            <div
              class="asc-avatar"
              :style="{ background: avatarColor(t.speaker ?? t.user_id ?? 'unknown') }"
            >
              {{ speakerInitial(t) }}
            </div>
            <div class="asc-transcript-body">
              <div class="asc-transcript-meta">
                <span class="asc-speaker-name">{{ speakerLabel(t) }}</span>
                <span class="asc-transcript-time">{{ transcriptTimeLabel(t) }}</span>
              </div>
              <div class="asc-transcript-text">{{ t.text }}</div>
            </div>
          </div>

          <!-- 实时片段 -->
          <div
            v-for="seg in Object.values(liveSegments)"
            :key="seg.segment_key"
            class="asc-transcript-item asc-transcript-item--live"
          >
            <div
              class="asc-avatar"
              :style="{ background: avatarColor(seg.speaker ?? 'live') }"
            >
              {{ seg.speaker ? seg.speaker.slice(0, 1) : '?' }}
            </div>
            <div class="asc-transcript-body">
              <div class="asc-transcript-meta">
                <span class="asc-speaker-name">{{ seg.speaker ?? '说话中...' }}</span>
                <span class="asc-live-badge">实时</span>
              </div>
              <div class="asc-transcript-text asc-transcript-text--live">{{ seg.text }}</div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.asc-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 16px 20px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.asc-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.asc-header-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.asc-session-title {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
}

.asc-group-name {
  font-size: 14px;
  color: #6b7280;
}

.asc-loading,
.asc-error {
  padding: 40px;
  text-align: center;
  color: #6b7280;
}

.asc-error {
  color: #ef4444;
}

.asc-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 14px 16px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
}

.asc-ws-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.asc-ws-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.asc-ws-dot--connected { background: #10b981; }
.asc-ws-dot--connecting,
.asc-ws-dot--reconnecting { background: #f59e0b; }
.asc-ws-dot--disconnected { background: #d1d5db; }

.asc-ws-label {
  font-size: 13px;
  color: #6b7280;
}

.asc-recording-badge {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.asc-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #9ca3af;
  flex-wrap: wrap;
}

.asc-transcript-panel {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.asc-transcript-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.asc-transcript-title {
  font-weight: 600;
  font-size: 14px;
  color: #374151;
}

.asc-transcript-count {
  font-size: 13px;
  color: #9ca3af;
}

.asc-transcript-list {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  max-height: 60vh;
}

.asc-transcript-empty {
  text-align: center;
  padding: 40px 0;
  color: #9ca3af;
  font-size: 14px;
}

.asc-transcript-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.asc-transcript-item--live {
  opacity: 0.75;
}

.asc-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
  margin-top: 2px;
}

.asc-transcript-body {
  flex: 1;
  min-width: 0;
}

.asc-transcript-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.asc-speaker-name {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.asc-transcript-time {
  font-size: 12px;
  color: #9ca3af;
}

.asc-live-badge {
  font-size: 11px;
  padding: 1px 6px;
  background: #fef3c7;
  color: #92400e;
  border-radius: 4px;
  border: 1px solid #fde68a;
}

.asc-transcript-text {
  font-size: 15px;
  color: #1f2937;
  line-height: 1.55;
  word-break: break-word;
}

.asc-transcript-text--live {
  color: #6b7280;
  font-style: italic;
}
</style>
