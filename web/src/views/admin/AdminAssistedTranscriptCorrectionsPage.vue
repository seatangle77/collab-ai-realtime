<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTimeToCST, formatTimeToCST } from '../../utils/datetime'
import {
  getSessionUtterances,
  type UtteranceOut,
} from '../../api/admin/coi-transcript-coding'
import {
  deleteTranscriptCorrection,
  listCorrectableTranscripts,
  listTranscriptCorrectionGroups,
  listTranscriptCorrectionSessions,
  saveTranscriptCorrection,
  type AssistedCondition,
  type CorrectableTranscript,
  type CorrectionStatus,
  type TranscriptCorrectionGroup,
  type TranscriptCorrectionSession,
} from '../../api/admin/transcript-corrections'

const CONDITION_LABELS: Record<AssistedCondition, string> = {
  glasses: '眼镜',
  app_notification: 'App 通知',
}

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
const pageSize = ref(100)
const total = ref(0)
const dirty = ref(false)
const selectedReferenceOrder = ref<number | null>(null)
const referenceElements = new Map<number, HTMLElement>()

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
const selectedTranscript = computed(() =>
  transcripts.value.find(item => item.transcript_id === selectedTranscriptId.value) ?? null,
)
const selectedReference = computed(() =>
  referenceUtterances.value.find(item => item.order_index === selectedReferenceOrder.value) ?? null,
)
const uncorrectedCount = computed(() => {
  const session = currentSession.value
  return session ? session.transcript_count - session.corrected_count : 0
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

function setReferenceElement(orderIndex: number, element: unknown) {
  if (element instanceof HTMLElement) referenceElements.set(orderIndex, element)
  else referenceElements.delete(orderIndex)
}

function transcriptRelativeSeconds(transcript: CorrectableTranscript): number | null {
  const sessionStartedAt = currentSession.value?.started_at
  if (!transcript.start || !sessionStartedAt) return null
  const transcriptMs = Date.parse(transcript.start)
  const sessionMs = Date.parse(sessionStartedAt)
  if (!Number.isFinite(transcriptMs) || !Number.isFinite(sessionMs)) return null
  return (transcriptMs - sessionMs) / 1000
}

async function locateClosestReference(transcript: CorrectableTranscript) {
  const relativeSeconds = transcriptRelativeSeconds(transcript)
  if (relativeSeconds == null) return
  const timed = referenceUtterances.value.filter(item => item.start_time != null)
  if (!timed.length) return
  const closest = timed.reduce((best, item) =>
    Math.abs((item.start_time ?? 0) - relativeSeconds)
      < Math.abs((best.start_time ?? 0) - relativeSeconds)
      ? item
      : best,
  )
  selectedReferenceOrder.value = closest.order_index
  await nextTick()
  referenceElements.get(closest.order_index)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
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
    if (selectedTranscript.value) await locateClosestReference(selectedTranscript.value)
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
  sessions.value = []
  selectedSessionId.value = ''
  loadedSessionId.value = ''
  transcripts.value = []
  referenceUtterances.value = []
  selectedReferenceOrder.value = null
  selectedTranscriptId.value = ''
  fillForm(null)
  if (!groupId) return
  loadingSessions.value = true
  try {
    sessions.value = await listTranscriptCorrectionSessions(groupId)
    loadedGroupId.value = groupId
    if (selectFirst && sessions.value[0]) {
      selectedSessionId.value = sessions.value[0].session_id
      loadedSessionId.value = selectedSessionId.value
      await Promise.all([
        loadTranscripts(true),
        loadReferenceUtterances(selectedSessionId.value),
      ])
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

async function loadTranscripts(selectFirst = true) {
  if (!selectedSessionId.value) return
  loadingTranscripts.value = true
  try {
    const response = await listCorrectableTranscripts(selectedSessionId.value, {
      page: page.value,
      page_size: pageSize.value,
      correction_status: filters.correction_status || undefined,
      speaker: filters.speaker.trim() || undefined,
      keyword: filters.keyword.trim() || undefined,
    })
    transcripts.value = response.items
    total.value = response.meta.total
    page.value = response.meta.page
    pageSize.value = response.meta.page_size
    loadedSessionId.value = selectedSessionId.value
    selectedTranscriptId.value = ''
    fillForm(null)
    if (selectFirst && transcripts.value[0]) {
      selectTranscript(transcripts.value[0], false)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载转写失败')
  } finally {
    loadingTranscripts.value = false
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
  await Promise.all([
    loadTranscripts(true),
    loadReferenceUtterances(sessionId),
  ])
}

async function selectTranscript(transcript: CorrectableTranscript, askBeforeSwitch = true) {
  if (transcript.transcript_id === selectedTranscriptId.value) return
  if (askBeforeSwitch && !(await confirmDiscard())) return
  selectedTranscriptId.value = transcript.transcript_id
  fillForm(transcript)
  await locateClosestReference(transcript)
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

function updateCorrectionCounts(wasCorrected: boolean, isCorrected: boolean) {
  if (wasCorrected === isCorrected) return
  const delta = isCorrected ? 1 : -1
  const session = currentSession.value
  if (session) session.corrected_count += delta
  const group = groups.value.find(item => item.group_id === selectedGroupId.value)
  if (group) group.corrected_count += delta
}

async function handleSave(moveNext: boolean) {
  const transcript = selectedTranscript.value
  const correctedText = form.corrected_text.trim()
  if (!transcript) return
  if (!correctedText) {
    ElMessage.warning('修订文本不能为空')
    return
  }
  const wasCorrected = transcript.is_corrected
  saving.value = true
  try {
    const correction = await saveTranscriptCorrection(transcript.transcript_id, {
      corrected_text: correctedText,
      correction_reason: form.correction_reason.trim() || null,
      corrected_by: form.corrected_by.trim() || null,
    })
    transcript.effective_text = correction.corrected_text
    transcript.is_corrected = true
    transcript.correction_id = correction.id
    transcript.correction_reason = correction.correction_reason
    transcript.corrected_by = correction.corrected_by
    transcript.corrected_at = correction.updated_at
    updateCorrectionCounts(wasCorrected, true)
    dirty.value = false
    ElMessage.success('修订已保存，原始转写未修改')
    if (moveNext) await selectNextTranscript(transcript.transcript_id)
  } catch (error: any) {
    ElMessage.error(error?.message || '保存修订失败')
  } finally {
    saving.value = false
  }
}

async function selectNextTranscript(currentId: string) {
  const index = transcripts.value.findIndex(item => item.transcript_id === currentId)
  const next = transcripts.value[index + 1]
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
    await deleteTranscriptCorrection(transcript.transcript_id)
    transcript.effective_text = transcript.original_text
    transcript.is_corrected = false
    transcript.correction_id = null
    transcript.correction_reason = null
    transcript.corrected_by = null
    transcript.corrected_at = null
    updateCorrectionCounts(true, false)
    fillForm(transcript)
    ElMessage.success('修订已清除，已恢复原始转写')
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
</script>

<template>
  <div class="correction-page">
    <header class="page-header">
      <div>
        <h1>提示转写修订</h1>
        <p>对照同一会话已保存的录音重转译内容，修订辅助条件小组的实时转写；两份原始数据均不修改。</p>
      </div>
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

    <section class="correction-workbench">
      <main class="transcript-pane pane-card">
        <div class="pane-heading">
          <div><strong>会话转写</strong><span>当前筛选共 {{ total }} 条</span></div>
        </div>
        <div v-loading="loadingTranscripts" class="transcript-list">
          <button
            v-for="transcript in transcripts"
            :key="transcript.transcript_id"
            type="button"
            class="transcript-row"
            :class="{
              active: transcript.transcript_id === selectedTranscriptId,
              corrected: transcript.is_corrected,
            }"
            @click="selectTranscript(transcript)"
          >
            <div class="transcript-row__meta">
              <strong>{{ transcript.speaker_name }}</strong>
              <span>{{ formatTimeToCST(transcript.start ?? transcript.created_at) }}</span>
              <el-tag v-if="transcript.is_corrected" type="warning" size="small">已修订</el-tag>
              <el-tag v-else type="info" size="small" effect="plain">未修订</el-tag>
            </div>
            <p>{{ transcript.effective_text || '（无文本）' }}</p>
          </button>
          <el-empty v-if="!loadingTranscripts && transcripts.length === 0" description="没有符合条件的转写" />
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
            :class="{ active: utterance.order_index === selectedReferenceOrder }"
            @click="selectReference(utterance)"
          >
            <div class="reference-row__meta">
              <strong>#{{ utterance.order_index }}</strong>
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
          有时间戳时会自动定位到最接近的参考句，也可以手动选择。
        </div>
      </section>

      <aside class="editor-pane pane-card">
        <div class="pane-heading">
          <div><strong>当前转写修订</strong><span>所有修改只写入修订表</span></div>
        </div>
        <div v-if="selectedTranscript" class="editor-form">
          <div class="speaker-card">
            <div><strong>{{ selectedTranscript.speaker_name }}</strong><span>{{ formatDateTimeToCST(selectedTranscript.start ?? selectedTranscript.created_at) }}</span></div>
            <small>转写 ID：{{ selectedTranscript.transcript_id }}</small>
          </div>

          <label>原始转写（只读）</label>
          <div class="original-text">{{ selectedTranscript.original_text || '（原始文本为空）' }}</div>

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
        <el-empty v-else description="请选择一条转写" />
      </aside>
    </section>
  </div>
</template>

<style scoped>
.correction-page { display: flex; flex-direction: column; gap: 14px; min-width: 1180px; }
.page-header h1 { margin: 0; color: #1e2d40; font-size: 20px; }
.page-header p { margin: 6px 0 0; color: #68778e; font-size: 14px; }
.filter-card { border: 1px solid #e3e9f2; }
.filters { display: grid; grid-template-columns: 140px 180px 230px 140px 160px minmax(180px, 1fr) auto; gap: 10px; }
.filter-actions { display: flex; white-space: nowrap; }
.summary-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; overflow: hidden; border: 1px solid #e3e9f2; border-radius: 8px; background: #e3e9f2; }
.summary-strip > div { display: flex; min-height: 58px; flex-direction: column; justify-content: center; gap: 4px; padding: 9px 16px; background: #fff; }
.summary-strip span { color: #748196; font-size: 12px; }
.summary-strip strong { color: #26364b; font-size: 16px; }
.summary-strip .corrected-number { color: #b45309; }
.correction-workbench { display: grid; grid-template-columns: minmax(360px, 1fr) minmax(330px, .9fr) minmax(370px, 1fr); gap: 12px; height: calc(100vh - 260px); min-height: 570px; }
.pane-card { display: flex; min-width: 0; flex-direction: column; overflow: hidden; border: 1px solid #dfe6ef; border-radius: 9px; background: #fff; box-shadow: 0 4px 14px rgba(31, 45, 67, .04); }
.pane-heading { display: flex; min-height: 58px; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-bottom: 1px solid #e7ecf3; box-sizing: border-box; }
.pane-heading > div { display: flex; flex-direction: column; gap: 3px; }
.pane-heading strong { color: #24344a; font-size: 15px; }
.pane-heading span { color: #7a8799; font-size: 12px; }
.transcript-list { flex: 1; overflow-y: auto; padding: 10px; }
.transcript-row { display: block; width: 100%; margin-bottom: 8px; padding: 11px 13px; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.transcript-row:hover { border-color: #a8b9cf; background: #f8fafc; }
.transcript-row.active { border-color: #3b82f6; background: #eff6ff; box-shadow: inset 3px 0 #3b82f6; }
.transcript-row.corrected:not(.active) { border-color: #f3c477; background: #fffbeb; }
.transcript-row__meta { display: flex; align-items: center; gap: 9px; }
.transcript-row__meta strong { color: #26364b; font-size: 13px; }
.transcript-row__meta span { margin-right: auto; color: #8995a6; font-size: 11px; }
.transcript-row p { margin: 7px 0 0; color: #405067; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.pagination { display: flex; min-height: 52px; align-items: center; justify-content: flex-end; padding: 5px 12px; border-top: 1px solid #e7ecf3; }
.reference-list { flex: 1; overflow-y: auto; padding: 10px; }
.reference-row { display: block; width: 100%; margin-bottom: 8px; padding: 10px 12px; border: 1px solid #dfe8e4; border-radius: 8px; background: #fbfefc; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.reference-row:hover { border-color: #8fc4aa; background: #f2fbf6; }
.reference-row.active { border-color: #22a06b; background: #ecfdf5; box-shadow: inset 3px 0 #22a06b; }
.reference-row__meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.reference-row__meta strong { color: #217052; font-size: 12px; }
.reference-row__meta span { color: #87968f; font-size: 11px; }
.reference-row p { margin: 6px 0 0; color: #40574d; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.reference-note { padding: 9px 12px; border-top: 1px solid #e7ecf3; color: #7b8b84; font-size: 11px; line-height: 1.5; }
.editor-pane { overflow-y: auto; }
.editor-pane .pane-heading { flex: 0 0 auto; }
.editor-form { display: flex; flex-direction: column; padding: 16px; }
.speaker-card { padding: 11px 12px; border-radius: 8px; background: #f4f7fb; }
.speaker-card > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.speaker-card strong { color: #26364b; font-size: 14px; }
.speaker-card span, .speaker-card small { color: #7b8798; font-size: 11px; }
.speaker-card small { display: block; margin-top: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.editor-form label { margin: 14px 0 6px; color: #34445a; font-size: 12px; font-weight: 700; }
.original-text { min-height: 86px; padding: 11px 12px; border: 1px solid #e2e8f0; border-radius: 7px; background: #f8fafc; color: #536176; font-size: 14px; line-height: 1.65; white-space: pre-wrap; }
.selected-reference { padding: 10px 11px; border: 1px solid #b9dfcc; border-radius: 7px; background: #f2fbf6; }
.selected-reference > div:first-child { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.selected-reference strong { color: #217052; font-size: 12px; }
.selected-reference span { color: #7c9187; font-size: 11px; }
.selected-reference p { margin: 7px 0 9px; color: #40574d; font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
.reference-actions { display: flex; gap: 6px; }
.reference-actions .el-button + .el-button { margin-left: 0; }
.saved-meta, .dirty-note { margin-top: 10px; color: #8390a2; font-size: 11px; }
.dirty-note { color: #b7791f; }
.editor-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.editor-actions .el-button + .el-button { margin-left: 0; }
@media (max-width: 1300px) {
  .filters { grid-template-columns: repeat(4, minmax(150px, 1fr)); }
}
</style>
