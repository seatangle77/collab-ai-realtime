<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import { getUtteranceCount, getSessionUtterances, saveTranscriptUtterances } from '../../api/admin/coi-transcript-coding'
import type { AdminGroup, AdminChatSession } from '../../types/admin'

// ── Types ─────────────────────────────────────────────────────────────────────

interface DraftLine {
  key: number
  content: string
  startTime: number | null
  endTime: number | null
}

interface LocalDraft {
  fileName: string
  lines: DraftLine[]
  savedAt: string
}

const FILLER_RE = /^[\s嗯啊哦哈哎呀哟喂呵嘻吧呢是好对、，。！？…—·]+$/
const LINE_RE = /^\[(\d+):(\d+(?:\.\d+)?),(\d+):(\d+(?:\.\d+)?),\d+\]\s+(.+)$/

// ── 群组 / 会话 ────────────────────────────────────────────────────────────────

const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const existingCount = ref(0)
const loadingGroups = ref(false)
const loadingSessions = ref(false)

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

async function onGroupChange() {
  selectedSessionId.value = ''
  existingCount.value = 0
  sessions.value = []
  resetContent()
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  try {
    const res = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = res.items
    if (res.items.length > 0) {
      selectedSessionId.value = res.items[0]!.id
      await checkExistingAndDraft()
    }
  } finally {
    loadingSessions.value = false
  }
}

async function onSessionChange() {
  existingCount.value = 0
  resetContent()
  await checkExistingAndDraft()
}

async function checkExistingAndDraft() {
  if (!selectedSessionId.value) return
  try {
    const res = await getUtteranceCount(selectedSessionId.value)
    existingCount.value = res.count
  } catch {}
  checkDraft()
}

// ── 草稿（localStorage）────────────────────────────────────────────────────────

const hasDraft = ref(false)
const draftInfo = ref<{ fileName: string; savedAt: string; count: number } | null>(null)

function draftKey(sid: string) {
  return `coi_preprocess_draft_${sid}`
}

function checkDraft() {
  if (!selectedSessionId.value) return
  const raw = localStorage.getItem(draftKey(selectedSessionId.value))
  if (!raw) { hasDraft.value = false; draftInfo.value = null; return }
  try {
    const d = JSON.parse(raw) as LocalDraft
    hasDraft.value = true
    draftInfo.value = { fileName: d.fileName, savedAt: d.savedAt, count: d.lines.length }
  } catch {
    hasDraft.value = false
    draftInfo.value = null
  }
}

function saveDraft() {
  if (!selectedSessionId.value || lines.value.length === 0) return
  const draft: LocalDraft = {
    fileName: uploadedFileName.value,
    lines: lines.value,
    savedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  }
  localStorage.setItem(draftKey(selectedSessionId.value), JSON.stringify(draft))
  hasDraft.value = true
  draftInfo.value = { fileName: draft.fileName, savedAt: draft.savedAt, count: draft.lines.length }
  ElMessage.success('草稿已保存到本地')
}

function restoreDraft() {
  if (!selectedSessionId.value) return
  const raw = localStorage.getItem(draftKey(selectedSessionId.value))
  if (!raw) return
  try {
    const d = JSON.parse(raw) as LocalDraft
    lines.value = d.lines
    uploadedFileName.value = d.fileName
    let max = 0
    for (const l of d.lines) { if (l.key > max) max = l.key }
    keyCounter = max
    ElMessage.success(`已恢复草稿：${d.lines.length} 条`)
  } catch {
    ElMessage.error('草稿数据损坏，无法恢复')
  }
}

function clearDraft() {
  if (!selectedSessionId.value) return
  localStorage.removeItem(draftKey(selectedSessionId.value))
  hasDraft.value = false
  draftInfo.value = null
}

// ── 从数据库加载 ───────────────────────────────────────────────────────────────

const loadingFromDB = ref(false)

async function loadFromDB() {
  if (!selectedSessionId.value) return
  loadingFromDB.value = true
  try {
    const res = await getSessionUtterances(selectedSessionId.value)
    if (res.utterances.length === 0) {
      ElMessage.warning('该会话暂无已保存的预处理数据')
      return
    }
    keyCounter = 0
    lines.value = res.utterances.map(u => ({
      key: ++keyCounter,
      content: u.content,
      startTime: u.start_time,
      endTime: null,
    }))
    uploadedFileName.value = '[从数据库加载]'
    ElMessage.success(`已加载 ${lines.value.length} 条，可继续编辑后保存`)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loadingFromDB.value = false
  }
}

// ── 文件解析 ───────────────────────────────────────────────────────────────────

const filterEnabled = ref(true)
const rawLines = ref<DraftLine[]>([])
const uploadedFileName = ref('')
let keyCounter = 0

function parseTime(min: string, sec: string) {
  return parseInt(min, 10) * 60 + parseFloat(sec)
}

function fmt(s: number | null): string {
  if (s == null || isNaN(s)) return '--'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1).padStart(4, '0')
  return `${m}:${sec}`
}

function resetContent() {
  rawLines.value = []
  lines.value = []
  uploadedFileName.value = ''
  editingIndex.value = null
  splittingIndex.value = null
}

function handleFileChange(file: UploadFile) {
  if (!selectedSessionId.value) {
    ElMessage.warning('请先选择群组和会话')
    return
  }
  const raw = file.raw
  if (!raw) return
  uploadedFileName.value = file.name
  const reader = new FileReader()
  reader.onload = evt => {
    keyCounter = 0
    rawLines.value = (evt.target?.result as string)
      .split('\n')
      .map(l => l.trim().match(LINE_RE))
      .filter((m): m is RegExpMatchArray => !!m)
      .map(m => ({
        key: ++keyCounter,
        content: m[5]!.trim(),
        startTime: parseTime(m[1]!, m[2]!),
        endTime: parseTime(m[3]!, m[4]!),
      }))
    applyFilter()
  }
  reader.readAsText(raw, 'utf-8')
}

const lines = ref<DraftLine[]>([])
const removedCount = computed(() => rawLines.value.length - lines.value.length)

function applyFilter() {
  keyCounter = 0
  lines.value = (filterEnabled.value
    ? rawLines.value.filter(l => !FILLER_RE.test(l.content))
    : [...rawLines.value]
  ).map(l => ({ ...l, key: ++keyCounter }))
}

watch(filterEnabled, applyFilter)

// ── 行内编辑 ───────────────────────────────────────────────────────────────────

const editingIndex = ref<number | null>(null)
const editingContent = ref('')
const editInputRef = ref<HTMLTextAreaElement[]>([])

function startEdit(index: number) {
  splittingIndex.value = null
  editingIndex.value = index
  editingContent.value = lines.value[index]!.content
  nextTick(() => {
    const el = editInputRef.value[0]
    el?.focus()
    el?.select()
  })
}

function confirmEdit() {
  if (editingIndex.value === null) return
  const trimmed = editingContent.value.trim()
  if (trimmed) {
    lines.value[editingIndex.value]!.content = trimmed
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

// ── 拆分 ───────────────────────────────────────────────────────────────────────

const splittingIndex = ref<number | null>(null)
const splitTextareaRef = ref<HTMLTextAreaElement[]>([])

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
  const line = lines.value[splittingIndex.value]!
  const fullText = textarea.value  // 用 textarea 当前值（可能已编辑）
  const part1 = fullText.slice(0, pos).trim()
  const part2 = fullText.slice(pos).trim()
  if (!part1 || !part2) {
    ElMessage.warning('光标位置无法拆分，请将光标放在文字中间')
    return
  }
  const newLine: DraftLine = {
    key: ++keyCounter,
    content: part2,
    startTime: line.startTime,
    endTime: line.endTime,
  }
  line.content = part1
  lines.value.splice(splittingIndex.value + 1, 0, newLine)
  splittingIndex.value = null
}

// ── 其他编辑操作 ───────────────────────────────────────────────────────────────

function deleteLine(index: number) {
  lines.value.splice(index, 1)
}

function mergeDown(index: number) {
  if (index >= lines.value.length - 1) return
  const a = lines.value[index]!
  const b = lines.value[index + 1]!
  a.content = a.content + ' ' + b.content
  a.endTime = b.endTime
  lines.value.splice(index + 1, 1)
}

// ── 保存到后端 ─────────────────────────────────────────────────────────────────

const saving = ref(false)

function exportCSV() {
  if (lines.value.length === 0) return
  const header = '序号,时间戳,内容,CoI分类'
  const rows = lines.value.map((l, i) =>
    `${i + 1},${fmt(l.startTime)},"${l.content.replace(/"/g, '""')}",`
  )
  const csv = '﻿' + [header, ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const sessionTitle = sessions.value.find(s => s.id === selectedSessionId.value)?.session_title ?? selectedSessionId.value.slice(0, 8)
  const safeName = sessionTitle.replace(/[/\\:*?"<>|]/g, '_')
  a.download = `coi_utterances_${safeName}_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function handleSave() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  if (lines.value.length === 0) { ElMessage.warning('没有可保存的内容'); return }

  try {
    await ElMessageBox.confirm(
      `将保存 ${lines.value.length} 条预处理话语。${existingCount.value > 0 ? `原有 ${existingCount.value} 条数据将被覆盖。` : ''}确认保存？`,
      '确认保存预处理结果',
      { type: 'warning', confirmButtonText: '保存', cancelButtonText: '取消' },
    )
  } catch { return }

  saving.value = true
  try {
    const payload = lines.value.map((l, i) => ({
      order_index: i + 1,
      content: l.content,
      start_time: l.startTime,
      coi_category: null,
    }))
    const res = await saveTranscriptUtterances(selectedSessionId.value, payload)
    ElMessage.success(`预处理保存成功：${res.saved} 条${res.deleted_previous > 0 ? `，覆盖旧数据 ${res.deleted_previous} 条` : ''}`)
    existingCount.value = res.saved
    clearDraft()
    resetContent()
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
      <h2 class="page-title">CoI 预处理（录音转写）</h2>
      <span class="header-desc">上传腾讯 ASR 的 TXT → 清洗 → 保存，之后到「CoI 编码（录音转写）」完成编码</span>
    </div>

    <!-- 控制栏 -->
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
            <el-tag v-if="existingCount > 0" type="warning" size="small">
              已有 {{ existingCount }} 条，将覆盖
            </el-tag>
            <el-tag v-else-if="selectedSessionId" type="info" size="small">无预处理数据</el-tag>
          </div>
        </div>

        <div class="control-right">
          <template v-if="lines.length > 0">
            <div class="filter-item">
              <el-switch v-model="filterEnabled" size="small" />
              <span class="filter-label">过滤填充词</span>
              <el-tag v-if="filterEnabled && removedCount > 0" type="info" size="small">
                已过滤 {{ removedCount }} 条
              </el-tag>
            </div>
            <span class="count-text">共 {{ lines.length }} 条</span>
          </template>

          <el-button
            v-if="existingCount > 0 && lines.length === 0"
            :loading="loadingFromDB"
            @click="loadFromDB"
          >
            加载已有数据
          </el-button>

          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            accept=".txt"
            :on-change="handleFileChange"
          >
            <el-button :type="lines.length ? 'default' : 'primary'" plain>
              <el-icon style="margin-right:4px"><UploadFilled /></el-icon>
              {{ uploadedFileName || '上传 TXT 文件' }}
            </el-button>
          </el-upload>

          <template v-if="lines.length > 0">
            <el-button @click="exportCSV">导出 CSV</el-button>
            <el-button @click="saveDraft">保存草稿</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">
              保存预处理结果
            </el-button>
          </template>
        </div>
      </div>
    </el-card>

    <!-- 草稿提示 -->
    <el-alert
      v-if="hasDraft && lines.length === 0 && draftInfo"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>
        <span>发现本地草稿：{{ draftInfo.fileName }}，共 {{ draftInfo.count }} 条，保存于 {{ draftInfo.savedAt }}</span>
        <el-button size="small" type="primary" style="margin-left:12px" @click="restoreDraft">恢复草稿</el-button>
        <el-button size="small" style="margin-left:6px" @click="clearDraft">丢弃</el-button>
      </template>
    </el-alert>

    <!-- 话语列表 -->
    <el-card v-if="lines.length > 0" shadow="never">
      <template #header>
        <div class="list-header">
          <span class="list-title">预处理话语列表</span>
          <span class="list-desc">点击文字可编辑；保存后，在「CoI 编码（录音转写）」页逐条打标签</span>
        </div>
      </template>

      <div class="line-list">
        <div
          v-for="(line, i) in lines"
          :key="line.key"
          class="line-row"
          :class="{ 'is-editing': editingIndex === i, 'is-splitting': splittingIndex === i }"
        >
          <span class="line-num">{{ i + 1 }}</span>
          <span class="line-time">{{ fmt(line.startTime) }}</span>

          <!-- 编辑态 -->
          <textarea
            v-if="editingIndex === i"
            ref="editInputRef"
            v-model="editingContent"
            class="line-edit-input"
            rows="2"
            @keydown="onEditKeydown"
            @blur="confirmEdit"
          />

          <!-- 拆分态 -->
          <div v-else-if="splittingIndex === i" class="split-area">
            <textarea
              ref="splitTextareaRef"
              class="line-edit-input"
              :value="line.content"
              rows="2"
            />
            <div class="split-hint">将光标点击到要拆分的位置，然后点「在光标处拆分」</div>
            <div class="split-actions">
              <el-button size="small" type="primary" @click="splitAtCursor">在光标处拆分</el-button>
              <el-button size="small" @click="cancelSplit">取消</el-button>
            </div>
          </div>

          <!-- 展示态 -->
          <span
            v-else
            class="line-content editable"
            @click="startEdit(i)"
            title="点击编辑"
          >{{ line.content }}</span>

          <div v-if="splittingIndex !== i" class="line-actions">
            <el-button v-if="editingIndex !== i" link size="small" @click="startEdit(i)">编辑</el-button>
            <el-button link size="small" @click="startSplit(i)">拆分</el-button>
            <el-button link size="small" :disabled="i === lines.length - 1" @click="mergeDown(i)">合并↓</el-button>
            <el-button link type="danger" size="small" @click="deleteLine(i)">删除</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 空状态 -->
    <el-card v-else shadow="never" class="empty-card">
      <el-empty
        :image-size="120"
        :description="selectedSessionId ? '请上传腾讯 ASR 导出的 TXT 文件' : '请先选择群组'"
      />
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.header-desc { font-size: 13px; color: #909399; }

.control-card :deep(.el-card__body) { padding: 14px 20px; }
.control-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.control-left { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.control-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.control-item { display: flex; align-items: center; gap: 8px; }
.control-label { font-size: 13px; color: #606266; white-space: nowrap; }
.filter-item { display: flex; align-items: center; gap: 6px; }
.filter-label { font-size: 13px; color: #606266; }
.count-text { font-size: 13px; color: #606266; }

.list-header { display: flex; align-items: center; gap: 10px; }
.list-title { font-size: 14px; font-weight: 600; color: #303133; }
.list-desc { font-size: 12px; color: #909399; }

.line-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: calc(100vh - 320px);
  overflow-y: auto;
}
.line-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 13px;
  transition: background 0.12s;
  border: 1px solid transparent;
}
.line-row:hover { background: #f5f7fa; }
.line-row.is-editing { background: #f0f7ff; border-color: #c6e2ff; }
.line-row.is-splitting { background: #fff7e6; border-color: #ffd591; align-items: flex-start; }

.line-num { width: 28px; flex-shrink: 0; text-align: right; font-size: 11px; color: #c0c4cc; font-weight: 600; padding-top: 2px; }
.line-time { width: 46px; flex-shrink: 0; font-size: 11px; color: #909399; padding-top: 2px; }

.line-content { flex: 1; color: #303133; line-height: 1.5; word-break: break-all; }
.line-content.editable { cursor: text; }
.line-content.editable:hover { color: #409eff; }

.line-edit-input {
  flex: 1;
  font-size: 13px;
  font-family: inherit;
  line-height: 1.5;
  color: #303133;
  border: 1px solid #409eff;
  border-radius: 4px;
  padding: 4px 8px;
  resize: vertical;
  outline: none;
  background: #fff;
  word-break: break-all;
}

.split-area { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.split-hint { font-size: 11px; color: #b45309; }
.split-actions { display: flex; gap: 6px; }

.line-actions { display: flex; gap: 2px; flex-shrink: 0; opacity: 0; padding-top: 1px; }
.line-row:hover .line-actions { opacity: 1; }
.line-row.is-editing .line-actions { opacity: 1; }

.empty-card :deep(.el-card__body) { display: flex; align-items: center; justify-content: center; min-height: 300px; }
</style>
