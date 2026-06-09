<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import {
  listSessionsSummary,
  listCoiUtterances,
  importFromTranscripts,
  updateCoiUtterance,
  deleteCoiUtterance,
  deleteCoiSession,
  mergeCoiUtterances,
  splitCoiUtterance,
  codeCoiUtterance,
  reorderCoiUtterances,
  type CoiUtterance,
  type SessionSummary,
} from '../../api/admin/coi-utterances'
import type { AdminGroup, AdminChatSession } from '../../types/admin'

const COI_LABELS: Record<string, { label: string; color: string }> = {
  TE: { label: '触发', color: '#e6a23c' },
  EX: { label: '探索', color: '#409eff' },
  IN: { label: '整合', color: '#67c23a' },
  RE: { label: '解决', color: '#f56c6c' },
}

function formatCST(iso: string): string {
  const d = new Date(new Date(iso).getTime() + 8 * 60 * 60 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
}

function getDisplayTime(u: CoiUtterance): string {
  if (u.start_time != null) {
    const d = new Date((u.start_time + 8 * 60 * 60) * 1000)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
  }
  return formatCST(u.created_at)
}

// ── 会话 summary 列表 ─────────────────────────────────────────────────────────
const summaries = ref<SessionSummary[]>([])
const loadingSummaries = ref(false)

async function fetchSummaries() {
  loadingSummaries.value = true
  try {
    summaries.value = await listSessionsSummary()
  } catch (e: any) {
    ElMessage.error(e?.message || '加载会话列表失败')
  } finally {
    loadingSummaries.value = false
  }
}

// ── 导入对话框 ────────────────────────────────────────────────────────────────
const importDialogVisible = ref(false)
const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const importGroupId = ref('')
const importSessionId = ref('')
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const importing = ref(false)

async function openImportDialog() {
  importDialogVisible.value = true
  if (groups.value.length > 0) return
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page_size: 200 })
    groups.value = res.items
  } finally {
    loadingGroups.value = false
  }
}

async function onImportGroupChange() {
  importSessionId.value = ''
  sessions.value = []
  if (!importGroupId.value) return
  loadingSessions.value = true
  try {
    const res = await listAdminChatSessions({ group_id: importGroupId.value, page_size: 200 })
    sessions.value = res.items
  } finally {
    loadingSessions.value = false
  }
}

async function handleImport() {
  if (!importSessionId.value) return
  importing.value = true
  try {
    const res = await importFromTranscripts(importSessionId.value)
    ElMessage.success(`导入成功：${res.imported} 条，跳过 ${res.skipped} 条（已存在）`)
    importDialogVisible.value = false
    await fetchSummaries()
    // 如果导入的就是当前打开的会话，刷新发言列表
    if (importSessionId.value === selectedSessionId.value) {
      await fetchUtterances()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

// ── 当前打开的会话 ─────────────────────────────────────────────────────────────
const selectedSessionId = ref('')
const selectedSummary = computed(() =>
  summaries.value.find((s) => s.session_id === selectedSessionId.value) ?? null
)

async function selectSession(summary: SessionSummary) {
  selectedSessionId.value = summary.session_id
  await fetchUtterances()
}

function backToList() {
  selectedSessionId.value = ''
  utterances.value = []
  selected.value.clear()
}

async function handleDeleteSession(summary: SessionSummary, event: Event) {
  event.stopPropagation()
  await ElMessageBox.confirm(
    `确认删除会话「${summary.session_title}」的全部 ${summary.total} 条发言编码数据？此操作不可恢复。`,
    '确认删除',
    { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' },
  )
  try {
    await deleteCoiSession(summary.session_id)
    ElMessage.success('已删除')
    await fetchSummaries()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

// ── 发言单元列表 ───────────────────────────────────────────────────────────────
const utterances = ref<CoiUtterance[]>([])
const loading = ref(false)
const selected = ref<Set<string>>(new Set())

const totalCount = computed(() => utterances.value.length)
const codedCount = computed(() => utterances.value.filter((u) => u.coi_category).length)

function jumpToNextUncoded() {
  const next = utterances.value.find((u) => !u.coi_category)
  if (!next) { ElMessage.success('所有发言已编码完成！'); return }
  const el = document.getElementById(`utterance-${next.id}`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function fetchUtterances() {
  if (!selectedSessionId.value) return
  loading.value = true
  selected.value.clear()
  try {
    utterances.value = await listCoiUtterances(selectedSessionId.value)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// ── 多选 ───────────────────────────────────────────────────────────────────────
function toggleSelect(id: string) {
  if (selected.value.has(id)) {
    selected.value.delete(id)
  } else {
    selected.value.add(id)
  }
}

function selectAll() {
  if (selected.value.size === utterances.value.length) {
    selected.value.clear()
  } else {
    selected.value = new Set(utterances.value.map((u) => u.id))
  }
}

// ── 合并 ───────────────────────────────────────────────────────────────────────
const merging = ref(false)
async function performMerge(ids: string[]) {
  merging.value = true
  try {
    await mergeCoiUtterances(ids)
    ElMessage.success('合并成功')
    await fetchUtterances()
  } catch (e: any) {
    ElMessage.error(e?.message || '合并失败')
  } finally {
    merging.value = false
  }
}

async function handleMerge() {
  if (selected.value.size < 2) {
    ElMessage.warning('请至少选择 2 条发言')
    return
  }
  const selectedIds = utterances.value
    .filter((u) => selected.value.has(u.id))
    .map((u) => u.id)
  await performMerge(selectedIds)
}

async function mergeDown(index: number) {
  const current = utterances.value[index]
  const next = utterances.value[index + 1]
  if (!current || !next) return
  await performMerge([current.id, next.id])
}

// ── 编辑 ───────────────────────────────────────────────────────────────────────
const editingId = ref<string | null>(null)
const editContent = ref('')
const editSpeaker = ref('')

function startEdit(u: CoiUtterance) {
  editingId.value = u.id
  editContent.value = u.content
  editSpeaker.value = u.speaker_name || u.speaker || ''
}

async function saveEdit(u: CoiUtterance) {
  try {
    const updated = await updateCoiUtterance(u.id, {
      content: editContent.value,
      speaker: editSpeaker.value || undefined,
    })
    const idx = utterances.value.findIndex((x) => x.id === u.id)
    if (idx !== -1) utterances.value[idx] = updated
    editingId.value = null
    ElMessage.success('已保存')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

function cancelEdit() {
  editingId.value = null
}

// ── 删除 ───────────────────────────────────────────────────────────────────────
async function handleDelete(u: CoiUtterance) {
  await ElMessageBox.confirm('确认删除此发言单元？', '确认删除', { type: 'warning' })
  try {
    await deleteCoiUtterance(u.id)
    utterances.value = utterances.value.filter((x) => x.id !== u.id)
    selected.value.delete(u.id)
    ElMessage.success('已删除')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

// ── 拆分 ───────────────────────────────────────────────────────────────────────
const splitDialogVisible = ref(false)
const splitTarget = ref<CoiUtterance | null>(null)
const splitText = ref('')
const splitOffset = ref(0)
const splitTextareaRef = ref<HTMLTextAreaElement | null>(null)

function openSplitDialog(u: CoiUtterance) {
  splitTarget.value = u
  splitText.value = u.content
  splitOffset.value = 0
  splitDialogVisible.value = true
}

function onSplitTextareaClick() {
  splitOffset.value = splitTextareaRef.value?.selectionStart ?? 0
}

function onSplitTextareaKeyup() {
  splitOffset.value = splitTextareaRef.value?.selectionStart ?? 0
}

const splitPreviewA = computed(() =>
  splitOffset.value > 0 ? splitText.value.slice(0, splitOffset.value) : '',
)
const splitPreviewB = computed(() =>
  splitOffset.value > 0 ? splitText.value.slice(splitOffset.value) : '',
)

const splitting = ref(false)
async function confirmSplit() {
  if (!splitTarget.value || splitOffset.value <= 0) {
    ElMessage.warning('请先在文本中点击选择拆分位置')
    return
  }
  splitting.value = true
  try {
    const parts = await splitCoiUtterance(splitTarget.value.id, splitOffset.value)
    const idx = utterances.value.findIndex((x) => x.id === splitTarget.value!.id)
    if (idx !== -1) {
      utterances.value.splice(idx, 1, ...parts)
    }
    splitDialogVisible.value = false
    ElMessage.success('拆分成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '拆分失败')
  } finally {
    splitting.value = false
  }
}

// ── CoI 编码 ──────────────────────────────────────────────────────────────────
async function handleCode(u: CoiUtterance, category: 'TE' | 'EX' | 'IN' | 'RE' | null) {
  const newCat = u.coi_category === category ? null : category
  try {
    const updated = await codeCoiUtterance(u.id, newCat)
    const idx = utterances.value.findIndex((x) => x.id === u.id)
    if (idx !== -1) utterances.value[idx] = updated
    // 更新 summary 里的 coded 数
    const s = summaries.value.find((x) => x.session_id === selectedSessionId.value)
    if (s) s.coded = utterances.value.filter((x) => x.coi_category).length
  } catch (e: any) {
    ElMessage.error(e?.message || '编码失败')
  }
}

// ── 上移/下移 ─────────────────────────────────────────────────────────────────
const reordering = ref(false)

async function moveUp(index: number) {
  if (index === 0) return
  const arr = [...utterances.value]
  const tmp = arr[index - 1] as CoiUtterance
  arr[index - 1] = arr[index] as CoiUtterance
  arr[index] = tmp
  await applyReorder(arr)
}

async function moveDown(index: number) {
  if (index === utterances.value.length - 1) return
  const arr = [...utterances.value]
  const tmp = arr[index] as CoiUtterance
  arr[index] = arr[index + 1] as CoiUtterance
  arr[index + 1] = tmp
  await applyReorder(arr)
}

async function applyReorder(arr: CoiUtterance[]) {
  utterances.value = arr
  reordering.value = true
  try {
    await reorderCoiUtterances(arr.map((u, i) => ({ id: u.id, order_index: i + 1 })))
  } catch (e: any) {
    ElMessage.error(e?.message || '排序保存失败')
  } finally {
    reordering.value = false
  }
}

// ── 导出 CSV ──────────────────────────────────────────────────────────────────
function exportCSV() {
  const headers = ['序号', '说话人', '发言内容', 'CoI分类', '分类名称', '发言时间']
  const rows = utterances.value.map((u, index) => {
    const label = u.coi_category ? (COI_LABELS[u.coi_category]?.label ?? u.coi_category) : ''
    const time = getDisplayTime(u)
    return [
      index + 1,
      u.speaker_name || u.speaker || '',
      u.content,
      u.coi_category ?? '',
      label,
      time,
    ]
  })

  const escape = (v: string | number) => {
    const s = String(v)
    return s.includes(',') || s.includes('"') || s.includes('\n')
      ? `"${s.replace(/"/g, '""')}"`
      : s
  }

  const csv = '﻿' + [headers, ...rows].map((r) => r.map(escape).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const title = selectedSummary.value
    ? `${selectedSummary.value.group_name}_${selectedSummary.value.session_title}_CoI编码`
    : 'CoI编码'
  a.href = url
  a.download = `${title}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(fetchSummaries)
</script>

<template>
  <div class="page-container">
    <!-- ── 标题栏 ── -->
    <div class="page-header">
      <div class="header-left">
        <el-button v-if="selectedSessionId" link @click="backToList">← 返回列表</el-button>
        <h2 class="page-title">
          CoI 发言编码
          <span v-if="selectedSummary" class="page-subtitle">
            / {{ selectedSummary.group_name }} · {{ selectedSummary.session_title }}
          </span>
        </h2>
      </div>
      <el-button type="primary" @click="openImportDialog">+ 导入新会话</el-button>
    </div>

    <!-- ── 会话列表视图 ── -->
    <template v-if="!selectedSessionId">
      <el-card shadow="never" v-loading="loadingSummaries">
        <el-empty v-if="!loadingSummaries && summaries.length === 0" description="暂无已导入的会话，点击「导入新会话」开始" />

        <el-table v-else :data="summaries" style="width: 100%" @row-click="selectSession" row-class-name="summary-row">
          <el-table-column prop="group_name" label="群组" width="150" />
          <el-table-column prop="session_title" label="会话" min-width="200" />
          <el-table-column label="进度" width="280">
            <template #default="{ row }">
              <div class="progress-cell">
                <el-progress
                  :percentage="row.total > 0 ? Math.round((row.coded / row.total) * 100) : 0"
                  :stroke-width="8"
                  :color="row.coded === row.total ? '#67c23a' : '#409eff'"
                  style="flex: 1"
                />
                <span class="progress-text">{{ row.coded }} / {{ row.total }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.coded === row.total" type="success" size="small">已完成</el-tag>
              <el-tag v-else-if="row.coded > 0" type="warning" size="small">编码中</el-tag>
              <el-tag v-else type="info" size="small">未开始</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="" width="80">
            <template #default>
              <span class="enter-hint">进入 →</span>
            </template>
          </el-table-column>
          <el-table-column label="" width="60">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="handleDeleteSession(row, $event)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- ── 发言编辑视图 ── -->
    <template v-else>
      <el-card shadow="never">
        <div class="editor-header">
          <div class="editor-stats">
            <el-tag type="info" size="small">共 {{ totalCount }} 条</el-tag>
            <el-tag type="success" size="small">已编码 {{ codedCount }} 条</el-tag>
            <el-tag type="warning" size="small">未编码 {{ totalCount - codedCount }} 条</el-tag>
          </div>
          <div style="display:flex;gap:8px">
            <el-button size="small" plain @click="exportCSV">导出 CSV</el-button>
            <el-button size="small" type="primary" plain @click="jumpToNextUncoded">
              跳到下一条未编码 ↓
            </el-button>
          </div>
        </div>

        <!-- 批量操作行 -->
        <div class="batch-row" v-if="utterances.length > 0">
          <el-checkbox
            :model-value="selected.size === utterances.length && utterances.length > 0"
            :indeterminate="selected.size > 0 && selected.size < utterances.length"
            @change="selectAll"
          >
            全选
          </el-checkbox>
          <el-button
            size="small"
            type="warning"
            :loading="merging"
            :disabled="selected.size < 2"
            @click="handleMerge"
          >
            合并选中 ({{ selected.size }})
          </el-button>
          <div class="legend">
            <span v-for="(v, k) in COI_LABELS" :key="k" class="legend-item">
              <el-tag :color="v.color" effect="dark" size="small">{{ k }}</el-tag>
              {{ v.label }}
            </span>
          </div>
        </div>

        <!-- 列表主体 -->
        <div v-loading="loading" class="utterance-list">
          <el-empty v-if="!loading && utterances.length === 0" description="暂无数据，请点击「导入新会话」重新导入" />

          <div
            v-for="(u, index) in utterances"
            :key="u.id"
            :id="`utterance-${u.id}`"
            class="utterance-item"
            :class="{ 'is-selected': selected.has(u.id), 'is-coded': !!u.coi_category }"
          >
            <!-- 左侧：勾选 + 序号 + 排序 -->
            <div class="item-left">
              <el-checkbox :model-value="selected.has(u.id)" @change="toggleSelect(u.id)" />
              <span class="order-num">{{ index + 1 }}</span>
              <div class="move-btns">
                <el-button link size="small" :disabled="index === 0 || reordering" @click="moveUp(index)">↑</el-button>
                <el-button link size="small" :disabled="index === utterances.length - 1 || reordering" @click="moveDown(index)">↓</el-button>
              </div>
            </div>

            <!-- 中间：说话人 + 内容 -->
            <div class="item-body">
              <div class="item-meta">
                <template v-if="editingId === u.id">
                  <el-input v-model="editSpeaker" size="small" placeholder="说话人" style="width: 120px" />
                </template>
                <template v-else>
                  <span class="speaker-name">{{ u.speaker_name || u.speaker || '未知说话人' }}</span>
                </template>
                <span class="source-count" v-if="u.source_transcript_ids.length > 1">
                  [合并自 {{ u.source_transcript_ids.length }} 条转写]
                </span>
                <span class="created-time">{{ getDisplayTime(u) }}</span>
              </div>

              <template v-if="editingId === u.id">
                <el-input v-model="editContent" type="textarea" :rows="3" style="width: 100%" />
                <div class="edit-actions">
                  <el-button size="small" type="primary" @click="saveEdit(u)">保存</el-button>
                  <el-button size="small" @click="cancelEdit">取消</el-button>
                </div>
              </template>
              <template v-else>
                <div class="item-content">{{ u.content }}</div>
              </template>
            </div>

            <!-- 右侧：CoI 编码 + 操作 -->
            <div class="item-right">
              <div class="code-btns">
                <el-button
                  v-for="(v, k) in COI_LABELS"
                  :key="k"
                  size="small"
                  :type="u.coi_category === k ? 'primary' : 'default'"
                  :style="u.coi_category === k ? `background:${v.color};border-color:${v.color}` : ''"
                  @click="handleCode(u, k as any)"
                >
                  {{ k }}
                </el-button>
              </div>
              <div class="item-ops">
                <el-button
                  link
                  size="small"
                  :disabled="index === utterances.length - 1 || merging"
                  @click="mergeDown(index)"
                >
                  向下合并
                </el-button>
                <el-button link size="small" @click="startEdit(u)">编辑</el-button>
                <el-button link size="small" @click="openSplitDialog(u)">拆分</el-button>
                <el-button link size="small" type="danger" @click="handleDelete(u)">删除</el-button>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </template>

    <!-- ── 导入对话框 ── -->
    <el-dialog v-model="importDialogVisible" title="导入新会话" width="420px">
      <div style="display: flex; flex-direction: column; gap: 12px;">
        <el-select
          v-model="importGroupId"
          placeholder="选择群组"
          style="width: 100%"
          :loading="loadingGroups"
          filterable
          @change="onImportGroupChange"
        >
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>

        <el-select
          v-model="importSessionId"
          placeholder="选择会话"
          style="width: 100%"
          :loading="loadingSessions"
          :disabled="!importGroupId"
          filterable
        >
          <el-option v-for="s in sessions" :key="s.id" :label="s.session_title" :value="s.id" />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" :disabled="!importSessionId" @click="handleImport">
          从转写导入
        </el-button>
      </template>
    </el-dialog>

    <!-- ── 拆分对话框 ── -->
    <el-dialog v-model="splitDialogVisible" title="拆分发言" width="600px">
      <p class="split-tip">在下方文本中点击选择拆分位置（光标所在处），然后点击「确认拆分」。</p>
      <textarea
        ref="splitTextareaRef"
        v-model="splitText"
        class="split-textarea"
        readonly
        @click="onSplitTextareaClick"
        @keyup="onSplitTextareaKeyup"
      />
      <div v-if="splitOffset > 0" class="split-preview">
        <div class="preview-block">
          <div class="preview-label">第一段（前 {{ splitOffset }} 字）</div>
          <div class="preview-content">{{ splitPreviewA }}</div>
        </div>
        <div class="preview-block">
          <div class="preview-label">第二段（剩余）</div>
          <div class="preview-content">{{ splitPreviewB }}</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="splitDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="splitting" :disabled="splitOffset <= 0" @click="confirmSplit">
          确认拆分
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.header-left { display: flex; align-items: center; gap: 8px; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.page-subtitle { font-size: 14px; font-weight: 400; color: #909399; }

/* 会话列表 */
:deep(.summary-row) { cursor: pointer; }
:deep(.summary-row:hover td) { background: #f5f7fa !important; }
.progress-cell { display: flex; align-items: center; gap: 10px; }
.progress-text { font-size: 12px; color: #606266; white-space: nowrap; }
.enter-hint { font-size: 13px; color: #409eff; }

/* 编辑器头部 */
.editor-header { display: flex; align-items: center; justify-content: flex-end; margin-bottom: 12px; }
.editor-stats { display: flex; gap: 8px; }

.batch-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 12px;
}
.legend { display: flex; gap: 10px; margin-left: auto; font-size: 13px; color: #606266; }
.legend-item { display: flex; align-items: center; gap: 4px; }

.utterance-list { display: flex; flex-direction: column; gap: 8px; min-height: 160px; }

.utterance-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px;
  background: #fff;
  transition: border-color 0.2s, background 0.2s;
}
.utterance-item.is-selected { border-color: #409eff; background: #f0f7ff; }
.utterance-item.is-coded { border-left: 3px solid #67c23a; }

.item-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 40px;
}
.order-num { font-size: 12px; color: #909399; font-weight: 600; }
.move-btns { display: flex; flex-direction: column; }

.item-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.item-meta { display: flex; align-items: center; gap: 8px; }
.speaker-name { font-weight: 600; font-size: 13px; color: #303133; }
.source-count { font-size: 11px; color: #909399; }
.created-time { font-size: 11px; color: #c0c4cc; margin-left: auto; }
.item-content { font-size: 14px; color: #303133; line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
.edit-actions { display: flex; gap: 8px; }

.item-right { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; min-width: 160px; }
.code-btns { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; }
.item-ops { display: flex; gap: 4px; }

/* 拆分对话框 */
.split-tip { font-size: 13px; color: #606266; margin-bottom: 10px; }
.split-textarea {
  width: 100%;
  height: 120px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 8px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  cursor: text;
  box-sizing: border-box;
}
.split-preview { display: flex; gap: 12px; margin-top: 12px; }
.preview-block { flex: 1; border: 1px dashed #dcdfe6; border-radius: 4px; padding: 8px; }
.preview-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.preview-content { font-size: 13px; color: #303133; line-height: 1.5; white-space: pre-wrap; word-break: break-all; }
</style>
