<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import {
  importCoiUnitsFromPreprocess,
  listCoiUnits,
  saveCoiUnits,
  type CoiUnit,
} from '../../api/admin/coi-units'
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
const importing = ref(false)
const saving = ref(false)
const units = ref<DraftUnit[]>([])
let keyCounter = 0

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

async function importFromPreprocess() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  try {
    await ElMessageBox.confirm(
      '将从预处理结果导入观点单元，并覆盖该会话已有观点单元与新编码结果。确认导入？',
      '确认导入',
      { type: 'warning', confirmButtonText: '导入', cancelButtonText: '取消' },
    )
  } catch { return }

  importing.value = true
  try {
    const res = await importCoiUnitsFromPreprocess(selectedSessionId.value)
    clearCoiDownstreamDrafts(selectedSessionId.value)
    await loadUnits()
    ElMessage.success(`已导入 ${res.imported} 条观点单元`)
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

function fmt(s: number | null): string {
  if (s == null || Number.isNaN(s)) return '--'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1).padStart(4, '0')
  return `${m}:${sec}`
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
      <span class="header-desc">基于预处理转写拆分、合并并确认正式观点单元</span>
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
          <span v-if="selectedSessionId" class="count-text">共 {{ totalCount }} 条</span>
          <el-button
            :disabled="!selectedSessionId"
            :loading="loadingUnits"
            @click="loadUnits"
          >
            加载已有观点单元
          </el-button>
          <el-button
            type="primary"
            plain
            :disabled="!selectedSessionId"
            :loading="importing"
            @click="importFromPreprocess"
          >
            从预处理导入
          </el-button>
          <template v-if="units.length > 0">
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

    <el-card v-if="units.length > 0" shadow="never" v-loading="loadingUnits">
      <template #header>
        <div class="list-header">
          <span class="list-title">观点单元列表</span>
          <span class="list-desc">点击文字可编辑；保存后 A/B/final 编码会重新开始</span>
        </div>
      </template>

      <div class="unit-list">
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

          <span
            v-else
            class="unit-content editable"
            title="点击编辑"
            @click="startEdit(i)"
          >{{ unit.content }}</span>

          <div v-if="splittingIndex !== i" class="unit-actions">
            <el-button v-if="editingIndex !== i" link size="small" @click="startEdit(i)">编辑</el-button>
            <el-button link size="small" @click="startSplit(i)">拆分</el-button>
            <el-button link size="small" :disabled="i === units.length - 1" @click="mergeDown(i)">合并↓</el-button>
            <el-button link type="danger" size="small" @click="deleteUnit(i)">删除</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <el-card v-else shadow="never" class="empty-card" v-loading="loadingUnits">
      <el-empty
        :image-size="120"
        :description="selectedSessionId ? '请从预处理结果导入，或加载已有观点单元' : '请先选择群组'"
      />
    </el-card>
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

.unit-list { display: flex; flex-direction: column; gap: 6px; max-height: calc(100vh - 300px); overflow-y: auto; }
.unit-row {
  display: grid;
  grid-template-columns: 42px 62px minmax(0, 1fr) auto;
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
.unit-content { font-size: 16px; color: #303133; line-height: 1.7; word-break: break-word; }
.editable { cursor: text; }
.unit-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
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
.empty-card { min-height: 320px; display: flex; align-items: center; justify-content: center; }
@media (max-width: 760px) {
  .unit-row { grid-template-columns: 36px 56px minmax(0, 1fr); }
  .unit-actions { grid-column: 3; justify-content: flex-start; flex-wrap: wrap; }
}
</style>
