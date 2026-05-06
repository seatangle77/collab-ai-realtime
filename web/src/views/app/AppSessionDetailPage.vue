<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Capacitor } from '@capacitor/core'
import type { PluginListenerHandle } from '@capacitor/core'
import { App as CapApp } from '@capacitor/app'
import { useAudioRecorder } from '../../composables/useAudioRecorder'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MoreFilled } from '@element-plus/icons-vue'
import AppEmptyState from '../../components/AppEmptyState.vue'
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
  uploadOfflineAudioSegment,
} from '../../api/appSessions'
import { listMyGroups } from '../../api/appGroups'
import { extractErrorMessage } from '../../utils/error'
import PushNotification from '../../components/PushNotification.vue'
import { type InfoGapButton } from '../../components/InfoGapButtons.vue'
import AiInsightSheet from '../../components/AiInsightSheet.vue'
import { appHttp } from '../../api/appHttp'
import { buildPushLogDedupeKey, parsePushLogTime, sortPushLogsByTriggeredAtDesc } from '../../utils/pushLogs'

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
const reconnectAttempt = ref(0)
const pendingRecordingStart = ref(false)
const {
  isRecording,
  recordingSource,
  onChunk,
  startRecording,
  startFileInjection,
  restartSegment,
  stopRecording,
} = useAudioRecorder()
const transcriptsListEl = ref<HTMLElement | null>(null)
const debugAudioEnabled = ref(false)
const debugFileInputEl = ref<HTMLInputElement | null>(null)
const debugInjecting = ref(false)
const debugInjectedFileName = ref('')
const selectedInjectionFile = ref<File | null>(null)

interface PushLogItem {
  id: string
  session_id: string
  target_user_id?: string | null
  state_id?: string | null
  analysis_run_id?: string | null
  analysis_window_start?: string | null
  push_content?: string | null
  push_channel: string
  jpush_message_id?: string | null
  delivery_status: string
  delivery_reason?: string | null
  triggered_at: string
  delivered_at?: string | null
}

interface SummaryHistoryItem {
  id: string
  session_id: string
  version: number
  content: string
  analysis_run_id: string
  window_start?: string | null
  window_end?: string | null
  created_at?: string | null
}

type AudioUploadNoticeKind = 'info' | 'success' | 'warning' | 'error'
type OfflineAudioSegmentStatus = 'buffering' | 'pending_upload' | 'uploading' | 'uploaded' | 'failed'

interface OfflineAudioSegment {
  id: string
  mimeType: string
  startedAt: number
  endedAt: number
  chunks: Blob[]
  sizeBytes: number
  status: OfflineAudioSegmentStatus
  retryCount: number
}

// ── 推送通知 ──────────────────────────────────────────────────────────────────
const pushContent = ref('')
const pushVisible = ref(false)

function showPushNotification(content: string, _triggeredAt?: string | null) {
  pushContent.value = content
  pushVisible.value = false
  // 强制触发 watch（即使上一条还没消失也能重新触发）
  requestAnimationFrame(() => { pushVisible.value = true })
}

// ── 讨论摘要 ──────────────────────────────────────────────────────────────────
const currentSummary = ref('')
const summaryVersion = ref(0)
const summaryHistory = ref<SummaryHistoryItem[]>([])
const pushLogs = ref<PushLogItem[]>([])
const seenPushNotificationKeys = new Set<string>()

function normalizeInfoGapButton(button: InfoGapButton): InfoGapButton {
  return {
    ...button,
    explanation: button.explanation ?? '',
    viewed: button.viewed ?? false,
  }
}

function normalizePushLog(item: PushLogItem): PushLogItem | null {
  if (!item.push_content) return null
  if (currentUser.value?.id && item.target_user_id && item.target_user_id !== currentUser.value.id) {
    return null
  }
  return item
}

function pushLogMergeKey(item: PushLogItem): string {
  return buildPushLogDedupeKey(item) ?? item.id
}

function sortPushLogs(items: PushLogItem[]): PushLogItem[] {
  return sortPushLogsByTriggeredAtDesc(items)
}

function isAiInterventionPushLog(item: PushLogItem): boolean {
  return item.push_channel === 'web' && Boolean(item.state_id || item.analysis_run_id || item.analysis_window_start)
}

function mergePushLogs(existing: PushLogItem[], incoming: PushLogItem[]): { merged: PushLogItem[]; newItems: PushLogItem[] } {
  const byKey = new Map<string, PushLogItem>()
  const existingKeys = new Set(existing.map((item) => pushLogMergeKey(item)))

  for (const item of existing) {
    byKey.set(pushLogMergeKey(item), item)
  }

  const newItems: PushLogItem[] = []
  for (const raw of incoming) {
    const item = normalizePushLog(raw)
    if (!item) continue
    const key = pushLogMergeKey(item)
    const previous = byKey.get(key)
    if (!previous) {
      byKey.set(key, item)
      newItems.push(item)
      continue
    }
    if (previous.id.startsWith('live-push-') && !item.id.startsWith('live-push-')) {
      byKey.set(key, item)
      continue
    }
    byKey.set(key, { ...previous, ...item })
  }

  return {
    merged: sortPushLogs(Array.from(byKey.values())),
    newItems: newItems.filter((item) => !existingKeys.has(pushLogMergeKey(item))),
  }
}

function maybeNotifyNewPush(item: PushLogItem) {
  const key = pushLogMergeKey(item)
  if (seenPushNotificationKeys.has(key)) return
  seenPushNotificationKeys.add(key)
  if (item.push_content) {
    showPushNotification(item.push_content, item.triggered_at)
  }
}

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
    const data = await appHttp.get<SummaryHistoryItem[]>(
      `/api/sessions/${sessionId}/summaries`,
    )
    summaryHistory.value = [...data].sort((a, b) => b.version - a.version)
  } catch {
    // 404 或暂无摘要时静默处理
  }
}

async function fetchPushLogs(options: { notifyNew?: boolean } = {}) {
  try {
    const data = await appHttp.get<PushLogItem[]>(
      `/api/sessions/${sessionId}/push-logs`,
    )
    const normalized = data
      .map((item) => normalizePushLog(item))
      .filter((item): item is PushLogItem => Boolean(item))
    const { merged, newItems } = mergePushLogs(pushLogs.value, normalized)
    pushLogs.value = merged
    if (options.notifyNew) {
      const latestNew = sortPushLogs(newItems).find((item) => !isAiInterventionPushLog(item))
      if (latestNew) maybeNotifyNewPush(latestNew)
    }
  } catch {
    // 静默失败，不覆盖已展示内容
  }
}

// ── 相关概念 ──────────────────────────────────────────────────────────────────
const infoGapButtons = ref<InfoGapButton[]>([])

async function fetchInfoGapButtons() {
  try {
    const includeAll = session.value?.status === 'ended'
    const data = await appHttp.get<InfoGapButton[]>(
      `/api/sessions/${sessionId}/info-gap/buttons${includeAll ? '?include_all=true' : ''}`,
    )
    infoGapButtons.value = data.map((button) => normalizeInfoGapButton(button))
  } catch {
    // 静默失败，不影响主流程
  }
}

function handleInfoGapButtonClicked(buttonId: string, content: string, keyword: string) {
  infoGapButtons.value = infoGapButtons.value.map((button) => {
    if (button.id !== buttonId) return button
    return {
      ...button,
      explanation: content,
      viewed: true,
    }
  })
  if (content) showPushNotification(`${keyword}：${content}`)
}

function upsertPushEvent(push: PushLogItem) {
  const normalized = normalizePushLog(push)
  if (!normalized) return
  const { merged, newItems } = mergePushLogs(pushLogs.value, [normalized])
  pushLogs.value = merged
  const latestNew = sortPushLogs(newItems)[0]
  if (latestNew) maybeNotifyNewPush(latestNew)
}

const wsStatusLabel = computed(() => {
  switch (wsStatus.value) {
    case 'connecting':
      return '正在连接...'
    case 'connected':
      return ''
    case 'reconnecting':
      return '网络不稳定，正在恢复...'
    case 'disconnected':
      return '连接已断开'
    default:
      return ''
  }
})

const BASE_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 30_000
const MAX_RECONNECT_TRIES = 5
const OFFLINE_AUDIO_MAX_MS = 60_000
const OFFLINE_AUDIO_MAX_BYTES = 20 * 1024 * 1024
const OFFLINE_AUDIO_MAX_RETRIES = 2
const LIVE_SEGMENT_TTL_MS =
  typeof window !== 'undefined' && typeof (window as any).__APP_LIVE_SEGMENT_TTL_MS === 'number'
    ? (window as any).__APP_LIVE_SEGMENT_TTL_MS
    : 30_000
const LIVE_SEGMENT_CLEANUP_INTERVAL_MS = 5_000

let appStateListener: PluginListenerHandle | null = null
let ws: WebSocket | null = null
let pingTimer: ReturnType<typeof setInterval> | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pushLogsPollTimer: ReturnType<typeof setInterval> | null = null
let liveSegmentCleanupTimer: ReturnType<typeof setInterval> | null = null
let unmounted = false
/** 为 true 时不自动重连（页面卸载、主动关闭） */
let wsIntentionalClose = false
let chunkSeq = 0
let activeOfflineAudioSegment: OfflineAudioSegment | null = null
let offlineAudioTransitioning = false
let audioNoticeTimer: ReturnType<typeof setTimeout> | null = null

const offlineAudioSegments = ref<OfflineAudioSegment[]>([])
const audioUploadNotice = ref('')
const audioUploadNoticeKind = ref<AudioUploadNoticeKind>('info')
const offlineAudioPartialLost = ref(false)
const offlineAudioFlushing = ref(false)

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
const canStartRecording = computed(() => {
  return isHost.value
    && session.value?.status === 'ongoing'
    && wsStatus.value === 'connected'
    && !isRecording.value
    && !debugInjecting.value
})
const canStopRecording = computed(() => {
  return isHost.value && session.value?.status === 'ongoing' && isRecording.value
})
const canUseFileInjection = computed(() => {
  return debugAudioEnabled.value
    && session.value?.status === 'ongoing'
    && wsStatus.value === 'connected'
    && !debugInjecting.value
    && !Capacitor.isNativePlatform()
})
const canSelectInjectionFile = computed(() => {
  return debugAudioEnabled.value && !debugInjecting.value && !Capacitor.isNativePlatform()
})
const recorderMetaText = computed(() => {
  if (debugInjecting.value) {
    return debugInjectedFileName.value
      ? `正在准备注入 ${debugInjectedFileName.value}，完成后会沿用正式录音链路发送。`
      : '正在准备文件注入，完成后会沿用正式录音链路发送。'
  }
  if (recordingSource.value === 'file') {
    return debugInjectedFileName.value
      ? `文件注入中：${debugInjectedFileName.value}，音频会沿用正式录音链路实时发送到会话连接。`
      : '文件注入中，音频会沿用正式录音链路实时发送到会话连接。'
  }
  if (isRecording.value) {
    return '录音中，音频会实时发送到会话连接。'
  }
  if (selectedInjectionFile.value) {
    return `已选择测试音频：${selectedInjectionFile.value.name}，发起后会自动注入。`
  }
  return '连接成功后可开始录音并实时发送音频。'
})
const hasSummary = computed(() => !!currentSummary.value)
const shouldShowWsStatus = computed(() => {
  return session.value?.status === 'ongoing' && wsStatus.value !== 'connected'
})

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
    if (!selectedInjectionFile.value) {
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
    clearPushLogsPollTimer()
    await flushOfflineAudioSegments()
    await stopRecording()
    resetDebugInjectionState()
    resetOfflineAudioState()
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

async function handleStartRecording() {
  if (!canStartRecording.value) return
  chunkSeq = 0
  resetOfflineAudioState()
  try {
    await startRecording()
  } catch (err) {
    ElMessage.error(extractErrorMessage(err))
  }
}

async function handleStopRecording() {
  if (!canStopRecording.value) return
  try {
    await flushOfflineAudioSegments()
    await stopRecording()
    resetDebugInjectionState()
  } catch (err) {
    ElMessage.error(extractErrorMessage(err))
  }
}

async function openDebugFilePicker() {
  if (!canSelectInjectionFile.value) return
  if (session.value?.status === 'ongoing' && isRecording.value) {
    try {
      await stopRecording()
      resetDebugInjectionState()
    } catch (err) {
      ElMessage.error(extractErrorMessage(err))
      return
    }
  }
  debugFileInputEl.value?.click()
}

function resetDebugInjectionState() {
  debugInjecting.value = false
  debugInjectedFileName.value = ''
}

async function handleDebugFileSelected(event: Event) {
  const input = event.target as HTMLInputElement | null
  const file = input?.files?.[0]
  if (!file) {
    return
  }
  if (file.type && !file.type.startsWith('audio/')) {
    resetDebugInjectionState()
    ElMessage.error('请选择音频文件进行注入')
    if (input) {
      input.value = ''
    }
    return
  }
  debugInjectedFileName.value = file.name
  selectedInjectionFile.value = file
  if (session.value?.status === 'ongoing') {
    chunkSeq = 0
    debugInjecting.value = true
    try {
      await startFileInjection(file)
    } catch (err) {
      resetDebugInjectionState()
      ElMessage.error(extractErrorMessage(err))
    } finally {
      debugInjecting.value = false
      if (input) {
        input.value = ''
      }
    }
    return
  }
  ElMessage.success(`已选择测试音频：${file.name}`)
  if (input) {
    input.value = ''
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
  wsIntentionalClose = false
  openWebSocket()
}


function handleSessionAction(command: string) {
  if (command === 'edit') {
    void handleEditTitle()
    return
  }
  if (command === 'cancel') {
    void handleCancel()
    return
  }
  if (command === 'leave') {
    handleLeave()
  }
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

function setAudioUploadNotice(
  message: string,
  kind: AudioUploadNoticeKind,
  options: { autoClearMs?: number } = {},
) {
  if (audioNoticeTimer) {
    clearTimeout(audioNoticeTimer)
    audioNoticeTimer = null
  }
  audioUploadNotice.value = message
  audioUploadNoticeKind.value = kind
  if (options.autoClearMs) {
    audioNoticeTimer = setTimeout(() => {
      audioUploadNotice.value = ''
      audioNoticeTimer = null
    }, options.autoClearMs)
  }
}

function clearAudioUploadNotice() {
  if (audioNoticeTimer) {
    clearTimeout(audioNoticeTimer)
    audioNoticeTimer = null
  }
  audioUploadNotice.value = ''
}

function buildOfflineSegmentId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `offline-${crypto.randomUUID()}`
  }
  return `offline-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function totalOfflineAudioBytes(): number {
  return offlineAudioSegments.value.reduce((sum, segment) => sum + segment.sizeBytes, 0)
    + (activeOfflineAudioSegment?.sizeBytes ?? 0)
}

function totalOfflineAudioMs(now = Date.now()): number {
  const queuedMs = offlineAudioSegments.value.reduce(
    (sum, segment) => sum + Math.max(0, segment.endedAt - segment.startedAt),
    0,
  )
  const activeMs = activeOfflineAudioSegment
    ? Math.max(0, now - activeOfflineAudioSegment.startedAt)
    : 0
  return queuedMs + activeMs
}

function markOfflineAudioPartialLost(message = '网络中断时间较长，部分录音未能保存，实录可能不完整') {
  offlineAudioPartialLost.value = true
  setAudioUploadNotice(message, 'warning')
}

function shouldBufferOfflineAudio(): boolean {
  return isHost.value
    && isRecording.value
    && recordingSource.value === 'microphone'
    && session.value?.status === 'ongoing'
}

async function beginOfflineAudioBuffering() {
  if (!shouldBufferOfflineAudio()) return
  if (activeOfflineAudioSegment || offlineAudioTransitioning) return

  offlineAudioTransitioning = true
  setAudioUploadNotice('网络中断，正在暂存录音', offlineAudioPartialLost.value ? 'warning' : 'info')
  try {
    await restartSegment()
    const now = Date.now()
    activeOfflineAudioSegment = {
      id: buildOfflineSegmentId(),
      mimeType: 'audio/webm',
      startedAt: now,
      endedAt: now,
      chunks: [],
      sizeBytes: 0,
      status: 'buffering',
      retryCount: 0,
    }
  } catch (err) {
    console.warn('beginOfflineAudioBuffering failed:', err)
    markOfflineAudioPartialLost('网络中断期间录音暂存启动失败，实录可能不完整')
  } finally {
    offlineAudioTransitioning = false
  }
}

function queueActiveOfflineAudioSegment() {
  if (!activeOfflineAudioSegment) return
  const segment = activeOfflineAudioSegment
  activeOfflineAudioSegment = null
  if (!segment.chunks.length || segment.sizeBytes <= 0) return
  offlineAudioSegments.value = [
    ...offlineAudioSegments.value,
    { ...segment, status: 'pending_upload' },
  ]
}

function bufferOfflineAudioChunk(blob: Blob, mimeType: string) {
  if (!activeOfflineAudioSegment) {
    void beginOfflineAudioBuffering()
    return
  }

  const now = Date.now()
  const nextBytes = totalOfflineAudioBytes() + blob.size
  const nextMs = totalOfflineAudioMs(now)
  if (nextBytes > OFFLINE_AUDIO_MAX_BYTES || nextMs > OFFLINE_AUDIO_MAX_MS) {
    markOfflineAudioPartialLost()
    return
  }

  activeOfflineAudioSegment.mimeType = mimeType || activeOfflineAudioSegment.mimeType
  activeOfflineAudioSegment.endedAt = now
  activeOfflineAudioSegment.chunks.push(blob)
  activeOfflineAudioSegment.sizeBytes += blob.size
}

async function prepareOfflineAudioForReplay() {
  if (!activeOfflineAudioSegment || offlineAudioTransitioning) {
    queueActiveOfflineAudioSegment()
    return
  }

  offlineAudioTransitioning = true
  try {
    await restartSegment()
  } catch (err) {
    console.warn('prepareOfflineAudioForReplay restart failed:', err)
    markOfflineAudioPartialLost('网络恢复时录音分段失败，部分实录可能不完整')
  } finally {
    offlineAudioTransitioning = false
    queueActiveOfflineAudioSegment()
  }
}

async function flushOfflineAudioSegments() {
  await prepareOfflineAudioForReplay()
  if (!offlineAudioSegments.value.length || offlineAudioFlushing.value) return

  offlineAudioFlushing.value = true
  setAudioUploadNotice('网络已恢复，正在补传刚才的录音', offlineAudioPartialLost.value ? 'warning' : 'info')
  try {
    while (offlineAudioSegments.value.length) {
      const segment = offlineAudioSegments.value[0]
      if (!segment) break
      segment.status = 'uploading'
      const audio = new Blob(segment.chunks, { type: segment.mimeType })
      try {
        await uploadOfflineAudioSegment(sessionId, {
          segmentId: segment.id,
          startedAt: new Date(segment.startedAt).toISOString(),
          endedAt: new Date(segment.endedAt).toISOString(),
          mimeType: segment.mimeType,
          audio,
        })
        segment.status = 'uploaded'
        offlineAudioSegments.value = offlineAudioSegments.value.slice(1)
      } catch (err) {
        segment.retryCount += 1
        if (segment.retryCount <= OFFLINE_AUDIO_MAX_RETRIES) {
          segment.status = 'pending_upload'
          continue
        }
        segment.status = 'failed'
        markOfflineAudioPartialLost('部分录音补传失败，实录可能不完整')
        console.warn('offline audio upload failed:', err)
        break
      }
    }
    if (!offlineAudioSegments.value.length && !offlineAudioPartialLost.value) {
      setAudioUploadNotice('刚才的录音已补传', 'success', { autoClearMs: 3000 })
    }
  } finally {
    offlineAudioFlushing.value = false
  }
}

function resetOfflineAudioState() {
  activeOfflineAudioSegment = null
  offlineAudioSegments.value = []
  offlineAudioPartialLost.value = false
  offlineAudioFlushing.value = false
  offlineAudioTransitioning = false
  clearAudioUploadNotice()
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

async function sendAudioChunk(blob: Blob, mimeType = blob.type || 'audio/webm') {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    if (shouldBufferOfflineAudio()) {
      if (!activeOfflineAudioSegment) {
        void beginOfflineAudioBuffering()
      } else if (!offlineAudioTransitioning) {
        bufferOfflineAudioChunk(blob, mimeType)
      }
    }
    return
  }
  chunkSeq += 1
  const audioB64 = await blobToBase64(blob)
  ws.send(
    JSON.stringify({
      type: 'audio_chunk',
      data: {
        seq: chunkSeq,
        mime_type: mimeType,
        audio_b64: audioB64,
        duration_ms: 1000,
        sent_at: Date.now(),
      },
    }),
  )
}

// 注册音频分块回调，每块数据直接发送 WS
onChunk((blob, mimeType) => {
  if (offlineAudioTransitioning) return
  if (activeOfflineAudioSegment || (!ws || ws.readyState !== WebSocket.OPEN)) {
    if (shouldBufferOfflineAudio()) {
      bufferOfflineAudioChunk(blob, mimeType)
    }
    return
  }
  void sendAudioChunk(blob, mimeType).catch((err) => {
    console.warn('sendAudioChunk failed:', err)
    if (shouldBufferOfflineAudio()) {
      void beginOfflineAudioBuffering()
    }
  })
})


function sendPingNow() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  try {
    ws.send(JSON.stringify({ type: 'ping', data: {} }))
  } catch {
    // ignore，close handler 会处理重连
  }
}

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
    return
  }
  if (typeof payload !== 'object' || payload === null) {
    return
  }
  const p = payload as { type?: unknown; data?: unknown }
  const msgType = p.type
  const data = p.data
  if (typeof msgType !== 'string' || typeof data !== 'object' || data === null) {
    return
  }
  if (msgType === 'connected') {
    reconnectAttempt.value = 0
    clearReconnectTimer()
    wsStatus.value = 'connected'
    sendPingNow()
    void flushOfflineAudioSegments()
    void refetchTranscriptsAndMerge().finally(clearLiveSegments)
    void fetchPushLogs()
    if (pendingRecordingStart.value) {
      pendingRecordingStart.value = false
      chunkSeq = 0
      if (selectedInjectionFile.value) {
        debugInjecting.value = true
        debugInjectedFileName.value = selectedInjectionFile.value.name
        startFileInjection(selectedInjectionFile.value)
          .catch((err) => {
            resetDebugInjectionState()
            ElMessage.error(extractErrorMessage(err))
          })
          .finally(() => {
            debugInjecting.value = false
          })
      } else {
        startRecording().catch((err) => {
          ElMessage.error(extractErrorMessage(err))
        })
      }
    }
    return
  }
  if (msgType === 'pong') {
    return
  }
  if (msgType === 'error') {
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
          updatedAt: Date.now(),
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
        updatedAt: Date.now(),
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
    clearPushLogsPollTimer()
    void stopRecording().finally(() => {
      resetDebugInjectionState()
      resetOfflineAudioState()
      clearLiveSegments()
    })
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
      void fetchSummaryHistory()
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
    const isForCurrentUser = !d.target_user_id || !currentUser.value?.id || d.target_user_id === currentUser.value.id
    if (d.content && isForCurrentUser) {
      upsertPushEvent({
        id: `live-push-${d.triggered_at ?? Date.now()}-${d.content}`,
        session_id: sessionId,
        target_user_id: d.target_user_id ?? currentUser.value?.id ?? null,
        state_id: null,
        analysis_run_id: d.analysis_run_id ?? null,
        analysis_window_start: d.analysis_window_start ?? null,
        push_content: d.content,
        push_channel: 'web',
        jpush_message_id: null,
        delivery_status: 'delivered',
        delivery_reason: 'ws_delivered',
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
      const newBtns = d.buttons
        .map((button) => normalizeInfoGapButton(button))
        .filter((b) => !existingIds.has(b.id))
      infoGapButtons.value = [...infoGapButtons.value, ...newBtns]
    }
    return
  }
}

function attachTestMessageInjector() {
  if (typeof window === 'undefined') return
  ;(window as any).__appSessionDetailInjectWsMessage = (message: unknown) => {
    try {
      handleWsMessage(new MessageEvent('message', { data: JSON.stringify(message) }))
    } catch {
      // Test hook only; ignore malformed payloads.
    }
  }
  ;(window as any).__appSessionDetailTriggerBeforeUnload = () => {
    handleBeforeUnload()
  }
}

function detachTestMessageInjector() {
  if (typeof window === 'undefined') return
  delete (window as any).__appSessionDetailInjectWsMessage
  delete (window as any).__appSessionDetailTriggerBeforeUnload
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

function pushDisplayTime(value: string | null | undefined): string {
  const parsed = parsePushLogTime(value)
  if (parsed == null) return ''
  return new Date(parsed).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
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

interface TranscriptGroupTimelineItem {
  type: 'transcript_group'
  key: string
  group: TranscriptMessageGroup
}

interface SuggestionTimelineItem {
  type: 'push'
  key: string
  push: PushLogItem
}

type TranscriptTimelineItem = TranscriptGroupTimelineItem | SuggestionTimelineItem

interface LiveTranscriptSegment {
  segment_key: string
  text: string
  speaker?: string
  status: 'live' | 'pending_final'
  updatedAt: number
}

function transcriptSortTimestamp(item: AppTranscript): number {
  const createdAt = parsePushLogTime(item.created_at)
  if (createdAt != null) return createdAt
  const startTime = parsePushLogTime(String(item.start ?? ''))
  if (startTime != null) return startTime
  return 0
}

function pushSortTimestamp(item: PushLogItem): number {
  return parsePushLogTime(item.triggered_at) ?? 0
}

function buildTranscriptItems(transcriptItems: AppTranscript[], pushItems: PushLogItem[]): TranscriptTimelineItem[] {
  const events = [
    ...transcriptItems.map((item, index) => ({
      type: 'transcript' as const,
      key: item.transcript_id || `transcript-${index}`,
      at: transcriptSortTimestamp(item),
      item,
      order: index,
    })),
    ...pushItems
      .filter((item) => item.push_channel !== 'info_gap')
      .map((item, index) => ({
        type: 'push' as const,
        key: item.id || `push-${index}`,
        at: pushSortTimestamp(item),
        item,
        order: index,
      })),
  ].sort((a, b) => {
    if (a.at !== b.at) return a.at - b.at
    if (a.type !== b.type) return a.type === 'transcript' ? -1 : 1
    return a.order - b.order
  })

  const result: TranscriptTimelineItem[] = []
  let currentGroup: TranscriptMessageGroup | null = null
  let groupIndex = 0

  const flushGroup = () => {
    if (!currentGroup) return
    result.push({
      type: 'transcript_group',
      key: `group-${currentGroup.groupKey}-${groupIndex}`,
      group: currentGroup,
    })
    groupIndex += 1
    currentGroup = null
  }

  for (const event of events) {
    if (event.type === 'push') {
      flushGroup()
      result.push({
        type: 'push',
        key: `push-${event.key}`,
        push: event.item,
      })
      continue
    }

    const transcript = event.item
    const key = speakerKey(transcript)
    if (!currentGroup || currentGroup.groupKey !== key) {
      flushGroup()
      currentGroup = {
        groupKey: key,
        speakerLabel: speakerDisplayLabel(transcript),
        initial: speakerInitial(transcript.speaker_name || transcript.speaker),
        avatarClass: avatarClassForKey(key),
        messages: [transcript],
      }
    } else {
      currentGroup.messages.push(transcript)
    }
  }

  flushGroup()
  return result
}

const transcriptItems = computed(() => buildTranscriptItems(transcripts.value, pushLogs.value))
const liveSegments = ref<Record<string, LiveTranscriptSegment>>({})
const liveSegmentList = computed(() => Object.values(liveSegments.value))

function clearLiveSegments() {
  liveSegments.value = {}
}

function cleanupExpiredLiveSegments() {
  const now = Date.now()
  const next: Record<string, LiveTranscriptSegment> = {}
  for (const [key, segment] of Object.entries(liveSegments.value)) {
    if (now - segment.updatedAt <= LIVE_SEGMENT_TTL_MS) {
      next[key] = segment
    }
  }
  if (Object.keys(next).length !== Object.keys(liveSegments.value).length) {
    liveSegments.value = next
  }
}

function startLiveSegmentCleanupTimer() {
  clearLiveSegmentCleanupTimer()
  liveSegmentCleanupTimer = setInterval(
    cleanupExpiredLiveSegments,
    LIVE_SEGMENT_CLEANUP_INTERVAL_MS,
  )
}

function clearLiveSegmentCleanupTimer() {
  if (liveSegmentCleanupTimer != null) {
    clearInterval(liveSegmentCleanupTimer)
    liveSegmentCleanupTimer = null
  }
}

function scrollTranscriptsToBottom() {
  nextTick(() => {
    const el = transcriptsListEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(
  () => transcriptItems.value.length,
  () => {
    scrollTranscriptsToBottom()
  },
)

watch(isRecording, (active) => {
  if (!active && recordingSource.value == null && (debugInjecting.value || debugInjectedFileName.value)) {
    resetDebugInjectionState()
  }
})


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
    console.warn('refetchTranscriptsAndMerge failed:', err)
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

function clearPushLogsPollTimer() {
  if (pushLogsPollTimer != null) {
    clearInterval(pushLogsPollTimer)
    pushLogsPollTimer = null
  }
}

function handleVisibilityChange() {
  if (document.visibilityState === 'visible') sendPingNow()
}

function handleDeviceChange() {
  sendPingNow()
}

function closeWsForUnmount() {
  wsIntentionalClose = true
  clearReconnectTimer()
  clearPushLogsPollTimer()
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
  socket.onerror = () => {
    if (unmounted || wsIntentionalClose) return
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
    void beginOfflineAudioBuffering()
    scheduleReconnect()
  }
}

onMounted(async () => {
  unmounted = false
  wsIntentionalClose = false
  reconnectAttempt.value = 0
  attachTestMessageInjector()
  startLiveSegmentCleanupTimer()
  debugAudioEnabled.value = true
  currentUser.value = loadCurrentUser()
  await loadData()
  await Promise.allSettled([
    fetchPushLogs(),
  ])
  // 仅会话已「进行中」时才自动连接 WS（如刷新页面场景）
  if (session.value?.status === 'ongoing') {
    openWebSocket()
    void fetchInfoGapButtons()
    void fetchLatestSummary()
    void fetchSummaryHistory()
  } else if (session.value?.status === 'ended') {
    void fetchLatestSummary()
    void fetchSummaryHistory()
    void fetchInfoGapButtons()
  }
  window.addEventListener('beforeunload', handleBeforeUnload)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  navigator.mediaDevices?.addEventListener('devicechange', handleDeviceChange)
  if (Capacitor.isNativePlatform()) {
    appStateListener = await CapApp.addListener('appStateChange', ({ isActive }) => {
      if (isActive) sendPingNow()
    })
  }
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  navigator.mediaDevices?.removeEventListener('devicechange', handleDeviceChange)
  appStateListener?.remove()
  appStateListener = null
  detachTestMessageInjector()
  unmounted = true
  void stopRecording().finally(() => {
    resetDebugInjectionState()
    resetOfflineAudioState()
    clearLiveSegments()
  })
  closeWsForUnmount()
  clearPushLogsPollTimer()
  clearLiveSegmentCleanupTimer()
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
        <div class="app-session-detail-actions">
          <template v-if="isHost">
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
                v-if="debugAudioEnabled"
                type="button"
                class="app-session-detail-secondary-btn app-session-detail-debug-btn"
                :disabled="!canSelectInjectionFile"
                @click="openDebugFilePicker"
              >
                {{ selectedInjectionFile ? '更换测试音频' : '选择测试音频' }}
              </button>
              <el-dropdown trigger="click" @command="handleSessionAction">
                <button
                  type="button"
                  class="app-session-detail-more-btn"
                  aria-label="更多操作"
                >
                  <el-icon :size="18">
                    <MoreFilled />
                  </el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit">修改标题</el-dropdown-item>
                    <el-dropdown-item command="cancel" class="app-session-detail-dropdown-danger">
                      取消会话
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
            <template v-else-if="session.status === 'ongoing'">
              <button
                type="button"
                class="app-session-detail-danger-btn app-session-detail-icon-btn app-session-detail-danger-btn--primary"
                @click="handleEnd"
                title="结束会话"
              >
                <span class="app-session-detail-btn-icon" aria-hidden="true">⏹</span>
                结束
              </button>
              <button
                v-if="debugAudioEnabled"
                type="button"
                class="app-session-detail-secondary-btn app-session-detail-debug-btn"
                :disabled="!canUseFileInjection"
                @click="openDebugFilePicker"
              >
                {{ selectedInjectionFile ? '更换测试音频' : '文件注入' }}
              </button>
              <el-dropdown trigger="click" @command="handleSessionAction">
                <button
                  type="button"
                  class="app-session-detail-more-btn"
                  aria-label="更多操作"
                >
                  <el-icon :size="18">
                    <MoreFilled />
                  </el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit">修改标题</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </template>
          <template v-else>
            <button
              type="button"
              class="app-session-detail-secondary-btn"
              @click="handleLeave"
            >
              离开会话
            </button>
          </template>
        </div>
        <input
          ref="debugFileInputEl"
          class="app-session-detail-debug-input"
          type="file"
          accept="audio/*"
          @change="handleDebugFileSelected"
        >
      </div>

<div class="app-session-detail-transcripts">
        <div class="app-session-detail-transcripts-header">
          <h3 class="app-session-detail-transcripts-title">
            讨论实录
            <span v-if="!isHost" class="app-session-detail-readonly-badge">只读</span>
          </h3>
          <div
            v-if="shouldShowWsStatus"
            class="app-session-detail-ws-status"
            data-testid="ws-status"
            :class="`is-${wsStatus}`"
          >
            <span class="app-session-detail-ws-status-dot" aria-hidden="true"></span>
            <span>{{ wsStatusLabel }}</span>
          </div>
        </div>
        <div
          v-if="isHost && session.status === 'ongoing'"
          class="app-session-detail-recorder-bar"
        >
          <div class="app-session-detail-recorder-actions">
            <button
              v-if="!isRecording"
              type="button"
              class="app-session-detail-primary-btn app-session-detail-icon-btn"
              :disabled="!canStartRecording"
              data-testid="record-start"
              @click="handleStartRecording"
            >
              <span class="app-session-detail-btn-icon" aria-hidden="true">●</span>
              开始录音
            </button>
            <button
              v-else
              type="button"
              class="app-session-detail-danger-btn app-session-detail-icon-btn"
              data-testid="record-stop"
              @click="handleStopRecording"
            >
              <span class="app-session-detail-btn-icon" aria-hidden="true">■</span>
              停止录音
            </button>
          </div>
          <span class="app-session-detail-recorder-meta">
            {{ recorderMetaText }}
          </span>
        </div>
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
        <div
          v-if="audioUploadNotice"
          class="app-session-detail-audio-upload-banner"
          :class="`is-${audioUploadNoticeKind}`"
        >
          <span class="app-session-detail-audio-upload-dot" aria-hidden="true"></span>
          <span>{{ audioUploadNotice }}</span>
        </div>

        <div v-if="transcriptsLoading" class="app-session-detail-loading">正在加载讨论实录...</div>
        <div
          v-else-if="!transcriptItems.length && !liveSegmentList.length"
          class="app-session-detail-transcripts-empty"
        >
          <AppEmptyState
            icon="📝"
            title="暂无讨论实录"
            description="会话开始后，转录内容会出现在这里。"
            compact
          />
        </div>
        <div v-else ref="transcriptsListEl" class="app-session-detail-transcripts-scroll">
<ul class="app-session-detail-transcripts-list">
            <li
              v-for="item in transcriptItems"
              :key="item.key"
              class="app-session-detail-transcript-group"
            >
              <div v-if="item.type === 'transcript_group'" class="app-session-detail-transcript-row">
                <div
                  class="app-session-detail-transcript-avatar"
                  :class="item.group.avatarClass"
                  :title="item.group.speakerLabel"
                  aria-hidden="true"
                >
                  {{ item.group.initial }}
                </div>
                <div class="app-session-detail-transcript-bubbles">
                  <p class="app-session-detail-speaker-name">{{ item.group.speakerLabel }}</p>
                  <div
                    v-for="(message, idx) in item.group.messages"
                    :key="message.transcript_id"
                    class="app-session-detail-bubble-stack"
                  >
                    <div class="app-session-detail-bubble">
                      <p class="app-session-detail-transcript-text">{{ message.text }}</p>
                    </div>
                    <p
                      v-if="idx === item.group.messages.length - 1"
                      class="app-session-detail-bubble-time"
                    >
                      {{ transcriptTimeLabel(message) }}
                    </p>
                  </div>
                </div>
              </div>
              <div v-else class="app-session-detail-ai-card">
                <div class="app-session-detail-ai-card__head">
                  <span class="app-session-detail-ai-card__icon" aria-hidden="true">◈</span>
                  <span class="app-session-detail-ai-card__label">AI 建议</span>
                  <span class="app-session-detail-ai-card__time">
                    {{ pushDisplayTime(item.push.triggered_at) }}
                  </span>
                </div>
                <p class="app-session-detail-ai-card__content">{{ item.push.push_content }}</p>
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

  <AiInsightSheet
    v-if="(session?.status === 'ongoing' || session?.status === 'ended') && (hasSummary || infoGapButtons.length > 0)"
    :session-id="sessionId"
    :summary="currentSummary"
    :summary-version="summaryVersion"
    :summary-history="summaryHistory"
    :has-summary="hasSummary"
    :buttons="infoGapButtons"
    :session-ongoing="session.status === 'ongoing'"
    @button-clicked="handleInfoGapButtonClicked"
  />
</template>

<style scoped>
.app-session-detail-page {
  max-width: var(--app-content-width-default);
  margin: 0 auto;
  padding: 8px 0 80px;
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
  font-size: var(--app-font-size-caption);
  color: var(--app-text-secondary);
}

.app-session-detail-error {
  padding: 16px 18px;
  border-radius: var(--app-radius-card);
  background: var(--app-danger-soft);
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: var(--app-font-size-body);
}

.app-session-detail-header {
  padding: 18px 20px;
  border-radius: var(--app-radius-card);
  background: var(--app-bg-elevated);
  border: 1px solid var(--app-border);
  box-shadow: var(--app-shadow-card);
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
  font-size: var(--app-font-size-title);
  font-weight: 600;
  color: var(--app-text-primary);
  flex: 1;
}

.app-session-detail-status-tag {
  flex-shrink: 0;
}

.app-session-detail-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}

.app-session-detail-primary-btn {
  border-radius: var(--app-radius-pill);
  border: 1px solid var(--app-primary);
  padding: 6px 16px;
  font-size: 13px;
  background: var(--app-primary);
  color: var(--app-bg-elevated);
  cursor: pointer;
}

.app-session-detail-primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.app-session-detail-primary-btn:not(:disabled):hover {
  background: var(--app-primary-hover);
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
  border-radius: var(--app-radius-pill);
  border: 1px solid var(--app-border);
  padding: 6px 14px;
  font-size: 13px;
  background: var(--app-bg-elevated);
  color: var(--app-text-primary);
  cursor: pointer;
}

.app-session-detail-secondary-btn:hover {
  background: var(--app-bg-page);
}

.app-session-detail-secondary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.app-session-detail-danger-btn {
  border-radius: var(--app-radius-pill);
  border: 1px solid rgba(248, 113, 113, 0.5);
  padding: 6px 14px;
  font-size: 13px;
  background: var(--app-bg-elevated);
  color: #b91c1c;
  cursor: pointer;
}

.app-session-detail-danger-btn--primary {
  margin-left: auto;
}

.app-session-detail-danger-btn:hover:enabled {
  background: var(--app-danger-soft);
  border-color: #ef4444;
}

.app-session-detail-danger-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.app-session-detail-transcripts {
  padding: 18px 20px;
  border-radius: var(--app-radius-card);
  background: var(--app-bg-elevated);
  border: 1px solid var(--app-border);
  box-shadow: var(--app-shadow-card);
}

.app-session-detail-transcripts-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.app-session-detail-transcripts-title {
  margin: 0;
  font-size: var(--app-font-size-heading);
  font-weight: 600;
  color: var(--app-text-primary);
  display: flex;
  align-items: center;
}

.app-session-detail-readonly-badge {
  font-size: 11px;
  font-weight: 400;
  color: var(--app-text-muted);
  background: var(--app-bg-page);
  border-radius: var(--app-radius-pill);
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

.app-session-detail-audio-upload-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 12px;
}

.app-session-detail-audio-upload-banner.is-info {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
}

.app-session-detail-audio-upload-banner.is-success {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.app-session-detail-audio-upload-banner.is-warning {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}

.app-session-detail-audio-upload-banner.is-error {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.app-session-detail-audio-upload-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: currentColor;
  flex-shrink: 0;
}

.app-session-detail-ws-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--app-radius-pill);
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: var(--app-font-size-caption);
  line-height: 1;
}

.app-session-detail-ws-status.is-reconnecting {
  border-color: #fde68a;
  background: #fffbeb;
  color: #a16207;
}

.app-session-detail-ws-status.is-disconnected {
  border-color: #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.app-session-detail-ws-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: currentColor;
  flex-shrink: 0;
}

.app-session-detail-recorder-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.app-session-detail-recorder-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.app-session-detail-debug-btn {
  padding-inline: 12px;
}

.app-session-detail-debug-input {
  display: none;
}

.app-session-detail-recorder-meta {
  font-size: var(--app-font-size-caption);
  color: var(--app-text-secondary);
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
  padding: 12px 12px 8px;
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

.app-session-detail-ai-card {
  margin: 0 auto;
  width: min(100%, 540px);
  padding: 10px 14px;
  border-radius: var(--app-radius-sm);
  background: var(--app-color-ai-soft);
  border: 1px solid var(--app-color-ai-border);
  border-left: 3px solid var(--app-color-ai);
  box-shadow: none;
}

.app-session-detail-ai-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  font-size: var(--app-font-size-caption);
  color: #9a3412;
}

.app-session-detail-ai-card__icon {
  font-size: 13px;
}

.app-session-detail-ai-card__label {
  font-weight: 600;
  color: var(--app-color-ai);
}

.app-session-detail-ai-card__time {
  margin-left: auto;
  color: var(--app-color-ai);
  font-variant-numeric: tabular-nums;
}

.app-session-detail-ai-card__content {
  margin: 0;
  font-size: var(--app-font-size-body);
  line-height: 1.7;
  color: var(--app-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
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
  font-size: var(--app-font-size-caption);
  line-height: 1.2;
  color: var(--app-text-secondary);
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
  border-radius: var(--app-radius-bubble);
  border-top-left-radius: 4px;
  background: var(--app-bg-elevated);
  box-shadow: var(--app-shadow-card);
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

.app-session-detail-more-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--app-radius-pill);
  border: 1px solid var(--app-border);
  background: var(--app-bg-elevated);
  color: var(--app-text-secondary);
  cursor: pointer;
}

.app-session-detail-more-btn:hover {
  background: var(--app-bg-page);
  color: var(--app-text-primary);
}

.app-session-detail-dropdown-danger {
  color: #b91c1c;
}
</style>
