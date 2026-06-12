<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import {
  getSessionUtterances,
  saveTranscriptUtterances,
} from '../../api/admin/coi-transcript-coding'
import type { AdminGroup, AdminChatSession } from '../../types/admin'

type CoiCategory = 'TE' | 'EX' | 'IN' | 'RE'

interface DraftUtterance {
  key: number
  order_index: number
  content: string
  startTime: number | null
  category: CoiCategory | null
}

interface LocalDraft {
  utterances: DraftUtterance[]
  savedAt: string
}

const COI_LABELS: Record<CoiCategory, { label: string; color: string; bg: string }> = {
  TE: { label: '触发', color: '#b45309', bg: '#fef9ee' },
  EX: { label: '探索', color: '#1d4ed8', bg: '#f0f5ff' },
  IN: { label: '整合', color: '#15803d', bg: '#f0fdf4' },
  RE: { label: '解决', color: '#b91c1c', bg: '#fff5f5' },
}
const COI_KEYS = Object.keys(COI_LABELS) as CoiCategory[]

// ── 群组 / 会话 ────────────────────────────────────────────────────────────────

const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const loadingUtterances = ref(false)

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
  window.addEventListener('keydown', handleKeydown)
})
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))

async function onGroupChange() {
  selectedSessionId.value = ''
  sessions.value = []
  utterances.value = []
  hasDraft.value = false
  draftInfo.value = null
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  try {
    const res = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = res.items
    if (res.items.length > 0) {
      selectedSessionId.value = res.items[0]!.id
      await loadUtterances()
    }
  } finally {
    loadingSessions.value = false
  }
}

async function onSessionChange() {
  utterances.value = []
  hasDraft.value = false
  draftInfo.value = null
  await loadUtterances()
}

let keyCounter = 0

async function loadUtterances() {
  if (!selectedSessionId.value) return
  checkDraft()
  loadingUtterances.value = true
  try {
    const res = await getSessionUtterances(selectedSessionId.value)
    if (res.utterances.length === 0) {
      ElMessage.info('该会话暂无预处理数据，请先在「CoI 预处理」页上传并保存')
      return
    }
    keyCounter = 0
    utterances.value = res.utterances.map(u => ({
      key: ++keyCounter,
      order_index: u.order_index,
      content: u.content,
      startTime: u.start_time,
      category: (u.coi_category as CoiCategory | null) ?? null,
    }))
    focusedIndex.value = 0
    nextTick(scrollToFocused)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载话语失败')
  } finally {
    loadingUtterances.value = false
  }
}

// ── 草稿（localStorage）────────────────────────────────────────────────────────

const hasDraft = ref(false)
const draftInfo = ref<{ savedAt: string; count: number; codedCount: number } | null>(null)

function draftKey(sid: string) {
  return `coi_coding_draft_${sid}`
}

function checkDraft() {
  if (!selectedSessionId.value) return
  const raw = localStorage.getItem(draftKey(selectedSessionId.value))
  if (!raw) { hasDraft.value = false; draftInfo.value = null; return }
  try {
    const d = JSON.parse(raw) as LocalDraft
    hasDraft.value = true
    const coded = d.utterances.filter(u => u.category).length
    draftInfo.value = { savedAt: d.savedAt, count: d.utterances.length, codedCount: coded }
  } catch {
    hasDraft.value = false
    draftInfo.value = null
  }
}

function saveDraft() {
  if (!selectedSessionId.value || utterances.value.length === 0) return
  const draft: LocalDraft = {
    utterances: utterances.value,
    savedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  }
  localStorage.setItem(draftKey(selectedSessionId.value), JSON.stringify(draft))
  hasDraft.value = true
  const coded = utterances.value.filter(u => u.category).length
  draftInfo.value = { savedAt: draft.savedAt, count: utterances.value.length, codedCount: coded }
  ElMessage.success('草稿已保存到本地')
}

function restoreDraft() {
  if (!selectedSessionId.value) return
  const raw = localStorage.getItem(draftKey(selectedSessionId.value))
  if (!raw) return
  try {
    const d = JSON.parse(raw) as LocalDraft
    keyCounter = 0
    for (const u of d.utterances) { if (u.key > keyCounter) keyCounter = u.key }
    utterances.value = d.utterances
    focusedIndex.value = 0
    ElMessage.success(`已恢复草稿：${d.utterances.length} 条，已编码 ${d.utterances.filter(u => u.category).length} 条`)
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

// ── 编码 ───────────────────────────────────────────────────────────────────────

const utterances = ref<DraftUtterance[]>([])
const focusedIndex = ref(0)
const saving = ref(false)

const codedCount = computed(() => utterances.value.filter(u => u.category).length)
const totalCount = computed(() => utterances.value.length)
const progressPct = computed(() =>
  totalCount.value > 0 ? Math.round((codedCount.value / totalCount.value) * 100) : 0,
)

function fmt(s: number | null): string {
  if (s == null || isNaN(s)) return '--'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1).padStart(4, '0')
  return `${m}:${sec}`
}

function scrollToFocused() {
  document.getElementById(`utt-${focusedIndex.value}`)?.scrollIntoView({ behavior: 'auto', block: 'nearest' })
}

function setCategory(index: number, cat: CoiCategory) {
  const u = utterances.value[index]
  if (!u) return
  if (u.category === cat) {
    u.category = null
  } else {
    u.category = cat
    if (index === focusedIndex.value) {
      const next = utterances.value.findIndex((u, i) => i > index && !u.category)
      if (next !== -1) {
        focusedIndex.value = next
        nextTick(scrollToFocused)
      }
    }
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (!utterances.value.length) return
  const tag = (e.target as HTMLElement).tagName
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return
  if (splittingIndex.value !== null) return
  switch (e.key) {
    case '1': e.preventDefault(); codeAndAdvance('TE'); break
    case '2': e.preventDefault(); codeAndAdvance('EX'); break
    case '3': e.preventDefault(); codeAndAdvance('IN'); break
    case '4': e.preventDefault(); codeAndAdvance('RE'); break
    case '0': e.preventDefault(); advance(); break
    case 'ArrowDown':
      e.preventDefault()
      if (focusedIndex.value < utterances.value.length - 1) { focusedIndex.value++; nextTick(scrollToFocused) }
      break
    case 'ArrowUp':
      e.preventDefault()
      if (focusedIndex.value > 0) { focusedIndex.value--; nextTick(scrollToFocused) }
      break
  }
}

function codeAndAdvance(cat: CoiCategory) {
  const u = utterances.value[focusedIndex.value]
  if (!u) return
  u.category = cat
  advance()
}

function advance() {
  if (focusedIndex.value < utterances.value.length - 1) {
    focusedIndex.value++
    nextTick(scrollToFocused)
  }
}

// ── 合并 / 拆分 ────────────────────────────────────────────────────────────────

const splittingIndex = ref<number | null>(null)
const splitTextareaRef = ref<HTMLTextAreaElement[]>([])

function mergeDown(index: number) {
  if (index >= utterances.value.length - 1) return
  const a = utterances.value[index]!
  const b = utterances.value[index + 1]!
  a.content = a.content + ' ' + b.content
  utterances.value.splice(index + 1, 1)
  reorderIndexes()
}

function startSplit(index: number) {
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
  const fullText = textarea.value
  const part1 = fullText.slice(0, pos).trim()
  const part2 = fullText.slice(pos).trim()
  if (!part1 || !part2) {
    ElMessage.warning('光标位置无法拆分，请将光标放在文字中间')
    return
  }
  const line = utterances.value[splittingIndex.value]!
  const newLine: DraftUtterance = {
    key: ++keyCounter,
    order_index: 0,
    content: part2,
    startTime: line.startTime,
    category: null,
  }
  line.content = part1
  utterances.value.splice(splittingIndex.value + 1, 0, newLine)
  splittingIndex.value = null
  reorderIndexes()
}

function reorderIndexes() {
  utterances.value.forEach((u, i) => { u.order_index = i + 1 })
}

// ── 保存 ───────────────────────────────────────────────────────────────────────

async function handleSave() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  if (codedCount.value === 0) { ElMessage.warning('还没有已编码的话语'); return }
  const uncoded = totalCount.value - codedCount.value
  try {
    await ElMessageBox.confirm(
      `将保存全部 ${totalCount.value} 条话语（已编码 ${codedCount.value} 条，未编码 ${uncoded} 条保留为空）。确认保存？`,
      '确认保存编码结果',
      { type: 'warning', confirmButtonText: '保存', cancelButtonText: '取消' },
    )
  } catch { return }
  saving.value = true
  try {
    const payload = utterances.value.map(u => ({
      order_index: u.order_index,
      content: u.content,
      start_time: u.startTime,
      coi_category: u.category,
    }))
    const res = await saveTranscriptUtterances(selectedSessionId.value, payload)
    ElMessage.success(`编码保存成功：${res.saved} 条`)
    clearDraft()
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
      <h2 class="page-title">CoI 编码（录音转写）</h2>
      <span class="header-desc">
        键盘：<kbd>1</kbd>TE <kbd>2</kbd>EX <kbd>3</kbd>IN <kbd>4</kbd>RE <kbd>0</kbd>跳过 <kbd>↑↓</kbd>切换焦点行
      </span>
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
          </div>
        </div>
        <div class="control-right">
          <template v-if="totalCount > 0">
            <el-progress
              :percentage="progressPct"
              :stroke-width="8"
              style="width: 120px"
              :color="progressPct === 100 ? '#67c23a' : '#409eff'"
            />
            <span class="progress-text">{{ codedCount }} / {{ totalCount }}</span>
            <el-button @click="saveDraft">保存草稿</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">保存编码结果</el-button>
          </template>
        </div>
      </div>
    </el-card>

    <!-- 草稿提示 -->
    <el-alert
      v-if="hasDraft && utterances.length === 0 && draftInfo"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>
        <span>发现本地草稿：共 {{ draftInfo.count }} 条，已编码 {{ draftInfo.codedCount }} 条，保存于 {{ draftInfo.savedAt }}</span>
        <el-button size="small" type="primary" style="margin-left:12px" @click="restoreDraft">恢复草稿</el-button>
        <el-button size="small" style="margin-left:6px" @click="clearDraft">丢弃</el-button>
      </template>
    </el-alert>

    <!-- 话语列表（行内编码） -->
    <el-card v-if="totalCount > 0" shadow="never" v-loading="loadingUtterances">
      <template #header>
        <div class="list-header">
          <span class="list-title">话语列表</span>
          <div style="display:flex;gap:6px">
            <el-tag size="small" type="success">已编 {{ codedCount }}</el-tag>
            <el-tag size="small" type="info">未编 {{ totalCount - codedCount }}</el-tag>
          </div>
        </div>
      </template>

      <div class="utt-list">
        <div
          v-for="(u, i) in utterances"
          :id="`utt-${i}`"
          :key="u.key"
          class="utt-row"
          :class="{ 'is-focused': i === focusedIndex, 'is-coded': !!u.category, 'is-splitting': splittingIndex === i }"
          @click="splittingIndex === null && (focusedIndex = i)"
        >
          <!-- 拆分模式 -->
          <template v-if="splittingIndex === i">
            <div class="split-area">
              <div class="utt-meta">
                <span class="utt-num">{{ u.order_index }}</span>
                <span class="utt-time">{{ fmt(u.startTime) }}</span>
              </div>
              <textarea
                ref="splitTextareaRef"
                class="split-input"
                :value="u.content"
                rows="3"
              />
              <div class="split-hint">将光标点击到要拆分的位置，然后点「在光标处拆分」</div>
              <div class="split-actions">
                <el-button size="small" type="primary" @click.stop="splitAtCursor">在光标处拆分</el-button>
                <el-button size="small" @click.stop="cancelSplit">取消</el-button>
              </div>
            </div>
          </template>

          <!-- 正常模式 -->
          <template v-else>
            <div class="utt-top">
              <span class="utt-num">{{ u.order_index }}</span>
              <span class="utt-time">{{ fmt(u.startTime) }}</span>
              <span class="utt-content">{{ u.content }}</span>
            </div>
            <div class="utt-bottom">
              <div class="utt-btns">
                <button
                  v-for="cat in COI_KEYS"
                  :key="cat"
                  class="cat-btn"
                  :class="{ 'is-active': u.category === cat }"
                  :style="u.category === cat
                    ? { background: COI_LABELS[cat].color, borderColor: COI_LABELS[cat].color, color: '#fff' }
                    : { borderColor: COI_LABELS[cat].color, color: COI_LABELS[cat].color, background: COI_LABELS[cat].bg }"
                  @click.stop="setCategory(i, cat)"
                >{{ cat }} {{ COI_LABELS[cat].label }}</button>
                <button
                  v-if="u.category"
                  class="clear-btn"
                  @click.stop="u.category = null"
                >✕</button>
              </div>
              <div v-if="i === focusedIndex" class="edit-btns">
                <el-button link size="small" @click.stop="startSplit(i)">拆分</el-button>
                <el-button link size="small" :disabled="i === utterances.length - 1" @click.stop="mergeDown(i)">合并↓</el-button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </el-card>

    <!-- 空状态 -->
    <el-card v-else shadow="never" class="empty-card" v-loading="loadingUtterances">
      <el-empty
        :image-size="120"
        :description="selectedSessionId ? '该会话暂无预处理数据，请先完成预处理' : '请先选择群组'"
      />
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.header-desc { font-size: 12px; color: #909399; }
.header-desc kbd {
  display: inline-block;
  padding: 1px 5px;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
  background: #f5f7fa;
  font-size: 11px;
  margin: 0 2px;
}

.control-card :deep(.el-card__body) { padding: 14px 20px; }
.control-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.control-left { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.control-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.control-item { display: flex; align-items: center; gap: 8px; }
.control-label { font-size: 13px; color: #606266; white-space: nowrap; }
.progress-text { font-size: 13px; font-weight: 500; color: #303133; white-space: nowrap; }

.list-header { display: flex; align-items: center; justify-content: space-between; }
.list-title { font-size: 14px; font-weight: 600; color: #303133; }

.utt-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}

.utt-row {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1.5px solid transparent;
  cursor: pointer;
  transition: all 0.12s;
  background: #fff;
}
.utt-row:hover { background: #f8fafc; }
.utt-row.is-focused { border-color: #409eff; background: #f0f7ff; }
.utt-row.is-coded { border-left: 3px solid #67c23a; }
.utt-row.is-focused.is-coded { border-color: #409eff; border-left-color: #409eff; }
.utt-row.is-splitting { border-color: #f59e0b; background: #fff7e6; cursor: default; }

.utt-top {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}
.utt-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.utt-num {
  font-size: 11px;
  color: #c0c4cc;
  font-weight: 600;
  flex-shrink: 0;
  width: 24px;
  text-align: right;
}
.utt-time {
  font-size: 11px;
  color: #909399;
  flex-shrink: 0;
  width: 40px;
}
.utt-content {
  font-size: 13px;
  color: #303133;
  line-height: 1.6;
  word-break: break-all;
}

.utt-btns {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-left: 72px;
}

.edit-btns {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.cat-btn {
  padding: 3px 12px;
  border: 1.5px solid;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.12s;
  line-height: 1.6;
}
.cat-btn:hover { opacity: 0.8; }
.cat-btn.is-active { box-shadow: 0 2px 6px rgba(0,0,0,0.15); }

.clear-btn {
  padding: 3px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 5px;
  font-size: 11px;
  color: #909399;
  background: #fff;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.12s;
}
.clear-btn:hover { color: #f56c6c; border-color: #f56c6c; }

.split-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.utt-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.split-input {
  font-size: 13px;
  font-family: inherit;
  line-height: 1.5;
  color: #303133;
  border: 1px solid #f59e0b;
  border-radius: 4px;
  padding: 6px 8px;
  resize: vertical;
  outline: none;
  background: #fff;
  word-break: break-all;
}
.split-hint { font-size: 11px; color: #b45309; }
.split-actions { display: flex; gap: 6px; }

.empty-card :deep(.el-card__body) { display: flex; align-items: center; justify-content: center; min-height: 300px; }
</style>
