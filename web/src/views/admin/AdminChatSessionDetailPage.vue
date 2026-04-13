<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type {
  AdminChatSession,
  AdminDiscussionState,
  AdminDiscussionSummary,
  AdminInfoGapButton,
  AdminPushLog,
  AdminTranscript,
  AdminWindowMetric,
  Page,
} from '../../types/admin'
import { getAdminChatSession, updateAdminChatSession, deleteAdminChatSession } from '../../api/admin/chat-sessions'
import {
  listAdminTranscripts,
  createAdminTranscript,
  updateAdminTranscript,
  deleteAdminTranscript,
  deleteAdminTranscriptsBatch,
  type CreateAdminTranscriptPayload,
  type UpdateAdminTranscriptPayload,
} from '../../api/admin/adminTranscripts'
import { listPushLogs } from '../../api/admin/push-logs'
import { listDiscussionSummaries } from '../../api/admin/discussion-summaries'
import { listInfoGapButtons } from '../../api/admin/info-gap-buttons'
import { listDiscussionStates } from '../../api/admin/discussion-states'
import { listWindowMetrics } from '../../api/admin/window-metrics'
import { formatDateTimeToCST } from '../../utils/datetime'

const route = useRoute()
const router = useRouter()
const sessionId = route.params.id as string

const STATE_TYPE_LABELS: Record<string, string> = {
  low_participation: '低参与',
  over_dominance: '过度主导',
  disengaged: '参与不足',
  deadlock: '讨论僵局',
  topic_drift: '话题偏移',
  low_depth: '深度不足',
  homogeneous: '观点同质化',
}

interface TranscriptTimelineItem {
  kind: 'transcript'
  key: string
  sortAt: number
  transcript: AdminTranscript
}

interface PushTimelineItem {
  kind: 'push'
  key: string
  sortAt: number
  push: AdminPushLog
}

type TimelineItem = TranscriptTimelineItem | PushTimelineItem

interface AnalysisTimelineEntry {
  key: string
  kind: 'summary' | 'reasoning'
  title: string
  at: string | null
  windowStart: string | null
  windowEnd: string | null
  summaryVersion?: number
  content?: string
  keywords: string[]
  clickedKeywords: string[]
  pushes: AdminPushLog[]
  recipients: string[]
}

const session = ref<AdminChatSession | null>(null)
const pageLoading = ref(true)
const error = ref('')
const refreshing = ref(false)
const transcriptTimelineLoading = ref(false)
const lastRefreshedAt = ref<string | null>(null)
const activeTab = ref<'timeline' | 'analysis' | 'raw'>('timeline')
const elapsedNow = ref(Date.now())

const allTranscripts = ref<AdminTranscript[]>([])
const discussionSummaries = ref<AdminDiscussionSummary[]>([])
const pushLogs = ref<AdminPushLog[]>([])
const infoGapButtons = ref<AdminInfoGapButton[]>([])
const discussionStates = ref<AdminDiscussionState[]>([])
const windowMetrics = ref<AdminWindowMetric[]>([])

const transcripts = ref<AdminTranscript[]>([])
const transcriptTotal = ref(0)
const transcriptPage = ref(1)
const transcriptPageSize = ref(20)
const transcriptLoading = ref(false)
const selectedTranscripts = ref<AdminTranscript[]>([])
const transcriptTableRef = ref<{ clearSelection: () => void } | null>(null)
const timelineScrollEl = ref<HTMLElement | null>(null)
const timelineShouldStickToBottom = ref(true)

const editSessionVisible = ref(false)
const editSessionFormRef = ref<FormInstance>()
const editSessionForm = reactive({
  session_title: '',
  status: 'not_started' as 'not_started' | 'ongoing' | 'ended',
  ended_at: null as Date | null,
})
const editSessionRules: FormRules<typeof editSessionForm> = {
  session_title: [{ required: true, message: '请输入会话标题', trigger: 'blur' }],
}

const addTranscriptVisible = ref(false)
const addTranscriptFormRef = ref<FormInstance>()
const addTranscriptForm = reactive({
  speaker: '',
  text: '',
  start: '',
  end: '',
})
const addTranscriptRules: FormRules<typeof addTranscriptForm> = {
  text: [{ required: true, message: '请输入转写文本', trigger: 'blur' }],
  start: [{ required: true, message: '请输入开始时间', trigger: 'blur' }],
  end: [{ required: true, message: '请输入结束时间', trigger: 'blur' }],
}

const editTranscriptVisible = ref(false)
const editTranscriptFormRef = ref<FormInstance>()
const editTranscriptForm = reactive({
  transcript_id: '',
  speaker: '',
  text: '',
  start: '',
  end: '',
})
const editTranscriptRules: FormRules<typeof editTranscriptForm> = {
  text: [{ required: true, message: '请输入转写文本', trigger: 'blur' }],
  start: [{ required: true, message: '请输入开始时间', trigger: 'blur' }],
  end: [{ required: true, message: '请输入结束时间', trigger: 'blur' }],
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null
const TIMELINE_BOTTOM_THRESHOLD_PX = 48

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null
  const ts = new Date(value).getTime()
  return Number.isNaN(ts) ? null : ts
}

function formatDisplayTime(value: string | null | undefined): string {
  if (!value) return '-'
  try {
    return formatDateTimeToCST(value)
  } catch {
    return value
  }
}

function formatClock(value: string | null | undefined): string {
  const ts = parseTime(value)
  if (ts == null) return '--:--'
  return new Date(ts).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function formatDuration(ms: number | null): string {
  if (ms == null || ms < 0) return '--:--:--'
  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return [hours, minutes, seconds].map((item) => String(item).padStart(2, '0')).join(':')
}

function formatTranscriptSpeakerLabel(transcript: AdminTranscript): string {
  const uid = (transcript.speaker || transcript.user_id || '').trim()
  const name = (transcript.speaker_name || '').trim()
  if (name && uid) return `${name}（${uid}）`
  return name || uid || '未标注说话人'
}

function statusLabel(s: string | null | undefined) {
  if (s === 'ended') return '已结束'
  if (s === 'ongoing') return '进行中'
  return '未开始'
}

function statusType(s: string | null | undefined) {
  if (s === 'ended') return 'info'
  if (s === 'ongoing') return 'success'
  return 'warning'
}

function stateTypeLabel(value: string | null | undefined): string {
  if (!value) return '未知状态'
  return STATE_TYPE_LABELS[value] ?? value
}

function summarizeMetrics(metrics: Record<string, unknown> | null | undefined): string[] {
  if (!metrics) return []
  const entries = [
    ['speaking_ratio', '发言占比'],
    ['silence_s', '沉默时长'],
    ['ttr', '词汇丰富度'],
    ['arg_density', '论证密度'],
    ['srep', '重复度'],
    ['info_gain', '信息增益'],
  ] as const

  return entries
    .map(([key, label]) => {
      const value = metrics[key]
      if (value == null || value === '') return null
      return `${label}: ${String(value)}`
    })
    .filter((item): item is string => Boolean(item))
}

async function loadAllPages<T>(
  fetcher: (page: number, pageSize: number) => Promise<Page<T>>,
  pageSize = 100,
): Promise<T[]> {
  let page = 1
  let total = Infinity
  const items: T[] = []

  while (items.length < total) {
    const res = await fetcher(page, pageSize)
    items.push(...res.items)
    total = res.meta.total
    if (res.items.length === 0 || items.length >= total) break
    page += 1
  }

  return items
}

const sessionDurationText = computed(() => {
  if (!session.value?.started_at) return '--:--:--'
  const startMs = parseTime(session.value.started_at)
  if (startMs == null) return '--:--:--'
  const endMs = session.value.ended_at ? parseTime(session.value.ended_at) : elapsedNow.value
  return formatDuration((endMs ?? elapsedNow.value) - startMs)
})

const refreshText = computed(() => {
  if (!lastRefreshedAt.value) return '尚未刷新'
  return formatDisplayTime(lastRefreshedAt.value)
})

function dedupeTimelinePushLogs(items: AdminPushLog[]): AdminPushLog[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const content = (item.push_content || '').trim()
    if (!content) return false
    const triggeredAt = parseTime(item.triggered_at)
    const timeBucket = triggeredAt == null ? 'na' : String(Math.floor(triggeredAt / 1000))
    const key = [
      item.target_user_id || '',
      item.target_user_name || '',
      content,
      timeBucket,
    ].join('::')
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

const transcriptTimelineItems = computed<TimelineItem[]>(() => {
  const transcriptItems: TimelineItem[] = allTranscripts.value
    .map((item) => {
      const sortAt = parseTime(item.created_at) ?? 0
      return {
        kind: 'transcript' as const,
        key: `transcript-${item.transcript_id}`,
        sortAt,
        transcript: item,
      }
    })

  const pushItems: TimelineItem[] = dedupeTimelinePushLogs(pushLogs.value)
    .map((item) => {
      const sortAt = parseTime(item.triggered_at) ?? 0
      return {
        kind: 'push' as const,
        key: `push-${item.id}`,
        sortAt,
        push: item,
      }
    })

  return [...transcriptItems, ...pushItems].sort((a, b) => a.sortAt - b.sortAt)
})


const analysisTimeline = computed<AnalysisTimelineEntry[]>(() => {
  const summaryEntries: AnalysisTimelineEntry[] = discussionSummaries.value.map((item) => {
    const relatedKeywords = infoGapButtons.value.filter((button) => button.window_start === item.window_start)
    return {
      key: `summary-${item.id}`,
      kind: 'summary',
      title: '摘要分析',
      at: item.created_at,
      windowStart: item.window_start,
      windowEnd: item.window_end,
      summaryVersion: item.version,
      content: item.content,
      keywords: relatedKeywords.map((button) => button.keyword),
      clickedKeywords: relatedKeywords
        .filter((button) => button.status === 'clicked')
        .map((button) => button.keyword),
      pushes: [],
      recipients: [],
    }
  })

  const reasoningEntries: AnalysisTimelineEntry[] = discussionStates.value.map((item) => {
    const stateAt = parseTime(item.triggered_at) ?? 0
    const matchedSummary = discussionSummaries.value.reduce<AdminDiscussionSummary | null>((best, current) => {
      const currentTs = parseTime(current.created_at ?? current.window_end) ?? parseTime(current.window_end) ?? 0
      if (!best) return current
      const bestTs = parseTime(best.created_at ?? best.window_end) ?? parseTime(best.window_end) ?? 0
      return Math.abs(currentTs - stateAt) < Math.abs(bestTs - stateAt) ? current : best
    }, null)

    const relatedPushes = pushLogs.value.filter((push) => push.state_id === item.id)
    const relatedKeywords = matchedSummary
      ? infoGapButtons.value.filter((button) => button.window_start === matchedSummary.window_start)
      : []

    return {
      key: `reasoning-${item.id}`,
      kind: 'reasoning',
      title: `${stateTypeLabel(item.state_type)} 分析`,
      at: item.triggered_at,
      windowStart: matchedSummary?.window_start ?? null,
      windowEnd: matchedSummary?.window_end ?? null,
      keywords: relatedKeywords.map((button) => button.keyword),
      clickedKeywords: relatedKeywords
        .filter((button) => button.status === 'clicked')
        .map((button) => button.keyword),
      pushes: relatedPushes,
      recipients: Array.from(
        new Set(
          relatedPushes
            .map((push) => push.target_user_name || push.target_user_id)
            .filter((name): name is string => Boolean(name)),
        ),
      ),
      content: summarizeMetrics(item.trigger_metrics as Record<string, unknown> | null).join(' / '),
    }
  })

  return [...summaryEntries, ...reasoningEntries].sort((a, b) => {
    const aTime = parseTime(a.at ?? a.windowEnd ?? a.windowStart) ?? 0
    const bTime = parseTime(b.at ?? b.windowEnd ?? b.windowStart) ?? 0
    return bTime - aTime
  })
})

const clickedKeywordIds = computed(() => new Set(
  infoGapButtons.value
    .filter((button) => button.status === 'clicked')
    .map((button) => button.id),
))

function isTimelineNearBottom(): boolean {
  const el = timelineScrollEl.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= TIMELINE_BOTTOM_THRESHOLD_PX
}

function syncTimelineStickiness() {
  timelineShouldStickToBottom.value = isTimelineNearBottom()
}

function scrollTimelineToBottom(force = false) {
  nextTick(() => {
    const el = timelineScrollEl.value
    if (!el) return
    if (!force && !timelineShouldStickToBottom.value) return
    el.scrollTop = el.scrollHeight
    timelineShouldStickToBottom.value = true
  })
}

function handleTimelineScroll() {
  syncTimelineStickiness()
}

async function fetchTranscriptsPage(p: number) {
  transcriptPage.value = p
  transcriptLoading.value = true
  try {
    const res = await listAdminTranscripts({
      session_id: sessionId,
      page: p,
      page_size: transcriptPageSize.value,
    })
    transcripts.value = res.items
    transcriptTotal.value = res.meta.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载转写列表失败')
  } finally {
    transcriptLoading.value = false
  }
}

async function fetchTimelineTranscripts() {
  transcriptTimelineLoading.value = true
  try {
    allTranscripts.value = await loadAllPages((page, pageSize) => listAdminTranscripts({
      session_id: sessionId,
      page,
      page_size: pageSize,
    }))
  } finally {
    transcriptTimelineLoading.value = false
  }
}

async function fetchAnalysisData() {
  const [summaryRes, pushRes, infoGapRes, stateRes, metricRes] = await Promise.allSettled([
    loadAllPages((page, pageSize) => listDiscussionSummaries({ session_id: sessionId, page, page_size: pageSize })),
    loadAllPages((page, pageSize) => listPushLogs({ session_id: sessionId, page, page_size: pageSize })),
    loadAllPages((page, pageSize) => listInfoGapButtons({ session_id: sessionId, page, page_size: pageSize })),
    loadAllPages((page, pageSize) => listDiscussionStates({ session_id: sessionId, page, page_size: pageSize })),
    loadAllPages((page, pageSize) => listWindowMetrics({ session_id: sessionId, page, page_size: pageSize })),
  ])

  if (summaryRes.status === 'fulfilled') discussionSummaries.value = summaryRes.value
  else discussionSummaries.value = []

  if (pushRes.status === 'fulfilled') pushLogs.value = pushRes.value
  else pushLogs.value = []

  if (infoGapRes.status === 'fulfilled') infoGapButtons.value = infoGapRes.value
  else infoGapButtons.value = []

  if (stateRes.status === 'fulfilled') discussionStates.value = stateRes.value
  else discussionStates.value = []

  if (metricRes.status === 'fulfilled') windowMetrics.value = metricRes.value
  else windowMetrics.value = []
}

async function refreshAdminRealtimeData(options: { silent?: boolean } = {}) {
  if (!options.silent) refreshing.value = true
  try {
    const [sessionData] = await Promise.all([
      getAdminChatSession(sessionId),
      fetchTimelineTranscripts(),
      fetchAnalysisData(),
      fetchTranscriptsPage(transcriptPage.value),
    ])
    session.value = sessionData
    lastRefreshedAt.value = new Date().toISOString()
  } catch (e: any) {
    if (!options.silent) {
      ElMessage.error(e?.message || '刷新会话详情失败')
    }
    throw e
  } finally {
    refreshing.value = false
  }
}

async function loadData() {
  pageLoading.value = true
  error.value = ''
  try {
    await refreshAdminRealtimeData()
  } catch {
    error.value = '会话不存在或加载失败'
  } finally {
    pageLoading.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    if (session.value?.status === 'ongoing') {
      void refreshAdminRealtimeData({ silent: true })
    }
  }, 10000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startElapsedTimer() {
  stopElapsedTimer()
  elapsedNow.value = Date.now()
  elapsedTimer = setInterval(() => {
    elapsedNow.value = Date.now()
  }, 1000)
}

function stopElapsedTimer() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

watch(
  () => session.value?.status,
  (status) => {
    if (status === 'ongoing') startPolling()
    else stopPolling()
  },
)

watch(
  () => transcriptTimelineItems.value.length,
  (length, previousLength) => {
    if (!length || activeTab.value !== 'timeline') return
    if (previousLength === 0 || timelineShouldStickToBottom.value) {
      scrollTimelineToBottom(previousLength === 0)
    }
  },
)

watch(
  () => activeTab.value,
  (tab) => {
    if (tab !== 'timeline' || !transcriptTimelineItems.value.length) return
    scrollTimelineToBottom()
  },
)

function openEditSession() {
  if (!session.value) return
  editSessionForm.session_title = session.value.session_title
  editSessionForm.status = session.value.status ?? 'not_started'
  editSessionForm.ended_at = session.value.ended_at ? new Date(session.value.ended_at) : null
  editSessionVisible.value = true
}

async function submitEditSession() {
  if (!editSessionFormRef.value) return
  await editSessionFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const updated = await updateAdminChatSession(sessionId, {
        session_title: editSessionForm.session_title,
        status: editSessionForm.status,
        ended_at: editSessionForm.ended_at ? editSessionForm.ended_at.toISOString() : null,
      })
      session.value = updated
      editSessionVisible.value = false
      ElMessage.success('会话信息已更新')
      await refreshAdminRealtimeData({ silent: true })
    } catch (e: any) {
      ElMessage.error(e?.message || '更新会话失败')
    }
  })
}

function openAddTranscript() {
  addTranscriptForm.speaker = ''
  addTranscriptForm.text = ''
  addTranscriptForm.start = ''
  addTranscriptForm.end = ''
  addTranscriptVisible.value = true
}

async function submitAddTranscript() {
  if (!addTranscriptFormRef.value || !session.value) return
  await addTranscriptFormRef.value.validate(async (valid) => {
    if (!valid || !session.value) return
    try {
      const payload: CreateAdminTranscriptPayload = {
        session_id: sessionId,
        group_id: session.value.group_id,
        text: addTranscriptForm.text,
        start: addTranscriptForm.start,
        end: addTranscriptForm.end,
        speaker: addTranscriptForm.speaker || null,
      }
      await createAdminTranscript(payload)
      ElMessage.success('转写记录已添加')
      addTranscriptVisible.value = false
      await refreshAdminRealtimeData({ silent: true })
    } catch (e: any) {
      ElMessage.error(e?.message || '添加转写失败')
    }
  })
}

function openEditTranscript(row: AdminTranscript) {
  editTranscriptForm.transcript_id = row.transcript_id
  editTranscriptForm.speaker = row.speaker ?? ''
  editTranscriptForm.text = row.text ?? ''
  editTranscriptForm.start = row.start ?? ''
  editTranscriptForm.end = row.end ?? ''
  editTranscriptVisible.value = true
}

async function submitEditTranscript() {
  if (!editTranscriptFormRef.value) return
  await editTranscriptFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload: UpdateAdminTranscriptPayload = {
        text: editTranscriptForm.text,
        start: editTranscriptForm.start,
        end: editTranscriptForm.end,
        speaker: editTranscriptForm.speaker || null,
      }
      await updateAdminTranscript(editTranscriptForm.transcript_id, payload)
      ElMessage.success('转写记录已更新')
      editTranscriptVisible.value = false
      await refreshAdminRealtimeData({ silent: true })
    } catch (e: any) {
      ElMessage.error(e?.message || '更新转写失败')
    }
  })
}

async function handleDeleteTranscript(row: AdminTranscript) {
  try {
    await ElMessageBox.confirm('确认删除这条转写记录吗？该操作不可恢复。', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await deleteAdminTranscript(row.transcript_id)
    ElMessage.success('转写记录已删除')
    if (transcripts.value.length === 1 && transcriptPage.value > 1) {
      transcriptPage.value -= 1
    }
    await refreshAdminRealtimeData({ silent: true })
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

async function handleBatchDeleteTranscripts() {
  if (selectedTranscripts.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除已选 ${selectedTranscripts.value.length} 条转写记录吗？该操作不可恢复。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  try {
    const ids = selectedTranscripts.value.map((item) => item.transcript_id)
    const res = await deleteAdminTranscriptsBatch(ids)
    ElMessage.success(`成功删除 ${res.deleted} 条转写记录`)
    transcriptTableRef.value?.clearSelection?.()
    await refreshAdminRealtimeData({ silent: true })
  } catch (e: any) {
    ElMessage.error(e?.message || '批量删除失败')
  }
}

async function handleDeleteSession() {
  if (!session.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除会话「${session.value.session_title}」吗？该操作不可恢复。`,
      '删除会话',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  try {
    await deleteAdminChatSession(sessionId)
    ElMessage.success('会话已删除')
    router.push('/admin/chat-sessions')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除会话失败')
  }
}

function handleTranscriptSelectionChange(rows: AdminTranscript[]) {
  selectedTranscripts.value = rows
}

function handleTranscriptPageChange(page: number) {
  void fetchTranscriptsPage(page)
}

function handleTranscriptPageSizeChange(size: number) {
  transcriptPageSize.value = size
  void fetchTranscriptsPage(1)
}

onMounted(() => {
  startElapsedTimer()
  void loadData()
})

onUnmounted(() => {
  stopPolling()
  stopElapsedTimer()
})
</script>

<template>
  <div class="admin-session-detail-page">
    <div class="admin-session-detail-back">
      <el-button link @click="router.push('/admin/chat-sessions')">← 返回会话列表</el-button>
    </div>

    <div v-if="pageLoading" class="admin-session-detail-loading">正在加载...</div>
    <div v-else-if="error" class="admin-session-detail-error">{{ error }}</div>

    <template v-else-if="session">
      <el-card class="admin-session-hero" shadow="never">
        <div class="admin-session-hero__header">
          <div class="admin-session-hero__title-wrap">
            <div class="admin-session-hero__title-row">
              <h1 class="admin-session-hero__title">{{ session.session_title }}</h1>
              <el-tag :type="statusType(session.status)" effect="light">
                {{ statusLabel(session.status) }}
              </el-tag>
            </div>
            <div class="admin-session-hero__sub">
              会话 ID：{{ session.id }}
            </div>
          </div>

          <div class="admin-session-hero__actions">
            <el-button :loading="refreshing" @click="refreshAdminRealtimeData()">手动刷新</el-button>
            <el-button type="primary" @click="openEditSession">编辑</el-button>
            <el-button type="danger" @click="handleDeleteSession">删除</el-button>
          </div>
        </div>

        <div class="admin-session-hero__grid">
          <section class="admin-session-panel">
            <div class="admin-session-panel__title">基本信息</div>
            <div class="admin-session-meta">
              <div class="admin-session-meta__item">
                <span class="admin-session-meta__label">群组</span>
                <span class="admin-session-meta__value">{{ session.group_name || '-' }}</span>
              </div>
              <div class="admin-session-meta__item">
                <span class="admin-session-meta__label">群组 ID</span>
                <span class="admin-session-meta__value">{{ session.group_id }}</span>
              </div>
              <div class="admin-session-meta__item">
                <span class="admin-session-meta__label">创建时间</span>
                <span class="admin-session-meta__value">{{ formatDisplayTime(session.created_at) }}</span>
              </div>
              <div class="admin-session-meta__item">
                <span class="admin-session-meta__label">最后更新</span>
                <span class="admin-session-meta__value">{{ formatDisplayTime(session.last_updated) }}</span>
              </div>
              <div class="admin-session-meta__item">
                <span class="admin-session-meta__label">开始时间</span>
                <span class="admin-session-meta__value">{{ formatDisplayTime(session.started_at) }}</span>
              </div>
              <div class="admin-session-meta__item">
                <span class="admin-session-meta__label">结束时间</span>
                <span class="admin-session-meta__value">{{ formatDisplayTime(session.ended_at) }}</span>
              </div>
            </div>
          </section>

          <section class="admin-session-panel admin-session-panel--status">
            <div class="admin-session-panel__title">实时状态</div>
            <div class="admin-session-status__headline">
              <span class="admin-session-status__dot" :class="`is-${session.status || 'not_started'}`"></span>
              <span class="admin-session-status__text">{{ statusLabel(session.status) }}</span>
              <span class="admin-session-status__duration">{{ sessionDurationText }}</span>
            </div>

            <div class="admin-session-status__stats">
              <div class="admin-session-stat">
                <span class="admin-session-stat__label">转录</span>
                <strong class="admin-session-stat__value">{{ allTranscripts.length }}</strong>
              </div>
              <div class="admin-session-stat">
                <span class="admin-session-stat__label">AI 分析</span>
                <strong class="admin-session-stat__value">{{ analysisTimeline.length }}</strong>
              </div>
              <div class="admin-session-stat">
                <span class="admin-session-stat__label">推送</span>
                <strong class="admin-session-stat__value">{{ pushLogs.length }}</strong>
              </div>
              <div class="admin-session-stat">
                <span class="admin-session-stat__label">信息缺口</span>
                <strong class="admin-session-stat__value">{{ infoGapButtons.length }}</strong>
              </div>
            </div>

            <div class="admin-session-status__foot">
              <span>最后刷新 {{ refreshText }}</span>
              <span v-if="session.status === 'ongoing'" class="admin-session-status__polling">进行中，每 10 秒自动刷新</span>
            </div>
          </section>
        </div>
      </el-card>

      <el-tabs v-model="activeTab" class="admin-session-tabs">
        <el-tab-pane label="讨论实录" name="timeline">
          <el-card shadow="never">
            <template #header>
              <div class="admin-tab-header">
                <div>
                  <div class="admin-tab-header__title">气泡式讨论实录</div>
                  <div class="admin-tab-header__sub">管理员可查看所有用户收到的 AI 建议</div>
                </div>
                <div class="admin-tab-header__actions">
                  <span class="admin-tab-header__time">最后刷新 {{ refreshText }}</span>
                  <el-button size="small" :loading="refreshing" @click="refreshAdminRealtimeData()">刷新</el-button>
                </div>
              </div>
            </template>

            <div v-if="transcriptTimelineLoading" class="admin-session-detail-loading">正在整理实录...</div>
            <div v-else-if="!transcriptTimelineItems.length" class="admin-session-detail-empty">暂无讨论实录</div>
            <div
              v-else
              ref="timelineScrollEl"
              class="timeline-scroll-shell"
              @scroll="handleTimelineScroll"
            >
              <div class="timeline-stream">
                <template v-for="item in transcriptTimelineItems" :key="item.key">
                  <div v-if="item.kind === 'transcript'" class="timeline-bubble timeline-bubble--transcript">
                    <div class="timeline-bubble__meta">
                      <span class="timeline-bubble__speaker">{{ formatTranscriptSpeakerLabel(item.transcript) }}</span>
                      <span class="timeline-bubble__time">{{ formatDisplayTime(item.transcript.created_at) }}</span>
                    </div>
                    <div class="timeline-bubble__content">{{ item.transcript.text || '-' }}</div>
                  </div>

                  <div v-else class="timeline-bubble timeline-bubble--push">
                    <div class="timeline-bubble__meta">
                      <span class="timeline-bubble__speaker">◈ AI 建议</span>
                      <span class="timeline-bubble__time">{{ formatClock(item.push.triggered_at) }}</span>
                      <span class="timeline-bubble__recipient">
                        → 发给：{{ item.push.target_user_name || item.push.target_user_id }}
                      </span>
                    </div>
                    <div class="timeline-bubble__content">{{ item.push.push_content || '-' }}</div>
                  </div>
                </template>
              </div>
            </div>
          </el-card>
        </el-tab-pane>

        <el-tab-pane label="AI 分析" name="analysis">
          <div class="analysis-grid">
            <el-card shadow="never">
              <template #header>
                <div class="admin-tab-header">
                  <div class="admin-tab-header__title">讨论摘要历史</div>
                </div>
              </template>
              <div v-if="!discussionSummaries.length" class="admin-session-detail-empty">暂无摘要历史</div>
              <div v-else class="analysis-timeline">
                <div v-for="item in discussionSummaries" :key="item.id" class="analysis-card analysis-card--summary">
                  <div class="analysis-card__head">
                    <strong>v{{ item.version }}</strong>
                    <span>{{ formatClock(item.created_at) }}</span>
                  </div>
                  <div class="analysis-card__window">
                    覆盖窗口：{{ formatDisplayTime(item.window_start) }} - {{ formatDisplayTime(item.window_end) }}
                  </div>
                  <div class="analysis-card__body">{{ item.content }}</div>
                </div>
              </div>
            </el-card>

            <el-card shadow="never">
              <template #header>
                <div class="admin-tab-header">
                  <div class="admin-tab-header__title">Agent 分析轮次时间线</div>
                </div>
              </template>
              <div v-if="!analysisTimeline.length" class="admin-session-detail-empty">暂无分析记录</div>
              <div v-else class="analysis-timeline">
                <div
                  v-for="item in analysisTimeline"
                  :key="item.key"
                  class="analysis-card"
                  :class="item.kind === 'reasoning' ? 'analysis-card--reasoning' : 'analysis-card--summary'"
                >
                  <div class="analysis-card__head">
                    <strong>{{ item.title }}<template v-if="item.summaryVersion"> v{{ item.summaryVersion }}</template></strong>
                    <span>{{ formatClock(item.at || item.windowEnd) }}</span>
                  </div>
                  <div class="analysis-card__window" v-if="item.windowStart || item.windowEnd">
                    覆盖窗口：{{ formatDisplayTime(item.windowStart) }} - {{ formatDisplayTime(item.windowEnd) }}
                  </div>
                  <div class="analysis-card__body" v-if="item.content">{{ item.content }}</div>
                  <div class="analysis-card__meta" v-if="item.keywords.length">
                    信息缺口：{{ item.keywords.join('、') }}
                  </div>
                  <div class="analysis-card__meta" v-if="item.pushes.length">
                    推送建议：{{ item.pushes.length }} 条
                    <template v-if="item.recipients.length">
                      （{{ item.recipients.join('、') }}）
                    </template>
                  </div>
                </div>
              </div>
            </el-card>

            <el-card shadow="never">
              <template #header>
                <div class="admin-tab-header">
                  <div class="admin-tab-header__title">信息缺口关键词</div>
                </div>
              </template>
              <div v-if="!infoGapButtons.length" class="admin-session-detail-empty">暂无信息缺口关键词</div>
              <div v-else class="keyword-cloud">
                <div
                  v-for="item in infoGapButtons"
                  :key="item.id"
                  class="keyword-pill"
                  :class="{ 'is-clicked': clickedKeywordIds.has(item.id) }"
                >
                  <span>{{ item.keyword }}</span>
                  <span class="keyword-pill__meta">
                    {{ item.user_name || item.user_id }}
                    <template v-if="clickedKeywordIds.has(item.id)"> · 已点击</template>
                  </span>
                </div>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane label="原始数据" name="raw">
          <div class="raw-grid">
            <el-card shadow="never">
              <template #header>
                <div class="admin-session-detail-transcripts-header">
                  <span>转写记录（{{ transcriptTotal }}）</span>
                  <div class="admin-session-detail-transcripts-toolbar">
                    <el-button
                      type="danger"
                      size="small"
                      :disabled="selectedTranscripts.length === 0"
                      @click="handleBatchDeleteTranscripts"
                    >
                      {{ selectedTranscripts.length > 0 ? `批量删除 (${selectedTranscripts.length})` : '批量删除' }}
                    </el-button>
                    <el-button type="primary" size="small" @click="openAddTranscript">新增转写</el-button>
                  </div>
                </div>
              </template>

              <div v-if="!transcripts.length && !transcriptLoading" class="admin-session-detail-empty">
                暂无转写记录
              </div>

              <el-table
                v-else
                ref="transcriptTableRef"
                :data="transcripts"
                v-loading="transcriptLoading"
                border
                size="small"
                style="width: 100%"
                @selection-change="handleTranscriptSelectionChange"
              >
                <el-table-column type="selection" width="44" />
                <el-table-column prop="transcript_id" label="ID" min-width="200" show-overflow-tooltip />
                <el-table-column prop="speaker" label="说话人" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">{{ formatTranscriptSpeakerLabel(row) }}</template>
                </el-table-column>
                <el-table-column prop="text" label="内容" min-width="240" show-overflow-tooltip />
                <el-table-column prop="start" label="开始" min-width="100" show-overflow-tooltip />
                <el-table-column prop="end" label="结束" min-width="100" show-overflow-tooltip />
                <el-table-column label="是否已编辑" min-width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.is_edited ? 'warning' : 'info'" size="small">
                      {{ row.is_edited ? '已编辑' : '原始' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="创建时间" min-width="160" show-overflow-tooltip>
                  <template #default="{ row }">{{ formatDisplayTime(row.created_at) }}</template>
                </el-table-column>
                <el-table-column label="操作" min-width="140" fixed="right">
                  <template #default="{ row }">
                    <el-button type="primary" link size="small" @click="openEditTranscript(row)">编辑</el-button>
                    <el-button type="danger" link size="small" @click="handleDeleteTranscript(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>

              <div v-if="transcriptTotal > transcriptPageSize" class="admin-session-detail-pagination">
                <el-pagination
                  v-model:current-page="transcriptPage"
                  v-model:page-size="transcriptPageSize"
                  :total="transcriptTotal"
                  :page-sizes="[10, 20, 50]"
                  layout="total, sizes, prev, pager, next"
                  @current-change="handleTranscriptPageChange"
                  @size-change="handleTranscriptPageSizeChange"
                />
              </div>
            </el-card>

            <el-card shadow="never">
              <template #header>
                <div class="admin-tab-header">
                  <div class="admin-tab-header__title">Push Logs</div>
                </div>
              </template>
              <div v-if="!pushLogs.length" class="admin-session-detail-empty">暂无推送日志</div>
              <el-table v-else :data="pushLogs" border size="small" style="width: 100%">
                <el-table-column prop="id" label="ID" min-width="180" show-overflow-tooltip />
                <el-table-column label="收件人" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.target_user_name || row.target_user_id }}</template>
                </el-table-column>
                <el-table-column prop="state_type" label="状态类型" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">{{ stateTypeLabel(row.state_type) }}</template>
                </el-table-column>
                <el-table-column prop="push_content" label="推送内容" min-width="280" show-overflow-tooltip />
                <el-table-column prop="push_channel" label="渠道" min-width="90" />
                <el-table-column prop="delivery_status" label="投递状态" min-width="100" />
                <el-table-column label="触发时间" min-width="160" show-overflow-tooltip>
                  <template #default="{ row }">{{ formatDisplayTime(row.triggered_at) }}</template>
                </el-table-column>
                <el-table-column label="送达时间" min-width="160" show-overflow-tooltip>
                  <template #default="{ row }">{{ formatDisplayTime(row.delivered_at) }}</template>
                </el-table-column>
              </el-table>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>

    <el-dialog v-model="editSessionVisible" title="编辑会话" width="480px">
      <el-form ref="editSessionFormRef" :model="editSessionForm" :rules="editSessionRules" label-width="80px">
        <el-form-item label="会话标题" prop="session_title">
          <el-input v-model="editSessionForm.session_title" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editSessionForm.status" style="width: 100%">
            <el-option label="未开始" value="not_started" />
            <el-option label="进行中" value="ongoing" />
            <el-option label="已结束" value="ended" />
          </el-select>
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker
            v-model="editSessionForm.ended_at"
            type="datetime"
            placeholder="留空则不修改"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editSessionVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditSession">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="addTranscriptVisible" title="新增转写" width="480px">
      <el-form ref="addTranscriptFormRef" :model="addTranscriptForm" :rules="addTranscriptRules" label-width="80px">
        <el-form-item label="说话人">
          <el-input v-model="addTranscriptForm.speaker" placeholder="可选" />
        </el-form-item>
        <el-form-item label="内容" prop="text">
          <el-input v-model="addTranscriptForm.text" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="开始时间" prop="start">
          <el-input v-model="addTranscriptForm.start" placeholder="如 00:00:01.000" />
        </el-form-item>
        <el-form-item label="结束时间" prop="end">
          <el-input v-model="addTranscriptForm.end" placeholder="如 00:00:05.000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addTranscriptVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAddTranscript">添加</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editTranscriptVisible" title="编辑转写" width="480px">
      <el-form ref="editTranscriptFormRef" :model="editTranscriptForm" :rules="editTranscriptRules" label-width="80px">
        <el-form-item label="说话人">
          <el-input v-model="editTranscriptForm.speaker" placeholder="可选" />
        </el-form-item>
        <el-form-item label="内容" prop="text">
          <el-input v-model="editTranscriptForm.text" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="开始时间" prop="start">
          <el-input v-model="editTranscriptForm.start" />
        </el-form-item>
        <el-form-item label="结束时间" prop="end">
          <el-input v-model="editTranscriptForm.end" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editTranscriptVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditTranscript">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-session-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-session-detail-back {
  margin-bottom: 4px;
}

.admin-session-detail-loading {
  font-size: 13px;
  color: #6b7280;
  padding: 16px 0;
}

.admin-session-detail-error {
  padding: 14px 18px;
  border-radius: 8px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 14px;
}

.admin-session-hero :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.admin-session-hero__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.admin-session-hero__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.admin-session-hero__title {
  margin: 0;
  font-size: 28px;
  line-height: 1.2;
  color: #111827;
}

.admin-session-hero__sub {
  margin-top: 4px;
  font-size: 14px;
  color: #6b7280;
}

.admin-session-hero__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.admin-session-hero__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(250px, 320px);
  gap: 12px;
}

.admin-session-panel {
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 10px;
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
}

.admin-session-panel__title {
  font-size: 17px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 8px;
}

.admin-session-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.admin-session-meta__item {
  min-height: 54px;
  padding: 6px 10px;
  border-radius: 10px;
  background: #f9fafb;
  border: 1px solid #eef2f7;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}

.admin-session-meta__label {
  font-size: 11px;
  font-weight: 500;
  color: #6b7280;
  line-height: 1.1;
}

.admin-session-meta__value {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.15;
  color: #111827;
  word-break: break-word;
}

.admin-session-panel--status {
  background: linear-gradient(180deg, #fffaf0 0%, #fff 100%);
}

.admin-session-status__headline {
  display: flex;
  align-items: center;
  gap: 8px 10px;
  flex-wrap: wrap;
  font-size: 15px;
  color: #111827;
  margin-bottom: 0;
}

.admin-session-status__dot {
  width: 11px;
  height: 11px;
  border-radius: 999px;
  background: #f59e0b;
  box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.14);
}

.admin-session-status__dot.is-ongoing {
  background: #10b981;
  box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.14);
}

.admin-session-status__dot.is-ended {
  background: #94a3b8;
  box-shadow: 0 0 0 4px rgba(148, 163, 184, 0.14);
}

.admin-session-status__text {
  font-size: 15px;
  font-weight: 700;
}

.admin-session-status__duration {
  font-size: 16px;
  font-weight: 700;
  color: #0f766e;
  margin-left: auto;
}

.admin-session-status__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.admin-session-stat {
  min-height: 56px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #fde68a;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.admin-session-stat__label {
  color: #6b7280;
  font-size: 12px;
  font-weight: 500;
}

.admin-session-stat__value {
  font-size: 16px;
  line-height: 1;
  color: #111827;
}

.admin-session-status__foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
  font-size: 12px;
  color: #6b7280;
}

.admin-session-status__polling {
  color: #b45309;
}

.admin-session-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}

.admin-tab-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.admin-tab-header__title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.admin-tab-header__sub,
.admin-tab-header__time {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
}

.admin-tab-header__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.timeline-scroll-shell {
  max-height: min(70vh, 760px);
  min-height: 360px;
  overflow-y: auto;
  padding-right: 6px;
}

.timeline-stream {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.timeline-bubble {
  max-width: 86%;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid #e5e7eb;
  background: #fff;
}

.timeline-bubble--transcript {
  align-self: flex-start;
  background: #f9fafb;
}

.timeline-bubble--push {
  align-self: center;
  width: min(100%, 720px);
  background: #fff7ed;
  border-color: #fdba74;
  box-shadow: 0 10px 20px rgba(249, 115, 22, 0.08);
}

.timeline-bubble__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 10px;
  align-items: center;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 8px;
}

.timeline-bubble__speaker {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}

.timeline-bubble__recipient {
  color: #c2410c;
}

.timeline-bubble__content {
  font-size: 14px;
  line-height: 1.75;
  color: #1f2937;
  white-space: pre-wrap;
  word-break: break-word;
}

.analysis-grid,
.raw-grid {
  display: grid;
  gap: 16px;
}

.analysis-timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.analysis-card {
  border-left: 4px solid #fb923c;
  background: #fff7ed;
  border-radius: 12px;
  padding: 14px 16px;
}

.analysis-card--summary {
  border-left-color: #60a5fa;
  background: #eff6ff;
}

.analysis-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 14px;
  color: #111827;
}

.analysis-card__window,
.analysis-card__meta {
  margin-top: 8px;
  font-size: 13px;
  color: #4b5563;
}

.analysis-card__body {
  margin-top: 10px;
  font-size: 14px;
  color: #1f2937;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.keyword-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.keyword-pill {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 999px;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
  color: #111827;
}

.keyword-pill.is-clicked {
  background: #ecfdf5;
  border-color: #6ee7b7;
}

.keyword-pill__meta {
  font-size: 11px;
  color: #6b7280;
}

.admin-session-detail-transcripts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.admin-session-detail-transcripts-toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.admin-session-detail-empty {
  padding: 24px 0;
  color: #9ca3af;
  text-align: center;
  font-size: 13px;
}

.admin-session-detail-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (max-width: 980px) {
  .admin-session-hero__header,
  .admin-tab-header,
  .admin-session-detail-transcripts-header {
    flex-direction: column;
    align-items: stretch;
  }

  .admin-session-hero__grid,
  .admin-session-meta,
  .admin-session-status__stats {
    grid-template-columns: 1fr;
  }

  .admin-session-status__duration {
    margin-left: 0;
  }

  .timeline-bubble {
    max-width: 100%;
  }

  .timeline-scroll-shell {
    max-height: min(62vh, 560px);
    min-height: 300px;
    padding-right: 2px;
  }
}
</style>
