<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import {
  listCoiUnits,
  saveCoiUnits,
  type CoiUnit,
} from '../../api/admin/coi-units'
import { getSessionUtterances, type UtteranceOut } from '../../api/admin/coi-transcript-coding'
import type { AdminChatSession, AdminGroup } from '../../types/admin'
import { clearCoiDownstreamDrafts, coiUnitsDraftKey } from '../../utils/coiDraftKeys'

interface DraftUnit {
  key: number
  content: string
  speaker: string | null
  speakerUserId: string | null
  sourceTranscriptIds: string[]
  startTime: number | null
}

interface ReferenceUnit {
  key: number
  content: string
  speaker: string | null
  startTime: number | null
}

interface LocalDraft {
  units: DraftUnit[]
  savedAt: string
}

const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const loadingUnits = ref(false)
const saving = ref(false)
const units = ref<DraftUnit[]>([])
const referenceUnits = ref<ReferenceUnit[]>([])
const referenceFileName = ref('')
let keyCounter = 0
let referenceKeyCounter = 0

const hasDraft = ref(false)
const draftInfo = ref<{ savedAt: string; count: number } | null>(null)
const editingIndex = ref<number | null>(null)
const editingContent = ref('')
const editInputRef = ref<HTMLTextAreaElement[]>([])
const splittingIndex = ref<number | null>(null)
const splitTextareaRef = ref<HTMLTextAreaElement[]>([])

const totalCount = computed(() => units.value.length)

onMounted(async () => {
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page_size: 200 })
    groups.value = res.items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
})

function resetContent() {
  units.value = []
  editingIndex.value = null
  splittingIndex.value = null
  hasDraft.value = false
  draftInfo.value = null
}

async function onGroupChange() {
  selectedSessionId.value = ''
  sessions.value = []
  resetContent()
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  try {
    const res = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = res.items
    if (res.items.length > 0) {
      selectedSessionId.value = res.items[0]!.id
      await loadUnits()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

async function onSessionChange() {
  resetContent()
  await loadUnits()
}

function draftKey() {
  return selectedSessionId.value ? coiUnitsDraftKey(selectedSessionId.value) : ''
}

function checkDraft() {
  const key = draftKey()
  if (!key) return
  const raw = localStorage.getItem(key)
  if (!raw) { hasDraft.value = false; draftInfo.value = null; return }
  try {
    const draft = JSON.parse(raw) as LocalDraft
    hasDraft.value = true
    draftInfo.value = { savedAt: draft.savedAt, count: draft.units.length }
  } catch {
    hasDraft.value = false
    draftInfo.value = null
  }
}

function saveDraft() {
  const key = draftKey()
  if (!key || units.value.length === 0) return
  const draft: LocalDraft = {
    units: units.value,
    savedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  }
  localStorage.setItem(key, JSON.stringify(draft))
  hasDraft.value = true
  draftInfo.value = { savedAt: draft.savedAt, count: draft.units.length }
  ElMessage.success('草稿已保存到本地')
}

function restoreDraft() {
  const key = draftKey()
  if (!key) return
  const raw = localStorage.getItem(key)
  if (!raw) return
  try {
    const draft = JSON.parse(raw) as LocalDraft
    units.value = draft.units
    keyCounter = draft.units.reduce((max, item) => Math.max(max, item.key), 0)
    ElMessage.success(`已恢复草稿：${draft.units.length} 条`)
  } catch {
    ElMessage.error('草稿数据损坏，无法恢复')
  }
}

function clearDraft() {
  const key = draftKey()
  if (!key) return
  localStorage.removeItem(key)
  hasDraft.value = false
  draftInfo.value = null
}

function toDraftUnit(unit: CoiUnit): DraftUnit {
  return {
    key: ++keyCounter,
    content: unit.content,
    speaker: unit.speaker,
    speakerUserId: unit.speaker_user_id,
    sourceTranscriptIds: unit.source_transcript_ids,
    startTime: unit.start_time,
  }
}

function utteranceToDraftUnit(utterance: UtteranceOut): DraftUnit {
  return {
    key: ++keyCounter,
    content: utterance.content,
    speaker: null,
    speakerUserId: null,
    sourceTranscriptIds: [],
    startTime: utterance.start_time,
  }
}

async function loadUnits() {
  if (!selectedSessionId.value) return
  loadingUnits.value = true
  try {
    const res = await listCoiUnits(selectedSessionId.value)
    keyCounter = 0
    units.value = res.map(toDraftUnit)
    checkDraft()
    if (res.length === 0) {
      ElMessage.info('该会话暂无观点单元，可从预处理结果导入')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载观点单元失败')
  } finally {
    loadingUnits.value = false
  }
}

async function loadLatestPreprocess() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  loadingUnits.value = true
  try {
    const res = await getSessionUtterances(selectedSessionId.value)
    keyCounter = 0
    units.value = res.utterances.map(utteranceToDraftUnit)
    editingIndex.value = null
    splittingIndex.value = null
    checkDraft()
    if (res.utterances.length === 0) {
      ElMessage.warning('该会话暂无最新预处理内容，请先在 CoI 预处理页保存')
    } else {
      ElMessage.success(`已加载最新预处理内容：${res.utterances.length} 条`)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载最新预处理内容失败')
  } finally {
    loadingUnits.value = false
  }
}

function fmt(s: number | null): string {
  if (s == null || Number.isNaN(s)) return '--'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1).padStart(4, '0')
  return `${m}:${sec}`
}

function fmtCsvTimestamp(s: number | null): string {
  return s == null || Number.isNaN(s) ? '' : fmt(s)
}

function csvEscape(value: string | number | null | undefined): string {
  const text = String(value ?? '')
  return `"${text.replace(/"/g, '""')}"`
}

function stripBom(text: string): string {
  return text.replace(/^\uFEFF/, '')
}

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  const source = stripBom(text)

  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i]
    const next = source[i + 1]

    if (ch === '"') {
      if (inQuotes && next === '"') {
        field += '"'
        i += 1
      } else {
        inQuotes = !inQuotes
      }
    } else if (ch === ',' && !inQuotes) {
      row.push(field)
      field = ''
    } else if ((ch === '\n' || ch === '\r') && !inQuotes) {
      row.push(field)
      field = ''
      if (row.some(cell => cell.trim() !== '')) rows.push(row)
      row = []
      if (ch === '\r' && next === '\n') i += 1
    } else {
      field += ch
    }
  }

  row.push(field)
  if (row.some(cell => cell.trim() !== '')) rows.push(row)
  return rows
}

function rowsToObjects(rows: string[][]): Record<string, string>[] {
  if (rows.length === 0) return []
  const headers = rows[0]!.map(header => header.trim())
  return rows.slice(1).map(row => {
    const obj: Record<string, string> = {}
    headers.forEach((header, index) => {
      obj[header] = row[index]?.trim() ?? ''
    })
    return obj
  })
}

function parseCsvTimestamp(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const match = trimmed.match(/^(\d+):(\d+(?:\.\d+)?)$/)
  if (!match) return null
  return parseInt(match[1]!, 10) * 60 + parseFloat(match[2]!)
}

function parseReferenceCsv(text: string): ReferenceUnit[] {
  const rows = parseCsvRows(text)
  const headers = rows[0]?.map(header => header.trim()) ?? []
  const contentHeader = headers.includes('观点单元内容')
    ? '观点单元内容'
    : headers.includes('整理后内容')
      ? '整理后内容'
      : ''

  if (!contentHeader) {
    throw new Error('CSV 缺少必要列：观点单元内容 或 整理后内容')
  }

  referenceKeyCounter = 0
  return rowsToObjects(rows)
    .map(row => {
      const content = row[contentHeader]?.trim() ?? ''
      return {
        key: ++referenceKeyCounter,
        content,
        speaker: row['说话人']?.trim() || null,
        startTime: parseCsvTimestamp(row['时间戳'] ?? ''),
      }
    })
    .filter(unit => unit.content)
}

function handleReferenceFileChange(file: UploadFile) {
  const raw = file.raw
  if (!raw) return
  const reader = new FileReader()
  reader.onload = evt => {
    try {
      const text = evt.target?.result as string
      const parsed = parseReferenceCsv(text)
      referenceUnits.value = parsed
      referenceFileName.value = file.name
      if (parsed.length === 0) {
        ElMessage.warning('参考 CSV 未解析到可用观点单元')
      } else {
        ElMessage.success(`已加载参考稿：${parsed.length} 条`)
      }
    } catch (e: any) {
      referenceUnits.value = []
      referenceFileName.value = ''
      ElMessage.error(e?.message || '参考 CSV 解析失败')
    }
  }
  reader.readAsText(raw, 'utf-8')
}

function clearReference() {
  referenceUnits.value = []
  referenceFileName.value = ''
  referenceKeyCounter = 0
}

function exportCSV() {
  if (units.value.length === 0) {
    ElMessage.warning('没有可导出的观点单元')
    return
  }
  const header = ['序号', '时间戳', '说话人', '观点单元内容', '来源转录ID']
  const rows = units.value.map((unit, index) => [
    index + 1,
    fmtCsvTimestamp(unit.startTime),
    unit.speaker ?? '',
    unit.content,
    unit.sourceTranscriptIds.join(';'),
  ])
  const csv = '\uFEFF' + [
    header.map(csvEscape).join(','),
    ...rows.map(row => row.map(csvEscape).join(',')),
  ].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const sessionTitle = sessions.value.find(s => s.id === selectedSessionId.value)?.session_title ?? selectedSessionId.value.slice(0, 8)
  const safeName = sessionTitle.replace(/[/\\:*?"<>|]/g, '_')
  a.download = `coi_units_${safeName}_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function startEdit(index: number) {
  splittingIndex.value = null
  editingIndex.value = index
  editingContent.value = units.value[index]!.content
  nextTick(() => {
    editInputRef.value[0]?.focus()
    editInputRef.value[0]?.select()
  })
}

function confirmEdit() {
  if (editingIndex.value === null) return
  const trimmed = editingContent.value.trim()
  if (trimmed) {
    units.value[editingIndex.value]!.content = trimmed
  }
  editingIndex.value = null
}

function cancelEdit() {
  editingIndex.value = null
}

function onEditKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    confirmEdit()
  } else if (e.key === 'Escape') {
    cancelEdit()
  }
}

function startSplit(index: number) {
  editingIndex.value = null
  splittingIndex.value = index
  nextTick(() => splitTextareaRef.value[0]?.focus())
}

function cancelSplit() {
  splittingIndex.value = null
}

function splitAtCursor() {
  if (splittingIndex.value === null) return
  const textarea = splitTextareaRef.value[0]
  if (!textarea) return
  const pos = textarea.selectionStart
  const unit = units.value[splittingIndex.value]!
  const part1 = textarea.value.slice(0, pos).trim()
  const part2 = textarea.value.slice(pos).trim()
  if (!part1 || !part2) {
    ElMessage.warning('光标位置无法拆分，请将光标放在文字中间')
    return
  }
  unit.content = part1
  units.value.splice(splittingIndex.value + 1, 0, {
    key: ++keyCounter,
    content: part2,
    speaker: unit.speaker,
    speakerUserId: unit.speakerUserId,
    sourceTranscriptIds: unit.sourceTranscriptIds,
    startTime: unit.startTime,
  })
  splittingIndex.value = null
}

function mergeDown(index: number) {
  if (index >= units.value.length - 1) return
  const current = units.value[index]!
  const next = units.value[index + 1]!
  current.content = `${current.content} ${next.content}`
  current.sourceTranscriptIds = Array.from(new Set([...current.sourceTranscriptIds, ...next.sourceTranscriptIds]))
  units.value.splice(index + 1, 1)
}

function deleteUnit(index: number) {
  units.value.splice(index, 1)
}

async function handleSave() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  if (units.value.length === 0) { ElMessage.warning('没有可保存的观点单元'); return }
  try {
    await ElMessageBox.confirm(
      `将保存 ${units.value.length} 条观点单元，并清空该会话已有 A/B/final 编码。确认保存？`,
      '确认保存观点单元',
      { type: 'warning', confirmButtonText: '保存', cancelButtonText: '取消' },
    )
  } catch { return }

  saving.value = true
  try {
    const payload = units.value.map((unit, index) => ({
      order_index: index + 1,
      content: unit.content,
      speaker: unit.speaker,
      speaker_user_id: unit.speakerUserId,
      source_transcript_ids: unit.sourceTranscriptIds,
      start_time: unit.startTime,
    }))
    const res = await saveCoiUnits(selectedSessionId.value, payload)
    clearCoiDownstreamDrafts(selectedSessionId.value)
    await loadUnits()
    ElMessage.success(`观点单元已保存：${res.saved} 条`)
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">CoI 观点整理</h2>
      <span class="header-desc">从最新预处理内容开始整理；保存后才写入正式观点单元</span>
    </div>

    <el-card shadow="never" class="control-card">
      <div class="control-bar">
        <div class="control-left">
          <div class="control-item">
            <span class="control-label">群组</span>
            <el-select
              v-model="selectedGroupId"
              placeholder="选择群组"
              style="width: 200px"
              :loading="loadingGroups"
              filterable
              @change="onGroupChange"
            >
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </div>

          <div v-if="sessions.length > 0" class="control-item">
            <span class="control-label">会话</span>
            <el-select
              v-model="selectedSessionId"
              style="width: 240px"
              :loading="loadingSessions"
              filterable
              @change="onSessionChange"
            >
              <el-option v-for="s in sessions" :key="s.id" :label="s.session_title" :value="s.id" />
            </el-select>
          </div>
        </div>

        <div class="control-right">
          <span v-if="selectedSessionId" class="count-text">右侧 {{ totalCount }} 条</span>
          <el-button
            type="primary"
            plain
            :disabled="!selectedSessionId"
            :loading="loadingUnits"
            @click="loadLatestPreprocess"
          >
            加载最新预处理内容
          </el-button>
          <el-button
            :disabled="!selectedSessionId"
            :loading="loadingUnits"
            @click="loadUnits"
          >
            加载历史观点单元
          </el-button>
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            accept=".csv"
            :on-change="handleReferenceFileChange"
          >
            <el-button plain>
              <el-icon style="margin-right:4px"><UploadFilled /></el-icon>
              {{ referenceFileName || '上传参考 CSV' }}
            </el-button>
          </el-upload>
          <el-button v-if="referenceUnits.length > 0" @click="clearReference">清空参考</el-button>
          <template v-if="units.length > 0">
            <el-button @click="exportCSV">导出 CSV</el-button>
            <el-button @click="saveDraft">保存草稿</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">保存观点单元</el-button>
          </template>
        </div>
      </div>
    </el-card>

    <el-alert
      v-if="hasDraft && units.length === 0 && draftInfo"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>
        <span>发现观点整理草稿：共 {{ draftInfo.count }} 条，保存于 {{ draftInfo.savedAt }}</span>
        <el-button size="small" type="primary" style="margin-left:12px" @click="restoreDraft">恢复草稿</el-button>
        <el-button size="small" style="margin-left:6px" @click="clearDraft">丢弃</el-button>
      </template>
    </el-alert>

    <div class="comparison-grid">
      <el-card shadow="never" class="pane-card reference-pane">
        <template #header>
          <div class="list-header">
            <span class="list-title">上传参考稿</span>
            <span class="list-desc">
              {{ referenceUnits.length > 0 ? `${referenceUnits.length} 条 · 只读对照` : '上传 CSV 后在此显示' }}
            </span>
          </div>
        </template>

        <div v-if="referenceUnits.length > 0" class="reference-list">
          <div
            v-for="(unit, i) in referenceUnits"
            :key="unit.key"
            class="unit-row reference-row"
          >
            <span class="unit-num">{{ i + 1 }}</span>
            <span class="unit-time">{{ fmt(unit.startTime) }}</span>
            <div class="unit-main">
              <span v-if="unit.speaker" class="unit-speaker">{{ unit.speaker }}</span>
              <span class="unit-content">{{ unit.content }}</span>
            </div>
            <span class="unit-actions-placeholder"></span>
          </div>
        </div>

        <el-empty
          v-else
          class="pane-empty"
          :image-size="96"
          description="上传参考 CSV 后在此显示，只用于对照"
        />
      </el-card>

      <el-card shadow="never" class="pane-card working-pane" v-loading="loadingUnits">
        <template #header>
          <div class="list-header">
            <span class="list-title">正式编辑区</span>
            <span class="list-desc">建议加载最新预处理内容；保存后才写入观点单元</span>
          </div>
        </template>

        <div v-if="units.length > 0" class="unit-list">
          <div
            v-for="(unit, i) in units"
            :key="unit.key"
            class="unit-row"
            :class="{ 'is-editing': editingIndex === i, 'is-splitting': splittingIndex === i }"
          >
            <span class="unit-num">{{ i + 1 }}</span>
            <span class="unit-time">{{ fmt(unit.startTime) }}</span>

            <textarea
              v-if="editingIndex === i"
              ref="editInputRef"
              v-model="editingContent"
              class="unit-edit-input"
              rows="2"
              @keydown="onEditKeydown"
              @blur="confirmEdit"
            />

            <div v-else-if="splittingIndex === i" class="split-area">
              <textarea
                ref="splitTextareaRef"
                class="unit-edit-input"
                :value="unit.content"
                rows="2"
              />
              <div class="split-actions">
                <el-button size="small" type="primary" @click="splitAtCursor">在光标处拆分</el-button>
                <el-button size="small" @click="cancelSplit">取消</el-button>
              </div>
            </div>

            <div
              v-else
              class="unit-main editable"
              title="点击编辑"
              @click="startEdit(i)"
            >
              <span class="unit-content">{{ unit.content }}</span>
            </div>

            <div v-if="splittingIndex !== i" class="unit-actions">
              <el-button v-if="editingIndex !== i" link size="small" @click="startEdit(i)">编辑</el-button>
              <el-button link size="small" @click="startSplit(i)">拆分</el-button>
              <el-button link size="small" :disabled="i === units.length - 1" @click="mergeDown(i)">合并↓</el-button>
              <el-button link type="danger" size="small" @click="deleteUnit(i)">删除</el-button>
            </div>
          </div>
        </div>

        <el-empty
          v-else
          class="pane-empty"
          :image-size="96"
          :description="selectedSessionId ? '请加载最新预处理内容，或加载历史观点单元' : '请先选择群组'"
        />
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.header-desc { font-size: 12px; color: #909399; }

.control-card :deep(.el-card__body) { padding: 14px 20px; }
.control-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.control-left { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.control-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.control-item { display: flex; align-items: center; gap: 8px; }
.control-label, .count-text { font-size: 13px; color: #606266; white-space: nowrap; }

.list-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
.list-title { font-size: 14px; font-weight: 600; color: #303133; }
.list-desc { font-size: 12px; color: #909399; }

.comparison-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}
.pane-card :deep(.el-card__body) { padding: 12px; }
.reference-list,
.unit-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: calc(100vh - 330px);
  overflow-y: auto;
}
.unit-row {
  display: grid;
  grid-template-columns: 42px 62px minmax(0, 1fr) 128px;
  align-items: start;
  gap: 8px;
  padding: 11px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
}
.unit-row.is-editing, .unit-row.is-splitting { background: #f8fafc; border-color: #c6e2ff; }
.unit-num { font-size: 13px; color: #909399; font-weight: 600; text-align: right; line-height: 27px; }
.unit-time { font-size: 13px; color: #909399; line-height: 27px; }
.unit-main { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.unit-speaker { font-size: 12px; line-height: 1.2; color: #909399; }
.unit-content { font-size: 16px; color: #303133; line-height: 1.7; word-break: break-word; }
.reference-row { background: #fcfcfd; }
.unit-actions-placeholder { width: 128px; min-height: 1px; }
.editable { cursor: text; }
.unit-actions { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; justify-content: flex-start; }
.unit-edit-input {
  width: 100%;
  min-height: 54px;
  padding: 8px 10px;
  border: 1px solid #409eff;
  border-radius: 6px;
  font-family: inherit;
  font-size: 16px;
  line-height: 1.7;
  resize: vertical;
  box-sizing: border-box;
}
.split-area { display: flex; flex-direction: column; gap: 6px; }
.split-actions { display: flex; gap: 8px; }
.pane-empty { min-height: 320px; display: flex; align-items: center; justify-content: center; }
@media (max-width: 760px) {
  .comparison-grid { grid-template-columns: 1fr; }
  .unit-row { grid-template-columns: 36px 56px minmax(0, 1fr); }
  .unit-actions,
  .unit-actions-placeholder { grid-column: 3; justify-content: flex-start; flex-wrap: wrap; }
  .unit-actions-placeholder { display: none; }
}
</style>
