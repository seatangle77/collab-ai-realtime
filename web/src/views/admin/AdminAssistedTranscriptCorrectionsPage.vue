<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import RecordingFinalVersionPanel from '../../components/admin/RecordingFinalVersionPanel.vue'
import { formatDateTimeToCST } from '../../utils/datetime'
import {
  getSessionUtterances,
  type UtteranceOut,
} from '../../api/admin/coi-transcript-coding'
import {
  createMergedTranscriptCorrection,
  deleteMergedTranscriptCorrection,
  deleteTranscriptCorrection,
  getTranscriptAlignmentRun,
  listCorrectableTranscripts,
  listTranscriptCorrectionGroups,
  listTranscriptCorrectionSessions,
  resolveTranscriptAlignmentBoundary,
  saveTranscriptAlignmentRun,
  saveTranscriptCorrection,
  startTranscriptAlignmentRun,
  updateMergedTranscriptCorrection,
  type AiAlignmentMatch,
  type AlignmentRun,
  type AssistedCondition,
  type CorrectableTranscript,
  type CorrectionStatus,
  type TranscriptCorrectionGroup,
  type TranscriptCorrectionSession,
} from '../../api/admin/transcript-corrections'

const showLegacyEditor = ref(false)

const CONDITION_LABELS: Record<AssistedCondition, string> = {
  glasses: '眼镜',
  app_notification: 'App 通知',
}

interface AlignmentAnchor {
  sessionId: string
  transcriptId: string
  transcriptRelativeSeconds: number
  referenceOrder: number
  referenceStartTime: number
}

type TranscriptContentView = 'latest' | 'original'

const REFERENCE_MATCH_WINDOW_SECONDS = 8
const REFERENCE_MAX_DISTANCE_SECONDS = 15
const ALIGNMENT_POLL_INTERVAL_MS = 1200

const groups = ref<TranscriptCorrectionGroup[]>([])
const sessions = ref<TranscriptCorrectionSession[]>([])
const transcripts = ref<CorrectableTranscript[]>([])
const referenceUtterances = ref<UtteranceOut[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const selectedTranscriptId = ref('')
const loadedGroupId = ref('')
const loadedSessionId = ref('')
const loadedCondition = ref<AssistedCondition | ''>('')
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const loadingTranscripts = ref(false)
const loadingReferences = ref(false)
const saving = ref(false)
const page = ref(1)
const pageSize = ref(500)
const total = ref(0)
const dirty = ref(false)
const mergeEditing = ref(false)
const mergeSelectionIds = ref<string[]>([])
const selectedReferenceOrder = ref<number | null>(null)
const alignedReferenceOrder = ref<number | null>(null)
const alignedReferenceDistanceSeconds = ref<number | null>(null)
const alignmentAnchor = ref<AlignmentAnchor | null>(null)
const alignmentRun = ref<AlignmentRun | null>(null)
const transcriptContentView = ref<TranscriptContentView>('latest')
const startingAlignmentRun = ref(false)
const savingAlignmentRun = ref(false)
const resolvingAiMatchId = ref('')
const focusedAiMatchId = ref('')
const referenceElements = new Map<number, HTMLElement>()
let alignmentPollTimer: ReturnType<typeof setTimeout> | null = null

const filters = reactive({
  condition: '' as AssistedCondition | '',
  correction_status: '' as CorrectionStatus | '',
  speaker: '',
  keyword: '',
})

const form = reactive({
  corrected_text: '',
  correction_reason: '',
  corrected_by: '',
})

const visibleGroups = computed(() =>
  groups.value.filter(group => !filters.condition || group.condition === filters.condition),
)
const currentSession = computed(() =>
  sessions.value.find(session => session.session_id === selectedSessionId.value) ?? null,
)

const displayTranscripts = computed<CorrectableTranscript[]>(() => {
  const emittedCorrections = new Set<string>()
  return transcripts.value.flatMap((source) => {
    const transcript = source.correction_reason === '录音完整修订'
      ? { ...source, speaker_name: '录音修订（说话人见最终版本）', speaker_user_id: null }
      : source
    if (!transcript.is_merged || !transcript.correction_id) return [transcript]
    if (emittedCorrections.has(transcript.correction_id)) return []
    emittedCorrections.add(transcript.correction_id)
    const sourceIds = new Set(transcript.source_transcript_ids)
    const members = transcripts.value.filter(item => sourceIds.has(item.transcript_id))
    const speakerNames = [...new Set(members.map(item => item.speaker_name))]
    return [{
      ...transcript,
      speaker_name: transcript.correction_reason === '录音完整修订' ? transcript.speaker_name : speakerNames.join(' / '),
      original_text: members.map(item => item.original_text?.trim()).filter(Boolean).join(' '),
      start: members[0]?.start ?? transcript.start,
      end: members[members.length - 1]?.end ?? transcript.end,
    }]
  })
})
const transcriptListItems = computed(() =>
  transcriptContentView.value === 'original' ? transcripts.value : displayTranscripts.value,
)
const finalTranscripts = computed(() => displayTranscripts.value.filter(item => !item.final_excluded))
const excludedFinalTranscripts = computed(() => displayTranscripts.value.filter(item => item.final_excluded))
const selectedTranscript = computed(() =>
  transcriptListItems.value.find(item => item.transcript_id === selectedTranscriptId.value) ?? null,
)
const selectedReference = computed(() =>
  referenceUtterances.value.find(item => item.order_index === selectedReferenceOrder.value) ?? null,
)
const selectedTranscriptRelativeSeconds = computed(() => {
  const transcript = selectedTranscript.value
  return transcript ? transcriptRelativeSeconds(transcript) : null
})
const expectedReferenceSeconds = computed(() => {
  const anchor = alignmentAnchor.value
  const transcriptSeconds = selectedTranscriptRelativeSeconds.value
  if (!anchor || transcriptSeconds == null) return null
  return anchor.referenceStartTime + (transcriptSeconds - anchor.transcriptRelativeSeconds)
})
const referenceCandidateOrders = computed(() => {
  const expectedSeconds = expectedReferenceSeconds.value
  if (expectedSeconds == null) return new Set<number>()
  return new Set(
    referenceUtterances.value
      .filter(item =>
        item.start_time != null
        && Math.abs(item.start_time - expectedSeconds) <= REFERENCE_MATCH_WINDOW_SECONDS,
      )
      .map(item => item.order_index),
  )
})
const canSetAlignmentAnchor = computed(() =>
  selectedTranscriptRelativeSeconds.value != null && selectedReference.value?.start_time != null,
)
const alignmentOffsetSeconds = computed(() => {
  const anchor = alignmentAnchor.value
  return anchor ? anchor.referenceStartTime - anchor.transcriptRelativeSeconds : null
})
const uncorrectedCount = computed(() => {
  const session = currentSession.value
  return session ? session.transcript_count - session.corrected_count : 0
})
const mergeSelectionSet = computed(() => new Set(mergeSelectionIds.value))
const selectedMergeTranscripts = computed(() =>
  transcripts.value.filter(item => mergeSelectionSet.value.has(item.transcript_id)),
)
const selectedEditingSourceIds = computed(() => {
  if (mergeEditing.value) return [...mergeSelectionIds.value]
  return selectedTranscript.value?.source_transcript_ids?.length
    ? selectedTranscript.value.source_transcript_ids
    : selectedTranscript.value ? [selectedTranscript.value.transcript_id] : []
})
const editingSourceTranscripts = computed(() => {
  const ids = new Set(selectedEditingSourceIds.value)
  return transcripts.value.filter(item => ids.has(item.transcript_id))
})
const alignmentRunInProgress = computed(() =>
  alignmentRun.value?.status === 'queued' || alignmentRun.value?.status === 'running',
)
const alignmentProgress = computed(() => {
  const run = alignmentRun.value
  if (!run?.total_chunks) return 0
  return Math.min(run.status === 'running' || run.status === 'queued' ? 99 : 100, Math.round(run.completed_chunks / run.total_chunks * 100))
})
const focusedAiMatch = computed(() =>
  alignmentRun.value?.matches.find(item => item.match_id === focusedAiMatchId.value) ?? null,
)
const focusedAiTranscriptIds = computed(() => new Set(focusedAiMatch.value?.transcript_ids ?? []))
const focusedAiReferenceOrders = computed(() => new Set(focusedAiMatch.value?.reference_orders ?? []))
const aiMatchByTranscriptId = computed(() => {
  const byId = new Map<string, AiAlignmentMatch>()
  for (const match of alignmentRun.value?.matches ?? []) {
    for (const transcriptId of match.transcript_ids) byId.set(transcriptId, match)
  }
  return byId
})
const outOfScopeTranscriptIds = computed(() =>
  new Set(alignmentRun.value?.out_of_scope_transcript_ids ?? []),
)
const unmatchedTranscriptIds = computed(() => new Set(alignmentRun.value?.unmatched_transcript_ids ?? []))
const unmatchedReferenceOrders = computed(() => new Set(alignmentRun.value?.unmatched_reference_orders ?? []))
const unsavedOrganizedMatches = computed(() =>
  (alignmentRun.value?.matches ?? []).filter(item => !item.saved),
)
const reviewRequiredCount = computed(() =>
  (alignmentRun.value?.matches ?? []).filter(item => item.review_required && !item.saved).length,
)
const organizedTranscriptCount = computed(() =>
  alignmentRun.value?.summary.organized_transcripts ?? 0,
)
const targetTranscriptCount = computed(() =>
  alignmentRun.value?.summary.total_target_transcripts ?? 0,
)
function isAiSavedCorrection(item: CorrectableTranscript): boolean {
  return item.is_corrected && (item.correction_reason ?? '').startsWith('AI 整场匹配')
}
const manuallyCorrectedFinalCount = computed(() =>
  finalTranscripts.value.filter(item => item.is_corrected && !isAiSavedCorrection(item)).length,
)
const aiCorrectedFinalCount = computed(() =>
  finalTranscripts.value.filter(item => isAiSavedCorrection(item)).length,
)
const originalFinalCount = computed(() =>
  finalTranscripts.value.filter(item => !item.is_corrected).length,
)
const hasSavedCorrections = computed(() =>
  finalTranscripts.value.some(item => item.is_corrected),
)
const hasSessionCorrections = computed(() =>
  (currentSession.value?.corrected_count ?? 0) > 0,
)
const historicalRerunReady = computed(() =>
  !hasSessionCorrections.value || transcriptContentView.value === 'original',
)
const hasPreparedAlignment = computed(() =>
  Boolean(
    alignmentRun.value
    && !alignmentRunInProgress.value
    && alignmentRun.value.status !== 'failed'
    && unsavedOrganizedMatches.value.length,
  ),
)
const showFinalVersion = computed(() =>
  !alignmentRunInProgress.value && !hasPreparedAlignment.value && hasSavedCorrections.value,
)
const showAlignmentPanel = computed(() => hasPreparedAlignment.value || showFinalVersion.value)

function aiMatchForTranscript(transcriptId: string): AiAlignmentMatch | null {
  return aiMatchByTranscriptId.value.get(transcriptId) ?? null
}

function isFirstVisibleTranscriptInMatch(transcriptId: string, match: AiAlignmentMatch): boolean {
  const visibleIds = new Set(transcriptListItems.value.map(item => item.transcript_id))
  return match.transcript_ids.find(id => visibleIds.has(id)) === transcriptId
}

function canMergeAiMatch(match: AiAlignmentMatch, direction: 'previous' | 'next'): boolean {
  const matches = alignmentRun.value?.matches ?? []
  const index = matches.findIndex(item => item.match_id === match.match_id)
  return direction === 'previous' ? index > 0 : index >= 0 && index < matches.length - 1
}

const timeMatchedTranscriptIds = computed(() => {
  const anchor = alignmentAnchor.value
  const reference = selectedReference.value
  if (!anchor || reference?.start_time == null) return new Set<string>()
  const referenceIndex = referenceUtterances.value.findIndex(
    item => item.order_index === reference.order_index,
  )
  const nextReference = referenceUtterances.value
    .slice(referenceIndex + 1)
    .find(item => item.start_time != null)
  const referenceEnd = nextReference?.start_time ?? reference.start_time + 12
  const liveStart = anchor.transcriptRelativeSeconds
    + (reference.start_time - anchor.referenceStartTime)
  const liveEnd = anchor.transcriptRelativeSeconds
    + (referenceEnd - anchor.referenceStartTime)
  return new Set(
    transcripts.value
      .filter((item) => {
        if (item.is_corrected) return false
        const seconds = transcriptRelativeSeconds(item)
        return seconds != null && seconds >= liveStart - 1 && seconds < liveEnd + 1
      })
      .map(item => item.transcript_id),
  )
})

function naturalSortGroups(items: TranscriptCorrectionGroup[]) {
  return items.sort((left, right) =>
    left.group_name.localeCompare(right.group_name, 'zh-CN', {
      numeric: true,
      sensitivity: 'base',
    }),
  )
}

function formatRelativeTime(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return '--:--'
  const safeSeconds = Math.max(0, seconds)
  const minutes = Math.floor(safeSeconds / 60)
  const remainder = (safeSeconds % 60).toFixed(1).padStart(4, '0')
  return `${minutes}:${remainder}`
}

function formatSignedSeconds(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return '--'
  return `${seconds >= 0 ? '+' : ''}${seconds.toFixed(1)} 秒`
}

function alignmentStorageKey(sessionId: string): string {
  return `assisted-transcript-alignment:${sessionId}`
}

function alignmentRunStorageKey(sessionId: string): string {
  return `assisted-transcript-ai-run:v2:${sessionId}`
}

function stopAlignmentPolling() {
  if (alignmentPollTimer) clearTimeout(alignmentPollTimer)
  alignmentPollTimer = null
}

function clearAlignmentRun(removeStored = true) {
  stopAlignmentPolling()
  if (removeStored && selectedSessionId.value) {
    localStorage.removeItem(alignmentRunStorageKey(selectedSessionId.value))
  }
  alignmentRun.value = null
  focusedAiMatchId.value = ''
}

function applyAlignmentRun(run: AlignmentRun) {
  alignmentRun.value = run
}

async function pollAlignmentRun(runId: string) {
  stopAlignmentPolling()
  try {
    const previousStatus = alignmentRun.value?.status
    const run = await getTranscriptAlignmentRun(runId)
    if (run.session_id !== selectedSessionId.value) return
    const completedNow = (
      run.status === 'completed' || run.status === 'completed_with_errors'
    ) && previousStatus !== 'completed' && previousStatus !== 'completed_with_errors'
    applyAlignmentRun(run)
    if (run.status === 'queued' || run.status === 'running') {
      alignmentPollTimer = setTimeout(() => pollAlignmentRun(runId), ALIGNMENT_POLL_INTERVAL_MS)
    } else if (run.status === 'failed') {
      ElMessage.error(run.message || 'AI 匹配失败')
    } else if (run.status === 'completed_with_errors') {
      ElMessage.warning(run.message || '部分内容需要确认')
    } else if (completedNow) {
      ElMessage.success(`AI整理完成，可以直接保存`)
    }
  } catch (error: any) {
    const message = String(error?.message ?? '')
    if (message.includes('AI 匹配结果不存在或已过期')) {
      clearAlignmentRun(true)
      ElMessage.info('此前的 AI 整理预览已过期，已显示数据库中保存的最终版本')
      return
    }
    ElMessage.error(error?.message || '读取 AI 匹配进度失败')
  }
}

async function restoreAlignmentRun(sessionId: string) {
  clearAlignmentRun(false)
  if (!sessionId || !alignmentAnchor.value) return
  const runId = localStorage.getItem(alignmentRunStorageKey(sessionId))
  if (!runId) return
  await pollAlignmentRun(runId)
}

function restoreAlignmentAnchor(sessionId: string) {
  alignmentAnchor.value = null
  alignedReferenceOrder.value = null
  alignedReferenceDistanceSeconds.value = null
  if (!sessionId) return
  try {
    const raw = localStorage.getItem(alignmentStorageKey(sessionId))
    if (!raw) return
    const parsed = JSON.parse(raw) as Partial<AlignmentAnchor>
    if (
      parsed.sessionId === sessionId
      && typeof parsed.transcriptId === 'string'
      && typeof parsed.transcriptRelativeSeconds === 'number'
      && typeof parsed.referenceOrder === 'number'
      && typeof parsed.referenceStartTime === 'number'
    ) {
      alignmentAnchor.value = parsed as AlignmentAnchor
    }
  } catch {
    localStorage.removeItem(alignmentStorageKey(sessionId))
  }
}

function setReferenceElement(orderIndex: number, element: unknown) {
  if (element instanceof HTMLElement) referenceElements.set(orderIndex, element)
  else referenceElements.delete(orderIndex)
}

function transcriptRelativeSeconds(transcript: CorrectableTranscript): number | null {
  const sessionStartedAt = currentSession.value?.started_at ?? currentSession.value?.created_at
  if (!transcript.start || !sessionStartedAt) return null
  const transcriptMs = Date.parse(transcript.start)
  const sessionMs = Date.parse(sessionStartedAt)
  if (!Number.isFinite(transcriptMs) || !Number.isFinite(sessionMs)) return null
  return (transcriptMs - sessionMs) / 1000
}

async function locateAlignedReference(transcript: CorrectableTranscript) {
  const anchor = alignmentAnchor.value
  const relativeSeconds = transcriptRelativeSeconds(transcript)
  if (!anchor || relativeSeconds == null) {
    alignedReferenceOrder.value = null
    alignedReferenceDistanceSeconds.value = null
    return
  }
  const expectedSeconds = anchor.referenceStartTime + (relativeSeconds - anchor.transcriptRelativeSeconds)
  const timed = referenceUtterances.value.filter(item => item.start_time != null)
  if (!timed.length) return
  const closest = timed.reduce((best, item) =>
    Math.abs((item.start_time ?? 0) - expectedSeconds)
      < Math.abs((best.start_time ?? 0) - expectedSeconds)
      ? item
      : best,
  )
  const distance = Math.abs((closest.start_time ?? 0) - expectedSeconds)
  alignedReferenceOrder.value = closest.order_index
  alignedReferenceDistanceSeconds.value = distance
  selectedReferenceOrder.value = distance <= REFERENCE_MAX_DISTANCE_SECONDS
    ? closest.order_index
    : null
  await nextTick()
  referenceElements.get(closest.order_index)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

async function setAlignmentAnchor() {
  const transcript = selectedTranscript.value
  const reference = selectedReference.value
  const transcriptSeconds = selectedTranscriptRelativeSeconds.value
  if (!transcript || !reference || transcriptSeconds == null || reference.start_time == null) {
    ElMessage.warning('请先在中间选择一条实时转写，再在左侧选择对应的录音重转译')
    return
  }
  clearAlignmentRun()
  const anchor: AlignmentAnchor = {
    sessionId: selectedSessionId.value,
    transcriptId: transcript.transcript_id,
    transcriptRelativeSeconds: transcriptSeconds,
    referenceOrder: reference.order_index,
    referenceStartTime: reference.start_time,
  }
  alignmentAnchor.value = anchor
  localStorage.setItem(alignmentStorageKey(anchor.sessionId), JSON.stringify(anchor))
  await locateAlignedReference(transcript)
  ElMessage.success('对齐起点已保存，之后选择实时转写时将自动定位录音重转译')
}

function clearAlignmentAnchor() {
  if (selectedSessionId.value) {
    localStorage.removeItem(alignmentStorageKey(selectedSessionId.value))
  }
  alignmentAnchor.value = null
  clearAlignmentRun()
  alignedReferenceOrder.value = null
  alignedReferenceDistanceSeconds.value = null
  ElMessage.success('已清除当前会话的对齐起点')
}

async function loadReferenceUtterances(sessionId: string) {
  referenceUtterances.value = []
  selectedReferenceOrder.value = null
  referenceElements.clear()
  if (!sessionId) return
  loadingReferences.value = true
  try {
    const response = await getSessionUtterances(sessionId)
    if (sessionId !== selectedSessionId.value) return
    referenceUtterances.value = response.utterances
    if (selectedTranscript.value) await locateAlignedReference(selectedTranscript.value)
  } catch (error: any) {
    ElMessage.error(error?.message || '加载录音重转译对照失败')
  } finally {
    loadingReferences.value = false
  }
}

function fillForm(transcript: CorrectableTranscript | null) {
  form.corrected_text = transcript?.effective_text ?? ''
  form.correction_reason = transcript?.correction_reason ?? ''
  form.corrected_by = transcript?.corrected_by ?? ''
  dirty.value = false
}

function resetMergeEditing() {
  mergeEditing.value = false
  mergeSelectionIds.value = []
}

async function confirmDiscard(): Promise<boolean> {
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm(
      '当前转写有尚未保存的修改，继续后这些修改会丢失。',
      '离开当前转写',
      { type: 'warning', confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' },
    )
    return true
  } catch {
    return false
  }
}

async function loadGroups() {
  loadingGroups.value = true
  try {
    groups.value = naturalSortGroups(await listTranscriptCorrectionGroups())
  } catch (error: any) {
    ElMessage.error(error?.message || '加载辅助组失败')
  } finally {
    loadingGroups.value = false
  }
}

async function loadSessions(groupId: string, selectFirst = true) {
  clearAlignmentRun(false)
  restoreAlignmentAnchor('')
  transcriptContentView.value = 'latest'
  sessions.value = []
  selectedSessionId.value = ''
  loadedSessionId.value = ''
  transcripts.value = []
  referenceUtterances.value = []
  selectedReferenceOrder.value = null
  selectedTranscriptId.value = ''
  resetMergeEditing()
  fillForm(null)
  if (!groupId) return
  loadingSessions.value = true
  try {
    sessions.value = await listTranscriptCorrectionSessions(groupId)
    loadedGroupId.value = groupId
    if (selectFirst && sessions.value[0]) {
      selectedSessionId.value = sessions.value[0].session_id
      loadedSessionId.value = selectedSessionId.value
      restoreAlignmentAnchor(selectedSessionId.value)
      await Promise.all([
        loadTranscripts(true),
        loadReferenceUtterances(selectedSessionId.value),
      ])
      await restoreAlignmentRun(selectedSessionId.value)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

let transcriptLoadRequest = 0
async function loadTranscripts(selectFirst = true) {
  const request = ++transcriptLoadRequest
  const sessionId = selectedSessionId.value
  if (!selectedSessionId.value) return
  loadingTranscripts.value = true
  try {
    const response = await listCorrectableTranscripts(sessionId, {
      page: page.value,
      page_size: pageSize.value,
      content_view: transcriptContentView.value,
      correction_status: filters.correction_status || undefined,
      speaker: filters.speaker.trim() || undefined,
      keyword: filters.keyword.trim() || undefined,
    })
    if (request !== transcriptLoadRequest || sessionId !== selectedSessionId.value) return
    transcripts.value = response.items
    total.value = response.meta.total
    page.value = response.meta.page
    pageSize.value = response.meta.page_size
    loadedSessionId.value = selectedSessionId.value
    selectedTranscriptId.value = ''
    resetMergeEditing()
    fillForm(null)
    if (selectFirst && transcriptListItems.value[0]) {
      selectTranscript(transcriptListItems.value[0], false)
    }
  } catch (error: any) {
    if (request === transcriptLoadRequest && sessionId === selectedSessionId.value) ElMessage.error(error?.message || '加载转写失败')
  } finally {
    if (request === transcriptLoadRequest) loadingTranscripts.value = false
  }
}

async function initializePage() {
  await loadGroups()
  const firstGroup = visibleGroups.value[0]
  if (!firstGroup) return
  selectedGroupId.value = firstGroup.group_id
  loadedGroupId.value = firstGroup.group_id
  await loadSessions(firstGroup.group_id)
}

async function handleConditionChange() {
  if (!(await confirmDiscard())) {
    filters.condition = loadedCondition.value
    return
  }
  loadedCondition.value = filters.condition
  const firstGroup = visibleGroups.value[0]
  selectedGroupId.value = firstGroup?.group_id ?? ''
  loadedGroupId.value = selectedGroupId.value
  page.value = 1
  await loadSessions(selectedGroupId.value)
}

async function handleGroupChange(groupId: string) {
  if (!(await confirmDiscard())) {
    selectedGroupId.value = loadedGroupId.value
    return
  }
  page.value = 1
  await loadSessions(groupId)
}

async function handleSessionChange(sessionId: string) {
  if (!(await confirmDiscard())) {
    selectedSessionId.value = loadedSessionId.value
    return
  }
  page.value = 1
  loadedSessionId.value = sessionId
  transcriptContentView.value = 'latest'
  restoreAlignmentAnchor(sessionId)
  await Promise.all([
    loadTranscripts(true),
    loadReferenceUtterances(sessionId),
  ])
  await restoreAlignmentRun(sessionId)
}

async function startAiAlignment() {
  const anchor = alignmentAnchor.value
  if (!historicalRerunReady.value) {
    ElMessage.warning('请先切换到“修订前实时转写”，再重新设置对齐并运行 AI 整理')
    return
  }
  if (!anchor) {
    ElMessage.warning('请先设置录音与实时转写的对齐起点')
    return
  }
  try {
    await ElMessageBox.confirm(
      hasSessionCorrections.value
        ? '系统会从你重新设置的起点开始，根据修订前实时转写生成新的 AI 整理预览。当前已保存修订会一直保留到新结果保存成功。'
        : '系统会从你设置的起点开始，自动整理后面的全部实时转写。本次只生成预览，不会修改原始数据。',
      hasSessionCorrections.value ? '重新 AI 整理' : '自动整理整场',
      { type: 'info', confirmButtonText: '开始整理', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  startingAlignmentRun.value = true
  clearAlignmentRun()
  try {
    const run = await startTranscriptAlignmentRun(selectedSessionId.value, {
      transcript_id: anchor.transcriptId,
      transcript_relative_seconds: anchor.transcriptRelativeSeconds,
      reference_order: anchor.referenceOrder,
      reference_start_time: anchor.referenceStartTime,
    })
    applyAlignmentRun(run)
    localStorage.setItem(alignmentRunStorageKey(selectedSessionId.value), run.run_id)
    await pollAlignmentRun(run.run_id)
  } catch (error: any) {
    ElMessage.error(error?.message || '启动整场 AI 匹配失败')
  } finally {
    startingAlignmentRun.value = false
  }
}

async function focusAiMatch(match: AiAlignmentMatch) {
  if (!(await confirmDiscard())) return
  dirty.value = false
  focusedAiMatchId.value = match.match_id
  selectedReferenceOrder.value = match.reference_orders[0] ?? null
  await nextTick()
  if (selectedReferenceOrder.value != null) {
    referenceElements.get(selectedReferenceOrder.value)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
  const loadedItems = transcripts.value.filter(item => match.transcript_ids.includes(item.transcript_id))
  if (loadedItems.length !== match.transcript_ids.length) {
    ElMessage.info('该整理组涉及当前分页之外的转写')
    return
  }
  const firstLoaded = loadedItems[0]
  if (!firstLoaded) return
  resetMergeEditing()
  selectedTranscriptId.value = firstLoaded.transcript_id
  fillForm(firstLoaded)
  await locateAlignedReference(firstLoaded)
}

async function resolveAiBoundary(
  match: AiAlignmentMatch,
  action: 'previous' | 'next' | 'keep',
) {
  const run = alignmentRun.value
  if (!run || match.saved) return
  if (!(await confirmDiscard())) return
  dirty.value = false
  resolvingAiMatchId.value = match.match_id
  try {
    const freshRun = await resolveTranscriptAlignmentBoundary(run.run_id, match.match_id, action)
    applyAlignmentRun(freshRun)
    focusedAiMatchId.value = ''
    ElMessage.success(action === 'keep' ? '已确认当前分组' : '已并入相邻段')
  } catch (error: any) {
    ElMessage.error(error?.message || '调整分组失败')
  } finally {
    resolvingAiMatchId.value = ''
  }
}

async function saveWholeAlignment() {
  const run = alignmentRun.value
  if (!run || !unsavedOrganizedMatches.value.length) return
  if (!(await confirmDiscard())) return
  try {
    await ElMessageBox.confirm(
      `即将一次保存整场 ${unsavedOrganizedMatches.value.length} 个 AI 修订组。${run.excluded_transcript_ids?.length ? `范围内 ${run.excluded_transcript_ids.length} 条未匹配实时转写将不进入最终正文，原始数据保留。` : ''}${run.summary.replaceable_ai_transcripts ? `其中 ${run.summary.replaceable_ai_transcripts} 条旧 AI 结果会在同一事务中替换。` : ''}${reviewRequiredCount.value ? `有 ${reviewRequiredCount.value} 个橙色位置尚未检查，也会按当前录音原文保存。` : ''}人工修订、原始录音文本和实时转写都不会修改。`,
      '保存整场修订',
      { type: 'warning', confirmButtonText: '保存整场修订', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  dirty.value = false
  savingAlignmentRun.value = true
  try {
    const result = await saveTranscriptAlignmentRun(
      run.run_id,
      unsavedOrganizedMatches.value.map(item => item.match_id),
      form.corrected_by.trim() || null,
    )
    const freshRun = await getTranscriptAlignmentRun(run.run_id)
    applyAlignmentRun(freshRun)
    await Promise.all([loadTranscripts(false), refreshCorrectionCounts()])
    transcriptContentView.value = 'latest'
    if (result.skipped.length) {
      ElMessage.warning(`已保存 ${result.saved_matches} 组，另有 ${result.skipped.length} 组因数据变化而跳过`)
    } else {
      ElMessage.success(`整场修订已保存，共整理 ${result.saved_transcripts} 条实时转写`)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '批量保存 AI 匹配失败')
  } finally {
    savingAlignmentRun.value = false
  }
}

async function switchTranscriptContentView(view: TranscriptContentView) {
  if (transcriptContentView.value === view) return
  if (
    view === 'original'
    && alignmentRun.value
    && !alignmentRunInProgress.value
    && !unsavedOrganizedMatches.value.length
  ) {
    clearAlignmentRun()
  }
  transcriptContentView.value = view
  page.value = 1
  await loadTranscripts(false)
  selectedTranscriptId.value = ''
  resetMergeEditing()
  fillForm(null)
  await nextTick()
  if (transcriptListItems.value[0]) {
    await selectTranscript(transcriptListItems.value[0], false)
  }
}

async function showOriginalTranscriptsForRerun() {
  await switchTranscriptContentView('original')
  ElMessage.info('已显示修订前实时转写，请重新选择两边对应内容并设置对齐起点')
}

async function selectTranscript(transcript: CorrectableTranscript, askBeforeSwitch = true) {
  if (transcript.transcript_id === selectedTranscriptId.value) return
  if (askBeforeSwitch && !(await confirmDiscard())) return
  resetMergeEditing()
  selectedTranscriptId.value = transcript.transcript_id
  fillForm(transcript)
  await locateAlignedReference(transcript)
}

function toggleMergeSelection(transcript: CorrectableTranscript) {
  if (transcript.is_corrected) {
    ElMessage.warning('这条内容已有修订，请先清除原修订再参与新的合并')
    return
  }
  const selected = new Set(mergeSelectionIds.value)
  if (selected.has(transcript.transcript_id)) selected.delete(transcript.transcript_id)
  else selected.add(transcript.transcript_id)
  mergeSelectionIds.value = transcripts.value
    .filter(item => selected.has(item.transcript_id))
    .map(item => item.transcript_id)
}

function selectTimeMatchedTranscripts() {
  const ids = [...timeMatchedTranscriptIds.value]
  if (!ids.length) {
    ElMessage.info('当前录音时间范围内没有可合并的未修订实时转写')
    return
  }
  mergeSelectionIds.value = transcripts.value
    .filter(item => ids.includes(item.transcript_id))
    .map(item => item.transcript_id)
  ElMessage.success(`已选中时间对应的 ${mergeSelectionIds.value.length} 条实时转写`)
}

async function startMergedEditing() {
  if (mergeSelectionIds.value.length < 2) {
    ElMessage.warning('请至少选择两条未修订的实时转写')
    return
  }
  if (!(await confirmDiscard())) return
  const first = selectedMergeTranscripts.value[0]
  if (!first) return
  mergeEditing.value = true
  selectedTranscriptId.value = first.transcript_id
  form.corrected_text = selectedMergeTranscripts.value
    .map(item => (item.effective_text ?? item.original_text ?? '').trim())
    .filter(Boolean)
    .join(' ')
  form.correction_reason = ''
  form.corrected_by = ''
  dirty.value = true
  await locateAlignedReference(first)
}

function selectReference(utterance: UtteranceOut) {
  selectedReferenceOrder.value = utterance.order_index
}

function useReference(mode: 'replace' | 'append') {
  const content = selectedReference.value?.content.trim()
  if (!content) return
  if (mode === 'replace') {
    form.corrected_text = content
  } else {
    const current = form.corrected_text.trim()
    form.corrected_text = current ? `${current} ${content}` : content
  }
  dirty.value = true
}

async function handleSearch() {
  if (!(await confirmDiscard())) return
  page.value = 1
  await loadTranscripts(true)
}

async function handleReset() {
  if (!(await confirmDiscard())) return
  filters.correction_status = ''
  filters.speaker = ''
  filters.keyword = ''
  page.value = 1
  await loadTranscripts(true)
}

function markDirty() {
  dirty.value = true
}

async function refreshCorrectionCounts() {
  try {
    const [freshGroups, freshSessions] = await Promise.all([
      listTranscriptCorrectionGroups(),
      listTranscriptCorrectionSessions(selectedGroupId.value),
    ])
    groups.value = naturalSortGroups(freshGroups)
    sessions.value = freshSessions
  } catch {
    ElMessage.warning('修订已保存，但顶部数量暂未刷新')
  }
}

async function handleSave(moveNext: boolean) {
  const transcript = selectedTranscript.value
  const correctedText = form.corrected_text.trim()
  if (!transcript) return
  if (!correctedText) {
    ElMessage.warning('修订文本不能为空')
    return
  }
  saving.value = true
  try {
    const payload = {
      corrected_text: correctedText,
      correction_reason: form.correction_reason.trim() || null,
      corrected_by: form.corrected_by.trim() || null,
    }
    let savedCorrectionId: string
    if (mergeEditing.value) {
      const correction = await createMergedTranscriptCorrection(selectedSessionId.value, {
        ...payload,
        transcript_ids: mergeSelectionIds.value,
      })
      savedCorrectionId = correction.id
    } else if (transcript.is_merged && transcript.correction_id) {
      const correction = await updateMergedTranscriptCorrection(transcript.correction_id, payload)
      savedCorrectionId = correction.id
    } else {
      const correction = await saveTranscriptCorrection(transcript.transcript_id, payload)
      savedCorrectionId = correction.id
    }
    dirty.value = false
    await Promise.all([loadTranscripts(false), refreshCorrectionCounts()])
    const saved = displayTranscripts.value.find(item => item.correction_id === savedCorrectionId)
    if (moveNext && saved) await selectNextTranscript(saved.transcript_id)
    else if (saved) await selectTranscript(saved, false)
    ElMessage.success('修订已保存，原始实时转写未修改')
  } catch (error: any) {
    ElMessage.error(error?.message || '保存修订失败')
  } finally {
    saving.value = false
  }
}

async function selectNextTranscript(currentId: string) {
  const index = displayTranscripts.value.findIndex(item => item.transcript_id === currentId)
  const next = displayTranscripts.value[index + 1]
  if (next) {
    await selectTranscript(next, false)
  } else {
    ElMessage.info('当前页已经是最后一条转写')
  }
}

async function handleClearCorrection() {
  const transcript = selectedTranscript.value
  if (!transcript?.is_corrected) return
  try {
    await ElMessageBox.confirm(
      '清除后将恢复显示原始转写，只删除修订记录。',
      '清除人工修订',
      { type: 'warning', confirmButtonText: '清除修订', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    if (transcript.is_merged && transcript.correction_id) {
      await deleteMergedTranscriptCorrection(transcript.correction_id)
    } else {
      await deleteTranscriptCorrection(transcript.transcript_id)
    }
    await Promise.all([loadTranscripts(true), refreshCorrectionCounts()])
    ElMessage.success('修订已清除，原始实时转写未修改')
  } catch (error: any) {
    ElMessage.error(error?.message || '清除修订失败')
  } finally {
    saving.value = false
  }
}

async function changePage(value: number) {
  if (!(await confirmDiscard())) return
  page.value = value
  await loadTranscripts(true)
}

async function changePageSize(value: number) {
  if (!(await confirmDiscard())) return
  pageSize.value = value
  page.value = 1
  await loadTranscripts(true)
}

onMounted(initializePage)
onBeforeUnmount(stopAlignmentPolling)
</script>

<template>
  <div class="correction-page review-workspace">
    <header class="page-header">
      <div>
        <h1>提示转写修订</h1>
        <p>以全部录音文字生成最终正文；实时转写辅助确认位置和说话人，原始数据保留。</p>
      </div>
      <el-button @click="showLegacyEditor = !showLegacyEditor">{{ showLegacyEditor ? '返回录音最终版本' : '查看旧版逐条修订' }}</el-button>
    </header>

    <el-card shadow="never" class="filter-card">
      <div class="filters">
        <el-select v-model="filters.condition" placeholder="辅助条件" clearable @change="handleConditionChange">
          <el-option label="眼镜" value="glasses" />
          <el-option label="App 通知" value="app_notification" />
        </el-select>
        <el-select
          v-model="selectedGroupId"
          placeholder="小组"
          filterable
          :loading="loadingGroups"
          @change="handleGroupChange"
        >
          <el-option
            v-for="group in visibleGroups"
            :key="group.group_id"
            :label="`${group.group_name}（${group.corrected_count}/${group.transcript_count}）`"
            :value="group.group_id"
          />
        </el-select>
        <el-select
          v-model="selectedSessionId"
          placeholder="会话"
          filterable
          :loading="loadingSessions"
          :disabled="!selectedGroupId"
          @change="handleSessionChange"
        >
          <el-option
            v-for="session in sessions"
            :key="session.session_id"
            :label="session.session_title || session.session_id"
            :value="session.session_id"
          />
        </el-select>
        <el-select v-model="filters.correction_status" placeholder="修订状态" clearable>
          <el-option label="已修订" value="corrected" />
          <el-option label="未修订" value="uncorrected" />
        </el-select>
        <el-input v-model="filters.speaker" placeholder="搜索说话人" clearable @keyup.enter="handleSearch" />
        <el-input v-model="filters.keyword" placeholder="搜索转写内容" clearable @keyup.enter="handleSearch" />
        <div class="filter-actions">
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </div>
      </div>
    </el-card>

    <section v-if="currentSession" class="summary-strip">
      <div><span>当前小组</span><strong>{{ currentSession.group_name }}</strong></div>
      <div><span>实验条件</span><strong>{{ CONDITION_LABELS[currentSession.condition] }}</strong></div>
      <div><span>转写总数</span><strong>{{ currentSession.transcript_count }}</strong></div>
      <div><span>已修订</span><strong class="corrected-number">{{ currentSession.corrected_count }}</strong></div>
      <div><span>未修订</span><strong>{{ uncorrectedCount }}</strong></div>
    </section>

    <section v-if="currentSession" class="alignment-strip" :class="{ 'is-aligned': alignmentAnchor }">
      <div class="alignment-copy">
        <strong>录音与实时转写对齐</strong>
        <template v-if="alignmentAnchor">
          <span>
            起点：实时 {{ formatRelativeTime(alignmentAnchor.transcriptRelativeSeconds) }}
            ↔ 录音 {{ formatRelativeTime(alignmentAnchor.referenceStartTime) }}
          </span>
          <el-tag size="small" type="success" effect="plain">
            时间偏移 {{ formatSignedSeconds(alignmentOffsetSeconds) }}
          </el-tag>
          <span v-if="expectedReferenceSeconds != null" class="current-alignment">
            当前预计对应录音 {{ formatRelativeTime(expectedReferenceSeconds) }}
            <template v-if="alignedReferenceDistanceSeconds != null">
              · 最近句相差 {{ alignedReferenceDistanceSeconds.toFixed(1) }} 秒
            </template>
          </span>
        </template>
        <span v-else>先在中间选择一条实时转写，再在左侧选择与它对应的录音句，然后设置起点。</span>
      </div>
      <div class="alignment-actions">
        <el-button
          type="primary"
          :disabled="!canSetAlignmentAnchor || !historicalRerunReady"
          @click="setAlignmentAnchor"
        >
          {{ alignmentAnchor ? '以当前两条重新对齐' : '以当前两条设为对齐起点' }}
        </el-button>
        <el-button v-if="alignmentAnchor" @click="clearAlignmentAnchor">清除对齐</el-button>
      </div>
    </section>

    <section class="correction-workbench">
      <main class="transcript-pane pane-card">
        <div class="pane-heading">
          <div><strong>实时转写（修改对象）</strong><span>当前筛选共 {{ total }} 条</span></div>
          <div class="transcript-heading-actions">
            <el-button-group v-if="hasSessionCorrections">
              <el-button
                size="small"
                :type="transcriptContentView === 'latest' ? 'primary' : 'default'"
                @click="switchTranscriptContentView('latest')"
              >最新修订</el-button>
              <el-button
                size="small"
                :type="transcriptContentView === 'original' ? 'primary' : 'default'"
                @click="switchTranscriptContentView('original')"
              >修订前实时转写</el-button>
            </el-button-group>
            <div v-if="!alignmentRun && transcriptContentView === 'latest'" class="merge-actions">
              <el-button
                v-if="timeMatchedTranscriptIds.size"
                size="small"
                plain
                @click="selectTimeMatchedTranscripts"
              >选中对应的 {{ timeMatchedTranscriptIds.size }} 条</el-button>
              <el-button
                size="small"
                type="primary"
                :disabled="mergeSelectionIds.length < 2"
                @click="startMergedEditing"
              >合并修订 {{ mergeSelectionIds.length }} 条</el-button>
            </div>
          </div>
        </div>
        <div id="recording-save-controls"></div>
        <div class="transcript-ai-bar">
          <div class="transcript-ai-bar__top">
            <div>
              <strong>{{ showLegacyEditor ? (hasSessionCorrections ? '历史修订重新整理' : '自动整理整场') : 'AI整理' }}</strong>
              <el-tag size="small" effect="plain">qwen3-max</el-tag>
            </div>
            <el-button
              size="small"
              type="primary"
              :loading="startingAlignmentRun || alignmentRunInProgress"
              :disabled="!alignmentAnchor || !referenceUtterances.length || alignmentRunInProgress || !historicalRerunReady"
              @click="startAiAlignment"
            >{{ showLegacyEditor ? (hasSessionCorrections ? '重新 AI 整理' : '自动整理整场') : 'AI整理' }}</el-button>
          </div>
          <span
            v-if="hasSessionCorrections && transcriptContentView === 'latest'"
            class="transcript-ai-hint"
          >如需重新整理历史修订，请先切换到“修订前实时转写”。</span>
          <span v-else-if="!alignmentAnchor" class="transcript-ai-hint">请先设置对齐起点，再运行AI整理。</span>
          <template v-else-if="alignmentRun">
            <div v-if="alignmentRunInProgress" class="ai-progress">
              <el-progress :percentage="alignmentProgress" :stroke-width="9" />
              <span>{{ alignmentRun.message }} · {{ alignmentRun.completed_chunks }}/{{ alignmentRun.total_chunks }} 段</span>
            </div>
            <template v-else-if="alignmentRun.status !== 'failed'">
              <el-alert
                v-if="alignmentRun.status === 'completed_with_errors'"
                type="warning"
                :closable="false"
                :title="alignmentRun.message"
              />
              <div class="ai-summary">
                <el-tag type="success">已整理 {{ organizedTranscriptCount }} / {{ targetTranscriptCount }} 条</el-tag>
                <el-tag v-if="reviewRequiredCount" type="warning">可选检查 {{ reviewRequiredCount }} 处</el-tag>
                <el-tag v-if="alignmentRun.summary.replaceable_ai_transcripts" type="info">
                  将替换旧 AI {{ alignmentRun.summary.replaceable_ai_transcripts }} 条
                </el-tag>
                <el-tag v-else type="success" effect="plain">{{ showLegacyEditor ? 'AI 已全部整理' : '辅助对应已结束' }}</el-tag>
                <el-tag v-if="alignmentRun.summary.out_of_scope_transcripts" type="info">
                  录音范围外 {{ alignmentRun.summary.out_of_scope_transcripts }} 条
                </el-tag>
              </div>
              <div v-if="showLegacyEditor" class="transcript-ai-controls">
                <el-button
                  size="small"
                  type="success"
                  :disabled="!unsavedOrganizedMatches.length"
                  :loading="savingAlignmentRun"
                  @click="saveWholeAlignment"
                >保存整场修订</el-button>
                <span v-if="reviewRequiredCount" class="transcript-ai-hint">
                  橙色位置可以检查，也可以跳过并直接保存 AI 结果。
                </span>
              </div>
            </template>
            <el-alert
              v-else
              type="warning"
              :closable="false"
              :title="showLegacyEditor ? alignmentRun.message : `AI整理已结束，录音会自动按连续段归入正文，可直接保存。`"
            />
            <p v-if="alignmentRun.status === 'failed' && (unmatchedTranscriptIds.size || unmatchedReferenceOrders.size)" class="transcript-ai-hint">
              录音会自动按连续段归入正文，无需人工逐条匹配。
            </p>
          </template>
          <span v-else class="transcript-ai-hint">整理结果会直接显示在下方；正常位置不需要操作。</span>
        </div>
        <div v-loading="loadingTranscripts" class="transcript-list">
          <div
            v-for="transcript in transcriptListItems"
            :key="transcript.transcript_id"
            class="transcript-row"
            :class="{
              active: transcript.transcript_id === selectedTranscriptId,
              corrected: transcriptContentView === 'latest' && transcript.is_corrected,
              selected: mergeSelectionSet.has(transcript.transcript_id),
              'time-matched': timeMatchedTranscriptIds.has(transcript.transcript_id),
              'ai-focused': focusedAiTranscriptIds.has(transcript.transcript_id),
              'ai-matched': !!aiMatchForTranscript(transcript.transcript_id),
            }"
            @click="selectTranscript(transcript)"
          >
            <div
              v-if="transcriptContentView === 'latest' && hasPreparedAlignment && aiMatchForTranscript(transcript.transcript_id) && isFirstVisibleTranscriptInMatch(transcript.transcript_id, aiMatchForTranscript(transcript.transcript_id)!)"
              class="inline-ai-match"
              :class="{ 'needs-review': aiMatchForTranscript(transcript.transcript_id)!.review_required }"
              @click.stop="focusAiMatch(aiMatchForTranscript(transcript.transcript_id)!)"
            >
              <div>
                <div class="inline-ai-match__meta">
                  <el-tag
                    size="small"
                    :type="aiMatchForTranscript(transcript.transcript_id)!.review_required ? 'warning' : 'success'"
                  >{{ aiMatchForTranscript(transcript.transcript_id)!.review_required ? '可选检查' : '已整理' }}</el-tag>
                  <strong>
                    已整理 {{ aiMatchForTranscript(transcript.transcript_id)!.transcript_ids.length }} 条实时转写
                  </strong>
                  <el-tag v-if="aiMatchForTranscript(transcript.transcript_id)!.saved" size="small" type="info">已保存</el-tag>
                </div>
                <p>准确原文：{{ aiMatchForTranscript(transcript.transcript_id)!.reference_text }}</p>
                <small v-if="aiMatchForTranscript(transcript.transcript_id)!.review_required">
                  {{ aiMatchForTranscript(transcript.transcript_id)!.review_reason }}
                </small>
              </div>
              <div v-if="aiMatchForTranscript(transcript.transcript_id)!.review_required" class="boundary-actions">
                <el-button
                  size="small"
                  :disabled="!canMergeAiMatch(aiMatchForTranscript(transcript.transcript_id)!, 'previous')"
                  :loading="resolvingAiMatchId === aiMatchForTranscript(transcript.transcript_id)!.match_id"
                  @click.stop="resolveAiBoundary(aiMatchForTranscript(transcript.transcript_id)!, 'previous')"
                >并入上一段</el-button>
                <el-button
                  size="small"
                  :disabled="!canMergeAiMatch(aiMatchForTranscript(transcript.transcript_id)!, 'next')"
                  :loading="resolvingAiMatchId === aiMatchForTranscript(transcript.transcript_id)!.match_id"
                  @click.stop="resolveAiBoundary(aiMatchForTranscript(transcript.transcript_id)!, 'next')"
                >并入下一段</el-button>
                <el-button
                  size="small"
                  type="warning"
                  :loading="resolvingAiMatchId === aiMatchForTranscript(transcript.transcript_id)!.match_id"
                  @click.stop="resolveAiBoundary(aiMatchForTranscript(transcript.transcript_id)!, 'keep')"
                >保持当前分组</el-button>
              </div>
              <el-button v-else size="small" plain @click.stop="focusAiMatch(aiMatchForTranscript(transcript.transcript_id)!)">查看</el-button>
            </div>
            <div class="transcript-row__meta">
              <el-checkbox
                v-if="!alignmentRun && transcriptContentView === 'latest'"
                :model-value="mergeSelectionSet.has(transcript.transcript_id)"
                :disabled="transcript.is_corrected"
                aria-label="加入合并修订"
                @click.stop
                @change="toggleMergeSelection(transcript)"
              />
              <strong>{{ transcript.speaker_name }}</strong>
              <el-tag v-if="transcript.final_excluded || alignmentRun?.excluded_transcript_ids?.includes(transcript.transcript_id)" type="info" size="small">不进入正文</el-tag>
              <el-tag v-else-if="transcriptContentView === 'latest' && unmatchedTranscriptIds.has(transcript.transcript_id)" type="danger" size="small">按连续段整理</el-tag>
              <span>相对时间 {{ formatRelativeTime(transcriptRelativeSeconds(transcript)) }}</span>
              <el-tag v-if="transcriptContentView === 'latest' && transcript.is_merged" type="success" size="small">
                已合并 {{ transcript.source_transcript_ids.length }} 条
              </el-tag>
              <template v-if="transcriptContentView === 'latest'">
                <el-tag v-if="transcript.is_corrected" type="warning" size="small">已修订</el-tag>
                <el-tag v-else type="info" size="small" effect="plain">未修订</el-tag>
              </template>
              <el-tag
                v-if="alignmentRun && !alignmentRunInProgress && outOfScopeTranscriptIds.has(transcript.transcript_id)"
                type="info"
                size="small"
                effect="plain"
              >录音范围外</el-tag>
            </div>
            <p>
              {{ (transcriptContentView === 'original'
                ? transcript.original_text
                : transcript.effective_text) || '（无文本）' }}
            </p>
          </div>
          <el-empty v-if="!loadingTranscripts && transcriptListItems.length === 0" description="没有符合条件的转写" />
        </div>
        <div class="pagination">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            :page-sizes="[50, 100, 200, 500]"
            layout="total, sizes, prev, pager, next"
            @current-change="changePage"
            @size-change="changePageSize"
          />
        </div>
      </main>

      <section class="reference-pane pane-card">
        <div class="pane-heading">
          <div>
            <strong>录音重转译对照</strong>
            <span>来自 CoI 预处理页已保存内容 · 无说话人</span>
          </div>
          <el-tag size="small" type="success" effect="plain">{{ referenceUtterances.length }} 条</el-tag>
        </div>
        <div v-loading="loadingReferences" class="reference-list">
          <button
            v-for="utterance in referenceUtterances"
            :key="utterance.order_index"
            :ref="element => setReferenceElement(utterance.order_index, element)"
            type="button"
            class="reference-row"
            :class="{
              active: utterance.order_index === selectedReferenceOrder,
              candidate: referenceCandidateOrders.has(utterance.order_index),
              'auto-target': utterance.order_index === alignedReferenceOrder,
              'ai-focused': focusedAiReferenceOrders.has(utterance.order_index),
            }"
            @click="selectReference(utterance)"
          >
            <div class="reference-row__meta">
              <strong>#{{ utterance.order_index }}</strong>
              <el-tag v-if="unmatchedReferenceOrders.has(utterance.order_index)" type="danger" size="small">按连续段整理</el-tag>
              <span>{{ formatRelativeTime(utterance.start_time) }}</span>
            </div>
            <p>{{ utterance.content }}</p>
          </button>
          <el-empty
            v-if="!loadingReferences && referenceUtterances.length === 0"
            :image-size="90"
            description="该会话尚未保存 CoI 预处理内容"
          />
        </div>
        <div class="reference-note">
          <template v-if="alignmentAnchor">
            蓝色是当前选中的录音句；浅绿色只是前后 {{ REFERENCE_MATCH_WINDOW_SECONDS }} 秒的时间候选。
          </template>
          <template v-else>
            请先手动选择一条与中间实时转写对应的录音句，并在上方设置对齐起点。
          </template>
        </div>
      </section>

      <aside v-if="!showLegacyEditor" class="editor-pane pane-card">
        <RecordingFinalVersionPanel
          :session-id="selectedSessionId"
          :alignment-run-id="alignmentRun?.run_id"
          :alignment-status="alignmentRun?.status"
          :alignment-offset-seconds="alignmentAnchor ? alignmentAnchor.referenceStartTime - alignmentAnchor.transcriptRelativeSeconds : undefined"
          :suggested-start-id="alignmentAnchor?.transcriptId"
          @saved="loadTranscripts(false)"
        >
          <template #empty>
            <div v-if="hasSavedCorrections" class="final-version-list">
              <article v-for="item in finalTranscripts" :key="item.correction_id || item.transcript_id">
                <div><strong>{{ item.speaker_name }}</strong><span>{{ formatDateTimeToCST(item.start ?? item.created_at) }}</span></div>
                <p>{{ item.effective_text || '（无文本）' }}</p>
              </article>
            </div>
            <el-empty v-else description="AI整理完成并确认保存后，显示最终修订结果" :image-size="60" />
          </template>
        </RecordingFinalVersionPanel>
      </aside>
      <aside v-else class="editor-pane pane-card">
        <div
          v-if="showAlignmentPanel"
          class="ai-ready-panel"
          :class="{ 'shows-final': showFinalVersion }"
        >
          <template v-if="hasPreparedAlignment">
            <el-tag type="success" size="large">AI 修订已准备好</el-tag>
            <h2>不需要逐条手动修订</h2>
            <p>
              每个整理组里的“准确原文”就是将要保存的修订文字；实时转写只用于对应说话人和时间，
              不会混入最终正文。
            </p>
            <div class="ai-ready-count">
              <strong>{{ organizedTranscriptCount }}</strong>
              <span>条实时转写已经处理</span>
            </div>
            <el-button
              size="large"
              type="success"
              :loading="savingAlignmentRun"
              @click="saveWholeAlignment"
            >直接保存整场修订</el-button>
            <small v-if="reviewRequiredCount">
              有 {{ reviewRequiredCount }} 个橙色位置可选检查；不检查也可以直接保存。
            </small>
            <small>
              保存时只会替换同一范围内的旧 AI 修订；人工修订、录音转译和原始实时转写都不会改变。
            </small>
          </template>
          <template v-else>
            <div class="final-version-heading">
              <div>
                <el-tag type="success">已保存</el-tag>
                <h2>最终修订版本</h2>
              </div>
              <span>共 {{ finalTranscripts.length }} 个最终段落</span>
            </div>
            <div class="final-version-summary">
              <span class="manual">原有人工修订 {{ manuallyCorrectedFinalCount }}</span>
              <span class="ai">AI 修订 {{ aiCorrectedFinalCount }}</span>
              <span v-if="originalFinalCount" class="original">前后保留原文 {{ originalFinalCount }} 条</span>
              <span v-if="excludedFinalTranscripts.length" class="original">未进入正文 {{ excludedFinalTranscripts.length }} 条</span>
            </div>
            <div class="final-version-actions">
              <el-button
                type="primary"
                plain
                @click="showOriginalTranscriptsForRerun"
              >查看修订前内容并重新整理</el-button>
            </div>
            <p class="final-version-note">
              对齐范围内只显示录音修订内容，未匹配的实时转写不进入正文；对齐范围前后可保留原文。
            </p>
            <div class="final-version-list">
              <article
                v-for="item in finalTranscripts"
                :key="item.correction_id || item.transcript_id"
                :class="{
                  'is-manual': item.is_corrected && !isAiSavedCorrection(item),
                  'is-ai': isAiSavedCorrection(item),
                }"
              >
                <div>
                  <strong>{{ item.speaker_name }}</strong>
                  <span class="final-row-meta">
                    <el-tag v-if="item.is_corrected && !isAiSavedCorrection(item)" size="small" type="warning">原有人工修订</el-tag>
                    <el-tag v-else-if="isAiSavedCorrection(item)" size="small" type="success">AI 修订</el-tag>
                    <el-tag v-else size="small" type="info" effect="plain">保留原文</el-tag>
                    {{ formatDateTimeToCST(item.start ?? item.created_at) }}
                  </span>
                </div>
                <p>{{ item.effective_text || '（无文本）' }}</p>
                <small v-if="item.is_merged">由 {{ item.source_transcript_ids.length }} 条实时转写合并</small>
              </article>
            </div>
          </template>
        </div>
        <div v-else class="pane-heading">
          <div>
            <strong>
              {{ mergeEditing || selectedTranscript?.is_merged
                ? `合并修订 ${selectedEditingSourceIds.length} 条`
                : '当前转写修订' }}
            </strong>
            <span>只保存修订记录，原始转写不变</span>
          </div>
        </div>
        <div
          v-if="!showAlignmentPanel && selectedTranscript"
          class="editor-form"
        >
          <div class="speaker-card">
            <div><strong>{{ selectedTranscript.speaker_name }}</strong><span>{{ formatDateTimeToCST(selectedTranscript.start ?? selectedTranscript.created_at) }}</span></div>
            <small>
              {{ selectedEditingSourceIds.length > 1
                ? `包含 ${selectedEditingSourceIds.length} 条原始实时转写`
                : `转写 ID：${selectedTranscript.transcript_id}` }}
            </small>
          </div>

          <label>原始实时转写（只读）</label>
          <div v-if="editingSourceTranscripts.length > 1" class="source-transcript-list">
            <div v-for="item in editingSourceTranscripts" :key="item.transcript_id">
              <span>{{ item.speaker_name }} · {{ formatRelativeTime(transcriptRelativeSeconds(item)) }}</span>
              <p>{{ item.original_text || '（原始文本为空）' }}</p>
            </div>
          </div>
          <div v-else class="original-text">{{ selectedTranscript.original_text || '（原始文本为空）' }}</div>

          <template v-if="selectedReference">
            <label>当前选中的重转译对照</label>
            <div class="selected-reference">
              <div>
                <strong>#{{ selectedReference.order_index }}</strong>
                <span>{{ formatRelativeTime(selectedReference.start_time) }}</span>
              </div>
              <p>{{ selectedReference.content }}</p>
              <div class="reference-actions">
                <el-button size="small" @click="useReference('replace')">替换到编辑框</el-button>
                <el-button size="small" @click="useReference('append')">追加到编辑框</el-button>
              </div>
            </div>
          </template>

          <label>修订文本</label>
          <el-input v-model="form.corrected_text" type="textarea" :rows="9" @input="markDirty" />

          <label>修订说明</label>
          <el-input
            v-model="form.correction_reason"
            placeholder="可选：记录转写错误或修订依据"
            @input="markDirty"
          />

          <label>修订者</label>
          <el-input v-model="form.corrected_by" placeholder="可选：填写姓名或代号" @input="markDirty" />

          <div v-if="selectedTranscript.is_corrected" class="saved-meta">
            上次修订：{{ formatDateTimeToCST(selectedTranscript.corrected_at) }}
          </div>
          <div v-if="dirty" class="dirty-note">当前有尚未保存的修改</div>

          <div class="editor-actions">
            <el-button type="primary" :loading="saving" @click="handleSave(true)">保存并下一条</el-button>
            <el-button :loading="saving" @click="handleSave(false)">仅保存</el-button>
            <el-button
              v-if="selectedTranscript.is_corrected"
              type="danger"
              plain
              :loading="saving"
              @click="handleClearCorrection"
            >清除修订</el-button>
          </div>
        </div>
        <el-empty
          v-else-if="!showAlignmentPanel"
          description="请选择一条转写"
        />
      </aside>
    </section>
  </div>
</template>

<style scoped>
.correction-page { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.page-header h1 { margin: 0; color: #1e2d40; font-size: 20px; }
.page-header p { margin: 6px 0 0; color: #68778e; font-size: 14px; }
.filter-card { border: 1px solid #e3e9f2; }
.filters { display: grid; grid-template-columns: 140px 180px 230px 140px 160px minmax(180px, 1fr) auto; gap: 10px; }
.filter-actions { display: flex; white-space: nowrap; }
.summary-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; overflow: hidden; border: 1px solid #e3e9f2; border-radius: 8px; background: #e3e9f2; }
.summary-strip > div { display: flex; min-height: 58px; flex-direction: column; justify-content: center; gap: 4px; padding: 9px 16px; background: #fff; }
.summary-strip span { color: #748196; font-size: 13px; }
.summary-strip strong { color: #26364b; font-size: 16px; }
.summary-strip .corrected-number { color: #b45309; }
.alignment-strip { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 11px 14px; border: 1px solid #d7e1ee; border-radius: 8px; background: #f8fafc; }
.alignment-strip.is-aligned { border-color: #9bd5b7; background: #f2fbf6; }
.alignment-copy { display: flex; min-width: 0; flex: 1; flex-wrap: wrap; align-items: center; gap: 6px 12px; color: #627086; font-size: 13px; }
.alignment-copy strong { color: #26364b; font-size: 14px; }
.alignment-copy .current-alignment { flex-basis: 100%; color: #327255; }
.alignment-actions { display: flex; flex: 0 0 auto; gap: 8px; }
.alignment-actions .el-button + .el-button { margin-left: 0; }
.transcript-ai-bar { padding: 10px 12px; border-bottom: 1px solid #e1e7f0; background: #f8f7ff; }
.transcript-ai-bar__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.transcript-ai-bar__top > div { display: flex; align-items: center; gap: 7px; color: #334155; font-size: 14px; }
.transcript-ai-hint { display: block; margin-top: 6px; color: #718096; font-size: 12px; }
.ai-progress { display: flex; flex-direction: column; gap: 5px; margin-top: 8px; }
.ai-progress span { color: #68778e; font-size: 13px; }
.ai-summary { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.transcript-ai-controls { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.transcript-ai-controls .el-button + .el-button { margin-left: 0; }
.inline-ai-match { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 8px; margin: -3px -4px 9px; padding: 8px 9px; border: 1px solid #a7d7bd; border-radius: 7px; background: #f2fbf6; }
.inline-ai-match.needs-review { border-color: #f0b65a; background: #fff8e8; }
.inline-ai-match > div { min-width: 0; }
.inline-ai-match__meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; }
.inline-ai-match__meta strong { color: #276749; font-size: 12px; }
.inline-ai-match p { margin: 5px 0 0; color: #40574d; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
.inline-ai-match small { display: block; margin-top: 4px; color: #9a6700; font-size: 12px; }
.boundary-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; max-width: 210px; }
.boundary-actions .el-button + .el-button { margin-left: 0; }
.correction-workbench { display: grid; grid-template-columns: minmax(330px, .9fr) minmax(400px, 1.15fr) minmax(370px, 1fr); gap: 12px; height: 62vh; min-height: 520px; }
.reference-pane { order: 1; }
.transcript-pane { order: 2; }
.editor-pane { order: 3; }
.pane-card { display: flex; min-width: 0; flex-direction: column; overflow: hidden; border: 1px solid #dfe6ef; border-radius: 9px; background: #fff; box-shadow: 0 4px 14px rgba(31, 45, 67, .04); }
.pane-heading { display: flex; min-height: 58px; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-bottom: 1px solid #e7ecf3; box-sizing: border-box; }
.pane-heading > div { display: flex; flex-direction: column; gap: 3px; }
.pane-heading strong { color: #24344a; font-size: 15px; }
.pane-heading span { color: #7a8799; font-size: 13px; }
.pane-heading .transcript-heading-actions { align-items: flex-end; flex-direction: row; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.pane-heading .merge-actions { flex-direction: row; flex-wrap: wrap; justify-content: flex-end; }
.merge-actions .el-button + .el-button { margin-left: 0; }
.transcript-list { flex: 1; overflow-y: auto; padding: 10px; }
.transcript-row { display: block; width: 100%; margin-bottom: 8px; padding: 11px 13px; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.transcript-row:hover { border-color: #a8b9cf; background: #f8fafc; }
.transcript-row.active { border-color: #3b82f6; background: #eff6ff; box-shadow: inset 3px 0 #3b82f6; }
.transcript-row.time-matched:not(.active):not(.corrected) { border-color: #9bd5b7; background: #f2fbf6; }
.transcript-row.selected { border-color: #7c3aed; background: #f5f3ff; box-shadow: inset 3px 0 #7c3aed; }
.transcript-row.ai-matched:not(.active):not(.selected) { border-color: #c4b5fd; background: #fcfbff; }
.transcript-row.ai-focused { outline: 2px solid #8b5cf6; outline-offset: -2px; }
.transcript-row.corrected:not(.active) { border-color: #f3c477; background: #fffbeb; }
.transcript-row__meta { display: flex; align-items: center; gap: 9px; }
.transcript-row__meta strong { color: #26364b; font-size: 14px; }
.transcript-row__meta span { margin-right: auto; color: #8995a6; font-size: 12px; }
.transcript-row p { margin: 7px 0 0; color: #405067; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.pagination { display: flex; min-height: 52px; align-items: center; justify-content: flex-end; padding: 5px 12px; border-top: 1px solid #e7ecf3; }
.reference-list { flex: 1; overflow-y: auto; padding: 10px; }
.reference-row { display: block; width: 100%; margin-bottom: 8px; padding: 10px 12px; border: 1px solid #dfe8e4; border-radius: 8px; background: #fbfefc; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.reference-row:hover { border-color: #c4b5fd; background: #f5f3ff; }
.reference-row.candidate { border-color: #b9dfcc; background: #f2fbf6; }
.reference-row.auto-target { box-shadow: inset 3px 0 #22a06b; }
.reference-row.active { border-color: #3b82f6; background: #eff6ff; box-shadow: inset 4px 0 #3b82f6; }
.reference-row.ai-focused { outline: 2px solid #8b5cf6; outline-offset: -2px; }
.reference-row__meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.reference-row__meta strong { color: #217052; font-size: 13px; }
.reference-row__meta span { color: #87968f; font-size: 12px; }
.reference-row p { margin: 6px 0 0; color: #40574d; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.reference-note { padding: 9px 12px; border-top: 1px solid #e7ecf3; color: #7b8b84; font-size: 12px; line-height: 1.5; }
.editor-pane { overflow-y: auto; }
.editor-pane .pane-heading { flex: 0 0 auto; }
.ai-ready-panel { display: flex; min-height: 100%; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 30px; box-sizing: border-box; text-align: center; background: linear-gradient(180deg, #f2fbf6 0%, #fff 70%); }
.ai-ready-panel h2 { margin: 2px 0 0; color: #22543d; font-size: 22px; }
.ai-ready-panel p { max-width: 330px; margin: 0; color: #536b60; font-size: 14px; line-height: 1.75; }
.ai-ready-panel small { max-width: 330px; color: #718096; font-size: 13px; line-height: 1.6; }
.ai-ready-count { display: flex; flex-direction: column; gap: 3px; padding: 14px 32px; border: 1px solid #b7e1ca; border-radius: 10px; background: #fff; }
.ai-ready-count strong { color: #16a34a; font-size: 30px; }
.ai-ready-count span { color: #64748b; font-size: 13px; }
.ai-ready-panel.shows-final { min-height: 0; align-items: stretch; justify-content: flex-start; gap: 10px; padding: 0; text-align: left; background: #fff; }
.final-version-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 16px 10px; border-bottom: 1px solid #e5e7eb; background: #f2fbf6; }
.final-version-heading > div { display: flex; align-items: center; gap: 8px; }
.final-version-heading h2 { margin: 0; font-size: 17px; }
.final-version-heading > span { color: #64748b; font-size: 12px; }
.final-version-summary { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px; }
.final-version-summary span { padding: 5px 8px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.final-version-summary .manual { color: #9a5b00; background: #fff3d6; }
.final-version-summary .ai { color: #18794e; background: #e7f8ef; }
.final-version-summary .original { color: #596579; background: #edf1f6; }
.final-version-actions { padding: 0 16px; }
.ai-ready-panel .final-version-note { max-width: none; padding: 0 16px; color: #557064; font-size: 13px; line-height: 1.55; }
.final-version-list { flex: 1; overflow-y: auto; padding: 0 12px 12px; }
.final-version-list article { margin-bottom: 8px; padding: 10px 11px; border: 1px solid #d7e9df; border-radius: 8px; background: #fbfefc; }
.final-version-list article.is-manual { border-color: #efc472; background: #fffaf0; }
.final-version-list article.is-ai { border-color: #a7d7bd; background: #f5fcf8; }
.final-version-list article > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.final-version-list article strong { color: #285b44; font-size: 13px; }
.final-version-list article span { color: #84958d; font-size: 12px; }
.final-row-meta { display: flex; align-items: center; justify-content: flex-end; gap: 5px; }
.final-version-list article p { margin: 6px 0 0; color: #334b40; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.final-version-list article small { display: block; max-width: none; margin-top: 5px; color: #7a8d83; font-size: 12px; }
.editor-form { display: flex; flex-direction: column; padding: 16px; }
.speaker-card { padding: 11px 12px; border-radius: 8px; background: #f4f7fb; }
.speaker-card > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.speaker-card strong { color: #26364b; font-size: 14px; }
.speaker-card span, .speaker-card small { color: #7b8798; font-size: 12px; }
.speaker-card small { display: block; margin-top: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.editor-form label { margin: 14px 0 6px; color: #34445a; font-size: 13px; font-weight: 700; }
.original-text { min-height: 86px; padding: 11px 12px; border: 1px solid #e2e8f0; border-radius: 7px; background: #f8fafc; color: #536176; font-size: 14px; line-height: 1.65; white-space: pre-wrap; }
.source-transcript-list { overflow: hidden; border: 1px solid #d8ddeb; border-radius: 7px; background: #fafbff; }
.source-transcript-list > div { padding: 9px 11px; border-bottom: 1px solid #e7eaf1; }
.source-transcript-list > div:last-child { border-bottom: 0; }
.source-transcript-list span { color: #7c8798; font-size: 12px; }
.source-transcript-list p { margin: 4px 0 0; color: #4d5b70; font-size: 14px; line-height: 1.55; white-space: pre-wrap; }
.selected-reference { padding: 10px 11px; border: 1px solid #93c5fd; border-radius: 7px; background: #eff6ff; }
.selected-reference > div:first-child { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.selected-reference strong { color: #2563eb; font-size: 13px; }
.selected-reference span { color: #7184a0; font-size: 12px; }
.selected-reference p { margin: 7px 0 9px; color: #405067; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.reference-actions { display: flex; gap: 6px; }
.reference-actions .el-button + .el-button { margin-left: 0; }
.saved-meta, .dirty-note { margin-top: 10px; color: #8390a2; font-size: 12px; }
.dirty-note { color: #b7791f; }
.editor-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.editor-actions .el-button + .el-button { margin-left: 0; }
@media (max-width: 1300px) {
  .filters { grid-template-columns: repeat(4, minmax(150px, 1fr)); }
  .alignment-strip { align-items: flex-start; flex-direction: column; }
  .transcript-ai-controls { align-items: flex-start; flex-direction: column; }
}
</style>

<style scoped src="../../styles/review-workspace.css"></style>
