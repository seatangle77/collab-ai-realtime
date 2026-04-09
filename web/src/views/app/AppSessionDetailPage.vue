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
import PushNotification from '../../components/PushNotification.vue'
import InfoGapButtons, { type InfoGapButton } from '../../components/InfoGapButtons.vue'
import { appHttp } from '../../api/appHttp'

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

interface DiscussionSummaryItem {
  id: string
  session_id: string
  version: number
  content: string
  analysis_run_id: string
  window_start: string
  window_end: string
  created_at: string
}

interface PushLogItem {
  id: string
  session_id: string
  state_id?: string | null
  analysis_run_id?: string | null
  analysis_window_start?: string | null
  push_content?: string | null
  push_channel: string
  jpush_message_id?: string | null
  delivery_status: string
  triggered_at: string
  delivered_at?: string | null
}

interface AnalysisClockItem {
  key: string
  label: string
  secondsLeft: number
}

interface AnalysisRunCard {
  id: string
  kind: 'summary_run' | 'reasoning_run'
  title: string
  scheduledAt: string
  producedAt?: string
  windowStart: string
  windowEnd: string
  summaryContent?: string
  summaryVersion?: number
  pushes: string[]
  keywords: string[]
}

// ── 推送通知 ──────────────────────────────────────────────────────────────────
const pushContent = ref('')
const pushVisible = ref(false)
const recentPushes = ref<Array<{ content: string; at: number }>>([])

function showPushNotification(content: string, triggeredAt?: string | null) {
  pushContent.value = content
  const fallbackTs = Date.now()
  const parsed = triggeredAt ? new Date(triggeredAt).getTime() : NaN
  recentPushes.value = [{ content, at: Number.isNaN(parsed) ? fallbackTs : parsed }, ...recentPushes.value].slice(0, 5)
  pushVisible.value = false
  // 强制触发 watch（即使上一条还没消失也能重新触发）
  requestAnimationFrame(() => { pushVisible.value = true })
}

function pushTimeLabel(ts: number): string {
  return new Date(ts).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

// ── AI 分析时钟 ───────────────────────────────────────────────────────────────
const SILENCE_INTERVAL_S = 30
const SUMMARY_FIRST_OFFSET_S = 105
const REASONING_INTERVAL_S = 120
const clockNowMs = ref(Date.now())
let analysisClockTimer: ReturnType<typeof setInterval> | null = null

function startAnalysisClock() {
  stopAnalysisClock()
  clockNowMs.value = Date.now()
  analysisClockTimer = setInterval(() => {
    clockNowMs.value = Date.now()
  }, 1000)
}

function stopAnalysisClock() {
  if (analysisClockTimer !== null) {
    clearInterval(analysisClockTimer)
    analysisClockTimer = null
  }
}

function parseMs(value: string | undefined | null): number | null {
  if (!value) return null
  const ts = new Date(value).getTime()
  return Number.isNaN(ts) ? null : ts
}

function secondsUntilNextAligned(sessionStartMs: number | null, firstOffsetS: number, intervalS: number): number {
  if (sessionStartMs == null) return intervalS
  const nowMs = clockNowMs.value
  const firstAt = sessionStartMs + firstOffsetS * 1000
  if (nowMs <= firstAt) {
    return Math.max(0, Math.ceil((firstAt - nowMs) / 1000))
  }
  const elapsed = nowMs - firstAt
  const remainder = elapsed % (intervalS * 1000)
  const leftMs = remainder === 0 ? 0 : intervalS * 1000 - remainder
  return Math.max(0, Math.ceil(leftMs / 1000))
}

const analysisClocks = computed<AnalysisClockItem[]>(() => {
  const sessionStartMs = parseMs(session.value?.started_at ?? null)
  return [
    {
      key: 'silence',
      label: '群组沉默分析',
      secondsLeft: secondsUntilNextAligned(sessionStartMs, SILENCE_INTERVAL_S, SILENCE_INTERVAL_S),
    },
    {
      key: 'summary',
      label: '摘要分析',
      secondsLeft: secondsUntilNextAligned(sessionStartMs, SUMMARY_FIRST_OFFSET_S, REASONING_INTERVAL_S),
    },
    {
      key: 'reasoning',
      label: '推理提示分析',
      secondsLeft: secondsUntilNextAligned(sessionStartMs, REASONING_INTERVAL_S, REASONING_INTERVAL_S),
    },
  ]
})

// ── 讨论摘要 ──────────────────────────────────────────────────────────────────
const currentSummary = ref('')
const summaryVersion = ref(0)
const summaryHistory = ref<DiscussionSummaryItem[]>([])
const pushLogs = ref<PushLogItem[]>([])
const agentTimelineRuns = ref<AnalysisRunCard[]>([])

async function fetchLatestSummary() {
  try {
    const data = await appHttp.get<{ content: string; version: number }>(
      `/api/sessions/${sessionId}/summary`,
    )
    if (data.content) {
      currentSummary.value = data.content
      summaryVersion.value = data.version
    }
  } catch {
    // 404 或暂无摘要时静默处理
  }
}

async function fetchSummaryHistory() {
  try {
    const data = await appHttp.get<DiscussionSummaryItem[]>(
      `/api/sessions/${sessionId}/summaries`,
    )
    summaryHistory.value = data
    rebuildAgentTimeline()
  } catch {
    summaryHistory.value = []
    rebuildAgentTimeline()
  }
}

async function fetchPushLogs() {
  try {
    const data = await appHttp.get<PushLogItem[]>(
      `/api/sessions/${sessionId}/push-logs`,
    )
    pushLogs.value = data
    recentPushes.value = data
      .filter((item) => item.push_content)
      .map((item) => ({
        content: item.push_content ?? '',
        at: new Date(item.triggered_at).getTime(),
      }))
      .filter((item) => !Number.isNaN(item.at))
      .slice(0, 5)
    rebuildAgentTimeline()
  } catch {
    pushLogs.value = []
    rebuildAgentTimeline()
  }
}

// ── 信息缺口按钮 ──────────────────────────────────────────────────────────────
const infoGapButtons = ref<InfoGapButton[]>([])

async function fetchInfoGapButtons() {
  try {
    const data = await appHttp.get<InfoGapButton[]>(
      `/api/sessions/${sessionId}/info-gap/buttons`,
    )
    infoGapButtons.value = data
    rebuildAgentTimeline()
  } catch {
    // 静默失败，不影响主流程
  }
}

function handleInfoGapButtonClicked(buttonId: string) {
  infoGapButtons.value = infoGapButtons.value.filter((b) => b.id !== buttonId)
  rebuildAgentTimeline()
}

function timelineSortValue(value: string | undefined): number {
  if (!value) return 0
  const t = new Date(value).getTime()
  return Number.isNaN(t) ? 0 : t
}

function timelineTimeLabel(value: string | undefined): string {
  return formatDateTimeToCST(value ?? null)
}

const timelineLegend = '计划开始 = 这一轮按时钟应触发的时间；覆盖窗口 = 这一轮实际分析的讨论区间；实际产出 = 摘要或建议真正写出/发出的时间。'

function timelineWindowLabel(windowStart: string | undefined, windowEnd: string | undefined): string {
  if (!windowStart || !windowEnd) return '-'
  return `${formatDateTimeToCST(windowStart)} - ${formatDateTimeToCST(windowEnd)}`
}

function upsertSummaryEvent(summary: DiscussionSummaryItem) {
  const idx = summaryHistory.value.findIndex((item) => item.id === summary.id)
  if (idx >= 0) {
    summaryHistory.value[idx] = summary
  } else {
    summaryHistory.value = [summary, ...summaryHistory.value]
  }
  rebuildAgentTimeline()
}

function upsertPushEvent(push: PushLogItem) {
  const idx = pushLogs.value.findIndex((item) => item.id === push.id)
  if (idx >= 0) {
    pushLogs.value[idx] = push
  } else {
    pushLogs.value = [push, ...pushLogs.value]
  }
  rebuildAgentTimeline()
}

function buildSummaryRunId(windowStart: string): string {
  return `summary:${sessionId}:${windowStart}`
}

function buildReasoningRunId(windowStart: string): string {
  return `reasoning:${sessionId}:${windowStart}`
}

function addSecondsToIso(value: string, seconds: number): string {
  const baseMs = parseMs(value)
  if (baseMs == null) return value
  return new Date(baseMs + seconds * 1000).toISOString()
}

function rebuildAgentTimeline() {
  const runs: AnalysisRunCard[] = []

  for (const summary of summaryHistory.value) {
    runs.push({
      id: summary.analysis_run_id || buildSummaryRunId(summary.window_start),
      kind: 'summary_run',
      title: '摘要分析',
      scheduledAt: summary.window_end,
      producedAt: summary.created_at,
      windowStart: summary.window_start,
      windowEnd: summary.window_end,
      summaryContent: summary.content,
      summaryVersion: summary.version,
      pushes: [],
      keywords: [],
    })
  }

  const reasoningRunMap = new Map<string, AnalysisRunCard>()
  for (const push of pushLogs.value) {
    const windowStart = push.analysis_window_start
    if (!windowStart) continue
    const runId = push.analysis_run_id || buildReasoningRunId(windowStart)
    const run = reasoningRunMap.get(runId) ?? {
      id: runId,
      kind: 'reasoning_run',
      title: '推理提示分析',
      scheduledAt: addSecondsToIso(windowStart, REASONING_INTERVAL_S),
      producedAt: push.triggered_at,
      windowStart,
      windowEnd: addSecondsToIso(windowStart, REASONING_INTERVAL_S),
      pushes: [],
      keywords: [],
    }
    if (push.push_content) run.pushes.push(push.push_content)
    if (!run.producedAt || timelineSortValue(push.triggered_at) > timelineSortValue(run.producedAt)) {
      run.producedAt = push.triggered_at
    }
    reasoningRunMap.set(runId, run)
  }

  for (const button of infoGapButtons.value) {
    const windowStart = button.window_start
    if (!windowStart || !button.created_at) continue
    const runId = button.analysis_run_id || buildReasoningRunId(windowStart)
    const run = reasoningRunMap.get(runId) ?? {
      id: runId,
      kind: 'reasoning_run',
      title: '推理提示分析',
      scheduledAt: addSecondsToIso(windowStart, REASONING_INTERVAL_S),
      producedAt: button.created_at,
      windowStart,
      windowEnd: addSecondsToIso(windowStart, REASONING_INTERVAL_S),
      pushes: [],
      keywords: [],
    }
    if (!run.keywords.includes(button.keyword)) {
      run.keywords.push(button.keyword)
    }
    if (!run.producedAt || timelineSortValue(button.created_at) > timelineSortValue(run.producedAt)) {
      run.producedAt = button.created_at
    }
    reasoningRunMap.set(runId, run)
  }

  runs.push(...Array.from(reasoningRunMap.values()))
  agentTimelineRuns.value = runs.sort((a, b) => timelineSortValue(b.scheduledAt) - timelineSortValue(a.scheduledAt))
}

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
      rebuildAgentTimeline()
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
    // Native(Android)：使用 VoiceRecorder 权限 API，避免 getUserMedia 占住麦克风导致 MICROPHONE_BEING_USED
    // Browser：使用 getUserMedia 检查权限
    if (Capacitor.isNativePlatform()) {
      try {
        const { VoiceRecorder } = await import('capacitor-voice-recorder')
        const perm = await VoiceRecorder.hasAudioRecordingPermission()
        if (!perm.value) {
          const req = await VoiceRecorder.requestAudioRecordingPermission()
          if (!req.value) throw new Error('denied')
        }
      } catch {
        ElMessage.error('需要麦克风权限才能发起会话')
        return
      }
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        stream.getTracks().forEach((t) => t.stop())
      } catch {
        ElMessage.error('需要麦克风权限才能发起会话')
        return
      }
    }

    // 2. 改会话状态为进行中
    try {
      const updated = await startSession(sessionId)
      session.value = updated
      rebuildAgentTimeline()
    } catch (err) {
      ElMessage.error(extractErrorMessage(err))
      return
    }

    // 3. 标记待录音，建立 WS（connected 后自动开始录音）
    pendingRecordingStart.value = true
    wsIntentionalClose = false
    openWebSocket()
    startAnalysisClock()
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
    stopAnalysisClock()
    wsIntentionalClose = true
    ws?.close(1000, 'host_ended')
    // 再通知后端
    const updated = await endSession(sessionId)
    session.value = updated
    rebuildAgentTimeline()
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
    rebuildAgentTimeline()
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
    const d = data as Partial<AppTranscript> & {
      transcript_id?: string
      text?: string
      segment_key?: string
    }
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
    const next = { ...liveSegments.value }
    if (typeof d.segment_key === 'string' && d.segment_key) {
      delete next[d.segment_key]
    } else {
      // 兼容旧后端：缺少 segment_key 时仍按文本兜底清理
      for (const [k, v] of Object.entries(next)) {
        if (v.text.trim() === item.text.trim()) delete next[k]
      }
    }
    liveSegments.value = next
    scrollTranscriptsToBottom()
    return
  }
  if (msgType === 'transcript_segment') {
    const d = data as { segment_key?: string; text?: string; speaker?: string; is_final?: boolean }
    if (!d.segment_key) return
    if (d.is_final) {
      const existing = liveSegments.value[d.segment_key]
      const finalText = typeof d.text === 'string' && d.text.trim() ? d.text : existing?.text
      if (!finalText || !finalText.trim()) return
      liveSegments.value = {
        ...liveSegments.value,
        [d.segment_key]: {
          segment_key: d.segment_key,
          text: finalText,
          speaker: d.speaker ?? existing?.speaker,
          status: 'pending_final',
        },
      }
      return
    }
    if (typeof d.text !== 'string' || !d.text.trim()) return
    liveSegments.value = {
      ...liveSegments.value,
      [d.segment_key]: {
        segment_key: d.segment_key,
        text: d.text,
        speaker: d.speaker,
        status: 'live',
      },
    }
    scrollTranscriptsToBottom()
    return
  }
  if (msgType === 'session_ended') {
    const d = data as { session_id?: string; reason?: string }
    if (session.value) {
      session.value = { ...session.value, status: 'ended' }
    }
    stopRecording()
    stopAnalysisClock()
    wsIntentionalClose = true
    ws?.close(1000, 'session_ended')
    void loadTranscripts()
    if (d.reason === 'host_timeout') {
      ElMessage.warning('发起人长时间未响应，会话已自动结束')
    } else if (d.reason === 'host_ended') {
      ElMessage.info('发起人已结束会话')
    } else {
      ElMessage.info('会话已结束')
    }
    return
  }
  if (msgType === 'summary_update') {
    const d = data as {
      id?: string | null
      content?: string
      version?: number
      analysis_run_id?: string | null
      window_start?: string | null
      window_end?: string | null
      created_at?: string | null
    }
    if (typeof d.content === 'string' && d.content) {
      currentSummary.value = d.content
      summaryVersion.value = d.version ?? summaryVersion.value
      if (d.id && d.created_at && d.window_start && d.window_end && typeof d.version === 'number') {
        upsertSummaryEvent({
          id: d.id,
          session_id: sessionId,
          version: d.version,
          content: d.content,
          analysis_run_id: d.analysis_run_id ?? buildSummaryRunId(d.window_start),
          window_start: d.window_start,
          window_end: d.window_end,
          created_at: d.created_at,
        })
      }
    }
    return
  }
  if (msgType === 'push_notification') {
    const d = data as {
      content?: string
      target_user_id?: string
      triggered_at?: string | null
      analysis_run_id?: string | null
      analysis_window_start?: string | null
    }
    if (d.content) {
      showPushNotification(d.content, d.triggered_at)
      upsertPushEvent({
        id: `live-push-${d.triggered_at ?? Date.now()}-${d.content}`,
        session_id: sessionId,
        state_id: null,
        analysis_run_id: d.analysis_run_id ?? null,
        analysis_window_start: d.analysis_window_start ?? null,
        push_content: d.content,
        push_channel: 'web',
        jpush_message_id: null,
        delivery_status: 'delivered',
        triggered_at: d.triggered_at ?? new Date().toISOString(),
        delivered_at: null,
      })
    }
    return
  }
  if (msgType === 'info_gap_button') {
    const d = data as { buttons?: InfoGapButton[] }
    if (Array.isArray(d.buttons)) {
      // 合并去重（保留已点击的不再添加）
      const existingIds = new Set(infoGapButtons.value.map((b) => b.id))
      const newBtns = d.buttons.filter((b) => !existingIds.has(b.id))
      infoGapButtons.value = [...infoGapButtons.value, ...newBtns]
      rebuildAgentTimeline()
    }
    return
  }
}

function speakerInitial(speaker: string | null | undefined): string {
  const s = (speaker || '未').trim()
  if (!s) return '未'
  const asciiOnly = /^[A-Za-z0-9]+$/.test(s)
  if (asciiOnly) return s.slice(0, 2).toUpperCase()
  return s.slice(0, 2)
}

/** 用于分组合并连续同一说话人；优先用 speaker（uid），否则用展示名 */
function speakerKey(t: AppTranscript): string {
  const id = (t.speaker || '').trim()
  if (id) return id
  return (t.speaker_name || '').trim() || '__unknown__'
}

function speakerDisplayLabel(t: AppTranscript): string {
  return (t.speaker_name || t.speaker || '未知说话人').trim() || '未知说话人'
}

const AVATAR_CLASS_BY_HASH = [
  'app-session-detail-avatar--blue',
  'app-session-detail-avatar--sky',
  'app-session-detail-avatar--cyan',
  'app-session-detail-avatar--teal',
  'app-session-detail-avatar--emerald',
  'app-session-detail-avatar--green',
  'app-session-detail-avatar--lime',
  'app-session-detail-avatar--violet',
  'app-session-detail-avatar--indigo',
  'app-session-detail-avatar--amber',
  'app-session-detail-avatar--orange',
  'app-session-detail-avatar--rose',
]

function avatarClassForKey(key: string): string {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0
  const classes = AVATAR_CLASS_BY_HASH
  const i = Math.abs(h) % classes.length
  return classes[i] ?? classes[0] ?? 'app-session-detail-avatar--blue'
}

function transcriptTimeLabel(item: AppTranscript): string {
  if (item.created_at) {
    const d = new Date(item.created_at)
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
    }
  }
  const s = item.start != null ? String(item.start) : ''
  const e = item.end != null ? String(item.end) : ''
  if (s && e) return `${s} - ${e}`
  return s || e || ''
}

interface TranscriptMessageGroup {
  groupKey: string
  speakerLabel: string
  initial: string
  avatarClass: string
  messages: AppTranscript[]
}

interface LiveTranscriptSegment {
  segment_key: string
  text: string
  speaker?: string
  status: 'live' | 'pending_final'
}

function buildTranscriptGroups(items: AppTranscript[]): TranscriptMessageGroup[] {
  const sorted = [...items].sort((a, b) => {
    const sa = String(a.start ?? '')
    const sb = String(b.start ?? '')
    return sa.localeCompare(sb)
  })
  const groups: TranscriptMessageGroup[] = []
  for (const t of sorted) {
    const key = speakerKey(t)
    const prev = groups[groups.length - 1]
    if (prev && prev.groupKey === key) {
      prev.messages.push(t)
    } else {
      groups.push({
        groupKey: key,
        speakerLabel: speakerDisplayLabel(t),
        initial: speakerInitial(t.speaker_name || t.speaker),
        avatarClass: avatarClassForKey(key),
        messages: [t],
      })
    }
  }
  return groups
}

const groupedTranscripts = computed(() => buildTranscriptGroups(transcripts.value))
const liveSegments = ref<Record<string, LiveTranscriptSegment>>({})
const liveSegmentList = computed(() => Object.values(liveSegments.value))

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
  await Promise.allSettled([
    fetchSummaryHistory(),
    fetchPushLogs(),
  ])
  // 仅会话已「进行中」时才自动连接 WS（如刷新页面场景）
  if (session.value?.status === 'ongoing') {
    openWebSocket()
    void fetchInfoGapButtons()
    void fetchLatestSummary()
    startAnalysisClock()
  } else if (session.value?.status === 'ended') {
    void fetchLatestSummary()
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
  stopAnalysisClock()
  closeWsForUnmount()
  wsStatus.value = 'disconnected'
})
</script>

<template>
  <div class="app-session-detail-page">
    <!-- 推送消息 Toast（fixed 定位，不占文档流） -->
    <PushNotification
      :content="pushContent"
      :visible="pushVisible"
      @dismissed="pushVisible = false"
    />

    <div v-if="pageLoading" class="app-session-detail-loading">正在加载会话详情...</div>

    <div v-else-if="error" class="app-session-detail-error">{{ error }}</div>

    <template v-else-if="session">
      <div class="app-session-detail-header">
        <div class="app-session-detail-title-row">
          <button type="button" class="app-session-detail-back-btn" @click="goBack">‹</button>
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

      <!-- 信息缺口关键词按钮（会话进行中时显示） -->
      <InfoGapButtons
        v-if="session.status === 'ongoing' && infoGapButtons.length > 0"
        :session-id="sessionId"
        :buttons="infoGapButtons"
        @clicked="handleInfoGapButtonClicked"
      />

      <!-- AI 分析时钟（会话进行中时显示） -->
      <div v-if="session.status === 'ongoing'" class="app-agent-status-bar">
        <span class="app-agent-status-dot" aria-hidden="true"></span>
        <template v-for="(clock, index) in analysisClocks" :key="clock.key">
          <span v-if="index > 0" class="app-agent-status-sep">&nbsp;·&nbsp;</span>
          {{ clock.label }} {{ clock.secondsLeft }}s 后
        </template>
      </div>
      <div v-if="session.status === 'ongoing'" class="app-agent-status-note">
        倒计时按会话开始时间恢复，刷新页面后会继续对齐真实分析时钟。
      </div>

      <!-- 讨论摘要（有内容时显示） -->
      <div v-if="currentSummary" class="app-session-summary-panel">
        <div class="app-session-summary-header">
          <span class="app-session-summary-icon" aria-hidden="true">◈</span>
          <span class="app-session-summary-label">讨论摘要</span>
          <span class="app-session-summary-version">v{{ summaryVersion }}</span>
        </div>
        <p class="app-session-summary-content">{{ currentSummary }}</p>
        <p class="app-session-summary-note">这里显示的是最新摘要内容，不代表分析开始时间；具体时间请看下方轮次时间线。</p>
      </div>

      <div v-if="agentTimelineRuns.length > 0" class="app-agent-timeline-panel">
        <div class="app-agent-timeline-header">
          <span class="app-agent-timeline-label">Agent 时间线</span>
          <span class="app-agent-timeline-sub">按分析轮次展示计划时间、覆盖窗口与实际产出</span>
        </div>
        <div class="app-agent-timeline-note">{{ timelineLegend }}</div>
        <ul class="app-agent-timeline-list">
          <li
            v-for="run in agentTimelineRuns"
            :key="run.id"
            class="app-agent-timeline-item"
            :class="`is-${run.kind}`"
          >
            <div class="app-agent-timeline-time">{{ timelineTimeLabel(run.scheduledAt) }}</div>
            <div class="app-agent-timeline-body">
              <div class="app-agent-timeline-title-row">
                <span class="app-agent-timeline-title">{{ run.title }}</span>
                <span v-if="run.kind === 'summary_run' && run.summaryVersion" class="app-agent-timeline-badge">v{{ run.summaryVersion }}</span>
              </div>
              <div class="app-agent-timeline-window">
                计划开始：{{ timelineTimeLabel(run.scheduledAt) }}
              </div>
              <div class="app-agent-timeline-window">
                覆盖窗口：{{ timelineWindowLabel(run.windowStart, run.windowEnd) }}
              </div>
              <div v-if="run.producedAt" class="app-agent-timeline-window">
                实际产出：{{ timelineTimeLabel(run.producedAt) }}
              </div>
              <p v-if="run.summaryContent" class="app-agent-timeline-content">{{ run.summaryContent }}</p>
              <p v-for="push in run.pushes" :key="`${run.id}-${push}`" class="app-agent-timeline-content">{{ push }}</p>
              <div v-if="run.keywords.length > 0" class="app-agent-timeline-window">
                信息缺口：{{ run.keywords.join('、') }}
              </div>
            </div>
          </li>
        </ul>
      </div>

      <!-- 最近 AI 建议（常驻，避免提示一闪而过） -->
      <div v-if="recentPushes.length > 0" class="app-ai-suggestions-panel">
        <div class="app-ai-suggestions-header">
          <span class="app-ai-suggestions-label">最近 AI 建议</span>
          <span class="app-ai-suggestions-sub">保留最近 {{ recentPushes.length }} 条</span>
        </div>
        <ul class="app-ai-suggestions-list">
          <li
            v-for="item in recentPushes"
            :key="`${item.at}-${item.content}`"
            class="app-ai-suggestions-item"
          >
            <span class="app-ai-suggestions-time">{{ pushTimeLabel(item.at) }}</span>
            <span class="app-ai-suggestions-content">{{ item.content }}</span>
          </li>
        </ul>
      </div>

      <div class="app-session-detail-transcripts">
        <h3 class="app-session-detail-transcripts-title">
          讨论实录
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

        <div v-if="transcriptsLoading" class="app-session-detail-loading">正在加载讨论实录...</div>
        <div
          v-else-if="!transcripts.length && !liveSegmentList.length"
          class="app-session-detail-transcripts-empty"
        >
          暂无讨论实录
        </div>
        <div v-else ref="transcriptsListEl" class="app-session-detail-transcripts-scroll">
          <ul class="app-session-detail-transcripts-list">
            <li
              v-for="(group, gIdx) in groupedTranscripts"
              :key="`${group.groupKey}-${gIdx}`"
              class="app-session-detail-transcript-group"
            >
              <div class="app-session-detail-transcript-row">
                <div
                  class="app-session-detail-transcript-avatar"
                  :class="group.avatarClass"
                  :title="group.speakerLabel"
                  aria-hidden="true"
                >
                  {{ group.initial }}
                </div>
                <div class="app-session-detail-transcript-bubbles">
                  <p class="app-session-detail-speaker-name">{{ group.speakerLabel }}</p>
                  <div
                    v-for="(item, idx) in group.messages"
                    :key="item.transcript_id"
                    class="app-session-detail-bubble-stack"
                  >
                    <div class="app-session-detail-bubble">
                      <p class="app-session-detail-transcript-text">{{ item.text }}</p>
                    </div>
                    <p
                      v-if="idx === group.messages.length - 1"
                      class="app-session-detail-bubble-time"
                    >
                      {{ transcriptTimeLabel(item) }}
                    </p>
                  </div>
                </div>
              </div>
            </li>
            <li
              v-for="seg in liveSegmentList"
              :key="seg.segment_key"
              class="app-session-detail-transcript-group app-session-detail-transcript-group--live"
              :class="{
                'app-session-detail-transcript-group--pending': seg.status === 'pending_final',
              }"
            >
              <div class="app-session-detail-transcript-row">
                <div
                  class="app-session-detail-transcript-avatar app-session-detail-avatar--gray"
                  :title="seg.status === 'pending_final' ? '确认中' : '识别中'"
                  aria-hidden="true"
                >
                  ...
                </div>
                <div class="app-session-detail-transcript-bubbles">
                  <p class="app-session-detail-speaker-name">
                    {{ seg.status === 'pending_final' ? '确认中' : '识别中' }}
                  </p>
                  <div
                    class="app-session-detail-bubble"
                    :class="{
                      'app-session-detail-bubble--live': seg.status === 'live',
                      'app-session-detail-bubble--pending': seg.status === 'pending_final',
                    }"
                  >
                    <p class="app-session-detail-transcript-text">{{ seg.text }}</p>
                  </div>
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
.app-agent-status-bar {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 14px;
  margin-bottom: 12px;
  border-radius: 8px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  font-size: 12px;
  color: #15803d;
}

.app-agent-status-note {
  margin: -4px 0 12px;
  font-size: 11px;
  color: #4b5563;
}

.app-agent-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  flex-shrink: 0;
  animation: agent-dot-pulse 2s ease-in-out infinite;
}

@keyframes agent-dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.app-session-summary-panel {
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 8px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}

.app-session-summary-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.app-session-summary-icon {
  font-size: 13px;
  color: #3b82f6;
}

.app-session-summary-label {
  font-size: 12px;
  font-weight: 600;
  color: #1d4ed8;
}

.app-session-summary-version {
  font-size: 11px;
  color: #93c5fd;
  margin-left: auto;
}

.app-session-summary-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #1e3a5f;
  white-space: pre-wrap;
}

.app-session-summary-note {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: #475569;
}

.app-agent-timeline-panel {
  padding: 14px 16px;
  margin-bottom: 12px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #dbeafe;
}

.app-agent-timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.app-agent-timeline-label {
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
}

.app-agent-timeline-sub {
  font-size: 11px;
  color: #64748b;
}

.app-agent-timeline-note {
  margin-bottom: 10px;
  font-size: 11px;
  line-height: 1.5;
  color: #475569;
}

.app-agent-timeline-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.app-agent-timeline-item {
  display: grid;
  grid-template-columns: 148px 1fr;
  gap: 12px;
  align-items: start;
}

.app-agent-timeline-time {
  font-size: 12px;
  color: #475569;
  font-variant-numeric: tabular-nums;
}

.app-agent-timeline-body {
  padding: 10px 12px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
}

.app-agent-timeline-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.app-agent-timeline-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.app-agent-timeline-badge {
  font-size: 11px;
  color: #1d4ed8;
  background: #dbeafe;
  border-radius: 999px;
  padding: 2px 8px;
}

.app-agent-timeline-window {
  font-size: 12px;
  color: #475569;
  margin-bottom: 4px;
}

.app-agent-timeline-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: #1e293b;
  white-space: pre-wrap;
}

.app-ai-suggestions-panel {
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 8px;
  background: #fffbeb;
  border: 1px solid #fde68a;
}

.app-ai-suggestions-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.app-ai-suggestions-label {
  font-size: 12px;
  font-weight: 600;
  color: #92400e;
}

.app-ai-suggestions-sub {
  font-size: 11px;
  color: #b45309;
}

.app-ai-suggestions-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.app-ai-suggestions-item {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 8px;
  font-size: 13px;
  line-height: 1.45;
}

.app-ai-suggestions-time {
  color: #a16207;
  font-variant-numeric: tabular-nums;
}

.app-ai-suggestions-content {
  color: #78350f;
}

.app-session-detail-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 8px 0 16px;
}

.app-session-detail-back-btn {
  background: none;
  border: none;
  font-size: 22px;
  line-height: 1;
  color: var(--app-text-secondary);
  cursor: pointer;
  padding: 0 4px 0 0;
  flex-shrink: 0;
  transition: color 0.15s ease;
}

.app-session-detail-back-btn:hover {
  color: var(--app-text-primary);
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
  font-size: 14px;
  color: var(--app-text-muted);
  padding: 12px 0;
}

/* 聊天气泡区：浅灰底（与 demo bg-slate-50 一致） */
.app-session-detail-transcripts-scroll {
  max-height: calc(100vh - 360px);
  min-height: 220px;
  overflow-y: auto;
  margin: 0 -8px;
  padding: 16px 12px 8px;
  border-radius: var(--app-radius-md);
  background: var(--app-bg-page);
}

.app-session-detail-transcripts-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.app-session-detail-transcript-group {
  list-style: none;
}

.app-session-detail-transcript-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.app-session-detail-transcript-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.app-session-detail-avatar--blue {
  background: #3b82f6;
}

.app-session-detail-avatar--sky {
  background: #0ea5e9;
}

.app-session-detail-avatar--cyan {
  background: #06b6d4;
}

.app-session-detail-avatar--teal {
  background: #14b8a6;
}

.app-session-detail-avatar--emerald {
  background: #10b981;
}

.app-session-detail-avatar--green {
  background: #22c55e;
}

.app-session-detail-avatar--lime {
  background: #84cc16;
}

.app-session-detail-avatar--violet {
  background: #8b5cf6;
}

.app-session-detail-avatar--indigo {
  background: #6366f1;
}

.app-session-detail-avatar--amber {
  background: #f59e0b;
}

.app-session-detail-avatar--orange {
  background: #f97316;
}

.app-session-detail-avatar--rose {
  background: #f43f5e;
}

.app-session-detail-avatar--gray {
  background: #9ca3af;
}

.app-session-detail-transcript-bubbles {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.app-session-detail-speaker-name {
  margin: 0 0 4px 2px;
  font-size: 12px;
  line-height: 1.2;
  color: #6b7280;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-session-detail-bubble-stack {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.app-session-detail-bubble {
  display: inline-block;
  align-self: flex-start;
  max-width: 100%;
  padding: 10px 16px;
  border-radius: 16px;
  border-top-left-radius: 4px;
  background: var(--app-bg-elevated);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.10), 0 1px 2px -1px rgba(15, 23, 42, 0.08);
}

.app-session-detail-bubble--live {
  opacity: 0.82;
  border: 1px dashed #d1d5db;
}

.app-session-detail-bubble--pending {
  opacity: 0.58;
  border: 1px dashed #d1d5db;
}

.app-session-detail-bubble-time {
  margin: 2px 0 0 4px;
  font-size: 11px;
  line-height: 1.3;
  color: var(--app-text-muted);
}

.app-session-detail-transcript-text {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--app-text-primary);
}
</style>
