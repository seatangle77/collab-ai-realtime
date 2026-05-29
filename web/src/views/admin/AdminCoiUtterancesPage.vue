<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import {
  listCoiUtterances,
  importFromTranscripts,
  updateCoiUtterance,
  deleteCoiUtterance,
  mergeCoiUtterances,
  splitCoiUtterance,
  codeCoiUtterance,
  reorderCoiUtterances,
  type CoiUtterance,
} from '../../api/admin/coi-utterances'
import type { AdminGroup, AdminChatSession } from '../../types/admin'

const COI_LABELS: Record<string, { label: string; color: string }> = {
  TE: { label: '触发', color: '#e6a23c' },
  EX: { label: '探索', color: '#409eff' },
  IN: { label: '整合', color: '#67c23a' },
  RE: { label: '解决', color: '#f56c6c' },
}

// ── 选择器 ────────────────────────────────────────────────────────────────────
const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const loadingGroups = ref(false)
const loadingSessions = ref(false)

async function fetchGroups() {
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page_size: 200 })
    groups.value = res.items
  } finally {
    loadingGroups.value = false
  }
}

async function fetchSessions() {
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  selectedSessionId.value = ''
  utterances.value = []
  try {
    const res = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = res.items
  } finally {
    loadingSessions.value = false
  }
}

// ── 发言单元列表 ───────────────────────────────────────────────────────────────
const utterances = ref<CoiUtterance[]>([])
const loading = ref(false)
const selected = ref<Set<string>>(new Set())

const totalCount = computed(() => utterances.value.length)
const codedCount = computed(() => utterances.value.filter((u) => u.coi_category).length)

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

// ── 导入 ───────────────────────────────────────────────────────────────────────
const importing = ref(false)
async function handleImport() {
  if (!selectedSessionId.value) return
  importing.value = true
  try {
    const res = await importFromTranscripts(selectedSessionId.value)
    ElMessage.success(`导入成功：${res.imported} 条，跳过 ${res.skipped} 条（已存在）`)
    await fetchUtterances()
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  } finally {
    importing.value = false
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
async function handleMerge() {
  if (selected.value.size < 2) {
    ElMessage.warning('请至少选择 2 条发言')
    return
  }
  const selectedIds = utterances.value
    .filter((u) => selected.value.has(u.id))
    .map((u) => u.id)

  await ElMessageBox.confirm(`合并选中的 ${selectedIds.length} 条发言？合并后无法自动撤销。`, '确认合并', {
    type: 'warning',
  })

  merging.value = true
  try {
    await mergeCoiUtterances(selectedIds)
    ElMessage.success('合并成功')
    await fetchUtterances()
  } catch (e: any) {
    ElMessage.error(e?.message || '合并失败')
  } finally {
    merging.value = false
  }
}

// ── 编辑 ───────────────────────────────────────────────────────────────────────
const editingId = ref<string | null>(null)
const editContent = ref('')
const editSpeaker = ref('')

function startEdit(u: CoiUtterance) {
  editingId.value = u.id
  editContent.value = u.content
  editSpeaker.value = u.speaker || ''
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

onMounted(fetchGroups)
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">CoI 发言编码</h2>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never">
      <div class="toolbar-row">
        <div class="toolbar-left">
          <el-select
            v-model="selectedGroupId"
            placeholder="选择群组"
            style="width: 180px"
            :loading="loadingGroups"
            filterable
            data-testid="coi-group-select"
            @change="fetchSessions"
          >
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>

          <el-select
            v-model="selectedSessionId"
            placeholder="选择会话"
            style="width: 220px"
            :loading="loadingSessions"
            :disabled="!selectedGroupId"
            filterable
            data-testid="coi-session-select"
            @change="fetchUtterances"
          >
            <el-option v-for="s in sessions" :key="s.id" :label="s.session_title" :value="s.id" />
          </el-select>

          <el-button type="primary" :loading="importing" :disabled="!selectedSessionId" @click="handleImport">
            从转写导入
          </el-button>
        </div>

        <div class="toolbar-right" v-if="utterances.length > 0">
          <el-tag type="info" size="small">共 {{ totalCount }} 条</el-tag>
          <el-tag type="success" size="small">已编码 {{ codedCount }} 条</el-tag>
          <el-tag type="warning" size="small">未编码 {{ totalCount - codedCount }} 条</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 发言列表 -->
    <el-card shadow="never">
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
        <el-empty v-if="!selectedSessionId" description="请先选择群组和会话" />
        <el-empty v-else-if="!loading && utterances.length === 0" description="暂无数据，请点击「从转写导入」" />

        <div
          v-for="(u, index) in utterances"
          :key="u.id"
          class="utterance-item"
          :class="{ 'is-selected': selected.has(u.id), 'is-coded': !!u.coi_category }"
        >
          <!-- 左侧：勾选 + 序号 + 排序 -->
          <div class="item-left">
            <el-checkbox :model-value="selected.has(u.id)" @change="toggleSelect(u.id)" />
            <span class="order-num">{{ u.order_index }}</span>
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
                <span class="speaker-name">{{ u.speaker || '未知说话人' }}</span>
              </template>
              <span class="source-count" v-if="u.source_transcript_ids.length > 1">
                [合并自 {{ u.source_transcript_ids.length }} 条转写]
              </span>
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
              <el-button link size="small" @click="startEdit(u)">编辑</el-button>
              <el-button link size="small" @click="openSplitDialog(u)">拆分</el-button>
              <el-button link size="small" type="danger" @click="handleDelete(u)">删除</el-button>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 拆分对话框 -->
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
.page-title { margin: 0; font-size: 18px; font-weight: 600; }

.toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.toolbar-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }

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
