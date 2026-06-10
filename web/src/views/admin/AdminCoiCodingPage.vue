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

// ── Types ─────────────────────────────────────────────────────────────────────

type CoiCategory = 'TE' | 'EX' | 'IN' | 'RE'

interface DraftUtterance {
  order_index: number
  content: string
  startTime: number | null
  category: CoiCategory | null
}

const COI_LABELS: Record<CoiCategory, { label: string; color: string; bg: string }> = {
  TE: { label: '触发', color: '#b45309', bg: '#fef3c7' },
  EX: { label: '探索', color: '#1d4ed8', bg: '#dbeafe' },
  IN: { label: '整合', color: '#15803d', bg: '#dcfce7' },
  RE: { label: '解决', color: '#b91c1c', bg: '#fee2e2' },
}

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
})

async function onGroupChange() {
  selectedSessionId.value = ''
  sessions.value = []
  utterances.value = []
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  try {
    const res = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = res.items
    if (res.items.length > 0) {
      selectedSessionId.value = res.items[0].id
      await loadUtterances()
    }
  } finally {
    loadingSessions.value = false
  }
}

async function onSessionChange() {
  utterances.value = []
  await loadUtterances()
}

async function loadUtterances() {
  if (!selectedSessionId.value) return
  loadingUtterances.value = true
  try {
    const res = await getSessionUtterances(selectedSessionId.value)
    if (res.utterances.length === 0) {
      ElMessage.info('该会话暂无预处理数据，请先在「CoI 预处理」页上传并保存')
      return
    }
    utterances.value = res.utterances.map(u => ({
      order_index: u.order_index,
      content: u.content,
      startTime: u.start_time,
      category: (u.coi_category as CoiCategory | null) ?? null,
    }))
    focusedIndex.value = 0
  } catch (e: any) {
    ElMessage.error(e?.message || '加载话语失败')
  } finally {
    loadingUtterances.value = false
  }
}

// ── 编码 ───────────────────────────────────────────────────────────────────────

const utterances = ref<DraftUtterance[]>([])
const focusedIndex = ref(0)
const saving = ref(false)

const focused = computed(() => utterances.value[focusedIndex.value] ?? null)
const codedCount = computed(() => utterances.value.filter(u => u.category).length)
const totalCount = computed(() => utterances.value.length)
const progressPct = computed(() =>
  totalCount.value > 0 ? Math.round((codedCount.value / totalCount.value) * 100) : 0,
)

function fmt(s: number | null): string {
  if (s == null) return '--'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1).padStart(4, '0')
  return `${m}:${sec}`
}

function focusRow(i: number) {
  focusedIndex.value = i
  nextTick(scrollToFocused)
}

function scrollToFocused() {
  document.getElementById(`utt-${focusedIndex.value}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

function codeAndAdvance(cat: CoiCategory) {
  const u = focused.value
  if (!u) return
  u.category = cat
  if (focusedIndex.value < utterances.value.length - 1) {
    focusedIndex.value++
    nextTick(scrollToFocused)
  }
}

function skipNext() {
  if (focusedIndex.value < utterances.value.length - 1) {
    focusedIndex.value++
    nextTick(scrollToFocused)
  }
}

function clearCategory() {
  const u = focused.value
  if (u) u.category = null
}

function handleKeydown(e: KeyboardEvent) {
  if (!utterances.value.length) return
  const tag = (e.target as HTMLElement).tagName
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return
  switch (e.key) {
    case '1': e.preventDefault(); codeAndAdvance('TE'); break
    case '2': e.preventDefault(); codeAndAdvance('EX'); break
    case '3': e.preventDefault(); codeAndAdvance('IN'); break
    case '4': e.preventDefault(); codeAndAdvance('RE'); break
    case '0': e.preventDefault(); skipNext(); break
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

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))

// ── 保存 ───────────────────────────────────────────────────────────────────────

const uncodedCount = computed(() => totalCount.value - codedCount.value)

async function handleSave() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  if (codedCount.value === 0) { ElMessage.warning('还没有已编码的话语'); return }

  try {
    await ElMessageBox.confirm(
      `将保存全部 ${totalCount.value} 条话语（已编码 ${codedCount.value} 条，未编码 ${uncodedCount.value} 条保留为空）。确认保存？`,
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
      <span class="header-desc">键盘：<kbd>1</kbd>TE <kbd>2</kbd>EX <kbd>3</kbd>IN <kbd>4</kbd>RE <kbd>0</kbd>跳过 <kbd>↑↓</kbd>切换</span>
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
            <div class="progress-area">
              <el-progress
                :percentage="progressPct"
                :stroke-width="8"
                style="width: 130px"
                :color="progressPct === 100 ? '#67c23a' : '#409eff'"
              />
              <span class="progress-text">{{ codedCount }} / {{ totalCount }}</span>
            </div>
            <el-button type="primary" :loading="saving" @click="handleSave">
              保存编码结果
            </el-button>
          </template>
        </div>
      </div>
    </el-card>

    <!-- 编码工作区 -->
    <div v-if="totalCount > 0" class="workspace">
      <!-- 左栏：话语列表 -->
      <el-card shadow="never" class="list-card" v-loading="loadingUtterances">
        <template #header>
          <div class="list-header">
            <span class="list-title">话语列表</span>
            <div style="display:flex;gap:6px">
              <el-tag size="small" type="success">已编 {{ codedCount }}</el-tag>
              <el-tag size="small" type="info">未编 {{ totalCount - codedCount }}</el-tag>
            </div>
          </div>
        </template>

        <div class="utterance-list">
          <div
            v-for="(u, i) in utterances"
            :id="`utt-${i}`"
            :key="u.order_index"
            class="utt-row"
            :class="{ 'is-focused': i === focusedIndex, 'is-coded': !!u.category }"
            @click="focusRow(i)"
          >
            <span class="row-num">{{ u.order_index }}</span>
            <span class="row-time">{{ fmt(u.startTime) }}</span>
            <span class="row-content">{{ u.content.length > 36 ? u.content.slice(0, 36) + '…' : u.content }}</span>
            <span
              v-if="u.category"
              class="row-badge"
              :style="{ color: COI_LABELS[u.category].color, background: COI_LABELS[u.category].bg }"
            >{{ u.category }}</span>
          </div>
        </div>
      </el-card>

      <!-- 右栏：当前话语 -->
      <el-card shadow="never" class="focus-card">
        <template v-if="focused">
          <div class="focus-meta">
            <span class="focus-pos">{{ focusedIndex + 1 }} / {{ totalCount }}</span>
            <span class="focus-time">{{ fmt(focused.startTime) }}</span>
            <el-tag
              v-if="focused.category"
              size="small"
              effect="dark"
              :style="{ background: COI_LABELS[focused.category].color, borderColor: COI_LABELS[focused.category].color }"
            >
              {{ focused.category }} · {{ COI_LABELS[focused.category].label }}
            </el-tag>
            <el-tag v-else size="small" type="info">待编码</el-tag>
          </div>

          <div class="focus-content">{{ focused.content }}</div>

          <div class="code-btns">
            <button
              v-for="(v, k) in COI_LABELS"
              :key="k"
              class="code-btn"
              :class="{ 'is-active': focused.category === k }"
              :style="focused.category === k
                ? { background: v.color, borderColor: v.color, color: '#fff' }
                : { borderColor: v.color, color: v.color }"
              @click="codeAndAdvance(k as CoiCategory)"
            >
              <span class="btn-key">{{ { TE: 1, EX: 2, IN: 3, RE: 4 }[k] }}</span>
              <span class="btn-label">{{ k }} {{ v.label }}</span>
            </button>
          </div>

          <div class="aux-row">
            <el-button size="small" @click="skipNext">跳过 →</el-button>
            <el-button v-if="focused.category" size="small" type="warning" plain @click="clearCategory">
              清除编码
            </el-button>
          </div>
        </template>

        <div v-else class="focus-done">所有话语已处理完毕 🎉</div>
      </el-card>
    </div>

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
.progress-area { display: flex; align-items: center; gap: 8px; }
.progress-text { font-size: 13px; font-weight: 500; color: #303133; white-space: nowrap; }

/* 工作区 */
.workspace { display: flex; gap: 16px; align-items: flex-start; }

/* 左栏 */
.list-card { width: 400px; flex-shrink: 0; }
.list-card :deep(.el-card__body) { padding: 0; }
.list-card :deep(.el-card__header) { padding: 12px 16px; }
.list-header { display: flex; align-items: center; justify-content: space-between; }
.list-title { font-size: 14px; font-weight: 600; color: #303133; }

.utterance-list {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.utt-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.12s;
  font-size: 13px;
}
.utt-row:hover { background: #f5f7fa; }
.utt-row.is-focused { background: #ecf5ff; border-color: #409eff; }
.utt-row.is-coded { border-left: 3px solid #67c23a; }
.row-num { width: 24px; flex-shrink: 0; text-align: right; font-size: 11px; color: #c0c4cc; font-weight: 600; }
.row-time { width: 42px; flex-shrink: 0; font-size: 11px; color: #909399; }
.row-content { flex: 1; color: #303133; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.row-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

/* 右栏 */
.focus-card { flex: 1; min-width: 0; position: sticky; top: 16px; }

.focus-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}
.focus-pos { font-size: 13px; font-weight: 600; color: #303133; }
.focus-time { font-size: 12px; color: #909399; flex: 1; }

.focus-content {
  font-size: 16px;
  line-height: 1.75;
  color: #1a202c;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px 18px;
  margin-bottom: 18px;
  min-height: 80px;
  white-space: pre-wrap;
  word-break: break-all;
}

.code-btns { display: flex; gap: 10px; margin-bottom: 14px; }
.code-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 8px;
  border: 2px solid;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.code-btn:hover { opacity: 0.85; transform: translateY(-1px); }
.code-btn.is-active { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
.btn-key { font-size: 11px; opacity: 0.6; font-weight: 600; }
.btn-label { font-size: 14px; font-weight: 700; }

.aux-row { display: flex; gap: 8px; }

.focus-done {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  font-size: 16px;
  color: #67c23a;
  font-weight: 500;
}

.empty-card :deep(.el-card__body) { display: flex; align-items: center; justify-content: center; min-height: 300px; }
</style>
