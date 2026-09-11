<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import type { AdminChatSession } from '../../types/admin'
import { formatDateTimeToCST, formatTimeToCST } from '../../utils/datetime'
import {
  deleteCueCoding,
  downloadCueCodingExport,
  getCueCodingProgress,
  getCueSessionContext,
  findCueRelatedDiscussion,
  type CueRelatedDiscussion,
  type CueTaskType,
  listCueCodingGroups,
  listCueEvents,
  saveCueCoding,
  type CueCodingProgress,
  type CueCodingGroup,
  type CueCodingStatus,
  type CueCondition,
  type CueContextTranscript,
  type CueEvent,
  type CueSessionContext,
  type CueUptakeCode,
} from '../../api/admin/cue-uptake-coding'

const CODER_ROLE = 'primary'
const CODE_OPTIONS: Array<{
  value: CueUptakeCode
  label: string
  short: string
  definition: string
  type: 'info' | 'warning' | 'success' | 'danger'
}> = [
  {
    value: 'not_discussed',
    label: '未讨论',
    short: '未讨论',
    definition: '后续讨论未实质涉及提示提出的问题或思考方向；仅出现相同物品名称不算讨论',
    type: 'info',
  },
  {
    value: 'discussed_not_adopted',
    label: '讨论未采纳',
    short: '未采纳',
    definition: '后续实质讨论了提示提出的问题或思考方向，但未见其被用于形成、支持或调整小组观点、判断或答案',
    type: 'warning',
  },
  {
    value: 'discussed_adopted',
    label: '讨论并采纳',
    short: '已采纳',
    definition: '后续实质讨论了提示提出的问题或思考方向，并有明确证据表明它被用于形成、支持或调整小组观点、判断或答案；不要求同意问句隐含的立场',
    type: 'success',
  },
  {
    value: 'uncertain',
    label: '无法判断',
    short: '无法判断',
    definition: '因提示前已有相同讨论、提示重叠或材料不足，无法可靠区分上述情况',
    type: 'danger',
  },
  {
    value: 'not_included',
    label: '不纳入',
    short: '不纳入',
    definition: '提示本身存在问题，不作为有效分析样本。',
    type: 'danger',
  },
]

interface TimelineTranscriptItem {
  kind: 'transcript'
  id: string
  timestamp: string | null
  transcript: CueContextTranscript
}

interface TimelineCueItem {
  kind: 'cue'
  id: string
  timestamp: string
  cue: CueEvent
}

type TimelineItem = TimelineTranscriptItem | TimelineCueItem

const groups = ref<CueCodingGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const events = ref<CueEvent[]>([])
const progress = ref<CueCodingProgress | null>(null)
const context = ref<CueSessionContext | null>(null)
let contextRequest = 0
const selectedPushLogId = ref('')
const loading = ref(false)
const loadingContext = ref(false)
const loadingSessions = ref(false)
const saving = ref(false)
const exporting = ref(false)
const timelineScrollRef = ref<HTMLElement | null>(null)
const page = ref(1)
const pageSize = ref(30)
const total = ref(0)
const dirty = ref(false)
const relatedResults = reactive(new Map<string, CueRelatedDiscussion>())
const relatedPending = reactive(new Set<string>())
const relatedErrors = reactive(new Map<string, string>())
const relatedPositions = reactive(new Map<string, number>())
const sessionTasks = reactive<Record<string, CueTaskType>>({})
try {
  const saved = JSON.parse(localStorage.getItem('cue-session-tasks-v1') || '{}')
  for (const [id, task] of Object.entries(saved || {})) {
    if (task === 'moon' || task === 'sea' || task === 'winter') sessionTasks[id] = task
  }
} catch { /* Invalid or unavailable local storage leaves tasks unselected. */ }
const selectedTask = computed(() => selectedEvent.value ? sessionTasks[selectedEvent.value.session_id] : undefined)
const sessionAnalysisPending = computed(() => events.value.some(event =>
  event.session_id === selectedEvent.value?.session_id && relatedPending.has(event.push_log_id)))
function changeTask(task: CueTaskType) {
  const event = selectedEvent.value
  if (!event) return
  sessionTasks[event.session_id] = task
  try { localStorage.setItem('cue-session-tasks-v1', JSON.stringify(sessionTasks)) } catch { /* Keep in-memory selection. */ }
  for (const cue of context.value?.cues ?? []) {
    relatedResults.delete(cue.push_log_id)
    relatedErrors.delete(cue.push_log_id)
    relatedPositions.delete(cue.push_log_id)
  }
}
const currentRelated = computed(() => relatedResults.get(selectedPushLogId.value))
const relatedMatches = computed(() => (currentRelated.value?.matches ?? []).filter(match =>
  context.value?.transcripts.some(item => item.transcript_id === match.transcript_id && item.text === match.text),
))
const relatedById = computed(() => new Map(relatedMatches.value.map(match => [match.transcript_id, match])))
const relatedPosition = computed(() => relatedPositions.get(selectedPushLogId.value) ?? -1)

async function lookupRelated() {
  const event = selectedEvent.value
  const task = selectedTask.value
  if (!event || !task || relatedPending.has(event.push_log_id)) return
  const id = event.push_log_id
  relatedPending.add(id)
  relatedErrors.delete(id)
  try {
    const result = await findCueRelatedDiscussion(id, task)
    if (result.push_log_id !== id) throw new Error('查找结果与当前提示不一致，请重试')
    if (sessionTasks[event.session_id] !== task) return
    relatedResults.set(id, result)
    relatedPositions.delete(id)
  } catch (error: any) {
    relatedErrors.set(id, error?.message || 'AI 查找失败，请重试')
  } finally {
    relatedPending.delete(id)
  }
}

function navigateRelated(direction: number) {
  const matches = relatedMatches.value
  if (!matches.length) return
  const previous = relatedPosition.value
  const index = previous < 0 ? (direction > 0 ? 0 : matches.length - 1)
    : (previous + direction + matches.length) % matches.length
  const match = matches[index]
  if (!match) return
  relatedPositions.set(selectedPushLogId.value, index)
  const container = timelineScrollRef.value
  const target = document.getElementById(`transcript-timeline-${match.transcript_id}`)
  if (container && target) {
    container.scrollTo({ top: target.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 12, behavior: 'auto' })
  }
}

function applySuggestedCode() {
  const recommendation = currentRelated.value
  if (!recommendation?.suggested_code || loadingContext.value || saving.value
    || relatedMatches.value.length !== recommendation.matches.length) return
  form.uptake_code = recommendation.suggested_code
  markDirty()
  ElMessage.info('已填入推荐编码，请核对证据和判断说明后保存')
}

const filters = reactive({
  condition: '' as CueCondition | '',
  group_id: '',
  session_id: '',
  coding_status: '' as CueCodingStatus | '',
  uptake_code: '' as CueUptakeCode | '',
  keyword: '',
})

const form = reactive({
  uptake_code: '' as CueUptakeCode | '',
  evidence_transcript_ids: [] as string[],
  coding_reason: '',
  coded_by: '',
})

const selectedEvent = computed(() =>
  events.value.find(item => item.push_log_id === selectedPushLogId.value) ?? null,
)
const selectedGroupName = computed(() =>
  groups.value.find(group => group.group_id === filters.group_id)?.group_name
    ?? selectedEvent.value?.group_name
    ?? '当前小组',
)
const visibleGroups = computed(() =>
  groups.value.filter(group => !filters.condition || group.condition === filters.condition),
)
const selectedEvidence = computed(() => {
  const idSet = new Set(form.evidence_transcript_ids)
  return (context.value?.transcripts ?? []).filter(item =>
    evidenceIds(item).some(transcriptId => idSet.has(transcriptId))
      || item.source_transcript_ids.some(id => idSet.has(id)),
  )
})
const completionPercentage = computed(() =>
  progress.value ? Math.round(progress.value.completion_rate * 100) : 0,
)
const timelineItems = computed<TimelineItem[]>(() => {
  if (!context.value) return []
  const transcripts: TimelineTranscriptItem[] = context.value.transcripts.map(transcript => ({
    kind: 'transcript',
    id: `transcript-${transcript.transcript_id}`,
    timestamp: transcript.start ?? transcript.created_at,
    transcript,
  }))
  const cues: TimelineCueItem[] = context.value.cues.map(cue => ({
    kind: 'cue',
    id: `cue-${cue.push_log_id}`,
    timestamp: cue.received_at,
    cue,
  }))
  if (context.value.final_version_id) {
    // Keep the document's exact order, even when times repeat or are missing.
    const remaining = [...cues].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    const result: TimelineItem[] = []
    for (const transcript of transcripts) {
      const time = transcript.timestamp ? Date.parse(transcript.timestamp) : null
      while (remaining.length && time !== null && Date.parse(remaining[0]!.timestamp) <= time) {
        result.push(remaining.shift()!)
      }
      result.push(transcript)
    }
    return [...result, ...remaining]
  }
  return [...transcripts, ...cues].sort((left, right) => {
    const leftTime = left.timestamp ? new Date(left.timestamp).getTime() : Number.MAX_SAFE_INTEGER
    const rightTime = right.timestamp ? new Date(right.timestamp).getTime() : Number.MAX_SAFE_INTEGER
    if (leftTime !== rightTime) return leftTime - rightTime
    return left.kind === 'cue' ? -1 : 1
  })
})

function codeMeta(code: CueUptakeCode | null | undefined) {
  return CODE_OPTIONS.find(option => option.value === code)
}

function eventParams() {
  return {
    page: page.value,
    page_size: pageSize.value,
    condition: filters.condition || undefined,
    group_id: filters.group_id || undefined,
    session_id: filters.session_id || undefined,
    coding_status: filters.coding_status || undefined,
    uptake_code: filters.uptake_code || undefined,
    keyword: filters.keyword.trim() || undefined,
    coder_role: CODER_ROLE,
  }
}

function progressParams() {
  return {
    condition: filters.condition || undefined,
    group_id: filters.group_id || undefined,
    session_id: filters.session_id || undefined,
    coder_role: CODER_ROLE,
  }
}

async function loadGroups() {
  try {
    const response = await listCueCodingGroups()
    groups.value = response.sort((left, right) =>
      left.group_name.localeCompare(right.group_name, 'zh-CN', {
        numeric: true,
        sensitivity: 'base',
      }),
    )
  } catch (error: any) {
    ElMessage.error(error?.message || '加载可编码小组失败')
  }
}

async function handleConditionChange() {
  if (!visibleGroups.value.some(group => group.group_id === filters.group_id)) {
    filters.group_id = visibleGroups.value[0]?.group_id ?? ''
    await loadSessions()
  }
}

async function loadSessions() {
  sessions.value = []
  filters.session_id = ''
  if (!filters.group_id) return
  loadingSessions.value = true
  try {
    const response = await listAdminChatSessions({ group_id: filters.group_id, page_size: 200 })
    sessions.value = response.items
  } catch (error: any) {
    ElMessage.error(error?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

async function loadProgress() {
  try {
    progress.value = await getCueCodingProgress(progressParams())
  } catch (error: any) {
    ElMessage.error(error?.message || '加载编码进度失败')
  }
}

async function loadEvents(selectFirst = true) {
  loading.value = true
  try {
    const response = await listCueEvents(eventParams())
    events.value = response.items
    total.value = response.meta.total
    page.value = response.meta.page
    pageSize.value = response.meta.page_size
    const selectedStillExists = events.value.some(item => item.push_log_id === selectedPushLogId.value)
    if (!selectedStillExists) {
      selectedPushLogId.value = ''
      context.value = null
      resetForm()
    }
    if (selectFirst && !selectedPushLogId.value && events.value[0]) {
      await selectEvent(events.value[0], false)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载提示列表失败')
  } finally {
    loading.value = false
  }
}

async function refreshPage() {
  await Promise.all([loadEvents(), loadProgress()])
}

async function loadDefaultGroupAndData() {
  loading.value = true
  try {
    const firstGroup = visibleGroups.value[0]
    if (!firstGroup) {
      events.value = []
      total.value = 0
      progress.value = await getCueCodingProgress({ coder_role: CODER_ROLE })
      return
    }
    filters.group_id = firstGroup.group_id
    await loadSessions()
    page.value = 1
    await refreshPage()
  } catch (error: any) {
    ElMessage.error(error?.message || '加载默认小组失败')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.uptake_code = ''
  form.evidence_transcript_ids = []
  form.coding_reason = ''
  form.coded_by = ''
  dirty.value = false
}

function fillForm(event: CueEvent) {
  form.uptake_code = event.coding?.uptake_code ?? ''
  form.evidence_transcript_ids = [...(event.coding?.evidence_transcript_ids ?? [])]
  form.coding_reason = event.coding?.coding_reason ?? ''
  form.coded_by = event.coding?.coded_by ?? ''
  dirty.value = false
}

async function confirmDiscard(): Promise<boolean> {
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm(
      '当前提示有尚未保存的修改，继续后这些修改会丢失。',
      '切换提示',
      { type: 'warning', confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' },
    )
    return true
  } catch {
    return false
  }
}

async function selectEvent(event: CueEvent, askBeforeSwitch = true) {
  if (event.push_log_id === selectedPushLogId.value) return
  if (askBeforeSwitch && !(await confirmDiscard())) return
  selectedPushLogId.value = event.push_log_id
  fillForm(event)
  const request = ++contextRequest
  context.value = null
  loadingContext.value = true
  try {
    const sessionContext = await getCueSessionContext(event.session_id, CODER_ROLE)
    if (request !== contextRequest || selectedPushLogId.value !== event.push_log_id) return
    context.value = sessionContext
    nextTick(() => {
      if (request !== contextRequest || selectedPushLogId.value !== event.push_log_id) return
      const container = timelineScrollRef.value
      const target = document.getElementById(`cue-timeline-${event.push_log_id}`)
      if (!container || !target) return
      const top = target.getBoundingClientRect().top
        - container.getBoundingClientRect().top
        + container.scrollTop
      container.scrollTo({ top, behavior: 'auto' })
    })
  } catch (error: any) {
    if (request !== contextRequest || selectedPushLogId.value !== event.push_log_id) return
    context.value = null
    ElMessage.error(error?.message || '加载会话上下文失败')
  } finally {
    if (request === contextRequest && selectedPushLogId.value === event.push_log_id) loadingContext.value = false
  }
}

async function handleSearch() {
  if (!(await confirmDiscard())) return
  page.value = 1
  selectedPushLogId.value = ''
  context.value = null
  resetForm()
  await refreshPage()
}

async function handleReset() {
  if (!(await confirmDiscard())) return
  filters.condition = ''
  filters.group_id = ''
  filters.session_id = ''
  filters.coding_status = ''
  filters.uptake_code = ''
  filters.keyword = ''
  sessions.value = []
  page.value = 1
  selectedPushLogId.value = ''
  context.value = null
  resetForm()
  await loadDefaultGroupAndData()
}

function markDirty() {
  dirty.value = true
}

function discussionTime(transcript: CueContextTranscript) {
  if (!transcript.final_version_id) return formatTimeToCST(transcript.start ?? transcript.created_at)
  const seconds = transcript.relative_seconds
  if (seconds == null) return '时间未标注'
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
}

function evidenceIds(transcript: CueContextTranscript): string[] {
  if (transcript.final_version_id) return [transcript.transcript_id]
  return transcript.source_transcript_ids.length
    ? transcript.source_transcript_ids
    : [transcript.transcript_id]
}

function isEvidenceSelected(transcript: CueContextTranscript): boolean {
  const selected = new Set(form.evidence_transcript_ids)
  return evidenceIds(transcript).every(transcriptId => selected.has(transcriptId))
}

function toggleEvidence(transcript: CueContextTranscript) {
  const ids = evidenceIds(transcript)
  const selected = new Set(form.evidence_transcript_ids)
  const shouldRemove = ids.every(transcriptId => selected.has(transcriptId))
  ids.forEach((transcriptId) => {
    if (shouldRemove) selected.delete(transcriptId)
    else selected.add(transcriptId)
  })
  form.evidence_transcript_ids = [...selected]
  markDirty()
}

function validateForm(): boolean {
  if (!form.uptake_code) {
    ElMessage.warning('请选择编码结果')
    return false
  }
  if (
    ['discussed_not_adopted', 'discussed_adopted'].includes(form.uptake_code)
    && form.evidence_transcript_ids.length === 0
  ) {
    ElMessage.warning('讨论相关编码至少需要选择一条证据发言')
    return false
  }
  if (form.uptake_code === 'uncertain' && !form.coding_reason.trim()) {
    ElMessage.warning('无法判断时必须填写判断原因')
    return false
  }
  return true
}

async function handleSave(moveNext: boolean) {
  const event = selectedEvent.value
  if (!event || !validateForm()) return
  saving.value = true
  try {
    const coding = await saveCueCoding(event.push_log_id, {
      coder_role: CODER_ROLE,
      uptake_code: form.uptake_code as CueUptakeCode,
      evidence_transcript_ids: [...form.evidence_transcript_ids],
      coding_reason: form.coding_reason.trim() || null,
      coded_by: form.coded_by.trim() || null,
    })
    event.coding = coding
    const cachedContext = context.value?.session_id === event.session_id ? context.value : null
    const cachedEvent = cachedContext?.cues.find(item => item.push_log_id === event.push_log_id)
    if (cachedEvent) cachedEvent.coding = coding
    dirty.value = false
    await loadProgress()
    ElMessage.success('编码已保存')
    if (moveNext) await selectNextUncoded(event.push_log_id)
  } catch (error: any) {
    ElMessage.error(error?.message || '保存编码失败')
  } finally {
    saving.value = false
  }
}

async function selectNextUncoded(afterPushLogId: string) {
  const currentIndex = events.value.findIndex(item => item.push_log_id === afterPushLogId)
  const next = events.value.slice(currentIndex + 1).find(item => !item.coding)
    ?? events.value.slice(0, currentIndex).find(item => !item.coding)
  if (next) {
    await selectEvent(next, false)
    return
  }
  ElMessage.info('当前页没有其他未编码提示')
}

async function handleDeleteCoding() {
  const event = selectedEvent.value
  if (!event?.coding) return
  try {
    await ElMessageBox.confirm(
      '只会清除当前提示的人工编码，不会删除提示或讨论文本。确认继续？',
      '清除编码',
      { type: 'warning', confirmButtonText: '清除编码', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await deleteCueCoding(event.push_log_id, CODER_ROLE)
    event.coding = null
    const cachedContext = context.value?.session_id === event.session_id ? context.value : null
    const cachedEvent = cachedContext?.cues.find(item => item.push_log_id === event.push_log_id)
    if (cachedEvent) cachedEvent.coding = null
    resetForm()
    await loadProgress()
    ElMessage.success('当前提示编码已清除')
  } catch (error: any) {
    ElMessage.error(error?.message || '清除编码失败')
  } finally {
    saving.value = false
  }
}

async function changePage(value: number) {
  if (!(await confirmDiscard())) return
  page.value = value
  selectedPushLogId.value = ''
  context.value = null
  resetForm()
  await loadEvents()
}

async function changePageSize(value: number) {
  if (!(await confirmDiscard())) return
  pageSize.value = value
  page.value = 1
  selectedPushLogId.value = ''
  context.value = null
  resetForm()
  await loadEvents()
}

async function handleExport() {
  exporting.value = true
  try {
    await downloadCueCodingExport(eventParams())
    ElMessage.success('导出完成')
  } catch (error: any) {
    ElMessage.error(error?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await loadGroups()
  await loadDefaultGroupAndData()
})
</script>

<template>
  <div class="cue-page review-workspace">
    <header class="page-header">
      <div>
        <h1>提示采纳编码</h1>
        <p>逐条对照 AI 提示与会话文本，记录提示是否进入讨论以及是否被采纳。</p>
      </div>
      <el-button :loading="exporting" @click="handleExport">导出当前结果</el-button>
    </header>

    <el-card shadow="never" class="filter-card">
      <div class="filters">
        <el-select v-model="filters.condition" placeholder="实验条件" clearable @change="handleConditionChange">
          <el-option label="眼镜" value="glasses" />
          <el-option label="App 通知" value="app_notification" />
        </el-select>
        <el-select
          v-model="filters.group_id"
          placeholder="小组"
          filterable
          @change="loadSessions"
        >
          <el-option
            v-for="group in visibleGroups"
            :key="group.group_id"
            :label="`${group.group_name}（${group.event_count}）`"
            :value="group.group_id"
          />
        </el-select>
        <el-select
          v-model="filters.session_id"
          placeholder="会话"
          clearable
          filterable
          :loading="loadingSessions"
          :disabled="!filters.group_id"
        >
          <el-option
            v-for="session in sessions"
            :key="session.id"
            :label="session.session_title || session.id"
            :value="session.id"
          />
        </el-select>
        <el-select v-model="filters.coding_status" placeholder="编码状态" clearable>
          <el-option label="已编码" value="coded" />
          <el-option label="未编码" value="uncoded" />
        </el-select>
        <el-select v-model="filters.uptake_code" placeholder="编码结果" clearable>
          <el-option v-for="option in CODE_OPTIONS" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="搜索提示内容"
          clearable
          @keyup.enter="handleSearch"
        />
        <div class="filter-actions">
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </div>
      </div>
    </el-card>

    <section class="progress-strip">
      <div class="progress-main">
        <span class="progress-label">{{ selectedGroupName }} 编码进度</span>
        <strong>{{ progress?.coded ?? 0 }} / {{ progress?.total ?? 0 }}</strong>
        <el-progress :percentage="completionPercentage" :stroke-width="8" />
      </div>
      <div class="progress-count"><span>未编码</span><strong>{{ progress?.uncoded ?? 0 }}</strong></div>
      <div v-for="option in CODE_OPTIONS" :key="option.value" class="progress-count">
        <span>{{ option.label }}</span>
        <strong>{{ progress?.by_code?.[option.value] ?? 0 }}</strong>
      </div>
    </section>

    <section class="coding-workbench">
      <aside class="event-pane pane-card">
        <div class="pane-heading">
          <div>
            <strong>提示列表</strong>
            <span>共 {{ total }} 条</span>
          </div>
        </div>
        <div v-loading="loading" class="event-list">
          <button
            v-for="event in events"
            :key="event.push_log_id"
            type="button"
            class="event-card"
            :class="{ active: event.push_log_id === selectedPushLogId }"
            @click="selectEvent(event)"
          >
            <div class="event-card__top">
              <span class="event-target">{{ event.target_user_name }}</span>
              <el-tag v-if="event.coding" :type="codeMeta(event.coding.uptake_code)?.type" size="small">
                {{ codeMeta(event.coding.uptake_code)?.short }}
              </el-tag>
              <el-tag v-else type="info" size="small" effect="plain">未编码</el-tag>
            </div>
            <p>{{ event.push_content }}</p>
            <div class="event-card__meta">
              <span>{{ event.group_name }}</span>
              <span>{{ formatTimeToCST(event.received_at) }}</span>
            </div>
            <el-tag v-if="event.possible_duplicate" type="warning" size="small" effect="plain">可能重复</el-tag>
          </button>
          <el-empty v-if="!loading && events.length === 0" description="没有符合条件的提示" :image-size="72" />
        </div>
        <div class="event-pagination">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            :page-sizes="[20, 30, 50, 100]"
            small
            layout="total, sizes, prev, next"
            @current-change="changePage"
            @size-change="changePageSize"
          />
        </div>
      </aside>

      <main class="timeline-pane pane-card" v-loading="loadingContext">
        <div class="pane-heading">
          <div>
            <strong>会话讨论</strong>
            <span v-if="context">{{ context.group_name }} · {{ context.session_title || context.session_id }}</span>
          </div>
          <el-tag v-if="context?.final_version_id" type="success" size="small">最终修订版本 · {{ context.transcripts.length }} 段</el-tag>
          <span v-if="context" class="member-count">{{ context.members.length }} 名成员</span>
        </div>
        <div v-if="selectedEvent" class="related-toolbar">
          <div class="related-controls">
            <el-select :model-value="selectedTask" aria-label="本会话任务类型" placeholder="先选择本会话任务" size="small" style="width: 170px" :disabled="sessionAnalysisPending" @change="changeTask">
              <el-option label="月球求生" value="moon" />
              <el-option label="海上求生" value="sea" />
              <el-option label="冬季求生（冬日）" value="winter" />
            </el-select>
            <el-button size="small" type="primary" plain :loading="relatedPending.has(selectedPushLogId)" :disabled="loadingContext || !context || !selectedTask" @click="lookupRelated">
              {{ relatedPending.has(selectedPushLogId) ? '正在分析' : currentRelated ? '重新分析' : 'AI 分析提示与讨论' }}
            </el-button>
            <template v-if="currentRelated">
              <span role="status">{{ !currentRelated.analyzed_count ? '没有可分析的后续讨论' : relatedMatches.length ? `找到 ${relatedMatches.length} 条相关讨论` : '未找到相关讨论' }}</span>
              <template v-if="relatedMatches.length">
                <el-button size="small" @click="navigateRelated(-1)">上一条</el-button>
                <span>{{ relatedPosition < 0 ? '—' : relatedPosition + 1 }} / {{ relatedMatches.length }}</span>
                <el-button size="small" @click="navigateRelated(1)">下一条</el-button>
              </template>
            </template>
          </div>
          <small v-if="!selectedTask">请先选择本会话任务类型；选择会在当前浏览器按会话记住。</small>
          <small>解释提示含义，分析提示后直到本次会话结束的讨论并推荐编码；结果供参考，刷新后清除。</small>
          <small v-if="currentRelated?.excluded_boundary_count">已排除 {{ currentRelated.excluded_boundary_count }} 段跨越提示时间、时间相同或时间不明的发言。</small>
          <small v-if="currentRelated && relatedMatches.length !== currentRelated.matches.length">部分原文与结果不一致，已隐藏相关标记，请刷新页面后重新查找。</small>
          <span v-if="relatedErrors.get(selectedPushLogId)" class="related-error" role="alert">{{ relatedErrors.get(selectedPushLogId) }}</span>
        </div>
        <div v-if="context" ref="timelineScrollRef" class="timeline-scroll">
          <div
            v-for="item in timelineItems"
            :id="item.kind === 'cue' ? `cue-timeline-${item.cue.push_log_id}` : `transcript-timeline-${item.transcript.transcript_id}`"
            :key="item.id"
            class="timeline-entry"
            :class="{
              'timeline-entry--cue': item.kind === 'cue',
              'timeline-entry--current': item.kind === 'cue' && item.cue.push_log_id === selectedPushLogId,
              'timeline-entry--evidence': item.kind === 'transcript' && isEvidenceSelected(item.transcript),
              'timeline-entry--related': item.kind === 'transcript' && relatedById.has(item.transcript.transcript_id),
            }"
          >
            <template v-if="item.kind === 'transcript'">
              <div class="timeline-avatar">{{ item.transcript.speaker_name.slice(0, 1) }}</div>
              <div class="transcript-body">
                <div class="transcript-meta">
                  <strong>{{ item.transcript.speaker_name }}</strong>
                  <span>{{ discussionTime(item.transcript) }}</span>
                  <el-tooltip v-if="relatedById.has(item.transcript.transcript_id)" :content="relatedById.get(item.transcript.transcript_id)?.reason" placement="top">
                    <el-tag type="warning" size="small" tabindex="0">AI 相关</el-tag>
                  </el-tooltip>
                  <el-tag v-if="item.transcript.is_corrected" type="warning" size="small" effect="plain">已修订</el-tag>
                  <el-tag v-if="item.transcript.is_merged" type="success" size="small" effect="plain">
                    合并 {{ item.transcript.source_transcript_ids.length }} 条
                  </el-tag>
                  <el-popover v-if="item.transcript.is_corrected && !item.transcript.final_version_id" placement="top" width="360" trigger="click">
                    <template #reference><el-button link type="info">查看原文</el-button></template>
                    <div class="raw-transcript-popover">{{ item.transcript.original_text || '（原始文本为空）' }}</div>
                  </el-popover>
                  <el-button
                    class="evidence-button"
                    link
                    :type="isEvidenceSelected(item.transcript) ? 'success' : 'primary'"
                    @click="toggleEvidence(item.transcript)"
                  >
                    {{ isEvidenceSelected(item.transcript) ? '已选证据' : '选为证据' }}
                  </el-button>
                </div>
                <p>{{ item.transcript.text || (item.transcript.final_version_id ? '（空白原文）' : '（无文本）') }}</p>
              </div>
            </template>
            <template v-else>
              <div class="cue-marker">AI</div>
              <div class="cue-body">
                <div class="cue-meta">
                  <strong>{{ item.cue.push_log_id === selectedPushLogId ? '当前提示' : '同会话其他提示' }}</strong>
                  <span>发送给 {{ item.cue.target_user_name }}</span>
                  <span>{{ formatTimeToCST(item.timestamp) }}</span>
                </div>
                <p>{{ item.cue.push_content }}</p>
              </div>
            </template>
          </div>
          <div class="timeline-bottom-space" aria-hidden="true" />
        </div>
        <el-empty v-else description="请从左侧选择一条提示" />
      </main>

      <aside class="coding-pane pane-card">
        <div class="pane-heading">
          <div>
            <strong>当前提示编码</strong>
            <span>编码身份：primary</span>
          </div>
        </div>
        <div v-if="selectedEvent" class="coding-form">
          <section class="selected-cue">
            <header class="review-block-heading"><strong>提示原文</strong><span>生成时记录</span></header>
            <div><span>提示对象</span><strong>{{ selectedEvent.target_user_name }}</strong></div>
            <p>{{ selectedEvent.push_content }}</p>
            <small>{{ formatDateTimeToCST(selectedEvent.received_at) }}</small>
            <details :key="selectedEvent.push_log_id" class="generation-basis">
              <summary>生成依据</summary>
              <div class="generation-basis-content">
                <template v-if="selectedEvent.generation_analysis || selectedEvent.generation_anchor?.text">
                  <strong>生成理由</strong>
                  <p>{{ selectedEvent.generation_analysis || '未记录生成理由' }}</p>
                  <strong>对应原发言<span v-if="selectedEvent.generation_anchor?.speaker_name"> · {{ selectedEvent.generation_anchor.speaker_name }}</span></strong>
                  <p>{{ selectedEvent.generation_anchor?.text || '未记录对应原发言' }}</p>
                  <small>生成时的记录，仅帮助理解提示意图，不代表后续讨论证据。</small>
                </template>
                <p v-else>无生成依据</p>
              </div>
            </details>
          </section>

          <section v-if="currentRelated?.interpretation" class="cue-ai-analysis" aria-label="AI 提示分析">
            <header class="review-block-heading"><strong>AI 分析</strong><span>辅助参考</span></header>
            <strong>提示含义</strong>
            <p>{{ currentRelated.interpretation }}</p>
            <template v-if="currentRelated.suggested_code">
              <div class="ai-recommendation-label"><strong>推荐编码</strong><span>{{ codeMeta(currentRelated.suggested_code)?.label }}</span></div>
              <p>{{ currentRelated.coding_reason }}</p>
              <small>仅回答或展开问题不自动算采纳，需有用于小组判断的明确证据。提示前已有讨论或提示重叠需人工核对；相关高亮不等于正式证据。</small>
              <el-button size="small" plain :disabled="loadingContext || saving || relatedPending.has(selectedPushLogId) || relatedMatches.length !== currentRelated.matches.length" @click="applySuggestedCode">采用推荐编码</el-button>
            </template>
          </section>

          <div class="manual-coding-heading">人工编码</div>
          <el-radio-group v-model="form.uptake_code" class="code-options" @change="markDirty">
            <el-radio
              v-for="option in CODE_OPTIONS"
              :key="option.value"
              :value="option.value"
              border
              :class="`code-option--${option.value}`"
            >
              <div class="code-option-copy">
                <strong>{{ option.label }}</strong>
                <span>{{ option.definition }}</span>
              </div>
            </el-radio>
          </el-radio-group>

          <section class="evidence-box">
            <div class="section-title">
              <strong>已选证据发言</strong>
              <span>{{ selectedEvidence.length }} 条</span>
            </div>
            <div v-if="selectedEvidence.length" class="evidence-list">
              <div v-for="evidence in selectedEvidence" :key="evidence.transcript_id" class="evidence-item">
                <div><strong>{{ evidence.speaker_name }}</strong><span>{{ formatTimeToCST(evidence.start ?? evidence.created_at) }}</span></div>
                <p>{{ evidence.text || '（无文本）' }}</p>
                <el-button link type="danger" @click="toggleEvidence(evidence)">移除</el-button>
              </div>
            </div>
            <p v-else class="empty-hint">在中间讨论文本中点击“选为证据”。</p>
          </section>

          <label class="field-label">判断说明</label>
          <el-input
            v-model="form.coding_reason"
            type="textarea"
            :rows="3"
            :placeholder="form.uptake_code === 'uncertain' ? '无法判断时必填' : '可选：记录判断依据或补充说明'"
            @input="markDirty"
          />

          <label class="field-label">编码者</label>
          <el-input v-model="form.coded_by" placeholder="可选：填写姓名或代号" @input="markDirty" />

          <div v-if="selectedEvent.coding" class="saved-meta">
            上次保存：{{ formatDateTimeToCST(selectedEvent.coding.coded_at) }}
          </div>
          <div v-if="dirty" class="dirty-note">当前有尚未保存的修改</div>

          <div class="coding-actions">
            <el-button type="primary" :loading="saving" @click="handleSave(true)">保存并下一条</el-button>
            <el-button :loading="saving" @click="handleSave(false)">仅保存</el-button>
            <el-button
              v-if="selectedEvent.coding"
              type="danger"
              plain
              :loading="saving"
              @click="handleDeleteCoding"
            >清除编码</el-button>
          </div>
        </div>
        <el-empty v-else description="尚未选择提示" :image-size="80" />
      </aside>
    </section>
  </div>
</template>

<style scoped>
.cue-page { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.page-header h1 { margin: 0; color: #1e2d40; font-size: 20px; font-weight: 700; }
.page-header p { margin: 6px 0 0; color: #68778e; font-size: 14px; }
.filter-card { border: 1px solid #e3e9f2; }
.filters { display: grid; grid-template-columns: 140px 180px 210px 140px 150px minmax(180px, 1fr) auto; gap: 10px; }
.filter-actions { display: flex; white-space: nowrap; }
.progress-strip { display: grid; grid-template-columns: minmax(270px, 1.6fr) repeat(6, minmax(88px, .55fr)); gap: 1px; overflow: hidden; border: 1px solid #e3e9f2; border-radius: 8px; background: #e3e9f2; }
.progress-main, .progress-count { min-height: 58px; padding: 10px 14px; background: #fff; box-sizing: border-box; }
.progress-main { display: grid; grid-template-columns: auto auto minmax(110px, 1fr); align-items: center; gap: 10px; }
.progress-main :deep(.el-progress) { width: 100%; }
.progress-label, .progress-count span { color: #718098; font-size: 13px; }
.progress-main strong, .progress-count strong { color: #1e2d40; font-size: 17px; }
.progress-count { display: flex; flex-direction: column; justify-content: center; gap: 3px; }
.coding-workbench { display: grid; grid-template-columns: 286px minmax(430px, 1fr) 350px; gap: 12px; height: calc(100vh - 260px); min-height: 570px; }
.pane-card { min-width: 0; overflow: hidden; border: 1px solid #dfe6ef; border-radius: 9px; background: #fff; box-shadow: 0 4px 14px rgba(31, 45, 67, .04); }
.pane-heading { display: flex; min-height: 58px; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid #e7ecf3; box-sizing: border-box; }
.pane-heading > div { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.pane-heading strong { color: #24344a; font-size: 15px; }
.pane-heading span { overflow: hidden; color: #7a8799; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.event-pane, .timeline-pane, .coding-pane { display: flex; flex-direction: column; }
.event-list { flex: 1; overflow-y: auto; padding: 8px; }
.event-card { display: block; width: 100%; margin: 0 0 8px; padding: 11px; border: 1px solid #e3e9f1; border-radius: 8px; background: #fff; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.event-card:hover { border-color: #9eb7d5; background: #f8fbff; }
.event-card.active { border-color: #3b82f6; background: #eff6ff; box-shadow: inset 3px 0 #3b82f6; }
.event-card__top, .event-card__meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.event-target { color: #26364b; font-size: 14px; font-weight: 700; }
.event-card p { display: -webkit-box; overflow: hidden; margin: 8px 0; color: #425269; font-size: 14px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.event-card__meta { margin-bottom: 6px; color: #8a96a8; font-size: 12px; }
.event-pagination { display: flex; min-height: 48px; align-items: center; justify-content: center; padding: 4px 6px; border-top: 1px solid #e7ecf3; }
.member-count { flex: 0 0 auto; color: #68778e; font-size: 13px; }
.timeline-scroll { flex: 1; overflow-y: auto; padding: 18px 20px 36px; }
.timeline-bottom-space { height: calc(100% - 110px); min-height: 260px; }
.timeline-entry { display: flex; gap: 10px; margin-bottom: 17px; scroll-margin: 120px 0; }
.timeline-avatar, .cue-marker { display: grid; flex: 0 0 auto; width: 34px; height: 34px; place-items: center; border-radius: 50%; background: #edf2f7; color: #516178; font-size: 13px; font-weight: 700; }
.transcript-body { min-width: 0; flex: 1; padding: 10px 12px; border: 1px solid #e6ebf2; border-radius: 4px 10px 10px; background: #fff; }
.transcript-meta { display: flex; align-items: center; gap: 9px; }
.transcript-meta strong { color: #26364b; font-size: 14px; }
.transcript-meta span { color: #8995a6; font-size: 12px; }
.transcript-meta .evidence-button { margin-left: auto; }
.transcript-body p, .cue-body p { margin: 7px 0 0; color: #35455b; font-size: 14px; line-height: 1.65; white-space: pre-wrap; }
.timeline-entry--evidence .transcript-body { border-color: #72c796; background: #f0fdf4; box-shadow: inset 3px 0 #22a65a; }
.timeline-entry--related .transcript-body { border-color: #e6bd58; background: #fffbeb; }
.timeline-entry--related.timeline-entry--evidence .transcript-body { box-shadow: inset 3px 0 #22a65a; }
.related-toolbar { padding: 10px 16px; border-bottom: 1px solid #e6eaf0; display: flex; flex-direction: column; gap: 7px; }
.related-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 13px; }
.related-controls .el-button + .el-button { margin-left: 0; }
.related-toolbar small { color: #77859a; font-size: 12px; }
.related-error { color: #c0392b; font-size: 13px; overflow-wrap: anywhere; }
.timeline-entry--cue { margin: 24px 0; }
.timeline-entry--cue .cue-marker { background: #eef2ff; color: #4f46e5; }
.cue-body { min-width: 0; flex: 1; padding: 12px 14px; border: 1px dashed #aab8d0; border-radius: 9px; background: #f8faff; }
.timeline-entry--current .cue-marker { background: #2563eb; color: #fff; }
.timeline-entry--current .cue-body { border: 2px solid #3b82f6; background: #eff6ff; box-shadow: 0 8px 20px rgba(59, 130, 246, .12); }
.cue-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; color: #6f7d91; font-size: 12px; }
.cue-meta strong { color: #315b9b; font-size: 14px; }
.coding-pane { overflow-y: auto; }
.coding-pane > .pane-heading { flex: 0 0 auto; }
.coding-form { padding: 14px; }
.selected-cue { padding: 14px; border: 1px solid #e9d5ac; border-left: 3px solid #b88635; border-radius: 9px; background: #fffaf0; }
.selected-cue > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.selected-cue span, .selected-cue small { color: #7b6a50; font-size: 12px; }
.selected-cue strong { color: #293a51; font-size: 14px; }
.selected-cue p { margin: 10px 0; color: #493c2b; font-size: 15px; line-height: 1.7; white-space: pre-wrap; }
.code-options { display: flex; flex-direction: column; align-items: stretch; gap: 8px; margin-top: 12px; }
.code-options :deep(.el-radio) { width: 100%; height: auto; margin: 0; padding: 10px 11px; box-sizing: border-box; }
.code-options :deep(.el-radio__label) { min-width: 0; padding-left: 8px; white-space: normal; }
.code-options :deep(.el-radio.is-bordered.is-checked) { box-shadow: 0 4px 12px color-mix(in srgb, var(--cue-code-color) 14%, transparent); }
.code-options :deep(.el-radio.is-checked .el-radio__inner) { border-color: var(--cue-code-color); background: var(--cue-code-color); }
.code-options :deep(.el-radio.is-checked .el-radio__label) { color: var(--cue-code-color); }
.code-options :deep(.el-radio.is-bordered.is-checked) { border-color: var(--cue-code-color); background: var(--cue-code-bg); }
.code-option--not_discussed { --cue-code-color: #64748b; --cue-code-bg: #f1f5f9; }
.code-option--discussed_not_adopted { --cue-code-color: #d97706; --cue-code-bg: #fffbeb; }
.code-option--discussed_adopted { --cue-code-color: #15803d; --cue-code-bg: #f0fdf4; }
.code-option--uncertain { --cue-code-color: #7c3aed; --cue-code-bg: #f5f3ff; }
.code-option--not_included { --cue-code-color: #be123c; --cue-code-bg: #fff1f2; }
.code-option-copy { display: flex; flex-direction: column; gap: 3px; }
.code-option-copy strong { color: #26364b; font-size: 14px; }
.code-option-copy span { color: #64748b; font-size: 13px; line-height: 1.65; }
.evidence-box { margin-top: 18px; padding: 14px; border: 1px solid #b9dccf; border-left: 3px solid #438770; border-radius: 9px; background: #f3faf7; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.section-title strong, .field-label { color: #34445a; font-size: 13px; font-weight: 700; }
.section-title span { color: #718098; font-size: 12px; }
.evidence-list { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.evidence-item { padding: 12px; border: 1px solid #deeee6; border-radius: 7px; background: #fff; }
.evidence-item > div { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 6px 10px; }
.evidence-item strong { color: #28634f; font-size: 13px; }
.evidence-item span { color: #617e70; font-size: 12px; font-variant-numeric: tabular-nums; }
.evidence-item p { max-height: 180px; overflow-y: auto; margin: 8px 0; color: #344c40; font-size: 14px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.empty-hint { margin: 10px 0 0; color: #617e70; font-size: 13px; line-height: 1.6; }
.field-label { display: block; margin: 14px 0 6px; }
.saved-meta, .dirty-note { margin-top: 9px; color: #8491a3; font-size: 12px; }
.dirty-note { color: #b7791f; }
.coding-actions { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }
.coding-actions .el-button + .el-button { margin-left: 0; }
.raw-transcript-popover { color: #526176; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
@media (max-width: 1350px) {
  .filters { grid-template-columns: repeat(4, minmax(140px, 1fr)); }
  .coding-workbench { grid-template-columns: 250px minmax(420px, 1fr) 320px; }
}
.generation-basis { margin-top: 12px; border-top: 1px solid #eadcbe; padding-top: 10px; }
.generation-basis summary { cursor: pointer; color: #856020; font-size: 13px; font-weight: 600; }
.generation-basis summary:focus-visible { outline: 2px solid #b88635; outline-offset: 4px; border-radius: 3px; }
.cue-ai-analysis { margin: 16px 0; padding: 14px; border: 1px solid #d9ccec; border-left: 3px solid #8b6bb1; border-radius: 9px; background: #f8f5fc; overflow-wrap: anywhere; }
.cue-ai-analysis strong { display: block; color: #654884; font-size: 13px; }
.cue-ai-analysis p { margin: 7px 0 14px; font-size: 14px; color: #443b50; line-height: 1.75; white-space: pre-wrap; }
.cue-ai-analysis small { display: block; color: #756781; font-size: 12px; line-height: 1.65; margin-bottom: 12px; }
.generation-basis-content { max-height: 280px; overflow-y: auto; margin-top: 10px; padding: 12px; border-radius: 6px; background: #f5eddc; overflow-wrap: anywhere; }
.generation-basis-content > strong { display: block; font-size: 13px; color: #775723; }
.generation-basis-content p { white-space: pre-wrap; font-size: 14px; line-height: 1.7; margin: 6px 0 14px; }
.generation-basis-content small { display: block; line-height: 1.6; }
.coding-pane .review-block-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px 10px; margin-bottom: 14px; }
.coding-pane .review-block-heading strong { font-size: 14px; font-weight: 650; color: #856020; }
.coding-pane .review-block-heading span { padding: 2px 7px; border-radius: 4px; background: #f2e6cc; color: #795d2d; font-size: 11px; line-height: 1.5; }
.cue-ai-analysis .review-block-heading strong { color: #654884; }
.cue-ai-analysis .review-block-heading span { background: #eae1f3; color: #6c508d; }
.ai-recommendation-label { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding-top: 12px; border-top: 1px solid #e5dced; }
.ai-recommendation-label > span { font-size: 13px; font-weight: 600; color: #654884; background: #eae1f3; border-radius: 5px; padding: 3px 8px; }
.cue-ai-analysis :deep(.el-button) { --el-button-text-color: #654884; --el-button-border-color: #cdbbdf; --el-button-bg-color: #fff; --el-button-hover-text-color: #53356f; --el-button-hover-border-color: #8b6bb1; --el-button-hover-bg-color: #eee7f5; }
.manual-coding-heading { margin-top: 20px; padding-top: 16px; border-top: 1px solid #e3e8ef; font-size: 14px; font-weight: 650; color: #34445a; }
</style>

<style scoped src="../../styles/review-workspace.css"></style>
