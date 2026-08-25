<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import {
  generateAiCodes,
  getAiCodingItems,
  reviewAiCodingUnits,
  saveAiCodeAdjustments,
  type AiCodingItem,
} from '../../api/admin/coi-ai-coding'
import type { CoiCategory } from '../../api/admin/coi-units'
import type { AdminChatSession, AdminGroup } from '../../types/admin'

interface EditableAiCodingItem extends AiCodingItem {
  selected: boolean
  dirty: boolean
}

const COI_LABELS: Record<CoiCategory, string> = {
  TE: '触发',
  EX: '探索',
  IN: '整合',
  RE: '解决',
  OTHER: '其他（非认知）',
}
const COI_KEYS = Object.keys(COI_LABELS) as CoiCategory[]
const MAX_SELECTION = 20

const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const items = ref<EditableAiCodingItem[]>([])
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const loadingItems = ref(false)
const reviewing = ref(false)
const generating = ref(false)
const saving = ref(false)
const filter = ref<'all' | 'uncoded' | 'coded' | 'adjusted'>('all')

const selectedItems = computed(() => items.value.filter(item => item.selected))
const codedCount = computed(() => items.value.filter(hasAiResult).length)
const dirtyItems = computed(() => items.value.filter(item => item.dirty))
const visibleItems = computed(() => items.value.filter((item) => {
  if (filter.value === 'uncoded') return !hasAiResult(item)
  if (filter.value === 'coded') return hasAiResult(item)
  if (filter.value === 'adjusted') return isAdjusted(item)
  return true
}))

function hasAiResult(item: AiCodingItem): boolean {
  return item.has_ai_result || item.coded_at !== null || item.coding_reason.trim().length > 0
}

onMounted(loadGroups)

async function loadGroups() {
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page_size: 200 })
    groups.value = res.items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
}

async function onGroupChange() {
  selectedSessionId.value = ''
  sessions.value = []
  items.value = []
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  try {
    const res = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = res.items
    if (res.items.length > 0) {
      selectedSessionId.value = res.items[0]!.id
      await loadItems()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

function toEditable(item: AiCodingItem): EditableAiCodingItem {
  return {
    ...item,
    coi_categories: [...item.coi_categories],
    ai_original_categories: [...item.ai_original_categories],
    selected: false,
    dirty: false,
  }
}

async function loadItems() {
  if (!selectedSessionId.value) {
    items.value = []
    return false
  }
  loadingItems.value = true
  try {
    items.value = (await getAiCodingItems(selectedSessionId.value)).map(toEditable)
    if (items.value.length === 0) ElMessage.info('该会话暂无观点单元')
    return true
  } catch (e: any) {
    ElMessage.error(e?.message || '加载 AI 编码失败')
    return false
  } finally {
    loadingItems.value = false
  }
}

async function refreshItems() {
  if (await loadItems()) ElMessage.success('观点单元已刷新')
}

function selectUncoded() {
  let count = 0
  for (const item of items.value) {
    item.selected = !hasAiResult(item) && count < MAX_SELECTION
    if (item.selected) count += 1
  }
  if (items.value.filter(item => !hasAiResult(item)).length > MAX_SELECTION) {
    ElMessage.info(`一次最多选择 ${MAX_SELECTION} 条，已选择前 ${MAX_SELECTION} 条未编码观点`)
  }
}

function clearSelection() {
  for (const item of items.value) item.selected = false
}

function onSelectChange(item: EditableAiCodingItem, value: boolean) {
  if (value && selectedItems.value.length > MAX_SELECTION) {
    item.selected = false
    ElMessage.warning(`一次最多选择 ${MAX_SELECTION} 条`)
  }
}

async function handleReviewUnits() {
  if (!selectedSessionId.value || selectedItems.value.length === 0) {
    ElMessage.warning('请先勾选需要检查的观点')
    return
  }
  const selectedIds = new Set(selectedItems.value.map(item => item.unit_id))
  reviewing.value = true
  try {
    const res = await reviewAiCodingUnits(selectedSessionId.value, [...selectedIds])
    items.value = res.items.map((item) => ({
      ...toEditable(item),
      selected: selectedIds.has(item.unit_id),
    }))
    ElMessage.success(`AI 观点检查完成：${res.saved} 条`)
  } catch (e: any) {
    ElMessage.error(e?.message || 'AI 观点检查失败')
  } finally {
    reviewing.value = false
  }
}

async function handleGenerate() {
  if (!selectedSessionId.value || selectedItems.value.length === 0) {
    ElMessage.warning('请先勾选需要 AI 编码的观点')
    return
  }
  if (dirtyItems.value.length > 0) {
    ElMessage.warning('请先保存当前人工调整，再进行新的 AI 编码')
    return
  }
  const unreviewed = selectedItems.value.filter(item => !item.ai_segmentation_reviewed_at).length
  if (unreviewed > 0) {
    try {
      await ElMessageBox.confirm(
        `所选内容中有 ${unreviewed} 条尚未进行观点单元检查，是否仍然继续编码？`,
        '尚未检查观点单元',
        { type: 'warning', confirmButtonText: '继续编码', cancelButtonText: '先检查' },
      )
    } catch { return }
  }
  const recoded = selectedItems.value.filter(hasAiResult).length
  if (recoded > 0) {
    try {
      await ElMessageBox.confirm(
        `所选内容中有 ${recoded} 条已经存在 AI 编码，继续会重新生成并覆盖当前 C 编码。`,
        '确认重新编码',
        { type: 'warning', confirmButtonText: '继续编码', cancelButtonText: '取消' },
      )
    } catch { return }
  }
  generating.value = true
  try {
    const res = await generateAiCodes(
      selectedSessionId.value,
      selectedItems.value.map(item => item.unit_id),
    )
    items.value = res.items.map(toEditable)
    ElMessage.success(`AI 编码完成：${res.saved} 条`)
  } catch (e: any) {
    ElMessage.error(e?.message || 'AI 编码失败')
  } finally {
    generating.value = false
  }
}

function toggleCategory(item: EditableAiCodingItem, category: CoiCategory) {
  if (category === 'OTHER') {
    item.coi_categories = item.coi_categories.includes('OTHER') ? [] : ['OTHER']
    item.dirty = true
    return
  }
  const selected = new Set(item.coi_categories)
  selected.delete('OTHER')
  if (selected.has(category)) selected.delete(category)
  else selected.add(category)
  item.coi_categories = COI_KEYS.filter(key => selected.has(key))
  item.dirty = true
}

function markReasonDirty(item: EditableAiCodingItem) {
  item.dirty = true
}

function sameCategories(left: CoiCategory[], right: CoiCategory[]): boolean {
  return left.length === right.length && left.every(category => right.includes(category))
}

function isAdjusted(item: EditableAiCodingItem): boolean {
  return hasAiResult(item)
    && !sameCategories(item.coi_categories, item.ai_original_categories)
}

async function handleSaveAdjustments() {
  if (!selectedSessionId.value || dirtyItems.value.length === 0) return
  const invalid = dirtyItems.value.find(item => !item.coding_reason.trim())
  if (invalid) {
    ElMessage.warning(`第 ${invalid.order_index} 条的编码理由不能为空`)
    return
  }
  saving.value = true
  try {
    const res = await saveAiCodeAdjustments(
      selectedSessionId.value,
      dirtyItems.value.map(item => ({
        unit_id: item.unit_id,
        coi_categories: item.coi_categories,
        coding_reason: item.coding_reason.trim(),
      })),
    )
    items.value = res.items.map(toEditable)
    ElMessage.success(`已保存 ${res.saved} 条人工调整`)
  } catch (e: any) {
    ElMessage.error(e?.message || '保存调整失败')
  } finally {
    saving.value = false
  }
}

function fmt(seconds: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) return '--'
  const minutes = Math.floor(seconds / 60)
  const rest = (seconds % 60).toFixed(1).padStart(4, '0')
  return `${minutes}:${rest}`
}

function fmtReviewedAt(value: string | null): string {
  return value ? value.replace('T', ' ').slice(0, 19) : ''
}

function readableSuggestion(value: string): string {
  let readable = value
  for (const item of items.value) {
    readable = readable.split(`[${item.unit_id}]`).join(`第${item.order_index}条`)
    readable = readable.split(item.unit_id).join(`第${item.order_index}条`)
  }
  return readable
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h2 class="page-title">CoI AI 编码员 C</h2>
        <p class="page-desc">可先让 AI 检查观点单元，再进行编码；建议和编码结果均可由研究员判断与调整。</p>
      </div>
    </div>

    <el-card shadow="never">
      <div class="control-bar">
        <div class="control-group">
          <span class="control-label">群组</span>
          <el-select v-model="selectedGroupId" placeholder="选择群组" filterable style="width: 200px" :loading="loadingGroups" @change="onGroupChange">
            <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
          </el-select>
          <span class="control-label">会话</span>
          <el-select v-model="selectedSessionId" placeholder="选择会话" filterable style="width: 240px" :loading="loadingSessions" :disabled="sessions.length === 0" @change="loadItems">
            <el-option v-for="session in sessions" :key="session.id" :label="session.session_title" :value="session.id" />
          </el-select>
        </div>
        <div class="control-group">
          <el-button :disabled="!selectedSessionId" :loading="loadingItems" @click="refreshItems">刷新观点</el-button>
          <el-button :disabled="items.length === 0" @click="selectUncoded">选择未编码</el-button>
          <el-button :disabled="selectedItems.length === 0" @click="clearSelection">清除选择</el-button>
          <el-button type="warning" plain :disabled="selectedItems.length === 0" :loading="reviewing" @click="handleReviewUnits">
            AI 检查观点（{{ selectedItems.length }}）
          </el-button>
          <el-button type="primary" :disabled="selectedItems.length === 0" :loading="generating" @click="handleGenerate">
            AI 编码所选（{{ selectedItems.length }}）
          </el-button>
          <el-button type="success" :disabled="dirtyItems.length === 0" :loading="saving" @click="handleSaveAdjustments">
            保存调整（{{ dirtyItems.length }}）
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card v-if="items.length > 0" shadow="never" v-loading="loadingItems || reviewing || generating">
      <template #header>
        <div class="list-header">
          <span>观点单元：已编码 {{ codedCount }} / {{ items.length }}</span>
          <el-radio-group v-model="filter" size="small">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="uncoded">未编码</el-radio-button>
            <el-radio-button value="coded">已编码</el-radio-button>
            <el-radio-button value="adjusted">分类已调整</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <div class="coding-list">
        <div v-for="item in visibleItems" :key="item.unit_id" class="coding-row" :class="{ 'is-coded': hasAiResult(item), 'is-dirty': item.dirty }">
          <div class="unit-line">
            <el-checkbox v-model="item.selected" @change="onSelectChange(item, Boolean($event))" />
            <span class="unit-index">{{ item.order_index }}</span>
            <span class="unit-time">{{ fmt(item.start_time) }}</span>
            <span class="unit-content">{{ item.content }}</span>
          </div>

          <div v-if="item.ai_segmentation_suggestion" class="segmentation-suggestion">
            <el-tag :type="item.ai_segmentation_suggestion === '无需调整' ? 'success' : 'warning'" size="small">
              观点检查
            </el-tag>
            <span>{{ readableSuggestion(item.ai_segmentation_suggestion) }}</span>
            <span class="suggestion-time">{{ fmtReviewedAt(item.ai_segmentation_reviewed_at) }}</span>
          </div>

          <div v-if="hasAiResult(item)" class="result-area">
            <div class="category-row">
              <span class="field-label">编码</span>
              <el-button
                v-for="category in COI_KEYS"
                :key="category"
                size="small"
                :type="item.coi_categories.includes(category) ? 'primary' : 'default'"
                @click="toggleCategory(item, category)"
              >{{ category }} {{ COI_LABELS[category] }}</el-button>
              <el-tag v-if="item.coi_categories.length === 0" type="info" size="small">不编码</el-tag>
              <el-tag v-if="isAdjusted(item)" type="warning" size="small">
                AI 原始：{{ item.ai_original_categories.join(' / ') || '不编码' }}
              </el-tag>
            </div>
            <div class="reason-row">
              <span class="field-label">理由</span>
              <el-input v-model="item.coding_reason" type="textarea" :rows="2" maxlength="2000" show-word-limit @input="markReasonDirty(item)" />
            </div>
            <div class="result-meta">{{ item.coded_by || 'AI 编码员 C' }}</div>
          </div>
          <div v-else class="uncoded-hint">尚未进行 AI 编码</div>
        </div>
      </div>
    </el-card>

    <el-card v-else shadow="never" v-loading="loadingItems">
      <el-empty :description="selectedSessionId ? '该会话暂无观点单元' : '请先选择群组和会话'" />
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.page-desc { margin: 6px 0 0; color: #909399; font-size: 13px; }
.control-bar { display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; }
.control-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.control-label { color: #606266; font-size: 14px; white-space: nowrap; }
.list-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.coding-list { display: flex; flex-direction: column; gap: 8px; max-height: calc(100vh - 300px); overflow-y: auto; }
.coding-row { border: 1px solid #ebeef5; border-left: 3px solid #dcdfe6; border-radius: 7px; padding: 12px; }
.coding-row.is-coded { border-left-color: #67c23a; }
.coding-row.is-dirty { background: #fffaf0; border-left-color: #e6a23c; }
.unit-line { display: flex; align-items: baseline; gap: 8px; }
.unit-index { width: 28px; color: #909399; font-size: 12px; text-align: right; flex-shrink: 0; }
.unit-time { width: 42px; color: #909399; font-size: 12px; flex-shrink: 0; }
.unit-content { color: #303133; line-height: 1.7; word-break: break-word; }
.segmentation-suggestion { margin: 9px 0 0 72px; display: flex; align-items: flex-start; gap: 8px; color: #606266; font-size: 13px; line-height: 24px; }
.suggestion-time { margin-left: auto; color: #a8abb2; font-size: 12px; white-space: nowrap; }
.result-area { margin: 10px 0 0 72px; display: flex; flex-direction: column; gap: 10px; }
.category-row, .reason-row { display: flex; align-items: flex-start; gap: 8px; flex-wrap: wrap; }
.reason-row :deep(.el-textarea) { flex: 1; min-width: 280px; }
.field-label { width: 38px; color: #606266; font-size: 13px; line-height: 28px; flex-shrink: 0; }
.result-meta { color: #a8abb2; font-size: 12px; padding-left: 46px; }
.uncoded-hint { margin: 8px 0 0 72px; color: #a8abb2; font-size: 13px; }
@media (max-width: 720px) {
  .segmentation-suggestion, .result-area, .uncoded-hint { margin-left: 0; }
  .reason-row :deep(.el-textarea) { min-width: 100%; }
}
</style>
