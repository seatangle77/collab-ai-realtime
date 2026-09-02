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
    definition: '后续讨论中没有把该提示内容拿出来讨论。',
    type: 'info',
  },
  {
    value: 'discussed_not_adopted',
    label: '讨论未采纳',
    short: '未采纳',
    definition: '提示被拿出来讨论，但没有被接受或用于推进讨论。',
    type: 'warning',
  },
  {
    value: 'discussed_adopted',
    label: '讨论并采纳',
    short: '已采纳',
    definition: '提示经过讨论后被认为有用，并用于形成观点或推进讨论。',
    type: 'success',
  },
  {
    value: 'uncertain',
    label: '无法判断',
    short: '无法判断',
    definition: '现有文本或其他材料不足以作出判断。',
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
const contextCache = new Map<string, CueSessionContext>()
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
  return (context.value?.transcripts ?? []).filter(item => idSet.has(item.transcript_id))
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
  const cacheKey = `${event.session_id}:${CODER_ROLE}`
  loadingContext.value = true
  try {
    let sessionContext = contextCache.get(cacheKey)
    if (!sessionContext) {
      sessionContext = await getCueSessionContext(event.session_id, CODER_ROLE)
      contextCache.set(cacheKey, sessionContext)
    }
    context.value = sessionContext
    nextTick(() => {
      const container = timelineScrollRef.value
      const target = document.getElementById(`cue-timeline-${event.push_log_id}`)
      if (!container || !target) return
      const top = target.getBoundingClientRect().top
        - container.getBoundingClientRect().top
        + container.scrollTop
      container.scrollTo({ top, behavior: 'auto' })
    })
  } catch (error: any) {
    context.value = null
    ElMessage.error(error?.message || '加载会话上下文失败')
  } finally {
    loadingContext.value = false
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

function toggleEvidence(transcriptId: string) {
  const index = form.evidence_transcript_ids.indexOf(transcriptId)
  if (index >= 0) form.evidence_transcript_ids.splice(index, 1)
  else form.evidence_transcript_ids.push(transcriptId)
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
    const cachedContext = contextCache.get(`${event.session_id}:${CODER_ROLE}`)
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
    const cachedContext = contextCache.get(`${event.session_id}:${CODER_ROLE}`)
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
  <div class="cue-page">
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
          <span v-if="context" class="member-count">{{ context.members.length }} 名成员</span>
        </div>
        <div v-if="context" ref="timelineScrollRef" class="timeline-scroll">
          <div
            v-for="item in timelineItems"
            :id="item.kind === 'cue' ? `cue-timeline-${item.cue.push_log_id}` : undefined"
            :key="item.id"
            class="timeline-entry"
            :class="{
              'timeline-entry--cue': item.kind === 'cue',
              'timeline-entry--current': item.kind === 'cue' && item.cue.push_log_id === selectedPushLogId,
              'timeline-entry--evidence': item.kind === 'transcript' && form.evidence_transcript_ids.includes(item.transcript.transcript_id),
            }"
          >
            <template v-if="item.kind === 'transcript'">
              <div class="timeline-avatar">{{ item.transcript.speaker_name.slice(0, 1) }}</div>
              <div class="transcript-body">
                <div class="transcript-meta">
                  <strong>{{ item.transcript.speaker_name }}</strong>
                  <span>{{ formatTimeToCST(item.timestamp) }}</span>
                  <el-tag v-if="item.transcript.is_corrected" type="warning" size="small" effect="plain">已修订</el-tag>
                  <el-popover v-if="item.transcript.is_corrected" placement="top" width="360" trigger="click">
                    <template #reference><el-button link type="info">查看原文</el-button></template>
                    <div class="raw-transcript-popover">{{ item.transcript.original_text || '（原始文本为空）' }}</div>
                  </el-popover>
                  <el-button
                    class="evidence-button"
                    link
                    :type="form.evidence_transcript_ids.includes(item.transcript.transcript_id) ? 'success' : 'primary'"
                    @click="toggleEvidence(item.transcript.transcript_id)"
                  >
                    {{ form.evidence_transcript_ids.includes(item.transcript.transcript_id) ? '已选证据' : '选为证据' }}
                  </el-button>
                </div>
                <p>{{ item.transcript.text || '（无文本）' }}</p>
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
            <div><span>提示对象</span><strong>{{ selectedEvent.target_user_name }}</strong></div>
            <p>{{ selectedEvent.push_content }}</p>
            <small>{{ formatDateTimeToCST(selectedEvent.received_at) }}</small>
          </section>

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
              <strong>证据发言</strong>
              <span>{{ selectedEvidence.length }} 条</span>
            </div>
            <div v-if="selectedEvidence.length" class="evidence-list">
              <div v-for="evidence in selectedEvidence" :key="evidence.transcript_id" class="evidence-item">
                <div><strong>{{ evidence.speaker_name }}</strong><span>{{ formatTimeToCST(evidence.start ?? evidence.created_at) }}</span></div>
                <p>{{ evidence.text || '（无文本）' }}</p>
                <el-button link type="danger" @click="toggleEvidence(evidence.transcript_id)">移除</el-button>
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
.cue-page { display: flex; flex-direction: column; gap: 14px; min-width: 1000px; }
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
.progress-label, .progress-count span { color: #718098; font-size: 12px; }
.progress-main strong, .progress-count strong { color: #1e2d40; font-size: 17px; }
.progress-count { display: flex; flex-direction: column; justify-content: center; gap: 3px; }
.coding-workbench { display: grid; grid-template-columns: 286px minmax(430px, 1fr) 350px; gap: 12px; height: calc(100vh - 260px); min-height: 570px; }
.pane-card { min-width: 0; overflow: hidden; border: 1px solid #dfe6ef; border-radius: 9px; background: #fff; box-shadow: 0 4px 14px rgba(31, 45, 67, .04); }
.pane-heading { display: flex; min-height: 58px; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid #e7ecf3; box-sizing: border-box; }
.pane-heading > div { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.pane-heading strong { color: #24344a; font-size: 15px; }
.pane-heading span { overflow: hidden; color: #7a8799; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.event-pane, .timeline-pane, .coding-pane { display: flex; flex-direction: column; }
.event-list { flex: 1; overflow-y: auto; padding: 8px; }
.event-card { display: block; width: 100%; margin: 0 0 8px; padding: 11px; border: 1px solid #e3e9f1; border-radius: 8px; background: #fff; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.event-card:hover { border-color: #9eb7d5; background: #f8fbff; }
.event-card.active { border-color: #3b82f6; background: #eff6ff; box-shadow: inset 3px 0 #3b82f6; }
.event-card__top, .event-card__meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.event-target { color: #26364b; font-size: 13px; font-weight: 700; }
.event-card p { display: -webkit-box; overflow: hidden; margin: 8px 0; color: #425269; font-size: 13px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.event-card__meta { margin-bottom: 6px; color: #8a96a8; font-size: 11px; }
.event-pagination { display: flex; min-height: 48px; align-items: center; justify-content: center; padding: 4px 6px; border-top: 1px solid #e7ecf3; }
.member-count { flex: 0 0 auto; color: #68778e; font-size: 12px; }
.timeline-scroll { flex: 1; overflow-y: auto; padding: 18px 20px 36px; }
.timeline-bottom-space { height: calc(100% - 110px); min-height: 260px; }
.timeline-entry { display: flex; gap: 10px; margin-bottom: 17px; scroll-margin: 120px 0; }
.timeline-avatar, .cue-marker { display: grid; flex: 0 0 auto; width: 34px; height: 34px; place-items: center; border-radius: 50%; background: #edf2f7; color: #516178; font-size: 12px; font-weight: 700; }
.transcript-body { min-width: 0; flex: 1; padding: 10px 12px; border: 1px solid #e6ebf2; border-radius: 4px 10px 10px; background: #fff; }
.transcript-meta { display: flex; align-items: center; gap: 9px; }
.transcript-meta strong { color: #26364b; font-size: 13px; }
.transcript-meta span { color: #8995a6; font-size: 11px; }
.transcript-meta .evidence-button { margin-left: auto; }
.transcript-body p, .cue-body p { margin: 7px 0 0; color: #35455b; font-size: 14px; line-height: 1.65; white-space: pre-wrap; }
.timeline-entry--evidence .transcript-body { border-color: #72c796; background: #f0fdf4; box-shadow: inset 3px 0 #22a65a; }
.timeline-entry--cue { margin: 24px 0; }
.timeline-entry--cue .cue-marker { background: #eef2ff; color: #4f46e5; }
.cue-body { min-width: 0; flex: 1; padding: 12px 14px; border: 1px dashed #aab8d0; border-radius: 9px; background: #f8faff; }
.timeline-entry--current .cue-marker { background: #2563eb; color: #fff; }
.timeline-entry--current .cue-body { border: 2px solid #3b82f6; background: #eff6ff; box-shadow: 0 8px 20px rgba(59, 130, 246, .12); }
.cue-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; color: #6f7d91; font-size: 11px; }
.cue-meta strong { color: #315b9b; font-size: 13px; }
.coding-pane { overflow-y: auto; }
.coding-pane > .pane-heading { flex: 0 0 auto; }
.coding-form { padding: 14px; }
.selected-cue { padding: 11px 12px; border-radius: 8px; background: #f4f7fb; }
.selected-cue > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.selected-cue span, .selected-cue small { color: #77859a; font-size: 11px; }
.selected-cue strong { color: #293a51; font-size: 13px; }
.selected-cue p { margin: 8px 0; color: #34455c; font-size: 13px; line-height: 1.55; white-space: pre-wrap; }
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
.code-option-copy strong { color: #26364b; font-size: 13px; }
.code-option-copy span { color: #748196; font-size: 11px; line-height: 1.45; }
.evidence-box { margin-top: 14px; padding: 10px; border: 1px solid #e2e8f0; border-radius: 8px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.section-title strong, .field-label { color: #34445a; font-size: 12px; font-weight: 700; }
.section-title span { color: #718098; font-size: 11px; }
.evidence-list { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.evidence-item { padding: 8px; border-radius: 6px; background: #f0fdf4; }
.evidence-item > div { display: flex; gap: 8px; }
.evidence-item strong { color: #23663e; font-size: 11px; }
.evidence-item span { color: #789184; font-size: 10px; }
.evidence-item p { display: -webkit-box; overflow: hidden; margin: 4px 0; color: #405749; font-size: 11px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.empty-hint { margin: 8px 0 0; color: #8995a6; font-size: 11px; }
.field-label { display: block; margin: 14px 0 6px; }
.saved-meta, .dirty-note { margin-top: 9px; color: #8491a3; font-size: 11px; }
.dirty-note { color: #b7791f; }
.coding-actions { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }
.coding-actions .el-button + .el-button { margin-left: 0; }
.raw-transcript-popover { color: #526176; font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
@media (max-width: 1350px) {
  .filters { grid-template-columns: repeat(4, minmax(140px, 1fr)); }
  .coding-workbench { grid-template-columns: 250px minmax(420px, 1fr) 320px; }
}
</style>
